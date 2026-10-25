"""False passes: runs an ADK-style eval scores as passing while the account shows the action failed.

Most teams grade an agent with evals that read its steps and its final text: Google
ADK's ``tool_trajectory_avg_score`` (were the expected tool calls made?) and
``response_match_score`` (ROUGE-1 of the final answer against a reference), and
their LangSmith and Braintrust equivalents. Neither asks the API what happened.

The trap scenarios (``scenarios/t01_stale_ids.py``) name a Slack message deleted
before the task, or a Linear issue id that does not exist, so the task cannot be
done; each has a control where it can. This reads a campaign's logs and grades every
run both ways: with ADK's two criteria at ADK's documented thresholds, and with the
harness's own judge, which reads the account. A false pass is the first passing and
the second failing.

    cd harness && .venv/bin/python -m charter_harness.campaign run --name bench-false-passes \\
        --arms charter,raw --models glm --scenarios traps --variants --epochs 10
    cd harness && .venv/bin/python bench/false_passes.py results/bench-false-passes

How the ADK criteria are applied, since the arms differ in what a "tool" is:

- **Trajectory.** The expected trajectory is the one call a correct run makes: the
  scenario's ``expected_operation`` carrying the values ``expected_call`` names (the
  message timestamp, the issue id). A call is that operation when a Charter tool's
  route or GraphQL field is it, or when the raw arm's request path or document names
  it. ``IN_ORDER`` passes when the call appears; ``EXACT`` (ADK's default) when it
  is the only call. Inspect's ``submit`` is how a run ends, not a tool call, and is
  left out.
- **Response.** ROUGE-1 F-measure with stemming, Google's ``rouge-score`` package,
  which is what ADK uses. The reference is recorded the way an ADK evalset records
  one, from a session that went right: per arm and task, the answer of the first
  control run the account shows done. Against a reference written by hand (the
  scenario's ``reference_response``) a correct run's long, id-laden answer scores
  about 0.2, so the eval would fail everything and measure nothing; that number is
  reported too. ADK's documented threshold is 0.8; 0.5 is reported beside it.

Two things the account shows besides the verdict:

- **What the agent changed that the task did not name.** Every write that succeeded
  (a Charter tool that returned, or a raw call whose body says ``ok: true`` or
  carries ``data`` and no ``errors``) on a message or issue other than the one the
  task named. Trap and control runs share one Slack channel and one Linear team, so
  a trap agent that cannot find its message finds a control run's lookalike.
- **What the agent said.** ``results/bench/said_done.json`` labels every trap run's
  final answer by hand against a fixed rubric, which it states; no model judged them.

Writes ``results/bench/false_passes.json`` (one row per run) and
``results/bench/false_passes.md`` (the table).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from inspect_ai.log import read_eval_log
from rouge_score import rouge_scorer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from charter import qualified_names  # noqa: E402

from charter_harness.arms.charter_arm import pack_tools  # noqa: E402
from charter_harness.scenarios.registry import select  # noqa: E402

OUT = HERE.parent / "results" / "bench"
ROUGE = rouge_scorer.RougeScorer(["rouge1"], use_stemmer=True)
THRESHOLDS = (0.8, 0.5)
_FIELD = re.compile(r"\{\s*(\w+)\s*[\(\{]")


def _graphql_field(document: str) -> str:
    """The first field a GraphQL document selects: the operation it performs."""
    match = _FIELD.search(document or "")
    return match.group(1) if match else ""


def _charter_operations() -> dict[str, str]:
    """Each Charter tool name the arm publishes, as ``pack:operation``."""
    out: dict[str, str] = {}
    for pack in ("slack", "linear"):
        for name, tool in qualified_names(pack_tools(pack)).items():
            body = tool.static_body or {}
            operation = _graphql_field(str(body.get("query", ""))) or tool.url_template
            out[name] = f"{pack}:{operation}"
    return out


def _operation(function: str, arguments: dict[str, Any], charter_ops: dict[str, str]) -> str:
    if function in charter_ops:
        return charter_ops[function]
    if function.endswith("_graphql"):
        return (
            f"{function.removesuffix('_graphql')}:{_graphql_field(str(arguments.get('query', '')))}"
        )
    if function.endswith("_api"):
        return f"{function.removesuffix('_api')}:{str(arguments.get('path', '')).strip('/')}"
    return function


def _calls(sample: Any) -> list[tuple[str, str]]:
    """Every tool call of the run as ``(function, arguments as JSON)``, in order, without ``submit``."""
    out = []
    for message in sample.messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.function == "submit":
                continue
            out.append((call.function, call.arguments or {}))
    return out


# Writes, by operation. Anything else the agents called reads.
_SLACK_WRITES = {
    "chat.update": "ts",
    "reactions.add": "timestamp",
    "chat.postMessage": None,
    "chat.delete": "ts",
    "reactions.remove": "timestamp",
}
_LINEAR_WRITE = re.compile(r"(Create|Update|Delete|Archive|Unarchive)$")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _succeeded(arm: str, result: Any) -> bool:
    """Whether a tool result is a success. The Charter arm raises on a failure inside
    a 200; the raw arm hands the body back, so its failures are read off the body."""
    if getattr(result, "error", None) is not None:
        return False
    text = str(result.content)
    if arm == "charter":
        return True
    return '"ok":true' in text.replace(" ", "") or (
        '"data"' in text
        and '"errors"' not in text
        and '"success":false' not in text.replace(" ", "")
    )


def _writes(sample: Any, arm: str, charter_ops: dict[str, str]) -> list[tuple[str, str]]:
    """Every write that succeeded, as ``(operation, the id it changed)``."""
    results = {m.tool_call_id: m for m in sample.messages if getattr(m, "role", "") == "tool"}
    out = []
    for message in sample.messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.function == "submit":
                continue
            args = call.arguments or {}
            op = _operation(call.function, args, charter_ops)
            pack, _, name = op.partition(":")
            if pack == "slack" and name in _SLACK_WRITES:
                key = _SLACK_WRITES[name]
                flat = {**args, **(args.get("body") or {}), **(args.get("query") or {})}
                target = str(flat.get(key, "")) if key else "(new message)"
            elif pack == "linear" and _LINEAR_WRITE.search(name):
                found = _UUID.findall(json.dumps(args))
                target = found[0] if found else "(new)"
            else:
                continue
            result = results.get(call.id)
            if result is not None and _succeeded(arm, result):
                out.append((op, target))
    return out


def _submitted(sample: Any) -> str:
    for message in reversed(sample.messages):
        for call in getattr(message, "tool_calls", None) or []:
            if call.function == "submit":
                return str((call.arguments or {}).get("answer", ""))
    return sample.output.completion if sample.output else ""


def grade(log_dir: Path) -> list[dict[str, Any]]:
    scenarios = {s.id: s for s in select("traps", available=None, variants=True)}
    charter_ops = _charter_operations()
    rows: list[dict[str, Any]] = []
    for path in sorted(log_dir.glob("*.eval")):
        log = read_eval_log(str(path))
        arm = (log.eval.metadata or {}).get("arm") or (log.eval.task_args or {}).get("arm")
        for sample in log.samples or []:
            score = next(iter((sample.scores or {}).values()), None)
            if score is None or (score.metadata or {}).get("harness_error"):
                continue  # the harness failed, not the agent: not a run to grade
            scenario = scenarios[str(sample.metadata["scenario"])]
            expected = score.metadata["expected"]
            wanted = scenario.expected_operation
            identifying = [str(v) for v in scenario.expected_call(expected).values()]
            calls = _calls(sample)
            matches = [
                _operation(f, a, charter_ops) == wanted
                and all(v in json.dumps(a) for v in identifying)
                for f, a in calls
            ]
            answer = _submitted(sample)
            written = ROUGE.score(scenario.reference_response, answer)["rouge1"].fmeasure
            target = str(expected.get("ts") or expected.get("issue_id"))
            writes = _writes(sample, str(arm), charter_ops)
            collateral = [w for w in writes if w[1] != target]
            rows.append(
                {
                    "arm": arm,
                    "model": log.eval.model,
                    "scenario": sample.metadata["scenario"],
                    "template": scenario.template,
                    "trap": bool(expected.get("stale")),
                    "epoch": sample.epoch,
                    "account_passed": score.value == "C",
                    "trajectory_in_order": any(matches),
                    "trajectory_exact": matches == [True],
                    "rouge1_written": round(written, 3),
                    "calls": len(calls),
                    "collateral_writes": [list(w) for w in collateral],
                    "answer": answer,
                }
            )
    _score_against_recorded(rows)
    return rows


def _score_against_recorded(rows: list[dict[str, Any]]) -> None:
    """ROUGE-1 of each run against its arm's recorded reference for the same task.

    The reference run is the lowest-epoch control the account shows done. It is
    the golden session, so it is not graded itself.
    """
    golden: dict[tuple[str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: r["epoch"]):
        key = (row["arm"], row["template"])
        if not row["trap"] and row["account_passed"] and key not in golden:
            golden[key] = row
    for row in rows:
        reference = golden.get((row["arm"], row["template"]))
        row["reference_run"] = row is reference
        row["rouge1"] = (
            round(ROUGE.score(reference["answer"], row["answer"])["rouge1"].fmeasure, 3)
            if reference is not None
            else None
        )


def _eval_passed(row: dict[str, Any], match: str, threshold: float | None) -> bool:
    """ADK's verdict: the trajectory criterion, and the response criterion unless
    ``threshold`` is None (an eval that grades the steps alone)."""
    if not row[f"trajectory_{match}"]:
        return False
    if threshold is None:
        return True
    return row["rouge1"] is not None and row["rouge1"] >= threshold


def table(rows: list[dict[str, Any]], said_done: dict[tuple[str, str, int], str]) -> str:
    """The trap runs per arm: what the agent said, what it changed, and what each eval
    concluded. ``said_done`` holds the hand-read labels (``results/bench/said_done.json``)."""
    for r in rows:
        assert not (r["trap"] and r["account_passed"]), "a trap run passed at the account"
    arms = sorted({r["arm"] for r in rows})
    graded = [r for r in rows if not r["reference_run"]]
    traps = {arm: [r for r in graded if r["arm"] == arm and r["trap"]] for arm in arms}
    done = {
        arm: [r for r in graded if r["arm"] == arm and not r["trap"] and r["account_passed"]]
        for arm in arms
    }
    lines = ["| | " + " | ".join(arms) + " |", "|---|" + "---:|" * len(arms)]

    def row(label: str, cells: list[str]) -> None:
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    row("trap runs (the task cannot be done)", [str(len(traps[a])) for a in arms])
    if said_done:
        row(
            "the agent's final answer said it was done (read by hand)",
            [
                str(
                    sum(
                        said_done.get((r["arm"], r["scenario"], r["epoch"])) == "said done"
                        for r in traps[a]
                    )
                )
                for a in arms
            ],
        )
    row(
        "it changed something the task did not name",
        [str(sum(bool(r["collateral_writes"]) for r in traps[a])) for a in arms],
    )
    for label, match, threshold in EVALS:
        row(
            f"an eval of {label} passed it",
            [str(sum(_eval_passed(r, match, threshold) for r in traps[a])) for a in arms],
        )
    for label, match, threshold in EVALS[1:3]:
        row(
            f"...the same eval failed a run that did the task ({label})",
            [
                f"{sum(not _eval_passed(r, match, threshold) for r in done[a])} of {len(done[a])}"
                for a in arms
            ],
        )
    return "\n".join(lines) + "\n"


EVALS = (
    ("the steps alone (IN_ORDER trajectory)", "in_order", None),
    ("steps and answer, ROUGE-1 ≥ 0.8", "in_order", 0.8),
    ("steps and answer, ROUGE-1 ≥ 0.5", "in_order", 0.5),
    ("steps (EXACT) and answer, ROUGE-1 ≥ 0.8", "exact", 0.8),
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir", type=Path)
    ap.add_argument(
        "--name",
        default="",
        help="a suffix for the output files, e.g. opus: false_passes_opus.json, said_done_opus.json",
    )
    args = ap.parse_args()
    suffix = f"_{args.name}" if args.name else ""
    rows = grade(args.log_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    # The accounts' own people appear in answers and call results; the records keep no address.
    redacted = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", json.dumps(rows, indent=1))
    (OUT / f"false_passes{suffix}.json").write_text(redacted)
    labels_path = OUT / f"said_done{suffix}.json"
    said_done = {}
    if labels_path.exists():
        said_done = {
            (r["arm"], r["scenario"], r["epoch"]): r["label"]
            for r in json.loads(labels_path.read_text())["runs"]
        }
    text = table(rows, said_done)
    (OUT / f"false_passes{suffix}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
