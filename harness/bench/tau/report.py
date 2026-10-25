"""Summarise ``results/bench/tau/[<run>/]<model>.jsonl`` into ``summary.md`` beside it.

    python report.py glm-5p3-flash [claude-sonnet ...]
    python report.py --run run2 glm-5p3-flash ...

Per arm: τ²-bench's DB reward over episodes, and where the run was judged, the
full reward (the DB check times the natural-language assertions), pass^k over tasks (every trial of the
task passed), the calls that broke a rule of ``RULES.md`` and still ran, Charter's
refusals by rule, and how episodes ended. An episode the evaluator could not score
is listed, never counted as a failure.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "bench" / "tau"
ARMS = ["stock", "charter_plain", "charter_rules"]


def refusal_kind(message: str) -> str:
    if "No user has been authenticated" in message:
        return "rule 1"
    if "different user" in message or "not the user authenticated" in message:
        return "rule 2"
    if "explicit yes" in message:
        return "rule 3"
    return "types"


def load(run_dir: Path, model: str) -> list[dict[str, Any]]:
    path = run_dir / f"{model}.jsonl"
    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        key = (r["arm"], r["task"], r["trial"])
        if key not in latest or latest[key].get("error"):
            latest[key] = r
    return list(latest.values())


def section(model: str, rows: list[dict[str, Any]]) -> list[str]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    arms = [a for a in ARMS if a in by_arm]
    out = [f"## {model}", ""]
    judged = any("full_reward" in r for r in rows)
    out += [
        "| arm | DB pass | "
        + ("DB and assertions | assertions unmet, DB right | " if judged else "")
        + "pass^1 | pass^k | broke a rule and ran | refused (1 / 2 / 3 / types) "
        "| too many errors | unscored | agent $/episode |",
        "|---|---:|" + ("---:|---:|" if judged else "") + "---:|---:|---:|---|---:|---:|---:|",
    ]
    for arm in arms:
        rs = by_arm[arm]
        scored = [r for r in rs if r.get("reward") is not None]
        passed = sum(1 for r in scored if r["reward"] == 1.0)
        tasks: dict[str, list[float]] = defaultdict(list)
        for r in scored:
            tasks[r["task"]].append(r["reward"])
        k = max((len(v) for v in tasks.values()), default=0)
        full = {t: v for t, v in tasks.items() if len(v) == k}
        pass1 = sum(sum(v) / len(v) for v in full.values()) / len(full) if full else 0
        passk = sum(1 for v in full.values() if all(x == 1.0 for x in v))
        broken = Counter(n for r in scored for b in r.get("broken", []) for n in b["rules"])
        refused = Counter(refusal_kind(x["message"]) for r in scored for x in r.get("refusals", []))
        ref = " / ".join(str(refused[kind]) for kind in ("rule 1", "rule 2", "rule 3", "types"))
        many = sum(1 for r in scored if "TOO_MANY_ERRORS" in (r.get("termination") or ""))
        costs = [r["agent_cost_usd"] for r in scored if r.get("agent_cost_usd") is not None]
        cost = f"{sum(costs) / len(costs):.4f}" if costs else "n/a"
        brk = sum(broken.values())
        brk_text = (
            f"{brk} ({', '.join(f'rule {n}: {c}' for n, c in sorted(broken.items()))})"
            if brk
            else "0"
        )
        graded = ""
        if judged:
            fr = [r for r in scored if r.get("full_reward") is not None]
            both = sum(1 for r in fr if r["full_reward"] == 1.0)
            unmet = sum(1 for r in fr if r["reward"] == 1.0 and r.get("nl_reward") == 0.0)
            ungraded = len(scored) - len(fr)
            graded = f"{both}/{len(fr)}" + (f" ({ungraded} ungraded)" if ungraded else "")
            graded = f"{graded} | {unmet} | "
        out.append(
            f"| {arm} | {passed}/{len(scored)} | {graded}{pass1:.0%} | {passk}/{len(full)} (k={k}) "
            f"| {brk_text} | {ref} | {many} | {len(rs) - len(scored)} | {cost} |"
        )
    out.append("")
    # Per task, so a difference can be read back to the conversations.
    out += ["| task | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for task in sorted({r["task"] for r in rows}, key=int):
        cells = []
        for arm in arms:
            rs = sorted((r for r in by_arm[arm] if r["task"] == task), key=lambda r: r["trial"])
            cells.append(
                " ".join(
                    "?" if r.get("reward") is None else ("✓" if r["reward"] == 1.0 else "✗")
                    for r in rs
                )
            )
        out.append(f"| {task} | " + " | ".join(cells) + " |")
    out.append("")
    unscored = [r for r in rows if r.get("reward") is None]
    if unscored:
        out += ["Unscored episodes:", ""]
        out += [
            f"- {r['arm']} task {r['task']} trial {r['trial']}: {r.get('error', '')[:160]}"
            for r in unscored
        ]
        out.append("")
    # Rule 3 reads the start of the message. What the user said instead, in the
    # first 200 characters the row keeps of it:
    said: Counter[str] = Counter()
    for r in rows:
        for b in r.get("broken", []) if r["arm"] in ("stock", "charter_plain") else []:
            if 3 not in b["rules"]:
                continue
            words = re.sub(r"[^\w\s]", " ", b["user_said"].lower()).split()
            said["a yes later in the message" if "yes" in words else "no yes in it"] += 1
    if said:
        out += [
            "Writes on stock and charter_plain that rule 3 would have refused, by what the "
            "user's message said: " + ", ".join(f"{w}: {c}" for w, c in said.most_common()),
            "",
        ]
    return out


def main() -> None:
    args = sys.argv[1:]
    run = ""
    if args[:1] == ["--run"]:
        run, args = args[1], args[2:]
    run_dir = OUT_DIR / run if run else OUT_DIR
    models = args or ["glm-5p3-flash"]
    grading = (
        "The DB check, and the full reward: the DB check times the natural-language "
        "assertions, judged by glm-5p3-flash in place of the OpenAI model τ²-bench names."
        if run
        else "DB reward only (the NL-assertion judge is not run)."
    )
    lines = [
        "# τ²-bench retail, stock against Charter",
        "",
        f"{grading} 'Broke a rule and ran' counts "
        "calls that reached the tools, succeeded, and break a rule of RULES.md, on every "
        "arm alike. Generated by bench/tau/report.py.",
        "",
    ]
    for model in models:
        lines += section(model, load(run_dir, model))
    (run_dir / "summary.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
