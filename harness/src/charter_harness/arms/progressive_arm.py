"""
The Charter arm with :class:`~charter.session.ToolSession` in front of it.

The mechanism this arm was built to test now lives in the SDK — see
:mod:`charter.discovery` for what it does and why it is shaped that way. What is
left here is the Inspect binding, which is the one part that cannot be in core:
Inspect re-resolves a :class:`~inspect_ai.tool.ToolSource` on every turn of the
react loop, and that is what lets the list grow.

A loaded tool is ``charter_tooldef(...)``, the same object the Charter arm hands
over, so the two arms stay comparable and the guard sees identical calls.

The arm keeps ``threshold`` as a constructor argument and forces
``progressive=True``: the benchmark exists to measure the mechanism, so it runs
even on a scenario whose packs are small enough that core would turn it off.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from charter.discovery import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_THRESHOLD,
    SEARCH_TOOL_NAME,
    parse_query,
    rank,
    schema_tokens,
)
from charter.session import ToolSession
from inspect_ai.tool import Tool, ToolDef, ToolParams
from inspect_ai.util import JSONSchema

from charter_harness.arms.base import register
from charter_harness.arms.charter_arm import charter_tooldef, model_facing_names, pack_tools
from charter_harness.context import run_context
from charter_harness.settings import Wiring

# Re-exported so the arm reads as one surface and its tests keep naming one
# module. The implementations are core's.
__all__ = [
    "DEFAULT_THRESHOLD",
    "DEFAULT_MAX_RESULTS",
    "SEARCH_TOOL_NAME",
    "parse_query",
    "rank",
    "schema_tokens",
    "Catalogue",
    "ProgressiveArm",
]


class Catalogue:
    """A :class:`ToolSession` as an Inspect ``ToolSource``.

    Inspect calls :meth:`tools` once per turn, so what this returns is what the
    model sees next: resident tools, then ``ToolSearch`` while anything is still
    deferred, then whatever has been loaded, in load order. An unloaded tool is
    absent from it.
    """

    def __init__(self, session: ToolSession, names: dict[str, str]) -> None:
        self.session = session
        # qualified name -> the name this arm publishes. The two are the same
        # today; kept explicit so the arm, not core, owns what the model reads.
        self.names = names

    @property
    def deferrable(self):
        """The tools whose schemas are not loaded, by name."""
        return self.session.deferrable

    @property
    def resident(self):
        """The tools whose schemas are always sent."""
        return self.session.resident

    @property
    def loaded(self) -> list[str]:
        """What ``ToolSearch`` has loaded, in load order."""
        return self.session.loaded

    def catalogue_text(self) -> str:
        """Every deferrable tool, by name, one per line."""
        return "\n".join(sorted(self.session.deferrable))

    def _search_tooldef(self) -> ToolDef:
        definition = self.session.search_definition()

        async def ToolSearch(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:  # noqa: N802
            import json

            return json.dumps(self.session.search(query, max_results), ensure_ascii=False)

        return ToolDef(
            ToolSearch,
            name=SEARCH_TOOL_NAME,
            description=definition["description"],
            parameters=ToolParams(
                properties={
                    name: JSONSchema.model_validate(schema)
                    for name, schema in definition["parameters"]["properties"].items()
                },
                required=list(definition["parameters"]["required"]),
                additionalProperties=False,
            ),
            max_output=0,
        )

    async def tools(self) -> list[Tool]:
        session = self.session
        out: list[Tool] = [
            charter_tooldef(tool, name=name).as_tool() for name, tool in session.resident.items()
        ]
        if session.offers_search():
            out.append(self._search_tooldef().as_tool())
        for name in session.loaded:
            out.append(charter_tooldef(session.deferrable[name], name=name).as_tool())
        return out


class ProgressiveArm:
    """The Charter arm with large schemas loaded on demand."""

    name = "progressive"

    def __init__(self, threshold: int = DEFAULT_THRESHOLD) -> None:
        self.threshold = threshold

    def tools(self, packs: Sequence[str], wiring: Wiring) -> list[Any]:
        names = model_facing_names(packs)
        tools = [tool for pack in packs for tool in pack_tools(pack)]
        index = {
            names[(tool.pack or pack, tool.name)]: [pack, tool.name]
            for pack in packs
            for tool in pack_tools(pack)
        }

        session = ToolSession(tools, progressive=True, threshold=self.threshold)

        ctx = run_context()
        ctx.arm = self.name
        # Every tool the guard may see, loaded or not: the index maps a call back
        # to its pack, and a tool loaded three turns from now still needs checking.
        ctx.tool_index = index

        if not session.deferrable:
            # ToolDefs, like the Charter arm: with nothing deferred there is no
            # ToolSource to re-resolve and the two arms are the same list.
            return [charter_tooldef(t, name=n) for n, t in session.resident.items()]
        return [Catalogue(session, {n: n for n in session.tools})]


register(ProgressiveArm())
