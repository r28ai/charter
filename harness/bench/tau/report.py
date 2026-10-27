"""Summarise ``results/bench/tau/[<run>/]<model>.jsonl`` into ``summary.md`` beside it.

    python report.py glm-5p3-flash [claude-sonnet ...]
    python report.py --run run2 glm-5p3-flash ...
    python report.py --run <run> --trials 1 claude-sonnet   # only the trials every task completed

One section per domain and model. Per arm: τ²-bench's DB check, and where the run
was judged its full grade (retail: the DB check times the natural-language
assertions; airline: times the facts the agent had to communicate); pass^1 to
pass^k over tasks; the calls that broke a rule of the domain's rules file and still
ran, counted on every arm alike; the conversations among them τ²-bench graded as
passes; Charter's refusals by rule; and how episodes ended. Then, between stock and
charter_rules, the tasks a refusal lost and the ones it gained, what the agent did
after a refusal (from the saved conversations), how much each arm moved between
trials, and what the run cost. An episode the evaluator could not score is listed,
never counted as a failure.

The summaries of runs made before airline (``summary.md``, ``run2/summary.md``)
were written by the earlier version of this file and are kept as they were.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "results" / "bench" / "tau"
PROVIDER_LOG = OUT_DIR.parent / "claude_provider_calls.jsonl"
ARMS = ["stock", "charter_plain", "charter_rules"]
RULES_FILE = {"retail": "RULES.md", "airline": "RULES_AIRLINE.md"}
FULL = {"retail": "DB and assertions", "airline": "DB and communicated"}


def refusal_kind(message: str) -> str:
    """Retail: which of RULES.md's rules a refusal is, by its words."""
    if "No user has been authenticated" in message:
        return "rule 1"
    if "different user" in message or "not the user authenticated" in message:
        return "rule 2"
    if "explicit yes" in message:
        return "rule 3"
    return "types"


def kinds(domain: str, refusal: dict[str, Any]) -> list[str]:
    if domain == "retail":
        return [refusal_kind(refusal["message"])]
    return [f"rule {n}" for n in refusal.get("rules", [])] or ["types"]


def load(run_dir: Path, model: str) -> list[dict[str, Any]]:
    path = run_dir / f"{model}.jsonl"
    latest: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for line in path.read_text().splitlines():
        r = json.loads(line)
        r.setdefault("domain", "retail")  # rows from before airline
        key = (r["domain"], r["arm"], r["task"], r["trial"])
        if key not in latest or latest[key].get("error"):
            latest[key] = r
    return list(latest.values())


def conversations(run_dir: Path, model: str) -> dict[tuple[str, str, str, int], list[dict]]:
    """Each episode's messages, from ``--out``'s saved conversations, when there are any."""
    path = run_dir / "conversations" / f"{model}.jsonl.gz"
    out: dict[tuple[str, str, str, int], list[dict]] = {}
    if path.exists():
        with gzip.open(path, "rt") as f:
            for line in f:
                c = json.loads(line)
                key = (c.get("domain", "retail"), c["arm"], c["task"], c["trial"])
                out[key] = c["simulation"]["messages"]
    return out


def grade(r: dict[str, Any], judged: bool) -> float | None:
    """The episode's pass or fail: τ²-bench's full grade if judged, else its DB check."""
    if r.get("reward") is None:
        return None
    return r.get("full_reward") if judged else r["reward"]


def pass_hat(tasks: dict[str, list[float]], k: int) -> float:
    """Sierra's pass^k: per task, the chance k trials drawn from its n all pass."""
    scores = [
        comb(sum(x == 1.0 for x in v), k) / comb(len(v), k) for v in tasks.values() if len(v) >= k
    ]
    return sum(scores) / len(scores) if scores else 0.0


def section(domain: str, model: str, rows: list[dict[str, Any]], convs: dict) -> list[str]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    arms = [a for a in ARMS if a in by_arm]
    judged = any("full_reward" in r for r in rows)
    basis = FULL[domain] if judged else "DB"
    out = [f"## {domain}, {model}", ""]
    out += [
        "| arm | DB right | "
        + (f"{FULL[domain]} | " if judged else "")
        + "pass^1 … pass^k | broke a rule and ran | conversations with one | graded a pass "
        "| refused | too many errors | unscored |",
        "|---|---:|" + ("---:|" if judged else "") + "---|---|---:|---:|---|---:|---:|",
    ]
    for arm in arms:
        rs = by_arm[arm]
        scored = [r for r in rs if r.get("reward") is not None]
        db = sum(1 for r in scored if r["reward"] == 1.0)
        tasks: dict[str, list[float]] = defaultdict(list)
        for r in scored:
            g = grade(r, judged)
            if g is not None:
                tasks[r["task"]].append(g)
        k = min((len(v) for v in tasks.values()), default=0)
        hats = " / ".join(f"{pass_hat(tasks, j):.0%}" for j in range(1, k + 1)) or "n/a"
        broken = Counter(n for r in scored for b in r.get("broken", []) for n in b["rules"])
        brk = sum(len(r.get("broken", [])) for r in scored)
        brk_text = (
            f"{brk} ({', '.join(f'rule {n}: {c}' for n, c in sorted(broken.items()))})"
            if brk
            else "0"
        )
        with_one = [r for r in scored if r.get("broken")]
        passed = [r for r in with_one if grade(r, judged) == 1.0]
        refused = Counter(
            x for r in scored for f in r.get("refusals", []) for x in kinds(domain, f)
        )
        ref = (
            ", ".join(f"{kind}: {c}" for kind, c in sorted(refused.items(), key=_by_rule))
            if refused
            else "0"
        )
        many = sum(1 for r in scored if "TOO_MANY_ERRORS" in (r.get("termination") or ""))
        full = ""
        if judged:
            fr = [r for r in scored if r.get("full_reward") is not None]
            both = sum(1 for r in fr if r["full_reward"] == 1.0)
            ungraded = len(scored) - len(fr)
            full = f"{both}/{len(fr)}" + (f" ({ungraded} ungraded)" if ungraded else "") + " | "
        out.append(
            f"| {arm} | {db}/{len(scored)} | {full}{hats} (k={k}) | {brk_text} | {len(with_one)} "
            f"| {len(passed)} | {ref} | {many} | {len(rs) - len(scored)} |"
        )
    out += [
        "",
        f"Pass and fail are by {basis}. 'Broke a rule and ran' counts calls that reached the "
        f"tools, succeeded, and break a rule of {RULES_FILE[domain]}. 'Graded a pass' is "
        "the conversations with at least one such call that τ²-bench scored as a pass.",
        "",
    ]

    # Each graded pass with a broken rule, so it can be read back to its conversation.
    passes = [r for r in rows if r.get("broken") and grade(r, judged) == 1.0 and r["arm"] in by_arm]
    if passes:
        out += ["Conversations τ²-bench graded as passes, with a rule broken and run:", ""]
        for r in sorted(passes, key=lambda r: (r["arm"], int(r["task"]), r["trial"])):
            calls = "; ".join(
                f"{b['tool']} (rule {', '.join(map(str, b['rules']))})" for b in r["broken"]
            )
            out.append(f"- {r['arm']}, task {r['task']}, trial {r['trial']}: {calls}")
        out.append("")

    # Per task, so a difference can be read back to the conversations.
    out += ["| task | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for task in sorted({r["task"] for r in rows}, key=int):
        cells = []
        for arm in arms:
            rs = sorted((r for r in by_arm[arm] if r["task"] == task), key=lambda r: r["trial"])
            cells.append(
                " ".join(
                    "?" if grade(r, judged) is None else ("✓" if grade(r, judged) == 1.0 else "✗")
                    for r in rs
                )
            )
        out.append(f"| {task} | " + " | ".join(cells) + " |")
    out.append("")

    out += _noise(by_arm, arms, judged)
    if "stock" in by_arm and "charter_rules" in by_arm:
        out += _lost_and_gained(domain, by_arm, judged)
    out += _after_refusals(domain, model, by_arm, convs)

    unscored = [r for r in rows if r.get("reward") is None]
    if unscored:
        out += ["Unscored episodes:", ""]
        out += [
            f"- {r['arm']} task {r['task']} trial {r['trial']}: {r.get('error', '')[:160]}"
            for r in unscored
        ]
        out.append("")
    if domain == "retail":
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


def _by_rule(item: tuple[str, int]) -> tuple[int, int]:
    kind = item[0]
    return (int(kind.split()[1]), 0) if kind.startswith("rule ") else (99, 0)


def _noise(by_arm: dict[str, list[dict]], arms: list[str], judged: bool) -> list[str]:
    lines = []
    for arm in arms:
        per: dict[int, list[float]] = defaultdict(list)
        for r in by_arm[arm]:
            g = grade(r, judged)
            if g is not None:
                per[r["trial"]].append(g)
        if len(per) > 1:
            counts = [f"{int(sum(v))}/{len(v)}" for _, v in sorted(per.items())]
            lines.append(f"{arm}: {', '.join(counts)}")
    if not lines:
        return []
    return ["Passes per trial, which is how far an arm moves by chance: " + "; ".join(lines), ""]


def _lost_and_gained(domain: str, by_arm: dict[str, list[dict]], judged: bool) -> list[str]:
    stock = {(r["task"], r["trial"]): r for r in by_arm["stock"] if grade(r, judged) is not None}
    rules = {
        (r["task"], r["trial"]): r for r in by_arm["charter_rules"] if grade(r, judged) is not None
    }
    lost, lost_quiet, gained = [], 0, []
    for key in sorted(stock.keys() & rules.keys(), key=lambda k: (int(k[0]), k[1])):
        s, c = grade(stock[key], judged), grade(rules[key], judged)
        if s == 1.0 and c != 1.0:
            if rules[key].get("refusals"):
                lost.append(rules[key])
            else:
                lost_quiet += 1
        elif s != 1.0 and c == 1.0:
            gained.append(rules[key])
    out = [
        f"Between stock and charter_rules on the same task and trial: charter_rules failed "
        f"{len(lost) + lost_quiet} that stock passed ({len(lost)} with a refusal in the "
        f"conversation, {lost_quiet} without one), and passed {len(gained)} that stock failed.",
        "",
    ]
    for r in lost:
        why = ", ".join(
            sorted(
                {x for f in r["refusals"] for x in kinds(domain, f)}, key=lambda x: _by_rule((x, 0))
            )
        )
        out.append(f"- lost, task {r['task']} trial {r['trial']}: refused by {why}")
    for r in gained:
        why = (
            ", ".join(
                sorted(
                    {x for f in r.get("refusals", []) for x in kinds(domain, f)},
                    key=lambda x: _by_rule((x, 0)),
                )
            )
            or "no refusal"
        )
        out.append(f"- gained, task {r['task']} trial {r['trial']}: {why}")
    if lost or gained:
        out.append("")
    return out


def _after_refusals(domain: str, model: str, by_arm: dict, convs: dict) -> list[str]:
    """What the agent did next after each refusal, by rule."""
    moves: dict[str, Counter[str]] = defaultdict(Counter)
    for arm, rows in by_arm.items():
        for r in rows:
            messages = convs.get((domain, arm, r["task"], r["trial"]))
            if not messages:
                continue
            for i, m in enumerate(messages):
                if m.get("role") != "tool" or m.get("execution_status") != "rejected":
                    continue
                call = _call_of(messages, m["id"])
                kind = kinds(
                    domain,
                    {
                        "message": m.get("content") or "",
                        "rules": _rules_in(domain, m.get("content") or ""),
                    },
                )
                nxt = next((x for x in messages[i + 1 :] if x.get("role") == "assistant"), None)
                if nxt is None:
                    move = "the conversation ended"
                elif nxt.get("tool_calls"):
                    move = (
                        "called the same tool again"
                        if any(t["name"] == (call or {}).get("name") for t in nxt["tool_calls"])
                        else "called another tool"
                    )
                else:
                    move = "spoke to the customer"
                later = any(
                    x.get("role") == "tool"
                    and x.get("execution_status") == "executed"
                    and not x.get("error")
                    and (_call_of(messages, x["id"]) or {}).get("name") == (call or {}).get("name")
                    for x in messages[i + 1 :]
                )
                for k in kind:
                    moves[k][move] += 1
                    if later:
                        moves[k]["the same tool later ran"] += 1
    if not moves:
        return []
    out = ["After a refusal, the agent's next move:", ""]
    for kind, c in sorted(moves.items(), key=lambda kv: _by_rule((kv[0], 0))):
        out.append(f"- {kind}: " + ", ".join(f"{m} {n}" for m, n in c.most_common()))
    out.append("")
    return out


def _rules_in(domain: str, content: str) -> list[int]:
    if domain != "airline":
        return []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from airline_api import refusal_rules

    return refusal_rules(content)


def _call_of(messages: list[dict], call_id: str) -> dict | None:
    for m in messages:
        for t in m.get("tool_calls") or []:
            if t.get("id") == call_id:
                return t
    return None


def cost(rows: list[dict[str, Any]]) -> list[str]:
    """Tokens, the Claude calls' price at API rates, and the customer's Fireworks spend."""
    scored = [r for r in rows if r.get("agent_tokens")]
    if not scored:
        return []
    tin = sum(r["agent_tokens"][0] for r in scored)
    tout = sum(r["agent_tokens"][1] for r in scored)
    user = sum(r.get("user_cost_usd") or 0.0 for r in rows)
    lines = [
        "## Cost",
        "",
        f"- Agent tokens: {tin:,} in and {tout:,} out over {len(scored)} episodes "
        f"({tin // len(scored):,} and {tout // len(scored):,} per episode).",
        f"- The customer on Fireworks (glm-5p3-flash): ${user:.2f}. The judge's calls are "
        "not counted here.",
    ]
    stamps = [r for r in rows if r.get("started_at") and r.get("finished_at")]
    if stamps and PROVIDER_LOG.exists():
        start = min(r["started_at"] for r in stamps)
        end = max(r["finished_at"] for r in stamps)
        calls = [
            json.loads(line)
            for line in PROVIDER_LOG.read_text().splitlines()
            if start <= json.loads(line)["at"] <= end
        ]
        usd = sum(c.get("cost_usd_at_api_prices") or 0.0 for c in calls)
        lines.append(
            f"- Claude through the subscription: {len(calls):,} calls between {start} and {end}, "
            f"${usd:,.2f} at API prices (what the API would have charged; the subscription "
            "was charged nothing extra). Every call the provider served in that window counts, "
            "including the resume probes."
        )
    return [*lines, ""]


def main() -> None:
    args = sys.argv[1:]
    run, trials = "", None
    if args[:1] == ["--run"]:
        run, args = args[1], args[2:]
    if args[:1] == ["--trials"]:
        trials, args = int(args[1]), args[2:]
    run_dir = OUT_DIR / run if run else OUT_DIR
    models = args or ["glm-5p3-flash"]
    sections: list[str] = []
    domains: set[str] = set()
    every: list[dict[str, Any]] = []
    for model in models:
        rows = load(run_dir, model)
        if trials is not None:  # a trial some tasks never reached would skew pass^k
            rows = [r for r in rows if r["trial"] < trials]
        every += rows
        convs = conversations(run_dir, model)
        for domain in ("airline", "retail"):
            mine = [r for r in rows if r["domain"] == domain]
            if mine:
                domains.add(domain)
                sections += section(domain, model, mine, convs)
    lines = [
        f"# τ²-bench {' and '.join(sorted(domains))}, stock against Charter",
        "",
        "Generated by bench/tau/report.py. Judged runs score τ²-bench's LLM-graded parts "
        "with glm-5p3-flash on τ²-bench's own prompts, in place of the OpenAI models it names.",
        "",
        *sections,
        *cost(every),
    ]
    print("\n".join(lines))
    if all("started_at" not in r for r in every):
        print(f"\n(not written: {run_dir / 'summary.md'} predates this report and is kept)")
        return
    (run_dir / "summary.md").write_text("\n".join(lines))


if __name__ == "__main__":
    main()
