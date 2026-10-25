"""Time a tool layer adds to one cheap call, against calling the API directly.

The same read, N times per arm, interleaved in a random order so that network
drift lands on every arm alike. Arms:

- ``direct``: plain ``httpx`` with one shared client. The floor.
- ``charter``: ``tool.ainvoke(..., client=shared)``, the configuration the
  latency page recommends. Charter's own share is also read off its call record
  (``overhead_ms``: validation, transforms, credentials, the response handler).
- ``charter_default``: ``tool.ainvoke(...)`` with no client, which opens a new
  connection per call. Reported because it is the default, not because it is the
  recommended setup.

- ``composio``: the same read through Composio's ``tools/execute``, which runs it on
  Composio's servers for the benchmark's connected account. Gmail only, because
  that is the account connected there. Zapier MCP is not measured.

    cd harness && .venv/bin/python bench/latency.py --n 100

Writes ``results/bench/latency.json``. Read-only calls; prints no credential.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from charter import CallCollector, collecting

from charter_harness.settings import load, wire_packs

OUT = Path(__file__).resolve().parent.parent / "results" / "bench" / "latency.json"


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _summary(xs: list[float]) -> dict[str, float]:
    return {
        "n": len(xs),
        "p50_ms": round(_pct(xs, 0.50), 1),
        "p95_ms": round(_pct(xs, 0.95), 1),
        "mean_ms": round(statistics.fmean(xs), 1),
    }


async def targets(
    s, http: httpx.AsyncClient, google_token: str | None
) -> dict[str, dict[str, Callable[[], Awaitable[Any]]]]:
    from charter.packs import github, gmail, slack

    out: dict[str, dict[str, Callable[[], Awaitable[Any]]]] = {}
    if google_token:
        g = {"Authorization": f"Bearer {google_token}"}

        async def gmail_direct():
            r = await http.get("https://gmail.googleapis.com/gmail/v1/users/me/labels", headers=g)
            r.raise_for_status()

        arms: dict[str, Callable[[], Awaitable[Any]]] = {
            "direct": gmail_direct,
            "charter": lambda: gmail.labels_list.ainvoke(client=http),
            "charter_default": lambda: gmail.labels_list.ainvoke(),
        }
        key, account = _composio("COMPOSIO_API_KEY"), _composio("COMPOSIO_BENCH_ACCOUNT")
        if key and account:

            async def gmail_composio():
                r = await http.post(
                    "https://backend.composio.dev/api/v3/tools/execute/GMAIL_LIST_LABELS",
                    headers={"x-api-key": key},
                    json={
                        "connected_account_id": account,
                        "user_id": "charter-benchmark",
                        "arguments": {},
                        "version": "latest",
                    },
                )
                r.raise_for_status()
                assert r.json().get("successful"), r.text[:200]

            arms["composio"] = gmail_composio
        out["gmail.labels_list"] = arms
    if s.slack_bot_token:
        auth = {"Authorization": f"Bearer {s.slack_bot_token}"}
        me = (await http.post("https://slack.com/api/auth.test", headers=auth)).json()["user_id"]

        async def slack_direct():
            r = await http.get(
                "https://slack.com/api/users.info", params={"user": me}, headers=auth
            )
            assert r.json()["ok"], r.text

        out["slack.users_info"] = {
            "direct": slack_direct,
            "charter": lambda: slack.users_info.ainvoke(user=me, client=http),
            "charter_default": lambda: slack.users_info.ainvoke(user=me),
        }
    if s.github_token:
        gh = {
            "Authorization": f"Bearer {s.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async def github_direct():
            r = await http.get("https://api.github.com/user", headers=gh)
            r.raise_for_status()

        out["github.users_get_authenticated"] = {
            "direct": github_direct,
            "charter": lambda: github.users_get_authenticated.ainvoke(client=http),
            "charter_default": lambda: github.users_get_authenticated.ainvoke(),
        }
    return out


def _composio(name: str) -> str:
    import os

    path = os.environ.get("CHARTER_HARNESS_ENV", "")
    if path:
        for line in Path(path).expanduser().read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip("'\"")
    return os.environ.get(name, "")


async def main(n: int, gap: float, warmup: int) -> None:
    s = load()
    wiring = wire_packs(s, frozenset({"slack", "github", "gmail"}) & s.available())
    google = await wiring.google_token() if "gmail" in s.available() else None
    result: dict[str, Any] = {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n": n,
        "targets": {},
    }
    async with httpx.AsyncClient(timeout=30) as http:
        for name, arms in (await targets(s, http, google)).items():
            for fn in arms.values():  # warm the shared connection and the schema
                for _ in range(warmup):
                    await fn()
            walls: dict[str, list[float]] = {arm: [] for arm in arms}
            overhead: list[float] = []
            schedule = [arm for arm in arms for _ in range(n)]
            random.shuffle(schedule)
            for arm in schedule:
                calls = CallCollector()
                t0 = time.perf_counter()
                with collecting(calls):
                    await arms[arm]()
                walls[arm].append((time.perf_counter() - t0) * 1000)
                if arm == "charter":
                    overhead.append(calls.records[-1].overhead_ms)
                await asyncio.sleep(gap)
            row = {arm: _summary(xs) for arm, xs in walls.items()}
            row["charter_overhead_ms"] = _summary(overhead)
            row["added_p50_ms"] = round(row["charter"]["p50_ms"] - row["direct"]["p50_ms"], 1)
            result["targets"][name] = row
            print(name, json.dumps(row))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--gap", type=float, default=0.35, help="seconds between calls")
    ap.add_argument("--warmup", type=int, default=3)
    args = ap.parse_args()
    asyncio.run(main(args.n, args.gap, args.warmup))
