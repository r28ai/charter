# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

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
from typing import (
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Collection,
    Dict,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Protocol,
    TypeVar,
    Union,
    runtime_checkable,
)
from urllib.parse import quote_plus

import httpx

from charter.auth.credentials import Credentials
from charter.types.errors import CredentialError, DeclarationError

__all__ = [
    "OAuth2Server",
    "OAuth2Client",
    "Revocation",
    "RevocationAuthMethod",
    "Revoker",
    "GrantToRevoke",
    "revoke_token",
    "OAuth2Flow",
    "AuthorizationRequest",
    "TokenGrant",
    "TokenEndpointAuthMethod",
    "Grant",
    "GrantLoader",
    "RefreshLock",
    "OnRefresh",
    "scopes_for",
    "states_match",
]

logger = logging.getLogger("charter")

_T = TypeVar("_T")

TokenEndpointAuthMethod = Literal["client_secret_post", "client_secret_basic", "secret_key_basic"]
"""How the client authenticates to the token endpoint (RFC 6749 §2.3.1).

``client_secret_post`` puts the credentials in the form body; it is what Google,
GitHub and most APIs expect. ``client_secret_basic`` puts them in an HTTP Basic
header, which the RFC nominally prefers and some servers require.

``secret_key_basic`` is not in the RFC. It sends the client secret alone as the
Basic username, with no password and no client ID, which is how an API that
authenticates every request with a secret key authenticates its token endpoint
too. Stripe is the case: a Stripe App exchanges and refreshes with
``-u sk_live_...:``, and its ``client_id`` appears only in the consent link.
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

# What a code exchange sends on its own account, which exchange_params may not
# replace: the grant, the code and its PKCE proof, and the client's identity.
_EXCHANGE_OWNED = (
    "grant_type",
    "code",
    "redirect_uri",
    "code_verifier",
    "client_id",
    "client_secret",
    "refresh_token",
)

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

RevocationAuthMethod = Literal[
    "client_secret_post", "client_secret_basic", "secret_key_basic", "none"
]
"""How the client authenticates to a revocation endpoint.

The token endpoint's methods, plus ``none`` for an endpoint that takes the token
alone. Google's is one: its revocation endpoint is documented with nothing but
``token``, so the client secret is not sent somewhere it is not asked for.
"""


# -----------------------------------------------------
# The server
# -----------------------------------------------------


@dataclass(frozen=True)
class Revocation:
    """How a server ends a grant: RFC 7009 unless declared otherwise.

    The defaults are the RFC. One POST to ``endpoint`` carrying the refresh
    token as ``token``, authenticated the way the token endpoint is, in the
    body format the token endpoint takes. Revoking a refresh token ends the
    grant and, where the server supports it, every access token issued from it
    (RFC 7009 §2.1), so the user disappears from the account's list of
    connected apps. Google, Linear and Notion are this shape, and a server that
    publishes ``revocation_endpoint`` in its metadata gets one from
    :meth:`OAuth2Server.discover`.

    The rest of the fields are how a vendor departs from it, each written down
    rather than coded, as the token endpoint's departures are:

    ``token_type`` is which token the endpoint takes. ``"access_token"`` is for
    an endpoint that ends the grant given any live access token: GitHub's
    ``DELETE /applications/{client_id}/grant``, Slack's ``apps.uninstall``,
    Shopify's ``api_permissions/current.json``. An
    :class:`OAuth2Client` refreshes first if its cached token has lapsed.

    ``auth_method`` is how the client authenticates, when it differs from the
    token endpoint. ``None`` inherits; ``"none"`` sends no client credentials.

    ``token_field`` is the body field carrying the token, ``"token"`` when
    left as ``None``. GitHub names it ``access_token``.

    ``token_header`` sends the token as the request's own credential instead of
    in the body. ``"Authorization"`` sends it as ``Bearer``; any other header
    gets the bare token, as Shopify's ``X-Shopify-Access-Token`` does. It only
    makes sense with ``token_type="access_token"``, and cannot be combined with
    ``token_field``.

    ``http_method`` is ``"POST"``, or ``"DELETE"`` for GitHub and Shopify.

    ``request_format`` is the body format, inheriting the token endpoint's
    when ``None``. GitHub's API takes JSON where its token endpoint takes a
    form.

    ``gone_errors`` and ``gone_statuses`` are how the server says the token was
    already dead, which for a disconnect is the outcome asked for rather than a
    failure. ``invalid_token`` (RFC 6750's code for a token that is not
    valid, and Google's answer), ``invalid_grant`` and the server's
    ``dead_grant_errors`` always count, and so does a ``401`` when the token
    is the request's own credential. Anything else raises. RFC 7009 itself
    has a server answer ``200`` for a token it does not know (§2.2), so one
    that follows it, as Notion does, never reports a grant already gone.

    ``token_type_hint`` sends RFC 7009's optional ``token_type_hint``, naming
    which token ``token`` is. Linear's docs suggest it "to help the server
    identify the token"; measured, Linear only finds a refresh token when told,
    so its declaration sets this.

    ``{client_id}`` in ``endpoint`` is replaced with the client ID, since
    GitHub's endpoint is per registration.
    """

    endpoint: str
    token_type: Literal["refresh_token", "access_token"] = "refresh_token"
    auth_method: Optional[RevocationAuthMethod] = None
    token_field: Optional[str] = None
    token_header: Optional[str] = None
    http_method: Literal["POST", "DELETE"] = "POST"
    request_format: Optional[Literal["form", "json"]] = None
    gone_errors: tuple[str, ...] = ()
    gone_statuses: tuple[int, ...] = ()
    token_type_hint: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or not self.endpoint:
            raise DeclarationError(
                "Revocation requires an endpoint", docs="reference/oauth#revocation"
            )
        if self.token_type not in ("refresh_token", "access_token"):
            raise DeclarationError(
                f"token_type must be 'refresh_token' or 'access_token', got {self.token_type!r}"
            )
        if self.auth_method not in (
            None,
            "client_secret_post",
            "client_secret_basic",
            "secret_key_basic",
            "none",
        ):
            raise DeclarationError(
                "auth_method must be None, 'client_secret_post', 'client_secret_basic', "
                f"'secret_key_basic' or 'none', got {self.auth_method!r}"
            )
        if self.http_method not in ("POST", "DELETE"):
            raise DeclarationError(
                f"http_method must be 'POST' or 'DELETE', got {self.http_method!r}"
            )
        if self.request_format not in (None, "form", "json"):
            raise DeclarationError(
                f"request_format must be None, 'form' or 'json', got {self.request_format!r}"
            )
        if self.token_field is not None and not self.token_field:
            raise DeclarationError("token_field must not be empty; leave it None for 'token'")
        if self.token_header is not None:
            if not self.token_header:
                raise DeclarationError("token_header must not be empty")
            if self.token_field is not None:
                raise DeclarationError(
                    "A Revocation sends the token in token_field or in token_header, "
                    f"not both: got token_field={self.token_field!r} and "
                    f"token_header={self.token_header!r}."
                )
            if self.token_type != "access_token":
                raise DeclarationError(
                    "token_header sends the token as the request's own credential, "
                    "and only an access token authenticates a request. Declare "
                    "token_type='access_token' with it.",
                    docs="reference/oauth#revocation",
                )
        codes = self.gone_errors
        if isinstance(codes, str) or not all(isinstance(c, str) and c for c in codes):
            raise DeclarationError(
                f"gone_errors must be a tuple of error codes, such as ('invalid_auth',), got {codes!r}"
            )
        object.__setattr__(self, "gone_errors", tuple(codes))
        statuses = self.gone_statuses
        if isinstance(statuses, (str, int)) or not all(
            isinstance(s, int) and not isinstance(s, bool) and 400 <= s < 500 for s in statuses
        ):
            raise DeclarationError(
                "gone_statuses must be a tuple of 4xx status codes, such as (422,), "
                f"got {statuses!r}"
            )
        object.__setattr__(self, "gone_statuses", tuple(statuses))
        if not isinstance(self.token_type_hint, bool):
            raise DeclarationError(
                f"token_type_hint must be True or False, got {self.token_type_hint!r}"
            )
        if self.token_type_hint and self.token_header is not None:
            raise DeclarationError(
                "token_type_hint names the token in the body, and token_header sends it "
                "as a header instead. Declare one or the other.",
                docs="reference/oauth#revocation",
            )


@runtime_checkable
class Revoker(Protocol):
    """A server's own way of ending a grant, where one declared request is not it.

    :class:`Revocation` declares a single request carrying a token, and that is
    every documented server but one. Stripe Apps ends a grant by uninstalling
    the app: find the account's install, then uninstall it, and neither request
    carries a token. A ``Revoker`` is such a procedure. It lives in the
    provider's pack (:class:`charter.packs.stripe.StripeAppUninstall`), and
    :meth:`OAuth2Client.revoke` and :func:`revoke_token` run it where they would
    send a ``Revocation``, so a disconnect is the same call for every server.

    ``grant_fields`` names the token-response fields it needs, such as Stripe's
    ``stripe_user_id``; a client takes them from the exchange, the stored grant
    or a refresh. ``revoke`` returns ``True`` when the server confirmed the grant
    ended, ``False`` when it was already gone, and raises
    :class:`CredentialError` for any other refusal. Make it a frozen dataclass,
    so two declarations of one server compare equal.
    """

    @property
    def grant_fields(self) -> tuple[str, ...]: ...

    async def revoke(self, grant: GrantToRevoke) -> bool: ...


@dataclass(frozen=True)
class GrantToRevoke:
    """What a :class:`Revoker` is handed to end one grant.

    ``fields`` holds the token-response fields its ``grant_fields`` names.
    ``http`` is the client to send with, which Charter owns and closes;
    :meth:`send` is the way to use it.
    """

    server: OAuth2Server
    client_id: str
    client_secret: str
    refresh_token: Optional[str]
    access_token: Optional[str]
    fields: Mapping[str, str]
    http: httpx.AsyncClient

    async def send(
        self,
        method: str,
        url: str,
        *,
        doing: str,
        auth_method: Optional[RevocationAuthMethod] = None,
        allow: Collection[int] = (),
        provider: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, str]] = None,
        data: Optional[Mapping[str, str]] = None,
        json: Optional[Mapping[str, Any]] = None,
    ) -> httpx.Response:
        """One request as the app, with its refusal turned into a :class:`CredentialError`.

        The client authenticates the way ``auth_method`` says, inheriting the
        server's ``token_endpoint_auth_method`` when ``None``, as a
        :class:`Revocation` does; ``"none"`` sends no client credentials. A
        response at ``300`` or above raises, unless its status is in ``allow``,
        with ``doing`` as what failed and the server's own code and message
        read from whichever error shape it uses. Every credential the grant
        holds is redacted from that message.
        """
        method = method.upper()
        sent_headers = dict(headers or {})
        sent_data = dict(data) if data is not None else None
        sent_json = dict(json) if json is not None else None
        chosen = auth_method or self.server.token_endpoint_auth_method
        if chosen != "none":
            fields, auth_headers = _client_auth(chosen, self.client_id, self.client_secret)
            sent_headers.update(auth_headers)
            if fields:
                # client_secret_post: the credentials travel in the body.
                if sent_json is not None:
                    sent_json.update(fields)
                elif method in ("GET", "HEAD"):
                    raise DeclarationError(
                        f"{chosen} sends the client's credentials in a body, and a {method} "
                        f"has none. Pass auth_method for {url}.",
                        docs="reference/oauth#granttorevoke",
                    )
                else:
                    sent_data = {**(sent_data or {}), **fields}
        resp = await self.http.request(
            method, url, headers=sent_headers, params=params, data=sent_data, json=sent_json
        )
        if resp.status_code < 300 or resp.status_code in allow:
            return resp
        code, explanation = _error_parts(_json_body(resp), resp.status_code)
        message = f"{doing} failed: {code or f'HTTP {resp.status_code}'}"
        if explanation:
            message = f"{message} — {explanation}"
        raise CredentialError(
            _redact(message, (self.client_secret, self.refresh_token, self.access_token)),
            provider=provider,
            status_code=resp.status_code,
            token_refused=False,
            docs="reference/oauth#granttorevoke",
        )


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

    ``uses_scopes=False`` is for a server whose permissions are fixed when the
    app is registered rather than asked for in the consent link — Notion's
    capabilities, a Stripe App's manifest. :meth:`OAuth2Flow.authorize` then
    takes no scopes and sends no ``scope`` parameter, where it would otherwise
    refuse an empty list as a bug upstream.

    ``scope_separator`` is how the consent link joins scopes. RFC 6749 §3.3
    says a space; Linear and Shopify document a comma, so their declarations
    say so.

    ``token_request_format`` is how the token endpoint wants its body. The RFC
    says a form, and so does nearly every server; Notion documents its token
    endpoint as JSON only, so its declaration says ``"json"``.

    ``default_expires_in`` is the access token's lifetime, in seconds, for a
    server that documents one but leaves ``expires_in`` out of its token
    response. Stripe is the case: its tokens last an hour and its response
    never says so. Without this, an absent ``expires_in`` reads as "never
    expires", so the token is only replaced once the API refuses it, and that
    call fails. With it, the token is renewed shortly before the hour, as a
    server that sends ``expires_in`` gets. A response that does carry
    ``expires_in`` always wins.

    ``exchange_params`` are vendor fields for the code exchange, as
    ``authorization_params`` are for the consent link. Shopify is the case: an
    offline token that expires, with a refresh token beside it, has to be asked
    for with ``expiring=1`` in the exchange, and Shopify requires public apps to
    use that token for the GraphQL Admin API. Only the exchange sends them, not
    the refreshes after it, and the fields the exchange itself owns are refused.

    ``dead_grant_errors`` are the error codes, besides RFC 6749's
    ``invalid_grant``, with which the server says a grant is gone: revoked,
    expired, or a refresh token already spent. Slack is the case: it answers a
    bad refresh token with ``invalid_refresh_token`` and an uninstalled app with
    ``token_revoked``, both inside an HTTP 200. Charter treats these codes as it
    treats ``invalid_grant``: it holds the token endpoint off for a minute,
    rereads a shared store for a successor, and raises a
    :class:`CredentialError` whose ``reauthorize`` is true. ``invalid_grant``
    always counts, so a server that uses only the RFC's code declares nothing
    here.

    ``revocation`` is how the server ends a grant, for the "disconnect" button:
    :class:`Revocation`, which is RFC 7009 unless it says otherwise, or a
    :class:`Revoker`, for a server whose disconnect is more than one request
    carrying a token (Stripe Apps).
    :meth:`OAuth2Client.revoke` and :func:`revoke_token` send it. ``None``
    means the server documents no way to end a grant.
    """

    token_endpoint: str
    token_endpoint_auth_method: TokenEndpointAuthMethod = "client_secret_post"
    issuer: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    authorization_params: Mapping[str, str] = field(default_factory=dict)
    uses_scopes: bool = True
    scope_separator: str = " "
    token_request_format: Literal["form", "json"] = "form"
    default_expires_in: Optional[int] = None
    exchange_params: Mapping[str, str] = field(default_factory=dict)
    dead_grant_errors: tuple[str, ...] = ()
    revocation: Optional[Union[Revocation, Revoker]] = None

    def __post_init__(self) -> None:
        if not self.token_endpoint:
            raise DeclarationError(
                "OAuth2Server requires a token_endpoint",
                docs="auth/authorization-servers",
            )
        if self.token_endpoint_auth_method not in (
            "client_secret_post",
            "client_secret_basic",
            "secret_key_basic",
        ):
            raise DeclarationError(
                "token_endpoint_auth_method must be 'client_secret_post', "
                "'client_secret_basic' or 'secret_key_basic', got "
                f"{self.token_endpoint_auth_method!r}"
            )
        if self.token_request_format not in ("form", "json"):
            raise DeclarationError(
                f"token_request_format must be 'form' or 'json', got {self.token_request_format!r}"
            )
        if not self.scope_separator:
            raise DeclarationError("scope_separator must not be empty")
        if self.default_expires_in is not None and (
            isinstance(self.default_expires_in, bool)
            or not isinstance(self.default_expires_in, int)
            or self.default_expires_in <= 0
        ):
            raise DeclarationError(
                "default_expires_in must be a positive number of seconds, got "
                f"{self.default_expires_in!r}"
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
        owned = sorted(set(self.exchange_params) & set(_EXCHANGE_OWNED))
        if owned:
            raise DeclarationError(
                f"exchange_params cannot set {', '.join(owned)}: the exchange sends "
                "those itself, from the flow and the code."
            )
        object.__setattr__(
            self,
            "exchange_params",
            MappingProxyType(dict(sorted(self.exchange_params.items()))),
        )
        # A bare string would iterate as its letters, and every one-letter code
        # would then match nothing, silently.
        codes = self.dead_grant_errors
        if isinstance(codes, str) or not all(isinstance(c, str) and c for c in codes):
            raise DeclarationError(
                "dead_grant_errors must be a tuple of error codes, such as "
                f"('invalid_refresh_token',), got {codes!r}"
            )
        object.__setattr__(self, "dead_grant_errors", tuple(codes))
        revocation = self.revocation
        if revocation is not None and not isinstance(revocation, Revocation):
            fields = getattr(revocation, "grant_fields", None)
            if (
                not isinstance(revocation, Revoker)
                or not inspect.iscoroutinefunction(revocation.revoke)
                or not isinstance(fields, tuple)
                or not all(isinstance(f, str) and f for f in fields)
            ):
                raise DeclarationError(
                    "revocation must be a Revocation, such as "
                    "Revocation('https://.../revoke'), or a Revoker with grant_fields and "
                    f"an async revoke(grant), got {revocation!r}",
                    docs="reference/oauth#revocation",
                )
        elif revocation is not None:
            auth = revocation.auth_method or self.token_endpoint_auth_method
            header = (revocation.token_header or "").lower()
            if header == "authorization" and auth in ("client_secret_basic", "secret_key_basic"):
                raise DeclarationError(
                    f"The revocation sends the token in the Authorization header, and "
                    f"{auth} authenticates the client in the same header. Declare "
                    "auth_method='client_secret_post' or 'none' on the Revocation.",
                    docs="reference/oauth#revocation",
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
                f"{url} advertises no token_endpoint, so it cannot be used to refresh a token.",
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
            revocation=_discovered_revocation(document, method),
        )


def _discovered_revocation(
    document: Dict[str, Any], token_method: TokenEndpointAuthMethod
) -> Optional[Revocation]:
    """The RFC 7009 endpoint a metadata document advertises, if Charter can use it.

    ``revocation_endpoint_auth_methods_supported`` is read the way the token
    endpoint's list is: the token endpoint's method is kept if the list allows
    it, and absent means the RFC default. A list naming nothing Charter can send
    leaves revocation undeclared rather than failing discovery, since the
    declaration still refreshes tokens.
    """
    endpoint = document.get("revocation_endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        return None
    supported = document.get("revocation_endpoint_auth_methods_supported")
    if not isinstance(supported, list) or not supported or token_method in supported:
        return Revocation(endpoint)
    candidates: tuple[RevocationAuthMethod, ...] = (
        "client_secret_post",
        "client_secret_basic",
        "none",
    )
    for method in candidates:
        if method in supported:
            return Revocation(endpoint, auth_method=method)
    return None


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
    if auth_method == "secret_key_basic":
        # The secret is the username and the password is empty — what
        # `curl -u sk_live_...:` sends. Not form-encoded first: this is the
        # API's own key auth, not RFC 6749's client authentication.
        encoded = base64.b64encode(f"{client_secret}:".encode()).decode("ascii")
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
    request_format: Literal["form", "json"] = "form",
) -> httpx.Response:
    """One POST to the token endpoint, owning the HTTP client if none was lent.

    A form, as RFC 6749 specifies, unless the server is declared to want JSON.
    """
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        if request_format == "json":
            return await http.post(token_endpoint, json=data, headers=headers)
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


_REDACT_MIN_LENGTH = 8
"""The shortest sent value that :func:`_redact` treats as a credential.

No server issues a token or secret this short. A test's ``"csec"`` is that
short, and replacing it would rewrite the server's own words wherever the
letters happened to appear, so a value below this is left in place.
"""


def _redact(text: str, sent: Iterable[Optional[str]]) -> str:
    """``text`` with every credential the request sent replaced by ``***``.

    Servers quote what they refuse. Stripe answers a used refresh token with
    "Refresh token does not exist: rt_..." and an unknown code with
    "Authorization code does not exist: ac_...". That description becomes the
    exception's message, and an exception message ends up in a log line, so
    a token that reached Charter's error would reach the log.

    What is redacted is exactly what this request sent, not a pattern. Each
    server prefixes its tokens differently, and the values are already in
    hand here.
    """
    for value in sent:
        if value and len(value) >= _REDACT_MIN_LENGTH:
            text = text.replace(value, "***")
    return text


def _json_body(resp: httpx.Response) -> Dict[str, Any]:
    """The response body as a dict, or an empty one when it is anything else."""
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _error_parts(
    payload: Mapping[str, Any], status_code: int
) -> tuple[Optional[str], Optional[str]]:
    """The error code and the explanation in a refusal, whichever shape it takes.

    RFC 6749's ``error`` and ``error_description``, which Slack sends in a
    ``200`` too; Stripe's API nests ``code`` and ``message`` under ``error``;
    Notion names its code ``code``; GitHub's API gives a ``message`` alone. A
    top-level ``code`` counts only on a failing status, where it cannot be a
    successful body's own field.
    """
    error = payload.get("error")
    if isinstance(error, Mapping):
        code, explanation = error.get("code"), error.get("message")
    else:
        code = error if isinstance(error, str) and error else None
        if code is None and status_code >= 400:
            code = payload.get("code")
        explanation = payload.get("error_description") or payload.get("message")
    return (
        code if isinstance(code, str) and code else None,
        explanation if isinstance(explanation, str) and explanation else None,
    )


def _dead_codes(server: OAuth2Server) -> tuple[str, ...]:
    """The error codes with which ``server`` says a grant is gone."""
    return ("invalid_grant", *server.dead_grant_errors)


def _token_failure(
    payload: Dict[str, Any],
    status_code: int,
    provider: Optional[str],
    sent: Iterable[Optional[str]] = (),
    dead: Iterable[str] = ("invalid_grant",),
) -> Optional[tuple[str, CredentialError]]:
    """The OAuth error in a token response, or ``None`` when it is a success.

    RFC 6749 §5.2 says a failure is a 400 with ``{"error": "..."}``. Enough
    servers answer 200 with the same body that both are checked — the same
    reason :class:`~charter.types.envelope.Envelope` exists for tools.

    Returned rather than raised so the caller can also see the error *code*:
    ``OAuth2Client`` marks the grant dead on ``invalid_grant``, and that state
    belongs on the client, not smuggled through an exception attribute.

    ``sent`` is the credentials the request carried, redacted from the
    message wherever the server quoted them back: :func:`_redact`.

    ``dead`` is the codes that mean the grant is gone, which is
    ``invalid_grant`` plus whatever the server declares in
    ``dead_grant_errors``.
    """
    error = payload.get("error")
    if status_code < 400 and not error:
        return None
    code = error if isinstance(error, str) else f"HTTP {status_code}"
    description = payload.get("error_description")
    message = f"Token request failed: {code}"
    if isinstance(description, str) and description:
        message = f"{message} — {description}"
    message = _redact(message, sent)
    reauthorize = code in dead
    if reauthorize:
        # GitHub's description ends in a full stop of its own.
        message = message.rstrip(".")
        message += ". The grant has expired or been revoked; the user has to authorize again."
    return code, CredentialError(
        message,
        provider=provider,
        status_code=status_code if status_code >= 400 else None,
        reauthorize=reauthorize,
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

GrantLoader = Callable[[], Union[str, "TokenGrant", Awaitable[Union[str, "TokenGrant"]]]]
"""Reads a grant from the host's store, for :class:`OAuth2Client`.

Passed as ``refresh_token`` when more than one process serves the same user.
Return the stored refresh token, so no process refreshes with one another has
already spent. Or return a :class:`~charter.auth.TokenGrant` with the stored
access token and its expiry as well, so a process takes the token another
already obtained instead of refreshing again. Against a server whose refresh
revokes the previous access token, as Stripe's does within seconds, sharing
the access token is what keeps workers from refusing each other's calls.
"""

RefreshLock = Callable[[], AsyncContextManager[Any]]
"""Takes a lock across processes for one grant, as an async context manager.

Passed as ``refresh_lock`` to :class:`OAuth2Client`, which holds it while it
reads the stored grant, refreshes if it still has to, and stores the result
through ``on_refresh``. The next process to take the lock then reads that
result instead of refreshing again, so no process ever presents a refresh
token another has already spent. Against a server with reuse detection
(RFC 9700 §4.14), presenting a spent token revokes the grant, so there this
lock is what keeps several processes from disconnecting the user.
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

    That single refresh is per process. Run two workers and each holds its own
    copy of the grant. Against a server that rotates, the first to refresh
    leaves the other's refresh token spent, and its next refresh answers
    ``invalid_grant`` for a grant that is fine. Against Stripe, whose refresh
    also revokes the previous access token, each worker's refresh fails the
    other's next call. Pass ``refresh_token`` as a :data:`GrantLoader` that
    reads what ``on_refresh`` stored. It is called before every refresh, and
    once more on ``invalid_grant``. When it returns a :class:`TokenGrant` whose
    access token is still good, that token is used and no refresh is made.
    Against a server that revokes a grant when a spent refresh token comes back,
    add a ``refresh_lock`` (:data:`RefreshLock`) so the processes take turns.
    """

    def __init__(
        self,
        server: OAuth2Server,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: Optional[Union[str, GrantLoader]] = None,
        grant: Grant = "refresh_token",
        scope: Optional[str] = None,
        on_refresh: Optional[OnRefresh] = None,
        refresh_lock: Optional[RefreshLock] = None,
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
        if grant == "client_credentials" and callable(refresh_token):
            raise ValueError(
                "A GrantLoader reads a refresh token, and the client_credentials grant "
                "has none to read."
            )
        if refresh_lock is not None and not callable(refresh_token):
            raise ValueError(
                "refresh_lock needs refresh_token to be a GrantLoader. Under the lock "
                "the client reads what the last holder stored; a refresh token passed "
                "as a string is a copy, and the lock cannot make a copy current."
            )

        self.server = server
        self.grant: Grant = grant
        self.scope = scope
        self.leeway_seconds = leeway_seconds

        self._client_id = client_id
        self._client_secret = client_secret
        # A loader is read before each refresh, so the string is only ever the
        # last value it returned or the server rotated to.
        self._load_grant: Optional[GrantLoader] = refresh_token if callable(refresh_token) else None
        # The last token the API refused, so a store still holding it is not
        # read back as the answer.
        self._refused_token: Optional[str] = None
        self._refresh_token: Optional[str] = None if callable(refresh_token) else refresh_token
        self._on_refresh = on_refresh
        self._refresh_lock = refresh_lock
        self._timeout = timeout
        self._http = client

        self._cached: Optional[Credentials] = None
        # The declared lifetime until a response states one, so the leeway cap
        # holds from the first call, stored token included.
        self._lifetime_seconds: Optional[int] = server.default_expires_in
        # The reason, not the exception. Re-raising one stored instance appends a
        # traceback to it on every raise — 5000 raises grew one to 15000 frames,
        # each pinning a stack frame and its locals.
        self._dead_reason: Optional[str] = None
        self._dead_status: Optional[int] = None
        self._dead_until: float = 0.0
        # The refresh token the server called dead, so a loader can tell when the
        # store holds another (the user connected again in some other process).
        self._dead_refresh_token: Optional[str] = None
        # The token-response fields a Revoker names (Stripe's stripe_user_id),
        # from the last response that carried them.
        self._grant_fields: Dict[str, str] = {}
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

        if self._dead_reason is not None and self._load_grant is not None:
            await self._lift_if_reconnected()
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
        self._lifetime_seconds = self.server.default_expires_in
        self._clear_dead()

    def invalidate(self, credentials: Credentials) -> None:
        """Drop the cached token if it is the one the API just refused.

        Called by the runtime on a 401. Without it a token revoked before its
        expiry — an app reinstalled, a secret rotated — was sent on every call
        until the expiry it was issued with, up to a day of 401s for a token the
        server could have replaced on the next request.

        Only that token: if another call has already replaced it, the
        replacement stays. The grant is untouched, so the next call refreshes
        rather than failing, and a server that answers that refresh with
        ``invalid_grant`` is held off by the cool-down as before.
        """
        self._refused_token = credentials.token
        cached = self._cached
        if cached is not None and cached.token == credentials.token:
            self._cached = None
            logger.debug(
                "OAuth token for %s was rejected; the next call fetches a new one",
                self.server.issuer or self.server.token_endpoint,
            )

    async def revoke(self) -> bool:
        """End the grant at the server, then stop using it here: the disconnect button.

        Sends the server's :class:`Revocation`. With the RFC's shape that is the
        refresh token, which ends the grant and every access token issued from
        it. With a vendor's that takes an access token it is the freshest one
        to be had, renewed first if it has lapsed. A client built with a
        :data:`GrantLoader` reads the store first, under its ``refresh_lock``,
        so it revokes the grant the store holds and not one another process
        has since rotated. An access token the server calls dead is renewed
        and sent again once: GitHub and Notion retire the previous access token
        when another process refreshes, and that says nothing about the grant.

        Returns ``True`` when the server confirmed the revocation and ``False``
        when it said the grant was already gone (revoked from the account's
        settings, expired, or revoked before). Both leave the user
        disconnected, so neither raises. A refusal for any other reason does
        raise :class:`CredentialError`, and the client is left as it was so
        the call can be retried.

        Afterwards the client does not refresh again: ``get_credentials``
        raises a ``CredentialError`` whose ``reauthorize`` is true, until
        :meth:`reset`, or until a loader returns a refresh token other than the
        revoked one (the user connected again). A ``client_credentials`` client
        only drops its token, since its next one is always to be had.

        Deleting the stored grant stays yours, after this returns.
        """
        revocation = self.server.revocation
        if revocation is None:
            raise DeclarationError(
                f"The server for {self.server.token_endpoint} declares no revocation, so "
                "there is nothing to send. Add revocation=Revocation(...) to the "
                "OAuth2Server if it has a revocation endpoint. Deleting the stored grant "
                "alone leaves it live at the server.",
                docs="reference/oauth#revocation",
            )
        work: Callable[[], Awaitable[bool]]
        if not isinstance(revocation, Revocation):
            work = self._run_revoker
        elif revocation.token_type == "access_token":
            if self._dead_reason is not None and self._load_grant is not None:
                await self._lift_if_reconnected()
            try:
                self._raise_if_grant_is_dead("")
            except CredentialError:
                # The server has already called the grant dead, so no access
                # token can be had to present, and there is nothing left to end.
                self._mark_revoked()
                return False
            work = self._revoke_by_access_token
        else:
            work = self._revoke_held_grant
        # Under the lock a refresh takes, so a refresh in flight lands first and
        # the token revoked is the one it rotated to, and no call waiting on the
        # lock refreshes a grant that has just been revoked.
        async with self._get_lock():
            revoked = await self._under_refresh_lock("", work)
            self._mark_revoked()
        return revoked

    async def _run_revoker(self) -> bool:
        """Hand the server's :class:`Revoker` the grant, with the fields it names."""
        revoker = self.server.revocation
        assert revoker is not None and not isinstance(revoker, Revocation)
        if self._load_grant is not None:
            await self._read_store()
        if any(name not in self._grant_fields for name in revoker.grant_fields):
            # Every token response names them, so ask for one.
            try:
                await self._renew("", adopt_stored=False)
            except CredentialError as exc:
                if not exc.reauthorize:
                    raise
                return False
        missing = [name for name in revoker.grant_fields if name not in self._grant_fields]
        if missing:
            raise CredentialError(
                f"{type(revoker).__name__} needs {', '.join(missing)} from the token "
                f"response, and {self.server.token_endpoint} sent none.",
                docs="reference/oauth#revoker",
            )
        access_token = self._stop_using_token()
        owns_client = self._http is None
        http = self._http or httpx.AsyncClient(timeout=self._timeout)
        try:
            return await revoker.revoke(
                GrantToRevoke(
                    server=self.server,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                    refresh_token=self._refresh_token,
                    access_token=access_token,
                    fields=dict(self._grant_fields),
                    http=http,
                )
            )
        finally:
            if owns_client:
                await http.aclose()

    def _stop_using_token(self) -> Optional[str]:
        """Drop the cached token as a revocation starts, and hand it back.

        Before the request rather than after, so no call in this process is
        given a token being revoked while the server answers, or while a
        Revoker waits for the server to finish. A call that needs one waits on
        the lock the revocation holds, then is told the grant is gone; if the
        revocation fails, it takes the token up again from the store or a
        refresh.
        """
        cached, self._cached = self._cached, None
        return cached.token if cached is not None else None

    def _note_grant_fields(self, payload: Mapping[str, Any]) -> None:
        """Keep the token-response fields the server's :class:`Revoker` will need."""
        revoker = self.server.revocation
        if revoker is None or isinstance(revoker, Revocation):
            return
        for name in revoker.grant_fields:
            value = payload.get(name)
            if isinstance(value, str) and value:
                self._grant_fields[name] = value

    async def _revoke_by_access_token(self) -> bool:
        """Revoke with the freshest access token, renewing it once if the server calls it dead."""
        token = await self._freshest_access_token()
        if token is None:
            return False
        self._stop_using_token()
        revoked = await self._send_revocation(access_token=token)
        if revoked or self.grant != "refresh_token":
            return revoked
        # A token retired by a refresh elsewhere, or ended early, says nothing
        # about the grant. A grant that still renews is still live: revoke it
        # with the new token. Marked refused so the store's copy is not reread.
        self._refused_token = token
        self._cached = None
        token = await self._renewed_access_token()
        if token is None:
            return False
        self._stop_using_token()
        return await self._send_revocation(access_token=token)

    async def _freshest_access_token(self) -> Optional[str]:
        """The store's live token when a loader has one, else the cached one, else a renewal.

        ``None`` when the server calls the grant dead.
        """
        if self._load_grant is not None:
            stored = await self._read_store()
            if stored is not None:
                self._cached = stored
        cached = self._cached
        if cached is not None and not cached.is_expired(self._effective_leeway()):
            return cached.token
        return await self._renewed_access_token()

    async def _renewed_access_token(self) -> Optional[str]:
        """A renewed access token, or ``None`` when the server calls the grant dead."""
        try:
            return (await self._renew("")).token
        except CredentialError as exc:
            if not exc.reauthorize:
                raise
            return None

    async def _revoke_held_grant(self) -> bool:
        """Revoke the refresh token this client holds, or its token if it holds none."""
        cached_token = self._stop_using_token()
        if self.grant == "client_credentials":
            if cached_token is None:
                return False
            # Its token is the whole grant, so a server calling it dead means
            # there is nothing left to revoke, which revoke_token would not
            # take from an access token.
            return await _revoke(
                self.server,
                cached_token,
                "access_token",
                client_id=self._client_id,
                client_secret=self._client_secret,
                timeout=self._timeout,
                client=self._http,
            )
        if self._load_grant is not None:
            await self._read_store()
        return await self._send_revocation(refresh_token=self._refresh_token)

    async def _send_revocation(
        self, *, refresh_token: Optional[str] = None, access_token: Optional[str] = None
    ) -> bool:
        return await revoke_token(
            self.server,
            client_id=self._client_id,
            client_secret=self._client_secret,
            refresh_token=refresh_token,
            access_token=access_token,
            timeout=self._timeout,
            client=self._http,
        )

    def _mark_revoked(self) -> None:
        """Drop the token, and refuse to refresh a grant known to be revoked."""
        self._cached = None
        if self.grant == "client_credentials":
            return
        self._dead_reason = "The grant was revoked with revoke(); the user has to authorize again."
        self._dead_status = None
        self._dead_until = float("inf")
        self._dead_refresh_token = self._refresh_token

    @property
    def refresh_token(self) -> Optional[str]:
        """The current refresh token — which is not necessarily the one passed in.

        A server that rotates hands back a new one on every refresh; Charter adopts
        it. Persist it through ``on_refresh``, or read it from here. With a
        loader, it is ``None`` until the first refresh reads one.
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
        refresh_token: Optional[GrantLoader] = None,
        **kwargs: Any,
    ) -> OAuth2Client:
        """A client seeded from a fresh :meth:`OAuth2Flow.exchange` grant.

        The bridge from acquisition to injection: the grant's access token
        pre-fills the cache, so the first tool call after connecting uses the
        token the exchange just returned instead of spending a refresh.

        ``refresh_token`` is for a host with several processes: pass the
        :data:`GrantLoader` that reads what ``on_refresh`` stores, and a
        ``refresh_lock`` in ``kwargs`` if the server needs one. The grant is
        still what fills the cache; the loader is what later refreshes read.

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
            refresh_token=refresh_token if refresh_token is not None else grant.refresh_token,
            on_refresh=on_refresh,
            **kwargs,
        )
        client._refresh_token = grant.refresh_token
        client._cached = Credentials(token=grant.access_token, expires_at=grant.expires_at)
        client._note_grant_fields(grant.raw)
        # The leeway cap wants the granted lifetime; the exchange response had it.
        client._lifetime_seconds = _granted_lifetime(grant.raw, server)
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
            reauthorize=True,
        )

    def _clear_dead(self) -> None:
        self._dead_reason = None
        self._dead_status = None
        self._dead_until = 0.0
        self._dead_refresh_token = None

    async def _lift_if_reconnected(self) -> None:
        """End the cool-down early if the store holds a grant other than the dead one.

        The cool-down protects the token endpoint, not the store. A user who
        connects again in another process leaves a new grant in the store, and
        this client should use it now rather than repeat a dead error for a
        minute. A store that can't be read leaves the cool-down as it is.
        """
        dead = self._dead_refresh_token
        try:
            await self._read_store()
        except CredentialError:
            self._refresh_token = dead
            return
        if self._refresh_token != dead:
            self._clear_dead()

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

    async def _request_token(self) -> tuple[httpx.Response, tuple[Optional[str], ...]]:
        """One token request, and the credentials it carried, for redaction."""
        data, headers = self._build_request()
        resp = await _post_token_form(
            self.server.token_endpoint,
            data,
            headers,
            client=self._http,
            timeout=self._timeout,
            request_format=self.server.token_request_format,
        )
        return resp, (data.get("refresh_token"), self._client_secret)

    async def _read_store(self) -> Optional[Credentials]:
        """Read the grant through the loader: adopt its refresh token, and return
        its access token if it is still worth sending instead of refreshing."""
        assert self._load_grant is not None
        try:
            value = self._load_grant()
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:
            raise CredentialError(
                f"Reading the stored grant failed: {type(exc).__name__}: {exc}",
                docs="auth/oauth-flow#more-than-one-process",
            ) from exc

        stored: Optional[Credentials] = None
        raw: Mapping[str, Any] = {}
        if isinstance(value, TokenGrant):
            refresh_token = value.refresh_token
            raw = value.raw
            if value.access_token:
                stored = Credentials(token=value.access_token, expires_at=value.expires_at)
        else:
            refresh_token = value
        if not isinstance(refresh_token, str) or not refresh_token:
            raise CredentialError(
                "The refresh_token loader returned no refresh token. It should return "
                "what on_refresh last stored for this grant.",
                docs="auth/oauth-flow#more-than-one-process",
            )
        if refresh_token != self._refresh_token:
            # Another grant than the one the fields were taken with: the user
            # may have connected another account, so they are learnt again.
            self._grant_fields.clear()
        self._refresh_token = refresh_token
        self._note_grant_fields(raw)

        if (
            stored is None
            or stored.token == self._refused_token
            or stored.is_expired(self._effective_leeway())
        ):
            return None
        return stored

    def _adopt(self, stored: Credentials, provider: str) -> Credentials:
        """Use an access token another process obtained and stored."""
        self._cached = stored
        logger.debug(
            "OAuth token for %s taken from the store; no refresh needed",
            provider or self.server.issuer or self.server.token_endpoint,
        )
        return stored

    async def _refresh(self, provider: str) -> Credentials:
        return await self._under_refresh_lock(provider, lambda: self._renew(provider))

    async def _under_refresh_lock(self, provider: str, work: Callable[[], Awaitable[_T]]) -> _T:
        """Run ``work`` holding the refresh lock, when there is one.

        Held across the read, the refresh and on_refresh, so whoever takes it
        next reads what this one stored rather than the token it spent. A
        revocation takes it too, so it ends the grant the store holds rather
        than one another process has just rotated away from.
        """
        if self._refresh_lock is None:
            return await work()
        try:
            lock = self._refresh_lock()
            await lock.__aenter__()
        except Exception as exc:
            raise CredentialError(
                f"Taking the refresh lock failed: {type(exc).__name__}: {exc}",
                provider=provider,
                docs="auth/oauth-flow#a-lock-around-the-refresh",
            ) from exc
        try:
            result = await work()
        except BaseException as exc:
            await self._release(lock, exc)
            raise
        await self._release(lock, None)
        return result

    @staticmethod
    async def _release(lock: AsyncContextManager[Any], exc: Optional[BaseException]) -> None:
        """Release the refresh lock without letting its failure replace the outcome.

        By now the refresh has succeeded or failed on its own terms. A release
        that raises (a Redis lock whose timeout ran out mid-refresh) is logged:
        it must not turn a token that was fetched and stored into an error, nor
        hide the error that is already on its way out.
        """
        try:
            await lock.__aexit__(
                type(exc) if exc else None, exc, exc.__traceback__ if exc else None
            )
        except Exception:
            logger.warning("charter: releasing the refresh lock raised", exc_info=True)

    async def _renew(self, provider: str, adopt_stored: bool = True) -> Credentials:
        if self._load_grant is not None and adopt_stored:
            stored = await self._read_store()
            if stored is not None:
                return self._adopt(stored, provider)

        payload, failure = await self._token_request(provider)
        if failure is not None and failure[1].reauthorize and self._load_grant is not None:
            # Another process may have spent this refresh token and stored its
            # successor while this one was reading. A server that rotates refuses
            # the spent one, so ask the store again before calling the grant dead.
            tried = self._refresh_token
            try:
                stored = await self._read_store()
            except CredentialError:
                # The store can't be read just now. The server's answer stands,
                # and the cool-down below keeps the endpoint from being asked again.
                logger.warning(
                    "charter: rereading the stored grant after %s failed", failure[0], exc_info=True
                )
                stored, self._refresh_token = None, tried
            if stored is not None and adopt_stored:
                return self._adopt(stored, provider)
            if self._refresh_token != tried:
                logger.debug(
                    "OAuth refresh token for %s was spent elsewhere; retrying with the stored one",
                    provider or self.server.issuer or self.server.token_endpoint,
                )
                payload, failure = await self._token_request(provider)

        if failure is not None:
            error = failure[1]
            if error.reauthorize:
                # Dead until somebody re-authorizes. Remember that, so an agent
                # still calling tools does not turn it into a stream of requests.
                self._dead_reason = error.message
                self._dead_status = error.status_code
                self._dead_until = monotonic() + _DEAD_GRANT_COOLDOWN_SECONDS
                self._dead_refresh_token = self._refresh_token
            raise error

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise CredentialError(
                f"{self.server.token_endpoint} returned no access_token.",
                provider=provider,
                docs="auth/authorization-servers",
            )

        lifetime = _granted_lifetime(payload, self.server)
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
        self._note_grant_fields(payload)

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

    async def _token_request(
        self, provider: str
    ) -> tuple[Dict[str, Any], Optional[tuple[str, CredentialError]]]:
        """One token request, read once: the payload, and the OAuth error in it if any."""
        resp, sent = await self._request_token()
        payload = _json_payload(resp, self.server.token_endpoint, provider)
        return payload, _token_failure(
            payload, resp.status_code, provider, sent, _dead_codes(self.server)
        )

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


def _granted_lifetime(payload: Dict[str, Any], server: OAuth2Server) -> Optional[int]:
    """The lifetime the response granted, or the server's declared one if it said nothing."""
    lifetime = _expires_in_seconds(payload.get("expires_in"))
    return lifetime if lifetime is not None else server.default_expires_in


# Last on purpose: flow.py and revocation.py build on the declarations above, so
# importing them at the bottom keeps the one-way dependency visible (each ->
# this module, never the reverse at import time).
from charter.auth.flow import (  # noqa: E402
    AuthorizationRequest,
    OAuth2Flow,
    TokenGrant,
    scopes_for,
    states_match,
)
from charter.auth.revocation import _revoke, revoke_token  # noqa: E402
