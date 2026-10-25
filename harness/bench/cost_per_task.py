"""Tokens, wall time and tool calls per *successful* task, from the published campaigns.

Per-run averages charge a failed run the same as a passing one, so an arm that
fails more looks cheaper than it is. Dividing the totals by successes is the
figure a team pays for. Harness-error runs never had a fair task and are left
out of both arms, as in the campaign reports.

    cd harness && .venv/bin/python bench/cost_per_task.py

Reads only ``results/*/summary.json``. No network, no model.
"""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
CAMPAIGNS = {"stage2-final": "breadth", "stage3-final-all": "depth"}
ARMS = {"progressive": "Charter", "raw": "raw"}


def rows() -> list[dict]:
    out = []
    for campaign, label in CAMPAIGNS.items():
        runs = json.loads((RESULTS / campaign / "summary.json").read_text())["runs"]
        for arm, name in ARMS.items():
            fair = [r for r in runs if r["arm"] == arm and not r.get("harness_error")]
            wins = sum(1 for r in fair if r["correct"])

            def total(key: str, fair: list[dict] = fair) -> float:
                return sum(r[key] or 0 for r in fair)

            out.append(
                {
                    "campaign": label,
                    "arm": name,
                    "runs": len(fair),
                    "successes": wins,
                    "tokens_per_success": total("total_tokens") / wins,
                    "wall_seconds_per_success": total("wall_seconds") / wins,
                    "tool_calls_per_success": total("tool_calls") / wins,
                }
            )
    return out


def main() -> None:
    print(
        "| campaign | arm | runs | successes | tokens / success | wall s / success | tool calls / success |"
    )
    print("|---|---|---:|---:|---:|---:|---:|")
    for r in rows():
        print(
            f"| {r['campaign']} | {r['arm']} | {r['runs']} | {r['successes']} | "
            f"{r['tokens_per_success']:,.0f} | {r['wall_seconds_per_success']:.1f} | "
            f"{r['tool_calls_per_success']:.2f} |"
        )


if __name__ == "__main__":
    main()
