"""
``ToolSession.dispatch`` hands its client through to the tool.

``Tool.ainvoke`` has always taken ``client``, so a loop you drive yourself can
hold one connection pool open instead of paying a TLS handshake per call. A
session sat in the middle of that and dropped the argument, so anyone routing
through ``dispatch`` — which is every OpenAI-loop and MCP user — could not reach
it. These pin that it arrives, and that omitting it still opens one per call.

The shared client is identified by a header only it carries: a request that
arrives without the header was made by a client this test did not create.
"""

from __future__ import annotations

from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import Path, ToolSession, api_key_tool_factory

BASE = "https://api.example.com/"
MARK = "x-shared-client"

factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "k"}, pack="demo")


class Args(BaseModel):
    item_id: Annotated[str, Path()]


read_item = factory(
    name="read_item",
    description="Read one item.",
    method="GET",
    url_template="v1/items/{item_id}",
    args_schema=Args,
)


def shared(name: str = "shared") -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={MARK: name})


def marks(route) -> list[Optional[str]]:
    return [call.request.headers.get(MARK) for call in route.calls]


@pytest.fixture
def route():
    with respx.mock:
        yield respx.get(f"{BASE}v1/items/abc").mock(
            return_value=httpx.Response(200, json={"id": "abc"})
        )


@pytest.fixture
def session():
    return ToolSession([read_item], progressive=False)


async def test_dispatch_passes_the_client_through(route, session):
    async with shared() as http:
        await session.dispatch("demo__read_item", {"item_id": "abc"}, client=http)
        await session.dispatch("demo__read_item", {"item_id": "abc"}, client=http)
    assert marks(route) == ["shared", "shared"]


async def test_dispatch_without_a_client_opens_its_own(route, session):
    await session.dispatch("demo__read_item", {"item_id": "abc"})
    assert marks(route) == [None]


async def test_dispatch_does_not_close_a_client_it_did_not_open(route, session):
    async with shared() as http:
        await session.dispatch("demo__read_item", {"item_id": "abc"}, client=http)
        assert not http.is_closed
    assert http.is_closed


async def test_the_client_is_keyword_only(route, session):
    """Positional would collide with a tool argument named `client`."""
    with pytest.raises(TypeError):
        async with shared() as http:
            await session.dispatch("demo__read_item", {"item_id": "abc"}, http)  # type: ignore[misc]


async def test_search_ignores_the_client_without_complaining(route):
    """ToolSearch makes no request, so a client passed alongside it is inert."""
    deferred = ToolSession([read_item])
    async with shared() as http:
        result = await deferred.dispatch(
            "ToolSearch", {"query": "select:demo__read_item"}, client=http
        )
    assert "demo__read_item" in result
    assert marks(route) == []
