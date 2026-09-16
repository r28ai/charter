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
from typing import Annotated

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import Path, Query, ToolSession, qualified_names, schema_tokens
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
    for var in ("GOOGLE_ACCESS_TOKEN", "STRIPE_API_KEY", "SHOPIFY_ACCESS_TOKEN",
                "FIRECRAWL_API_KEY"):
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
