"""The AgentDojo table, read off the recorded episodes: one row per model and arm.

    python report.py            # every model with a results file

Utility and attack success are AgentDojo's own judges (``run.py``). A row with an
error is not an episode: the model provider failed, so it is left out, and the
counts say how many episodes each number rests on. Writes ``summary.md`` beside
the results.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "bench" / "agentdojo"
ARMS = ("stock", "tool_filter", "charter_plain", "charter_rules")


def _pct(hit: int, of: int) -> str:
    return f"{hit}/{of} ({100 * hit / of:.0f}%)" if of else ""


def report() -> str:
    lines = [
        "AgentDojo banking v1.2.2, `important_instructions` attack. Utility: the user's task "
        "was done. Attack success: the injected task was done. Both read off the environment "
        "by AgentDojo's own checks.",
        "",
        "| model | arm | utility, no attack | utility under attack | attack success |",
        "|---|---|---:|---:|---:|",
    ]
    for path in sorted(OUT_DIR.glob("*.jsonl")):
        cells: dict[str, list[dict]] = defaultdict(list)
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("error") is None:
                cells[row["arm"]].append(row)
        for arm in ARMS:
            rows = cells.get(arm, [])
            if not rows:
                continue
            clean = [r for r in rows if r["injection_task"] is None]
            attacked = [r for r in rows if r["injection_task"] is not None]
            lines.append(
                f"| {path.stem} | {arm} | {_pct(sum(bool(r['utility']) for r in clean), len(clean))} "
                f"| {_pct(sum(bool(r['utility']) for r in attacked), len(attacked))} "
                f"| {_pct(sum(bool(r['attack_succeeded']) for r in attacked), len(attacked))} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    text = report()
    (OUT_DIR / "summary.md").write_text(text)
    print(text)
