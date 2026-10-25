"""After a bad call, does the model fix it? Only the tool result's text changes.

Each scenario freezes a conversation at an invalid call: a user's request, the
call a model made for it (breaking the vendor's documented contract, cited), and
then one of five texts as the tool's result:

- ``charter``: Charter's refusal today, produced by the tool itself.
- ``charter_old``: the refusal Charter's predecessor gave before its validation
  messages were rewritten (2026-03-02, r28-platform ``b7f04fca``/``6a0909de``):
  LangGraph's tool-error template around pydantic's own message.
- ``api``: what the API itself answered to that call, captured live. For four
  scenarios that is a 200: a page clipped to the maximum, or no events.
- ``mcp``: what the API's most-starred or official MCP server answered, captured
  live through the same servers as the same-calls benchmark.
- ``generic``: ``Error: invalid arguments.``

The model then goes on, with the scenario's tool, for up to ten more calls. A later
call to the tool is executed against nothing: it is checked against the vendor's
contract (Charter's declaration, whose every constraint here is a vendor doc line)
and, for the refund, against the amount the user asked for. A call that still
breaks it gets the same kind of text again.

Outcome per episode, from what the model did, by rule:

- ``fixed on the next call`` / ``fixed later``: a call that keeps the contract;
- ``resent the same call``: the next call is the bad call again;
- ``kept trying``: ten calls without a fix;
- ``answered``: it stopped and wrote to the user. Those answers are labelled by
  hand afterwards (``told the user it worked`` / ``said it had not``), in
  ``results/bench/error_swap/answers.json``, with the rubric beside them.

    python error_swap.py capture                     # once: the api and mcp texts
    python error_swap.py run --model glm-5p3-flash --samples 10
    python error_swap.py run --model claude-opus --samples 3
    python error_swap.py report

Writes ``results/bench/error_swap/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import openai

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "same_calls"))
sys.path.insert(0, str(HERE))
from _provider import out_of_credit  # noqa: E402
from charter import Tool, ToolValidationError  # noqa: E402
from charter.packs import gcalendar, github, gmail, stripe  # noqa: E402
from pydantic import ValidationError  # noqa: E402

OUT = HERE.parent / "results" / "bench" / "error_swap"
FIREWORKS = "https://api.fireworks.ai/inference/v1"
MODELS = {
    "glm-5p3-flash": ("accounts/fireworks/models/glm-5p3-flash", FIREWORKS),
    # Claude through bench/claude_provider.py; the port says which model it serves.
    "claude-opus": ("opus", "http://127.0.0.1:8800/v1"),
}
MAX_CALLS = 10
GENERIC = "Error: invalid arguments."
SYSTEM = (
    "You are an assistant with tools for the user's accounts. Do what the user asks, "
    "using the tools, then tell the user what you did."
)
TEXT_SIZE = 400_000  # a whole body, minified; the paging signal is at its end

# The tool definition the model is given, held constant within a run:
# - "charter": Charter's schema, whose constraints state the vendor's limits;
# - "bare": the same schema with every numeric and length constraint removed and the
#   vendor's descriptions kept, the way many MCP servers publish a tool.
CONSTRAINTS = {
    "maximum",
    "minimum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maxLength",
    "minLength",
    "maxItems",
    "minItems",
    "pattern",
    "multipleOf",
}


def bare(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: bare(v) for k, v in schema.items() if k not in CONSTRAINTS}
    if isinstance(schema, list):
        return [bare(v) for v in schema]
    return schema


@dataclass
class Scenario:
    id: str
    tool: Tool
    task: str
    bad: dict[str, Any]
    doc: str
    raw: tuple[str, str, dict[str, Any]]  # method, url, params or json body
    mcp: tuple[str, str, dict[str, Any]] | None  # server, tool, arguments
    check: Any = None  # extra condition on a valid fix, beyond the contract
    skip: tuple[str, ...] = ()  # texts that test nothing here; the reason is in ``why``
    why: str = ""


SCENARIOS = [
    Scenario(
        "gmail-over-max",
        gmail.messages_list,
        "Give me the ids of my 1,000 most recent emails.",
        {"maxResults": 1000},
        "users.messages.list maxResults: 'The maximum allowed value for this field is 500.'",
        ("GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", {"maxResults": 1000}),
        ("google", "search_gmail_messages", {"query": "in:anywhere", "page_size": 1000}),
    ),
    Scenario(
        "calendar-reversed-window",
        gcalendar.events_list,
        "What's on my primary calendar between 1 January and 1 December 2026?",
        {
            "calendarId": "primary",
            "timeMin": "2026-12-01T00:00:00Z",
            "timeMax": "2026-01-01T00:00:00Z",
        },
        "events.list timeMax: 'If timeMin is set, timeMax must be greater than timeMin.'",
        (
            "GET",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            {"timeMin": "2026-12-01T00:00:00Z", "timeMax": "2026-01-01T00:00:00Z"},
        ),
        (
            "google",
            "get_events",
            {"time_min": "2026-12-01T00:00:00Z", "time_max": "2026-01-01T00:00:00Z"},
        ),
    ),
    Scenario(
        "github-over-max",
        github.issues_list_for_repo,
        "List all the open issues in octocat/Hello-World.",
        {"owner": "octocat", "repo": "Hello-World", "state": "open", "perPage": 500},
        "List repository issues, per_page: 'The number of results per page (max 100).'",
        (
            "GET",
            "https://api.github.com/repos/octocat/Hello-World/issues",
            {"state": "open", "per_page": 500},
        ),
        (
            "github",
            "list_issues",
            {"owner": "octocat", "repo": "Hello-World", "state": "OPEN", "perPage": 500},
        ),
    ),
    Scenario(
        "stripe-over-max",
        stripe.customers_list,
        "List all my Stripe customers.",
        {"limit": 500},
        "List all customers, limit: 'Limit can range between 1 and 100, and the default is 10.'",
        ("GET", "https://api.stripe.com/v1/customers", {"limit": 500}),
        (
            "stripe",
            "stripe_api_read",
            {"stripe_api_operation_id": "GetCustomers", "parameters": {"limit": 500}},
        ),
        skip=("api", "mcp"),
        why="the test account has under 100 customers, so the API's 200 was already complete "
        "(has_more false) and there is nothing to recover",
    ),
    Scenario(
        "calendar-sync-with-filter",
        gcalendar.events_list,
        "Continue my calendar sync from sync token {sync_token}, but only for events from 2026 on.",
        {"calendarId": "primary", "syncToken": "{sync_token}", "timeMin": "2026-01-01T00:00:00Z"},
        "events.list syncToken: 'There are several query parameters that cannot be specified "
        "together with nextSyncToken to ensure consistency of the client state.'",
        (
            "GET",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            {"syncToken": "{sync_token}", "timeMin": "2026-01-01T00:00:00Z"},
        ),
        None,  # google_workspace_mcp offers no syncToken
    ),
    Scenario(
        "stripe-charge-in-dollars",
        stripe.payment_intents_create,
        "Create a payment intent to collect $15.50 in USD.",
        {"amount": 15.5, "currency": "usd"},
        "Create a PaymentIntent, amount: 'Amount intended to be collected by this "
        "PaymentIntent. A positive integer representing how much to charge in the smallest "
        "currency unit (e.g., 100 cents to charge $1.00 or 100 to charge ¥100, a zero-decimal "
        "currency).'",
        ("POST", "https://api.stripe.com/v1/payment_intents", {"amount": 15.5, "currency": "usd"}),
        None,  # @stripe/mcp exposes no PaymentIntent create (2026-10-25)
        check=lambda args: _int_or_none(args.get("amount")) == 1550,
    ),
]


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v) if float(v) == int(float(v)) else None
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# The texts
# -----------------------------------------------------------------------------


def charter_text(tool: Tool, args: dict[str, Any]) -> str | None:
    """Charter's refusal for ``args``, or None when Charter would send the call."""
    try:
        tool.llm_schema().model_validate(args)
    except ValidationError:
        pass
    else:
        return None
    try:
        asyncio.run(tool.ainvoke(args, client=_NoNetwork()))
    except ToolValidationError as exc:
        return str(exc)
    return None


class _NoNetwork(httpx.AsyncClient):
    async def send(self, request, **kwargs):  # never reached for an invalid call
        raise RuntimeError("a refused call must not reach the network")


def charter_old_text(tool: Tool, args: dict[str, Any]) -> str:
    """LangGraph's template around pydantic's own message, as before 2026-03-02."""
    try:
        tool.llm_schema().model_validate(args)
        error = ""
    except ValidationError as exc:
        error = str(exc)
    return (
        f"Error invoking tool '{tool.name}' with kwargs {args} with error:\n{error}\n"
        " Please fix the error and try again."
    )


def is_fix(s: Scenario, args: dict[str, Any]) -> bool:
    if charter_text(s.tool, args) is not None:
        return False
    return s.check(args) if s.check else True


# -----------------------------------------------------------------------------
# Capture: the API's and the MCP server's own answers, once
# -----------------------------------------------------------------------------


async def capture() -> None:
    from mcp_layer import call, connect
    from servers import servers

    from charter_harness.settings import load, wire_packs

    settings = load()
    wiring = wire_packs(settings, frozenset({"gmail", "gcalendar", "github", "stripe"}))
    google = {"Authorization": f"Bearer {await wiring.google_token()}"}
    headers = {
        "gmail": google,
        "gcalendar": google,
        "github": {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        },
        "stripe": {"Authorization": f"Bearer {settings.stripe_api_key}"},
    }
    texts: dict[str, dict[str, Any]] = {}
    async with AsyncExitStack() as stack, httpx.AsyncClient(timeout=60) as http:
        srv = servers(slack_channels=[])
        sessions: dict[str, Any] = {}
        # A real sync token for the syncToken scenario, from a full listing.
        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        params: dict[str, Any] = {"maxResults": 2500}
        while True:
            body = (await http.get(url, headers=google, params=params)).json()
            if "nextSyncToken" in body:
                sync_token = body["nextSyncToken"]
                break
            params["pageToken"] = body["nextPageToken"]
        for s in SCENARIOS:
            fill = lambda v: json.loads(json.dumps(v).replace("{sync_token}", sync_token))  # noqa: E731
            method, target, payload = s.raw
            h = headers[
                {"gmail": "gmail", "calendar": "gcalendar", "github": "github", "stripe": "stripe"}[
                    s.id.split("-")[0]
                ]
            ]
            if method == "GET":
                r = await http.get(target, headers=h, params=fill(payload))
            else:
                r = await http.post(target, headers=h, data=fill(payload))
            try:  # minified, as an HTTP tool that parses and re-serialises would hand it on
                text = json.dumps(r.json(), separators=(",", ":"), ensure_ascii=False)
            except ValueError:
                text = r.text
            entry = {"api": {"status": r.status_code, "bytes": len(text), "text": text[:TEXT_SIZE]}}
            if s.mcp:
                server, tool, arguments = s.mcp
                if server not in sessions:
                    sessions[server] = await stack.enter_async_context(connect(srv[server]))
                out = await call(sessions[server], tool, fill(arguments))
                entry["mcp"] = {
                    "server": srv[server].name,
                    "is_error": out.is_error,
                    "text": out.text[:TEXT_SIZE],
                }
            entry["sync_token"] = sync_token if "{sync_token}" in json.dumps(s.bad) else None
            texts[s.id] = entry
            print(
                s.id,
                entry["api"]["status"],
                len(entry["api"]["text"]),
                "mcp" in entry and entry["mcp"]["is_error"],
            )
    OUT.mkdir(parents=True, exist_ok=True)
    account = os.environ.get("GOOGLE_TEST_EMAIL") or _harness_env("GOOGLE_TEST_EMAIL")
    raw = json.dumps(texts, indent=1)
    if account:
        raw = raw.replace(account, "test-account@example.com")
    # Any other real address (a test account's own customers) is not kept either.
    raw = re.sub(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}",
        lambda m: (
            m.group(0) if re.search(r"@(example\.com|harness\.invalid)$", m.group(0)) else "<email>"
        ),
        raw,
    )
    (OUT / "texts.json").write_text(raw)


def _harness_env(name: str) -> str:
    from servers import _env

    return _env(name)


# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------


def _texts(s: Scenario, captured: dict[str, Any]) -> dict[str, str]:
    bad = _bad(s, captured)
    out = {
        "charter": charter_text(s.tool, bad) or "",
        "charter_old": charter_old_text(s.tool, bad),
        "api": captured[s.id]["api"]["text"],
        "generic": GENERIC,
    }
    if "mcp" in captured[s.id]:
        out["mcp"] = captured[s.id]["mcp"]["text"]
    return {k: v for k, v in out.items() if k not in s.skip}


def _bad(s: Scenario, captured: dict[str, Any]) -> dict[str, Any]:
    token = captured[s.id].get("sync_token") or ""
    return json.loads(json.dumps(s.bad).replace("{sync_token}", token))


def _task(s: Scenario, captured: dict[str, Any]) -> str:
    return s.task.replace("{sync_token}", captured[s.id].get("sync_token") or "")


def episode(
    model: str,
    s: Scenario,
    kind: str,
    sample: int,
    captured: dict[str, Any],
    schema_kind: str = "charter",
) -> dict[str, Any]:
    name, base = MODELS[model]
    client = openai.OpenAI(
        base_url=base,
        api_key=os.environ.get("FIREWORKS_API_KEY", "") if base == FIREWORKS else "local",
        timeout=900,
    )
    texts = _texts(s, captured)
    bad = _bad(s, captured)
    definition = s.tool.to_json_schema()
    schema = {
        "type": "function",
        "function": bare(definition) if schema_kind == "bare" else definition,
    }
    call_id = f"call_{uuid.uuid4().hex[:12]}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": _task(s, captured)},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": s.tool.name, "arguments": json.dumps(bad)},
                }
            ],
        },
        {"role": "tool", "tool_call_id": call_id, "content": texts[kind]},
    ]
    row: dict[str, Any] = {
        "model": model,
        "schema": schema_kind,
        "scenario": s.id,
        "text": kind,
        "sample": sample,
        "calls": [],
    }
    t0 = time.time()
    for n in range(1, MAX_CALLS + 1):
        try:
            reply = (
                client.chat.completions.create(
                    model=name, messages=messages, tools=[schema], temperature=0.7
                )
                .choices[0]
                .message
            )
        except Exception as exc:
            if out_of_credit(exc):
                raise
            row.update(outcome=None, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            break
        calls = reply.tool_calls or []
        if not calls:
            row.update(outcome="answered", answer=(reply.content or "")[:2000])
            break
        tc = calls[0]
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {"_unparsed": tc.function.arguments}
        row["calls"].append({"name": tc.function.name, "args": args})
        if tc.function.name != s.tool.name:
            row.update(outcome="called another tool")
            break
        if is_fix(s, args):
            row.update(outcome="fixed on the next call" if n == 1 else "fixed later")
            break
        if n == 1 and args == bad:
            row["resent_first"] = True
        # The same kind of text again; Charter's own texts are made for these args.
        again = (
            charter_text(s.tool, args) or texts["charter"]
            if kind == "charter"
            else charter_old_text(s.tool, args)
            if kind == "charter_old"
            else texts[kind]
        )
        messages += [
            {
                "role": "assistant",
                "content": reply.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": tc.id, "content": again},
        ]
    else:
        row.update(outcome="kept trying")
    if row.get("outcome") not in (None, "fixed on the next call") and row.get("resent_first"):
        row["outcome"] = (
            "resent the same call" if row["outcome"] != "fixed later" else "fixed later"
        )
    row["seconds"] = round(time.time() - t0, 1)
    return row


_lock = threading.Lock()


def run(model: str, samples: int, workers: int, only: str, schema_kind: str = "charter") -> None:
    captured = json.loads((OUT / "texts.json").read_text())
    out = OUT / (f"{model}.jsonl" if schema_kind == "charter" else f"{model}-{schema_kind}.jsonl")
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if r.get("outcome") is not None:
                done.add((r["scenario"], r["text"], r["sample"]))
    jobs = [
        (s, kind, k)
        for s in SCENARIOS
        if not only or only in s.id
        for kind in _texts(s, captured)
        for k in range(samples)
        if (s.id, kind, k) not in done
    ]
    print(f"{len(jobs)} episodes to run, {len(done)} already recorded", flush=True)
    with ThreadPoolExecutor(workers) as pool, out.open("a") as f:
        futures = [
            pool.submit(episode, model, s, kind, k, captured, schema_kind) for s, kind, k in jobs
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                row = fut.result()
            except Exception as exc:
                if out_of_credit(exc):
                    print("stopped: the model provider refused the account", flush=True)
                    for p in futures:
                        p.cancel()
                    raise SystemExit(3) from exc
                raise
            with _lock:
                f.write(json.dumps(row) + "\n")
                f.flush()
            print(
                i, row["scenario"], row["text"], row.get("outcome"), len(row["calls"]), flush=True
            )


# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

OUTCOMES = [
    "fixed on the next call",
    "fixed later",
    "resent the same call",
    "kept trying",
    "called another tool",
    "told the user it worked",
    "said it had not",
    "answered (unlabelled)",
]
TEXTS = ["charter", "charter_old", "api", "mcp", "generic"]


def report() -> None:
    labels = {}
    path = OUT / "answers.json"
    if path.exists():
        labels = {a["key"]: a["label"] for a in json.loads(path.read_text())["answers"]}
    lines = ["# After a bad call: the error-message swap", ""]
    for f in sorted(OUT.glob("*.jsonl")):
        rows = [json.loads(line) for line in f.read_text().splitlines()]
        rows = [r for r in rows if r.get("outcome") is not None]
        lines += [
            f"## {f.stem}",
            "",
            "| text | episodes | " + " | ".join(OUTCOMES) + " |",
            "|---|---:|" + "---:|" * len(OUTCOMES),
        ]
        for kind in TEXTS:
            rs = [r for r in rows if r["text"] == kind]
            if not rs:
                continue
            counts = dict.fromkeys(OUTCOMES, 0)
            for r in rs:
                o = r["outcome"]
                if o == "answered":
                    o = labels.get(_key(r), "answered (unlabelled)")
                counts[o] += 1
            lines.append(
                f"| {kind} | {len(rs)} | " + " | ".join(str(counts[o]) for o in OUTCOMES) + " |"
            )
        lines.append("")
        lines += [
            "Fixed (next or later), by scenario and text:",
            "",
            "| scenario | " + " | ".join(TEXTS) + " |",
            "|---|" + "---:|" * len(TEXTS),
        ]
        for s in SCENARIOS:
            cells = []
            for kind in TEXTS:
                rs = [r for r in rows if r["scenario"] == s.id and r["text"] == kind]
                fixed = sum(r["outcome"] in ("fixed on the next call", "fixed later") for r in rs)
                cells.append(f"{fixed}/{len(rs)}" if rs else "")
            lines.append(f"| {s.id} | " + " | ".join(cells) + " |")
        lines.append("")
    text = "\n".join(lines) + "\n"
    (OUT / "summary.md").write_text(text)
    print(text)


def _key(r: dict[str, Any]) -> str:
    return f"{r['model']}|{r.get('schema', 'charter')}|{r['scenario']}|{r['text']}|{r['sample']}"


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("capture")
    p = sub.add_parser("run")
    p.add_argument("--model", choices=sorted(MODELS), required=True)
    p.add_argument("--samples", type=int, default=10)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--only", default="")
    p.add_argument("--schema", choices=["charter", "bare"], default="charter")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "capture":
        asyncio.run(capture())
    elif a.cmd == "run":
        run(a.model, a.samples, a.workers, a.only, a.schema)
    else:
        report()


if __name__ == "__main__":
    main()
