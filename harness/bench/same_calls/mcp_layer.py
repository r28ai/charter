"""The MCP servers the same calls are sent through, pinned, and a client for them.

Each server is the most-starred one for its API on GitHub on 2026-10-24, or the
vendor's own where there is one. Each is run at its quickstart configuration, with
the harness's test credentials, and only the tools a case calls are used.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


@dataclass(frozen=True)
class Server:
    name: str
    why: str
    command: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Result:
    """What the layer handed back: whether it flagged an error, and its text."""

    is_error: bool
    text: str


@asynccontextmanager
async def connect(server: Server) -> AsyncIterator[ClientSession]:
    if server.url:
        http = create_mcp_http_client(headers=server.headers)
        async with http, streamable_http_client(server.url, http_client=http) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return
    params = StdioServerParameters(
        command=server.command[0],
        args=server.command[1:],
        env={**os.environ, **server.env},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call(session: ClientSession, tool: str, arguments: dict[str, Any]) -> Result:
    try:
        out = await session.call_tool(tool, arguments)
    except Exception as exc:  # a protocol-level refusal is an error the caller sees
        return Result(True, f"{type(exc).__name__}: {exc}")
    text = "\n".join(
        getattr(c, "text", json.dumps(getattr(c, "model_dump", dict)())) for c in out.content
    )
    return Result(bool(out.is_error), text)
