"""
Credential injection.

Charter never acquires or stores credentials. The host application owns that; this
module is the seam between the two.

A :class:`CredentialProvider` is anything with an async ``get_credentials``.
:class:`StaticTokenProvider`, :class:`EnvTokenProvider` and
:class:`CallbackProvider` cover a token you already hold;
:class:`~charter.auth.OAuth2Client` renews one against a token endpoint; and
:class:`SubjectProvider` puts any of those behind an end-user identity. Anything
else — a secrets manager, a broker — is a class of your own satisfying the same
protocol.

Refreshing is not the same as storing. ``OAuth2Client`` holds an access token in
memory for the seconds it is valid and writes it nowhere; persisting it is the
host's, through ``on_refresh``.

When a token is missing or rejected the runtime raises
:class:`~charter.types.errors.CredentialError` rather than interrupting or
re-authenticating on its own — the host decides what happens next.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import (
    Awaitable,
    Callable,
    Dict,
    Iterator,
    Optional,
    Protocol,
    Union,
    runtime_checkable,
)

from pydantic import BaseModel

from charter.types.errors import CredentialError

__all__ = [
    "Credentials",
    "CredentialProvider",
    "StaticTokenProvider",
    "EnvTokenProvider",
    "CallbackProvider",
    "SubjectProvider",
    "current_subject",
    "use_subject",
]


class Credentials(BaseModel):
    """A bearer token, and optionally when it stops being valid."""

    token: str
    expires_at: Optional[datetime] = None

    def is_expired(self, leeway_seconds: int = 0) -> bool:
        """Whether the token is past ``expires_at`` (minus ``leeway_seconds``).

        Credentials with no ``expires_at`` never report expired — the caller has
        not told us when they lapse, so we assume they are valid and let the API
        be the judge.

        Naive datetimes are read as UTC, so a provider that hands back a naive
        timestamp is not accidentally treated as far-future or far-past.
        """
        if self.expires_at is None:
            return False

        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
        return remaining <= leeway_seconds


@runtime_checkable
class CredentialProvider(Protocol):
    """Supplies credentials for a named provider.

    ``provider`` is the identifier the tool was built with (e.g. ``"google"``),
    so one implementation can serve several APIs.
    """

    async def get_credentials(self, provider: str) -> Credentials:
        ...


class StaticTokenProvider:
    """Hands back one token, unchanged, for every provider.

    The right choice for a script, a test, or any place you already hold a
    valid access token.
    """

    def __init__(self, token: str, *, expires_at: Optional[datetime] = None) -> None:
        if not token:
            raise CredentialError("StaticTokenProvider was given an empty token")
        self._credentials = Credentials(token=token, expires_at=expires_at)

    async def get_credentials(self, provider: str) -> Credentials:
        return self._credentials

    def __repr__(self) -> str:
        return "StaticTokenProvider(token=***)"


class EnvTokenProvider:
    """Reads the token from an environment variable on every call.

    Re-read per call on purpose: a sidecar that refreshes the variable is picked
    up without restarting the process.
    """

    def __init__(self, var_name: str) -> None:
        if not var_name:
            raise CredentialError("EnvTokenProvider requires an environment variable name")
        self.var_name = var_name

    async def get_credentials(self, provider: str) -> Credentials:
        token = os.environ.get(self.var_name)
        if not token:
            raise CredentialError(
                f"Environment variable {self.var_name!r} is unset or empty",
                provider=provider,
                docs="auth/your-own-account",
            )
        return Credentials(token=token)

    def __repr__(self) -> str:
        return f"EnvTokenProvider(var_name={self.var_name!r})"


class CallbackProvider:
    """Delegates to a function of your own — sync or async.

    The hook for a credential store of your own::

        async def fetch(provider: str) -> Credentials:
            row = await db.tokens.get(provider)
            return Credentials(token=row.access_token, expires_at=row.expires_at)

        credentials = CallbackProvider(fetch)

    Note what is *not* in scope here: ``provider`` names the API, never the end
    user. One of these serves one identity. For many, see
    :class:`SubjectProvider`; to refresh an OAuth grant rather than read a stored
    token, see :class:`~charter.auth.OAuth2Client`.
    """

    def __init__(
        self,
        fn: Callable[[str], Union[Credentials, Awaitable[Credentials]]],
    ) -> None:
        if not callable(fn):
            raise CredentialError("CallbackProvider requires a callable")
        self._fn = fn

    async def get_credentials(self, provider: str) -> Credentials:
        result = self._fn(provider)
        if isinstance(result, Credentials):
            return result
        return await result

    def __repr__(self) -> str:
        name = getattr(self._fn, "__name__", repr(self._fn))
        return f"CallbackProvider({name})"


# -----------------------------------------------------
# Serving many end users
# -----------------------------------------------------

current_subject: ContextVar[str] = ContextVar("charter_current_subject")
"""Who the next tool call acts for.

``get_credentials(provider)`` names the API, not the person, because the runtime
has no business knowing there is a person. When an application serves many end
users, the identity has to reach the credential lookup somehow, and every
alternative is worse: rebuilding a tool set per request throws away the schemas,
and threading a ``subject=`` argument through every adapter means a LangChain
shim, an ADK shim, and one for each framework after that.

So it travels out of band, and — this is the part that matters — it is read by
your *provider*, never by the runtime. The executor still calls
``get_credentials(name)`` and knows nothing else. Ambient state stays out of the
boundary; it lives one layer out, in an object you own.

A ContextVar is per-task in asyncio, so concurrent requests sharing one set of
tools cannot see each other's subject.
"""


@contextmanager
def use_subject(subject: str) -> Iterator[str]:
    """Set :data:`current_subject` for the duration of a block::

        with use_subject(request.user_id):
            await agent.ainvoke(...)

    Resets on the way out, including on an exception, so a failed request cannot
    leave its identity behind for the next one.
    """
    if not subject:
        raise CredentialError("use_subject requires a non-empty subject")
    token = current_subject.set(subject)
    try:
        yield subject
    finally:
        current_subject.reset(token)


class SubjectProvider:
    """One credential provider per end user, resolved per call.

    Give it a factory that builds a provider for a subject — typically reading
    that user's refresh token from your database and returning an
    :class:`~charter.auth.OAuth2Client`::

        async def for_user(subject: str) -> CredentialProvider:
            row = await db.grants.get(subject, "google")
            return OAuth2Client(GOOGLE, client_id=..., client_secret=...,
                                refresh_token=row.refresh_token,
                                on_refresh=partial(save, subject))

        gmail.configure(credential_provider=SubjectProvider(for_user))

    Built providers are kept, capped at ``max_subjects`` and evicted
    least-recently-used, so a long-lived server does not accumulate one per user
    it has ever seen. Because each provider carries its own cached token *and*
    its own refresh lock, eviction removes both together — there is no second
    structure keyed by subject growing quietly beside this one.

    Two limits worth knowing:

    *Not thread-safe.* Resolution is a read, an ``move_to_end`` and sometimes an
    insert; that sequence is not atomic across threads. One of these belongs to
    one event loop. Concurrency *within* a loop is handled — a cold start is
    single-flighted, so twelve simultaneous calls for one subject read your token
    store once.

    *Eviction during a refresh, against a server that rotates.* If a subject is
    evicted while its refresh is in flight and then looked up again, the rebuilt
    provider reads whatever your store holds — which is the old refresh token if
    ``on_refresh`` has not landed yet, and a rotating server has already
    invalidated it. Reaching this needs ``max_subjects`` distinct other users
    between the start and end of one refresh, so the default of 1000 makes it
    remote; if you serve more concurrent users than that and your provider
    rotates, raise the cap rather than tuning around it.
    """

    def __init__(
        self,
        factory: Callable[[str], Union[CredentialProvider, Awaitable[CredentialProvider]]],
        *,
        max_subjects: int = 1000,
    ) -> None:
        if not callable(factory):
            raise CredentialError("SubjectProvider requires a callable factory")
        if max_subjects < 1:
            raise ValueError("max_subjects must be at least 1")
        self._factory = factory
        self._max_subjects = max_subjects
        self._providers: OrderedDict[str, CredentialProvider] = OrderedDict()
        # Cold starts in flight, so twelve concurrent calls for one user do not
        # become twelve reads of your token store. Entries are removed in a
        # `finally`, so this is bounded by concurrent misses rather than by the
        # number of subjects ever seen — it cannot become a second structure
        # growing quietly beside the capped one.
        self._pending: Dict[str, asyncio.Future[CredentialProvider]] = {}

    async def get_credentials(self, provider: str) -> Credentials:
        subject = self.current()
        return await (await self._provider_for(subject)).get_credentials(provider)

    def current(self) -> str:
        """The subject for this call, or an error naming what to do about it.

        Never falls back to a default or to whoever went last. Acting as the
        wrong principal is the one failure a boundary layer cannot ship, so an
        unset subject is loud.
        """
        try:
            return current_subject.get()
        except LookupError:
            raise CredentialError(
                "No subject is set for this call, so Charter does not know whose "
                "credentials to use. Wrap the call in `with use_subject(user_id):` "
                "or call charter.auth.current_subject.set(user_id).",
                docs="reference/credentials#subjectprovider",
            ) from None

    async def _provider_for(self, subject: str) -> CredentialProvider:
        existing = self._providers.get(subject)
        if existing is not None:
            self._providers.move_to_end(subject)
            return existing

        in_flight = self._pending.get(subject)
        if in_flight is not None:
            # Someone is already building this one. Wait for theirs rather than
            # starting a second read of the token store — and share the result,
            # so both callers get one cached token and one refresh lock.
            return await asyncio.shield(in_flight)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[CredentialProvider] = loop.create_future()
        self._pending[subject] = future
        try:
            built = self._factory(subject)
            if inspect.isawaitable(built):
                built = await built
            if built is None:
                raise CredentialError(
                    f"SubjectProvider's factory returned no provider for subject "
                    f"{subject!r}.",
                    docs="reference/credentials#subjectprovider",
                )
            self._providers[subject] = built
            if len(self._providers) > self._max_subjects:
                self._providers.popitem(last=False)
            if not future.done():
                future.set_result(built)
            return built
        except BaseException as exc:
            # Waiters must fail the same way rather than hanging, and the next
            # caller gets a clean attempt.
            if not future.done():
                future.set_exception(exc)
            raise
        finally:
            self._pending.pop(subject, None)
            # A future nobody awaited is not an error; say so, or asyncio warns
            # at collection time about an exception that was in fact delivered.
            if future.done() and not future.cancelled():
                future.exception()

    def forget(self, subject: str) -> None:
        """Drop a subject's provider — after a revocation, or a sign-out."""
        self._providers.pop(subject, None)

    def __len__(self) -> int:
        return len(self._providers)

    def __repr__(self) -> str:
        return (
            f"SubjectProvider(subjects={len(self._providers)}, "
            f"max_subjects={self._max_subjects})"
        )
