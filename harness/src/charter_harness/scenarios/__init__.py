"""
The scenario corpus.

Each ``sNN_<name>.py`` module defines one :class:`~charter_harness.scenarios.base.Scenario`
and registers it. See :mod:`charter_harness.scenarios.base` for the contract and
:mod:`charter_harness.scenarios.registry` for lookup.
"""

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import (
    all_scenarios,
    by_id,
    load_all,
    register,
    select,
    templates,
)

__all__ = [
    "Expected",
    "Observed",
    "Scenario",
    "Verdict",
    "check",
    "norm",
    "all_scenarios",
    "by_id",
    "load_all",
    "register",
    "select",
    "templates",
]
