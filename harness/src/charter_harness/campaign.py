"""
A campaign: every arm x every model over the same scenarios, then a report.

    charter-harness run --name phase1 --arms charter,raw --models nemotron --epochs 3
    charter-harness report results/phase1

``run`` uses Inspect's ``eval_set`` so a campaign is resumable: re-running the
same command in the same directory finishes what did not complete and leaves
what did alone. ``report`` turns the logs in a results directory into
``summary.md`` and ``summary.json`` — the only place the essay's numbers may
come from.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

from inspect_ai import eval_set

from charter_harness.scenarios.registry import select
from charter_harness.settings import Settings, load, wire_packs
from charter_harness.task import DEFAULT_MESSAGE_LIMIT, DEFAULT_TIME_LIMIT, build_task
from charter_harness.world._http import WorldError

__all__ = ["MODELS", "run", "main"]

# Short names for the models a campaign can name. Both run on Fireworks with the
# same key; the second is the swap arm. MiniMax-M2.7 (`minimax-m2p7`) is still
# in the Fireworks catalogue but no longer deployed serverless — completions
# 404 — so the swap arm is its successor, MiniMax-M3.
MODELS: dict[str, str] = {
    "nemotron": "fireworks/accounts/fireworks/models/nemotron-3-ultra-nvfp4",
    "minimax": "fireworks/accounts/fireworks/models/minimax-m3",
    # The campaign pair: `lightning` is ~3B active parameters and the cheapest
    # tool-calling model Fireworks serves ($0.05/$0.20 per M against Ultra's
    # $0.60/$2.40), which is what makes it the headline rather than a
    # concession. `glm` is the swap arm - a different lineage at a similar price.
    "lightning": "fireworks/accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
    "glm": "fireworks/accounts/fireworks/models/glm-5p3-flash",
}

RESULTS_ROOT = Path(__file__).resolve().parents[2] / "results"


def resolve_model(name: str) -> str:
    return MODELS.get(name, name)


def preflight(models: list[str], api_key: str) -> None:
    """
    One tiny completion per Fireworks model before anything is seeded.

    Without this a dead model id still costs a seed and a teardown against the
    real accounts for every scenario-epoch, and the report shows it as "errors"
    that look like the agent's fault.
    """
    import httpx

    for model in models:
        if not model.startswith("fireworks/"):
            continue
        model_id = model.removeprefix("fireworks/")
        response = httpx.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_id,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise SystemExit(
                f"model {model_id} is not usable on Fireworks: {response.status_code} {response.text[:300]}"
            )


def preflight_world(settings: Settings, packs: frozenset[str]) -> None:
    """
    The one-time prerequisites a credential check cannot see.

    GitHub's token can be valid while the sandbox repository it must write to
    does not exist; every GitHub scenario-epoch would then seed-fail and be
    reported as a harness error. Check it once, up front, with the world
    client's own message about how to fix it.
    """
    import asyncio

    from charter_harness.world import World

    async def check() -> None:
        world = World(wire_packs(settings, packs & {"github"}))
        try:
            if "github" in packs:
                await world.github.ensure_sandbox()
        finally:
            await world.aclose()

    if "github" in packs:
        try:
            asyncio.run(check())
        except WorldError as exc:
            raise SystemExit(f"GitHub is not ready: {exc}") from exc


def run(
    *,
    name: str,
    arms: list[str],
    models: list[str],
    scenarios: str = "all",
    epochs: int = 3,
    max_samples: int = 2,
    max_connections: int = 4,
    message_limit: int = DEFAULT_MESSAGE_LIMIT,
    time_limit: int = DEFAULT_TIME_LIMIT,
    keep_fixtures: bool = False,
    retry_attempts: int = 2,
    variants: bool = False,
) -> Path:
    settings = load()
    if settings.fireworks_api_key:
        # Inspect's ``fireworks/`` provider reads the environment, so hand it the
        # resolved key (which already prefers a non-empty environment over the file).
        os.environ["FIREWORKS_API_KEY"] = settings.fireworks_api_key
    resolved_models = [resolve_model(m) for m in models]
    preflight(resolved_models, settings.fireworks_api_key or "")
    chosen = select(scenarios, available=settings.available(), variants=variants)
    if not chosen:
        raise SystemExit(
            f"no runnable scenario matches {scenarios!r} with the configured providers {sorted(settings.available())}"
        )
    preflight_world(settings, frozenset(p for s in chosen for p in s.packs))

    log_dir = RESULTS_ROOT / name
    log_dir.mkdir(parents=True, exist_ok=True)

    tasks = [
        build_task(
            arm=arm,
            scenarios=scenarios,
            epochs=epochs,
            message_limit=message_limit,
            time_limit=time_limit,
            keep_fixtures=keep_fixtures,
            variants=variants,
        )
        for arm in arms
    ]
    success, logs = eval_set(
        tasks=tasks,
        model=resolved_models,
        log_dir=str(log_dir),
        max_samples=max_samples,
        max_connections=max_connections,
        retry_attempts=retry_attempts,
        log_level="warning",
    )
    print(
        f"campaign {name}: {'complete' if success else 'INCOMPLETE'} — {len(logs)} log(s) in {log_dir}"
    )
    return log_dir


def _install_stack_dumper() -> None:
    """``kill -USR1 <pid>`` writes every thread's stack to /tmp/charter-stacks.txt.

    A campaign stalls roughly half the time it runs, and the cause has resisted
    diagnosis from the outside — socket states and buffer mtimes produced a wrong
    theory and a fix that did not hold. This says which await is actually blocked
    and whose code it is in. py-spy would do the same without a code change, but
    it requires root on macOS; faulthandler does not.

    The file is opened for the life of the process because faulthandler writes to
    the descriptor from a signal handler, where opening one is not safe.
    """
    import faulthandler

    handle = open("/tmp/charter-stacks.txt", "a", buffering=1)  # noqa: SIM115 - see docstring
    handle.write(f"\n===== pid {os.getpid()} armed =====\n")
    faulthandler.register(signal.SIGUSR1, file=handle, all_threads=True, chain=False)


def main(argv: list[str] | None = None) -> int:
    _install_stack_dumper()
    parser = argparse.ArgumentParser(prog="charter-harness", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run arms x models over the scenarios")
    p_run.add_argument("--name", required=True, help="results/<name>/ receives the logs")
    p_run.add_argument("--arms", default="charter,raw")
    p_run.add_argument(
        "--models", default="nemotron", help=f"comma-separated; short names: {', '.join(MODELS)}"
    )
    p_run.add_argument("--scenarios", default="all", help="all | id,id,... | pack name")
    p_run.add_argument("--epochs", type=int, default=3)
    p_run.add_argument(
        "--max-samples", type=int, default=2, help="samples in flight per task (quota-bound)"
    )
    p_run.add_argument("--max-connections", type=int, default=4)
    p_run.add_argument("--message-limit", type=int, default=DEFAULT_MESSAGE_LIMIT)
    p_run.add_argument("--time-limit", type=int, default=DEFAULT_TIME_LIMIT)
    p_run.add_argument("--keep-fixtures", action="store_true", help="skip teardown (debugging)")
    p_run.add_argument(
        "--variants",
        action="store_true",
        help="phase 3: include every parametric variant of the selected templates",
    )
    p_run.add_argument("--no-report", action="store_true")

    p_list = sub.add_parser("list", help="list the scenarios a selection resolves to")
    p_list.add_argument("--scenarios", default="all")
    p_list.add_argument("--variants", action="store_true")
    p_list.add_argument(
        "--all-providers", action="store_true", help="ignore which providers are configured"
    )

    p_rep = sub.add_parser("report", help="summarise the logs in a results directory")
    p_rep.add_argument("directory")

    args = parser.parse_args(argv)

    if args.command == "run":
        log_dir = run(
            name=args.name,
            arms=[a.strip() for a in args.arms.split(",") if a.strip()],
            models=[m.strip() for m in args.models.split(",") if m.strip()],
            scenarios=args.scenarios,
            epochs=args.epochs,
            max_samples=args.max_samples,
            max_connections=args.max_connections,
            message_limit=args.message_limit,
            time_limit=args.time_limit,
            keep_fixtures=args.keep_fixtures,
            variants=args.variants,
        )
        if not args.no_report:
            from charter_harness.report import write_report

            paths = write_report(log_dir)
            print("report:", ", ".join(str(p) for p in paths))
        return 0

    if args.command == "report":
        from charter_harness.report import write_report

        paths = write_report(Path(args.directory))
        print("report:", ", ".join(str(p) for p in paths))
        return 0

    if args.command == "list":
        from charter_harness.scenarios import select

        settings = load()
        available = None if args.all_providers else settings.available()
        chosen = select(args.scenarios, available=available, variants=args.variants)
        for s in chosen:
            print(f"{s.id:48} {','.join(s.requires)}")
        print(
            f"{len(chosen)} scenario(s)"
            + (
                ""
                if args.all_providers
                else f"; configured providers: {', '.join(sorted(settings.available()))}"
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
