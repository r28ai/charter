"""Every schema size the prose quotes, against the package that produces it.

The docs are full of numbers a reader can check in one line — `search_issues` is
7,748 tokens, three Linear list tools are 541,407 bytes through the OpenAI
adapter, the shipped packs come to 458,000 tokens of schema. Each is the whole
argument of the page it sits on, and each was written by running exactly the code
it appears beside.

Nothing was rechecking them. A change to what `to_json_schema` emits moved all of
them at once — dropping Pydantic's auto-generated titles took 10% off every
figure in this file — and the pages went on stating the old ones, which is the
failure mode that makes a reader stop trusting the numbers that *are* right.

So each figure is recomputed here and matched against the page. A test fails when
the runtime changes what it emits, and the fix is to rerun the snippet and paste
the new number, which is the work the page is claiming was done.

Tolerances are per-figure and stated: exact where the prose is exact, and loose
where the prose says "roughly". Nothing here is a performance budget — a number
moving is not a regression, it is a page to update.
"""

from __future__ import annotations

import json
import re
from pathlib import Path as FsPath

import pytest

from charter import ToolSession, json_tokens, schema_tokens
from charter.adapters.openai import to_openai_tools
from charter.execution.schema import llm_json_schema

ROOT = FsPath(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
README = ROOT / "README.md"


def _text(page: str) -> str:
    return (README if page == "README.md" else DOCS / page).read_text()


def _assert_quoted(page: str, template: str, value: int, *, tolerance: float = 0.0):
    """The page states `template` with `value` in it, give or take `tolerance`."""
    body = _text(page)
    exact = template.format(f"{value:,}")
    if exact in body:
        return
    if tolerance:
        # Find whatever number the page does state in this slot and compare.
        pattern = re.escape(template).replace(re.escape("{}"), r"([\d,]+)")
        found = re.search(pattern, body)
        if found:
            stated = int(found.group(1).replace(",", ""))
            if abs(stated - value) / value <= tolerance:
                return
            pytest.fail(f"{page} states {stated:,} where the package now produces {value:,}")
    pytest.fail(f"{page} does not state {value:,}: expected {exact!r}")


# --- one tool, one number ----------------------------------------------------


def _gdocs_batch_update():
    from charter.packs import gdocs

    return gdocs.documents_batch_update


def test_the_gdocs_union_costs_what_three_pages_say_it_costs():
    tool = _gdocs_batch_update()
    tokens = schema_tokens(tool)

    _assert_quoted("tools/projections.md", "cost {} tokens of schema", tokens)
    _assert_quoted("reference/tool.mdx", "a tool priced at {} tokens", tokens)
    _assert_quoted(
        "optimization/context-window.md", "gdocs.documents_batch_update    {} tokens", tokens
    )


def test_narrowing_the_gdocs_union_lands_where_two_pages_say():
    tool = _gdocs_batch_update()
    narrowed = tool.derived(
        name="documents_edit_text",
        keep={"insert_text", "delete_content_range", "replace_all_text"},
    )
    after = schema_tokens(narrowed)
    percent = round(100 * (schema_tokens(tool) - after) / schema_tokens(tool))

    _assert_quoted("tools/projections.md", "takes that to {}, or", after)
    assert f"or {percent}% smaller" in _text("tools/projections.md")
    assert f"->  {after:,}    ({percent}% smaller)" in _text("optimization/context-window.md"), (
        f"the context-window page states the wrong narrowed size (now {after:,}, {percent}% smaller)"
    )


def test_the_drop_that_makes_a_tool_larger_still_does():
    """A negative cost is the point of the example, so the direction is asserted too."""
    tool = _gdocs_batch_update()
    bigger = tool.derived(name="x", drop={"body.requests.insert_text.location.index"})
    before, after = schema_tokens(tool), schema_tokens(bigger)
    assert after > before, "dropping a shared-$def path no longer costs more than it saves"

    for page in ("tools/projections.md", "reference/tool.mdx"):
        assert f"{before:,} tokens to {after:,}" in _text(page), (
            f"{page} states the wrong pair for this drop (now {before:,} -> {after:,})"
        )


def test_the_linear_filter_figures_match_the_pack():
    from charter.packs import linear

    curated = schema_tokens(linear.search_issues)
    full = schema_tokens(linear.search_issues_full)
    lean = schema_tokens(linear.search_issues_full.derived(name="lean", drop={"filter"}))

    _assert_quoted("tools/projections.md", "`linear.search_issues` itself is {} tokens.", curated)
    _assert_quoted("optimization/context-window.md", "`search_issues` is {} tokens", curated)
    _assert_quoted("optimization/context-window.md", "`search_issues_full` costs {}.", full)
    assert (
        f"linear.search_issues_full    {full:,} tokens  ->  {lean:,}    ({round(full / lean)}x)"
        in _text("optimization/context-window.md")
    )


def test_the_widest_shipped_tool_is_priced_right_for_the_agent_rule():
    from charter.packs import gsheets

    _assert_quoted(
        "start/coding-agents.mdx",
        "`gsheets.spreadsheets_batch_update` is {} tokens of schema",
        schema_tokens(gsheets.spreadsheets_batch_update),
    )


# --- the README's worked projection ------------------------------------------


def test_the_readme_projection_produces_the_number_it_prints():
    from charter.packs import linear

    F = "variables.filter."
    # Laid out line for line as the README lays it out, because the point of the
    # test is that a reader can hold the two side by side.
    # fmt: off
    keep = {
        F + "id", F + "number", F + "title", F + "priority",
        F + "due_date", F + "created_at", F + "updated_at", F + "completed_at",
        F + "state.type", F + "state.name",
        F + "assignee.email", F + "assignee.name",
        F + "team.key", F + "team.name",
        F + "labels.name",
    }
    # fmt: on
    tokens = schema_tokens(linear.issues_list_full.derived(name="issues_list_triage", keep=keep))
    assert f"# {tokens}, i.e. {tokens * 4:,} bytes" in README.read_text(), (
        f"the README prints a figure this projection no longer produces (now {tokens})"
    )

    # And the warning beside it: keeping the whole relation is *larger*.
    whole = schema_tokens(
        linear.issues_list_full.derived(
            name="wide", keep=(keep - {F + "team.key", F + "team.name"}) | {F + "team"}
        )
    )
    assert whole > tokens
    _assert_quoted("README.md", "lands you at {} tokens", whole)
    _assert_quoted("README.md", "is curated at {} tokens", schema_tokens(linear.issues_list))


# --- whole payloads ----------------------------------------------------------


def test_progressive_disclosure_saves_what_two_pages_claim():
    from charter.packs import gmail, stripe

    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    first = json_tokens(to_openai_tools(session))
    everything = json_tokens(to_openai_tools([*gmail.TOOLS, *stripe.TOOLS]))

    claim = f"{first:,} tokens on the first turn instead of {everything:,}"
    for page in ("reference/tool-discovery.mdx", "using/adapters.mdx"):
        assert claim in _text(page), (
            f"{page} states a saving the session no longer produces: {claim}"
        )

    assert f"# ({len(session.tools)}, 1)" in _text("reference/tool-discovery.mdx")


def test_the_duplicated_defs_payload_is_the_size_the_page_prints():
    from charter.packs import linear

    three = [linear.teams_list_full, linear.issues_list_full, linear.projects_list_full]
    openai_bytes = len(json.dumps(to_openai_tools(three)))
    mcp_bytes = len(json.dumps([llm_json_schema(t.llm_schema()) for t in three]))
    projected = [t.derived(name=t.name + "_p", drop={"variables.filter"}) for t in three]
    projected_bytes = len(json.dumps(to_openai_tools(projected)))

    page = _text("optimization/context-window.md")
    assert f"OpenAI    {openai_bytes:,} bytes" in page, (
        f"OpenAI payload is now {openai_bytes:,} bytes"
    )
    assert f"MCP       {mcp_bytes:,} bytes" in page, f"MCP payload is now {mcp_bytes:,} bytes"
    assert f"as shipped    {openai_bytes:,} bytes" in page
    assert f"projected       {projected_bytes:,} bytes" in page, (
        f"the projected payload is now {projected_bytes:,} bytes"
    )
    assert f"{round(openai_bytes / projected_bytes)}x, because the saving lands" in page


def test_the_gdocs_pack_page_rounds_its_schema_size_honestly():
    """The page rounds — "roughly 29KB, about 7,300 tokens" — so this allows 10%."""
    tool = _gdocs_batch_update()
    kb = len(json.dumps(tool.to_json_schema()["parameters"])) / 1024
    tokens = schema_tokens(tool)

    stated = re.search(r"roughly (\d+)KB — about ([\d,]+) tokens", _text("packs/gdocs.mdx"))
    assert stated, "the gdocs page no longer states a schema size"
    assert abs(int(stated.group(1)) - kb) / kb < 0.1, f"the schema is now {kb:.0f}KB"
    claimed = int(stated.group(2).replace(",", ""))
    assert abs(claimed - tokens) / tokens < 0.1, f"the schema is now {tokens:,} tokens"


def test_the_flattening_page_states_the_schema_size_it_measures():
    """The one figure in that paragraph that still tracks the pack.

    The 1.92 GB and the 115 MB beside it do not: they are a record of one
    `langchain_core` run against the pack as it stood, and the page says so. This
    is the half that has to keep up, and it was the half that silently did not —
    the paragraph paired a stale byte count with a live conclusion.
    """
    from charter.packs import linear

    kb = round(len(json.dumps(linear.teams_list_full.to_json_schema()["parameters"])) / 1024)
    assert f"`teams_list_full` — {kb} KB" in _text("optimization/context-window.md"), (
        f"the flattening paragraph states the wrong schema size (now {kb} KB)"
    )


# --- the MCP setup page is load-bearing for the name budget ---------------------
#
# Tool names fit 64 characters only under the config the page recommends: one
# server holding every pack. A page that went back to a server per pack would put
# three gsheets tools out of reach without a single test failing, because nothing
# in the library can see the key a client was configured under.


def test_the_mcp_page_configures_one_server_holding_several_packs():
    """Every client example passes a pack list, so the pack stays out of the key."""
    text = _text("using/mcp.mdx")

    # The four client examples plus the `claude mcp add` line all name the server
    # `charter` and hand `--pack` more than one pack.
    assert text.count("gmail,gsheets,slack") == 4, "a client example stopped passing a pack list"
    assert "claude mcp add charter --" in text


def test_the_mcp_page_does_not_recommend_a_server_named_after_a_pack():
    """`charter-gsheets` as a config key puts three gsheets names over 64.

    The page may still *mention* the shape to explain why it is wrong — it does —
    so this checks the places a reader copies from: the fenced config blocks.

    Matched against the real pack names rather than `charter-\\w+`, which also hit
    `charter-ai`, the distribution name, the moment it appeared in an install
    line. The thing being forbidden is a *pack* in the server key, so the pack
    list is what to match on, and it tracks PACKS rather than a fixed three.
    """
    import re as _re

    from charter.mcp import PACKS

    text = _text("using/mcp.mdx")
    blocks = _re.findall(r"^```[^\n]*\n(.*?)^```", text, _re.S | _re.M)
    assert blocks, "no fenced blocks found; the page structure changed"
    per_pack = _re.compile(r"charter-(?:" + "|".join(_re.escape(p) for p in PACKS) + r")\b")
    offenders = [b for b in blocks if per_pack.search(b)]
    assert not offenders, "a copyable block names a server after its pack: " + repr(offenders)
