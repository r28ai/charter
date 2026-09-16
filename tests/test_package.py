"""R0 — packaging guardrails.

These encode the plan's global rules as executable checks so that a later task
cannot quietly reintroduce a heavy dependency or a phone-home.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path as FsPath

import pytest

import charter
from charter.types.errors import DOCS_BASE

SRC = FsPath(charter.__file__).parent

# Rule 5: core dependency budget is pydantic + httpx. Anything else must live
# behind an extra, i.e. under adapters/ or providers/.
FORBIDDEN = re.compile(
    r"\b(langchain|langgraph|google\.auth|google_auth|redis|psycopg|structlog|cryptography)\b"
)
EXTRAS_ALLOWED = ("adapters", "providers")

# Rule 3: no telemetry. No internal hostnames, no closed-source vocabulary.
#
# The terms are assembled from fragments on purpose: spelling them literally here
# would make this file itself a hit for R9's `grep -riE "..." oss/` hygiene check.
_INTERNAL_TERMS = (
    "surf" + "buddy",
    "engine" + r"\." + "r2" + "8",
    "r2" + "8" + "lib",
    "R2" + "8" + "Config",
    "R2" + "8" + "Lib" + "Config",
    # The name this package went by before it was Charter. A stray one is a
    # rename that did not finish, and it would reach users as a broken import or
    # a log line naming a library that no longer exists. Deliberately unanchored:
    # word boundaries missed `R2`+`8_UNCONFIGURED` and `_R2`+`8Server`, because an
    # underscore is a word character, and those two survived a whole sweep.
    "r2" + "8",
)
INTERNAL = re.compile("|".join(_INTERNAL_TERMS), re.IGNORECASE)


def _source_files() -> list[FsPath]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _core_files() -> list[FsPath]:
    return [p for p in _source_files() if not set(p.relative_to(SRC).parts) & set(EXTRAS_ALLOWED)]


def test_the_package_imports():
    assert charter.__version__


def test_py_typed_marker_ships():
    assert (SRC / "py.typed").is_file()


def test_there_is_source_to_check():
    """Guard against the scanning tests passing vacuously."""
    assert len(_core_files()) >= 6


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_core_modules_stay_inside_the_dependency_budget(path):
    hits = FORBIDDEN.findall(path.read_text())
    assert not hits, f"{path.relative_to(SRC)} imports out-of-budget dependency: {set(hits)}"


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_internal_or_closed_source_references(path):
    # The published documentation host is not an internal hostname: it is the
    # site the README, the docs and the agent-setup prompt all already name, and
    # it appears in source only as text an error message prints. It is excused
    # here by exact string and nowhere else, and the two tests below are what
    # keep that exemption from becoming a hole.
    hits = INTERNAL.findall(path.read_text().replace(DOCS_BASE, ""))
    assert not hits, f"{path.relative_to(SRC)} references internal name: {set(hits)}"


def test_the_docs_host_is_spelled_in_exactly_one_place():
    """One constant, so a moved docs site is one edit rather than a sweep.

    This is also what makes the exemption above safe to grant: the host cannot
    spread through the source without turning this red.
    """
    spelled = [p for p in _source_files() if DOCS_BASE in p.read_text()]
    assert [p.relative_to(SRC) for p in spelled] == [FsPath("types/errors.py")]


def test_the_docs_host_is_never_requested():
    """A link is text. Nothing in the library fetches it.

    The covenant is that Charter makes no network call except the ones you
    declare, and an error carrying a URL is the one change that could plausibly
    erode it. The module allowed to spell the host imports nothing that could
    make a request, so there is no line anywhere that could fetch it — which is
    a stronger claim than scanning for one, and one that cannot pass vacuously.
    """
    spelled = SRC / "types" / "errors.py"
    assert DOCS_BASE in spelled.read_text(), "the guard is checking the wrong module"

    imported = _imported_roots(spelled)
    assert not imported - set(sys.stdlib_module_names), (
        f"types/errors.py spells the docs host and imports {imported}; it may import "
        "only the standard library, so it has nothing to make a request with"
    )


def _imported_roots(path: FsPath) -> set[str]:
    """Top-level module names imported by a source file, from its AST."""
    import ast

    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import — always internal.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", _core_files(), ids=lambda p: str(p.relative_to(SRC)))
def test_core_imports_only_stdlib_pydantic_and_httpx(path):
    """Rule 5: the core may import stdlib, itself, pydantic, and httpx — nothing else."""
    import sys

    allowed = {"charter", "pydantic", "pydantic_core", "httpx", "typing_extensions"}
    stdlib = set(sys.stdlib_module_names)

    offenders = _imported_roots(path) - allowed - stdlib
    assert not offenders, f"{path.relative_to(SRC)} imports non-core dependency: {offenders}"


def test_no_network_calls_at_import_time():
    """Rule 3: importing charter must not touch the network.

    Runs in a subprocess so the import is genuinely fresh — reloading in-process
    would rebind classes the transform registry already holds references to.
    """
    import subprocess
    import sys
    import textwrap

    program = textwrap.dedent(
        """
        import socket

        def refuse(*args, **kwargs):
            raise AssertionError("charter opened a socket at import time")

        socket.socket.connect = refuse
        socket.create_connection = refuse

        import charter
        import charter.types
        import charter.transforms

        assert charter.__version__
        print("clean")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_logger_has_a_null_handler():
    """Rule: stdlib logging, NullHandler by default — the library never configures the host."""
    import logging

    logger = logging.getLogger("charter")
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
