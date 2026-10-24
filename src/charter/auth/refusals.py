# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""How a provider says a token's grant does not cover a call, read into one error.

Every provider says it differently. Google answers 403 with the standard
``WWW-Authenticate: Bearer error="insufficient_scope", scope="…"``; Slack answers
200 with ``{"ok": false, "error": "missing_scope", "needed": "chat:write"}``;
Linear answers "Invalid scope: `write` or `comments:create` required"; GitHub
answers 404 and names what it would accept in ``X-Accepted-OAuth-Scopes``. A host
that handles them one by one writes the same handler eight times.

So a pack declares its provider's shape once, on the factory, the way it declares
an :class:`~charter.types.envelope.Envelope`::

    LINEAR_REFUSAL = ScopeRefusal(
        status={200, 400},
        signal=r"Invalid scope",
        needed=r"Invalid scope:\\s*(.+?)\\s+required",
    )

and every tool built from it raises
:class:`~charter.types.errors.InsufficientScope`, whose ``needed`` is the scopes
to add. The standard header needs no declaration: any response carrying it raises
the same error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import AbstractSet, Any, Callable, Optional, Union

import httpx

from charter.auth.scopes import (
    Kind,
    ScopeRequirement,
    Unavailable,
    _cover,
    _narrowest_first,
    _options,
)
from charter.types.errors import DeclarationError, InsufficientScope

__all__ = ["ScopeRefusal", "bearer_insufficient_scope", "refusal_in"]

_PARAM = re.compile(r'(\w+)="([^"]*)"')


def _names(text: str) -> tuple[str, ...]:
    """Scope names out of a provider's words: backticked, quoted, or a plain list."""
    for quote in (r"`([^`]+)`", r"'([^']+)'", r'"([^"]+)"'):
        found = re.findall(quote, text)
        if found:
            return tuple(dict.fromkeys(found))
    words = [w for w in re.split(r"[,\s]+", text) if w and w.lower() not in ("or", "and")]
    return tuple(dict.fromkeys(words))


def _at(payload: Any, path: str) -> Any:
    for segment in path.split("."):
        if not isinstance(payload, Mapping):
            return None
        payload = payload.get(segment)
    return payload


@dataclass(frozen=True)
class ScopeRefusal:
    """Where a provider says the token's grant does not cover the call.

    Attributes
    ----------
    status:
        The statuses the refusal comes back with: 403 for most, 200 for an API
        that reports failure inside a success (Slack, Shopify), 404 for GitHub,
        which will not say whether a repository it hides exists.
    signal:
        A regular expression the response body must match. Without one, the
        status alone signals, which is right only beside ``held_header``.
    needed:
        A regular expression whose first group, found in the body, names the
        scopes the provider wants: "`write` or `comments:create`".
    needed_field:
        A dotted path in the JSON body to the same: Slack's ``needed``.
    needed_header:
        A response header listing the same, comma- or space-separated.
    held_header:
        A response header listing what the token holds. When it is declared, a
        response is a refusal only if the token holds none of the scopes named:
        GitHub answers a missing repository and an unreadable one with the same
        404, and only the two headers tell them apart.
    alternatives:
        Whether several named scopes are alternatives, any one of which lets the
        call through (Linear, Google, GitHub, Shopify), or all needed. True by
        default; Slack's comma-separated ``needed`` is the exception.
    kind:
        The kind of credential the named scopes belong to, when not the pack's
        default: a Stripe restricted key's ``rak_*`` permissions.
    """

    status: Union[int, AbstractSet[int]] = 403
    signal: Optional[str] = None
    needed: Optional[str] = None
    needed_field: Optional[str] = None
    needed_header: Optional[str] = None
    held_header: Optional[str] = None
    alternatives: bool = True
    kind: Optional[Kind] = None
    _statuses: frozenset[int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        statuses = frozenset({self.status} if isinstance(self.status, int) else self.status)
        if not statuses:
            raise DeclarationError(
                "ScopeRefusal needs the status the refusal comes back with.",
                docs="reference/oauth#scoperefusal",
            )
        if self.signal is None and self.held_header is None:
            raise DeclarationError(
                "A ScopeRefusal with no signal and no held_header would read every "
                f"response with status {sorted(statuses)} as a missing scope. Give the "
                "regular expression that tells this refusal apart.",
                docs="reference/oauth#scoperefusal",
            )
        for pattern in (self.signal, self.needed):
            if pattern is not None:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise DeclarationError(
                        f"ScopeRefusal pattern {pattern!r} is not a regular expression: {exc}.",
                        docs="reference/oauth#scoperefusal",
                    ) from None
        if self.needed is not None and re.compile(self.needed).groups < 1:
            raise DeclarationError(
                f"ScopeRefusal needed={self.needed!r} must capture the scopes in a group.",
                docs="reference/oauth#scoperefusal",
            )
        object.__setattr__(self, "_statuses", statuses)

    def read(self, resp: httpx.Response, payload: Any) -> Optional[tuple[str, ...]]:
        """The scopes named, possibly none, when ``resp`` is this refusal; else None."""
        if resp.status_code not in self._statuses:
            return None
        text = resp.text or ""
        if self.signal is not None and not re.search(self.signal, text):
            return None
        named: tuple[str, ...] = ()
        if self.needed is not None:
            match = re.search(self.needed, text)
            if match:
                named = _names(match.group(1))
        if not named and self.needed_field is not None:
            value = _at(payload, self.needed_field)
            if isinstance(value, str):
                named = _names(value)
            elif isinstance(value, Sequence):
                named = tuple(str(v) for v in value)
        if not named and self.needed_header is not None:
            named = _names(resp.headers.get(self.needed_header, ""))
        if self.held_header is not None:
            # No header means another kind of token, which says nothing here: a
            # fine-grained GitHub token is sent no X-OAuth-Scopes at all. Nothing
            # named means nothing to compare. Either way the 404 is the API's own.
            if self.held_header not in resp.headers or not named:
                return None
            if set(_names(resp.headers[self.held_header])) & set(named):
                return None
        return named

    def held(self, resp: httpx.Response) -> Optional[tuple[str, ...]]:
        if self.held_header is None:
            return None
        return _names(resp.headers.get(self.held_header, ""))


def bearer_insufficient_scope(resp: httpx.Response) -> Optional[tuple[str, ...]]:
    """The scopes an RFC 6750 ``insufficient_scope`` challenge names, or None.

    ``WWW-Authenticate: Bearer error="insufficient_scope", scope="a b"``. The
    standard calls ``scope`` the scope required; Google lists every scope that
    would do, so several are read as alternatives and the tool's declaration
    decides which is narrowest.
    """
    challenge = resp.headers.get("www-authenticate", "")
    if not challenge.lower().startswith("bearer"):
        return None
    params = dict(_PARAM.findall(challenge))
    if params.get("error") != "insufficient_scope":
        return None
    return tuple(dict.fromkeys(params.get("scope", "").split()))


def refusal_in(
    resp: httpx.Response,
    payload: Any,
    refusals: Sequence[ScopeRefusal],
    *,
    requirements: Optional[Callable[[Optional[Kind]], Sequence[ScopeRequirement]]] = None,
    tool_name: str = "this tool",
    provider: Optional[str] = None,
) -> Optional[InsufficientScope]:
    """The :class:`InsufficientScope` to raise when ``resp`` is a scope refusal, else None.

    ``requirements(kind)`` is what the tool declares under ``kind``. Of several
    scopes the provider would accept, the narrowest the tool lists comes first:
    Google names legacy aliases and ``drive.file`` beside the scope a reader
    needs, and the declaration knows which is which. When the provider names
    nothing, the declaration answers, less anything the token is known to hold.
    """
    standard = bearer_insufficient_scope(resp)
    if standard is not None:
        found: Optional[tuple[tuple[str, ...], bool, Optional[Kind], Optional[tuple[str, ...]]]] = (
            standard,
            True,
            None,
            None,
        )
    else:
        found = None
        for refusal in refusals:
            named = refusal.read(resp, payload)
            if named is not None:
                found = (named, refusal.alternatives, refusal.kind, refusal.held(resp))
                break
    if found is None:
        return None
    named, alternatives, kind, held = found

    declared: list[tuple[str, ...]] = []
    cannot: Optional[str] = None
    if requirements is not None:
        try:
            listed = list(requirements(kind))
        except DeclarationError:
            listed = []
        declared = [o for o in (_options(r) for r in listed) if o]
        cannot = next((r.reason for r in listed if isinstance(r, Unavailable)), None)
    try:
        rank = {scope: i for i, scope in enumerate(_narrowest_first(declared))}
    except DeclarationError:
        rank = {}

    words = _sentence(_provider_words(resp, payload))
    under = f" for {kind}" if kind is not None else ""
    if named and alternatives:
        known = sorted((s for s in named if s in rank), key=rank.__getitem__)
        needed = known[:1] or list(named[:1])
        message = f"{words} Add: {', '.join(needed)}{under}."
    elif named:
        needed = [s for s in named if not held or s not in held]
        message = f"{words} Add: {', '.join(needed)}{under}."
    else:
        have = set(held or ())
        needed = _cover([c for c in declared if not have & set(c)])
        if needed:
            message = (
                f"{words} The provider named no scope; {tool_name} declares "
                f"{', '.join(needed)}{under}."
            )
        elif cannot is not None:
            message = f"{words} {tool_name} cannot run with this credential: {cannot}."
        else:
            message = words
    return InsufficientScope(
        message,
        provider=provider,
        status_code=resp.status_code if resp.status_code >= 400 else 403,
        needed=needed,
        accepted=named if alternatives else (),
        kind=kind,
    )


def _sentence(text: str) -> str:
    """The provider's words, ending as a sentence ends, so more can follow."""
    text = text.strip()
    return text if not text or text[-1] in ".!?" else f"{text}."


def _provider_words(resp: httpx.Response, payload: Any) -> str:
    """The provider's own sentence about the refusal, as short as it comes."""
    if isinstance(payload, Mapping):
        for path in ("error.message", "message", "errors.0.message", "error"):
            node: Any = payload
            for segment in path.split("."):
                if isinstance(node, Mapping):
                    node = node.get(segment)
                elif isinstance(node, list) and segment.isdigit() and len(node) > int(segment):
                    node = node[int(segment)]
                else:
                    node = None
            if isinstance(node, str) and node:
                return node
    return resp.reason_phrase or "insufficient scope"
