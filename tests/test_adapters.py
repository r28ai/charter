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
    assert [t["function"]["name"] for t in tools] == [f"gmail_{t.name}" for t in gmail.TOOLS]


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
    assert [t.name for t in listed] == [f"firecrawl_{t.name}" for t in firecrawl.TOOLS]
    for t in listed:
        assert t.input_schema["type"] == "object"
        assert t.description


def test_every_listed_tool_says_whether_it_writes():
    """Codex runs a tool marked read-only without asking, and asks before the rest.

    Unannotated, every Charter tool was a write to it, and `codex exec` — which
    cannot ask — refused `gmail_messages_list`. The method is the one fact the
    server is sure of, so it is the only one claimed.
    """
    import anyio

    from charter.adapters.mcp import build_server
    from charter.session import ToolSession

    async def listed(tools):
        return {t.name: t.annotations for t in await build_server(tools).list_tools()}

    gmail_tools = anyio.run(listed, gmail.TOOLS)
    by_method = {f"gmail_{t.name}": t.method.upper() for t in gmail.TOOLS}
    assert {"GET", "POST", "DELETE"} <= set(by_method.values())
    for name, hints in gmail_tools.items():
        method = by_method[name]
        assert hints is not None, name
        assert hints.read_only_hint is (method == "GET"), name
        if method == "DELETE":
            assert hints.destructive_hint is True, name
        elif method != "GET":
            assert hints.destructive_hint is None, name  # a POST may only search

    search = anyio.run(listed, ToolSession(gmail.TOOLS, progressive=True))["ToolSearch"]
    assert search.read_only_hint is True and search.open_world_hint is False


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
                    await low.run(server_read, server_write, low.create_initialization_options())

                tg.start_soon(run_server)

                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()

                    listed = await session.list_tools()
                    names = [t.name for t in listed.tools]
                    assert "firecrawl_scrape" in names

                    result = await session.call_tool(
                        "firecrawl_scrape", {"url": "https://example.com"}
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
                    lambda: low.run(server_read, server_write, low.create_initialization_options())
                )
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "firecrawl_scrape", {"url": "https://example.com"}
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


def test_the_charter_mcp_command_is_the_module_entry_point():
    """Client configs name `charter-mcp`, so it must be `main` and not a copy of it."""
    from importlib.metadata import entry_points

    from charter.mcp import main

    (script,) = entry_points(group="console_scripts", name="charter-mcp")
    assert script.load() is main


def test_one_server_can_hold_several_packs():
    """The shape the setup page recommends, and the reason tool names fit.

    One server means one entry in the client config, so a host composes
    `mcp__charter__<pack>_<tool>` instead of `mcp__charter-<pack>__<pack>_<tool>`
    — the pack once rather than twice, which is eight characters of a
    64-character budget that belong to the pack author rather than to us. It is
    what lets the server keep the product's own name; see tests/test_naming.py.
    """
    from charter.mcp import load_pack, resolve_packs

    assert resolve_packs(["gmail", "gsheets"]) == ["gmail", "gsheets"]
    assert resolve_packs(["gmail,gsheets,stripe"]) == ["gmail", "gsheets", "stripe"]
    # Repeated, comma-separated and padded all arrive the same way, and a pack
    # named twice is loaded once.
    assert resolve_packs(["gmail,gsheets", "gmail", " stripe "]) == [
        "gmail",
        "gsheets",
        "stripe",
    ]

    names = resolve_packs(["gmail,gsheets"])
    tools = [t for n in names for t in load_pack(n)]
    assert len(tools) == len(load_pack("gmail")) + len(load_pack("gsheets"))
    assert all(isinstance(t, Tool) for t in tools)


def test_several_packs_are_one_toolsearch_not_several():
    """Discovery does not pay for the packs being together: ToolSearch spans them."""
    from charter.mcp import load_pack, resolve_packs
    from charter.session import ToolSession

    names = resolve_packs(["gmail,gsheets,stripe"])
    tools = [t for n in names for t in load_pack(n)]
    session = ToolSession(tools, progressive=True)

    assert len(session.tools) == len(tools)  # nothing collided away
    assert len(to_openai_tools(session)) == 1  # ...and it costs one definition


def test_an_unknown_pack_in_a_list_names_itself():
    from charter.mcp import resolve_packs

    with pytest.raises(ValueError, match="invalid pack: 'nope'"):
        resolve_packs(["gmail,nope"])

    with pytest.raises(ValueError, match="at least one pack"):
        resolve_packs([","])


@pytest.mark.parametrize(
    "argv",
    [
        [],  # no --pack at all
        ["--pack"],  # the flag with nothing after it
        ["--pack", "nope"],  # a pack that does not exist
        ["--pack", "gmail,nope"],  # one good, one not
        ["--pack", ""],  # empty string
    ],
)
def test_a_bad_pack_argument_is_a_usage_error_not_a_crash(argv):
    """Exit 2, the code argparse uses for every other usage mistake.

    `choices=PACKS` gave this for free until `--pack` learned to take a list and
    the validation moved into `resolve_packs`, which exited 1 instead — the same
    mistake reported two different ways depending on which half caught it.
    """
    from charter.mcp import main

    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2


def _served_session(monkeypatch, argv):
    """What `python -m charter.mcp` would serve, captured instead of run."""
    import charter.adapters.mcp as mcp_adapter
    from charter.mcp import main

    served = {}
    monkeypatch.setattr(mcp_adapter, "serve", lambda session, name: served.update(session=session))
    assert main(argv) == 0
    return served["session"]


def test_the_entry_point_sends_every_schema_by_default(monkeypatch):
    """The one shape every client handles.

    Loading on demand relies on the client re-listing when told the list
    changed. Codex logs the notification and keeps the list it started with,
    and ADK reads the list once per turn, so a progressive default left tools
    out of reach on both.
    """
    from charter.mcp import load_pack

    session = _served_session(monkeypatch, ["--pack", "gmail"])
    assert not session.progressive
    assert len(to_openai_tools(session)) == len(load_pack("gmail"))


def test_progressive_is_an_opt_in(monkeypatch):
    session = _served_session(monkeypatch, ["--pack", "gmail", "--progressive"])
    assert session.progressive
    assert [t["function"]["name"] for t in to_openai_tools(session)] == ["ToolSearch"]


def test_the_old_no_progressive_flag_still_parses(monkeypatch):
    """A client config written for 0.2.5, when it was the way to get every schema."""
    session = _served_session(monkeypatch, ["--pack", "gmail", "--no-progressive"])
    assert not session.progressive


def test_serve_publishes_a_plain_list_whole(monkeypatch):
    """`serve` follows `build_server`: an iterable is every schema, a session is on demand."""
    import charter.adapters.mcp as mcp_adapter

    built = {}

    class _Server:
        async def run_stdio_async(self):
            return None

    def fake_build(tools, name="charter", **_):
        built["tools"] = tools
        return _Server()

    monkeypatch.setattr(mcp_adapter, "build_server", fake_build)
    mcp_adapter.serve(gmail.TOOLS)
    assert built["tools"] is gmail.TOOLS
