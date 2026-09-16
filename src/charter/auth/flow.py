"""
Getting the grant — the two protocol steps, and nothing between them.

The authorization-code grant (RFC 6749 §4.1) has exactly two steps that are
protocol rather than product: build the authorization URL the user is sent to
(§4.1.1, PKCE per RFC 7636), and trade the code that comes back for tokens
(§4.1.3). :class:`OAuth2Flow` is those two steps. Everything between them — the
callback route, the session that holds ``state`` and the PKCE verifier, the
consent UI, where the refresh token is stored — belongs to your web framework,
and the flow object is deliberately stateless between calls so it cannot
quietly grow any of it.

The dangerous part of this flow is not the URL, it is the parameters that fail
silently when omitted. Google without ``access_type=offline`` returns no
refresh token: nothing errors, the integration works for an hour, then dies.
That lore lives on :class:`~charter.auth.OAuth2Server` as
``authorization_params``, and :meth:`OAuth2Flow.exchange` raises a
:class:`~charter.types.errors.CredentialError` naming it when the refresh token
it implies is missing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping, Optional
from urllib.parse import quote, urlencode

import httpx
from pydantic import BaseModel, Field

from charter.auth.oauth import (
    OAuth2Server,
    _client_auth,
    _expires_in_seconds,
    _json_payload,
    _post_token_form,
    _token_failure,
)
from charter.types.errors import CredentialError

if TYPE_CHECKING:
    from charter.tool import Tool

__all__ = [
    "AuthorizationRequest",
    "OAuth2Flow",
    "TokenGrant",
    "scopes_for",
    "states_match",
]

# Parameters neither the server's authorization_params nor extra_params may
# override: identity and the CSRF/PKCE material are set by the flow itself, and
# vendor lore that could smuggle a different client or callback is not lore.
_RESERVED_PARAMS = ("client_id", "redirect_uri", "state")
_RESERVED_PREFIX = "code_challenge"


def _pkce_verifier() -> str:
    """A PKCE code verifier: 32 random bytes, base64url, unpadded (RFC 7636 §4.1)."""
    return base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")


def _pkce_challenge(verifier: str) -> str:
    """The S256 code challenge for a verifier (RFC 7636 §4.2)."""
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def states_match(expected: str, received: str) -> bool:
    """Whether the callback's ``state`` is the one ``authorize()`` issued.

    Verifying ``state`` at the callback is the host's job — it is the CSRF check
    that keeps an attacker from splicing their code into your user's session.
    This does the comparison in constant time (a plain ``==`` leaks how many
    leading characters matched through timing), so the secure compare is one
    obvious call rather than a thing to remember.
    """
    return hmac.compare_digest(expected.encode("utf-8"), received.encode("utf-8"))


def scopes_for(tools: Iterable[Tool]) -> list[str]:
    """The scopes an authorization request must cover to run these tools.

    Reads the ``scopes`` metadata every tool is declared with, deduped in
    first-seen order — so ``scopes_for([*gmail.TOOLS, *gcalendar.TOOLS])`` is
    the consent screen for exactly what the agent can do, kept in lockstep with
    the tool set instead of hand-maintained beside it.
    """
    seen: list[str] = []
    for tool in tools:
        for scope in tool.scopes:
            if scope not in seen:
                seen.append(scope)
    return seen


@dataclass(frozen=True)
class AuthorizationRequest:
    """What :meth:`OAuth2Flow.authorize` hands back: a URL to send, facts to keep.

    Redirect the user to ``url``. Put ``state`` and ``code_verifier`` in your
    session — server-side, keyed to this browser — and produce them again at
    the callback: ``state`` for :func:`states_match`, ``code_verifier`` for
    :meth:`OAuth2Flow.exchange`. The library does not hold them for you,
    because only your framework knows which browser is which.
    """

    url: str
    state: str
    code_verifier: Optional[str]


class TokenGrant(BaseModel):
    """What a code exchange returned — the one moment a refresh token is visible.

    Deliberately not :class:`~charter.auth.Credentials`: that is the
    injection currency, a bearer token and its expiry, handed out on every tool
    call. A grant is what you persist once — the ``refresh_token`` goes to your
    store, and :meth:`~charter.auth.OAuth2Client.from_grant` turns the rest
    into a working provider without spending a refresh.

    ``scopes`` is what the server says was actually granted (users can deselect
    scopes on some consent screens), and ``raw`` is the untouched response body
    for whatever vendor extras came with it.
    """

    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: list[str] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"TokenGrant(scopes={self.scopes!r}, expires_at={self.expires_at!r}, "
            f"refresh_token={'***' if self.refresh_token else None}, access_token=***)"
        )

    # Pydantic renders __str__ from the field values, so an f-string or a bare
    # print of a grant would put both tokens in a log line — which is where a
    # secret is hardest to get back out of. Both spellings mask.
    __str__ = __repr__


class OAuth2Flow:
    """The stateless half of obtaining a grant, for a host serving its own users.

    Registration facts live here — ``client_id``, ``client_secret``,
    ``redirect_uri`` — beside the :class:`~charter.auth.OAuth2Server`
    declaration, the same line the module already draws: what the server *is*
    versus what *your registration* with it says.

    Stateless between calls, as a covenant: :meth:`authorize` returns ``state``
    and the PKCE verifier *to you*, and :meth:`exchange` takes the verifier
    back. Nothing is remembered in between — storage, sessions and routes stay
    the host's, forever.
    """

    def __init__(
        self,
        server: OAuth2Server,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        timeout: int = 20,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not isinstance(server, OAuth2Server):
            raise TypeError("OAuth2Flow requires an OAuth2Server declaration")
        if not client_id:
            raise CredentialError("OAuth2Flow requires a client_id")
        if not client_secret:
            raise CredentialError("OAuth2Flow requires a client_secret")
        if not redirect_uri:
            raise CredentialError(
                "OAuth2Flow requires a redirect_uri — the exact callback URL "
                "registered with the authorization server, never one built from "
                "user input.",
                docs="auth/oauth-flow#security-invariants",
            )
        self.server = server
        self.redirect_uri = redirect_uri
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout = timeout
        self._http = client

    def authorize(
        self,
        scopes: Iterable[str],
        *,
        state: Optional[str] = None,
        login_hint: Optional[str] = None,
        pkce: bool = True,
        extra_params: Optional[Mapping[str, str]] = None,
    ) -> AuthorizationRequest:
        """Build the authorization URL (RFC 6749 §4.1.1). Pure — no I/O, no state.

        PKCE is on by default and S256-only; ``pkce=False`` exists for the rare
        server that rejects unknown parameters, and is never the recommended
        path. ``state`` is generated (``secrets.token_urlsafe(32)``) unless you
        pass your own. Parameters merge later-wins: the standard set, then the
        server's ``authorization_params``, then ``extra_params`` — but neither
        map may override identity (``client_id``, ``redirect_uri``) or the
        CSRF/PKCE material (``state``, ``code_challenge*``).
        """
        scope_list = list(scopes)
        if not scope_list:
            raise CredentialError(
                "authorize() was called with no scopes. An authorization request "
                "for nothing is always a bug upstream — pass "
                "scopes_for(pack.TOOLS), or the scopes your integration needs.",
                docs="reference/oauth#scopes_for",
            )
        endpoint = self.server.authorization_endpoint
        if not endpoint:
            raise CredentialError(
                f"The server for {self.server.token_endpoint} declares no "
                "authorization_endpoint, so it can refresh a grant but not start "
                "one. Add authorization_endpoint to the OAuth2Server declaration.",
                docs="auth/authorization-servers",
            )

        state = state or secrets.token_urlsafe(32)
        params: Dict[str, str] = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scope_list),
            "state": state,
        }
        code_verifier: Optional[str] = None
        if pkce:
            code_verifier = _pkce_verifier()
            params["code_challenge"] = _pkce_challenge(code_verifier)
            params["code_challenge_method"] = "S256"
        if login_hint:
            params["login_hint"] = login_hint

        for source_name, source in (
            ("authorization_params", self.server.authorization_params),
            ("extra_params", extra_params or {}),
        ):
            for key, value in source.items():
                if key in _RESERVED_PARAMS or key.startswith(_RESERVED_PREFIX):
                    raise ValueError(
                        f"{key!r} cannot be set via {source_name}: identity and "
                        "the CSRF/PKCE material belong to the flow itself."
                    )
                params[key] = value

        # quote, not the default quote_plus: a space in `scope` must be %20 —
        # some servers reject the form-encoding "+" in a query string.
        query = urlencode(params, quote_via=quote)
        separator = "&" if "?" in endpoint else "?"
        return AuthorizationRequest(
            url=f"{endpoint}{separator}{query}", state=state, code_verifier=code_verifier
        )

    async def exchange(
        self,
        code: str,
        *,
        code_verifier: Optional[str] = None,
        expect_refresh_token: bool = True,
    ) -> TokenGrant:
        """Trade the callback's code for tokens (RFC 6749 §4.1.3).

        One form POST to the same token endpoint the refresh uses. Codes are
        single-use, so a failed exchange is never retried and no cooldown
        applies — restarting the flow is the host's move.

        ``expect_refresh_token`` defaults to ``True`` because the missing
        refresh token is the silent failure of this entire flow: the exchange
        succeeds, the access token works, and the integration dies within the
        hour. Pass ``False`` only for a server that genuinely never issues one.
        """
        if not code:
            raise CredentialError(
                "exchange() requires the authorization code from the callback."
            )
        data: Dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        auth_fields, headers = _client_auth(
            self.server.token_endpoint_auth_method, self._client_id, self._client_secret
        )
        data.update(auth_fields)

        resp = await _post_token_form(
            self.server.token_endpoint,
            data,
            headers,
            client=self._http,
            timeout=self._timeout,
        )
        payload = _json_payload(resp, self.server.token_endpoint, None)
        failure = _token_failure(payload, resp.status_code, None)
        if failure is not None:
            raise failure[1]

        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise CredentialError(
                f"{self.server.token_endpoint} returned no access_token.",
                docs="auth/authorization-servers",
            )

        raw_refresh = payload.get("refresh_token")
        refresh_token = (
            raw_refresh if isinstance(raw_refresh, str) and raw_refresh else None
        )
        if refresh_token is None and expect_refresh_token:
            raise CredentialError(
                f"{self.server.token_endpoint} returned no refresh_token, so this "
                "connection will die when the access token expires — typically "
                "within the hour, and without an error until then. Most servers "
                "only issue one when the authorization request asks for it: for "
                "Google, declare authorization_params={'access_type': 'offline', "
                "'prompt': 'consent'} on the OAuth2Server. If this server "
                "genuinely never issues refresh tokens, pass "
                "expect_refresh_token=False.",
                docs="auth/oauth-flow#the-failure-this-flow-exists-to-catch",
            )

        lifetime = _expires_in_seconds(payload.get("expires_in"))
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=lifetime)
            if lifetime is not None
            else None
        )
        scope = payload.get("scope")
        return TokenGrant(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scopes=scope.split() if isinstance(scope, str) else [],
            raw=payload,
        )

    def __repr__(self) -> str:
        return (
            f"OAuth2Flow(token_endpoint={self.server.token_endpoint!r}, "
            f"redirect_uri={self.redirect_uri!r}, client_secret=***)"
        )
