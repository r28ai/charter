"""Docs-consistency tests collect only where the docs they read exist.

The sdist ships `src/`, `tests/` and `examples/` but not `docs/`, `scripts/`
or `skills/` — see `[tool.hatch.build.targets.sdist]` in pyproject.toml. The
modules below are repo hygiene: they assert the published pages still agree
with the code, which is a claim about this checkout, not about whether the
library works. A distro packager building from the tarball has nothing for
them to read, and without this hook they raise FileNotFoundError during
collection — a failure that reads as "charter is broken on your platform"
when it means "you do not have the docs". In the repo every path below is
present, nothing is ignored, and the full suite runs as before.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each module against the trees it reads from outside tests/ and src/.
_READS = {
    "test_doc_figures.py": ("docs",),
    "test_measured_results.py": ("docs", "harness"),
    "test_docs_oauth.py": ("docs", "scripts"),
    "test_error_docs.py": ("docs",),
    "test_landing_docs.py": ("docs",),
    "test_pack_docs.py": ("docs", "scripts"),
    "test_pack_specs.py": ("docs", "scripts"),
    "test_readme.py": ("docs", "skills", "AGENTS.md"),
    "test_reference_docs.py": ("docs", "scripts"),
}

collect_ignore = [
    module
    for module, required in _READS.items()
    if not all((ROOT / path).exists() for path in required)
]
