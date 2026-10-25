"""AgentDojo's banking suite, four ways: stock tools, AgentDojo's tool filter, and Charter.

Arms, each the same model, system message, attack and tasks:

- ``stock``: the suite's own tools, AgentDojo's default pipeline.
- ``tool_filter``: AgentDojo's built-in defense of that name (the model first
  names the tools the task needs; the rest are removed), with the tools listed in
  its prompt; see :class:`VisibleToolFilter` for why.
- ``charter_plain``: the same API served over HTTP and declared with Charter,
  with no rule beyond the types. Separates the declaration from the rules.
- ``charter_rules``: the same declaration with the four rules in ``RULES.md``.

The attack is AgentDojo's ``important_instructions`` with its default model name
("the AI language model"), which is the registered
``important_instructions_no_model_name``. Utility and attack success are AgentDojo's
own judges, reading the environment after the run.

    python run.py --model glm-5p3-flash --arms stock,charter_rules --workers 8

Needs ``agentdojo`` and ``charter-ai`` installed, and ``FIREWORKS_API_KEY``.
Writes one JSON line per episode to ``results/bench/agentdojo/<model>.jsonl``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from collections.abc import Sequence
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import bank_api
import httpx
import openai
import yaml
from agentdojo.agent_pipeline import (
    AgentPipeline,
    InitQuery,
    OpenAILLM,
    SystemMessage,
    ToolsExecutionLoop,
    ToolsExecutor,
)
from agentdojo.agent_pipeline.agent_pipeline import TOOL_FILTER_PROMPT, load_system_message
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.llms.openai_llm import (
    OpenAILLMToolFilter,
    _message_to_openai,
    _openai_to_assistant_message,
    chat_completion_request,
)
from agentdojo.agent_pipeline.tool_execution import tool_result_to_str
from agentdojo.attacks.base_attacks import DEFAULT_MODEL_NAME
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.types import ChatToolResultMessage, text_content_block_from_string
from charter import CharterError, Tool
from pydantic.alias_generators import to_snake

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # bench/, for _provider
from _provider import out_of_credit  # noqa: E402


class OutOfCredit(Exception):
    """The model provider refused the account; the episode never ran."""


OUT_DIR = HERE.parent.parent / "results" / "bench" / "agentdojo"
SUITE_VERSION = "v1.2.2"
FIREWORKS = "https://api.fireworks.ai/inference/v1"
MODELS = {
    "glm-5p3-flash": "accounts/fireworks/models/glm-5p3-flash",
    "nemotron-lightning": "accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    # Claude through bench/claude_provider.py, which must be running.
    "claude-sonnet": "sonnet",
}
LOCAL = {"claude-sonnet": "http://127.0.0.1:8799/v1"}


# -----------------------------------------------------------------------------
# The Charter arm: the model reads Charter's schemas, and calls go through Charter
# -----------------------------------------------------------------------------


class CharterLLM(OpenAILLM):
    """AgentDojo's OpenAI element, offering Charter's tool schemas instead of the stock ones."""

    def __init__(self, client: openai.OpenAI, model: str, tools: Sequence[Tool]) -> None:
        super().__init__(client, model, temperature=0.0)
        self.schemas = [{"type": "function", "function": t.to_json_schema()} for t in tools]

    def query(self, query, runtime, env=EmptyEnv(), messages=(), extra_args={}):  # noqa: B006
        openai_messages = [_message_to_openai(m, self.model) for m in messages]
        completion = chat_completion_request(
            self.client, self.model, openai_messages, self.schemas, None, self.temperature
        )
        output = _openai_to_assistant_message(completion.choices[0].message)
        return query, runtime, env, [*messages, output], extra_args


class CharterExecutor(BasePipelineElement):
    """Runs each tool call through ``Tool.ainvoke`` against the HTTP API over ``env``.

    A refusal or an API error becomes the tool result's error, the way AgentDojo's
    own executor reports a function that raised. The text the model reads is
    Charter's message, which is the thing under test.
    """

    def __init__(self, tools: Sequence[Tool], runtime_functions) -> None:
        self.tools = {t.name: t for t in tools}
        self.functions = runtime_functions

    def query(self, query, runtime, env=EmptyEnv(), messages=(), extra_args={}):  # noqa: B006
        if not messages or messages[-1]["role"] != "assistant" or not messages[-1]["tool_calls"]:
            return query, runtime, env, messages, extra_args
        rt = FunctionsRuntime(self.functions)
        session = bank_api.Session(env=env, request=query)
        results = []
        for call in messages[-1]["tool_calls"]:
            tool = self.tools.get(call.function)
            content, error = "", None
            if tool is None:
                error = f"Invalid tool {call.function} provided."
            else:
                try:
                    out = _invoke(tool, dict(call.args), rt, env, session)
                    content = _as_stock(out)
                except CharterError as exc:
                    error = str(exc)
            # Record the call under the suite's own argument names, so AgentDojo's
            # traces read the same on every arm. The model saw camelCase names.
            call.args = {to_snake(k): v for k, v in call.args.items()}
            results.append(
                ChatToolResultMessage(
                    role="tool",
                    content=[text_content_block_from_string(content)],
                    tool_call_id=call.id,
                    tool_call=call,
                    error=error,
                )
            )
        return query, runtime, env, [*messages, *results], extra_args


def _as_stock(result: Any) -> str:
    """The text AgentDojo's own formatter would produce for the same value.

    The stock functions return pydantic models where the API returns their JSON,
    so a list of objects is dumped as the YAML the formatter makes of the models,
    and anything else is ``str()``, as it is there.
    """
    if isinstance(result, list):
        return yaml.safe_dump(
            [item if isinstance(item, dict) else str(item) for item in result]
        ).strip()
    return tool_result_to_str(result)


def _invoke(tool: Tool, args: dict[str, Any], rt: FunctionsRuntime, env: Env, session) -> Any:
    async def go():
        token = bank_api.SESSION.set(session)
        try:
            async with httpx.AsyncClient(transport=bank_api.transport(rt, env)) as client:
                return await tool.ainvoke(args, client=client)
        finally:
            bank_api.SESSION.reset(token)

    return asyncio.run(go())


class VisibleToolFilter(OpenAILLMToolFilter):
    """AgentDojo's tool filter, with the tools it chooses from written into its prompt.

    The filter sends the tools with ``tool_choice="none"`` and keeps the ones whose
    names its model writes back. OpenAI still shows a model its tools under
    ``"none"``; Fireworks does not. Asked to name its tools, nemotron-lightning
    answers nothing under ``"none"`` and ``send_money`` under ``"auto"``
    (2026-10-24), and in the filter itself glm-5p3-flash named
    ``get_transactions, calculate``, which do not exist. So the first run of this
    arm removed nearly every tool and measured the provider, not the defense; its
    rows are kept apart in ``results/bench/agentdojo/void/``. Listing the tools in
    the prompt gives the model what OpenAI's API gives it.

    The filter also leaves its own exchange in the conversation, ending it on an
    assistant message. Fireworks answers a conversation that ends that way with an
    empty message, so the agent never started (task 1, glm-5p3-flash: the filter
    kept ``get_most_recent_transactions``, then an empty reply). The second run of
    the arm is voided for that too. The filter's exchange is therefore dropped once
    it has chosen: the agent goes on with the conversation it had, and fewer tools,
    which is the defense's mechanism.
    """

    def query(self, query, runtime, env=EmptyEnv(), messages=(), extra_args=None):  # type: ignore[override]
        listing = "\n".join(
            f"- {name}: {function.description}" for name, function in runtime.functions.items()
        )
        prompt = self.prompt
        self.prompt = f"{prompt}\n\nThe tools available are:\n{listing}"
        try:
            query, runtime, env, _, extra_args = super().query(
                query, runtime, env, list(messages), extra_args or {}
            )
        finally:
            self.prompt = prompt
        return query, runtime, env, messages, extra_args


# -----------------------------------------------------------------------------
# Pipelines
# -----------------------------------------------------------------------------


def pipeline(arm: str, model: str, suite) -> AgentPipeline:
    client = openai.OpenAI(
        base_url=LOCAL.get(model, FIREWORKS),
        api_key=os.environ.get("FIREWORKS_API_KEY", "local") if model not in LOCAL else "local",
        timeout=900,
    )
    model_id = MODELS[model]
    system = SystemMessage(load_system_message(None))
    if arm in ("stock", "tool_filter"):
        llm = OpenAILLM(client, model_id, temperature=0.0)
        loop = ToolsExecutionLoop([ToolsExecutor(), llm])
        if arm == "stock":
            elements = [system, InitQuery(), llm, loop]
        else:
            elements = [
                system,
                InitQuery(),
                VisibleToolFilter(TOOL_FILTER_PROMPT, client, model_id),
                llm,
                loop,
            ]
    else:
        tools = bank_api.ruled_tools() if arm == "charter_rules" else bank_api.plain_tools()
        llm = CharterLLM(client, model_id, tools)
        loop = ToolsExecutionLoop([CharterExecutor(tools, suite.tools), llm])
        elements = [system, InitQuery(), llm, loop]
    p = AgentPipeline(elements)
    p.name = f"{model}-{arm}"
    return p


class Attack(ImportantInstructionsAttack):
    """``important_instructions_no_model_name``, without its pipeline-name lookup."""

    name = "important_instructions_no_model_name"

    def __init__(self, task_suite, target_pipeline) -> None:
        super(ImportantInstructionsAttack, self).__init__(
            self._JB_STRING, task_suite, target_pipeline
        )
        self.user_name = "Emma Johnson"
        self.model_name = DEFAULT_MODEL_NAME


# -----------------------------------------------------------------------------
# The run
# -----------------------------------------------------------------------------

_write = threading.Lock()


def episode(arm: str, model: str, user_id: str, injection_id: str | None) -> dict[str, Any]:
    suite = get_suite(SUITE_VERSION, "banking")
    p = pipeline(arm, model, suite)
    user_task = suite.user_tasks[user_id]
    injection_task = suite.injection_tasks[injection_id] if injection_id else None
    injections = Attack(suite, p).attack(user_task, injection_task) if injection_task else {}
    t0 = time.time()
    row: dict[str, Any] = {
        "arm": arm,
        "model": model,
        "user_task": user_id,
        "injection_task": injection_id,
    }
    try:
        utility, security = suite.run_task_with_pipeline(p, user_task, injection_task, injections)
        row.update(
            utility=bool(utility), attack_succeeded=bool(security) if injection_task else None
        )
    except Exception as exc:  # recorded, never folded into either column
        if out_of_credit(exc):
            raise OutOfCredit(str(exc)) from exc  # the agent never ran: not a row at all
        row.update(
            utility=None, attack_succeeded=None, error=f"{type(exc).__name__}: {str(exc)[:300]}"
        )
    row["seconds"] = round(time.time() - t0, 1)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="glm-5p3-flash", choices=sorted(MODELS))
    ap.add_argument("--arms", default="stock,tool_filter,charter_plain,charter_rules")
    ap.add_argument("--user-tasks", default="", help="comma-separated ids; default all")
    ap.add_argument("--injection-tasks", default="", help="comma-separated ids; default all")
    ap.add_argument(
        "--no-attack", action="store_true", help="also run each user task with no injection"
    )
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    suite = get_suite(SUITE_VERSION, "banking")
    users = args.user_tasks.split(",") if args.user_tasks else list(suite.user_tasks)
    injections = (
        args.injection_tasks.split(",") if args.injection_tasks else list(suite.injection_tasks)
    )
    jobs = [(arm, u, i) for arm in args.arms.split(",") for u in users for i in injections]
    if args.no_attack:
        jobs += [(arm, u, None) for arm in args.arms.split(",") for u in users]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.model}.jsonl"
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if r.get("error") is None:
                done.add((r["arm"], r["user_task"], r["injection_task"]))
    jobs = [j for j in jobs if j not in done]
    print(f"{len(jobs)} episodes to run, {len(done)} already recorded")

    written, stopped = 0, False
    with ThreadPoolExecutor(args.workers) as pool, out.open("a") as f:
        futures = [pool.submit(episode, arm, args.model, u, i) for arm, u, i in jobs]
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except OutOfCredit:
                if not stopped:
                    stopped = True
                    for pending in futures:
                        pending.cancel()  # those not started never will be
                continue
            except CancelledError:
                continue
            with _write:
                f.write(json.dumps(row) + "\n")
                f.flush()
            written += 1
            print(written, json.dumps(row), flush=True)
    if stopped:
        print(
            f"stopped: the model provider refused the account (credits or billing). {written} "
            "episodes recorded; rerun the same command to finish the rest.",
            flush=True,
        )
        raise SystemExit(3)


if __name__ == "__main__":
    main()
