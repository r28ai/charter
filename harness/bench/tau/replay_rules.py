"""Replay a recorded run's tool calls through the rules as they are now, offline.

The rules arm's refusals are part of a recorded result, so a change to how the
rules are written has to leave every one of them where it was. This rebuilds each
recorded episode's environment the way ``run.py`` does, then walks its
conversation: each user message reaches the session as it did during the run, and
each tool call goes through ``CharterEnv.get_response``, which validates it with
the rules and runs it on the episode's database. Every reply, refused or run, has
to be the reply that was recorded, byte for byte. No model is called.

    python replay_rules.py ../../results/bench/tau/sonnet5-2026-10-25

Exits non-zero, listing each difference, if any call came out differently.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import Any

import run
from tau2.data_model.message import ToolCall
from tau2.runner.build import build_text_orchestrator


def _episode_env(domain: str, task: Any, trial: int) -> run.CharterEnv:
    config = run.TextRunConfig(
        domain=domain,
        agent="llm_agent",
        llm_agent=run.MODELS["claude-sonnet"],
        user="user_simulator",
        llm_user=run.MODELS[run.USER_MODEL],
        seed=run.SEED + trial,
    )
    orch = build_text_orchestrator(config, task, seed=run.SEED + trial)
    state = task.initial_state
    orch.environment.set_state(
        initialization_data=state.initialization_data if state else None,
        initialization_actions=state.initialization_actions if state else None,
        message_history=[],
    )
    return run.CharterEnv(orch.environment, ruled=True)


def replay(row: dict[str, Any], tasks: dict[str, Any]) -> list[str]:
    """Every call in one recorded episode whose reply is not the recorded one."""
    domain = row.get("domain", "retail")  # runs before airline did not record it
    env = _episode_env(domain, tasks[str(row["task"])], int(row["trial"]))
    messages = row["simulation"]["messages"]
    recorded = {m["id"]: m for m in messages if m["role"] == "tool"}
    differences = []
    for message in messages:
        if message["role"] == "user" and message.get("content"):
            env.session.heard(message["content"])
        for call in message.get("tool_calls") or []:
            want = recorded.get(call["id"])
            if want is None:
                continue
            got = env.get_response(
                ToolCall(
                    id=call["id"],
                    name=call["name"],
                    arguments=dict(call["arguments"] or {}),
                    requestor="assistant",
                )
            )
            status = got.execution_status or "executed"
            if (status, got.content) != (want.get("execution_status", "executed"), want["content"]):
                differences.append(
                    f"{domain} task {row['task']} trial {row['trial']} {call['name']}: "
                    f"recorded {want.get('execution_status')} {want['content'][:80]!r}, "
                    f"now {status} {got.content[:80]!r}"
                )
    return differences


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1])
    rows = [
        json.loads(line)
        for path in sorted((run_dir / "conversations").glob("*.jsonl.gz"))
        for line in gzip.open(path, "rt")
    ]
    ruled = [r for r in rows if r["arm"] == "charter_rules"]
    tasks = {
        domain: {str(t.id): t for t in loader()}
        for domain, loader in (("retail", run.retail_tasks), ("airline", run.airline_tasks))
    }
    differences: list[str] = []
    calls = refused = 0
    for row in ruled:
        differences += replay(row, tasks[row.get("domain", "retail")])
        tool_messages = [m for m in row["simulation"]["messages"] if m["role"] == "tool"]
        calls += len(tool_messages)
        refused += sum(m.get("execution_status") == "rejected" for m in tool_messages)
    print(f"{len(ruled)} episodes, {calls} recorded calls, {refused} refused: ", end="")
    if differences:
        print(f"{len(differences)} differ")
        print("\n".join(differences))
        return 1
    print("every reply is the recorded one")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
