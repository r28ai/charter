"""
One name, every surface.

The claim these guard is that a pack is named the same way whether it is reached
inline, handed to LangChain or OpenAI, or served over MCP — for one pack, for
several, and for a hand-written pack mixed with shipped ones. Each surface
resolves a call differently, so agreeing on the *list* is not enough: every one
of them is also invoked here, by the name it published, and checked to reach the
tool it named.

Offline: every request is answered by respx.
"""

from __future__ import annotations

import json
from typing import Annotated

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import Path, Query, qualified_names
from charter.adapters.mcp import build_server
from charter.adapters.openai import to_openai_tools
from charter.auth import StaticTokenProvider
from charter.factories import api_key_tool_factory
from charter.packs import gcalendar, gmail, shopify, stripe


class Args(BaseModel):
    thing_id: Annotated[str, Path()]
    q: Annotated[str, Query()] = ""


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    for var in ("GOOGLE_ACCESS_TOKEN", "STRIPE_API_KEY", "SHOPIFY_ACCESS_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    gmail.configure(StaticTokenProvider("t"))
    gcalendar.configure(StaticTokenProvider("t"))
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


def sets(custom):
    return {
        "one pack, custom": list(custom),
        "one pack, shipped": list(gcalendar.TOOLS),
        "two shipped, with a collision": list(stripe.TOOLS) + list(shopify.TOOLS),
        "shipped plus custom": list(gmail.TOOLS) + list(custom),
        "three mixed": list(gcalendar.TOOLS) + list(stripe.TOOLS) + list(custom),
    }


async def mcp_names(tools):
    listed = await build_server(tools, name="charter").list_tools()
    return sorted(t.name for t in listed)


def openai_names(tools):
    return sorted(t["function"]["name"] for t in to_openai_tools(tools))


def langchain_names(tools):
    langchain = pytest.importorskip("charter.adapters.langchain")
    return sorted(t.name for t in langchain.to_langchain_tools(tools))


# -----------------------------------------------------
# The surfaces agree
# -----------------------------------------------------


@pytest.mark.parametrize("label", [
    "one pack, custom", "one pack, shipped", "two shipped, with a collision",
    "shipped plus custom", "three mixed",
])
async def test_every_surface_publishes_the_same_names(label, custom):
    tools = sets(custom)[label]
    core = sorted(qualified_names(tools))

    assert openai_names(tools) == core
    assert await mcp_names(tools) == core
    assert langchain_names(tools) == core
    assert len(core) == len(tools), "a tool went missing"
    assert all("__" in name for name in core)


async def test_a_pack_is_named_the_same_way_alone_as_beside_another(custom):
    """The property that makes a name safe to save in a prompt or an allow-list."""
    alone = sorted(qualified_names(gcalendar.TOOLS))
    beside = sorted(qualified_names(list(gcalendar.TOOLS) + list(custom)))
    assert alone == [n for n in beside if n.startswith("gcalendar__")]
    assert await mcp_names(gcalendar.TOOLS) == alone


# -----------------------------------------------------
# The surfaces route a call to the tool they named
# -----------------------------------------------------


@respx.mock
async def test_inline_needs_no_name_at_all(custom):
    """A Python reference. `tool.name` is still bare, because there is no
    namespace to share."""
    route = respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    assert custom[0].name == "my_tool"
    assert await custom[0].ainvoke({"thing_id": "42"}) == {"reached": "custom"}
    assert route.called


@respx.mock
async def test_mcp_routes_the_published_name_and_refuses_the_bare_one(custom):
    respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    server = build_server(list(stripe.TOOLS) + list(custom), name="charter")

    result = await server.call_tool("xyz__my_tool", {"thing_id": "42"})
    assert "custom" in result.content[0].text

    with pytest.raises(Exception) as exc:
        await server.call_tool("my_tool", {"thing_id": "42"})
    assert "Unknown tool" in str(exc.value)
    assert "xyz__my_tool" in str(exc.value), "the error should name what is available"


@respx.mock
async def test_openai_round_trips_through_qualified_names(custom):
    """The OpenAI APIs hand a call back for the caller to execute, so the map
    used to publish is the map used to route."""
    respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    tools = list(stripe.TOOLS) + list(custom)
    published = {t["function"]["name"] for t in to_openai_tools(tools)}
    by_name = qualified_names(tools)
    assert published == set(by_name)

    # what the model sends back
    call_name, call_args = "xyz__my_tool", '{"thing_id": "42"}'
    assert await by_name[call_name].ainvoke(json.loads(call_args)) == {"reached": "custom"}


@respx.mock
async def test_langchain_routes_by_the_name_it_was_given(custom):
    langchain = pytest.importorskip("charter.adapters.langchain")
    respx.get("https://myproprietary.api/v1/things/42").mock(
        return_value=httpx.Response(200, json={"reached": "custom"})
    )
    wrapped = {t.name: t for t in langchain.to_langchain_tools(list(stripe.TOOLS) + list(custom))}
    assert "xyz__my_tool" in wrapped and "my_tool" not in wrapped
    assert await wrapped["xyz__my_tool"].ainvoke({"thing_id": "42"}) == {"reached": "custom"}


# -----------------------------------------------------
# The collision, end to end
# -----------------------------------------------------


async def test_a_collision_reaches_two_different_tools(custom):
    """Stripe and Shopify both declare `products_list`. Published bare, this
    surface listed 23 tools and routed 21, sending two names to the wrong tool."""
    tools = list(stripe.TOOLS) + list(shopify.TOOLS)
    by_name = qualified_names(tools)

    assert len({t.name for t in tools}) < len(tools), "the collision is the premise"
    assert len(by_name) == len(tools)

    # Each name reaches its own tool — asserted on identity, because Shopify's
    # base URL is deferred until configure() and says nothing about the host.
    assert by_name["stripe__products_list"] is stripe.products_list
    assert by_name["shopify__products_list"] is shopify.products_list
    assert by_name["stripe__products_list"] is not by_name["shopify__products_list"]
    assert "api.stripe.com" in str(by_name["stripe__products_list"].base_url)
    assert await mcp_names(tools) == sorted(by_name)
