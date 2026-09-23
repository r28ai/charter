"""
Serve Charter tools over the Model Context Protocol.

Any MCP client — Claude Desktop, an IDE, another agent — can then call them.
Each tool's LLM view becomes the MCP inputSchema.

Run with:
    pip install 'charter-ai[mcp]'
    FIRECRAWL_API_KEY=... python examples/mcp_server.py

Or serve a shipped pack without writing any code at all:
    python -m charter.mcp --pack gmail
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
