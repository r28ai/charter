"""
Progressive disclosure, as Claude Code does it: a flat catalogue of names, a
``ToolSearch`` that turns names into loaded tools, and nothing callable until it
has been loaded.

The property under test is absence. Two earlier versions left deferred tools in
the tool list with a placeholder schema, so the model could call them and did —
guessing arguments, failing validation, guessing again, three to four times a
run. Making the wrong move unavailable took that to zero.

Offline: no credentials, no network.
"""

from __future__ import annotations

import json

import pytest
from inspect_ai.tool import ToolDef, ToolSource

from charter_harness.arms.base import arm_by_name
from charter_harness.arms.charter_arm import charter_tooldef, model_facing_names, pack_tools
from charter_harness.arms.progressive_arm import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_THRESHOLD,
    Catalogue,
    ProgressiveArm,
    parse_query,
    rank,
    schema_tokens,
)
from charter_harness.settings import Settings, Wiring

# gdocs holds the largest schema in the project (documents_batch_update, ~13,000
# tokens) and one of the smallest; linear adds enough tools to rank between.
PACKS = ("gdocs", "gcalendar", "linear")


@pytest.fixture
def wiring() -> Wiring:
    return Wiring(settings=Settings())


@pytest.fixture
def catalogue(wiring: Wiring) -> Catalogue:
    built = arm_by_name("progressive").tools(PACKS, wiring)
    assert len(built) == 1 and isinstance(built[0], Catalogue)
    return built[0]


async def names_of(cat: Catalogue) -> set[str]:
    return {ToolDef(t).name for t in await cat.tools()}


async def search(cat: Catalogue, query: str, **kwargs) -> dict:
    return json.loads(await cat._search_tooldef().tool(query=query, **kwargs))


def wire_tokens(defs: list[ToolDef]) -> int:
    payload = [
        {
            "name": d.name,
            "description": d.description,
            "parameters": {
                "properties": {
                    k: v.model_dump(exclude_none=True)
                    for k, v in (d.parameters.properties or {}).items()
                },
                "required": list(d.parameters.required or []),
            },
        }
        for d in defs
    ]
    return len(json.dumps(payload, ensure_ascii=False)) // 4


# -----------------------------------------------------
# The catalogue
# -----------------------------------------------------


def test_the_arm_offers_a_toolsource_inspect_will_re_resolve(catalogue):
    """Inspect resolves a ToolSource on every turn; that is what lets the list
    grow. A plain list would freeze the tools at turn one."""
    assert isinstance(catalogue, ToolSource)


def test_the_catalogue_is_names_only(catalogue):
    """As Claude Code has it. Descriptions would cost about five times as much,
    and the keyword form of ToolSearch is what replaces them."""
    text = catalogue.catalogue_text()
    assert text.splitlines() == sorted(catalogue.deferrable)
    for tool in catalogue.deferrable.values():
        first_sentence = (tool.description or "").strip().split(".")[0]
        if len(first_sentence) > 25:
            assert first_sentence not in text


def test_the_catalogue_does_not_shrink_as_tools_load(catalogue):
    """It sits in the prompt prefix. Rewriting it every turn would invalidate
    the cache that makes the prefix cheap."""
    before = catalogue.catalogue_text()
    catalogue.session.search("select:" + ",".join(catalogue.deferrable))
    assert catalogue.catalogue_text() == before


def test_the_search_description_warns_that_schemas_are_not_loaded(catalogue):
    description = catalogue._search_tooldef().description
    assert "NOT loaded" in description
    assert "select:" in description
    assert "ONE call" in description
    assert catalogue.catalogue_text() in description


def test_big_schemas_are_deferrable_and_small_ones_are_resident(catalogue):
    names = model_facing_names(PACKS)
    for pack in PACKS:
        for tool in pack_tools(pack):
            shown = names[(pack, tool.name)]
            assert (shown in catalogue.deferrable) == (schema_tokens(tool) > DEFAULT_THRESHOLD), (
                shown
            )


# -----------------------------------------------------
# Absence — the mechanism itself
# -----------------------------------------------------


async def test_an_unloaded_tool_is_absent_not_empty(catalogue):
    """The regression that cost two probe runs. Offering the tool with a
    placeholder schema is what invited the model to call it blind."""
    offered = await names_of(catalogue)
    assert "ToolSearch" in offered
    for name in catalogue.deferrable:
        assert name not in offered, f"{name} is callable before being loaded"


async def test_loading_adds_the_tool_with_its_real_schema(catalogue):
    assert "gdocs__documents_batch_update" not in await names_of(catalogue)
    await search(catalogue, "select:gdocs__documents_batch_update")
    assert "gdocs__documents_batch_update" in await names_of(catalogue)

    mine = next(
        ToolDef(t)
        for t in await catalogue.tools()
        if ToolDef(t).name == "gdocs__documents_batch_update"
    )
    theirs = charter_tooldef(
        catalogue.deferrable["gdocs__documents_batch_update"], name="gdocs__documents_batch_update"
    )
    # A loaded tool *is* the Charter arm's tool, not a wrapper around it. The two
    # arms have to be running the same thing for a comparison to mean anything.
    assert mine.description == theirs.description
    assert set(mine.parameters.properties or {}) == set(theirs.parameters.properties or {})
    assert mine.parameters.required == theirs.parameters.required


async def test_the_search_retires_once_everything_is_loaded(catalogue):
    await search(catalogue, "select:" + ",".join(catalogue.deferrable))
    offered = await names_of(catalogue)
    assert "ToolSearch" not in offered
    assert set(catalogue.deferrable) <= offered


# -----------------------------------------------------
# The three query forms
# -----------------------------------------------------


def test_select_is_exclusive_and_unbounded():
    """Naming tools is not a search: nothing is ranked, nothing is truncated.
    Silently dropping a named tool would strand a model about to call it."""
    exact, required, terms = parse_query("select:a,b, c ")
    assert exact == ["a", "b", "c"]
    assert (required, terms) == ([], [])


def test_a_plus_term_is_required_and_the_rest_rank():
    exact, required, terms = parse_query("+linear issue update")
    assert exact is None
    assert required == ["linear"]
    assert terms == ["issue", "update"]


async def test_select_loads_exactly_the_named_tools(catalogue):
    out = await search(catalogue, "select:linear__issues_list,linear__issue_update")
    assert out["loaded"] == ["linear__issue_update", "linear__issues_list"]
    assert {"linear__issues_list", "linear__issue_update"} <= await names_of(catalogue)


async def test_select_names_the_alternatives_for_a_name_it_does_not_know(catalogue):
    out = await search(catalogue, "select:linear__issues_list,gdocs__documents_batchUpdate")
    assert out["loaded"] == ["linear__issues_list"]
    assert out["unknown"]["names"] == ["gdocs__documents_batchUpdate"]
    assert "gdocs__documents_batch_update" in out["unknown"]["available"]


async def test_keywords_rank_and_respect_max_results(catalogue):
    out = await search(catalogue, "events calendar", max_results=2)
    assert len(out["loaded"]) == 2
    assert all("event" in n or "calendar" in n for n in out["loaded"])


def test_a_name_hit_outranks_a_description_hit(catalogue):
    ordered = rank(catalogue.deferrable, [], ["document"])
    assert ordered[0].startswith("gdocs__documents_")


def test_a_required_term_excludes_everything_without_it(catalogue):
    assert rank(catalogue.deferrable, ["events"], []) == [
        n for n in sorted(catalogue.deferrable) if "events" in n
    ]
    assert rank(catalogue.deferrable, ["nosuchprovider"], []) == []


async def test_a_query_that_matches_nothing_says_so_and_lists_what_exists(catalogue):
    """A miss reports the miss and shows the catalogue, rather than loading
    something to have loaded something.

    The query has to be nonsense to the *ranker*, which is a stronger condition
    than being nonsense in English. This read `"zzz nothing matches"` until the
    Linear pack described `document_create` as hanging "off nothing at all":
    `nothing` is an ordinary word, it appeared in a description, and the ranker
    scored the hit exactly as it is documented to. Nothing was wrong except the
    query.

    So the premise is asserted rather than assumed. A pack that starts using one
    of these tokens now fails here saying so, instead of turning this into a
    confusing failure about ranking."""
    query = "zzzqqq xyzzyfoo"
    haystack = " ".join(
        f"{name} {tool.description or ''}" for name, tool in catalogue.deferrable.items()
    ).lower()
    for token in query.split():
        assert token not in haystack, (
            f"{token!r} now appears in a tool name or description, so this query "
            "no longer tests a miss. Pick another nonsense token."
        )

    out = await search(catalogue, query)
    assert out["loaded"] == []
    assert "No tool matched" in out["note"]
    assert out["available"] == sorted(catalogue.deferrable)


def test_max_results_defaults_to_claude_codes_default():
    assert DEFAULT_MAX_RESULTS == 5


# -----------------------------------------------------
# The saving, on what actually goes over the wire
# -----------------------------------------------------


async def test_the_first_turn_is_much_smaller_than_the_charter_arm(catalogue, wiring):
    theirs = wire_tokens(arm_by_name("charter").tools(PACKS, wiring))
    mine = wire_tokens([ToolDef(t) for t in await catalogue.tools()])
    assert mine * 3 < theirs, f"{theirs:,} -> {mine:,} tokens"


async def test_loading_everything_costs_about_what_the_charter_arm_costs(catalogue, wiring):
    """The saving is in never loading what is never used. A run that loads the
    lot should land near the Charter arm, or the accounting is wrong."""
    theirs = wire_tokens(arm_by_name("charter").tools(PACKS, wiring))
    await search(catalogue, "select:" + ",".join(catalogue.deferrable))
    mine = wire_tokens([ToolDef(t) for t in await catalogue.tools()])
    assert 0.8 < mine / theirs < 1.3, f"{theirs:,} vs {mine:,}"


def test_a_threshold_above_every_schema_defers_nothing(wiring):
    built = ProgressiveArm(threshold=10**9).tools(PACKS, wiring)
    assert not any(isinstance(t, Catalogue) for t in built)
    assert all(isinstance(t, ToolDef) for t in built)


def test_an_arm_resolves_even_when_another_was_imported_first():
    """The registry's lazy import is keyed on the arm asked for, not on the
    registry being empty."""
    import subprocess
    import sys

    program = (
        "import charter_harness.arms.charter_arm\n"
        "from charter_harness.arms.base import arm_by_name\n"
        "print(arm_by_name('progressive').name, arm_by_name('raw').name)\n"
    )
    out = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["progressive", "raw"]
