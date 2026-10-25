"""How much tool schema each layer hands the model, for the same operations.

No model, no API call beyond listing tools. For every operation the same-calls
benchmark sends (``same_calls/run.py``), the definition each layer gives the model:
Charter's ``Tool.to_json_schema()``, the MCP server's ``tools/list`` entry (name,
description, input schema) and, where the benchmark's account connects, Composio's
tool (name, description, input parameters). Then each whole surface: every tool of
the Charter pack, every tool the MCP server lists at its quickstart configuration.

Bytes of compact JSON, which is what reaches the model's context; at roughly four
bytes a token. This is a published loss, not a win: Charter's declarations carry
the vendor's whole contract, and that costs context.

    cd harness && CHARTER_HARNESS_ENV=... .venv/bin/python bench/schema_size.py

Writes ``results/bench/schema_size.json`` and ``results/bench/schema_size.md``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "same_calls"))
from charter.packs import gcalendar, github, gmail, linear, slack, stripe  # noqa: E402
from mcp_layer import connect  # noqa: E402
from servers import _env, servers  # noqa: E402

OUT = HERE.parent / "results" / "bench"
COMPOSIO = "https://backend.composio.dev/api/v3/tools"

# (operation, Charter tool, MCP server, MCP tool, Composio tool), as in same_calls/run.py.
PAIRS = [
    ("Slack: add a reaction", slack.reactions_add, "slack", "reactions_add", None),
    ("Slack: post a message", slack.chat_post_message, "slack", "conversations_add_message", None),
    ("Linear: update an issue", linear.issue_update, "linear", "save_issue", None),
    ("Linear: comment on an issue", linear.comment_create, "linear", "save_comment", None),
    (
        "Gmail: update a label",
        gmail.labels_patch,
        "google",
        "manage_gmail_label",
        "GMAIL_PATCH_LABEL",
    ),
    (
        "Gmail: list messages",
        gmail.messages_list,
        "google",
        "search_gmail_messages",
        "GMAIL_FETCH_EMAILS",
    ),
    (
        "Gmail: create a draft",
        gmail.drafts_create,
        "google",
        "draft_gmail_message",
        "GMAIL_CREATE_EMAIL_DRAFT",
    ),
    ("Calendar: list events", gcalendar.events_list, "google", "get_events", None),
    (
        "GitHub: list a repository's issues",
        github.issues_list_for_repo,
        "github",
        "list_issues",
        None,
    ),
    ("Stripe: list customers", stripe.customers_list, "stripe", "stripe_api_read", None),
]
PACKS = {"slack": slack, "linear": linear, "google": None, "github": github, "stripe": stripe}


def size(obj: Any) -> int:
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode())


def mcp_entry(tool: Any) -> dict[str, Any]:
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.input_schema}


async def composio_entry(http: httpx.AsyncClient, slug: str) -> dict[str, Any]:
    r = await http.get(f"{COMPOSIO}/{slug}", headers={"x-api-key": _env("COMPOSIO_API_KEY")})
    r.raise_for_status()
    d = r.json()
    return {
        "name": d["slug"],
        "description": d.get("description"),
        "parameters": d.get("input_parameters"),
    }


async def main() -> None:
    from charter_harness.settings import load, wire_packs

    wire_packs(load(), frozenset({"gmail", "gcalendar", "slack", "github", "linear", "stripe"}))
    srv = servers(slack_channels=["C0C03BZL5TQ"])
    listed: dict[str, list[Any]] = {}
    async with AsyncExitStack() as stack, httpx.AsyncClient(timeout=60) as http:
        for name in sorted({p[2] for p in PAIRS}):
            session = await stack.enter_async_context(connect(srv[name]))
            listed[name] = (await session.list_tools()).tools
        rows = []
        for op, ctool, server, mtool, comp in PAIRS:
            m = next(t for t in listed[server] if t.name == mtool)
            row = {
                "operation": op,
                "charter": {"tool": ctool.name, "bytes": size(ctool.to_json_schema())},
                "mcp": {"server": srv[server].name, "tool": mtool, "bytes": size(mcp_entry(m))},
            }
            if comp:
                row["composio"] = {"tool": comp, "bytes": size(await composio_entry(http, comp))}
            rows.append(row)
    surfaces = []
    for name, tools in listed.items():
        charter_tools = [*gmail.TOOLS, *gcalendar.TOOLS] if name == "google" else PACKS[name].TOOLS
        surfaces.append(
            {
                "api": "Gmail and Calendar" if name == "google" else name.title(),
                "mcp": {
                    "server": srv[name].name,
                    "tools": len(tools),
                    "bytes": size([mcp_entry(t) for t in tools]),
                },
                "charter": {
                    "tools": len(charter_tools),
                    "bytes": size([t.to_json_schema() for t in charter_tools]),
                },
            }
        )
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "schema_size.json").write_text(
        json.dumps({"operations": rows, "surfaces": surfaces}, indent=2)
    )
    lines = [
        "### The same operation",
        "",
        "| operation | Charter | MCP server | Composio |",
        "|---|---:|---:|---:|",
    ]
    for r in rows:
        comp = f"{r['composio']['bytes']:,}" if "composio" in r else ""
        lines.append(
            f"| {r['operation']} | {r['charter']['bytes']:,} | {r['mcp']['bytes']:,} "
            f"(`{r['mcp']['tool']}`) | {comp} |"
        )
    lines += [
        "",
        "### The whole surface",
        "",
        "| API | Charter tools | Charter bytes | MCP server | its tools | its bytes |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for s in surfaces:
        lines.append(
            f"| {s['api']} | {s['charter']['tools']} | {s['charter']['bytes']:,} | "
            f"{s['mcp']['server']} | {s['mcp']['tools']} | {s['mcp']['bytes']:,} |"
        )
    text = "\n".join(lines) + "\n"
    (OUT / "schema_size.md").write_text(text)
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
