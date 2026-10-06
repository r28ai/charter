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

from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from charter.auth.oauth import OAuth2Server, _client_auth, _redact
from charter.types.errors import CredentialError, DeclarationError

__all__ = ["revoke_token"]

# RFC 7009 §2.2.1 for a token the server does not recognise, and RFC 6749's
# code for a grant that is gone. Either means there is nothing left to revoke.
_ALWAYS_GONE = ("invalid_token", "invalid_grant")


async def revoke_token(
    server: OAuth2Server,
    *,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
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
    the endpoint authenticates with it.

    Returns ``True`` when the server confirmed the revocation and ``False`` when
    it said the token was already dead, which a disconnect can treat as done.
    Raises :class:`~charter.types.errors.CredentialError` when the server refused
    for any other reason, and
    :class:`~charter.types.errors.DeclarationError` when ``server`` declares no
    revocation.
    """
    revocation = server.revocation
    if revocation is None:
        raise DeclarationError(
            f"The server for {server.token_endpoint} declares no revocation. Add "
            "revocation=Revocation(...) to the OAuth2Server if it has a revocation "
            "endpoint; if it has none, deleting the stored grant is the whole of "
            "disconnecting.",
            docs="reference/oauth#revocation",
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
    Notion names its code ``code`` and its text ``message``, and GitHub's API
    gives a ``message`` alone, so both are read for the explanation.
    """
    revocation = server.revocation
    assert revocation is not None
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    error = payload.get("error")
    if not isinstance(error, str) or not error:
        error = payload.get("code") if resp.status_code >= 400 else None
    code = error if isinstance(error, str) and error else None

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
    description = payload.get("error_description") or payload.get("message")
    if isinstance(description, str) and description:
        message = f"{message} — {description}"
    raise CredentialError(
        _redact(message, sent),
        status_code=resp.status_code if resp.status_code >= 400 else None,
        token_refused=False,
        docs="reference/oauth#revoke_token",
    )
