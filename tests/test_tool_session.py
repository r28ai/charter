"""
The tool surface that grows.

What these guard is that deferring a schema changes *when* it is sent and
nothing else: the same qualified name, the same validated arguments, the same
tool at the end of it, on every surface. And that the growth is append-only,
because a tool list that reorders as it grows re-serialises a prompt prefix that
was supposed to be cached.

Offline: every request is answered by respx.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import Mode, Path, Query, ToolSession, qualified_names, schema_tokens
from charter.adapters.mcp import build_server
from charter.adapters.openai import to_openai_tools
from charter.auth import StaticTokenProvider
from charter.discovery import SEARCH_TOOL_NAME
from charter.factories import api_key_tool_factory
from charter.packs import firecrawl, gcalendar, gmail, shopify, stripe
from charter.types.errors import ToolValidationError


class Args(BaseModel):
    thing_id: Annotated[str, Path()]
    q: Annotated[str, Query()] = ""


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    for var in (
        "GOOGLE_ACCESS_TOKEN",
        "STRIPE_API_KEY",
        "SHOPIFY_ACCESS_TOKEN",
        "FIRECRAWL_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    gmail.configure(StaticTokenProvider("t"))
    gcalendar.configure(StaticTokenProvider("t"))
    firecrawl.configure(api_key="fc-test")
    stripe.configure(api_key="sk_test_x")
    shopify.configure(shop="s.myshopify.com", access_token="a")


@pytest.fixture
def custom():
    """A pack written by hand, against an API Charter has never seen."""
    factory = api_key_tool_factory(
        base_url="https://myproprietary.api/v1/",
        pack="xyz",
        api_key_headers={"x-api-key": "k"},
    )
    return [
        factory(
            name="my_tool",
            args_schema=Args,
            method="GET",
            url_template="things/{thing_id}",
            description="Fetch a thing.",
        )
    ]


def names(definitions):
    return [d["function"]["name"] for d in definitions]


# -----------------------------------------------------
# What is deferred, and when nothing is
# -----------------------------------------------------


@pytest.mark.parametrize("pack", [firecrawl, gmail, stripe, shopify, gcalendar])
def test_every_tool_is_deferred_however_small_the_pack(pack):
    """Three tools or twenty-three, the model is given names and a ToolSearch.

    Claude Code keeps a hot set resident, but that set is its own built-in core;
    every tool from a configured MCP server is deferred, all of them. A Charter
    tool is a configured tool.
    """
    session = ToolSession(pack.TOOLS)
    assert session.progressive
    assert not session.resident
    assert set(session.deferrable) == set(session.tools)
    assert names(to_openai_tools(session)) == [SEARCH_TOOL_NAME]


def test_progressive_false_sends_everything():
    session = ToolSession(gmail.TOOLS, progressive=False)
    assert not session.deferrable
    assert set(names(to_openai_tools(session))) == set(qualified_names(gmail.TOOLS))
    assert SEARCH_TOOL_NAME not in names(to_openai_tools(session))


def test_a_threshold_is_still_available_for_a_pack_with_another_shape():
    session = ToolSession(gmail.TOOLS, threshold=200)
    assert session.resident and session.deferrable
    assert all(schema_tokens(t) <= 200 for t in session.resident.values())
    assert all(schema_tokens(t) > 200 for t in session.deferrable.values())


def test_the_first_turn_costs_a_fraction_of_the_inline_surface():
    tools = [*gmail.TOOLS, *stripe.TOOLS]
    session = ToolSession(tools)
    first = sum(len(json.dumps(d)) for d in to_openai_tools(session))
    inline = sum(len(json.dumps(d)) for d in to_openai_tools(tools))
    assert first * 10 < inline, f"{first} of {inline} bytes is not worth a round trip"


# -----------------------------------------------------
# An unloaded tool is absent, not empty
# -----------------------------------------------------


def test_a_deferred_tool_is_not_offered_at_all():
    """Not with an empty schema, not behind a wrapper. Both earlier designs left
    them callable and the model called them, guessing arguments."""
    session = ToolSession(gmail.TOOLS, threshold=200)
    published = set(names(to_openai_tools(session)))
    assert published == set(session.resident) | {SEARCH_TOOL_NAME}
    assert not published & set(session.deferrable)


async def test_calling_a_deferred_tool_says_how_to_load_it():
    session = ToolSession(gmail.TOOLS)
    deferred = sorted(session.deferrable)[0]
    with pytest.raises(ToolValidationError) as exc:
        await session.dispatch(deferred, {})
    assert f"select:{deferred}" in str(exc.value)


async def test_an_unknown_name_lists_what_is_callable():
    session = ToolSession(gmail.TOOLS)
    session.search(f"select:{sorted(session.deferrable)[0]}")
    with pytest.raises(ToolValidationError) as exc:
        await session.dispatch("gmail__not_a_tool", {})
    assert "Unknown tool" in str(exc.value)
    assert sorted(session.visible())[0] in str(exc.value)


# -----------------------------------------------------
# Searching
# -----------------------------------------------------


def test_select_loads_exactly_what_it_names():
    session = ToolSession(gmail.TOOLS)
    wanted = sorted(session.deferrable)[:3]
    result = session.search(f"select:{','.join(wanted)}")
    assert result["loaded"] == sorted(wanted)
    assert set(wanted) <= set(session.visible())


def test_select_is_not_truncated_by_max_results():
    """The caller named what it wants; dropping the tail would silently lose a
    tool the model is about to call."""
    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    wanted = sorted(session.deferrable)[:7]
    result = session.search(f"select:{','.join(wanted)}", max_results=2)
    assert result["loaded"] == sorted(wanted)


def test_a_required_term_filters_by_pack():
    """The pack is a substring of every qualified name, which is what makes `+`
    enough on its own."""
    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    loaded = session.search("+stripe list", max_results=20)["loaded"]
    assert loaded and all(n.startswith("stripe__") for n in loaded)


def test_an_unknown_name_comes_back_with_the_catalogue():
    session = ToolSession(gmail.TOOLS)
    result = session.search("select:gmail__nope")
    assert result["unknown"]["names"] == ["gmail__nope"]
    assert result["unknown"]["available"] == sorted(session.deferrable)


def test_a_query_that_matches_nothing_says_so():
    session = ToolSession(gmail.TOOLS)
    result = session.search("+zzz nothing")
    assert result["loaded"] == []
    assert result["available"] == sorted(session.deferrable)


def test_the_search_drops_out_once_everything_is_loaded():
    session = ToolSession(gmail.TOOLS)
    session.search(f"select:{','.join(session.deferrable)}")
    assert not session.offers_search()
    assert SEARCH_TOOL_NAME not in names(to_openai_tools(session))
    assert set(names(to_openai_tools(session))) == set(session.tools)


def test_reset_forgets_what_was_loaded():
    session = ToolSession(gmail.TOOLS)
    session.search(f"select:{sorted(session.deferrable)[0]}")
    assert session.visible()
    session.reset()
    assert session.visible() == session.resident == {}


# -----------------------------------------------------
# The growth is append-only, on every surface
# -----------------------------------------------------


async def test_every_surface_grows_by_appending(custom):
    """A tool list that reorders as it grows re-serialises the prompt prefix it
    was supposed to keep cached. Every fixed part must precede every growing one.
    """
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    tools = [*gmail.TOOLS, *stripe.TOOLS, *custom]
    session = ToolSession(tools)
    server = build_server(session)

    async def snapshot():
        return (
            names(to_openai_tools(session)),
            [t.name for t in await server.list_tools()],
        )

    history = [await snapshot()]
    for query in ("+stripe refund", "+gmail draft", f"select:{sorted(session.deferrable)[-1]}"):
        session.search(query)
        history.append(await snapshot())

    for surface in range(2):
        for before, after in zip(history, history[1:], strict=False):
            assert after[surface][: len(before[surface])] == before[surface], (
                "a load reordered the tool list instead of extending it"
            )
    assert len(history[-1][0]) > len(history[0][0]), "nothing was ever loaded"


def test_the_catalogue_is_stable_as_tools_load():
    """It sits in the prompt prefix; shrinking it each turn would invalidate the
    cache that makes the prefix cheap."""
    session = ToolSession(gmail.TOOLS)
    before = session.search_definition()["description"]
    session.search(f"select:{sorted(session.deferrable)[0]}")
    assert session.search_definition()["description"] == before


# -----------------------------------------------------
# A loaded tool is the tool, on every surface
# -----------------------------------------------------


@respx.mock
async def test_a_loaded_tool_reaches_the_api_through_the_session(custom):
    route = respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    # threshold=0 so even a two-field schema is deferred: the point here is that
    # a tool arriving through ToolSearch is the same tool, not that this one is big.
    session = ToolSession([*gmail.TOOLS, *custom], progressive=True, threshold=0)
    assert "xyz__my_tool" in session.deferrable
    session.search("select:xyz__my_tool")
    assert await session.dispatch("xyz__my_tool", {"thing_id": "42"}) == {"reached": "custom"}
    assert route.called


@respx.mock
async def test_mcp_publishes_and_routes_a_loaded_tool(custom):
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    session = ToolSession([*stripe.TOOLS, *custom], progressive=True, threshold=0)
    server = build_server(session)

    assert "xyz__my_tool" not in [t.name for t in await server.list_tools()]
    result = await server.call_tool(SEARCH_TOOL_NAME, {"query": "select:xyz__my_tool"})
    assert json.loads(result.content[0].text)["loaded"] == ["xyz__my_tool"]

    listed = {t.name: t for t in await server.list_tools()}
    # The LLM view is camel-cased, as it is for a tool that was never deferred.
    assert "thingId" in listed["xyz__my_tool"].input_schema["properties"]
    reached = await server.call_tool("xyz__my_tool", {"thing_id": "42"})
    assert "custom" in reached.content[0].text


async def test_langchain_publishes_the_search_and_the_loaded_tool():
    langchain = pytest.importorskip("charter.adapters.langchain")
    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])

    wrapped = {t.name: t for t in langchain.to_langchain_tools(session)}
    assert SEARCH_TOOL_NAME in wrapped
    target = sorted(session.deferrable)[0]
    assert target not in wrapped

    await wrapped[SEARCH_TOOL_NAME].ainvoke({"query": f"select:{target}"})
    reloaded = {t.name: t for t in langchain.to_langchain_tools(session)}
    assert target in reloaded
    assert reloaded[target].args_schema is session.tools[target].llm_schema()


# -----------------------------------------------------
# Nothing about naming changes
# -----------------------------------------------------


async def test_the_published_names_are_the_qualified_names(custom):
    """Deferral changes when a schema is sent, never what the tool is called."""
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    tools = [*stripe.TOOLS, *shopify.TOOLS, *custom]
    session = ToolSession(tools)
    session.search(f"select:{','.join(sorted(session.deferrable)[:4])}")

    published = set(names(to_openai_tools(session))) - {SEARCH_TOOL_NAME}
    assert published == set(session.visible())
    assert published <= set(qualified_names(tools))
    assert {t.name for t in await build_server(session).list_tools()} == published | {
        SEARCH_TOOL_NAME
    }


def test_a_plain_list_is_never_progressive():
    """A list has nowhere to record what a search loaded, so every surface sends
    every schema. One rule, four adapters."""
    assert set(names(to_openai_tools(list(gmail.TOOLS)))) == set(qualified_names(gmail.TOOLS))
    assert SEARCH_TOOL_NAME not in names(to_openai_tools(list(gmail.TOOLS)))


async def test_build_server_with_a_list_publishes_everything():
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    listed = {t.name for t in await build_server(list(gmail.TOOLS)).list_tools()}
    assert listed == set(qualified_names(gmail.TOOLS))


# -----------------------------------------------------
# Queries that ask for nothing
# -----------------------------------------------------


@pytest.mark.parametrize("query", ["", "   ", "\n", "select:", "select:,,,"])
def test_a_query_with_nothing_to_match_on_loads_nothing(query):
    """It used to load five.

    `rank` skipped a zero-scoring tool only when there were terms to score
    against, so a query with no terms kept every tool at zero and returned the
    first `max_results` alphabetically. A model that sent an empty query was told
    five unrelated tools were now available.
    """
    session = ToolSession(gmail.TOOLS)
    result = session.search(query)
    assert result["loaded"] == []
    assert not session.loaded
    assert result["available"] == sorted(session.deferrable)


async def test_toolsearch_with_no_arguments_at_all_loads_nothing():
    """`arguments: null` and `{}` both decay to an empty query."""
    session = ToolSession(gmail.TOOLS)
    await session.dispatch(SEARCH_TOOL_NAME, None)
    await session.dispatch(SEARCH_TOOL_NAME, {})
    assert not session.loaded


def test_a_required_term_alone_still_matches():
    """The fix must not take `+pack` with it: naming a pack is asking for
    something, and it is the documented way to filter by one."""
    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    loaded = session.search("+stripe", max_results=50)["loaded"]
    assert loaded and all(n.startswith("stripe__") for n in loaded)


def test_the_search_definition_is_not_shared_between_sessions():
    """It was one module-level dict handed out by reference.

    Callers edit tool definitions — adding `strict`, rewording a description —
    and doing that to one session's ToolSearch silently rewrote it for every
    other session in the process, and for the module constant.
    """
    from charter.discovery import SEARCH_PARAMETERS

    first, second = ToolSession(gmail.TOOLS), ToolSession(gmail.TOOLS)
    definition = to_openai_tools(first)[0]["function"]
    definition["parameters"]["properties"]["injected"] = {"type": "string"}
    definition["description"] = "clobbered"

    other = to_openai_tools(second)[0]["function"]
    assert "injected" not in other["parameters"]["properties"]
    assert not other["description"].startswith("clobbered")
    assert "injected" not in SEARCH_PARAMETERS["properties"]
    assert not to_openai_tools(first)[0]["function"]["description"].startswith("clobbered")


# -----------------------------------------------------
# The mode a session resolves
# -----------------------------------------------------


class Tiered(BaseModel):
    thing_id: Annotated[str, Path()]
    q: Annotated[Optional[str], Query()] = None
    raw_events: Annotated[Optional[str], Query(), Mode("pro, max")] = None
    model_weights: Annotated[Optional[str], Query(), Mode("max")] = None


@pytest.fixture
def tiered():
    """Two tools from one pack, built from a model that declares three tiers."""
    factory = api_key_tool_factory(
        base_url="https://tiers.api/v1/",
        pack="tier",
        api_key_headers={"x-api-key": "k"},
    )
    return [
        factory(
            name=name,
            args_schema=Tiered,
            method="GET",
            url_template="things/{thing_id}",
            description=f"The {name} endpoint.",
        )
        for name in ("reports_get", "reports_list")
    ]


def test_no_mode_hands_back_the_very_tools_it_was_given(tiered):
    """Backward compatibility, asserted by identity rather than by equality.

    Every existing session in the harness and the adapters passes no mode, and
    an equal-but-copied tool would satisfy every behavioural assertion while
    throwing away the views the pack built at import and doubling what the
    process holds.

    Built from a pack that *declares* modes, which is the half that matters.
    `mode=None` has to mean "leave each tool alone", not "resolve every tool at
    None": the second reads identically on a pack where nothing is labelled and
    quietly widens every labelled tool in every default session. Gmail declares
    no mode on any tool, so it cannot tell the two apart; Calendar ships `write`
    and `import` and can.
    """
    given = [*tiered, *gcalendar.TOOLS, *gmail.TOOLS]
    assert {t.mode for t in gcalendar.TOOLS} > {None}, "this pack no longer declares a mode"

    session = ToolSession(given)
    for name, tool in qualified_names(given).items():
        assert session.tools[name] is tool

    # The same claim stated as behaviour, in case identity is ever loosened.
    assert {t.mode for t in session.tools.values()} == {t.mode for t in given}

    assert session.mode is None
    assert "mode" not in repr(session)


def test_a_session_mode_reaches_the_catalogue_and_what_the_search_loads(tiered):
    """The deferred half has to be the resolved half too.

    The catalogue is built from `deferrable` and a load moves a tool out of it,
    so if the partition ran over the originals the model would search a
    catalogue of one surface and be handed tools from another.
    """
    session = ToolSession(tiered, mode="pro")
    assert set(session.deferrable) == {"tier__reports_get", "tier__reports_list"}

    session.search("select:tier__reports_get")
    loaded = session.visible()["tier__reports_get"]
    assert sorted(loaded.llm_schema().model_fields) == ["q", "raw_events", "thing_id"]

    # Spelled on the wire, because a published schema carries wire names.
    published = to_openai_tools(session)[-1]["function"]
    assert published["name"] == "tier__reports_get"
    assert sorted(published["parameters"]["properties"]) == ["q", "rawEvents", "thingId"]


def test_progressive_false_resolves_the_mode_too(tiered):
    session = ToolSession(tiered, progressive=False, mode="free")
    for definition in to_openai_tools(session):
        assert sorted(definition["function"]["parameters"]["properties"]) == ["q", "thingId"]


async def test_a_moded_session_dispatches_the_resolved_tool(tiered):
    """A field the mode withheld is not merely absent from the prompt.

    The schema the model is shown is the schema `dispatch` validates against, so
    a tier the deployment did not buy is refused by `extra="forbid"` rather than
    by anything the model was asked to respect.
    """
    session = ToolSession(tiered, progressive=False, mode="free")

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get("https://tiers.api/v1/things/t1").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        assert await session.dispatch("tier__reports_get", {"thing_id": "t1"}) == {"ok": True}
        assert route.called

        with pytest.raises(ToolValidationError, match="raw_events"):
            await session.dispatch("tier__reports_get", {"thing_id": "t1", "raw_events": "x"})


def test_one_pack_serves_three_tiers_without_a_toolset_dict(tiered):
    """The glue this replaces: `TOOLSETS = {"free": [...], "pro": [...]}`.

    Three sessions over the same tool objects, each resolving a different
    surface, and nothing in the pack or the deployment names a tier twice.
    """
    surfaces = {
        tier: sorted(
            ToolSession(tiered, mode=tier).tools["tier__reports_get"].llm_schema().model_fields
        )
        for tier in ("free", "pro", "max")
    }
    assert surfaces == {
        "free": ["q", "thing_id"],
        "pro": ["q", "raw_events", "thing_id"],
        "max": ["model_weights", "q", "raw_events", "thing_id"],
    }
    # The tools they were built from are untouched: a session resolves a view,
    # it does not reconfigure the pack for the rest of the process.
    assert sorted(tiered[0].llm_schema().model_fields) == [
        "model_weights",
        "q",
        "raw_events",
        "thing_id",
    ]


def test_constructing_a_moded_session_prepares_the_variants(tiered):
    """Building a session is `prepare()` for what it holds, at whatever mode.

    Partitioning sizes every schema and sizing one derives it, and that is the
    property that keeps the build at startup instead of inside the first
    request. A mode variant is a different tool object with a cold view, so if
    the partition ran over the originals the variants would all be cold.
    """
    session = ToolSession(tiered, mode="pro")
    for tool in session.tools.values():
        assert tool._views_ready, f"{tool.name} was left to build inside a request"
        assert tool._json_schema is not None
