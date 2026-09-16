"""
The Inspect task: seed, act, read back, judge, tear down — per sample.

One sample per scenario; ``epochs`` repeats each. The arm decides the tool
surface, and nothing else differs between two runs of the same scenario: same
model, same system prompt, same task text, same credentials, same limits, same
guard.

    inspect eval charter_harness/task.py@harness -T arm=charter -T scenarios=all --epochs 3 \\
        --model fireworks/accounts/fireworks/models/nemotron-3-ultra-nvfp4

Scoring never reads the transcript for the verdict. The scorer calls the
scenario's ``observe`` through the world clients, then its pure ``judge``. The
transcript and the ledger only supply the diagnostics in ``Score.metadata``.
``score_on_error=True`` means a run that crashed or hit a limit is still graded
by what it left in the world, which is the only honest way to grade it.
"""

from __future__ import annotations

import logging
import os

from inspect_ai import Epochs, Task, task
from inspect_ai.agent import AgentPrompt, as_solver, react
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Scorer, Target, accuracy, scorer, stderr
from inspect_ai.solver import Generate, Solver, TaskState, solver

from charter_harness.arms import Arm, arm_by_name
from charter_harness.arms.ledger import ledger
from charter_harness.context import mint_namespace, run_context
from charter_harness.guard import guard_policy
from charter_harness.scenarios import Scenario, select
from charter_harness.settings import Settings, Wiring, load, wire_packs
from charter_harness.world import World, WorldError

__all__ = ["SYSTEM_PROMPT", "harness", "build_task"]

logger = logging.getLogger(__name__)

# Identical on every arm and model. It says what the job is and how to behave;
# it says nothing about which tools exist or how to call them — the tool
# surface is the experimental variable and must not leak into the constant.
SYSTEM_PROMPT = """You are an operations assistant acting on the user's real business accounts through the tools provided.

Complete the task exactly as written. Read the current state before you change it, and where a read-back is cheap, confirm what you changed. Do not ask the user questions — nobody is there to answer; take the most reasonable interpretation and proceed. Never send email. Do not modify anything the task does not ask you to modify.

When the task is complete, call submit() with a short summary of what you did and the identifiers of anything you created."""

DEFAULT_MESSAGE_LIMIT = 60
DEFAULT_TIME_LIMIT = 900  # seconds per sample


# ------------------------------------------------------------------ solvers


@solver
def seed_world(world: World, scenarios: dict[str, Scenario], settings: Settings) -> Solver:
    """Mint the namespace, seed the fixtures, and rewrite the user message."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        scenario = scenarios[str(state.metadata["scenario"])]
        ns = mint_namespace()
        ctx = run_context()
        ctx.ns = ns
        ctx.scenario = scenario.id
        ctx.packs = list(scenario.packs)
        ctx.github_owner = settings.github_owner or ""

        try:
            expected = await scenario.seed(world, ns)
        except Exception as exc:
            # Recorded so the scorer can file this as a harness error rather than
            # grade an agent that never got a world to act on. Re-raised so the
            # agent does not run.
            ctx.seed_error = f"{type(exc).__name__}: {exc}"
            raise
        ctx.expected = expected
        ctx.seeded = True
        ctx.owned = {k: [str(i) for i in v] for k, v in scenario.owned(expected).items()}

        prompt = scenario.prompt(ns, expected)
        state.messages = [m for m in state.messages if m.role != "user"]
        state.messages.append(ChatMessageUser(content=prompt))
        state.metadata["ns"] = ns
        state.metadata["prompt"] = prompt
        return state

    return solve


@solver
def act(arm: Arm, wiring: Wiring, scenarios: dict[str, Scenario]) -> Solver:
    """Build the arm's tools for this scenario and run the react agent on them."""

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        scenario = scenarios[str(state.metadata["scenario"])]
        tools = arm.tools(scenario.packs, wiring)
        agent = react(
            prompt=AgentPrompt(instructions=SYSTEM_PROMPT),
            tools=tools,
            submit=True,
        )
        return await as_solver(agent)(state, generate)

    return solve


# ------------------------------------------------------------------- scorer


@scorer(metrics=[accuracy(), stderr()])
def state_scorer(world: World, scenarios: dict[str, Scenario]) -> Scorer:
    async def score(state: TaskState, target: Target) -> Score:
        ctx = run_context()
        scenario = scenarios[ctx.scenario]
        led = ledger()
        if not ctx.seeded:
            return Score(
                value=INCORRECT,
                answer="",
                explanation=f"harness error: seed failed: {ctx.seed_error or 'unknown'}",
                metadata={**led.summary(), "ns": ctx.ns, "scenario": ctx.scenario, "harness_error": "seed", "detail": ctx.seed_error},
            )
        try:
            observed = await scenario.observe(world, ctx.ns, ctx.expected)
        except WorldError as exc:
            return Score(
                value=INCORRECT,
                answer=state.output.completion[:500] if state.output else "",
                explanation=f"harness error: observe failed: {exc}",
                metadata={**led.summary(), "ns": ctx.ns, "scenario": ctx.scenario, "harness_error": "observe", "detail": str(exc)},
            )
        verdict = scenario.judge(ctx.expected, observed)
        return Score(
            value=CORRECT if verdict.correct else INCORRECT,
            answer=state.output.completion[:500] if state.output else "",
            explanation=verdict.explanation,
            metadata={
                **led.summary(),
                "ns": ctx.ns,
                "scenario": ctx.scenario,
                "packs": list(scenario.packs),
                "observed": observed,
                "expected": ctx.expected,
                "completed": state.completed,
            },
        )

    return score


# ------------------------------------------------------------------ cleanup


def make_cleanup(world: World, scenarios: dict[str, Scenario], keep: bool):
    async def cleanup(state: TaskState) -> None:
        if keep:
            return
        ctx = run_context()
        if not ctx.scenario or not ctx.ns:
            return
        if not ctx.seeded:
            # The seed did not finish, so there is no ground truth to tear down
            # by. Whatever it did create carries the namespace; name it.
            logger.warning("seed for %s failed; anything tagged %s is left for a manual sweep", ctx.scenario, ctx.ns)
            return
        scenario = scenarios[ctx.scenario]
        await scenario.teardown(world, ctx.ns, ctx.expected)

    return cleanup


# --------------------------------------------------------------------- task


def build_task(
    *,
    arm: str = "charter",
    scenarios: str = "all",
    epochs: int = 1,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
    time_limit: int = DEFAULT_TIME_LIMIT,
    keep_fixtures: bool = False,
    only_available: bool = True,
    variants: bool = False,
) -> Task:
    settings = load()
    if settings.fireworks_api_key and not os.environ.get("FIREWORKS_API_KEY"):
        os.environ["FIREWORKS_API_KEY"] = settings.fireworks_api_key

    chosen = select(scenarios, available=settings.available() if only_available else None, variants=variants)
    if not chosen:
        raise ValueError(
            f"no scenarios selected by {scenarios!r} with configured providers {sorted(settings.available())}"
        )
    needed = frozenset(p for s in chosen for p in s.requires)
    wiring = wire_packs(settings, needed)
    world = World(wiring)
    by_id = {s.id: s for s in chosen}
    the_arm = arm_by_name(arm)

    dataset = [
        Sample(
            id=s.id,
            input="(the task is written by the seed step)",
            metadata={
                "scenario": s.id,
                "template": s.template,
                "variant": s.variant,
                "params": s.params,
                "packs": list(s.packs),
                "summary": s.summary,
            },
        )
        for s in chosen
    ]

    return Task(
        name=f"harness-{arm}",
        dataset=dataset,
        setup=seed_world(world, by_id, settings),
        solver=act(the_arm, wiring, by_id),
        scorer=state_scorer(world, by_id),
        cleanup=make_cleanup(world, by_id, keep_fixtures),
        approval=guard_policy(),
        epochs=Epochs(epochs, ["mean"]),
        message_limit=message_limit,
        time_limit=time_limit,
        fail_on_error=False,
        score_on_error=True,
        metadata={"arm": arm, "scenarios": [s.id for s in chosen], "variants": variants},
    )


@task
def harness(
    arm: str = "charter",
    scenarios: str = "all",
    epochs: int = 1,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
    time_limit: int = DEFAULT_TIME_LIMIT,
    keep_fixtures: bool = False,
    variants: bool = False,
) -> Task:
    """The scenario harness. ``-T arm=charter|raw -T scenarios=all|<id,...>|<pack> -T variants=true``."""
    return build_task(
        arm=arm,
        scenarios=scenarios,
        epochs=epochs,
        message_limit=message_limit,
        time_limit=time_limit,
        keep_fixtures=keep_fixtures,
        variants=variants,
    )
