"""
What one run knows about itself, kept in the sample's Inspect store.

The namespace, the scenario, the arm, the ground truth the seed produced, the
identifiers of everything the seed created (so the guard can tell a delete of a
fixture from a delete of the user's real calendar), and the map from the tool
names the model sees back to (pack, Charter tool).
"""

from __future__ import annotations

import secrets
from typing import Any

from inspect_ai.util import StoreModel, store_as
from pydantic import Field

__all__ = ["RunContext", "run_context", "mint_namespace"]


def mint_namespace() -> str:
    """A short tag unique enough for concurrent runs against one account."""
    return "h" + secrets.token_hex(3)


class RunContext(StoreModel):
    ns: str = ""
    scenario: str = ""
    arm: str = ""
    packs: list[str] = Field(default_factory=list)
    expected: dict[str, Any] = Field(default_factory=dict)
    # True once the seed returned; a run whose seed failed is a harness error,
    # never the model's failure, and must not be graded as one.
    seeded: bool = False
    seed_error: str = ""
    # kind -> identifiers the seed created, e.g. {"gcalendar.event": [...ids]}
    owned: dict[str, list[str]] = Field(default_factory=dict)
    # tool name the model sees -> [pack, charter tool name]
    tool_index: dict[str, list[str]] = Field(default_factory=dict)
    github_owner: str = ""

    def own(self, kind: str, *identifiers: str) -> None:
        current = dict(self.owned)
        current[kind] = list(current.get(kind, [])) + [str(i) for i in identifiers]
        self.owned = current

    def owns(self, kind: str, identifier: Any) -> bool:
        return str(identifier) in set(self.owned.get(kind, []))


def run_context() -> RunContext:
    return store_as(RunContext)
