# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Exception hierarchy for Charter.

Every error raised by the library derives from :class:`CharterError`, so a host
application can catch the whole surface with a single ``except CharterError``.

The design replaces the closed-source runtime's control-flow interrupts: rather
than the library deciding what to do about an expired token or a rejected input,
it raises a typed exception and the host application decides.

Some errors carry a ``docs`` slug, which renders into a link when the error is
printed. The rule for when one is set: a link is for a *procedure* the message
could never contain — registering an OAuth app, choosing scopes, standing up a
callback route — never for a fix the message already states. "Pass the header"
needs no link; "obtain a refresh token from Google" is three screens of setup.
`ToolValidationError` carries none at all, and cannot be given one: it is written
to be handed straight back to a model, which pays for the URL in context and
cannot follow it. The adapters do return a `CredentialError` to the loop as text,
link included, and that is deliberate rather than an oversight — nothing in the
loop can fix a missing credential, so the reader who matters is the person
reading the trace afterwards, and the link is what they need next.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Sequence, Tuple, Type

__all__ = [
    "CharterError",
    "DeclarationError",
    "CredentialError",
    "InsufficientScope",
    "ToolValidationError",
    "ContextError",
    "TransformError",
    "APIError",
    "NetworkError",
    "unexpected_failure_text",
]

_EXCERPT_LIMIT = 500

DOCS_BASE = "https://docs.r28.ai/charter/"
"""Where a ``docs`` slug is rendered against. The one place a URL is spelled."""

_DOCS_LINK = re.compile(r"\s+See\s+" + re.escape(DOCS_BASE) + r"\S*")


def strip_docs_links(text: str) -> str:
    """``text`` with any rendered documentation link removed.

    A nested error can carry one into a message bound for a model: pydantic
    turns a `ValueError` raised inside a validator into a `ValidationError`
    whose text quotes it verbatim, and `Value` is filled in by the model, so a
    link on that validator would surface in the tool result. Stripping here
    makes "model-facing errors carry no link" a property of the class rather
    than a rule each raise site has to remember.
    """
    return _DOCS_LINK.sub("", text)


_PROVIDER_PAGES = {
    "google": "auth/providers/google",
    "slack": "auth/providers/slack",
    "github": "auth/providers/github",
    # The key packs. Each reads its key through a credential provider, so that
    # one process can hold a key per user, which makes the call look like a
    # bearer call; what the reader of a refused key needs is still where the key
    # comes from, and that is its pack page's own section.
    "stripe": "packs/stripe#authenticating",
    "linear": "packs/linear#authenticating",
    "granola": "packs/granola#authenticating",
    "firecrawl": "packs/firecrawl#authenticating",
    "tavily": "packs/tavily#authenticating",
    "luma": "packs/luma#authenticating",
}


def provider_docs(provider: Optional[str], *, bearer: bool = True) -> str:
    """The page a rejected credential should send the reader to.

    A lookup rather than an f-string: interpolating a provider name would
    generate `auth/providers/stripe` for a page that does not exist, and a dead
    link in an error message is worse than no link at all.

    ``bearer`` picks the fallback when the provider has no page of its own, and
    it is not a detail. `auth/your-own-account` is where a credential comes from
    — a table of every pack and the page that issues its credential — and it
    sends anyone using an API-key pack on to `auth/api-key-tool-factory`: there
    is no authorization server, no consent screen and no refresh. Sending a rejected
    Stripe key to a page whose second paragraph says it is not for you is a live
    link pointing the wrong way, which is the failure this whole mechanism is
    supposed to avoid.
    """
    page = _PROVIDER_PAGES.get(provider or "")
    if page is not None:
        return page
    return "auth/your-own-account" if bearer else "auth/api-key-tool-factory"


class CharterError(Exception):
    """Base class for every error raised by Charter.

    Attributes
    ----------
    docs:
        A documentation slug — ``"auth/oauth-flow#refresh-tokens"`` — or ``None``.
        A slug rather than a URL, for three reasons: moving a page is one edit
        instead of a grep across every raise site, a test can resolve every slug
        against the docs tree so a link cannot rot silently, and a host piping
        errors into a log or back into a model can drop the URL by ignoring the
        field rather than by parsing it back out of a string.
    """

    docs: Optional[str] = None

    def __init__(self, *args: Any, docs: Optional[str] = None) -> None:
        super().__init__(*args)
        self.docs = docs

    @property
    def docs_url(self) -> Optional[str]:
        """The rendered link, or ``None``. Appending ``.md`` gets the markdown."""
        return f"{DOCS_BASE}{self.docs}" if self.docs else None

    def _with_docs(self, text: str) -> str:
        """``text``, with the link appended when there is one."""
        url = self.docs_url
        return f"{text} See {url}" if url else text

    def __str__(self) -> str:
        return self._with_docs(super().__str__())

    def __reduce__(self) -> Any:
        # Exception's default pickling replays `cls(*self.args)`, which breaks on
        # any subclass with a required keyword: `APIError("boom")` is a TypeError
        # because `status_code` is missing. A host running tools in a process
        # pool or a task queue gets that TypeError instead of its error. Rebuild
        # from the instance dict instead, which also carries `provider`,
        # `retry_after` and `docs` across intact.
        return (_rebuild, (type(self), self.args, self.__dict__))


def _rebuild(cls: Type[CharterError], args: Tuple[Any, ...], state: Dict[str, Any]) -> CharterError:
    """Reconstruct an error without going through its ``__init__``."""
    error = cls.__new__(cls)
    Exception.__init__(error, *args)
    error.__dict__.update(state)
    return error


class DeclarationError(CharterError, ValueError):
    """A schema, marker or pack was declared in a shape the runtime cannot use.

    It names *whose* mistake this is, not when it surfaced. Most are raised while
    a tool is built or a declaration validated — a `Pagination` naming half a
    style, an `Envelope` that can never detect a failure, a factory given both
    kinds of credential. Some cannot be detected until a request is assembled and
    so come out of ``ainvoke``: a field with no `Path()`/`Query()`/`Body()`
    marker, a body that will not form-encode, an unconfigured pack host. Either
    way the fix is in the declaration and the reader is its author, which is why
    these carry a ``docs`` slug where an error written for a model does not.

    So it is not enough to guard only the declaration. A host that catches
    `ToolValidationError`, `CredentialError` and `APIError` around a call and
    nothing else will let this one escape; ``except CharterError`` catches it.

    Also a ``ValueError``, deliberately. Several of these are raised inside a
    pydantic validator, which converts ``ValueError`` and nothing else, and a
    host that already catches ``ValueError`` around a declaration keeps working.
    Catching ``CharterError`` catches them too.
    """


class CredentialError(CharterError):
    """Credentials for a provider are missing, expired, or were rejected.

    The library never re-authenticates on its own: it raises this so the host
    application can run whatever OAuth flow it owns and retry.

    Attributes
    ----------
    provider:
        Name of the provider whose credentials failed (e.g. ``"google"``), or
        ``None`` when the failure is not attributable to a specific provider.
    status_code:
        The HTTP status that triggered this, when it came from a response
        (``401`` by default; see ``credential_statuses``). ``None`` when the
        credentials were missing locally or a refresh failed.
    token_refused:
        Whether the API refused the token itself, so whatever issued it should
        drop it and fetch another. True for a credential status and for an
        envelope's ``credential_errors``. False for an envelope's
        ``permission_errors`` — the token works and may not do this, which no
        refresh changes — and for a failure raised before any request.
    reauthorize:
        Whether the grant itself is gone, so nothing but the user authorizing
        again brings it back: the token endpoint answered ``invalid_grant``, or
        a code its server declares in ``dead_grant_errors``. This is the one to
        show a reconnect button for. False for everything else, including a
        refused access token, which the next call replaces by refreshing.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        docs: Optional[str] = None,
        token_refused: Optional[bool] = None,
        reauthorize: bool = False,
    ) -> None:
        super().__init__(message, docs=docs)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        # A status means a response, and a response refusing credentials refused
        # this token, unless the raiser says the token is not what was wrong.
        self.token_refused = status_code is not None if token_refused is None else token_refused
        self.reauthorize = reauthorize

    def __str__(self) -> str:
        if self.provider:
            return self._with_docs(f"[{self.provider}] {self.message}")
        return self._with_docs(self.message)


class InsufficientScope(CredentialError):
    """The token works, and what it was granted does not cover this call.

    One error for every provider, however the provider says it: Google's
    ``WWW-Authenticate: Bearer error="insufficient_scope"``, Slack's
    ``missing_scope`` inside a 200, Linear's "Invalid scope: `write` required",
    GitHub's 404 beside ``X-Accepted-OAuth-Scopes``. Each pack declares its
    provider's shape once, as a ``ScopeRefusal``; the standard header needs no
    declaration at all.

    ``token_refused`` is always False: the token is kept, because a refresh
    returns the same grant. The fix is a wider grant, or another credential.

    Attributes
    ----------
    needed:
        The scopes to add so this call runs, narrowest first. What the provider
        named when it named something, read against the tool's own declaration
        so that of several it would accept the narrowest the tool lists comes
        first; what the tool declares when the provider names nothing.
    accepted:
        Every scope the provider said would let the call through, any one of
        which will do, in the provider's order. Empty when it named none.
    kind:
        The kind of credential the scopes belong to, when it is not the pack's
        default — a Stripe restricted key's permission, say.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        status_code: Optional[int] = 403,
        docs: Optional[str] = "reference/errors#insufficientscope",
        needed: Sequence[str] = (),
        accepted: Sequence[str] = (),
        kind: Optional[Any] = None,
    ) -> None:
        super().__init__(
            message, provider=provider, status_code=status_code, docs=docs, token_refused=False
        )
        self.needed = list(needed)
        self.accepted = tuple(accepted)
        self.kind = kind


class ToolValidationError(CharterError):
    """The arguments supplied for a tool call did not satisfy its schema.

    The message is written to be handed straight back to an LLM as the tool
    result, so it names the offending fields and how to fix them. That is also
    why this one takes no ``docs`` slug: the reader is a model mid-loop, which
    cannot follow a link and pays for it in context either way.

    Attributes
    ----------
    tool_name:
        Name of the tool whose input failed validation, when known.
    errors:
        The structured per-field errors, when available.
    """

    def __init__(
        self,
        message: str,
        *,
        tool_name: Optional[str] = None,
        errors: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        message = strip_docs_links(message)
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.errors = [
            {k: strip_docs_links(v) if isinstance(v, str) else v for k, v in error.items()}
            for error in (errors or [])
        ]

    def __str__(self) -> str:
        return self.message


class ContextError(CharterError):
    """The host's ``context`` for a call lacks a value a tool needs, or holds a wrong one.

    Raised for a ``FromContext`` field before any request is built, and before any
    rule reads it, so a rule never runs on a value the host did not supply. The
    mistake is the host's, not the model's, and the message says so: the adapters
    hand a :class:`CharterError` back to the model as the tool's result, and a
    model told only that a field is missing would try to supply it.

    Attributes
    ----------
    tool_name:
        The tool that was called.
    field:
        The ``FromContext`` field whose value was missing or invalid.
    key:
        The key the host was expected to pass it under.
    """

    def __init__(self, message: str, *, tool_name: str, field: str, key: str) -> None:
        super().__init__(message, docs="tools/wire-contract#per-call-context")
        self.tool_name = tool_name
        self.field = field
        self.key = key


class TransformError(CharterError):
    """A ``Format`` transform could not be resolved or failed while running.

    Attributes
    ----------
    transform:
        Name of the transform, as written in the ``Format`` marker.
    field:
        The field the transform was applied to, when known.
    """

    def __init__(
        self,
        message: str,
        *,
        transform: Optional[str] = None,
        field: Optional[str] = None,
        docs: Optional[str] = None,
    ) -> None:
        super().__init__(message, docs=docs)
        self.message = message
        self.transform = transform
        self.field = field

    def __str__(self) -> str:
        if self.field:
            return self._with_docs(f"{self.message} (field: {self.field})")
        return self._with_docs(self.message)


class APIError(CharterError):
    """The upstream API returned a non-success status.

    No ``docs`` slug: the failure is the API's, and Charter's documentation has
    nothing to say about it that the status and body do not. ``retry_after``
    carries what a host actually needs.

    Attributes
    ----------
    status_code:
        The HTTP status code returned by the API.
    body:
        An excerpt of the response body, truncated to keep it safe to pass into
        an LLM context window.
    url:
        The request URL, when known.
    retry_after:
        Seconds the server asked the caller to wait, from a ``Retry-After``
        header. Present on most 429s and some 503s. Charter never retries — this is
        the information a host application needs to decide whether and when to.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        body: str = "",
        url: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body[:_EXCERPT_LIMIT]
        self.url = url
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [f"HTTP {self.status_code}"]
        if self.url:
            parts.append(self.url)
        parts.append(self.message)
        if self.retry_after is not None:
            parts.append(f"retry after {self.retry_after}s")
        if self.body:
            parts.append(f"body: {self.body}")
        return " — ".join(parts)


class NetworkError(CharterError):
    """The request got no usable answer: the connection failed, dropped or timed out.

    Nothing was learned about the call itself — the arguments, the credentials
    and the API may all be fine — so the message says that, for the model that
    reads it as a tool result: no change to the call fixes this. It also says
    whether the request can have taken effect, which is what decides whether
    repeating it is safe. A connection that never opened changed nothing; a
    timeout waiting for the response may have followed a message being sent.

    Charter never retries. ``may_have_taken_effect`` is what a host needs to
    decide whether to, and the original ``httpx`` exception is ``__cause__``.
    Built by :func:`charter.types.transport.network_error`, which holds the
    ``httpx`` half: this module may import only the standard library.

    Attributes
    ----------
    url:
        The request URL without its query string, which can carry identifiers.
    host:
        The host that could not be reached.
    may_have_taken_effect:
        False when the request cannot have reached the server (the connection
        never opened), True when it may have been received and acted on.
    """

    def __init__(
        self,
        message: str,
        *,
        url: Optional[str] = None,
        host: Optional[str] = None,
        may_have_taken_effect: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.url = url
        self.host = host
        self.may_have_taken_effect = may_have_taken_effect

    def __str__(self) -> str:
        return self.message


def unexpected_failure_text(tool_name: str, exc: BaseException) -> str:
    """What a model is told when a tool failed with something that is not a CharterError.

    A :class:`CharterError` is written to be read, and the adapters hand its own
    message back. Anything else is a bug — in Charter, in a pack, or in host code
    the call ran through, such as a credential provider or a response handler —
    and its text was written for nobody: it can quote internal state, and it
    tells a model nothing about what to do. So the model gets the exception's
    type, the fact that its arguments were not the cause, and what to do instead
    of retrying; the adapter logs the traceback for whoever runs the host.
    """
    return (
        f"The tool {tool_name} failed on its side ({type(exc).__name__}). This was not "
        "caused by the arguments, and changing or repeating the call will not fix it. "
        "Tell the user this tool is not working right now; the details are in the "
        "host's log."
    )
