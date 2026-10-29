"""The host's context reaches a Charter call through LangChain and MCP too.

A `FromContext` field is useless behind an adapter that drops `context`: every
call would be refused for a value the host had but could not pass. These run a
real LangChain agent and a real MCP server, offline, and check that each call
carries the context of the run or request it belongs to, and never another's.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from typing import Annotated, Any, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import FromContext, Query, ToolSession, api_key_tool_factory

BASE = "https://shop.example.com/"


class ListOrders(BaseModel):
    customer_id: Annotated[str, Query(), FromContext()]
    status: Annotated[Optional[str], Query()] = None


shop = api_key_tool_factory(pack="shop", base_url=BASE, api_key_headers={"X-Key": "k"})
orders = shop(
    name="orders_list",
    description="List orders.",
    method="GET",
    url_template="v1/orders",
    args_schema=ListOrders,
)


def _orders_route() -> Any:
    return respx.get(f"{BASE}v1/orders").mock(return_value=httpx.Response(200, json={"orders": []}))


def _customers(route: Any) -> list:
    return [c.request.url.params.get("customer_id") for c in route.calls]


# -----------------------------------------------------
# LangChain
# -----------------------------------------------------


@dataclass
class RunContext:
    customer_id: str


class CustomerModel(BaseModel):
    customer_id: str


@respx.mock
async def test_to_langchain_binds_a_context_to_every_call():
    pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
    from charter.adapters.langchain import to_langchain, to_langchain_tools

    route = _orders_route()
    await to_langchain(orders, context={"customer_id": "cus_a"}).ainvoke({"status": "open"})
    (wrapped,) = to_langchain_tools([orders], context={"customer_id": "cus_b"})
    await wrapped.ainvoke({})

    assert _customers(route) == ["cus_a", "cus_b"]


async def test_without_a_context_langchain_hands_back_the_hosts_error():
    pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
    from charter.adapters.langchain import to_langchain

    result = await to_langchain(orders).ainvoke({})

    assert "did not pass 'customer_id'" in result
    assert "changing the call will not help" in result


def _agent(middleware: Any, context_schema: Any = None) -> Any:
    pytest.importorskip("langchain.agents")
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    class Scripted(GenericFakeChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
            return self

    script = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "shop_orders_list", "args": {"status": "open"}, "id": "c"}],
            ),
            AIMessage(content="done"),
        ]
    )
    return create_agent(
        Scripted(messages=script), tools=[], middleware=[middleware], context_schema=context_schema
    )


USER = {"messages": [{"role": "user", "content": "my open orders"}]}


@respx.mock
@pytest.mark.parametrize(
    "make",
    [
        RunContext,
        lambda customer_id: CustomerModel(customer_id=customer_id),
        lambda customer_id: {"customer_id": customer_id},
    ],
    ids=["dataclass", "pydantic", "dict"],
)
async def test_the_middleware_hands_each_run_its_own_context(make):
    """One middleware, one session, two users: each call carries its own run's
    customer. The wrapper is shared, so a context stored on it would cross."""
    pytest.importorskip("langchain.agents")
    from charter.adapters.langchain import CharterMiddleware

    route = _orders_route()
    middleware = CharterMiddleware(ToolSession([orders], progressive=False))

    for customer in ("cus_a", "cus_b"):
        await _agent(middleware).ainvoke(USER, context=make(customer))

    assert _customers(route) == ["cus_a", "cus_b"]


async def test_the_middleware_without_a_context_tells_the_model_it_is_not_its_to_fix():
    pytest.importorskip("langchain.agents")
    from charter.adapters.langchain import CharterMiddleware

    middleware = CharterMiddleware(ToolSession([orders], progressive=False))
    out = await _agent(middleware).ainvoke(USER)

    (result,) = [m.content for m in out["messages"] if m.type == "tool"]
    assert "did not pass 'customer_id'" in result


async def test_a_context_charter_cannot_read_is_refused_by_name():
    pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
    from charter.adapters.langchain import _as_context

    with pytest.raises(TypeError, match="reads it as a mapping, a dataclass or a pydantic model"):
        _as_context(("customer_id", "cus_a"))


# -----------------------------------------------------
# MCP
# -----------------------------------------------------


@respx.mock
async def test_an_mcp_server_hands_every_call_a_fixed_context():
    """A stdio server is one process for one user, so the launcher knows whose."""
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    from charter.adapters.mcp import build_server

    route = _orders_route()
    server = build_server([orders], context={"customer_id": "cus_a"})

    await server.call_tool("shop_orders_list", {"status": "open"})

    assert _customers(route) == ["cus_a"]


@respx.mock
@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_an_mcp_server_reads_the_context_from_each_request(asynchronous):
    """An HTTP server learns the user from the request, so the context is a
    function of it, called once per tool call."""
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    from charter.adapters.mcp import build_server

    def from_request(request: Any) -> dict:
        return {"customer_id": request.user}

    async def from_request_async(request: Any) -> dict:
        return from_request(request)

    route = _orders_route()
    server = build_server([orders], context=from_request_async if asynchronous else from_request)

    for user in ("cus_a", "cus_b"):
        await server.call_tool(
            "shop_orders_list", {}, context=types.SimpleNamespace(user=user, session=None)
        )

    assert _customers(route) == ["cus_a", "cus_b"]


async def test_an_mcp_client_cannot_supply_the_hosts_value():
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    from mcp.server.mcpserver.exceptions import ToolError

    from charter.adapters.mcp import build_server

    server = build_server([orders])
    tools = await server.list_tools()
    assert "customer_id" not in tools[0].input_schema["properties"]

    with pytest.raises(ToolError, match="did not pass 'customer_id'"):
        await server.call_tool("shop_orders_list", {})
    with pytest.raises(ToolError):
        await server.call_tool("shop_orders_list", {"customer_id": "cus_b"})
