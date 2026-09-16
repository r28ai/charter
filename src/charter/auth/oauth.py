"""
OAuth 2.0, declared — no vendor SDK, for any authorization server.

A token endpoint is the same shape everywhere: a form POST that trades a grant
for an access token. What differs between servers is small, finite, and written
down in RFC 8414 — so it is declared, exactly like everything else here, rather
than wrapped in a per-vendor client.

:class:`OAuth2Server` uses the RFC's own field names, which means three things:
an identity admin recognises the declaration, a server that publishes metadata
can fill it in itself, and the enterprise IdP you have never heard of — almost
always Okta, Entra, Auth0, Keycloak or Ping — needs no special support at all.

Three ways to get one, all producing the same frozen declaration::

    # 1. It publishes metadata (most enterprise IdPs, and Google)
    server = await OAuth2Server.discover("https://login.acme-corp.com")

    # 2. It does not — write the three constants
    server = OAuth2Server(
        issuer="https://github.com",
        token_endpoint="https://github.com/login/oauth/access_token",
    )

    # 3. Copy one from docs/auth/authorization-servers.md

Then hold it with your own credentials::

    from charter.auth import OAuth2Client
    from charter.packs import gmail

    gmail.configure(credential_provider=OAuth2Client(
        server,
        client_id=..., client_secret=..., refresh_token=...,
        on_refresh=save_to_db,
    ))

Getting the grant in the first place is protocol too — an authorization URL
(RFC 6749 §4.1.1, PKCE per RFC 7636) and one form POST (§4.1.3) — so
:class:`OAuth2Flow` covers exactly those two steps. What it never covers is
everything between them: the callback route, the session holding ``state`` and
the PKCE verifier, storage and the consent UI belong to your web framework, and
the library holds nothing between ``authorize()`` and ``exchange()``. Nothing
here signs anything either, so JWT-bearer and service-account grants stay out of
scope by the same rule that excludes request signing.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Dict, Literal, Mapping, Optional, Union
from urllib.parse import quote_plus

import httpx

from charter.auth.credentials import Credentials
from charter.types.errors import CredentialError, DeclarationError

__all__ = [
    "OAuth2Server",
    "OAuth2Client",
    "OAuth2Flow",
    "AuthorizationRequest",
    "TokenGrant",
    "TokenEndpointAuthMethod",
    "Grant",
    "scopes_for",
    "states_match",
]

logger = logging.getLogger("charter")

TokenEndpointAuthMethod = Literal["client_secret_post", "client_secret_basic"]
"""How the client authenticates to the token endpoint (RFC 6749 §2.3.1).

``client_secret_post`` puts the credentials in the form body; it is what Google,
GitHub and most APIs expect. ``client_secret_basic`` puts them in an HTTP Basic
header, which the RFC nominally prefers and some servers require.
"""

Grant = Literal["refresh_token", "client_credentials"]
"""The two grants that are a plain form POST.

``refresh_token`` is the agent acting for an end user; ``client_credentials`` is
the agent acting as itself. Every other grant needs either a browser redirect or
a signature, and neither belongs in this library.
"""

_WELL_KNOWN = (
    ".well-known/openid-configuration",
    ".well-known/oauth-authorization-server",
)

_MAX_EXPIRES_IN = 10 * 365 * 24 * 60 * 60  # ten years, in seconds

_DEAD_GRANT_COOLDOWN_SECONDS = 60.0
"""How long a client refuses to retry after the server called the grant dead.

``invalid_grant`` means the refresh token has been revoked or has expired, and no
amount of retrying will change that until a human authorizes again. Without this,
an agent that keeps calling tools turns one revoked user into a stream of
requests against the token endpoint — which rate-limits per *client*, so one
user's dead grant degrades every other user of the same app.

A window rather than a permanent mark, because some servers answer
``invalid_grant`` for transient reasons such as clock skew.
"""


# -----------------------------------------------------
# The server
# -----------------------------------------------------


@dataclass(frozen=True)
class OAuth2Server:
    """An authorization server, in RFC 8414's vocabulary.

    Deliberately few fields. Everything else a server might vary on is either
    detectable at runtime (a rotated refresh token announces itself by being in
    the response) or a property of *your* registration rather than of the
    server (scope, which grant you are using), and guessing those on your
    behalf is how a shipped constant becomes a silent bug.

    ``authorization_endpoint`` is optional: a declaration without one is still a
    perfectly good token-refresh-only server, and :meth:`OAuth2Flow.authorize`
    tells you to add it if you try to start a consent flow against one.

    ``authorization_params`` is the one field discovery can never fill in — it
    is registration and vendor lore, exactly the thing the metadata document
    cannot know. Google is the canonical case: without
    ``{"access_type": "offline", "prompt": "consent"}`` the server returns no
    refresh token, nothing fails, and the integration dies an hour later.
    Writing it on the server declaration puts the lore where the constants live.
    """

    token_endpoint: str
    token_endpoint_auth_method: TokenEndpointAuthMethod = "client_secret_post"
    issuer: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    authorization_params: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.token_endpoint:
            raise DeclarationError(
                "OAuth2Server requires a token_endpoint",
                docs="auth/authorization-servers",
            )
        if self.token_endpoint_auth_method not in (
            "client_secret_post",
            "client_secret_basic",
        ):
            raise DeclarationError(
                "token_endpoint_auth_method must be 'client_secret_post' or "
                f"'client_secret_basic', got {self.token_endpoint_auth_method!r}"
            )
        # NOTE(plan): the plan suggested a sorted tuple of pairs behind a
        # property, but an InitVar and a property cannot share a name on a
        # dataclass. A read-only proxy over a key-sorted dict is smaller and
        # keeps the attribute a real Mapping: dict equality already ignores
        # insertion order, so `==` holds either way, and what the two steps add
        # is refused mutation (frozen has to mean frozen all the way down) and a
        # repr that does not change with the order the params were typed in. The
        # cost is `hash()`, which nothing uses on a server declaration.
        object.__setattr__(
            self,
            "authorization_params",
            MappingProxyType(dict(sorted(self.authorization_params.items()))),
        )

    @classmethod
    async def discover(
        cls,
        issuer: str,
        *,
        client: Optional[httpx.AsyncClient] = None,
        timeout: int = 20,
    ) -> OAuth2Server:
        """Read the server's own metadata document and build a declaration from it.

        Tries OpenID Connect Discovery, then RFC 8414. This is the path for
        anything an enterprise runs — Okta, Entra ID, Auth0, Keycloak and Ping
        all publish one — and a discovered value cannot go stale the way a
        constant shipped in a release can.

        The one network call in this library that is not a tool call, and it is
        one you asked for by name.
        """
        base = issuer.rstrip("/")
        owns_client = client is None
        http = client or httpx.AsyncClient(timeout=timeout)
        errors: list[str] = []
        try:
            for path in _WELL_KNOWN:
                url = f"{base}/{path}"
                try:
                    resp = await http.get(url)
                except httpx.HTTPError as exc:
                    errors.append(f"{url}: {exc}")
                    continue
                if resp.status_code >= 400:
                    errors.append(f"{url}: HTTP {resp.status_code}")
                    continue
                try:
                    document = resp.json()
                except Exception:
                    errors.append(f"{url}: response was not JSON")
                    continue
                try:
                    return cls._from_metadata(document, url)
                except CredentialError as exc:
                    # A published-but-useless document is not a reason to skip
                    # the other well-known path: a server may answer the OIDC URL
                    # with something unrelated and still serve RFC 8414 properly.
                    errors.append(str(exc))
                    continue
        finally:
            if owns_client:
                await http.aclose()

        raise CredentialError(
            f"No authorization server metadata found for {issuer!r}. Tried: "
            + "; ".join(errors)
            + ". Declare the server explicitly instead.",
            docs="auth/authorization-servers",
        )

    @classmethod
    def _from_metadata(cls, document: Any, url: str) -> OAuth2Server:
        """Build a declaration from an RFC 8414 / OIDC discovery document."""
        if not isinstance(document, dict):
            raise CredentialError(
                f"{url} did not return a metadata object",
                docs="auth/authorization-servers",
            )

        token_endpoint = document.get("token_endpoint")
        if not isinstance(token_endpoint, str) or not token_endpoint:
            raise CredentialError(
                f"{url} advertises no token_endpoint, so it cannot be used to "
                "refresh a token.",
                docs="auth/authorization-servers",
            )

        # The document lists what the server supports; we have to pick one.
        # Prefer the form-body method: it is what most servers actually accept,
        # and the omission of the field entirely means the RFC default, which is
        # Basic — so only choose Basic when the server says so.
        supported = document.get("token_endpoint_auth_methods_supported")
        method: TokenEndpointAuthMethod = "client_secret_post"
        if isinstance(supported, list) and supported:
            if "client_secret_post" in supported:
                method = "client_secret_post"
            elif "client_secret_basic" in supported:
                method = "client_secret_basic"
            else:
                raise CredentialError(
                    f"{url} supports none of the client authentication methods Charter "
                    f"can use (needs client_secret_post or client_secret_basic; "
                    f"advertises {supported}).",
                    docs="reference/oauth#tokenendpointauthmethod",
                )

        issuer = document.get("issuer")
        # Absent is fine: the declaration still refreshes tokens. It only stops
        # being enough when OAuth2Flow.authorize() needs somewhere to send the
        # user, and that raises with instructions rather than guessing.
        authorization_endpoint = document.get("authorization_endpoint")
        return cls(
            token_endpoint=token_endpoint,
            token_endpoint_auth_method=method,
            issuer=issuer if isinstance(issuer, str) else None,
            authorization_endpoint=(
                authorization_endpoint
                if isinstance(authorization_endpoint, str) and authorization_endpoint
                else None
            ),
        )


# -----------------------------------------------------
# The token endpoint, shared
# -----------------------------------------------------
#
# A refresh (§6) and a code exchange (§4.1.3) are the same wire shape — one form
# POST, one JSON answer — differing by the grant_type string and two fields. The
# pieces below are that shared shape, used by OAuth2Client and OAuth2Flow alike.


def _client_auth(
    auth_method: TokenEndpointAuthMethod, client_id: str, client_secret: str
) -> tuple[Dict[str, str], Dict[str, str]]:
    """Form fields and headers that authenticate the client to the token endpoint."""
    headers: Dict[str, str] = {"Accept": "application/json"}
    if auth_method == "client_secret_basic":
        # RFC 6749 §2.3.1: each half is encoded with the
        # application/x-www-form-urlencoded algorithm before base64 — so a
        # space becomes "+", not "%20", and quote_plus is the right function.
        # Most servers decode either, but the spec picks one.
        pair = f"{quote_plus(client_id)}:{quote_plus(client_secret)}"
        encoded = base64.b64encode(pair.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
        return {}, headers
    return {"client_id": client_id, "client_secret": client_secret}, headers


async def _post_token_form(
    token_endpoint: str,
    data: Dict[str, str],
    headers: Dict[str, str],
    *,
    client: Optional[httpx.AsyncClient],
    timeout: int,
) -> httpx.Response:
    """One form POST to the token endpoint, owning the HTTP client if none was lent."""
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        return await http.post(token_endpoint, data=data, headers=headers)
    finally:
        if owns_client:
            await http.aclose()


def _json_payload(
    resp: httpx.Response, token_endpoint: str, provider: Optional[str]
) -> Dict[str, Any]:
    """The response body as a dict, or a CredentialError naming what came instead."""
    try:
        payload = resp.json()
    except Exception:
        payload = None

    if not isinstance(payload, dict):
        raise CredentialError(
            f"{token_endpoint} returned HTTP {resp.status_code} with a non-JSON body.",
            provider=provider,
            status_code=resp.status_code if resp.status_code >= 400 else None,
            docs="auth/authorization-servers",
        )
    return payload


def _token_failure(
    payload: Dict[str, Any], status_code: int, provider: Optional[str]
) -> Optional[tuple[str, CredentialError]]:
    """The OAuth error in a token response, or ``None`` when it is a success.

    RFC 6749 §5.2 says a failure is a 400 with ``{"error": "..."}``. Enough
    servers answer 200 with the same body that both are checked — the same
    reason :class:`~charter.types.envelope.Envelope` exists for tools.

    Returned rather than raised so the caller can also see the error *code*:
    ``OAuth2Client`` marks the grant dead on ``invalid_grant``, and that state
    belongs on the client, not smuggled through an exception attribute.
    """
    error = payload.get("error")
    if status_code < 400 and not error:
        return None
    code = error if isinstance(error, str) else f"HTTP {status_code}"
    description = payload.get("error_description")
    message = f"Token request failed: {code}"
    if isinstance(description, str) and description:
        message = f"{message} — {description}"
    if code == "invalid_grant":
        message += (
            ". The grant has expired or been revoked; the user has to "
            "authorize again."
        )
    return code, CredentialError(
        message,
        provider=provider,
        status_code=status_code if status_code >= 400 else None,
    )


# -----------------------------------------------------
# The client
# -----------------------------------------------------

OnRefresh = Callable[[Credentials, Optional[str]], Union[None, Awaitable[None]]]
"""Called after every successful refresh, with the new credentials and the
refresh token to store next time — which may be a new one, since some servers
rotate on every use.

This is where persistence lives, and it is the only place Charter will ever put it:
the library holds a token in memory for the seconds it is valid and writes it
nowhere.
"""


class OAuth2Client:
    """A :class:`~charter.auth.CredentialProvider` backed by a token endpoint.

    Holds one grant — one end user, or one machine identity. Serve many users by
    wrapping it in :class:`~charter.auth.SubjectProvider`, which keeps one of
    these per subject.

    The access token is cached in memory until ``leeway_seconds`` before it
    expires, and concurrent callers wait on a single refresh rather than each
    starting their own. That matters more than it looks: some servers invalidate
    the previous refresh token on use, so twelve parallel tool calls each firing
    their own refresh will poison eleven of them.
    """

    def __init__(
        self,
        server: OAuth2Server,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: Optional[str] = None,
        grant: Grant = "refresh_token",
        scope: Optional[str] = None,
        on_refresh: Optional[OnRefresh] = None,
        leeway_seconds: int = 90,
        timeout: int = 20,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not isinstance(server, OAuth2Server):
            raise TypeError("OAuth2Client requires an OAuth2Server declaration")
        if not client_id:
            raise CredentialError("OAuth2Client requires a client_id")
        if not client_secret:
            raise CredentialError("OAuth2Client requires a client_secret")
        if grant == "refresh_token" and not refresh_token:
            raise CredentialError(
                "OAuth2Client with the refresh_token grant requires a refresh_token. "
                "Charter refreshes a grant you already hold; obtaining one is your "
                "application's OAuth flow.",
                docs="auth/oauth-flow",
            )
        if grant not in ("refresh_token", "client_credentials"):
            raise ValueError(
                f"grant must be 'refresh_token' or 'client_credentials', got {grant!r}"
            )

        self.server = server
        self.grant: Grant = grant
        self.scope = scope
        self.leeway_seconds = leeway_seconds

        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._on_refresh = on_refresh
        self._timeout = timeout
        self._http = client

        self._cached: Optional[Credentials] = None
        self._lifetime_seconds: Optional[int] = None
        # The reason, not the exception. Re-raising one stored instance appends a
        # traceback to it on every raise — 5000 raises grew one to 15000 frames,
        # each pinning a stack frame and its locals.
        self._dead_reason: Optional[str] = None
        self._dead_status: Optional[int] = None
        self._dead_until: float = 0.0
        # A Lock binds to the event loop that first awaits it. Tool.invoke() runs
        # asyncio.run() per call, so a client built once and used from several
        # successive loops would otherwise raise. Rebinding on a loop change
        # keeps that working; the exotic case of two live loops in two threads
        # degrades to one extra refresh, never to a wrong token.
        self._lock: Optional[asyncio.Lock] = None
        self._lock_loop: Optional[asyncio.AbstractEventLoop] = None

    # -- provider protocol ------------------------------

    async def get_credentials(self, provider: str) -> Credentials:
        leeway = self._effective_leeway()
        cached = self._cached
        if cached is not None and not cached.is_expired(leeway):
            return cached

        self._raise_if_grant_is_dead(provider)

        async with self._get_lock():
            # Someone may have refreshed while we waited for the lock — or found
            # out the grant is dead, in which case do not queue up behind them.
            cached = self._cached
            if cached is not None and not cached.is_expired(self._effective_leeway()):
                return cached
            self._raise_if_grant_is_dead(provider)
            return await self._refresh(provider)

    def _effective_leeway(self) -> int:
        """``leeway_seconds``, capped at half the lifetime the server granted.

        Renewing 90 seconds early is sensible for an hour-long token and absurd
        for a 60-second one: the token is born already inside the window, so
        every call refreshes, and the cache turns one request into two. Against a
        server that rotates, it would also churn a new refresh token per call.

        Halving the granted lifetime keeps the early-renewal behaviour wherever
        it makes sense and degrades gracefully where it does not.
        """
        if self._lifetime_seconds is None:
            return self.leeway_seconds
        return max(0, min(self.leeway_seconds, self._lifetime_seconds // 2))

    def reset(self) -> None:
        """Forget the cached token and any dead-grant cool-down.

        Call this after re-authorizing, if you are reusing the client rather than
        building a new one with the new refresh token.
        """
        self._cached = None
        self._lifetime_seconds = None
        self._dead_reason = None
        self._dead_status = None
        self._dead_until = 0.0

    @property
    def refresh_token(self) -> Optional[str]:
        """The current refresh token — which is not necessarily the one passed in.

        A server that rotates hands back a new one on every refresh; Charter adopts
        it. Persist it through ``on_refresh``, or read it from here.
        """
        return self._refresh_token

    @classmethod
    def from_grant(
        cls,
        server: OAuth2Server,
        grant: TokenGrant,
        *,
        client_id: str,
        client_secret: str,
        on_refresh: Optional[OnRefresh] = None,
        **kwargs: Any,
    ) -> OAuth2Client:
        """A client seeded from a fresh :meth:`OAuth2Flow.exchange` grant.

        The bridge from acquisition to injection: the grant's access token
        pre-fills the cache, so the first tool call after connecting uses the
        token the exchange just returned instead of spending a refresh.

        A grant without a refresh token is refused — a client that can never
        refresh is a footgun, not a convenience. For a one-shot access token,
        use :class:`~charter.auth.StaticTokenProvider`.
        """
        if not grant.refresh_token:
            raise CredentialError(
                "The TokenGrant carries no refresh_token, so a client built from "
                "it could never refresh. Exchange with expect_refresh_token=True "
                "(the default), or hold the short-lived access token in a "
                "StaticTokenProvider instead.",
                docs="auth/oauth-flow#the-failure-this-flow-exists-to-catch",
            )
        client = cls(
            server,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=grant.refresh_token,
            on_refresh=on_refresh,
            **kwargs,
        )
        client._cached = Credentials(
            token=grant.access_token, expires_at=grant.expires_at
        )
        # The leeway cap wants the granted lifetime; the exchange response had it.
        client._lifetime_seconds = _expires_in_seconds(grant.raw.get("expires_in"))
        return client

    # -- internals --------------------------------------

    def _raise_if_grant_is_dead(self, provider: str) -> None:
        """Raise the last ``invalid_grant`` again instead of asking again.

        The host sees the same error either way; what changes is that the token
        endpoint does not. A fresh exception each time, for the reason above.
        """
        if self._dead_reason is None:
            return
        if monotonic() >= self._dead_until:
            self._dead_reason = None
            self._dead_status = None
            self._dead_until = 0.0
            return
        raise CredentialError(
            self._dead_reason,
            provider=provider,
            status_code=self._dead_status,
            docs="auth/oauth-flow",
        )

    def _get_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    def _build_request(self) -> tuple[Dict[str, str], Dict[str, str]]:
        """The form body and headers for one token request."""
        data: Dict[str, str] = {"grant_type": self.grant}
        if self.grant == "refresh_token":
            assert self._refresh_token is not None  # guarded in __init__
            data["refresh_token"] = self._refresh_token
        if self.scope:
            data["scope"] = self.scope

        auth_fields, headers = _client_auth(
            self.server.token_endpoint_auth_method, self._client_id, self._client_secret
        )
        data.update(auth_fields)
        return data, headers

    async def _refresh(self, provider: str) -> Credentials:
        data, headers = self._build_request()
        resp = await _post_token_form(
            self.server.token_endpoint,
            data,
            headers,
            client=self._http,
            timeout=self._timeout,
        )
        payload = self._parse(resp, provider)

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise CredentialError(
                f"{self.server.token_endpoint} returned no access_token.",
                provider=provider,
                docs="auth/authorization-servers",
            )

        lifetime = _expires_in_seconds(payload.get("expires_in"))
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=lifetime)
            if lifetime is not None
            else None
        )
        self._lifetime_seconds = lifetime

        # A rotated refresh token announces itself by being in the response, so
        # there is nothing to declare and nothing to configure — take whatever
        # comes back, keep the old one when nothing does.
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            self._refresh_token = rotated

        credentials = Credentials(token=access_token, expires_at=expires_at)
        self._cached = credentials

        logger.debug(
            "OAuth refresh ok for %s (expires_at=%s, rotated=%s)",
            provider or self.server.issuer or self.server.token_endpoint,
            expires_at,
            bool(isinstance(rotated, str) and rotated),
        )

        if self._on_refresh is not None:
            try:
                result = self._on_refresh(credentials, self._refresh_token)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                # Persistence is the host's problem, and a failure to write the
                # token down must not fail the call the token was fetched for.
                # The credential is still good for this process.
                logger.warning(
                    "charter: on_refresh raised; the new token was not persisted",
                    exc_info=True,
                )

        return credentials

    def _parse(self, resp: httpx.Response, provider: str) -> Dict[str, Any]:
        """Read the token response, turning an OAuth error into a CredentialError."""
        payload = _json_payload(resp, self.server.token_endpoint, provider)
        failure = _token_failure(payload, resp.status_code, provider)
        if failure is not None:
            code, error = failure
            if code == "invalid_grant":
                # Dead until somebody re-authorizes. Remember that, so an agent
                # still calling tools does not turn it into a stream of requests.
                self._dead_reason = error.message
                self._dead_status = error.status_code
                self._dead_until = monotonic() + _DEAD_GRANT_COOLDOWN_SECONDS
            raise error

        return payload

    def __repr__(self) -> str:
        return (
            f"OAuth2Client(token_endpoint={self.server.token_endpoint!r}, "
            f"grant={self.grant!r}, client_secret=***)"
        )


def _expires_in_seconds(expires_in: Any) -> Optional[int]:
    """The lifetime the server granted, in seconds, or ``None`` if it said nothing.

    Some tokens genuinely never expire (Notion, GitHub's classic OAuth apps).
    An absent ``expires_in`` means exactly that, and the cache then holds the
    token for the life of the process — correct, and the reason ``is_expired``
    treats a missing expiry as valid rather than as expired.

    A value of zero or less is the opposite claim: the server is saying the token
    is already dead. Reading that as "never expires" would cache a corpse
    forever, so it becomes an instant in the past.
    """
    if isinstance(expires_in, bool) or not isinstance(expires_in, (int, float, str)):
        return None
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError, OverflowError):
        # Python's json module parses bare `Infinity` and `NaN` happily, so a
        # server emitting non-standard JSON reaches here with a float that has no
        # integer form. OverflowError belongs in this list for the same reason
        # ValueError does: neither should escape a credential lookup.
        return None
    # A server is free to send nonsense. Clamping keeps an absurd value from
    # raising OverflowError out of a credential lookup, where the host is
    # catching CharterError and would never see it coming.
    return max(-_MAX_EXPIRES_IN, min(_MAX_EXPIRES_IN, seconds))


# Last on purpose: flow.py builds on the declarations above, so importing it at
# the bottom keeps the one-way dependency visible (flow -> this module, never
# the reverse at runtime).
from charter.auth.flow import (  # noqa: E402
    AuthorizationRequest,
    OAuth2Flow,
    TokenGrant,
    scopes_for,
    states_match,
)
