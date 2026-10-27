"""A local OpenAI-style chat endpoint answered by Claude through the Claude Code CLI.

The benchmark runners speak the OpenAI chat API (AgentDojo's OpenAI element, the rules
pilot, Inspect's OpenAI-compatible provider). This serves that API on localhost and
answers each request with one ``claude -p`` call, so a frontier model runs the same
agent loop, the same system prompts and the same tools as every other model here.
Claude acts as the model and nothing else:

- ``--system-prompt`` replaces Claude Code's own system prompt with the request's;
- ``--tools ""`` and ``--strict-mcp-config`` leave it no tool of its own: no shell,
  no files, no MCP server;
- ``--permission-mode default`` keeps the user's auto-mode note out of the context;
- ``--no-session-persistence``, and an empty working directory, keep each call
  independent and free of any project's instructions.

Claude Code still attaches about 500 tokens of its own context to the first message:
the account's email, the working directory, the date and the model's name. The
benchmark page says so.

**Tools are written into the prompt, not sent as API tools.** The CLI has no way to
take a caller's tool definitions, so each tool's name, description and JSON schema go
into the system prompt verbatim, and the model calls one by writing
``<tool_calls>[{"name": ..., "arguments": {...}}]</tool_calls>``. The runners see an
ordinary OpenAI response with ``tool_calls``. That is a difference from the other
models, which receive tools natively, and it is disclosed with every result.
Temperature cannot be set through the CLI; it is the CLI's default.

    python bench/claude_provider.py --model sonnet --port 8799 --concurrency 4

Then point a runner's OpenAI base URL at ``http://127.0.0.1:8799/v1``. Every call is
logged to ``results/bench/claude_provider_calls.jsonl``: tokens, seconds, the model
the CLI reports, and whether the reply parsed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

LOG = Path(__file__).resolve().parent.parent / "results" / "bench" / "claude_provider_calls.jsonl"
_TOOL_CALLS = re.compile(r"<tool_calls>\s*(.*?)\s*</tool_calls>", re.S)

PROTOCOL = """

# Tools

You can call the tools below. Each is given as its name, its description and the JSON
schema of its arguments. To call one or more, reply with nothing but:

<tool_calls>[{"name": "<tool name>", "arguments": {<arguments matching its schema>}}]</tool_calls>

The results will come back in the next message. To answer without calling a tool,
reply with plain text and no <tool_calls> block. Never describe a tool call in prose
instead of making it.

"""


def _text(content: Any) -> str:
    """An OpenAI message's content, whether a string or a list of parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))


def _system(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> str:
    system = "\n\n".join(_text(m.get("content")) for m in messages if m["role"] == "system")
    if not tools:
        return system
    listing = "\n\n".join(
        json.dumps(
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "parameters": t["function"].get("parameters", {}),
            },
            ensure_ascii=False,
        )
        for t in tools
        if t.get("type") == "function"
    )
    return system + PROTOCOL + listing


def _transcript(messages: list[dict[str, Any]]) -> str:
    """Everything but the system prompt, as one message the model continues from."""
    names: dict[str, str] = {}
    parts: list[str] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "user":
            parts.append(f"## user\n\n{_text(m.get('content'))}")
        elif role == "assistant":
            body = _text(m.get("content"))
            calls = []
            for call in m.get("tool_calls") or []:
                names[call["id"]] = call["function"]["name"]
                try:
                    arguments = json.loads(call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = call["function"].get("arguments")
                calls.append({"name": call["function"]["name"], "arguments": arguments})
            if calls:
                body += f"\n<tool_calls>{json.dumps(calls, ensure_ascii=False)}</tool_calls>"
            parts.append(f"## assistant (you)\n\n{body.strip()}")
        elif role == "tool":
            name = names.get(m.get("tool_call_id", ""), "tool")
            parts.append(f"## result of {name}\n\n{_text(m.get('content'))}")
    parts.append(
        "## your turn\n\nReply as the assistant: plain text for the user, or a <tool_calls> block."
    )
    return "\n\n".join(parts)


class SubscriptionLimit(Exception):
    """The Claude account is out of quota for now. Not this request's fault, and not
    retried: every later request would fail the same way until it resets or the CLI
    is logged in to another account, so the caller is told at once, as a 402."""


# What the CLI says when the account, not the request, is the problem (2026-10-25:
# "You've hit your session limit · resets 5:40am"). Lowercased.
_LIMIT_WORDS = (
    "session limit",
    "usage limit",
    "rate limit",
    "credit balance",
    "out of extra usage",
)
# Any "You've hit your <period> limit": the weekly one ("You've hit your weekly limit
# · resets Oct 26, 10pm", 2026-10-25) was missed by the list above, so a run kept
# scheduling episodes that could only fail.
_HIT_LIMIT = re.compile(r"hit your [\w-]+ limit")


def _is_limit(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _LIMIT_WORDS) or bool(_HIT_LIMIT.search(lowered))


def _parse(result: str) -> tuple[str, list[dict[str, Any]], bool]:
    """``(text, tool calls, parsed)`` from the model's reply."""
    match = _TOOL_CALLS.search(result)
    if not match:
        return result.strip(), [], True
    try:
        calls = json.loads(match.group(1))
        if isinstance(calls, dict):
            calls = [calls]
        out = [
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {
                    "name": str(c["name"]),
                    "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False),
                },
            }
            for c in calls
        ]
        text = (result[: match.start()] + result[match.end() :]).strip()
        return text, out, True
    except (json.JSONDecodeError, KeyError, TypeError):
        return result.strip(), [], False


class Provider:
    def __init__(
        self,
        model: str,
        concurrency: int,
        effort: str | None,
        simulate_limit: tuple[int, float] | None = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.slots = threading.Semaphore(concurrency)
        self.cwd = tempfile.mkdtemp(prefix="claude-provider-")
        self.log_lock = threading.Lock()
        LOG.parent.mkdir(parents=True, exist_ok=True)
        # (after this many requests, refuse every request for this many seconds)
        self.simulate_limit = simulate_limit
        self.requests = 0
        self.limited_until: float | None = None

    def _simulated_limit(self) -> None:
        """A rehearsal of a subscription limit, for testing a runner's stop and resume."""
        if self.simulate_limit is None:
            return
        with self.log_lock:
            self.requests += 1
            after, seconds = self.simulate_limit
            if self.limited_until is None and self.requests > after:
                self.limited_until = time.time() + seconds
            if self.limited_until is not None and time.time() < self.limited_until:
                resets = time.strftime("%I:%M%p", time.localtime(self.limited_until)).lower()
                raise SubscriptionLimit(
                    f"claude subscription limit: You've hit your session limit · resets "
                    f"{resets.lstrip('0')} (simulated)"
                )

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        self._simulated_limit()
        messages = request.get("messages", [])
        tools = request.get("tools") or []
        # Both can run to hundreds of kilobytes with a big tool set, past what an
        # argument list holds, so the prompt goes in on stdin and the system prompt
        # through a file.
        system_file = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", dir=self.cwd, delete=False, encoding="utf-8"
        )
        system_file.write(_system(messages, tools))
        system_file.close()
        prompt = _transcript(messages)
        command = [
            "claude",
            "-p",
            "--model",
            self.model,
            "--system-prompt-file",
            system_file.name,
            "--tools",
            "",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--permission-mode",
            "default",
            "--output-format",
            "json",
        ]
        if self.effort:
            command += ["--effort", self.effort]
        started = time.time()
        empty = 0
        with self.slots:
            for attempt in range(3):
                done = subprocess.run(
                    command,
                    cwd=self.cwd,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                try:
                    reply = json.loads(done.stdout)
                except json.JSONDecodeError:
                    reply = {"is_error": True, "result": (done.stderr or done.stdout)[:500]}
                if reply.get("is_error") and _is_limit(str(reply.get("result", ""))):
                    break  # retrying cannot help; the caller stops and resumes later
                if not reply.get("is_error"):
                    text, calls, parsed = _parse(str(reply.get("result", "")))
                    # An empty reply is neither an answer nor a call, and τ²-bench
                    # refuses the message outright (twice on 2026-10-24, one on
                    # each arm). Asked again, the model answers.
                    if text or calls:
                        break
                    empty += 1
                time.sleep(5 * (attempt + 1))
        Path(system_file.name).unlink(missing_ok=True)
        if reply.get("is_error"):
            detail = str(reply.get("result"))[:300]
            if _is_limit(detail):
                raise SubscriptionLimit(f"claude subscription limit: {detail}")
            raise RuntimeError(f"claude -p failed: {detail}")
        usage = reply.get("usage") or {}
        prompt_tokens = (
            usage.get("input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
        )
        with self.log_lock, LOG.open("a") as log:
            log.write(
                json.dumps(
                    {
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "model": list((reply.get("modelUsage") or {}).keys()),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": usage.get("output_tokens", 0),
                        "seconds": round(time.time() - started, 1),
                        "tool_calls": len(calls),
                        "parsed": parsed,
                        "empty_replies_retried": empty,
                        "cost_usd_at_api_prices": reply.get("total_cost_usd"),
                    }
                )
                + "\n"
            )
        message: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            message["tool_calls"] = calls
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.get("model", self.model),
            "choices": [
                {
                    "index": 0,
                    "message": message,
                    "finish_reason": "tool_calls" if calls else "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": prompt_tokens + usage.get("output_tokens", 0),
            },
        }


def serve(provider: Provider, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if not self.path.rstrip("/").endswith("/chat/completions"):
                self.send_error(404)
                return
            request = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            try:
                body, status = provider.complete(request), 200
            except SubscriptionLimit as exc:  # the account, like a provider out of credit
                body = {"error": {"message": str(exc), "type": "insufficient_quota"}}
                status = 402
            except Exception as exc:  # reported to the caller as the API would
                body, status = {"error": {"message": str(exc), "type": "server_error"}}, 500
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_: Any) -> None:
            pass

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--port", type=int, default=8799)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--effort", default=None, help="low, medium, high; the CLI's default if unset")
    ap.add_argument(
        "--simulate-limit",
        nargs=2,
        type=float,
        metavar=("AFTER", "SECONDS"),
        help="rehearse a limit: after AFTER requests, refuse every request for SECONDS",
    )
    args = ap.parse_args()
    print(f"serving {args.model} on http://127.0.0.1:{args.port}/v1", flush=True)
    limit = (int(args.simulate_limit[0]), args.simulate_limit[1]) if args.simulate_limit else None
    serve(Provider(args.model, args.concurrency, args.effort, limit), args.port)


if __name__ == "__main__":
    main()
