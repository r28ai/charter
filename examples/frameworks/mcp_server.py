# Needs `pip install "charter-ai[mcp]"`, and FIRECRAWL_API_KEY once a client calls a tool.
"""Serve Charter tools over MCP, to Claude Desktop, an IDE, or another agent.

A shipped pack needs no code at all:
`uvx --from 'charter-ai[mcp]' charter-mcp --pack gmail`
"""

import asyncio

from charter.adapters.mcp import build_server, serve
from charter.packs import firecrawl


def build():
    # firecrawl reads $FIRECRAWL_API_KEY on first use; firecrawl.configure(api_key=...)
    # supplies it explicitly instead.
    return build_server(firecrawl.TOOLS, name="firecrawl")


async def describe() -> None:
    """Show what an MCP client would see, without starting a transport."""
    for tool in await build().list_tools():
        fields = ", ".join(tool.input_schema.get("properties", {}))
        print(f"{tool.name:24} ({fields})")


if __name__ == "__main__":
    asyncio.run(describe())

    # Then serve it over stdio (blocks until the client disconnects):
    serve(firecrawl.TOOLS, name="firecrawl")
