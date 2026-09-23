# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
MCP bridge (extra ``[mcp]``).

Exposes Charter tools over the Model Context Protocol, so any MCP client — Claude
Desktop, an IDE, another agent — can call them.

Each tool's LLM view becomes the MCP ``inputSchema``, and ``Tool.ainvoke`` is the
handler. Charter errors become MCP tool errors rather than crashing the server, so a
failed call is something the client can read and retry.

    from charter.adapters.mcp import serve
    from charter.packs import gmail

    serve(gmail.TOOLS, name="gmail")

Or from the command line, which reads credentials from the environment::

    python -m charter.mcp --pack gmail

Written against the mcp 2.x server API (``MCPServer``); mcp 1.x had a different
low-level surface and is not supported.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from charter.discovery import SEARCH_TOOL_NAME
from charter.execution.schema import llm_json_schema
from charter.session import ToolSession, ToolsLike, view_of
from charter.types.errors import CharterError

__all__ = ["build_server", "serve", "serve_async"]

_INSTALL_HINT = (
    "The MCP adapter needs the mcp package. Install it with: pip install 'charter-ai[mcp]'"
)


def _require_mcp():
    try:
        import mcp.types as types
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.exceptions import ToolError
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(_INSTALL_HINT) from exc
    return MCPServer, types, ToolError


def _render(result: Any) -> str:
    """Render a tool result as text for an MCP content block."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)


def build_server(
    tools: ToolsLike,
    name: str = "charter",
    *,
    progressive: bool = False,
) -> Any:
    """Build an MCP server exposing ``tools``.

    Returned unstarted, so it can be driven directly in a test or run over any
    transport the caller likes. :func:`serve` runs it over stdio.

    Pass a :class:`~charter.session.ToolSession` and schemas are sent on demand.
    MCP is the surface where that costs nothing: the server holds the session,
    ``tools/list`` reports what is currently loaded, and a load emits
    ``notifications/tools/list_changed`` so the client re-lists on its own. The
    client sees plain tools appear, needing no cooperation and no knowledge that
    anything was deferred.

    A plain iterable publishes every schema, exactly as it does through the
    OpenAI and LangChain adapters. One rule across all four surfaces beats a
    per-surface default, even a good one: ``build_server(gmail.TOOLS)`` and
    ``to_openai_tools(gmail.TOOLS)`` should not quietly mean different things.
    :func:`serve` and ``python -m charter.mcp`` build the session for you, so the
    server people actually run is progressive by default.

    One server holds one session, which is right for stdio — one process, one
    client — but not for a single HTTP server shared between clients, where what
    one loads the next would see. Build a server per session there.
    """
    MCPServer, types, ToolError = _require_mcp()

    # `<pack>__<tool>`, always. A host composes `mcp__<server>__<tool>` on top,
    # taking `<server>` from the key the server was *configured under* rather
    # than the name reported here, so the result reads
    # `mcp__charter__gcalendar__events_list` — each segment a different fact.
    #
    # Which is why one server should hold every pack you want: configured under
    # `charter` the whole composed name peaks at 61 of the 64 a function name may
    # occupy, but a server per pack configured under `charter-gsheets` spells the
    # pack twice for eight more characters and puts three gsheets names over.
    # docs/using/mcp.mdx configures one server; tests/test_naming.py measures it.
    #
    # Qualified even for one pack, so that adding a second never renames the
    # first. Bare names also collided outright: stripe and shopify both declare
    # `products_list`, and this server listed 23 tools while routing 21, sending
    # two of them to the wrong tool.
    session = (
        tools if isinstance(tools, ToolSession) else ToolSession(tools, progressive=progressive)
    )

    class _CharterServer(MCPServer):
        """An MCPServer whose tools are Charter Tools.

        ``list_tools`` / ``call_tool`` are overridden rather than registering
        through ``add_tool``: that builds its schema by introspecting a Python
        signature, and the whole point here is that the schema is already
        declared, as Pydantic.
        """

        # Set below; annotated here so the class documents what it holds.
        session: Optional[ToolSession] = None

        async def list_tools(self) -> List[Any]:
            return [
                types.Tool(
                    name=entry_name,
                    description=(
                        entry["description"]
                        if isinstance(entry, dict)
                        else (entry.description or entry_name)
                    ),
                    input_schema=(
                        entry["parameters"]
                        if isinstance(entry, dict)
                        else llm_json_schema(entry.llm_schema())
                    ),
                )
                for entry_name, entry in view_of(session)
            ]

        async def call_tool(
            self,
            name: str,
            arguments: Dict[str, Any],
            context: Optional[Any] = None,
        ) -> Any:
            loaded_before = len(session.loaded)
            try:
                result = await session.dispatch(name, arguments or {})
            except CharterError as exc:
                # The library's errors are already written to be read, so pass
                # the message through rather than a generic failure. A
                # CredentialError's documentation link comes with it on purpose:
                # over MCP the reader of a setup failure is whoever configured
                # the server, and the page is what they need next.
                raise ToolError(str(exc)) from exc

            if name == SEARCH_TOOL_NAME and len(session.loaded) != loaded_before:
                await _announce(context)

            return types.CallToolResult(
                content=[types.TextContent(type="text", text=_render(result))]
            )

    # Charter's version, not the pack's: `serverInfo` identifies the software
    # answering the protocol, and a client that reports a misbehaving server
    # needs to name a release. Left unset it is the empty string, which is what
    # every `--pack` server reported before. Imported here rather than at module
    # scope because `charter/__init__` is what pulls this package's siblings in.
    from charter import __version__

    server = _CharterServer(name=name, version=__version__)
    server.session = session
    return server


async def _announce(context: Optional[Any]) -> None:
    """Tell the client the tool list grew.

    Best-effort by design. A client that never subscribed, or one on a transport
    with nowhere to push, is not an error: it re-lists on its own schedule and
    the loaded tools are there when it does. Failing the call that *worked*
    because the courtesy notification did not would be the wrong trade.
    """
    if context is None:
        return
    try:
        await context.session.send_tool_list_changed()
    except Exception:  # pragma: no cover - transport-dependent
        pass


def _served(tools: ToolsLike) -> ToolSession:
    """What a served server holds: a session, progressive by its own default.

    This is where the default lives rather than in :func:`build_server`, which
    stays a literal projection like its sister adapters. Serving is the entry
    point a person runs, one process to one stdio client, which is exactly the
    shape progressive disclosure needs.
    """
    return tools if isinstance(tools, ToolSession) else ToolSession(tools)


async def serve_async(tools: ToolsLike, name: str = "charter") -> None:
    """Run the MCP server over stdio until the client disconnects."""
    await build_server(_served(tools), name=name).run_stdio_async()


def serve(tools: ToolsLike, name: str = "charter") -> None:
    """Run the MCP server over stdio (blocking)."""
    import anyio

    anyio.run(serve_async, _served(tools), name)
