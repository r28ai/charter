"""τ²-bench's retail and airline domains, three ways: stock tools, and the same tools through
Charter.

Arms, each the same agent model, user simulator, policy and tasks:

- ``stock``: the domain's own tools and environment, τ²-bench's ``llm_agent``.
- ``charter_plain``: the same tools declared with Charter, field for field, and
  called over HTTP, with no rule beyond the types. Separates the declaration from
  the rules.
- ``charter_rules``: the same declaration with the domain's rules, committed
  before any of its tasks was read: ``RULES.md`` for retail (three rules),
  ``RULES_AIRLINE.md`` for airline (eleven).

A call Charter refuses never reaches the API. It is recorded the way τ²-bench
records a call its own orchestrator rejects (``execution_status="rejected"``), so
the evaluator's replay skips it, and the model reads Charter's message as the
tool's error. A call that reaches the API returns the text the stock environment
would have returned, errors included.

The reward is τ²-bench's DB check: the database after the conversation, replayed,
against the database after the task's gold actions. Retail also scores natural-
language assertions with an OpenAI judge; that half is not run here. Each episode
also records the calls that broke a rule and still ran, counted the same way on
every arm (:func:`broken_rules`).

    python run.py --model glm-5p3-flash --tasks 20 --trials 2 --workers 6
    python run.py --model claude-sonnet --domain airline,retail --split base --tasks 0 \\
        --arms stock,charter_rules --trials 4 --workers 4 --out <run>

Needs tau2-bench (sierra-research/tau2-bench at the commit in RULES.md) and
charter-ai installed in one environment, and ``FIREWORKS_API_KEY``:

    uv venv --python 3.12 .venv
    git clone https://github.com/sierra-research/tau2-bench .venv/src/tau2
    git -C .venv/src/tau2 checkout 0c69df456a96aa76a1162591574dad9c427a34d7
    uv pip install --python .venv/bin/python -e .venv/src/tau2 -e ../../..

Writes one JSON line per episode to ``results/bench/tau/<model>.jsonl``, and
resumes from it: an episode is keyed on its domain, arm, task and trial, and one
recorded without an ``error`` is never run again. Jobs run trial by trial, each
trial every domain in the order given, so a run cut short still has whole trials.
When the model provider refuses the account (credits, or a Claude subscription
limit), nothing more is scheduled, the episodes in flight are dropped unwritten,
and the run exits with code 3; ``resume.sh`` waits and reruns it.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import os
import sys
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import airline_api
import httpx
import retail_api
import tau2.evaluator.evaluator_nl_assertions as nl_judge
from charter import APIError, Tool, ToolValidationError
from pydantic.alias_generators import to_snake
from tau2.agent.llm_agent import LLMAgent
from tau2.data_model.message import AssistantMessage, ToolMessage, UserMessage
from tau2.data_model.semantic_communication import (
    CommunicateScorer,
    CommunicateScoring,
    SemanticCommunicateSettings,
)
from tau2.data_model.simulation import TextRunConfig
from tau2.data_model.tasks import RewardType
from tau2.domains.airline.environment import get_tasks as airline_tasks
from tau2.domains.retail.environment import get_tasks as retail_tasks
from tau2.environment.environment import Environment
from tau2.evaluator.evaluator import EvaluationType, evaluate_simulation
from tau2.runner.build import build_text_orchestrator
from tau2.runner.simulation import run_simulation

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # bench/, for _provider
from _provider import out_of_credit  # noqa: E402

OUT_DIR = HERE.parent.parent / "results" / "bench" / "tau"
TAU2_COMMIT = "0c69df456a96aa76a1162591574dad9c427a34d7"
MODELS = {
    "glm-5p3-flash": "fireworks_ai/accounts/fireworks/models/glm-5p3-flash",
    "nemotron-lightning": "fireworks_ai/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    # Claude through bench/claude_provider.py, which must be running.
    "claude-sonnet": "openai/sonnet",
}
LOCAL = {"claude-sonnet": {"api_base": "http://127.0.0.1:8799/v1", "api_key": "local"}}
USER_MODEL = "glm-5p3-flash"
PRICES = {
    "glm-5p3-flash": (0.15, 0.50),
    "nemotron-lightning": (0.05, 0.20),
}  # USD per million tokens, in and out
SEED = 300  # τ²-bench's default; trial t uses SEED + t
# τ²-bench grades retail's natural-language assertions with an OpenAI model
# (DEFAULT_LLM_NL_ASSERTIONS); this harness has no OpenAI key, so the same prompt
# goes to glm-5p3-flash, in JSON mode because the judge's reply is parsed as JSON.
JUDGE_MODEL = "glm-5p3-flash"
nl_judge.DEFAULT_LLM_NL_ASSERTIONS = MODELS[JUDGE_MODEL]
nl_judge.DEFAULT_LLM_NL_ASSERTIONS_ARGS = {
    "temperature": 0.0,
    "response_format": {"type": "json_object"},
}
# Every airline task's reward basis also grades what the agent told the customer
# (COMMUNICATE), judged by gpt-5.5 by default; the same substitution, with
# τ²-bench's own prompt. No retail task's basis includes it, so retail's scoring
# never reaches it and is left as it was.
COMMUNICATE = {
    "retail": CommunicateScoring(),
    "airline": CommunicateScoring(
        scorer=CommunicateScorer.SEMANTIC,
        judge=SemanticCommunicateSettings(
            model=MODELS[JUDGE_MODEL], model_args=dict(nl_judge.DEFAULT_LLM_NL_ASSERTIONS_ARGS)
        ),
    ),
}


JUDGED = False  # set by --judge
TRAJECTORIES: Path | None = None  # set by --out, where each conversation is kept
# Each domain's Charter declaration and rules, and its tasks.
APIS: dict[str, Any] = {"retail": retail_api, "airline": airline_api}
TASKS = {"retail": retail_tasks, "airline": airline_tasks}


class OutOfCredit(Exception):
    """The model provider refused the account; the episode never ran."""


# -----------------------------------------------------------------------------
# The Charter arms: the model reads Charter's schemas, and calls go through Charter
# -----------------------------------------------------------------------------


class _Offered:
    """What τ²-bench's agent reads off a tool: its name and its OpenAI schema."""

    def __init__(self, tool: Tool) -> None:
        self.name = tool.name
        self.openai_schema = {"type": "function", "function": tool.to_json_schema()}


class CharterEnv(Environment):
    """The episode's own environment, with calls routed through Charter.

    It keeps the stock domain name, toolkit and database, so τ²-bench evaluates it
    with the stock environment and nothing downstream can tell the arms apart.
    """

    def __init__(self, stock: Environment, ruled: bool) -> None:
        super().__init__(domain_name=stock.domain_name, policy=stock.policy, tools=stock.tools)
        self.api = APIS[stock.domain_name]
        tools = self.api.ruled_tools(stock) if ruled else self.api.plain_tools(stock)
        self.charter = {t.name: t for t in tools}
        if self.api is retail_api:
            self.session = retail_api.Session(owners=_owners(stock))
        else:
            self.session = airline_api.Session.of(self)
        self._replaying = False

    def get_tools(self) -> list[Any]:
        return [_Offered(t) for t in self.charter.values()]

    def set_state(self, *args: Any, **kwargs: Any) -> None:
        # The task's own history is replayed against the API directly, as stock.
        self._replaying = True
        try:
            super().set_state(*args, **kwargs)
        finally:
            self._replaying = False
        if self.api is airline_api:
            history = kwargs.get("message_history", args[2] if len(args) > 2 else None)
            if history:  # none has one at the pinned commit; the rules would not see it
                raise NotImplementedError("an airline task with a message history")
            self.session.restart()

    def get_response(self, message: Any) -> ToolMessage:
        tool = self.charter.get(message.name)
        if self._replaying or tool is None:
            return super().get_response(message)
        reply = {"id": message.id, "requestor": message.requestor, "role": "tool"}
        args = dict(message.arguments)
        # The trajectory records what reached the API, which is what τ²-bench
        # replays: Charter publishes camelCase names and repairs some values (a
        # list sent as a JSON string), so the model's own arguments may not be it.
        # A refused call reached nothing; it keeps the model's, in the domain's names.
        message.arguments = {to_snake(k): v for k, v in args.items()}
        sent: dict[str, Any] = {}
        try:
            result = _invoke(tool, args, self, sent)
        except ToolValidationError as exc:
            refusal = {"tool": message.name, "message": str(exc)}
            if self.api is airline_api:
                refusal["rules"] = airline_api.refusal_rules(str(exc))
            self.session.refusals.append(refusal)
            return ToolMessage(**reply, content=str(exc), error=True, execution_status="rejected")
        except APIError as exc:
            message.arguments = sent.get("args", message.arguments)
            return ToolMessage(**reply, content=f"Error: {_api_error(exc)}", error=True)
        message.arguments = sent["args"]
        self.sync_tools()
        if self.api is airline_api:
            self.session.ran(message.name, message.arguments)
        elif message.name in retail_api.LOOKUPS and self.session.user_id is None:
            self.session.user_id = result
        return ToolMessage(**reply, content=result)


def _invoke(tool: Tool, args: dict[str, Any], env: CharterEnv, sent: dict[str, Any]) -> Any:
    async def go() -> Any:
        # The rules read the session from Charter's per-call context.
        async with httpx.AsyncClient(transport=env.api.transport(env, sent)) as client:
            return await tool.ainvoke(args, client=client, context={"session": env.session})

    return asyncio.run(go())


def _api_error(exc: APIError) -> str:
    try:
        return json.loads(exc.body)["error"]
    except (ValueError, KeyError, TypeError):
        return str(exc)


def _owners(env: Environment) -> dict[str, str]:
    return {oid: order.user_id for oid, order in env.tools.db.orders.items()}


class SessionAgent(LLMAgent):
    """τ²-bench's own agent, telling the host what the user says (the rules read it)."""

    def __init__(self, *args: Any, session: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.session = session

    def generate_next_message(self, message: Any, state: Any) -> Any:
        if isinstance(message, UserMessage) and message.content:
            self.session.heard(message.content)
        return super().generate_next_message(message, state)


# -----------------------------------------------------------------------------
# Rules broken by calls that ran, the same count on every arm
# -----------------------------------------------------------------------------


def broken_rules(trajectory: list[Any], owners: dict[str, str]) -> list[dict[str, Any]]:
    """Each call that reached the tools, succeeded, and broke one of RULES.md's rules.

    Walks the conversation the way the rules arm's host does: the authenticated
    user is the first id a lookup returned, and the confirmation is the user's
    message before the call.
    """
    calls: dict[str, Any] = {}
    out: list[dict[str, Any]] = []
    user_id: str | None = None
    last_user = ""
    for m in trajectory:
        if isinstance(m, UserMessage):
            if m.content:
                last_user = m.content
            continue
        for tc in getattr(m, "tool_calls", None) or []:
            calls[tc.id] = (tc, last_user, user_id)
        tms = getattr(m, "tool_messages", None) or ([m] if isinstance(m, ToolMessage) else [])
        for tm in tms:
            if tm.id not in calls or tm.error or tm.execution_status != "executed":
                continue
            tc, said, authed = calls[tc_id := tm.id]
            del calls[tc_id]
            name, args = tc.name, tc.arguments or {}
            if name in retail_api.LOOKUPS and user_id is None:
                user_id = tm.content
            broke = []
            if name not in retail_api.OPEN and authed is None:
                broke.append(1)
            if authed is not None and (
                ("user_id" in args and args["user_id"] != authed)
                or owners.get(args.get("order_id", ""), authed) != authed
            ):
                broke.append(2)
            if name in retail_api.WRITES and not retail_api.is_yes(said):
                broke.append(3)
            if broke:
                out.append({"tool": name, "rules": broke, "user_said": said[:200]})
    return out


# -----------------------------------------------------------------------------
# The run
# -----------------------------------------------------------------------------

_write = threading.Lock()
_stop = threading.Event()  # set once the provider refuses the account


class Skipped(Exception):
    """An episode not started because the run is stopping."""


def _job(*args: Any) -> dict[str, Any]:
    # A worker takes its next job before the main thread hears of the refusal, so
    # a job checks here too rather than starting a conversation that cannot finish.
    if _stop.is_set():
        raise Skipped
    try:
        return episode(*args)
    except OutOfCredit:
        _stop.set()  # here, before this worker can take another job
        raise


def _now() -> str:
    """UTC, as bench/claude_provider.py stamps its calls, so a run's calls can be found."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _llm_args(model: str) -> dict[str, Any]:
    return {
        "temperature": 0.0,
        **LOCAL.get(model, {}),
        **({"timeout": 900} if model in LOCAL else {}),
    }


def _cost(trajectory: list[Any], role: type, model: str) -> tuple[int, int, float | None]:
    tin = tout = 0
    for m in trajectory:
        if isinstance(m, role) and getattr(m, "usage", None):
            tin += m.usage.get("prompt_tokens", 0) or 0
            tout += m.usage.get("completion_tokens", 0) or 0
    price = PRICES.get(model)
    return tin, tout, (round((tin * price[0] + tout * price[1]) / 1e6, 5) if price else None)


def _grade(sim: Any, task: Any, domain: str) -> dict[str, Any]:
    """τ²-bench's full grade: every component in the task's reward basis, multiplied.

    The judge's reply is parsed as JSON and occasionally is not; it is asked again
    up to twice, and if it still fails the assertions are recorded as ungraded,
    never as failed.
    """
    last: Exception | None = None
    for _ in range(3):
        try:
            info = evaluate_simulation(
                simulation=sim,
                task=task,
                evaluation_type=EvaluationType.ALL,
                solo_mode=False,
                domain=domain,
                communicate_scoring=COMMUNICATE[domain],
            )
            break
        except Exception as exc:
            if out_of_credit(exc):
                raise OutOfCredit(str(exc)) from exc
            last = exc
    else:
        return {"full_reward": None, "nl_reward": None, "judge_error": str(last)[:200]}
    breakdown = info.reward_breakdown or {}
    if domain == "airline":
        return {
            "full_reward": info.reward,
            "communicate_reward": breakdown.get(RewardType.COMMUNICATE),
            "communicate_unmet": [c.info for c in info.communicate_checks or [] if not c.met],
        }
    return {
        "full_reward": info.reward,
        "nl_reward": breakdown.get(RewardType.NL_ASSERTION),
        "nl_unmet": [c.nl_assertion for c in info.nl_assertions or [] if not c.met],
    }


def episode(domain: str, arm: str, model: str, task: Any, trial: int) -> dict[str, Any]:
    config = TextRunConfig(
        domain=domain,
        agent="llm_agent",
        llm_agent=MODELS[model],
        llm_args_agent=_llm_args(model),
        user="user_simulator",
        llm_user=MODELS[USER_MODEL],
        llm_args_user=_llm_args(USER_MODEL),
        seed=SEED + trial,
    )
    orch = build_text_orchestrator(config, task, seed=SEED + trial)
    owners = _owners(orch.environment) if domain == "retail" else {}
    if arm != "stock":
        env = CharterEnv(orch.environment, ruled=arm == "charter_rules")
        orch.environment = env
        orch.agent = SessionAgent(
            tools=env.get_tools(),
            domain_policy=orch.agent.domain_policy,
            llm=MODELS[model],
            llm_args=_llm_args(model),
            session=env.session,
        )
    row: dict[str, Any] = {
        "domain": domain,
        "arm": arm,
        "model": model,
        "task": task.id,
        "trial": trial,
        "started_at": _now(),
    }
    t0 = time.time()
    try:
        sim = run_simulation(orch, evaluation_type=EvaluationType.ENV)
    except Exception as exc:  # recorded, never folded into the reward
        if out_of_credit(exc):
            raise OutOfCredit(str(exc)) from exc
        row.update(reward=None, error=f"{type(exc).__name__}: {str(exc)[:300]}")
        row["seconds"] = round(time.time() - t0, 1)
        row["finished_at"] = _now()
        return row
    traj = sim.messages
    graded = _grade(sim, task, domain) if JUDGED else {}
    if TRAJECTORIES is not None:
        with _write, gzip.open(TRAJECTORIES / f"{model}.jsonl.gz", "at") as f:
            f.write(
                json.dumps(
                    {
                        "domain": domain,
                        "arm": arm,
                        "task": task.id,
                        "trial": trial,
                        "simulation": sim.model_dump(mode="json"),
                    }
                )
                + "\n"
            )
    a_in, a_out, a_cost = _cost(traj, AssistantMessage, model)
    u_in, u_out, u_cost = _cost(traj, UserMessage, USER_MODEL)
    refusals = orch.environment.session.refusals if arm != "stock" else []
    row.update(
        reward=sim.reward_info.reward if sim.reward_info else None,
        **graded,
        termination=str(sim.termination_reason),
        messages=len(traj),
        tool_calls=sum(len(getattr(m, "tool_calls", None) or []) for m in traj),
        refused=len(refusals),
        refusals=[
            {"tool": r["tool"], "message": r["message"][:240], **_rules_of(r)} for r in refusals
        ],
        broken=(
            broken_rules(traj, owners)
            if domain == "retail"
            else airline_api.broken_rules(traj, task)
        ),
        agent_tokens=[a_in, a_out],
        agent_cost_usd=a_cost,
        user_tokens=[u_in, u_out],
        user_cost_usd=u_cost,
        seconds=round(time.time() - t0, 1),
        finished_at=_now(),
    )
    return row


def _rules_of(refusal: dict[str, Any]) -> dict[str, Any]:
    return {"rules": refusal["rules"]} if "rules" in refusal else {}


def _key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    """What an episode is, for resuming. Rows from before airline are all retail."""
    return (row.get("domain", "retail"), row["arm"], row["task"], row["trial"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="glm-5p3-flash", choices=sorted(MODELS))
    ap.add_argument("--domain", default="retail", help="retail, airline, or both in run order")
    ap.add_argument("--arms", default="stock,charter_plain,charter_rules")
    ap.add_argument("--split", default="test", help="τ²-bench's task split; base is every task")
    ap.add_argument("--tasks", type=int, default=20, help="the first N of the split; 0 for all")
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="", help="a run name: results go to results/bench/tau/<out>/")
    ap.add_argument(
        "--judge",
        action="store_true",
        help="also grade what τ²-bench grades with an LLM: retail's NL assertions, airline's "
        "communicated facts (see JUDGE_MODEL)",
    )
    ap.add_argument(
        "--fireworks-budget",
        type=float,
        default=15.0,
        help="stop (exit 4) once the customer's Fireworks spend in this run's records reaches it",
    )
    args = ap.parse_args()
    global JUDGED, TRAJECTORIES
    JUDGED = args.judge

    domains = args.domain.split(",")
    tasks = {d: TASKS[d](args.split)[: args.tasks or None] for d in domains}
    jobs = [
        (domain, arm, task, trial)
        for trial in range(args.trials)
        for domain in domains
        for task in tasks[domain]
        for arm in args.arms.split(",")
    ]
    out_dir = OUT_DIR / args.out if args.out else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.out:
        TRAJECTORIES = out_dir / "conversations"
        TRAJECTORIES.mkdir(exist_ok=True)
    out = out_dir / f"{args.model}.jsonl"
    done = set()
    spent = 0.0
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            spent += r.get("user_cost_usd") or 0.0
            if r.get("error") is None:
                done.add(_key(r))
    if spent >= args.fireworks_budget:
        print(f"Fireworks spend in these records is ${spent:.2f}, at the budget", flush=True)
        raise SystemExit(4)
    jobs = [j for j in jobs if (j[0], j[1], j[2].id, j[3]) not in done]
    print(f"{len(jobs)} episodes to run, {len(done)} already recorded", flush=True)

    written, stopped, over = 0, "", False
    _stop.clear()
    with ThreadPoolExecutor(args.workers) as pool, out.open("a") as f:
        futures = [pool.submit(_job, d, arm, args.model, t, k) for d, arm, t, k in jobs]
        for fut in as_completed(futures):
            try:
                row = fut.result()
            except OutOfCredit as exc:
                if not stopped:
                    stopped = str(exc)[:500] or "out of credit"
                    _stop.set()
                    for pending in futures:
                        pending.cancel()
                continue
            except (CancelledError, Skipped):
                continue
            with _write:
                f.write(json.dumps(row) + "\n")
                f.flush()
            written += 1
            spent += row.get("user_cost_usd") or 0.0
            if spent >= args.fireworks_budget and not over:
                over = True
                _stop.set()
                for pending in futures:
                    pending.cancel()
            brief = {
                k: row.get(k)
                for k in ("domain", "arm", "task", "trial", "reward", "refused", "seconds")
            }
            print(written, json.dumps(brief), len(row.get("broken", [])), flush=True)
    if stopped:
        print(
            f"stopped: the model provider refused the account (credits or billing). {written} "
            "episodes recorded; rerun the same command to finish the rest.",
            flush=True,
        )
        print(f"provider said: {stopped}", flush=True)
        raise SystemExit(3)
    if over:
        print(
            f"stopped: the customer's Fireworks spend reached ${spent:.2f} "
            f"(--fireworks-budget {args.fireworks_budget}). {written} episodes recorded.",
            flush=True,
        )
        raise SystemExit(4)


if __name__ == "__main__":
    if not os.environ.get("FIREWORKS_API_KEY"):
        sys.exit("FIREWORKS_API_KEY is needed for the user simulator")
    main()
