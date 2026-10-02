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

import pytest

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
    "test_setup_docs.py": ("docs", "scripts"),
}

collect_ignore = [
    module
    for module, required in _READS.items()
    if not all((ROOT / path).exists() for path in required)
]


# A live test asserts a pack against a real provider. When the provider will not
# serve us — the key expired, the plan ran out, the rate limit hit — the test has
# learned nothing about the pack, and failing says something untrue about this
# checkout. Contributors run these on their own free-tier keys, which run dry
# sooner than ours; CI already excludes `-m live`, and this is the second guard.

_UNAVAILABLE_STATUSES = frozenset(
    {
        401,  # key rejected or expired
        402,  # payment required
        403,  # key lacks the plan or scope
        429,  # rate limited
        432,  # Tavily: "exceeds your plan's set usage limit"
    }
)

_UNAVAILABLE_PHRASES = (
    "usage limit",
    "quota",
    "rate limit",
    "too many requests",
    "expired",
    "invalid api key",
    "insufficient credits",
)


def _provider_unavailable(exc: BaseException) -> str | None:
    """Why this is the provider's state rather than the pack's behaviour."""
    from charter.types.errors import APIError, CredentialError

    if not isinstance(exc, (APIError, CredentialError)):
        return None

    status = getattr(exc, "status_code", None)
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    lowered = first_line.lower()

    if status in _UNAVAILABLE_STATUSES or any(p in lowered for p in _UNAVAILABLE_PHRASES):
        return f"provider unavailable (status {status}): {first_line[:120]}"
    return None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """Turn "the provider said no" into a skip, for live tests only.

    Scoped to the marker deliberately. Offline tests that raise a credential
    error have found a real bug, and swallowing that would hide it.
    """
    try:
        return (yield)
    except Exception as exc:
        if item.get_closest_marker("live") is not None:
            reason = _provider_unavailable(exc)
            if reason:
                pytest.skip(reason)
        raise


# A developer's shell may hold a real Google grant — this repository's own .env
# names one. Every Google pack now renews from those variables before it reads
# $GOOGLE_ACCESS_TOKEN, so without this a test that sets a fake access token
# would quietly refresh against Google instead, and only on that machine.
@pytest.fixture(autouse=True)
def _no_google_grant_from_the_machine(monkeypatch):
    from charter.packs._google import ENV_GRANT

    monkeypatch.delenv("GOOGLE_TOKEN_FILE", raising=False)
    monkeypatch.delenv("GOOGLE_REFRESH_TOKEN", raising=False)
    ENV_GRANT.reset()
    yield
    ENV_GRANT.reset()
