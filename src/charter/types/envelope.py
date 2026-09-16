"""
Envelopes — where an API hides failure inside a success.

Not every API uses the HTTP status line to say a call failed. Slack answers a
rejected request with ``200 OK`` and ``{"ok": false, "error": "channel_not_found"}``.
Every GraphQL API returns ``200`` with an ``errors`` array. A long tail of
services answer ``200`` with ``{"status": "error"}``.

A runtime that trusts the status code hands those bodies back as successes, and
the model reports the message sent. So the success predicate has to be part of
the contract, like everything else: declared once per API, enforced on every call.

    from charter import Envelope, oauth_tool_factory

    slack = oauth_tool_factory(
        base_url="https://slack.com/api/",
        provider="slack",
        credential_provider=provider,
        envelope=Envelope(
            ok_field="ok",
            error_field="error",
            credential_errors={"invalid_auth", "token_revoked"},
        ),
    )

Every tool built from that factory now raises ``CredentialError`` or ``APIError``
on a failed body, exactly as it would on a 4xx. Nothing to remember per tool.

**Failure is not always at the root.** A GraphQL mutation the server understood
and then declined does not populate ``errors`` — that array is for problems with
the *document*. The refusal sits inside the payload, one level below the
operation name: Linear's ``{"data": {"issueCreate": {"success": false}}}``,
Shopify's ``{"data": {"productCreate": {"userErrors": [...]}}}``. Every other
signal says the write happened.

So the field names here are *paths*, and a path may contain ``*`` to stand for
"whichever operation this tool called"::

    Envelope(
        errors_field=("errors", "data.*.userErrors"),
    )

One declaration on the factory, and every mutation in the pack is covered —
including the one somebody adds next year without reading this file. That is the
whole point of declaring it rather than writing it: there is no per-tool step to
forget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    AbstractSet,
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from charter.types.errors import (
    APIError,
    CredentialError,
    DeclarationError,
    provider_docs,
)

__all__ = ["Envelope", "GRAPHQL_ENVELOPE"]

_BODY_EXCERPT = 500

FieldPath = Union[str, Sequence[str]]
"""One dotted path, or several. ``*`` matches any key at that level."""


def _frozen(values: Iterable[str]) -> FrozenSet[str]:
    return frozenset(values)


def _paths(value: Optional[FieldPath]) -> Tuple[str, ...]:
    """Normalise one path or a sequence of them to a tuple."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _collect(payload: Any, path: str) -> List[Tuple[str, Any]]:
    """Every ``(concrete_path, value)`` reachable at ``path``.

    A ``*`` segment matches every key at that level, so ``data.*.userErrors``
    finds the mutation payload without the envelope having to know which
    operation the tool called. Returns an empty list when nothing matches, which
    is what lets a caller tell "the API said false" from "the API said nothing".
    """
    if not isinstance(payload, dict):
        return []

    found: List[Tuple[str, Any]] = [("", payload)]
    for segment in path.split("."):
        step: List[Tuple[str, Any]] = []
        for prefix, value in found:
            if not isinstance(value, dict):
                continue
            if segment == "*":
                step.extend(
                    (f"{prefix}.{key}" if prefix else key, child)
                    for key, child in value.items()
                )
            elif segment in value:
                step.append((f"{prefix}.{segment}" if prefix else segment, value[segment]))
        if not step:
            return []
        found = step

    return found


@dataclass(frozen=True)
class Envelope:
    """How to tell success from failure when the HTTP status will not.

    Declared on a factory (every tool inherits it) or on a single tool. Two
    shapes cover almost everything in the wild:

    * **A success flag** — ``ok_field="ok"`` fails the call when ``ok`` is falsy.
      Add ``ok_value="success"`` when the field carries a word rather than a bool.
    * **An error collection** — ``errors_field="errors"`` fails the call when that
      key holds a non-empty list. This is the GraphQL convention.

    Every field name is a **path**: dotted for nesting, with ``*`` standing for
    any key at that level. ``"ok"`` is a path of one segment, so the simple case
    reads exactly as before. ``"data.*.userErrors"`` reaches a GraphQL mutation
    payload without naming the operation.

    Attributes
    ----------
    ok_field:
        Path to a value that must indicate success. Falsy means failure unless
        ``ok_value`` is set, in which case the value must equal it.
    ok_value:
        Required value of ``ok_field``, for APIs that report ``"status": "ok"``.
    error_field:
        Path to the machine-readable error code, used for the message and
        matched against ``credential_errors``.
    errors_field:
        Path — or several paths — to a list of errors; non-empty means failure.
    credential_errors:
        Error codes that mean the credential is the problem. These raise
        :class:`~charter.types.errors.CredentialError` so a host application can
        refresh and retry; everything else raises
        :class:`~charter.types.errors.APIError`.
    detail_fields:
        Paths to extra values worth appending to the message — Slack's ``needed``
        names the missing scope, which is the single most useful thing in the
        response. Dotted and ``*`` paths work here too, so a detail one level
        down (a GraphQL ``extensions.code``) is reachable.
    retry_after:
        Optional. Given the failing payload, returns the seconds to wait, for an
        API that reports a rate limit inside a 200 rather than in a
        ``Retry-After`` header. A cost-budgeted API (Shopify) is the case: the
        response carries the budget and the restore rate, and the wait is
        arithmetic on them rather than a field to read. Charter never retries; it
        declines to throw away the answer to "when?".
    """

    ok_field: Optional[str] = None
    ok_value: Any = None
    error_field: Optional[str] = None
    errors_field: Optional[FieldPath] = None
    # Declared as the set it is read through, not the frozenset it is stored
    # as: every example here and in the docs passes a set literal, which
    # __post_init__ freezes. Naming the narrower type would make the documented
    # call a type error for anyone running a checker over their own pack.
    credential_errors: AbstractSet[str] = field(default_factory=frozenset)
    detail_fields: Tuple[str, ...] = ()
    retry_after: Optional[Callable[[Any], Optional[int]]] = None

    def __post_init__(self) -> None:
        if not self.ok_field and not self.errors_field:
            raise DeclarationError(
                "An Envelope needs either ok_field (a success flag) or errors_field "
                "(an error collection) — otherwise it can never detect a failure.",
                docs="tools/envelopes",
            )
        # dataclass(frozen=True) blocks assignment; go through object.__setattr__.
        object.__setattr__(self, "credential_errors", _frozen(self.credential_errors))
        object.__setattr__(self, "detail_fields", tuple(self.detail_fields))

    # -----------------------------------------------------

    def _failure(self, payload: Any) -> Optional[Tuple[str, str, Any]]:
        """The first failure in ``payload`` as ``(kind, where, value)``.

        ``kind`` is ``"errors"`` or ``"ok"``; ``where`` is the concrete path that
        matched, with any ``*`` resolved — which is how the message can name the
        operation that was declined.
        """
        # Error collections first: a document-level problem is more fundamental
        # than a flag, and a response can carry both.
        for path in _paths(self.errors_field):
            for where, value in _collect(payload, path):
                if isinstance(value, (list, tuple)) and len(value) > 0:
                    return ("errors", where, value)

        if self.ok_field is not None:
            for where, value in _collect(payload, self.ok_field):
                if self.ok_value is not None:
                    if value != self.ok_value:
                        return ("ok", where, value)
                elif not value:
                    return ("ok", where, value)

        return None

    def failed(self, payload: Any) -> bool:
        """Whether this payload represents a failure."""
        return self._failure(payload) is not None

    def describe(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        """``(code, message)`` for a failed payload."""
        failure = self._failure(payload)
        if failure is None:  # pragma: no cover - callers check failed() first
            return "", ""

        kind, where, value = failure
        code = ""

        if self.error_field:
            for _, raw in _collect(payload, self.error_field):
                if isinstance(raw, str) and raw:
                    code = raw
                    break

        if not code and kind == "errors":
            code = _describe_errors(value)

        if not code and kind == "ok" and "." in where:
            # No error code to quote, so name the flag that said no. Only worth
            # doing when the path is nested, because then it carries the
            # operation: "data.issueCreate.success is false". For a root-level
            # flag the path adds nothing over the generic code below.
            code = f"{where} is {_render(value)}"

        code = code or "unknown_error"

        details = [
            f"{where}: {value}"
            for path in self.detail_fields
            for where, value in _collect(payload, path)
            if value not in (None, "", [], {})
        ]
        message = f"the API rejected the call: {code}"
        if details:
            message = f"{message} ({'; '.join(details)})"
        return code, message

    def raise_for_payload(
        self,
        payload: Any,
        *,
        url: Optional[str] = None,
        provider: Optional[str] = None,
        bearer: bool = True,
    ) -> None:
        """Raise the right typed error if ``payload`` is a failure.

        Raises:
            CredentialError: the error code is in ``credential_errors``.
            APIError: any other declared failure. ``status_code`` stays 200 on
                purpose — that really was the status, and it is the fact that
                surprises whoever reads the log.
        """
        if not self.failed(payload):
            return

        code, message = self.describe(payload)

        if code in self.credential_errors:
            # Same link as a real 401 gets: an envelope is where the status was
            # hidden, not a different kind of credential failure.
            raise CredentialError(
                message,
                provider=provider,
                status_code=401,
                docs=provider_docs(provider, bearer=bearer),
            )

        body = payload
        if isinstance(payload, dict) and self.ok_field:
            body = {k: v for k, v in payload.items() if k != self.ok_field}

        wait: Optional[int] = None
        if self.retry_after is not None:
            try:
                wait = self.retry_after(payload)
            except Exception:
                # A resolver that cannot read this payload must not replace the
                # error the caller actually needs to see.
                wait = None

        raise APIError(
            message,
            status_code=200,
            body=str(body)[:_BODY_EXCERPT],
            url=url,
            retry_after=wait,
        )


def _render(value: Any) -> str:
    """A falsy value, spelled the way the wire spelled it."""
    if value is False:
        return "false"
    if value is None:
        return "null"
    return repr(value)


def _describe_errors(errors: Any) -> str:
    """One readable line from an error list, keeping the field path when there is one.

    ``userErrors`` entries carry ``{"field": ["handle"], "message": "..."}``;
    GraphQL's own ``errors`` carry ``{"message": "..."}``. Both read well as
    ``field: message``.
    """
    if not isinstance(errors, (list, tuple)) or not errors:
        return ""

    parts: List[str] = []
    for entry in errors[:3]:
        if not isinstance(entry, dict):
            parts.append(str(entry))
            continue
        message = entry.get("message") or entry.get("code") or str(entry)
        location = entry.get("field")
        if isinstance(location, (list, tuple)):
            location = ".".join(str(part) for part in location)
        parts.append(f"{location}: {message}" if location else str(message))

    if len(errors) > 3:
        parts.append(f"(+{len(errors) - 3} more)")
    return "; ".join(parts)


GRAPHQL_ENVELOPE = Envelope(errors_field="errors")
"""The GraphQL convention: HTTP 200 always, failures in an ``errors`` array.

This catches a document the server would not run. It does *not* catch a mutation
the server ran and then declined — that failure lives inside the payload, and
needs a path that reaches it. See the Linear and Shopify packs.
"""
