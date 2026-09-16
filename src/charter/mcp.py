"""
``python -m charter.mcp --pack gmail`` — serve a shipped pack over MCP.

Credentials come from the environment, so nothing has to be written down:

- Google packs (gmail, gcalendar, gsheets, gdocs, gdrive) read ``$GOOGLE_ACCESS_TOKEN``
- slack reads ``$SLACK_BOT_TOKEN``
- github reads ``$GITHUB_TOKEN``
- stripe reads ``$STRIPE_API_KEY``
- linear reads ``$LINEAR_API_KEY``
- shopify reads ``$SHOPIFY_SHOP`` and ``$SHOPIFY_ACCESS_TOKEN`` — it needs
  both, since its host is a property of the store
- firecrawl reads ``$FIRECRAWL_API_KEY``
- notion reads ``$NOTION_API_KEY``
- tavily reads ``$TAVILY_API_KEY``
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import List

from charter.tool import Tool

PACKS = (
    "gmail",
    "gcalendar",
    "gsheets",
    "gdocs",
    "gdrive",
    "gforms",
    "slack",
    "github",
    "stripe",
    "linear",
    "shopify",
    "firecrawl",
    "notion",
    "granola",
    "tavily",
)


def load_pack(name: str) -> List[Tool]:
    """Import a shipped pack and return its tools.

    The packs read their credentials from the documented environment variables
    on first use, so no configure() call is needed here.
    """
    if name not in PACKS:
        raise SystemExit(f"Unknown pack {name!r}. Choose one of: {', '.join(PACKS)}")
    module = importlib.import_module(f"charter.packs.{name}")
    return list(module.TOOLS)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m charter.mcp",
        description="Serve a Charter pack over the Model Context Protocol (stdio).",
    )
    parser.add_argument("--pack", required=True, choices=PACKS, help="Which pack to serve.")
    parser.add_argument("--name", default="charter", help="Server name (default: charter).")
    parser.add_argument(
        "--no-progressive",
        dest="progressive",
        action="store_false",
        help=(
            "Send every tool schema up front instead of loading them on demand. "
            "Use with a client that ignores notifications/tools/list_changed."
        ),
    )
    args = parser.parse_args(argv)

    tools = load_pack(args.pack)

    from charter.adapters.mcp import serve
    from charter.session import ToolSession

    session = ToolSession(tools, progressive=args.progressive)
    how = " (schemas on demand via ToolSearch)" if session.progressive else ""
    print(
        f"charter: serving {len(tools)} {args.pack} tools over MCP (stdio){how}",
        file=sys.stderr,
    )
    serve(session, name=args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
