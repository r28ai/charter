# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Schema -> HTTP request, and back.

``call_api`` is the whole wire layer: it reads the ``Path``/``Query``/``Body``
markers off a validated model, routes each field to its place in the request,
applies the key-case cascade, sends it, and turns a failure into a typed error.

Nothing here reaches for ambient state — no context vars, no global config, no
credential store. Everything arrives as an argument.
"""

from __future__ import annotations

import logging
from base64 import b64encode
from datetime import datetime, timezone
from time import perf_counter
from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from charter.auth import Credentials
from charter.execution.casing import DictKeyParser, convert_with_plan, key_plan, plan_for
from charter.observability import CallProbe
from charter.types.envelope import Envelope
from charter.types.errors import (
    APIError,
    CharterError,
    CredentialError,
    DeclarationError,
    ToolValidationError,
    provider_docs,
)
from charter.types.markers import (
    Body,
    KeyCase,
    Path,
    Query,
    TransportOverride,
    WireName,
    declared_body_fields,
)

__all__ = ["call_api", "BaseUrl", "DEFAULT_CREDENTIAL_STATUSES"]

logger = logging.getLogger("charter")


def _is_textual(content_type: str) -> bool:
    """Whether a response body can be decoded to text without losing anything.

    ``text/*`` and the structured types that are text underneath — XML, YAML,
    JavaScript, ``+json``. Everything else, and a response that declares no type
    at all, is treated as bytes: guessing wrong costs the caller the payload.
    """
    if not content_type:
        return False
    base, _, parameters = content_type.partition(";")
    base = base.strip()
    # A declared charset is the server saying how these bytes become characters.
    # It is the one signal that covers the vendor types no list can enumerate —
    # `application/vnd.github.diff; charset=utf-8` is a diff, and is text.
    if "charset=" in parameters:
        return True
    if base.startswith("text/"):
        return True
    if base.endswith(("+json", "+xml")):
        return True
    return base in _TEXTUAL_APPLICATION_TYPES


_TEXTUAL_APPLICATION_TYPES = frozenset(
    {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/ecmascript",
        "application/x-yaml",
        "application/yaml",
        "application/x-ndjson",
        "application/graphql",
        "application/x-www-form-urlencoded",
        # GitHub's diff and patch media types, which it serves without a charset.
        "application/vnd.github.diff",
        "application/vnd.github.patch",
        "application/vnd.github.raw",
    }
)


HTTPMethod = Literal["GET", "POST", "PATCH", "PUT", "DELETE"]

QueryFormat = Literal["repeat", "bracket"]
"""How structured query values are serialised.

``"repeat"`` (default) sends a list as repeated keys — ``labelIds=A&labelIds=B``,
which is what Google and most REST APIs expect. ``"bracket"`` sends
``expand[0]=A&created[gte]=1700000000``, which is what Stripe expects, matching
its body encoding.
"""

BaseUrl = Union[str, Callable[[], str]]
"""The API's base URL, or a callable resolving it at request time.

Usually a constant of the API. For a single-tenant-per-installation API it is
not: a Shopify store lives at ``https://{shop}.myshopify.com/``, a Zendesk
account at ``https://{subdomain}.zendesk.com/``. The host is a property of the
installation, supplied by ``configure()`` after the tools are built — and it
must never be a schema field, because the model would then choose which server
to talk to.
"""

BodyFormat = Literal["json", "form", "raw"]
"""How to serialise the request body.

``"json"`` is the default. ``"form"`` sends
``application/x-www-form-urlencoded`` with bracket notation for nested values —
the convention Stripe, Twilio, Mailgun and every OAuth2 token endpoint expect.

``"raw"`` sends the body's bytes with no encoding at all, for the endpoints that
take a *file* rather than a document: GitHub's release-asset upload wants the
asset itself in the body and its media type in ``Content-Type``. Nothing is
merged into a raw body, so ``static_body`` has nowhere to go and is refused
rather than silently dropped, and the ``Content-Type`` is the declaration's to
set — there is no type that can be inferred from an arbitrary byte string.
"""

# Header keys (lowercase) whose values must be masked in logs
_SENSITIVE_HEADER_KEYS = frozenset(
    {
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-auth-token",
    }
)

DEFAULT_CREDENTIAL_STATUSES = frozenset({401})
"""Status codes that mean "your credentials are the problem", not "your request is".

Only 401. A ``CredentialError`` is a specific instruction — *re-authenticate* —
and 403 is not that. HTTP separates the two on purpose: 401 says the request was
unauthenticated, 403 says it was authenticated and still not allowed. Google
answers 403 for an IAM permission it will keep refusing however many times you
consent, and GitHub answers 403 for a rate limit; reporting either as a
credential failure sends a well-behaved host into an OAuth flow that cannot fix
it, and loses the ``retry_after`` on the way.

An API that genuinely means "your token" by 403 — usually a missing scope — says
so on its factory with ``credential_statuses={401, 403}``. Declared once per API,
like everything else here.
"""

_ERROR_BODY_EXCERPT = 500


# -----------------------------------------------------
# Logging helpers
# -----------------------------------------------------


def _truncate_base64_for_log(obj: Any, *, _depth: int = 0) -> Any:
    """Truncate base64 ``data`` fields to the first 10 chars for HTTP logs.

    Keeps structure, avoids log bloat. Only runs when the log record is emitted.
    """
    if _depth > 30:
        return obj
    if isinstance(obj, dict):
        return {
            k: (
                v[:10] + "…"
                if k == "data" and isinstance(v, str) and len(v) > 10
                else _truncate_base64_for_log(v, _depth=_depth + 1)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_truncate_base64_for_log(x, _depth=_depth + 1) for x in obj]
    return obj


def _mask_headers_for_log(headers: Mapping[str, str], max_len: int = 50) -> Dict[str, str]:
    """Mask header values for safe logging.

    - Sensitive headers (Authorization, API keys, ...): partially redacted
    - All values capped at *max_len* characters to prevent log bloat
    """
    masked: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _SENSITIVE_HEADER_KEYS:
            # Sensitive: show auth type prefix + first few chars of secret
            if len(value) > 10:
                masked[key] = value[:10] + "***"
            else:
                masked[key] = value[:4] + "***"
        else:
            # Non-sensitive: just cap length
            if len(value) > max_len:
                masked[key] = value[: max_len - 3] + "..."
            else:
                masked[key] = value
    return masked


# -----------------------------------------------------
# Schema introspection
# -----------------------------------------------------


def _dumped(item: Any) -> Any:
    """One element of a list or mapping, rendered the way JSON needs it.

    Recursive, because containers nest: a ``List[List[Leaf]]`` or a
    ``Dict[str, List[Leaf]]`` reached ``json.dumps`` still holding model
    instances and raised a bare ``TypeError`` out of the encoder, which no
    adapter catches. One level of unwrapping only ever covered the annotations
    somebody happened to try.
    """
    if isinstance(item, BaseModel):
        return item.model_dump(exclude_none=True, mode="json")
    if isinstance(item, datetime):
        return item.isoformat()
    if isinstance(item, list):
        return [_dumped(element) for element in item]
    if isinstance(item, dict):
        return {key: _dumped(element) for key, element in item.items()}
    return item


def unwraps_body(declared_body_fields: int, marker: Body, value: Any) -> bool:
    """Whether this single ``Body()`` field's value *becomes* the request body.

    Unwrapping promotes a nested structure's own fields to the root of the
    request: ``update(user=Body(...))`` sends ``{"name": "Alice"}`` rather than
    ``{"user": {"name": "Alice"}}``. That is the right default — it is how most
    APIs read, and how ``issues_create`` and every Google pack are declared.

    A scalar has no fields to promote, so there is nothing the rule can mean
    there, and taking it literally produced a request no API accepts: a bare
    ``"C0123"`` as a JSON document, or — on a form-encoded API, which has no
    representation for a bare value at all — a local ``DeclarationError`` before
    the request was ever sent. Five tools across three packs were declared that
    way and none of them could run: Slack's ``conversations_join`` and Stripe's
    ``payment_methods_attach`` take a *required* scalar, so they failed on every
    call. A lone scalar keeps its field name, which is what those five meant.

    Lists still unwrap. An API whose body is a bare array is unusual but real,
    and a list, unlike a scalar, is a document.

    Two call sites depend on this answer — :func:`_extract_http_params` builds the
    body from it, and the transform routing in :mod:`charter.execution.executor`
    decides from it whether a transformed field replaces the body or is one key
    in it. They must agree, or a ``Format`` on a field moves every other field.
    """
    return declared_body_fields == 1 and not marker.envelop and isinstance(value, (dict, list))


def _extract_http_params(
    model: BaseModel,
    body_field_count: Optional[int] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Dict[str, Any]], Any]:
    """Extract HTTP *path*, *query*, and *body* parameters from a Pydantic model.

    Parameter location is decided using the ``Annotated`` markers from
    :mod:`charter.types` (``Path``, ``Query``, ``Body``).

    All nested Pydantic models are dumped with ``exclude_none=True`` so that
    optional fields with value ``None`` do **not** get serialised (many provider
    APIs, such as Gmail, reject unknown keys or explicit nulls).

    Body construction has three modes, to cover the API styles in the wild:

    1. **Single Body (standard unwrap)** — the default, ~90% of APIs.
       The schema declares exactly one ``Body()`` argument. Its value is
       unwrapped: the internal fields are propagated to the root of the JSON
       request. ``update(user=Body(...))`` -> ``{"name": "Alice", "email": "..."}``

       The count is taken from the *declared* schema, not from which fields
       happen to be populated on this call and not from the view being executed.
       Either substitution makes the wire shape a function of something other
       than the contract: the arguments in the first case, and a projection or a
       ``Mode`` in the second. ``body_field_count`` is that number, supplied by
       the caller that holds ``args_schema``; falling back to this model's own
       fields is for a schema handed straight to :func:`call_api`, where the
       model *is* the declaration.

       A lone *scalar* does not unwrap — there are no fields to promote — and
       keeps its name, so ``join(channel=Body())`` sends ``{"channel": "C1"}``.
       See :func:`unwraps_body`.

    2. **Single Body (explicit envelope)** — the edge case, ~10% of APIs.
       One argument marked ``Body(envelop=True)``. The argument's *name* is
       preserved as the root key. Useful for RPC-style or legacy endpoints.
       ``send(message=Body(envelop=True))`` -> ``{"message": {"text": "Hi"}}``

    3. **Multiple bodies (implicit merge)** — composite requests.
       Several arguments marked ``Body()``, merged into one object using their
       parameter names as keys. E.g. Google Sheets ``batchUpdate``.

    Returns
    -------
    tuple[path_params, query_params, body, body_source]
        path_params : variables to interpolate into the URL template.
        query_params : plain query string parameters.
        body : the JSON body to send (``None`` if no body).
        body_source : what to read the body's key cascade off, when a single
            ``Body()`` field unwrapped and the keys therefore stopped being this
            model's field names — the value's own class, or its annotation where
            the shape matters (a list applies its item plan per element, a
            mapping one level further down). ``None`` otherwise, which includes
            the merged and envelope shapes: there the keys *are* this model's
            fields and it is its own answer. Reported here rather than re-derived
            by the caller, so nothing guesses a second time at the unwrap
            decision made below.
    """
    path_params: Dict[str, Any] = {}
    query_params: Dict[str, Any] = {}
    body_fields: list[Tuple[str, Any, Body]] = []
    # What the key cascade for each field should be read off: the value's own
    # class when it is a model — more precise than the annotation, since a union
    # resolves to one member per call and the keys on the wire are that member's
    # — and the annotation otherwise, because a container's *shape* decides where
    # a plan applies and a dumped value no longer carries it.
    body_sources: Dict[str, Any] = {}

    # How many fields the *declaration* routes to the body. The unwrap decision
    # below is made from this, never from how many happen to be populated and
    # never from the view in hand: otherwise the same tool would send
    # {"channel": "C1", "text": "hi"} on one call and a bare "C1" on the next, or
    # change shape the moment a projection dropped an unrelated field.
    declared_count = (
        body_field_count if body_field_count is not None else declared_body_fields(model.__class__)
    )

    for name, field in model.__class__.model_fields.items():
        loc = next((m for m in field.metadata if isinstance(m, (Path, Query, Body))), None)

        # An unmarked top-level field is an unstated contract, and this is the
        # one place the runtime could paper over one. It used to default to
        # Body() and say so through `warnings` — a channel this library uses
        # nowhere else, that a host configuring the `charter` logger never sees,
        # and that `-W ignore` silences entirely. So the field went to the wire
        # on a guess, announced where nobody was listening. Every tool in every
        # pack marks its top-level fields; nothing was relying on the guess.
        if loc is None:
            # The name the author wrote, not the generated `_LLM` variant: the
            # reader of this message goes looking for the class in their own
            # code, and `SendEmail_LLM` is nowhere in it.
            declared_name = getattr(model, "charter_declared_name", "") or type(model).__name__
            raise DeclarationError(
                f"Field '{name}' on {declared_name} has no Path(), Query() "
                f"or Body() marker, so where it belongs in the request is undeclared. "
                f"Mark it — or Mode('response_only') it if the API only ever returns it.",
                docs="tools/wire-contract",
            )

        val = getattr(model, name)
        if val is None:
            continue

        body_sources[name] = type(val) if isinstance(val, BaseModel) else field.annotation

        # Dump nested BaseModel instances to dict before assigning
        if isinstance(val, BaseModel):
            val = val.model_dump(exclude_none=True, mode="json")
        # Convert datetime objects to RFC3339 timestamp strings
        elif isinstance(val, datetime):
            val = val.isoformat()
        # Handle lists that might contain BaseModel or datetime objects
        # Containers, to any depth. Mappings had no branch here at all, so a
        # `Dict[str, SomeModel]` field reached `json.dumps` still holding model
        # instances and raised a bare `TypeError` from the encoder — past every
        # adapter, none of which catch it.
        elif isinstance(val, (list, dict)):
            val = _dumped(val)

        if isinstance(loc, Path):
            path_params[name] = val
        elif isinstance(loc, Query):
            query_params[name] = val
        else:  # Body
            body_fields.append((name, val, loc))

    # Process body fields according to the three modes
    body_params: Optional[Dict[str, Any]] = None
    body_source: Any = None

    if len(body_fields) == 0:
        # No body fields populated
        body_params = None
    elif unwraps_body(declared_count, body_fields[0][2], body_fields[0][1]):
        # Mode 1: Single Body (Standard Unwrap). The schema declares exactly one
        # body field and its value is a structure, so that value *is* the body.
        body_params = body_fields[0][1]
        body_source = body_sources.get(body_fields[0][0])
    else:
        # Mode 2 (Explicit Envelope) and Mode 3 (Implicit Merge) are the same
        # construction: keys are field names.
        body_params = {}
        for name, val, _ in body_fields:
            body_params[name] = val

    return path_params, query_params, body_params, body_source


def _flatten_form(value: Any, prefix: str = "") -> List[Tuple[str, str]]:
    """Flatten a nested structure to form pairs using bracket notation.

    ``{"item": {"price": 5}}``   -> ``item[price]=5``
    ``{"ids": ["a", "b"]}``      -> ``ids[0]=a&ids[1]=b``
    ``{"on": True}``             -> ``on=true``

    Returns pairs; indexing makes every key unique, so the caller can safely
    build a mapping from them.

    This is the Rack/Stripe convention, which Twilio and the OAuth2 token
    endpoints also accept. ``None`` values are dropped rather than sent empty,
    matching how the JSON path already excludes them.
    """
    pairs: List[Tuple[str, str]] = []

    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}[{key}]" if prefix else str(key)
            pairs.extend(_flatten_form(item, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            pairs.extend(_flatten_form(item, f"{prefix}[{index}]"))
    elif value is None:
        return []
    elif isinstance(value, bool):
        pairs.append((prefix, "true" if value else "false"))
    else:
        pairs.append((prefix, str(value)))

    return pairs


# -----------------------------------------------------
# Error translation
# -----------------------------------------------------


def _provider_error_message(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    """Pull a human-readable message and status out of an error body.

    Handles the Google-style ``{"error": {"message": ..., "status": ...}}`` shape
    and the several flatter conventions other APIs use.
    """
    provider_message: Optional[str] = None
    provider_status: Optional[str] = None

    if isinstance(payload, dict):
        if isinstance(payload.get("error"), dict):
            gerr = payload["error"]
            if isinstance(gerr.get("message"), str) and gerr.get("message"):
                provider_message = gerr["message"]
            if isinstance(gerr.get("status"), str) and gerr.get("status"):
                provider_status = gerr["status"]

        if provider_message is None:
            top_level_message = (
                payload.get("detail")
                or payload.get("Message")
                or payload.get("message")
                or payload.get("error_description")
                or payload.get("error")
            )
            if isinstance(top_level_message, str) and top_level_message:
                provider_message = top_level_message
            elif isinstance(top_level_message, dict):
                nested = top_level_message.get("error") or top_level_message.get("message")
                if isinstance(nested, str) and nested:
                    provider_message = nested

    return provider_message, provider_status


# Everything legal inside one path segment (RFC 3986 sub-delims, plus ":" and
# "@") stays literal: a Google Calendar id is an email address, a Sheets range
# is "Sheet1!A1:B2", and percent-encoding those would change requests that work
# today. What is *not* in this set is the structural punctuation — "/" "?" "#"
# "%" and anything non-printable — which is exactly what lets a value escape the
# segment it was interpolated into.
_PATH_SAFE = "!$&'()*+,;=:@"


def _rate_limit_reset_in(resp: httpx.Response) -> Optional[int]:
    """Seconds until ``X-RateLimit-Reset``, when the request was rate limited.

    Read only when the response says the budget is actually spent
    (``x-ratelimit-remaining: 0``), so an ordinary response carrying its quota
    headers is not reported as a wait.
    """
    remaining = resp.headers.get("x-ratelimit-remaining")
    reset = resp.headers.get("x-ratelimit-reset")
    if reset is None or remaining is None:
        return None
    try:
        if int(remaining.strip()) > 0:
            return None
        seconds = int(float(reset.strip())) - int(datetime.now(timezone.utc).timestamp())
    except (ValueError, TypeError):
        return None
    # A reset already in the past means wait no time at all, not a negative one.
    return max(seconds, 0)


def _escape_path_params(path: Dict[str, Any], tool_input: BaseModel) -> Dict[str, Any]:
    """Percent-encode path values so a model cannot rewrite the request URL.

    ``url_template.format(**path)`` is a plain string substitution: whatever the
    value contains becomes part of the URL. Unescaped, a path parameter is not a
    parameter at all — it is an edit to the endpoint. Three things follow from
    that, and all three were reachable from a schema field:

    * ``".."`` walks up the template. ``repos_get_content(owner=o, repo=r,
      path="../../other/contents/README.md")`` reads a *different repository*,
      and ``"../../../../user"`` leaves the repository API altogether.
    * ``"?"`` starts a query string, so a value can add parameters the schema
      never declared — including ones the endpoint acts on.
    * ``"#"`` starts a fragment and truncates the rest of the path.

    Values arrive from a model that has usually just read untrusted text, so
    this is the boundary the rest of the wire contract assumes exists.

    ``/`` is encoded unless the field declares ``Path(allow_slash=True)``, which
    is for the genuinely multi-segment case (a file path).

    ``.`` and ``..`` are refused outright, opt-in or not. Both are
    normalisation tokens rather than names — ``httpx`` resolves them before the
    request leaves, so ``resource/{seg}/sub`` with ``seg="."`` is sent as
    ``resource/sub`` and the parameter has deleted its own segment. That is a
    weaker version of what ``..`` does and the same kind of thing: a value
    editing the endpoint instead of filling a hole in it. No API has a path
    segment legitimately named either.
    """
    allow_slash = {
        name
        for name, field in type(tool_input).model_fields.items()
        if any(isinstance(m, Path) and m.allow_slash for m in field.metadata)
    }

    escaped: Dict[str, Any] = {}
    for name, value in path.items():
        text = value if isinstance(value, str) else str(value)
        dotted = next((seg for seg in text.split("/") if seg in (".", "..")), None)
        if dotted is not None:
            declared = getattr(tool_input, "charter_declared_name", "") or type(tool_input).__name__
            raise ToolValidationError(
                f"Path parameter '{name}' on {declared} contains a '{dotted}' segment, which "
                f"would change which endpoint is called. Pass the value itself, not a "
                f"path relative to it.",
                errors=[{"loc": (name,), "msg": f"'{dotted}' is not allowed in a path parameter"}],
            )
        escaped[name] = quote(text, safe=_PATH_SAFE + ("/" if name in allow_slash else ""))
    return escaped


def _retry_after(resp: httpx.Response) -> Optional[int]:
    """Seconds from a ``Retry-After`` header, when the server sent one.

    Universal on 429 and common on 503 — Slack, GitHub, Stripe and Google all
    send it. Charter does not retry; it just refuses to throw away the answer to
    "when?" that the server already gave.

    Only the delta-seconds form is parsed. The HTTP-date form is legal but rare
    in JSON APIs, and guessing at clock skew is worse than reporting nothing.

    ``X-RateLimit-Reset`` is the fallback, because GitHub does not send
    ``Retry-After`` at all: it answers **403** with ``x-ratelimit-remaining: 0``
    and an epoch-seconds ``x-ratelimit-reset``. Same question, same answer, a
    different header — and dropping it leaves every backoff loop built on
    ``retry_after`` spinning against a limit it cannot see.
    """
    raw = resp.headers.get("retry-after")
    if not raw:
        return _rate_limit_reset_in(resp)
    try:
        seconds = int(raw.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _raise_for_status(
    resp: httpx.Response,
    url: str,
    provider: Optional[str],
    credential_statuses: FrozenSet[int] = DEFAULT_CREDENTIAL_STATUSES,
    bearer: bool = True,
) -> None:
    """Turn a >=400 response into the right typed error."""
    try:
        payload = resp.json()
    except Exception:
        payload = None

    provider_message, provider_status = _provider_error_message(payload)

    if provider_message:
        message = provider_message
    else:
        message = resp.reason_phrase or "request failed"
        if provider_status:
            message = f"{message} Status: {provider_status}."

    body_excerpt = resp.text[:_ERROR_BODY_EXCERPT] if resp.text else ""

    if resp.status_code in credential_statuses:
        # The library never re-authenticates on its own — the host app catches
        # this, refreshes however it likes, and retries.
        #
        # The link is the provider's own setup page where there is one, because
        # what a rejected token needs is that provider's consent parameters and
        # scopes rather than a general account of credentials. This is the
        # credential error most likely to be read in production.
        raise CredentialError(
            message,
            provider=provider,
            status_code=resp.status_code,
            docs=provider_docs(provider, bearer=bearer),
        )

    raise APIError(
        message,
        status_code=resp.status_code,
        body=body_excerpt,
        url=url,
        retry_after=_retry_after(resp),
    )


# -----------------------------------------------------
# Sending, and what a credential is allowed to follow
# -----------------------------------------------------


_MAX_REDIRECTS = 20


def _same_origin(a: httpx.URL, b: httpx.URL) -> bool:
    """Scheme, host and port — the three things that make a credential's audience."""
    return (a.scheme, a.host, a.port) == (b.scheme, b.host, b.port)


async def _send(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    request_kwargs: Dict[str, Any],
    *,
    follow_redirects: bool,
    credential_headers: FrozenSet[str],
) -> httpx.Response:
    """Send the request, following redirects without taking the credential along.

    httpx follows redirects perfectly well and strips exactly one header when
    the origin changes: ``Authorization``. That is the whole of its rule, and it
    is only half of the problem here — an api-key tool's credential is
    ``x-api-key``, ``X-Shopify-Access-Token``, whatever the API named it, and
    httpx has no way to know which of the headers it was handed is the secret.
    So ``follow_redirects=True`` on an api-key factory sent that key to whatever
    host the ``Location`` named, while the factory's own docstring promised the
    opposite — it had inherited the reassurance from the bearer factory, where
    it is true.

    The walk is httpx's own, not a reimplementation: each hop's request comes
    from ``Response.next_request``, which httpx builds with its rules for the
    303 method downgrade, the body, relative ``Location`` resolution and its
    ``Authorization`` stripping. The only thing added here is deleting the
    headers Charter knows to be credentials whenever the next hop leaves the
    current origin.

    Comparing consecutive hops rather than against the first is deliberate and
    sufficient: once a header has been dropped from one hop's request, every
    request built from that one is missing it too, so a redirect that wanders
    off the origin and back cannot carry the credential home.

    The redirect budget is httpx's own, and running out of it raises
    :class:`~charter.types.errors.APIError` rather than ``httpx.TooManyRedirects``
    — an httpx exception escaping here would pass every adapter, all of which
    catch :class:`~charter.types.errors.CharterError` and nothing else.
    """
    request = http.build_request(method, url, **request_kwargs)
    response = await http.send(request, follow_redirects=False)
    if not follow_redirects:
        return response

    for _ in range(_MAX_REDIRECTS):
        following = response.next_request
        if following is None:
            return response
        if not _same_origin(request.url, following.url):
            for name in credential_headers:
                if name in following.headers:
                    del following.headers[name]
        await response.aclose()
        request = following
        response = await http.send(request, follow_redirects=False)

    # The budget is redirects *followed*, so the answer to the last one still
    # counts. Returning only from inside the loop made the limit one lower than
    # it reads and than httpx's own: a chain of exactly _MAX_REDIRECTS hops
    # ending in a 200 was refused, holding a successful response.
    if response.next_request is None:
        return response

    raise APIError(
        f"Exceeded {_MAX_REDIRECTS} redirects.",
        status_code=response.status_code,
        body="",
        url=str(request.url),
    )


# -----------------------------------------------------
# call_api
# -----------------------------------------------------


async def call_api(
    method: HTTPMethod,
    url_template: str,  # e.g. "calendar/v3/calendars/{calendar_id}/events"
    tool_input: BaseModel,
    credentials: Optional[Credentials] = None,
    base_url: BaseUrl = "",
    timeout: int = 20,
    body_case: KeyCase = "camel",
    query_case: KeyCase = "snake",
    path_case: KeyCase = "snake",
    transport_override: Optional[TransportOverride] = None,
    provider: Optional[str] = None,
    envelope: Optional[Envelope] = None,
    body_format: BodyFormat = "json",
    query_format: QueryFormat = "repeat",
    static_query: Optional[Dict[str, Any]] = None,
    static_headers: Optional[Dict[str, str]] = None,
    static_body: Optional[Dict[str, Any]] = None,
    request_headers: Optional[Mapping[str, str]] = None,
    client: Optional[httpx.AsyncClient] = None,
    probe: Optional[CallProbe] = None,
    credential_statuses: Optional[Iterable[int]] = None,
    follow_redirects: bool = False,
    body_field_count: Optional[int] = None,
    credential_headers: Optional[Iterable[str]] = None,
) -> Any:
    """Map a validated tool input onto an HTTP request, send it, return the body.

    Parameters
    ----------
    method: The HTTP method to use.
    url_template: URL template, snake_case, e.g. ``"calendar/v3/calendars/{calendar_id}/events"``.
    tool_input: The validated Pydantic model carrying the markers.
    credentials: Bearer credentials, or ``None`` for API-key auth (headers come
        in via ``transport_override``).
    base_url: The base URL to join the template onto, or a callable returning
        it — see :data:`BaseUrl`.
    timeout: Request timeout in seconds.
    body_case: Case convention for body keys ("camel", "snake", "pascal", "kebab").
    query_case: Case convention for query keys.
    path_case: Case convention for path keys.
    transport_override: Optional override for path, query, body, or headers.
    provider: Provider name, used only to label a ``CredentialError``.
    envelope: How this API reports failure inside a 200 response. See
        :class:`~charter.types.envelope.Envelope`.
    body_format: ``"json"`` (default) or ``"form"`` for
        ``application/x-www-form-urlencoded``.
    query_format: ``"repeat"`` (default) or ``"bracket"`` for APIs that expect
        ``expand[0]=x`` rather than repeated keys.
    static_query: Query parameters sent on every request, verbatim — no casing
        conversion, and not overridable by tool input.
    static_headers: Headers sent on every request, verbatim.
    static_body: Body keys sent on every request, verbatim. This is how a
        constant that belongs in the *body* is declared — a GraphQL query
        document, a JSON-RPC ``method`` — without putting it in the schema,
        where the model would see it and could rewrite it.
    request_headers: Headers for this one call, supplied by the host
        application. Applied last, so they are the final word.
    client: An ``httpx.AsyncClient`` to reuse. One is created per call if omitted.
    probe: Optional scratch object the caller owns; the upstream timing and the
        exact request/response sizes are written into it. Measurement only —
        nothing here reads it back, and ``None`` disables it.
    credential_statuses: Which statuses mean "re-authenticate". Defaults to
        :data:`DEFAULT_CREDENTIAL_STATUSES` — see it for why that is 401 alone.
    body_field_count: How many fields the *declared* schema routes to the body,
        which is what decides whether a single ``Body()`` field unwraps. Supplied
        by :class:`~charter.execution.executor.ToolExecutor`, which holds the
        declaration; omitted, it is counted off ``tool_input`` itself, which is
        right only when that model is the declaration. See
        :func:`~charter.types.markers.declared_body_fields`.
    credential_headers: Names of the headers carrying this request's credential,
        dropped if a redirect leaves the origin. Supplied by
        :class:`~charter.execution.executor.ToolExecutor`, the only thing that
        knows which of the headers it assembled is the secret —
        ``Authorization`` for a bearer tool, whatever the API named it for an
        api-key one. :data:`_SENSITIVE_HEADER_KEYS` is the floor either way.
    follow_redirects: Whether a 3xx is followed. ``False`` by default, which is
        httpx's own default and the right one for a JSON API: a redirect there
        is usually a misconfigured URL, and following it silently would hide
        that. ``True`` is for endpoints whose *answer* is a redirect —
        GitHub hands out logs and artifacts as a 302 to a short-lived signed
        URL, and a caller that does not follow it receives an empty body and no
        way to ask again. No credential travels to the host the redirect names,
        whether it is a bearer token or an api key — see :func:`_send`.

    Raises
    ------
    CredentialError: on a status in ``credential_statuses`` (401 by default), or
        on an envelope-declared credential failure.
    APIError: on any other >= 400 response, or an envelope-declared failure.
    """
    # Extract parameters from the Pydantic model
    path, params, body, body_source = _extract_http_params(tool_input, body_field_count)

    # The one marker the path honours. See the interpolation below for why it is
    # this and not the full cascade.
    wire_names = {
        name: marker.name
        for name, field in type(tool_input).model_fields.items()
        for marker in field.metadata
        if isinstance(marker, WireName)
    }

    # Apply transport overrides if provided (MERGE, not replace)
    if transport_override:
        # Merge path parameters (per-key)
        path_override = transport_override.get("path")
        if path_override:
            path.update(path_override)

        # Merge query parameters (per-key)
        query_override = transport_override.get("query")
        if query_override:
            params.update(query_override)

        # Body handling - more complex due to single-body semantics
        override_body = transport_override.get("body")
        if override_body is not None:
            if isinstance(body, dict) and isinstance(override_body, dict):
                # Both are dicts - shallow merge
                body = {**body, **override_body}
            else:
                # Replace entirely (common case for transformed fields)
                body = override_body

    # Build URL with path parameters.
    # A callable base_url is resolved per request, so a pack whose host is a
    # property of the installation rather than of the API can be configured
    # after its tools are built.
    resolved_base = base_url() if callable(base_url) else base_url
    if not resolved_base:
        raise DeclarationError(
            "No base URL is configured for this tool. A pack whose host depends on "
            "the installation (a Shopify store, a Zendesk subdomain) must be "
            "configured before use.",
            docs="reference/configuration",
        )

    # Ensure base_url ends with a slash and url_template does not start with one.
    base_url = resolved_base
    if not base_url.endswith("/"):
        base_url += "/"
    if url_template.startswith("/"):
        url_template = url_template[1:]

    # A path value comes from the model, so it is escaped before it can rewrite
    # the URL it is being interpolated into. See _escape_path_params.
    path = _escape_path_params(path, tool_input)

    # Apply path_case conversion to path param keys before URL interpolation.
    # A WireName wins over the convention, as it does everywhere else.
    #
    # Deliberately *not* the key plan the body and query use. A path key is not a
    # key on the wire, it is the name of a hole in `url_template` that the pack
    # author wrote — so the only thing that may rename it is something naming it
    # outright. A model's `__case__` reaches every key in that model, which is
    # the right scope for a body and the wrong one here: a schema declaring
    # `__case__ = "pascal"` for its body would rename `doc_id` to `DocId` and
    # then fail to fill `{doc_id}`, which is not a wire mismatch but a template
    # that no longer has its parameter.
    if path_case != "snake" or wire_names:
        path = {
            wire_names.get(k) or DictKeyParser.convert_key(k, path_case): v for k, v in path.items()
        }

    try:
        url = f"{base_url}{url_template.format(**path)}"
    except KeyError as e:
        missing_key = str(e).strip("'")
        raise ValueError(
            f"Missing required path parameter '{missing_key}' for URL template "
            f"'{url_template}'. Available parameters: {list(path.keys())}"
        ) from e

    # Build headers.
    #
    # `httpx.Headers`, not a dict, because every `update` below is a precedence
    # rule and a dict cannot express one: HTTP header names are case-insensitive,
    # so `{"Idempotency-Key": ...}` and `{"idempotency-key": ...}` are two keys
    # in a dict and one header on the wire. Both survived, httpx joined them with
    # a comma, and the later one — the caller's, documented here as the final
    # word — neither won nor lost. The same shape sent an api-key credential
    # twice when `static_headers` spelled it differently from `api_key_headers`,
    # which is a malformed credential rather than a cosmetic duplicate.
    # `Headers.update` replaces by lowercased name, so the cascade means what it
    # says whatever anyone spelled.
    headers = httpx.Headers()

    if credentials is not None:
        headers["Authorization"] = f"Bearer {credentials.token}"

    # Apply the key cascade to the body.
    #
    # Read off whichever model the body's keys belong to: the unwrapped field's
    # own model when one field became the body, and the request model otherwise.
    # `_extract_http_params` reports which, rather than this deciding a second
    # time — the two answers disagreeing is how `WireName` came to need a special
    # case here that `Case` never got.
    #
    # The plan reaches every depth, so a nested model's `__case__` and a nested
    # field's `Case` mean what the cascade documents rather than stopping at the
    # root. Keys the plan does not name — what a transform produced, a free-form
    # mapping — fall back to the endpoint's case, which is what they always did.
    if body is None:
        json_payload = body
    else:
        if body_source is not None:
            # The body is one field's value, so its keys are that field's —
            # `plan_for` resolves the container shape as well as the model, and
            # answers None when there is no declaration to read (a transformed
            # payload, a free-form mapping).
            body_plan = plan_for(body_source, body_case)
        else:
            body_plan = key_plan(type(tool_input), body_case)
        json_payload = convert_with_plan(body, body_plan, body_case)

    # Apply the key cascade to the query, off the same graph at the query case.
    #
    # Unconditional, where this used to be gated on `query_case != "snake"` plus
    # a list of the overrides that had been found. The gate is what dropped a
    # field-level `Case` whenever a factory left `query_case` at its snake
    # default — six of the twelve shipped packs — while the body path beside it
    # honoured the same marker. Nothing failed loudly: a query parameter under
    # the wrong name is usually ignored rather than rejected.
    params_payload = (
        convert_with_plan(params, key_plan(type(tool_input), query_case), query_case)
        if isinstance(params, dict)
        else params
    )

    # Bracket-notation query, for APIs that serialise structured query values the
    # same way they serialise bodies (Stripe: expand[0]=x, created[gte]=...).
    if query_format == "bracket" and isinstance(params_payload, dict):
        params_payload = dict(_flatten_form(params_payload))

    # Static body keys are wire-literal for the same reason as static_query: a
    # GraphQL document lives under the key `query`, and casing it would break the
    # request. Applied last so tool input cannot overwrite the constant — the
    # model must not be able to rewrite the query document it is calling.
    if static_body is not None:
        if body_format == "raw":
            raise DeclarationError(
                "static_body cannot be merged into a raw body: a raw body is the "
                "bytes themselves, with no object to add a key to.",
                docs="reference/markers#body",
            )
        if json_payload is None:
            json_payload = dict(static_body)
        elif isinstance(json_payload, dict):
            json_payload = {**json_payload, **static_body}
        else:
            raise DeclarationError(
                "static_body can only be merged into an object body, but this schema "
                f"produced {type(json_payload).__name__}. A single Body() field unwraps "
                "to its bare value — use Body(envelop=True) to keep the field name, or "
                "mark several fields Body().",
                docs="reference/markers#body",
            )

    # Static query parameters are wire-literal: applied after casing so an
    # `api-version` key is not helpfully renamed to `apiVersion`, and applied
    # last so tool input cannot override infrastructure.
    if static_query:
        if not isinstance(params_payload, dict):
            params_payload = {}
        params_payload = {**params_payload, **static_query}

    # Static headers sit between auth and the transport override, so a caller's
    # explicit override still wins.
    if static_headers:
        headers.update(static_headers)

    # Only set Content-Type when we have a JSON body. The form path lets httpx
    # set application/x-www-form-urlencoded itself.
    if json_payload is not None and method != "GET" and body_format == "json":
        headers["Content-Type"] = "application/json"

    # Apply header overrides if provided (after setting defaults)
    if transport_override:
        headers_override = transport_override.get("headers")
        if headers_override:
            headers.update(headers_override)

    # Per-request headers come from the host application at the call site, so they
    # are the most specific authority and are applied last. None values are
    # dropped, which lets a caller pass an optional header unconditionally.
    if request_headers:
        headers.update({k: str(v) for k, v in request_headers.items() if v is not None})

    if logger.isEnabledFor(logging.DEBUG):
        req_extra: Dict[str, Any] = {"headers": _mask_headers_for_log(headers)}
        if params_payload:
            req_extra["query"] = params_payload
        if json_payload is not None:
            req_extra["body"] = _truncate_base64_for_log(json_payload)
        logger.debug("HTTP → %s %s", method, url, extra={"charter_request": req_extra})

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        # Don't use a falsy check — an empty dict {} is a valid JSON body.
        request_kwargs: Dict[str, Any] = {
            "params": params_payload,
            "headers": headers,
        }
        if json_payload is not None:
            if body_format == "raw":
                # The body is a file, not a document. Whatever Content-Type the
                # declaration set stands; httpx would not guess one anyway.
                if not isinstance(json_payload, (str, bytes)):
                    raise DeclarationError(
                        "A raw body must be a string or bytes, but this schema produced "
                        f"{type(json_payload).__name__}. Mark exactly one Body() field, "
                        "which unwraps to its bare value.",
                        docs="reference/markers#body",
                    )
                request_kwargs["content"] = (
                    json_payload.encode() if isinstance(json_payload, str) else json_payload
                )
            elif body_format == "form":
                # Form encoding has no way to express a top-level array or scalar,
                # and no form-encoded API accepts one. A single Body() field
                # unwraps by default, which is how you get here.
                if not isinstance(json_payload, dict):
                    raise DeclarationError(
                        "A form-encoded body must be a mapping of named fields, but this "
                        f"schema produced {type(json_payload).__name__}. A single Body() "
                        "field unwraps to its bare value — use Body(envelop=True) to keep "
                        "the field name, or mark several fields Body().",
                        docs="reference/markers#body",
                    )
                request_kwargs["data"] = dict(_flatten_form(json_payload))
            else:
                request_kwargs["json"] = json_payload
        # From here to the response is the provider's time, and only the
        # provider's. Everything Charter does sits outside this window, which is what
        # makes the overhead figure in a ToolCall an honest one.
        if probe is not None:
            probe.reached_network = True
        upstream_started = perf_counter()
        try:
            resp = await _send(
                http,
                method,
                url,
                request_kwargs,
                follow_redirects=follow_redirects,
                credential_headers=(
                    _SENSITIVE_HEADER_KEYS | {name.lower() for name in credential_headers}
                    if credential_headers is not None
                    else _SENSITIVE_HEADER_KEYS
                ),
            )
        finally:
            if probe is not None:
                probe.upstream_ms = (perf_counter() - upstream_started) * 1000
    finally:
        if owns_client:
            await http.aclose()

    if probe is not None:
        probe.status_code = resp.status_code
        if probe.observed:
            # Taken off the request httpx actually sent and the body it actually
            # read, so neither is a re-serialisation estimate. `resp.content` is
            # post-decompression: this is what the payload costs to hold and to
            # read, not what it cost the network.
            #
            # Guarded, because measuring a call must never be able to fail it —
            # the same rule `Tool._report` follows on the way out. A request
            # built for a redirect hop carries a stream that was never read, and
            # `.content` raises `RequestNotRead` on it: an observed call that
            # followed a redirect died here, after a perfectly good response,
            # and only when somebody was watching.
            try:
                probe.request_bytes = len(resp.request.content) + len(resp.request.url.query)
            except Exception:
                probe.request_bytes = len(resp.request.url.query)
            probe.payload_bytes = len(resp.content)

    content_type = (resp.headers.get("content-type") or "").lower()
    is_json_like = ("application/json" in content_type) or content_type.endswith("+json")

    if resp.status_code >= 400:
        logger.warning("HTTP ← %s %s", resp.status_code, resp.reason_phrase)
        # `credentials is None` is api-key mode: the executor resolves the
        # headers itself and passes no bearer credential. It decides which page
        # a rejected credential links to, and the two pages disagree about who
        # they are for.
        _raise_for_status(
            resp,
            url,
            provider,
            frozenset(credential_statuses)
            if credential_statuses is not None
            else DEFAULT_CREDENTIAL_STATUSES,
            bearer=credentials is not None,
        )

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("HTTP ← %s %s", resp.status_code, resp.reason_phrase)

    # Handle empty body (e.g. 204 No Content)
    if not resp.content:
        return {}

    if is_json_like:
        try:
            payload = resp.json()
        except Exception:
            pass
        else:
            # Some APIs answer 200 and put the failure in the body. The envelope
            # says where to look; without one, a 200 is taken at face value.
            if envelope is not None:
                try:
                    envelope.raise_for_payload(
                        payload,
                        url=url,
                        provider=provider,
                        bearer=credentials is not None,
                    )
                except CharterError:
                    # Flag it: the envelope is the only thing that knows this 200
                    # was really a failure, and a record that says `http_error 200`
                    # invites the reader to disbelieve it.
                    if probe is not None:
                        probe.envelope_failed = True
                    raise
            return payload

    # Non-JSON successful response. `resp.text` decodes bytes against the
    # charset the response declares and *replaces* anything that does not fit,
    # so running a ZIP or a PNG through it produces replacement characters that
    # read as content — the "decode that degrades instead of failing" failure,
    # one layer below where a response handler could catch it. A body that is
    # not text keeps its bytes instead, base64-encoded, with the two facts a
    # handler needs to decide what to do with them.
    if _is_textual(content_type):
        return {"raw": resp.text}
    return {
        "raw_base64": b64encode(resp.content).decode("ascii"),
        "content_type": content_type or "application/octet-stream",
        "size_bytes": len(resp.content),
    }
