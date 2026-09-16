"""
The scenario contract.

A scenario is five things, and the split between them is the point:

- ``seed`` puts namespaced fixtures into the real accounts and returns the
  ground truth (``Expected``) — the ids, values and counts a correct run must
  end with. Network.
- ``prompt`` is the task the user would type. It names what needs doing, not
  which tools to call.
- ``observe`` reads the world back after the agent has finished — through the
  world clients, never through the agent's transcript — and returns an
  ``Observed``. Network.
- ``judge`` compares ``Expected`` to ``Observed`` and says CORRECT or INCORRECT,
  with the reason. **Pure**: no network, no clock, no randomness. That is what
  makes it testable offline, which is what makes the not-vacuous check possible.
- ``teardown`` removes what ``seed`` created. Network.

Plus two hooks for the test that keeps every judge honest: ``example`` returns a
hand-written (expected, observed) pair the judge must accept, and
``wrong_observations`` returns at least two deliberately wrong observations —
each with the reason it is wrong — that the judge must reject.

A scenario is also a template. ``defaults`` names the knobs it exposes (fixture
data, counts, distractors) with their phase-1 values, and ``variants`` maps a
variant name to the overrides that define it; ``register`` instantiates every
variant as ``<id>@<variant>``. Seeds and prompts read ``self.params``; judges
read only ``expected``, so one judge — and one not-vacuous test — serves every
variant of a template.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from charter_harness.world import World

__all__ = ["Expected", "Observed", "Verdict", "Scenario", "norm", "check"]

Expected = dict[str, Any]
Observed = dict[str, Any]


@dataclass(frozen=True)
class Verdict:
    correct: bool
    explanation: str

    @classmethod
    def ok(cls, explanation: str = "matches the expected end state") -> Verdict:
        return cls(True, explanation)

    @classmethod
    def fail(cls, explanation: str) -> Verdict:
        return cls(False, explanation)


def norm(value: Any) -> str:
    """Case, surrounding whitespace and internal runs of whitespace do not count."""
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip().casefold()


def check(conditions: Iterable[tuple[bool, str]]) -> Verdict:
    """CORRECT if every condition holds; otherwise INCORRECT naming what failed."""
    failures = [reason for ok, reason in conditions if not ok]
    if failures:
        return Verdict.fail("; ".join(failures))
    return Verdict.ok()


class Scenario(ABC):
    """One task, end to end. Subclasses set ``id``, ``packs``, ``summary``."""

    id: str
    packs: tuple[str, ...]
    summary: str = ""
    # Providers the seed/observe/teardown need beyond the packs the model gets
    # (a scrape target hosted on GitHub, say). Empty for most scenarios.
    seed_only: tuple[str, ...] = ()
    # Parametric knobs and the named variants built from them (phase 3).
    defaults: dict[str, Any] = {}
    variants: dict[str, dict[str, Any]] = {}

    def __init__(self, variant: str = "", **overrides: Any) -> None:
        cls = type(self)
        unknown = sorted(set(overrides) - set(cls.defaults))
        if unknown:
            raise TypeError(f"{cls.id}: unknown parameter(s) {unknown}; knobs are {sorted(cls.defaults)}")
        self.template: str = cls.id
        self.variant: str = variant
        self.params: dict[str, Any] = {**cls.defaults, **overrides}
        if variant:
            self.id = f"{cls.id}@{variant}"

    @property
    def requires(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self.packs + self.seed_only))

    def instances(self) -> list[Scenario]:
        """This template and every declared variant of it, base first."""
        cls = type(self)
        out: list[Scenario] = [self]
        out.extend(cls(variant=name, **overrides) for name, overrides in cls.variants.items())
        return out

    # ---- network

    @abstractmethod
    async def seed(self, world: World, ns: str) -> Expected: ...

    @abstractmethod
    async def observe(self, world: World, ns: str, expected: Expected) -> Observed: ...

    @abstractmethod
    async def teardown(self, world: World, ns: str, expected: Expected) -> None: ...

    # ---- pure

    @abstractmethod
    def prompt(self, ns: str, expected: Expected) -> str: ...

    @abstractmethod
    def judge(self, expected: Expected, observed: Observed) -> Verdict: ...

    @abstractmethod
    def example(self) -> tuple[Expected, Observed]: ...

    @abstractmethod
    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]: ...

    # ---- conveniences

    def owned(self, expected: Expected) -> dict[str, Sequence[str]]:
        """Identifiers the guard should treat as this run's own. Default: the
        ``owned`` key the seed may have put in ``expected``."""
        return dict(expected.get("owned", {}))

    def __repr__(self) -> str:
        return f"<Scenario {self.id} packs={list(self.packs)}>"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for name, overrides in cls.variants.items():
            unknown = sorted(set(overrides) - set(cls.defaults))
            if unknown:
                raise TypeError(f"{cls.id}@{name}: unknown parameter(s) {unknown}; knobs are {sorted(cls.defaults)}")
