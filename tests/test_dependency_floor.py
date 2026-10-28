"""The floors pyproject.toml declares are the versions CI's `floor` job installs.

`pydantic>=2.9` stood while nothing ran against 2.9, and on everything before
2.12.3 a field marked `WireName` refused its own wire name. A floor is a claim
that the library works there, so CI installs exactly it and runs the suite. This
keeps the two from drifting apart: raise a floor in one place and not the other,
and this fails, offline, before either is wrong in a release.
"""

from __future__ import annotations

import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:  # 3.10 predates tomllib
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CORE = ("pydantic", "httpx")


def _declared_floors() -> dict[str, str]:
    spec = tomllib.loads((ROOT / "pyproject.toml").read_text())
    floors = {}
    for line in spec["project"]["dependencies"]:
        requirement = Requirement(line)
        lower = [s.version for s in requirement.specifier if s.operator == ">="]
        floors[requirement.name] = lower[0] if lower else ""
    return floors


def _floor_job() -> str:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    match = re.search(r"^  floor:\n(.*?)(?=^  \S)", workflow, re.S | re.M)
    assert match, "ci.yml has no `floor` job"
    return match.group(1)


def test_every_core_dependency_declares_a_floor():
    floors = _declared_floors()
    assert set(floors) == set(CORE)
    assert all(floors.values()), floors


def test_the_floor_job_installs_exactly_the_declared_floors():
    job = _floor_job()
    installed = {name: Version(v) for name, v in re.findall(r'"(pydantic|httpx)==([\d.]+)"', job)}
    assert installed == {name: Version(v) for name, v in _declared_floors().items()}


def test_the_floor_job_runs_on_the_oldest_python():
    spec = tomllib.loads((ROOT / "pyproject.toml").read_text())
    oldest = spec["project"]["requires-python"].removeprefix(">=")
    assert f"uv python install {oldest}" in _floor_job()
    assert f"uv venv --python {oldest}" in _floor_job()
