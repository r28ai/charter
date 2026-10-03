"""The MCP adapter's prompts, instructions and server-answered tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pytest

from charter import CredentialError
from charter.packs import stripe

pytest.importorskip("mcp", reason="needs the [mcp] extra")

from charter.adapters.mcp import build_server  # noqa: E402


@dataclass(frozen=True)
class Brief:
    name: str = "weekly_brief"
    title: str = "Weekly brief"
    description: str = "What changed this week."

    def render(self, details: str = "") -> str:
        return "Summarise the week." + (f" Focus: {details}" if details else "")


@dataclass
class Status:
    name: str = "status"
    description: str = "Say which credentials this server holds."
    read_only: bool = True
    fail: bool = False

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def call(self, arguments: Dict[str, Any]) -> str:
        if self.fail:
            raise CredentialError("nothing configured")
        return "stripe: configured"


async def test_a_prompt_is_listed_with_one_optional_argument_and_renders_it():
    server = build_server([stripe.balance_retrieve], prompts=[Brief()])
    [prompt] = await server.list_prompts()
    assert (prompt.name, prompt.title) == ("weekly_brief", "Weekly brief")
    assert [(a.name, a.required) for a in prompt.arguments] == [("details", False)]
    result = await server.get_prompt("weekly_brief", {"details": "billing"})
    assert result.messages[0].content.text == "Summarise the week. Focus: billing"


def test_instructions_are_what_the_server_opens_with():
    assert (
        build_server([], instructions="Stripe is connected.").instructions == "Stripe is connected."
    )
    assert build_server([]).instructions is None


async def test_a_server_answered_tool_is_listed_after_the_pack_tools_and_called_in_process():
    server = build_server([stripe.balance_retrieve], local_tools=[Status()])
    listed = await server.list_tools()
    assert [t.name for t in listed] == ["stripe_balance_retrieve", "status"]
    assert listed[1].annotations.read_only_hint is True
    result = await server.call_tool("status", {})
    assert result.content[0].text == "stripe: configured"


async def test_a_charter_error_from_a_server_answered_tool_reaches_the_client_as_text():
    from mcp.server.mcpserver.exceptions import ToolError

    server = build_server([], local_tools=[Status(fail=True)])
    with pytest.raises(ToolError, match="nothing configured"):
        await server.call_tool("status", {})
