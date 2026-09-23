"""
Every scenario module in this package, found by name and registered once.

A module registers by calling :func:`register` on an instance at import time;
:func:`load_all` imports every ``s??_*.py`` module so the registry is complete
without a hand-maintained list. Registering a template also registers each of
its declared variants as ``<template>@<variant>``.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from charter_harness.scenarios.base import Scenario

__all__ = ["SCENARIOS", "register", "load_all", "all_scenarios", "templates", "by_id", "select"]

SCENARIOS: dict[str, Scenario] = {}
_LOADED = False


def register(scenario: Scenario) -> Scenario:
    for instance in scenario.instances():
        if instance.id in SCENARIOS and SCENARIOS[instance.id].template != instance.template:
            raise ValueError(f"two scenarios registered as {instance.id!r}")
        SCENARIOS[instance.id] = instance
    return scenario


def load_all() -> dict[str, Scenario]:
    global _LOADED
    if not _LOADED:
        import charter_harness.scenarios as package

        for info in pkgutil.iter_modules(package.__path__):
            if info.name[:1] == "s" and info.name[1:3].isdigit():
                importlib.import_module(f"{package.__name__}.{info.name}")
        _LOADED = True
    return SCENARIOS


def all_scenarios(*, variants: bool = False) -> list[Scenario]:
    """The templates (phase 1/2), or every instance including variants (phase 3)."""
    load_all()
    chosen = [SCENARIOS[k] for k in sorted(SCENARIOS)]
    return chosen if variants else [s for s in chosen if not s.variant]


def templates() -> list[Scenario]:
    return all_scenarios(variants=False)


def by_id(scenario_id: str) -> Scenario:
    load_all()
    try:
        return SCENARIOS[scenario_id]
    except KeyError:
        raise KeyError(f"unknown scenario {scenario_id!r}; known: {sorted(SCENARIOS)}") from None


def select(
    spec: str | None, *, available: Iterable[str] | None = None, variants: bool = False
) -> list[Scenario]:
    """``"all"`` / ``None``, a comma-separated list of ids, or a pack name.

    An id may name a template (``linear_triage``) or one variant
    (``linear_triage@six``). With ``variants=True`` a template or pack name
    expands to the template and all its variants. With ``available`` (a set of
    configured providers), scenarios needing a provider that is not configured
    are dropped rather than failing at seed.
    """
    load_all()
    if not spec or spec == "all":
        chosen = all_scenarios(variants=variants)
    else:
        parts = [p.strip() for p in spec.split(",") if p.strip()]
        chosen = []
        for part in parts:
            if part in SCENARIOS:
                named = SCENARIOS[part]
                if named.variant:  # one explicit variant
                    chosen.append(named)
                else:  # a template: itself, plus its variants when asked for
                    chosen.extend(s for s in all_scenarios(variants=variants) if s.template == part)
            else:
                matching = [s for s in all_scenarios(variants=variants) if part in s.packs]
                if not matching:
                    raise KeyError(f"{part!r} is neither a scenario id nor a pack name")
                chosen.extend(matching)
    if available is not None:
        avail = set(available)
        chosen = [s for s in chosen if set(s.requires) <= avail]
    seen = set()
    unique = []
    for s in chosen:
        if s.id not in seen:
            seen.add(s.id)
            unique.append(s)
    return unique
