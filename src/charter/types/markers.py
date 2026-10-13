# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
HTTP request markers and control markers.

These markers are used as ``Annotated`` metadata on Pydantic model fields to
control how fields are mapped to HTTP request components (path, query, body)
and how they are transformed or filtered.
"""

from __future__ import annotations

import re
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    TypedDict,
)

from charter.types.errors import DeclarationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pydantic import BaseModel

__all__ = [
    "KeyCase",
    "declared_body_fields",
    "raw_body_exclusions",
    "raw_body_media_type",
    "Case",
    "Gloss",
    "Path",
    "Query",
    "Body",
    "Header",
    "check_header_fields",
    "Format",
    "Mode",
    "TransportOverride",
]


# -----------------------------------------------------
# Key case convention for HTTP serialization
# -----------------------------------------------------

KeyCase = Literal["camel", "snake", "pascal", "kebab"]
"""Which casing convention to apply when serializing keys for the wire.

- ``"camel"``  → ``dateTime``, ``userId``   (default, most Google/REST APIs)
- ``"snake"``  → ``date_time``, ``user_id`` (keys sent as-is)
- ``"pascal"`` → ``DateTime``, ``UserId``   (e.g. Google Maps ``LocalizedName``)
- ``"kebab"``  → ``date-time``, ``user-id`` (e.g. some REST / HTTP header-style APIs)
"""


# -----------------------------------------------------
# Field-level key case override (highest priority in cascade)
# -----------------------------------------------------


class Case:
    """Field-level key case override for HTTP serialization.

    Highest priority in the cascade: Field > Schema > Endpoint > Factory.

    Example:
        >>> display_name: Annotated[str, Case("pascal"), Body()]  # → DisplayName
    """

    def __init__(self, case: KeyCase) -> None:
        self.case: KeyCase = case

    def __repr__(self) -> str:
        return f"Case({self.case!r})"


class ConflictsWith:
    """This field cannot be sent alongside the named one(s).

    APIs state these rules in prose and answer them with a 400. Written as a
    validator, the rule needs a list of the fields it covers, which is a second
    place to keep in step: add a parameter and the list forgets it, delete one
    and the list keeps naming it. Declared on the field, the fact travels with
    the field.

    Google Calendar's ``events.list`` is the case this came from — ``syncToken``
    is refused beside eight other parameters, because an incremental sync
    continues the query its token came from. Each of the eight says so itself::

        i_cal_uid: Annotated[
            Optional[str], Field(None), Query(), ConflictsWith("sync_token")
        ]

    Enforced by :func:`~charter.execution.schema.create_llm_schema`, which builds
    the check from the markers, so a pack author declares and does not also
    write. The message names the API's own spelling of both fields — a
    :class:`WireName` if there is one — because the reader is a model holding the
    request it just sent.

    Args:
        fields: Names of the fields, as declared in Python, this one excludes.
        reason: A clause explaining *why*, appended to the message. Worth setting:
            "cannot be combined" tells a model what to stop doing and not what to
            do instead.
    """

    def __init__(self, *fields: str, reason: str = "") -> None:
        if not fields or any(not f or not f.strip() for f in fields):
            raise DeclarationError(
                "ConflictsWith needs the name of at least one field this one "
                "excludes, e.g. ConflictsWith('sync_token').",
                docs="tools/wire-contract",
            )
        self.fields: tuple = tuple(fields)
        self.reason: str = reason

    def __repr__(self) -> str:
        return f"ConflictsWith({', '.join(repr(f) for f in self.fields)})"


class WireName:
    """The exact key this field takes on the wire.

    Wins over every case convention — field, schema, endpoint and factory — and
    over the whole cascade, because it is not a convention: it is the name the
    API documents.

    :class:`Case` covers an API that is consistent in a convention Charter knows.
    This covers the field that is not, and the commonest reason is an acronym.
    ``snake_to_camel`` capitalises each component, so ``i_cal_uid`` becomes
    ``iCalUid`` where Google Calendar documents ``iCalUID``; the same shape
    produces ``htmlUrl`` for ``htmlURL`` and ``ipAddress`` for ``IPAddress``.
    No case convention reaches those names from a snake_case field, and an
    ``alias`` does not either — the runtime dumps by field name and converts the
    keys afterwards, so an alias set for the wire never arrives.

    That is worth a marker rather than a workaround because of how it fails.
    Many APIs ignore a query parameter they do not recognise, so the misspelled
    filter is dropped, the unfiltered result comes back, and the call answers
    200: nothing raises, and the pack looks correct until someone counts the
    rows. Charter's Calendar pack sent ``iCalUid`` for exactly as long as it
    existed.

    Example:
        >>> i_cal_uid: Annotated[str, WireName("iCalUID"), Query()]
    """

    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise DeclarationError(
                "WireName needs the key the API documents, e.g. WireName('iCalUID').",
                docs="tools/key-case-cascade",
            )
        self.name: str = name

    def __repr__(self) -> str:
        return f"WireName({self.name!r})"


# -----------------------------------------------------
# What the model is told, beyond what the API documents
# -----------------------------------------------------


class Gloss:
    """A sentence Charter adds for the model, kept out of the documented text.

    A gloss is a note written beside a text its writer may not alter, which is
    the position a pack is in: ``description`` carries the API's own words, and
    that is the rule that makes a pack checkable. A description can be diffed
    against the reference page, and anything that does not match is either an
    API change or a mistake. Editing one to help a model breaks that. The
    sentence a pack author wrote and the sentence the API publishes become
    indistinguishable, and the next person to regenerate the field from the docs
    deletes the help without knowing it was there.

    A ``Gloss`` is the pack's own sentence, declared separately and appended to
    the description in the LLM-facing schema only::

        amount: Annotated[
            Optional[int],
            Field(None, ge=1, description="A positive integer in the smallest "
                  "currency unit representing how much to refund."),
            Body(),
            Gloss("Cents, not dollars: $15.00 is 1500. Multiply a decimal amount by 100."),
        ]

    The wire schema keeps the documented text intact, so the diff against the
    reference page still means what it meant. The appending happens in
    :func:`~charter.execution.schema.create_llm_schema`, which every adapter
    reads its schema from, so a pack declares the gloss and nothing else.

    Stripe's ``POST /v1/refunds`` is the case this came from. "A positive
    integer in the smallest currency unit" is Stripe's phrase and it is correct;
    a 3B model reading ``15.00`` off a spreadsheet sent ``amount=15`` and
    refunded fifteen cents. Nothing rejects that: the units are the caller's to
    get right, the request is valid, and the API answers 200.

    What belongs in one: the unit and its conversion, the value a model reaches
    for that the API reads as something else, the field that looks optional and
    is not. What does not: a restatement of the description, and a rule
    ``ge``/``le``/``pattern``/:class:`ConflictsWith` can carry instead. Those
    are *checked*, and a gloss is only read. Reach for the constraint first and
    write a gloss for what no constraint can express.

    Args:
        text: The sentence, as the model should read it. Written for someone
            holding the description already, so it adds rather than repeats.
    """

    def __init__(self, text: str) -> None:
        if not text or not text.strip():
            raise DeclarationError(
                "Gloss needs the sentence to add for the model, e.g. "
                "Gloss('Cents, not dollars: $15.00 is 1500.'). Drop the marker "
                "if there is nothing to add."
            )
        self.text: str = text.strip()

    def __repr__(self) -> str:
        return f"Gloss({self.text!r})"


# -----------------------------------------------------
# HTTP Request markers
# -----------------------------------------------------


class Path:
    """Marker for path parameters.

    Path values are percent-encoded before they reach the URL, because they
    arrive from a model and a model reads untrusted text shortly before filling
    them in. Encoding ``/`` is what keeps a path parameter inside its own
    segment: without it, ``path="../../other/contents/file"`` walks up the
    template and reaches an endpoint the tool never declared.

    A few APIs take a genuinely multi-segment value — GitHub's file path is the
    example — and those opt in with ``Path(allow_slash=True)``. ``..`` is
    rejected either way; no API has a segment legitimately named that.
    """

    def __init__(self, allow_slash: bool = False) -> None:
        self.allow_slash = allow_slash

    def __repr__(self) -> str:
        return f"Path(allow_slash={self.allow_slash})" if self.allow_slash else "Path()"


class Query:
    """Marker for query parameters."""

    def __repr__(self) -> str:
        return "Query()"


class Body:
    """Marker for body parameters.

    Parameters
    ----------
    envelop : bool, default False
        If True, the field *name* is preserved in the serialized JSON instead of being
        stripped. This is required for APIs such as Gmail ``drafts.insert`` that expect
        a top-level object (e.g. ``{"message": {...}}``) rather than the raw value.
    media_type : str, optional
        The field is the *whole* request body, in this media type, when it is set:
        its value — after any ``Format`` transform — is sent as-is, with this
        ``Content-Type``. For an operation that takes its body in more than one
        format, the way Microsoft Graph's ``sendMail`` takes a JSON message *or*
        a base64 MIME document as ``text/plain``. One tool, two documented
        formats, and the model fills whichever argument it means.

        Such a field excludes every other body field — the runtime adds that
        rule to the view the model fills in, so it is declared once, here — and
        is left out of the JSON body: the remaining body fields unwrap and merge
        exactly as they would without it.
    """

    def __init__(self, envelop: bool = False, media_type: Optional[str] = None) -> None:
        if envelop and media_type:
            raise DeclarationError(
                "Body(envelop=True) names the field inside a JSON object, and "
                "Body(media_type=...) makes the field the whole body; a field is one or "
                "the other.",
                docs="reference/markers#body",
            )
        if media_type is not None and not media_type.strip():
            raise DeclarationError(
                "Body(media_type=...) needs the Content-Type the body is sent as, e.g. "
                "Body(media_type='text/plain').",
                docs="reference/markers#body",
            )
        self.envelop = envelop
        self.media_type = media_type

    def __repr__(self) -> str:
        if self.media_type:
            return f"Body(media_type={self.media_type!r})"
        return f"Body(envelop={self.envelop!r})"


# An RFC 9110 field name: a token.
_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

# Headers a schema field may not set. The first three carry a credential, and a
# model choosing one would choose whose account the call runs as. The rest are
# httpx's to derive from the request it is sending, and a model's value would
# describe a different request from the one that goes out.
_RESERVED_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "host",
        "content-length",
        "content-type",
        "transfer-encoding",
        "connection",
    }
)


class Header:
    """Marker for a request header whose value the model chooses.

    For an API that takes an argument as a header rather than in the query or
    the body: Microsoft Graph sizes a delta page with ``Prefer:
    odata.maxpagesize=10``, and nothing else it accepts does the same job. The
    field is an argument like any other — the model sees it under the field's
    name, with its description — and its value is written into the header.

    A value the *host* decides for a call — an idempotency key, a tenant
    selector — is not this. That is ``ainvoke(args, headers=...)``, which a model
    filling in arguments cannot reach.

    Parameters
    ----------
    name : str
        The header, sent as written.
    template : str, optional
        How the value is written into the header, with ``{}`` where it goes:
        ``Header("Prefer", template="odata.maxpagesize={}")``. Without one the
        value is the whole header.

    The value is a scalar; ``True`` and ``False`` are sent as ``true`` and
    ``false``. One holding a line break is refused before any request, because a
    header value cannot contain one and a value that did would be a second
    header. ``Authorization``, ``Proxy-Authorization`` and ``Cookie`` cannot be
    named, nor the headers httpx derives from the request; the tool also refuses
    a header its credential or its ``static_headers`` already set.
    """

    def __init__(self, name: str, template: Optional[str] = None) -> None:
        if not isinstance(name, str) or not _HEADER_NAME.match(name):
            raise DeclarationError(
                f"Header({name!r}) is not a header name: one token, such as 'Prefer' "
                "or 'X-Request-Priority'.",
                docs="reference/markers#header",
            )
        if name.lower() in _RESERVED_HEADERS:
            raise DeclarationError(
                f"Header({name!r}) names a header a schema field may not set: it carries "
                "a credential, or httpx derives it from the request. A value the host "
                "decides per call goes in ainvoke(headers=...).",
                docs="reference/markers#header",
            )
        if template is not None and template.count("{}") != 1:
            raise DeclarationError(
                f"Header({name!r}, template={template!r}) needs exactly one {{}} where "
                "the value goes, e.g. template='odata.maxpagesize={}'.",
                docs="reference/markers#header",
            )
        self.name = name
        self.template = template

    def render(self, value: Any) -> str:
        """The header value for ``value``: the template filled, or the value alone."""
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        return self.template.replace("{}", text) if self.template else text

    def __repr__(self) -> str:
        if self.template:
            return f"Header({self.name!r}, template={self.template!r})"
        return f"Header({self.name!r})"


def check_header_fields(
    schema: Type[BaseModel],
    tool_name: str,
    *,
    static_headers: Optional[Dict[str, str]] = None,
    credential_headers: Iterable[str] = (),
) -> None:
    """Refuse a ``Header`` field that would collide with a header the tool already sends.

    A field naming the credential's header would let a model replace the
    credential. One naming a static header would replace a value the author fixed
    for every call — Graph's ``Prefer: outlook.body-content-type`` beside a page
    size is the case, where the second silently drops the first — so the two are
    declared as one or the other, not both. Two fields naming one header would
    leave which one reaches the wire to field order.
    """
    taken = {name.lower(): "the credential" for name in credential_headers}
    taken.update({name.lower(): "static_headers" for name in (static_headers or {})})
    seen: Dict[str, str] = {}
    for field_name, field in schema.model_fields.items():
        for marker in field.metadata:
            if not isinstance(marker, Header):
                continue
            key = marker.name.lower()
            if key in taken:
                raise DeclarationError(
                    f"Tool {tool_name!r}: field {field_name!r} is sent as the "
                    f"{marker.name} header, which {taken[key]} already sets on every call.",
                    docs="reference/markers#header",
                )
            if key in seen:
                raise DeclarationError(
                    f"Tool {tool_name!r}: fields {seen[key]!r} and {field_name!r} are both "
                    f"sent as the {marker.name} header.",
                    docs="reference/markers#header",
                )
            seen[key] = field_name


# -----------------------------------------------------
# Format Transformation Marker
# -----------------------------------------------------


class Format:
    """Marker for fields that require format transformation.

    This marker indicates that a field should be transformed from a semantic type
    (what the LLM sees) to a wire format (what the API expects).

    Example:
        >>> raw: Annotated[str, Format("rfc822_base64")]

    The transform registry handles converting from the semantic type to the wire
    format automatically.
    """

    def __init__(self, transform: str) -> None:
        self.transform = transform

    def __repr__(self) -> str:
        return f"Format({self.transform!r})"


# -----------------------------------------------------
# Mode Control Marker
# -----------------------------------------------------


class Mode:
    """Marker for controlling field visibility based on operation mode.

    This marker allows you to specify when a field should be visible to the LLM
    based on the current operation mode or special input/output semantics.

    Features:
        - Multi-mode support: fields can belong to multiple modes using comma separation
        - Cascading: child fields automatically inherit parent modes
        - Compatible with ``Format`` transformations

    Special modes (always enforced, regardless of tool mode):
        - ``"request_only"``: field only exists in API requests (input-only, always
          shown to the LLM)
        - ``"response_only"``: field only exists in API responses (output-only, always
          hidden from the LLM)
        - ``"disabled"``: field is never exposed to the LLM

    Custom modes (only active when the tool specifies a matching mode):
        - Any string (e.g. ``"create"``, ``"update"``): field visible only when the
          tool uses that mode

    Examples:
        >>> id: Annotated[str, Mode("response_only")]      # API returns, never accepts
        >>> raw: Annotated[str, Mode("request_only")]      # required for writes only
        >>> internal: Annotated[int, Mode("disabled")]     # never exposed
        >>> full_text: Annotated[str, Mode("create")]      # only when mode="create"
        >>> delta: Annotated[str, Mode("update")]          # only when mode="update"

    Not the lever for making a tool smaller. A mode is declared by whoever wrote
    the pack, and it selects between behaviours that author anticipated — a
    version, a tier, a region, create against update. A field is hidden only by a
    mode someone put on it, so a tool you did not write offers exactly the cuts
    its author thought of, and none of them need be the one your agent wants.
    Narrowing an arbitrary tool to the part one job uses is
    :meth:`Tool.derived() <charter.Tool.derived>`, which needs nothing from the
    pack, can remove any path, and is the only one of the two that can bring an
    oversized schema back under a provider's limits.
    """

    def __init__(self, modes: str) -> None:
        # Parse comma-separated modes and strip whitespace
        self.modes: set[str] = (
            {mode.strip() for mode in modes.split(",") if mode.strip()} if modes else set()
        )

    def __repr__(self) -> str:
        return f"Mode({','.join(sorted(self.modes))!r})"


# -----------------------------------------------------
# Transport Override Types
# -----------------------------------------------------


class TransportOverride(TypedDict, total=False):
    """Override structure for HTTP transport parameters.

    Allows selective overriding of path, query, body, and headers that would
    normally be extracted from the Pydantic model.
    """

    path: Dict[str, Any]
    query: Dict[str, Any]
    body: Any
    headers: Dict[str, str]


# -----------------------------------------------------
# How many fields a schema routes to the body
# -----------------------------------------------------


def declared_body_fields(schema: Type[BaseModel]) -> int:
    """How many of ``schema``'s fields the wire contract sends in the JSON body.

    Everything that is not ``Path()``, ``Query()`` or ``Header()``, which includes a field
    carrying no marker at all — that one is refused later, by name, rather than
    being miscounted here. A ``Body(media_type=...)`` field is not counted: when
    it is set it is the whole body and nothing is merged with it, and when it is
    not, the body is the others alone and must take the shape they take without
    it — a create that gains a MIME alternative still unwraps its message.

    This lives beside the markers and not in :mod:`charter.execution.http`
    because two modules need the same answer and used to compute it separately.
    ``_extract_http_params`` counted the *executed view*'s fields and
    ``_create_auto_transformer`` counted the *source schema*'s, which agree until
    something removes a field from the view — and ``Tool.derived(drop=...)`` and
    ``Mode("response_only")`` both do. Then one of them said "one body field, so
    unwrap it" and the other said "two, so keep the names", and the request went
    out as neither: a projection that dropped an unrelated optional field turned
    ``{"reviewers": [...]}`` into a bare ``[...]``, and on a form-encoded API
    turned ``evidence[uncategorized_text]`` into a top-level key the server
    ignores.

    The count is a property of the *declaration*, so both callers now take it
    from ``args_schema`` and a view can no longer move it. That is the same rule
    the count already followed one level down — it is read from the schema rather
    than from which fields a given call populated, so that the wire shape is not
    a function of the arguments.
    """
    return sum(
        1
        for field in schema.model_fields.values()
        if not any(isinstance(m, (Path, Query, Header)) for m in field.metadata)
        and raw_body_media_type(field) is None
    )


def raw_body_media_type(field: Any) -> Optional[str]:
    """The media type a ``Body(media_type=...)`` field is sent as, else ``None``."""
    for marker in getattr(field, "metadata", None) or ():
        if isinstance(marker, Body) and marker.media_type:
            return marker.media_type
    return None


def raw_body_exclusions(fields: Dict[str, Any]) -> List[Tuple[str, Tuple[str, ...], str]]:
    """The exclusion rules a ``Body(media_type=...)`` field implies, as ``ConflictsWith`` would.

    ``fields`` maps a field name to its ``FieldInfo``. A field that is the whole
    request body cannot share it, so it excludes every other field the body
    would carry — everything that is not ``Path()``, ``Query()`` or ``Header()``. Derived from
    the marker rather than declared beside it, because a list a pack author
    writes out is a list that forgets the body field added next year.
    """
    body = [
        name
        for name, info in fields.items()
        if not any(
            isinstance(m, (Path, Query, Header)) for m in getattr(info, "metadata", None) or ()
        )
    ]
    rules = []
    for name in body:
        media_type = raw_body_media_type(fields[name])
        if media_type is None:
            continue
        others = tuple(other for other in body if other != name)
        if others:
            rules.append((name, others, f"It is the whole request body, sent as {media_type}."))
    return rules
