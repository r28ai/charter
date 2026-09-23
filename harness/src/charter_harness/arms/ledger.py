"""
What the model's tool calls cost, per sample, for either arm.

Inspect already records every tool call in its transcript. The ledger exists
for the numbers the transcript does not carry in a comparable form across arms:
how many bytes each call fed back into the context, whether the call reached
the network, what the outcome class was, and how many times the guard said no.

It lives in the sample's Inspect ``Store`` (via :class:`StoreModel`), which is
the framework's own per-sample scope — reachable from inside a tool call, from
the scorer, and from the log afterwards. Nothing here is a global.
"""

from __future__ import annotations

from typing import Any

from charter.observability import ToolCall
from inspect_ai.util import StoreModel, store_as
from pydantic import Field

__all__ = ["Ledger", "ledger", "record_charter_call", "record_raw_call"]


class Ledger(StoreModel):
    """Per-sample tool-call accounting, shared by both arms."""

    arm: str = ""
    calls: list[dict[str, Any]] = Field(default_factory=list)
    guard_rejections: list[dict[str, Any]] = Field(default_factory=list)
    truncations: int = 0

    # ---- derived, for the scorer's metadata ----

    @property
    def tool_calls(self) -> int:
        return len(self.calls)

    @property
    def tool_errors(self) -> int:
        return sum(1 for c in self.calls if c.get("outcome") != "ok")

    @property
    def context_bytes(self) -> int:
        return sum(int(c.get("context_bytes") or 0) for c in self.calls)

    @property
    def payload_bytes(self) -> int:
        return sum(int(c.get("payload_bytes") or 0) for c in self.calls)

    def summary(self) -> dict[str, Any]:
        outcomes: dict[str, int] = {}
        for c in self.calls:
            outcomes[c.get("outcome", "?")] = outcomes.get(c.get("outcome", "?"), 0) + 1
        return {
            "arm": self.arm,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "outcomes": outcomes,
            "context_bytes": self.context_bytes,
            "payload_bytes": self.payload_bytes,
            "guard_rejections": len(self.guard_rejections),
            "truncations": self.truncations,
        }


def ledger() -> Ledger:
    """The current sample's ledger (a process-wide one outside of an eval)."""
    return store_as(Ledger)


def record_charter_call(call: ToolCall) -> None:
    """``on_call`` sink for the Charter arm: one :class:`ToolCall` in, one row out."""
    led = ledger()
    led.calls = led.calls + [
        {
            "tool": call.tool,
            "provider": call.provider,
            "outcome": call.outcome,
            "status_code": call.status_code,
            "error_type": call.error_type,
            "reached_network": call.reached_network,
            "total_ms": round(call.total_ms, 1),
            "upstream_ms": round(call.upstream_ms, 1),
            "payload_bytes": call.payload_bytes,
            "context_bytes": call.context_bytes,
        }
    ]


def record_raw_call(
    *,
    tool: str,
    provider: str,
    method: str,
    path: str,
    status_code: int | None,
    ok: bool,
    total_ms: float,
    payload_bytes: int | None,
    context_bytes: int | None,
    truncated: bool,
    error_type: str | None = None,
) -> None:
    """The raw arm's equivalent row. ``payload_bytes`` is what the API sent,
    ``context_bytes`` what reached the model after the cap."""
    led = ledger()
    if truncated:
        led.truncations = led.truncations + 1
    led.calls = led.calls + [
        {
            "tool": tool,
            "provider": provider,
            "method": method,
            "path": path,
            "outcome": "ok" if ok else (error_type or "http_error"),
            "status_code": status_code,
            "error_type": error_type,
            "reached_network": status_code is not None,
            "total_ms": round(total_ms, 1),
            "upstream_ms": round(total_ms, 1),
            "payload_bytes": payload_bytes,
            "context_bytes": context_bytes,
            "truncated": truncated,
        }
    ]
