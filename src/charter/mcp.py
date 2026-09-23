# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
``python -m charter.mcp --pack gmail`` — serve shipped packs over MCP.

``--pack`` takes more than one (repeat it, or comma-separate), and one server
holding several is the shape to reach for. It is not only about the config being
shorter: an MCP host composes a tool name from the key the server is *configured
under*, so one server named ``charter`` publishes ``mcp__charter__<pack>__<tool>``
where a server per pack publishes ``mcp__charter-<pack>__<pack>__<tool>`` — the
pack spelled twice, for eight more of the 64 characters a function name is
allowed. ``ToolSearch`` spans everything loaded, so discovery does not suffer
for it.

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

A pack you have no credential for is inert rather than broken, so combining
packs costs nothing: the tool is listed, and calling it raises a
``CredentialError`` naming the variable to set.
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


def resolve_packs(values: List[str]) -> List[str]:
    """``["gmail", "gsheets,stripe"]`` -> ``["gmail", "gsheets", "stripe"]``.

    Repeated and comma-separated both work, because a client config is written
    by hand and neither spelling should be the wrong one. Order is the order
    given, and a pack named twice is loaded once.

    Raises ``ValueError`` rather than exiting, so ``main`` can route it through
    ``parser.error`` and a bad ``--pack`` stays a usage error — exit 2, with the
    usage line — which is what ``choices=PACKS`` gave before this took over the
    validation.
    """
    names: List[str] = []
    for value in values:
        for name in value.split(","):
            name = name.strip()
            if not name:
                continue
            if name not in PACKS:
                raise ValueError(f"invalid pack: {name!r} (choose from {', '.join(PACKS)})")
            if name not in names:
                names.append(name)
    if not names:
        raise ValueError("expected at least one pack name")
    return names


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m charter.mcp",
        description="Serve Charter packs over the Model Context Protocol (stdio).",
    )
    parser.add_argument(
        "--pack",
        action="append",
        required=True,
        metavar="PACK",
        help=(
            "Which pack to serve, one of: " + ", ".join(PACKS) + ". Repeat it, or "
            "comma-separate, to serve several from one server — which is worth "
            "doing: one server is one entry in your client config, one process, "
            "and a ToolSearch that spans the lot, and it keeps the pack out of "
            "the server name so tool names stay short."
        ),
    )
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

    try:
        packs = resolve_packs(args.pack)
    except ValueError as exc:
        parser.error(f"argument --pack: {exc}")
    tools = [tool for name in packs for tool in load_pack(name)]

    from charter.adapters.mcp import serve
    from charter.session import ToolSession

    session = ToolSession(tools, progressive=args.progressive)
    how = " (schemas on demand via ToolSearch)" if session.progressive else ""
    print(
        f"charter: serving {len(tools)} tools from {', '.join(packs)} over MCP (stdio){how}",
        file=sys.stderr,
    )
    serve(session, name=args.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
