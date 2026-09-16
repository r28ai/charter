"""
Inspect logs -> the numbers, per (model, arm), and per scenario.

Headline: task success rate over every scenario-epoch, with a binomial standard
error. Secondary, all means per run: tool calls, tool errors, guard rejections,
raw-arm truncations, bytes of tool output fed to the model, model tokens, wall
time. Everything is read from the logs a campaign wrote; nothing is typed in.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from inspect_ai.log import EvalLog, list_eval_logs, read_eval_log

from charter_harness.arms.raw_arm import RAW_RESPONSE_CAP

__all__ = ["Run", "Cell", "collect", "reportable_logs", "summarise", "write_report"]

# A log is evidence only once it has been finalised. A killed try leaves a
# "started" log behind whose scored samples are real but whose scenarios the
# retry runs again, so counting it would double-count every sample that the
# retry also covered. `_batch_complete.py` asks this module which logs count
# rather than keeping its own copy of the rule: the two answering differently
# is what let a batch be marked done on samples the report then discarded.
REPORTED_STATUSES = ("success", "error")


@dataclass
class Run:
    model: str
    arm: str
    scenario: str
    template: str
    epoch: int
    correct: bool | None  # None when the run produced no score at all
    explanation: str
    tool_calls: int = 0
    tool_errors: int = 0
    guard_rejections: int = 0
    truncations: int = 0
    context_bytes: int = 0
    payload_bytes: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    wall_seconds: float = 0.0
    error: str | None = None
    limit: str | None = None
    # "seed" / "observe" when the harness, not the agent, failed. Such a run is
    # reported but is not a data point about the model.
    harness_error: str | None = None


@dataclass
class Cell:
    model: str
    arm: str
    n: int = 0
    successes: int = 0
    runs: list[Run] = field(default_factory=list)
    harness_errors: list[Run] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.successes / self.n if self.n else 0.0

    @property
    def stderr(self) -> float:
        if not self.n:
            return 0.0
        p = self.rate
        return math.sqrt(p * (1 - p) / self.n)

    def mean(self, attr: str) -> float:
        return sum(getattr(r, attr) for r in self.runs) / len(self.runs) if self.runs else 0.0

    def total(self, attr: str) -> float:
        return sum(getattr(r, attr) for r in self.runs)

    def summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "arm": self.arm,
            "runs": self.n,
            "successes": self.successes,
            "success_rate": round(self.rate, 4),
            "stderr": round(self.stderr, 4),
            "mean_tool_calls": round(self.mean("tool_calls"), 2),
            "mean_tool_errors": round(self.mean("tool_errors"), 2),
            "guard_rejections": int(self.total("guard_rejections")),
            "truncations": int(self.total("truncations")),
            "mean_context_bytes": round(self.mean("context_bytes")),
            "mean_payload_bytes": round(self.mean("payload_bytes")),
            "mean_total_tokens": round(self.mean("total_tokens")),
            "mean_wall_seconds": round(self.mean("wall_seconds"), 1),
            "errors": sum(1 for r in self.runs if r.error),
            "limits": sum(1 for r in self.runs if r.limit),
            "harness_errors": len(self.harness_errors),
        }


# An inference-provider failure is not a data point about either arm. The model
# was never served, so the run says nothing about whether a declared boundary
# helps; scoring it INCORRECT records the provider's outage as the agent's
# mistake. On 2026-09-15 a Fireworks billing suspension did exactly that to two
# raw-arm samples, and both landed on doc_to_gmail_draft - the one scenario the
# published gap rests on - in the direction that flatters the thesis.
#
# The codes are deliberately narrow, because this is a lever for discarding
# inconvenient runs and a wide one would be unfalsifiable. Only account and
# infrastructure states qualify: auth, billing, precondition, and the provider's
# own 5xx. 429 is excluded - a rate limit is a consequence of the concurrency the
# harness chose, so it is the harness's problem to retry, not evidence to drop.
# 400/404/422 are excluded because a malformed request is about the arm that
# built it. Every match is listed individually in the report, never silently.
_OUTAGE_CODES = (401, 402, 403, 412, 500, 502, 503, 504)
_OUTAGE_RE = re.compile(r"^Error code: (\d{3})\b")


def provider_outage(message: str | None) -> str | None:
    """The provider-outage label for a sample error, or None if it is a real result.

    Matches the shape the OpenAI-compatible clients raise ("Error code: 412 -
    ..."), which is what reaches a sample when a generate call fails. A tool
    talking to a target API does not surface this way: the arms hand a non-2xx
    back to the model as tool output.
    """
    if not message:
        return None
    match = _OUTAGE_RE.match(message.strip())
    if match is None or int(match.group(1)) not in _OUTAGE_CODES:
        return None
    return f"provider {match.group(1)}"


def _short_model(model: str) -> str:
    return model.rsplit("/", 1)[-1]


def _runs_from_log(log: EvalLog) -> list[Run]:
    arm = str((log.eval.metadata or {}).get("arm") or log.eval.task.replace("harness-", ""))
    model = _short_model(log.eval.model)
    runs: list[Run] = []
    for sample in log.samples or []:
        score = (sample.scores or {}).get("state_scorer")
        meta = dict(score.metadata or {}) if score else {}
        usage = sample.model_usage or {}
        input_tokens = sum(u.input_tokens for u in usage.values())
        output_tokens = sum(u.output_tokens for u in usage.values())
        total_tokens = sum(u.total_tokens for u in usage.values())
        runs.append(
            Run(
                model=model,
                arm=arm,
                scenario=str(sample.id),
                template=str((sample.metadata or {}).get("template") or str(sample.id).split("@")[0]),
                epoch=sample.epoch,
                correct=None if score is None else (str(score.value) == "C"),
                explanation=(score.explanation or "") if score else "",
                tool_calls=int(meta.get("tool_calls") or 0),
                tool_errors=int(meta.get("tool_errors") or 0),
                guard_rejections=int(meta.get("guard_rejections") or 0),
                truncations=int(meta.get("truncations") or 0),
                context_bytes=int(meta.get("context_bytes") or 0),
                payload_bytes=int(meta.get("payload_bytes") or 0),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                wall_seconds=float(sample.total_time or 0.0),
                error=(sample.error.message if sample.error else None),
                limit=(sample.limit.type if sample.limit else None),
                harness_error=(str(meta["harness_error"]) if meta.get("harness_error") else None),
            )
        )
        outage = provider_outage(runs[-1].error)
        if outage and not runs[-1].harness_error:
            runs[-1].harness_error = outage
            runs[-1].explanation = f"harness error: {outage}: {runs[-1].error}"
    return runs


def reportable_logs(directory: Path | str) -> list[EvalLog]:
    """The finalised logs in a directory, oldest attempt first.

    Ordering is by the eval's own creation time, so a caller folding these in
    order ends on the most recent attempt at any sample.
    """
    logs: list[tuple[str, str, EvalLog]] = []
    for info in list_eval_logs(str(directory)):
        log = read_eval_log(info.name)
        if log.status not in REPORTED_STATUSES:
            continue
        logs.append((str(log.eval.created or ""), str(info.name), log))
    return [log for _, _, log in sorted(logs, key=lambda t: (t[0], t[1]))]


def collect(directory: Path) -> list[Run]:
    """Every scenario-epoch in a directory, counted once.

    A batch that was killed and retried has two finalised logs covering the same
    scenarios. Keyed by (model, arm, scenario, epoch) with the later attempt
    overwriting the earlier, a retry replaces its predecessor instead of being
    added to it. The last attempt wins even when it went worse: it is what
    happened, and a rule that kept the better one would be choosing its data.
    """
    latest: dict[tuple[str, str, str, int], Run] = {}
    for log in reportable_logs(directory):
        for run in _runs_from_log(log):
            latest[(run.model, run.arm, run.scenario, run.epoch)] = run
    return list(latest.values())


Breakdown = dict[str, dict[tuple[str, str], tuple[int, int]]]


def summarise(runs: list[Run]) -> tuple[dict[tuple[str, str], Cell], Breakdown]:
    cells: dict[tuple[str, str], Cell] = {}
    per_scenario: Breakdown = defaultdict(dict)
    for run in runs:
        key = (run.model, run.arm)
        cell = cells.setdefault(key, Cell(model=run.model, arm=run.arm))
        if run.harness_error:
            cell.harness_errors.append(run)
            continue
        cell.n += 1
        cell.successes += 1 if run.correct else 0
        cell.runs.append(run)
        k, n = per_scenario[run.scenario].get(key, (0, 0))
        per_scenario[run.scenario][key] = (k + (1 if run.correct else 0), n + 1)
    return cells, per_scenario


def per_template(runs: list[Run]) -> Breakdown:
    """Variants rolled up under their template — the phase-3 view."""
    out: Breakdown = defaultdict(dict)
    for run in runs:
        if run.harness_error:
            continue
        key = (run.model, run.arm)
        k, n = out[run.template].get(key, (0, 0))
        out[run.template][key] = (k + (1 if run.correct else 0), n + 1)
    return out


def _breakdown_table(title: str, breakdown: Breakdown, keys: list[tuple[str, str]]) -> list[str]:
    lines = [f"## {title}", ""]
    lines.append("| scenario | " + " | ".join(f"{m} · {a}" for m, a in keys) + " |")
    lines.append("|---|" + "---:|" * len(keys))
    for name in sorted(breakdown):
        row = [name]
        for key in keys:
            k, n = breakdown[name].get(key, (0, 0))
            row.append(f"{k}/{n}" if n else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return lines


def _markdown(cells: dict[tuple[str, str], Cell], per_scenario: Breakdown, directory: Path, templates: Breakdown | None = None) -> str:
    keys = sorted(cells)
    lines = [f"# Campaign `{directory.name}`", ""]
    lines.append("## Headline — task success by (model, arm)")
    lines.append("")
    lines.append("| model | arm | runs | success | rate | ± stderr | tool calls/run | tool errors/run | guard rejections | truncations | context bytes/run | tokens/run | wall s/run | errors | limits | harness errors |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key in keys:
        s = cells[key].summary()
        lines.append(
            f"| {s['model']} | {s['arm']} | {s['runs']} | {s['successes']} | {s['success_rate']:.0%} | {s['stderr']:.3f} | "
            f"{s['mean_tool_calls']} | {s['mean_tool_errors']} | {s['guard_rejections']} | {s['truncations']} | "
            f"{s['mean_context_bytes']:,} | {s['mean_total_tokens']:,} | {s['mean_wall_seconds']} | {s['errors']} | {s['limits']} | {s['harness_errors']} |"
        )
    lines.append("")
    if templates:
        lines.extend(_breakdown_table("Per template — successes / runs, variants rolled up", templates, keys))
    lines.extend(_breakdown_table("Per scenario — successes / runs", per_scenario, keys))
    lines.append("## Failures, with the judge's reason")
    lines.append("")
    any_failure = False
    for key in keys:
        for run in cells[key].runs:
            if run.correct:
                continue
            any_failure = True
            reason = run.explanation or run.error or run.limit or "no score"
            lines.append(f"- **{run.scenario}** · {run.model} · {run.arm} · epoch {run.epoch}: {reason}")
    if not any_failure:
        lines.append("_none_")
    lines.append("")
    harness_errors = [run for key in keys for run in cells[key].harness_errors]
    if harness_errors:
        lines.append("## Harness errors — excluded from the rates above")
        lines.append("")
        for run in harness_errors:
            lines.append(f"- **{run.scenario}** · {run.model} · {run.arm} · epoch {run.epoch}: {run.explanation}")
        lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "- A run is one scenario-epoch. Success means the scenario's judge accepted the state read back from the "
        "real accounts after the agent finished; the transcript is never consulted for the verdict."
    )
    lines.append(
        "- A harness error is a run the agent never had a fair shot at: its seed or read-back failed, or the "
        "inference provider refused to serve the model (auth, billing, precondition, or the provider's own 5xx). "
        "Such a run is listed individually above and not counted for or against any model. A rate limit is not "
        "one of these - that is the harness's concurrency to retry - and neither is a 4xx from a target API, "
        "which is a result about the arm that built the request."
    )
    lines.append("- stderr is the binomial standard error of the success rate over runs.")
    lines.append(
        "- Context bytes are the bytes of tool output handed back to the model, summed over a run. On the Charter arm "
        "this is after the packs' response trimming; on the raw arm it is the API's response body, capped at "
        f"{RAW_RESPONSE_CAP:,} bytes per call (truncations are counted)."
    )
    lines.append("- Tool errors on the Charter arm include calls rejected by schema validation before any request was sent.")
    lines.append("- Same model settings, system prompt, task text, credentials, endpoint set (guard-enforced) and limits on every arm; only the tool surface differs.")
    lines.append("")
    return "\n".join(lines)


def write_report(directory: Path) -> list[Path]:
    directory = Path(directory)
    runs = collect(directory)
    cells, per_scenario = summarise(runs)
    has_variants = any(r.scenario != r.template for r in runs)
    templates = per_template(runs) if has_variants else None
    md_path = directory / "summary.md"
    json_path = directory / "summary.json"
    md_path.write_text(_markdown(cells, per_scenario, directory, templates), encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "campaign": directory.name,
                "cells": [cells[k].summary() for k in sorted(cells)],
                "per_scenario": {
                    scenario: {f"{m}|{a}": {"successes": k, "runs": n} for (m, a), (k, n) in v.items()}
                    for scenario, v in per_scenario.items()
                },
                "per_template": {
                    template: {f"{m}|{a}": {"successes": k, "runs": n} for (m, a), (k, n) in v.items()}
                    for template, v in (templates or {}).items()
                },
                "runs": [asdict(r) for r in runs],
                "raw_response_cap_bytes": RAW_RESPONSE_CAP,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return [md_path, json_path]
