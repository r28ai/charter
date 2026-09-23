"""
The arm protocol, and the registry the task looks arms up in by name.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from charter_harness.settings import Wiring

__all__ = ["Arm", "ARMS", "arm_by_name"]


class Arm(Protocol):
    """One tool surface. ``tools`` is called once per sample with the scenario's packs."""

    name: str

    # The return may hold a ToolSource as well as ToolDefs: the progressive arm
    # grows its tool list as tools are loaded, and Inspect re-resolves a
    # ToolSource on every turn of the react loop.
    def tools(self, packs: Sequence[str], wiring: Wiring) -> list[Any]: ...


ARMS: dict[str, Arm] = {}


def register(arm: Arm) -> Arm:
    ARMS[arm.name] = arm
    return arm


def arm_by_name(name: str) -> Arm:
    # Import the concrete arms lazily so that importing the registry never pulls
    # in the raw arm's httpx client or the Charter packs before settings exist.
    #
    # Keyed on the arm actually asked for, not on the registry being empty: any
    # module that imports one arm directly registers it, and a check for
    # emptiness would then skip the import that registers the others.
    if name not in ARMS:
        import charter_harness.arms.charter_arm  # noqa: F401
        import charter_harness.arms.progressive_arm  # noqa: F401
        import charter_harness.arms.raw_arm  # noqa: F401

    try:
        return ARMS[name]
    except KeyError:
        raise ValueError(f"unknown arm {name!r}; known arms: {sorted(ARMS)}") from None
