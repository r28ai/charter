# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Ending a grant — the disconnect button, as one request.

Connecting a user is two protocol steps (:mod:`charter.auth.flow`); disconnecting
one is a third. RFC 7009 makes it one POST of the refresh token to a revocation
endpoint, after which the grant is gone at the server and the app no longer
appears in the user's list of connected apps. Deleting the stored token alone
leaves that grant alive, with every scope it was given, until it expires on its
own — for Google, never.

What varies between servers is declared on
:class:`~charter.auth.Revocation`, beside the token endpoint's own departures,
so this module holds one request and no vendor code. Which request goes out,
and what counts as "already gone", are the declaration's.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union
from urllib.parse import quote

import httpx

from charter.auth.oauth import (
    GrantToRevoke,
    OAuth2Server,
    Revocation,
    Revoker,
    _client_auth,
    _error_parts,
    _json_body,
    _redact,
)
from charter.types.errors import CredentialError, DeclarationError

__all__ = ["revoke_token"]

# RFC 6750's code for a token that is not valid, which is Google's answer, and
# RFC 6749's for a grant that is gone. Either means there is nothing left to
# revoke. RFC 7009 itself answers 200 for a token it does not know (§2.2), so a
# server that follows it never says so.
_ALWAYS_GONE = ("invalid_token", "invalid_grant")


async def revoke_token(
    server: OAuth2Server,
    *,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    fields: Optional[Mapping[str, str]] = None,
    timeout: int = 20,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Revoke a grant you hold as a string, without building a client.

    For a token that never refreshes — a Slack bot token from an app without
    rotation, a classic GitHub OAuth token — and for a disconnect handler that
    has a stored row rather than a live :class:`~charter.auth.OAuth2Client`.
    A client's own :meth:`~charter.auth.OAuth2Client.revoke` calls this.

    Pass what you have. A server that revokes by refresh token (RFC 7009, the
    default) is sent ``refresh_token`` when given, since that ends the whole
    grant, and ``access_token`` otherwise. A server declared with
    ``token_type="access_token"`` needs ``access_token``, and a live one:
    the endpoint authenticates with it. A server whose revocation is a
    :class:`~charter.auth.Revoker` is handed ``fields``, the token-response
    fields it names, such as Stripe's ``stripe_user_id``.

    Returns ``True`` when the server confirmed the revocation and ``False`` when
    it said the token was already dead, which a disconnect can treat as done.
    Raises :class:`~charter.types.errors.CredentialError` when the server refused
    for any other reason, and
    :class:`~charter.types.errors.DeclarationError` when ``server`` declares no
    revocation.

    An access token sent in place of the refresh token is the exception. When
    the server calls it dead, that says nothing about the grant: an access token
    lapses within the hour while the refresh token it came from stays live, and
    Google answers a lapsed one exactly as it answers a revoked one. So that
    raises ``CredentialError`` rather than returning ``False``.
    """
    revocation = _declared(server)
    if not isinstance(revocation, Revocation):
        return await _run(
            revocation,
            server,
            refresh_token,
            access_token,
            client_id,
            client_secret,
            fields,
            timeout,
            client,
        )
    if revocation.token_type == "access_token":
        token = access_token
        if not token:
            raise CredentialError(
                f"{revocation.endpoint} revokes a grant given an access token, and "
                "none was passed. A refresh token cannot be presented there; "
                "OAuth2Client.revoke() refreshes first when its token has lapsed.",
                docs="reference/oauth#revoke_token",
            )
    else:
        token = refresh_token or access_token
        if not token:
            raise CredentialError(
                "revoke_token() needs the refresh_token or the access_token to revoke.",
                docs="reference/oauth#revoke_token",
            )

    sent_refresh = revocation.token_type == "refresh_token" and bool(refresh_token)
    revoked = await _revoke(
        server,
        token,
        "refresh_token" if sent_refresh else "access_token",
        client_id=client_id,
        client_secret=client_secret,
        timeout=timeout,
        client=client,
    )
    if not revoked and revocation.token_type == "refresh_token" and not sent_refresh:
        raise CredentialError(
            f"{revocation.endpoint} called the access token dead, which says nothing "
            "about the grant: an access token lapses while the refresh token it came "
            "from stays live. Pass refresh_token to revoke the grant itself.",
            docs="reference/oauth#revoke_token",
        )
    return revoked


async def _run(
    revoker: Revoker,
    server: OAuth2Server,
    refresh_token: Optional[str],
    access_token: Optional[str],
    client_id: Optional[str],
    client_secret: Optional[str],
    fields: Optional[Mapping[str, str]],
    timeout: int,
    client: Optional[httpx.AsyncClient],
) -> bool:
    """Hand a :class:`~charter.auth.Revoker` the grant held as strings."""
    supplied = {name: value for name, value in (fields or {}).items() if value}
    missing = [name for name in revoker.grant_fields if name not in supplied]
    if missing:
        raise CredentialError(
            f"{type(revoker).__name__} ends a grant given {', '.join(missing)} from the "
            "token response; pass it in fields.",
            docs="reference/oauth#revoke_token",
        )
    if not client_id or not client_secret:
        raise CredentialError(
            f"{type(revoker).__name__} authenticates as the app, so it needs client_id "
            "and client_secret: the ones the grant was issued to.",
            docs="reference/oauth#revoke_token",
        )
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        return await revoker.revoke(
            GrantToRevoke(
                server=server,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                access_token=access_token,
                fields=supplied,
                http=http,
            )
        )
    finally:
        if owns_client:
            await http.aclose()


def _declared(server: OAuth2Server) -> Union[Revocation, Revoker]:
    """The server's revocation, or the error saying it declares none."""
    if server.revocation is None:
        raise DeclarationError(
            f"The server for {server.token_endpoint} declares no revocation. Add "
            "revocation=Revocation(...) to the OAuth2Server if it has a revocation "
            "endpoint. Deleting the stored grant alone leaves it live at the server.",
            docs="reference/oauth#revocation",
        )
    return server.revocation


async def _revoke(
    server: OAuth2Server,
    token: str,
    token_type: str,
    *,
    client_id: Optional[str],
    client_secret: Optional[str],
    timeout: int,
    client: Optional[httpx.AsyncClient],
) -> bool:
    """Send ``token`` to the server's revocation endpoint and read the answer.

    ``False`` means the server called *this token* dead. Whether that means the
    grant is gone is the caller's to say: it does for a refresh token, and for
    a ``client_credentials`` token, which is the whole grant.
    """
    revocation = _declared(server)
    assert isinstance(revocation, Revocation)
    auth_method = revocation.auth_method or server.token_endpoint_auth_method
    needs_client = auth_method != "none" or "{client_id}" in revocation.endpoint
    if needs_client and not (client_id and (client_secret or auth_method == "none")):
        raise CredentialError(
            f"Revoking at {revocation.endpoint} authenticates the client, so it needs "
            "client_id and client_secret: the ones the grant was issued to.",
            docs="reference/oauth#revoke_token",
        )

    if auth_method == "none":
        data: Dict[str, str] = {}
        headers: Dict[str, str] = {"Accept": "application/json"}
    else:
        assert client_id is not None and client_secret is not None  # checked above
        data, headers = _client_auth(auth_method, client_id, client_secret)

    if revocation.token_header is not None:
        if revocation.token_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {token}"
        else:
            headers[revocation.token_header] = token
    else:
        data[revocation.token_field or "token"] = token
        if revocation.token_type_hint:
            data["token_type_hint"] = token_type

    url = revocation.endpoint
    if "{client_id}" in url:
        url = url.replace("{client_id}", quote(client_id or "", safe=""))

    request_format = revocation.request_format or server.token_request_format
    body: Dict[str, Any] = {}
    if data:
        body = {"json": data} if request_format == "json" else {"data": data}

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        resp = await http.request(revocation.http_method, url, headers=headers, **body)
    finally:
        if owns_client:
            await http.aclose()

    return _outcome(resp, server, url, (token, client_secret))


def _outcome(
    resp: httpx.Response, server: OAuth2Server, url: str, sent: tuple[Optional[str], ...]
) -> bool:
    """``True`` for a revocation, ``False`` for a token already dead; raise otherwise.

    The failure is read as the token endpoint's is: an ``error`` field counts
    whatever the status, because Slack answers ``{"ok": false, ...}`` in a 200.
    The code and explanation come from whichever error shape the server uses.
    """
    revocation = server.revocation
    assert isinstance(revocation, Revocation)
    code, description = _error_parts(_json_body(resp), resp.status_code)

    if resp.status_code < 300 and code is None:
        return True

    gone = (*_ALWAYS_GONE, *server.dead_grant_errors, *revocation.gone_errors)
    if (
        (code is not None and code in gone)
        or resp.status_code in revocation.gone_statuses
        # The token was the request's own credential, and the request was
        # refused as unauthenticated: the token is what is dead.
        or (revocation.token_header is not None and resp.status_code == 401)
    ):
        return False

    message = f"Revocation at {url} failed: {code or f'HTTP {resp.status_code}'}"
    if description:
        message = f"{message} — {description}"
    raise CredentialError(
        _redact(message, sent),
        status_code=resp.status_code if resp.status_code >= 400 else None,
        token_refused=False,
        docs="reference/oauth#revoke_token",
    )
