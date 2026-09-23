"""Live validation: the packs, against the real APIs, with no model in the loop.

The offline suite in ``oss/tests`` proves a declaration is self-consistent. It
cannot prove the provider agrees with it: a field Stripe renamed, an enum value
Shopify dropped, a filter GitHub ignores rather than rejects. Every one of those
passes a respx mock and fails in production.

The scenario harness catches them, but it drives an agent, so it costs inference
and it only exercises whatever tools the model happened to choose. These call the
tools directly with hardcoded arguments. Every tool gets exercised, every run
costs nothing but the provider's own rate limit, and a failure names one endpoint
rather than one scenario.

Deselected by default, because the rest of the suite is offline by rule::

    cd oss/harness
    .venv/bin/python -m pytest tests/live -m live            # all providers
    .venv/bin/python -m pytest tests/live -m live -k stripe  # one

A provider without credentials skips rather than fails: partial wiring is the
normal state of a checkout, and a red suite that means "you did not configure
Shopify" trains people to ignore it. The same goes for a scope the token was not
granted — the ``scope_skip`` fixture turns the provider's own refusal into a skip that
names what to add, because "your Shopify token cannot read orders" is
configuration, not a broken pack.

What a test may assert is bounded by what the pack's response handler keeps. A
PaymentIntent's ``capture_method`` is trimmed away, so no test reads it back;
the manual-capture tests prove the flag arrived by the *behaviour* it caused —
``requires_capture`` rather than ``succeeded``. Asserting through the trim is the
stricter test anyway: it is what the agent sees.

Everything created here is named with a per-run tag and deleted on the way out,
through the world clients rather than through the packs.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from charter.types.errors import CharterError

from charter_harness.settings import Settings, Wiring, load, wire_packs
from charter_harness.world import World


@pytest.fixture(scope="session")
def run_tag() -> str:
    """A short id stamping everything this run creates, so leftovers are traceable."""
    return f"lv{uuid.uuid4().hex[:6]}"


@pytest.fixture(scope="session")
def settings() -> Settings:
    try:
        return load()
    except Exception as exc:  # pragma: no cover - configuration, not logic
        pytest.skip(f"harness/.env is not loadable: {exc}")


@pytest.fixture(scope="session")
def available(settings: Settings) -> frozenset[str]:
    """Which providers have credentials in this environment."""
    return settings.available()


@pytest.fixture(scope="session", autouse=True)
def wiring(settings: Settings, available: frozenset[str]) -> Wiring:
    """Point the real packs at the real credentials, once."""
    if not available:
        pytest.skip("no provider credentials configured")
    return wire_packs(settings, available)


@pytest.fixture
async def world(wiring: Wiring) -> AsyncIterator[World]:
    """The providers over raw httpx — the harness's own client, not the packs.

    Fixtures and teardown go through here on purpose. Deleting a test's leftovers
    with the tool under test would let a broken delete read as a clean run, and
    several of these objects have no delete tool in the pack at all.

    Function-scoped because each test gets its own event loop and an
    ``httpx.AsyncClient`` may not cross one.
    """
    world = World(wiring)
    try:
        yield world
    finally:
        await world.aclose()


@pytest.fixture
def needs(available: frozenset[str]) -> Callable[..., None]:
    """``needs("stripe")`` skips the test when that provider is unconfigured."""

    def _needs(*providers: str) -> None:
        missing = [p for p in providers if p not in available]
        if missing:
            pytest.skip(f"not configured: {', '.join(missing)}")

    return _needs


@pytest.fixture
def scope_skip() -> Callable[..., None]:
    """``scope_skip(exc, scope="reactions:read")`` — skip when the token is the problem.

    A token granted fewer scopes than the pack covers is a fact about this
    checkout, not a defect in the declaration, and the two must not look alike in
    the output. Anything else — a renamed field, a rejected enum — is the failure
    this suite exists to surface, so it is re-raised untouched.

    Both error types are accepted because providers disagree about which this is.
    Slack reports a missing scope inside a 200 with ``ok: false``, and the pack's
    envelope classifies that code as a credential failure, so it arrives as a
    :class:`CredentialError`; Shopify answers ``ACCESS_DENIED`` in a GraphQL error
    list, and GitHub a plain 403.
    """

    def _scope_skip(exc: CharterError, *, scope: str) -> None:
        detail = getattr(exc, "body", "") or str(exc)
        denied = getattr(exc, "status_code", None) in (401, 403) or "ACCESS_DENIED" in detail
        if not denied:
            raise exc
        pytest.skip(f"the token lacks {scope}: {detail[:200]}")

    return _scope_skip


@pytest.fixture(scope="session")
def github_owner(settings: Settings) -> str:
    owner = settings.github_owner or os.environ.get("GITHUB_OWNER")
    if not owner:
        pytest.skip("GITHUB_OWNER is not set")
    return owner


@pytest.fixture(scope="session")
def sandbox_repo(settings: Settings) -> str:
    """The repository GitHub writes are confined to.

    The harness guard enforces the same prefix on every arm; these tests are not
    under the guard, so the constraint is restated here rather than assumed.
    """
    repo = settings.github_sandbox_repo
    assert repo.startswith("harness-"), f"refusing to write to {repo!r}: not a sandbox"
    return repo


class Trash:
    """Whatever a test made, in the order it has to be undone."""

    def __init__(self) -> None:
        self._undo: list[Callable[[], Awaitable[object]]] = []

    def later(self, undo: Callable[[], Awaitable[object]]) -> None:
        """Register a zero-argument coroutine factory to run during teardown."""
        self._undo.append(undo)

    async def empty(self) -> list[str]:
        """Run every registered undo, newest first. Returns what failed.

        Teardown never raises: one undeletable leftover should not turn a passing
        live check red, and the names come back so a run can report them.
        """
        failures: list[str] = []
        while self._undo:
            undo = self._undo.pop()
            try:
                await undo()
            except Exception as exc:  # pragma: no cover - cleanup is best effort
                failures.append(f"{undo!r}: {exc}")
        return failures


@pytest.fixture
async def trash() -> AsyncIterator[Trash]:
    """Yields a Trash and empties it afterwards, pass or fail.

    Registered on the way in rather than at the end of the test body, so a
    failing assertion still deletes what ran before it.
    """
    bin_ = Trash()
    yield bin_
    failures = await bin_.empty()
    if failures:
        print("\nlive cleanup left behind:\n  " + "\n  ".join(failures))
