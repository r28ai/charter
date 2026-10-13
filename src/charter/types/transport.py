# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""How an ``httpx`` transport failure becomes a :class:`~charter.types.errors.NetworkError`.

Every place Charter sends a request — a tool's call and its redirects, a token
request, a revocation — routes its ``httpx.RequestError`` through
:func:`network_error`, so an adapter that catches ``CharterError`` catches a
dropped connection too, and the model reading it is told the same thing
whichever request failed. Separate from :mod:`charter.types.errors` because that
module spells the documentation host and so may import only the standard
library.
"""

from __future__ import annotations

from typing import Optional, Tuple, Type, Union

import httpx

from charter.types.errors import NetworkError

__all__ = ["network_error"]

# What each failure means, in the words a model reads, and whether the request
# can have reached the server. Order matters: the timeouts are checked before
# the broader classes they belong to.
_NEVER_SENT: Tuple[Tuple[Type[httpx.RequestError], str], ...] = (
    (httpx.ConnectTimeout, "timed out connecting"),
    (httpx.PoolTimeout, "timed out waiting for a free connection"),
    (httpx.ConnectError, "could not connect"),
    (httpx.ProxyError, "the proxy refused the connection"),
    (httpx.UnsupportedProtocol, "the URL's scheme is not one httpx can send"),
    (httpx.LocalProtocolError, "the request could not be written"),
)
_MAYBE_SENT: Tuple[Tuple[Type[httpx.RequestError], str], ...] = (
    (httpx.WriteTimeout, "timed out sending the request"),
    (httpx.ReadTimeout, "timed out waiting for the response"),
    (httpx.RemoteProtocolError, "the server closed the connection"),
    (httpx.ReadError, "the connection dropped while reading the response"),
    (httpx.WriteError, "the connection dropped while sending the request"),
    (httpx.DecodingError, "the response could not be decoded"),
)
_DETAIL_LIMIT = 200


def network_error(
    exc: httpx.RequestError,
    url: Union[str, httpx.URL],
    *,
    doing: Optional[str] = None,
) -> NetworkError:
    """The error for ``exc``, raised sending a request to ``url``.

    ``doing`` names the request when it is not the tool's own — "getting an
    access token" — so a model is not told the API was unreachable when it was
    the authorization server. The URL kept on the error has no query string,
    which can carry identifiers.
    """
    parsed = httpx.URL(str(url))
    host = parsed.host or str(url)
    reason, sent = _describe(exc)
    detail = str(exc).strip()
    if detail:
        reason = f"{reason}: {detail[:_DETAIL_LIMIT]}"
    while_ = f" while {doing}" if doing else ""
    if sent:
        message = (
            f"No response from {host}{while_} ({reason}). The request may have reached "
            "the server and taken effect, so check before repeating anything that changes "
            "data. This is a network problem on the tool's side, not a problem with the "
            "arguments."
        )
    else:
        message = (
            f"Could not reach {host}{while_} ({reason}). The request was never sent, so "
            "nothing changed. This is a network problem on the tool's side, not a problem "
            "with the arguments; the same call may work later."
        )
    return NetworkError(
        message,
        url=str(parsed.copy_with(query=None, fragment=None)),
        host=host,
        may_have_taken_effect=sent,
    )


def _describe(exc: httpx.RequestError) -> Tuple[str, bool]:
    """A short reason for ``exc``, and whether the request may have been received."""
    for kind, reason in _NEVER_SENT:
        if isinstance(exc, kind):
            return reason, False
    for kind, reason in _MAYBE_SENT:
        if isinstance(exc, kind):
            return reason, True
    # Anything httpx adds later: assume the worst about whether it was sent.
    return type(exc).__name__, True
