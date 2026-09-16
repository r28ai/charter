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
from typing import Any, Dict, Optional, Tuple, Type

__all__ = [
    "CharterError",
    "DeclarationError",
    "CredentialError",
    "ToolValidationError",
    "TransformError",
    "APIError",
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
}


def provider_docs(provider: Optional[str], *, bearer: bool = True) -> str:
    """The page a rejected credential should send the reader to.

    A lookup rather than an f-string: interpolating a provider name would
    generate `auth/providers/stripe` for a page that does not exist, and a dead
    link in an error message is worse than no link at all.

    ``bearer`` picks the fallback when the provider has no page of its own, and
    it is not a detail. `auth/your-own-account` opens by telling anyone using an
    API-key pack to go and read `auth/api-key-tool-factory` instead: there is no
    authorization server, no consent screen and no refresh. Sending a rejected
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


def _rebuild(
    cls: Type[CharterError], args: Tuple[Any, ...], state: Dict[str, Any]
) -> CharterError:
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
    """

    def __init__(
        self,
        message: str,
        *,
        provider: Optional[str] = None,
        status_code: Optional[int] = None,
        docs: Optional[str] = None,
    ) -> None:
        super().__init__(message, docs=docs)
        self.message = message
        self.provider = provider
        self.status_code = status_code

    def __str__(self) -> str:
        if self.provider:
            return self._with_docs(f"[{self.provider}] {self.message}")
        return self._with_docs(self.message)


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
