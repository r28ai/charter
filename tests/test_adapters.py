"""R5 + R7 — framework adapters: OpenAI, LangChain, MCP.

Each adapter is a projection of a Tool, so these check that the projection is
faithful and that execution still runs through charter.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import EmailContent, Path, Query, Tool
from charter.adapters.openai import to_openai_tool, to_openai_tools
from charter.packs import firecrawl, gmail

BASE = "https://api.example.com/"

langchain_core = pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
mcp = pytest.importorskip("mcp", reason="needs the [mcp] extra")


class GetWeather(BaseModel):
    city: Annotated[str, Path()]
    units: Annotated[Optional[str], Query()] = "metric"


def _tool(**overrides) -> Tool:
    kwargs = dict(
        name="get_current_weather",
        description="Get current weather for a city.",
        method="GET",
        url_template="v1/weather/{city}",
        args_schema=GetWeather,
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
    )
    kwargs.update(overrides)
    return Tool(**kwargs)


# -----------------------------------------------------
# OpenAI
# -----------------------------------------------------


def test_to_openai_tool_shape():
    fn = to_openai_tool(_tool())
    assert fn["type"] == "function"
    assert fn["function"]["name"] == "get_current_weather"
    assert fn["function"]["description"] == "Get current weather for a city."
    assert fn["function"]["parameters"]["type"] == "object"
    assert set(fn["function"]["parameters"]["properties"]) == {"city", "units"}


def test_to_openai_tools_preserves_order():
    tools = to_openai_tools(gmail.TOOLS)
    assert [t["function"]["name"] for t in tools] == [f"gmail__{t.name}" for t in gmail.TOOLS]


def test_openai_definitions_are_json_serialisable():
    """They go over the wire to the model provider — they must serialise."""
    json.dumps(to_openai_tools(gmail.TOOLS))


def test_openai_schema_hides_response_only_fields():
    fn = to_openai_tool(gmail.messages_send)
    body = fn["function"]["parameters"]["$defs"]["Message_LLM"]
    assert "id" not in body["properties"]
    assert "raw" in body["properties"]


# -----------------------------------------------------
# LangChain
# -----------------------------------------------------


def test_to_langchain_returns_a_structured_tool():
    from langchain_core.tools import BaseTool

    from charter.adapters.langchain import to_langchain

    lc = to_langchain(_tool())
    assert isinstance(lc, BaseTool)
    assert lc.name == "get_current_weather"
    assert lc.description == "Get current weather for a city."


def test_langchain_args_schema_is_the_charter_llm_view():
    from charter.adapters.langchain import to_langchain

    tool = _tool()
    assert to_langchain(tool).args_schema is tool.llm_schema()


@respx.mock
async def test_langchain_tool_executes_through_charter():
    from charter.adapters.langchain import to_langchain

    route = respx.get(f"{BASE}v1/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={"temp": 21})
    )

    lc = to_langchain(_tool())
    result = await lc.ainvoke({"city": "Tokyo"})

    assert result == {"temp": 21}
    assert route.calls.last.request.headers["x-api-key"] == "k"


@respx.mock
async def test_langchain_validation_error_is_returned_not_raised():
    """LangChain agents expect a readable tool result, not an exception."""
    from charter.adapters.langchain import to_langchain

    lc = to_langchain(_tool())
    result = await lc.ainvoke({"units": "metric"})  # missing required 'city'

    assert isinstance(result, str)
    assert "city" in result


@respx.mock
async def test_langchain_api_error_is_returned_as_text():
    from charter.adapters.langchain import to_langchain

    respx.get(f"{BASE}v1/weather/Tokyo").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )
    result = await to_langchain(_tool()).ainvoke({"city": "Tokyo"})
    assert "boom" in result


def test_langchain_tools_helper():
    from charter.adapters.langchain import to_langchain_tools

    assert len(to_langchain_tools(gmail.TOOLS)) == len(gmail.TOOLS)


def test_langchain_transformed_field_reaches_the_agent_as_a_semantic_type():
    from charter.adapters.langchain import to_langchain

    lc = to_langchain(gmail.messages_send)
    body = lc.args_schema.model_fields["body"].annotation
    assert body.model_fields["raw"].annotation is EmailContent


# -----------------------------------------------------
# MCP
# -----------------------------------------------------


def test_build_server_lists_every_tool():
    import anyio

    from charter.adapters.mcp import build_server

    server = build_server(firecrawl.TOOLS, name="firecrawl")

    async def go():
        return await server.list_tools()

    listed = anyio.run(go)
    assert [t.name for t in listed] == [f"firecrawl__{t.name}" for t in firecrawl.TOOLS]
    for t in listed:
        assert t.input_schema["type"] == "object"
        assert t.description


async def test_mcp_round_trip_lists_and_calls_a_pack_tool():
    """Drive the server in-process over memory streams, as a client would."""
    import anyio
    from mcp import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from charter.adapters.mcp import build_server

    firecrawl.configure(api_key="fc-test")
    server = build_server(firecrawl.TOOLS, name="firecrawl")
    low = server._lowlevel_server

    with respx.mock:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(200, json={"data": {"markdown": "# Hi"}})
        )

        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:

                async def run_server():
                    await low.run(
                        server_read, server_write, low.create_initialization_options()
                    )

                tg.start_soon(run_server)

                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()

                    listed = await session.list_tools()
                    names = [t.name for t in listed.tools]
                    assert "firecrawl__scrape" in names

                    result = await session.call_tool(
                        "firecrawl__scrape", {"url": "https://example.com"}
                    )
                    assert not result.is_error
                    payload = json.loads(result.content[0].text)
                    assert payload["data"]["markdown"] == "# Hi"

                tg.cancel_scope.cancel()


async def test_mcp_reports_a_failed_call_as_a_tool_error():
    import anyio
    from mcp import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams

    from charter.adapters.mcp import build_server

    firecrawl.configure(api_key="fc-test")
    server = build_server(firecrawl.TOOLS, name="firecrawl")
    low = server._lowlevel_server

    with respx.mock:
        respx.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(503, json={"error": "upstream down"})
        )

        async with create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ):
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    lambda: low.run(
                        server_read, server_write, low.create_initialization_options()
                    )
                )
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "firecrawl__scrape", {"url": "https://example.com"}
                    )
                    assert result.is_error
                    assert "upstream down" in result.content[0].text
                tg.cancel_scope.cancel()


# -----------------------------------------------------
# The `python -m charter.mcp` entry point
# -----------------------------------------------------


def test_mcp_cli_loads_every_pack():
    from charter.mcp import PACKS, load_pack

    for pack in PACKS:
        tools = load_pack(pack)
        assert tools and all(isinstance(t, Tool) for t in tools)


def test_mcp_cli_rejects_an_unknown_pack():
    from charter.mcp import load_pack

    with pytest.raises(SystemExit, match="Unknown pack"):
        load_pack("nope")


def test_mcp_cli_requires_a_pack_argument():
    from charter.mcp import main

    with pytest.raises(SystemExit):
        main([])
