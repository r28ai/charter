"""The evidence page, against the two campaign summaries it is built from.

`docs/guarantees/measured-results.mdx` is the page a reader is most likely to
check and least able to reproduce: it reports 534 runs against live accounts,
and nobody can re-run those. What they can do is open the summaries and add up
the rows, so those two files are tracked (see `.gitignore`) and every figure on
the page is recomputed from them here.

That this test did not exist is why the page drifted. The numbers were correct —
`stage2-final` and `stage3-final-all`, chosen deliberately — but the citation
beside them named `FINAL-breadth` and `FINAL-depth`, which are assembly paths in
`harness/scripts/overnight.sh` for a rerun that never produced a reported
campaign. One of those directories does not exist. The figures and the provenance
had drifted apart with nothing to notice, and reconstructing which cut was
canonical from directory names cost more than the page is worth, twice.

So: the campaign names are asserted, not just the numbers. A future rerun that
replaces these campaigns has to change this file, which is the point — the cut
the page reports becomes a decision recorded in the suite rather than a directory
somebody picked from an `ls`.

Not checked here: the failed-calls-by-cause table. That is a hand classification
of error strings and the summaries carry no category field, so there is nothing
to recompute it from. It is the one table on the page taken on trust.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path as FsPath

import pytest

ROOT = FsPath(__file__).resolve().parent.parent
PAGE = (ROOT / "docs/guarantees/measured-results.mdx").read_text()

# The two cuts the page reports. Named here so that changing which campaign is
# canonical is a deliberate edit rather than a silent one.
BREADTH = "stage2-final"
DEPTH = "stage3-final-all"


def _cell(campaign: str, arm: str) -> dict:
    """One (campaign, arm) cell, counted the way the page counts it.

    Harness errors are excluded — a run whose seed or provider failed is one the
    agent never had a fair shot at, and the summaries mark them. That exclusion
    is what makes 320 recorded depth runs 314 counted ones.
    """
    path = ROOT / "harness/results" / campaign / "summary.json"
    runs = [
        r
        for r in json.loads(path.read_text())["runs"]
        if r["arm"] == arm and not r["harness_error"]
    ]
    n = len(runs)

    def mean(key: str) -> float:
        return sum(r[key] for r in runs) / n

    return {
        "n": n,
        "ok": sum(r["correct"] for r in runs),
        "tool_calls": mean("tool_calls"),
        "tool_errors": mean("tool_errors"),
        "guard": sum(r["guard_rejections"] for r in runs),
        "truncations": sum(r["truncations"] for r in runs),
        "context": mean("context_bytes"),
        "payload": mean("payload_bytes"),
        "tokens": mean("total_tokens"),
        "wall": mean("wall_seconds"),
    }


def _near(value: float) -> set:
    """The page floors some averages and rounds others; both spellings pass."""
    return {f"{math.floor(value):,}", f"{round(value):,}"}


CELLS = {
    ("breadth", "progressive"): (BREADTH, "progressive"),
    ("breadth", "raw"): (BREADTH, "raw"),
    ("depth", "progressive"): (DEPTH, "progressive"),
    ("depth", "raw"): (DEPTH, "raw"),
}


def test_the_page_names_the_campaigns_it_reports():
    """The defect this file exists for: figures from one cut, citation to another."""
    assert f"harness/results/{BREADTH}/summary.json" in PAGE
    assert f"harness/results/{DEPTH}/summary.json" in PAGE
    for stale in ("FINAL-breadth", "FINAL-depth"):
        assert stale not in PAGE, (
            f"the page cites {stale}, which is an assembly path in overnight.sh "
            f"rather than a reported campaign"
        )


def test_the_cited_summaries_are_tracked():
    """Cited evidence nobody can open is not evidence."""
    for campaign in (BREADTH, DEPTH):
        for name in ("summary.json", "summary.md"):
            path = ROOT / "harness/results" / campaign / name
            assert path.exists(), f"{path.relative_to(ROOT)} is cited by the page and missing"


@pytest.mark.parametrize("campaign,arm", sorted(CELLS), ids=lambda v: str(v))
def test_the_success_table_row_matches_its_campaign(campaign, arm):
    c = _cell(*CELLS[(campaign, arm)])
    assert f"| {c['n']} | {c['ok']} | {100 * c['ok'] / c['n']:.1f}% |" in PAGE, (
        f"{campaign}/{arm} is {c['ok']}/{c['n']} ({100 * c['ok'] / c['n']:.1f}%) in the summary"
    )


def test_the_combined_row_and_the_run_total():
    tot = {
        arm: (
            sum(_cell(c, arm)["n"] for c in (BREADTH, DEPTH)),
            sum(_cell(c, arm)["ok"] for c in (BREADTH, DEPTH)),
        )
        for arm in ("progressive", "raw")
    }
    for arm, (n, ok) in tot.items():
        assert f"**{n}** | **{ok}** | **{100 * ok / n:.1f}%**" in PAGE, (
            f"the combined {arm} row is {ok}/{n} ({100 * ok / n:.1f}%)"
        )

    counted = sum(n for n, _ in tot.values())
    # Every run-count claim on the page, not just the first: the total appears in
    # the description, in the prose, and in the pages that link here, and a
    # half-applied correction is worse than none.
    stated = set(re.findall(r"\b(\d{3}) runs\b", PAGE))
    assert stated == {str(counted)}, (
        f"the page states run totals {sorted(stated)}; the summaries count {counted}"
    )


def test_the_z_test_is_the_one_these_numbers_produce():
    """The page's headline is that success is a wash. That has to keep being true."""
    (n1, o1), (n2, o2) = (
        (
            sum(_cell(c, arm)["n"] for c in (BREADTH, DEPTH)),
            sum(_cell(c, arm)["ok"] for c in (BREADTH, DEPTH)),
        )
        for arm in ("progressive", "raw")
    )
    pooled = (o1 + o2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (o1 / n1 - o2 / n2) / se
    p = math.erfc(abs(z) / math.sqrt(2))

    assert f"z = {z:.2f}" in PAGE, f"the z statistic is now {z:.2f}"
    assert f"p = {p:.2f}" in PAGE, f"the p value is now {p:.2f}"
    assert p > 0.05, (
        f"success is no longer a wash (p = {p:.3f}); the page argues at length that "
        f"it is, and that argument has to be rewritten rather than the number swapped"
    )


def _table(header: str) -> str:
    """The rows under one table header.

    Anchored rather than searched page-wide: the raw arm's rows begin with an
    empty campaign cell, so `| | raw | 110 | 105 |` from the success table
    matches a payload-row pattern perfectly and the assertion passes against the
    wrong numbers. That happened while writing this.
    """
    at = PAGE.index(header)
    return PAGE[at : PAGE.index("\n\n", at)]


PAYLOAD_TABLE = _table("| campaign | arm | payload bytes | context bytes |")
TOKEN_TABLE = _table("| campaign | Charter | raw | |")


def _rows(table: str) -> list:
    """Table rows as cell lists, with the campaign carried down.

    The raw arm's row leaves the campaign cell empty — `| | raw | 39,738 | ...`
    — so it is inherited from the Charter row above it, exactly as a reader
    reads it.
    """
    out, carried = [], ""
    for line in table.splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or not any(cells):
            continue
        carried = cells[0] or carried
        out.append([carried] + cells[1:])
    return out


@pytest.mark.parametrize("campaign,arm", sorted(CELLS), ids=lambda v: str(v))
def test_the_payload_and_context_row_matches(campaign, arm):
    c = _cell(*CELLS[(campaign, arm)])
    label = "Charter" if arm == "progressive" else "raw"
    match = [r for r in _rows(PAYLOAD_TABLE) if r[0] == campaign and r[1] == label]
    assert match, f"no payload/context row for {campaign}/{arm}"
    payload, context = (int(g.replace(",", "")) for g in match[0][2:4])
    assert abs(payload - c["payload"]) <= 1, (
        f"{campaign}/{arm} payload bytes are {c['payload']:,.0f}, the page says {payload:,}"
    )
    assert abs(context - c["context"]) <= 1, (
        f"{campaign}/{arm} context bytes are {c['context']:,.0f}, the page says {context:,}"
    )


@pytest.mark.parametrize("campaign", ["breadth", "depth"])
def test_the_tokens_row_matches(campaign):
    ch = _cell(*CELLS[(campaign, "progressive")])
    raw = _cell(*CELLS[(campaign, "raw")])
    row = re.search(rf"\| {campaign} \| ([\d,]+) \| ([\d,]+) \|", TOKEN_TABLE)
    assert row, f"no tokens row for {campaign}"
    got_ch, got_raw = (int(g.replace(",", "")) for g in row.groups())
    assert abs(got_ch - ch["tokens"]) <= 1, (
        f"{campaign} Charter tokens/run are {ch['tokens']:,.0f}, the page says {got_ch:,}"
    )
    assert abs(got_raw - raw["tokens"]) <= 1, (
        f"{campaign} raw tokens/run are {raw['tokens']:,.0f}, the page says {got_raw:,}"
    )


def test_the_rest_of_the_record_matches():
    rows = {
        "breadth": (_cell(BREADTH, "progressive"), _cell(BREADTH, "raw")),
        "depth": (_cell(DEPTH, "progressive"), _cell(DEPTH, "raw")),
    }
    for campaign, (ch, raw) in rows.items():
        assert f"{ch['tool_errors']:.2f} vs {raw['tool_errors']:.2f}" in PAGE, (
            f"{campaign} tool errors/run are {ch['tool_errors']:.2f} vs {raw['tool_errors']:.2f}"
        )
        assert f"{ch['guard']} vs {raw['guard']}" in PAGE, (
            f"{campaign} guard rejections are {ch['guard']} vs {raw['guard']}"
        )
        assert f"{ch['truncations']} vs {raw['truncations']}" in PAGE, (
            f"{campaign} truncations are {ch['truncations']} vs {raw['truncations']}"
        )
        assert f"{ch['wall']:.1f} vs {raw['wall']:.1f}" in PAGE, (
            f"{campaign} wall seconds/run are {ch['wall']:.1f} vs {raw['wall']:.1f}"
        )


def test_the_scenarios_the_page_singles_out_are_the_ones_that_move():
    """Including `github_to_linear`, which goes against Charter.

    The page names it as the first thing to investigate before this page is
    cited. A rerun where it comes out even is a different campaign and a
    different page, not a quiet edit to this one.
    """
    moved = {}
    for label, campaign in (("breadth", BREADTH), ("depth", DEPTH)):
        runs = json.loads((ROOT / "harness/results" / campaign / "summary.json").read_text())[
            "runs"
        ]
        tally = {}
        for r in runs:
            if r["harness_error"]:
                continue
            t = tally.setdefault((r["template"], r["arm"]), [0, 0])
            t[1] += 1
            t[0] += r["correct"]
        for template in {k[0] for k in tally}:
            ch = tally.get((template, "progressive"), [0, 0])
            raw = tally.get((template, "raw"), [0, 0])
            if ch[0] / max(ch[1], 1) != raw[0] / max(raw[1], 1):
                moved.setdefault(template, {})[label] = (ch, raw)

    for template, per in moved.items():
        assert f"`{template}`" in PAGE, (
            f"{template} differs between the arms and the page does not name it: {per}"
        )
        for ch, raw in per.values():
            assert f"Charter {ch[0]}/{ch[1]}, raw {raw[0]}/{raw[1]}" in PAGE, (
                f"{template} is Charter {ch[0]}/{ch[1]}, raw {raw[0]}/{raw[1]}"
            )


# --- other pages that quote the same campaigns --------------------------------
#
# The evidence page is not the only one reporting these runs, and the other one
# had drifted further than it did. /optimization/latency printed
# "breadth 71.2s vs 64.6s, Charter 10% slower" against a measured 46.3 vs 96.4,
# and built an argument on the reversal — "the same two arms went in opposite
# directions" — that the reported campaigns do not show. Two pages in one docs
# set drew opposite conclusions from the same two cuts.
#
# Any page that quotes a campaign figure is checked against the summaries, not
# just the page that owns them.

LATENCY = (ROOT / "docs/optimization/latency.mdx").read_text()


@pytest.mark.parametrize("campaign", ["breadth", "depth"])
def test_the_latency_page_quotes_the_wall_times_these_campaigns_produced(campaign):
    ch = _cell(*CELLS[(campaign, "progressive")])
    raw = _cell(*CELLS[(campaign, "raw")])
    row = re.search(rf"{campaign}\s+([\d.]+)s\s+([\d.]+)s", LATENCY)
    assert row, f"the latency page no longer prints a wall-time row for {campaign}"
    got_ch, got_raw = (float(g) for g in row.groups())
    assert abs(got_ch - ch["wall"]) < 0.05, (
        f"{campaign} Charter wall is {ch['wall']:.1f}s, the page says {got_ch}s"
    )
    assert abs(got_raw - raw["wall"]) < 0.05, (
        f"{campaign} raw wall is {raw['wall']:.1f}s, the page says {got_raw}s"
    )
    ratio = raw["wall"] / ch["wall"]
    assert f"Charter {ratio:.1f}x faster" in LATENCY, (
        f"{campaign} is {ratio:.2f}x, and the page states a different multiple"
    )


def test_the_latency_page_does_not_contradict_the_evidence_page():
    """Both report wall time. Neither may say Charter is the slower arm."""
    for campaign in ("breadth", "depth"):
        ch = _cell(*CELLS[(campaign, "progressive")])
        raw = _cell(*CELLS[(campaign, "raw")])
        assert ch["wall"] < raw["wall"], (
            f"Charter is now the slower arm in {campaign} ({ch['wall']:.1f}s against "
            f"{raw['wall']:.1f}s). Both pages assert the opposite in prose, and the "
            f"argument has to be rewritten rather than the numbers swapped"
        )
    assert "slower" not in LATENCY.split("## The number not to chase")[1].split("## Related")[0]


@pytest.mark.parametrize("campaign", ["breadth", "depth"])
def test_the_latency_page_quotes_the_supporting_figures_too(campaign):
    """The call counts and context bytes its explanation rests on."""
    ch = _cell(*CELLS[(campaign, "progressive")])
    raw = _cell(*CELLS[(campaign, "raw")])
    # Prose wraps, so the pair is matched with whitespace collapsed.
    flat = " ".join(LATENCY.split())
    assert f"{ch['tool_calls']:.2f} against {raw['tool_calls']:.2f}" in flat, (
        f"{campaign} tool calls/run are {ch['tool_calls']:.2f} against {raw['tool_calls']:.2f}"
    )
    for value in (ch["context"], raw["context"], ch["tokens"], raw["tokens"]):
        assert f"{round(value):,}" in LATENCY, (
            f"{campaign} quotes a figure the summaries no longer produce: {value:,.0f}"
        )
