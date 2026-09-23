# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The Tool: one API endpoint, declared as a schema.

A ``Tool`` binds a Pydantic schema to an HTTP endpoint and executes it locally,
in your process. It is not a LangChain tool, an MCP tool, or an OpenAI function
— those are :mod:`views <charter.adapters>` onto this one object.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import threading
from time import perf_counter
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)

import httpx
from pydantic import BaseModel

from charter.auth import CredentialProvider
from charter.execution.executor import ApiKeyHeaders, ResponseHandler, ToolExecutor
from charter.execution.http import BaseUrl, BodyFormat, HTTPMethod, QueryFormat
from charter.execution.schema import (
    _get_field_modes,
    create_llm_schema,
    in_force,
    llm_json_schema,
    should_include_field,
)
from charter.execution.validation import validate_input
from charter.observability import (
    CallProbe,
    CallSink,
    ToolCall,
    current_sinks,
    format_call_line,
)
from charter.types.envelope import Envelope
from charter.types.markers import KeyCase, TransportOverride
from charter.types.pagination import Pagination

if TYPE_CHECKING:  # pragma: no cover - typing only
    from charter.derive import PathCost

__all__ = ["Tool"]

logger = logging.getLogger("charter")


def _check_mode(mode: Any, where: str) -> None:
    """A mode is a label, or it is ``None``. There is no empty label.

    :func:`should_include_field` guards on ``if mode``, so *any falsy* mode reads
    as "no mode was given at all" — which is the **widest** view, where every
    custom label is inert and every tiered field is offered. ``None`` is the
    documented way to say that, and :class:`~charter.ToolSession` checks for it
    by identity before it copies anything.

    An empty string is not that. It arrives from a runtime value —
    ``ToolSession(tools, mode=plan_of(request.user))``, where a nullable plan
    column or a ``user.plan or ""`` hands back ``""`` for the smallest tier — and
    reading it as "no tier" widens the surface instead of narrowing it. It
    overrides a mode the *pack* shipped with, too: a tool built ``mode="free"``
    in a session at ``""`` goes from one field to every field the schema
    declares.

    That is the one direction a deployer's label must never move egress, and it
    is the only direction a wrong one can. A misspelt or unknown label fails
    closed — ``"prro"`` matches nothing and withholds everything optional — so
    this check is not about labels that are wrong, only about the one that is
    empty. Refused here, where ``derived()``, :meth:`Tool.with_mode` and a
    hand-built tool all converge, rather than at each door.
    ``ToolSession`` calls it once more on its own argument, for the surface that
    holds no tools to reach this one through.
    """
    from charter.types.errors import DeclarationError

    if mode is None or (isinstance(mode, str) and mode.strip()):
        return
    raise DeclarationError(
        f"mode {mode!r} ({where}) is not a label. A mode is a non-empty "
        f"string naming one of the labels the schema declares, or None for no mode at "
        f"all — and None is the *widest* view, not the narrowest, because a custom "
        f"Mode() is inert when there is nothing to match it against. An empty mode "
        f"would resolve that way too, so a tier that came back empty would be served "
        f"every tier's fields. Pass the label, or None if that is what you mean.",
        docs="boundary/mode-system",
    )


def _check_required_at_mode(
    source_schema: Type[BaseModel],
    modes: FrozenSet[str],
    prune: FrozenSet[str],
    tool_name: str,
) -> None:
    """A field the API requires has to survive the mode that resolves the view.

    ``Mode`` moves visibility and requiredness is a separate axis, so a mode can
    take a *required* field out of the view the model fills in — and then nothing
    puts it back. The tool constructs, validates a call that never mentions the
    field, and sends a body without it: a 400 on every call, naming a field the
    deployer never saw offered.

    :func:`~charter.derive._check_required` already refuses exactly this removal
    when a projection asks for it by path. The same removal reached through a
    label went unchecked, which mattered little while only the pack author could
    write ``mode=`` and matters now that :meth:`Tool.with_mode` and
    :class:`~charter.ToolSession` hand that lever to a deployer, who has no way
    to know which label makes which tool uncallable.

    Only the deployer's half is checked. A required field marked
    ``Mode("response_only")`` or ``Mode("disabled")`` is withheld at every label,
    so no mode did that and no mode can fix it — it is the author's own
    declaration, and :func:`~charter.egress_map` already reports it. The test is
    therefore "present with no mode, absent at this one", which is the mode's
    doing exactly.

    Walks into kept fields only, which is what makes one visited set correct
    here. A cascade only ever *removes*, and a field the mode kept carries a
    label the mode matches, so everything under it inherits a cascade that
    matches too — the answer for a nested model does not depend on the route
    taken to reach it. A subtree the mode removed is reported by its own root
    field and not descended into: if that root is optional, the API never sees
    the branch and nothing is missing; if it is required, it is the finding.
    """
    from charter.types.errors import DeclarationError

    if not modes:
        # No partition is in force, so nothing custom is filtered and this cannot
        # fire. Skipping keeps it off the import path of the 543 shipped tools
        # that declare no mode.
        return

    missing: List[str] = []
    seen: Set[int] = set()
    stack: List[Tuple[Type[BaseModel], str, Optional[set]]] = [(source_schema, "", None)]
    while stack:
        model, path, parent_modes = stack.pop()
        if id(model) in seen:
            continue
        seen.add(id(model))
        for field_name, field in model.model_fields.items():
            field_path = f"{path}.{field_name}" if path else field_name
            if field_path in prune:
                # A projection removed it, and `_check_required` ruled on that
                # when the projection was planned — including the pin that makes
                # dropping a required field legal.
                continue
            if not should_include_field(field, modes, parent_modes):
                if field.is_required() and should_include_field(field, None, parent_modes):
                    missing.append(field_path)
                continue
            field_modes = _get_field_modes(field) or parent_modes
            # `_models_in`, not an unwrap that takes the first member of a
            # union: this is a guard, and a model it does not reach is a model
            # nobody checked. `Union[Draft, Published]` would hide a required
            # field in the second half otherwise. That argument is already
            # written out above that function.
            stack.extend(
                (nested, field_path, field_modes) for nested in _models_in(field.annotation)
            )

    if not missing:
        return

    listed = ", ".join(repr(path) for path in sorted(missing))
    them = "it" if len(missing) == 1 else "them"
    raise DeclarationError(
        f"{_labels(modes)} withholds {listed}, which the API requires, so {tool_name!r} "
        f"cannot be called: the request would go out without {them} and be rejected "
        f"every time. A required field has to be visible at every label the pack "
        f"offers — name each of them in its Mode(), or leave it unlabelled — and a "
        f"constant the API needs on every call belongs in static_body/static_query on "
        f"the factory rather than in the schema.",
        docs="boundary/mode-system",
    )


def _labels(modes: FrozenSet[str]) -> str:
    """A set of labels, named the way an error should name it.

    One reads as `mode 'free'` and two as `modes 'create' and 'free'`, because
    both messages below are about a field that no label in force reaches and the
    reader needs to see every label that was in force to know which one to
    change.
    """
    listed = sorted(modes)
    if len(listed) == 1:
        return f"mode {listed[0]!r}"
    return "modes " + " and ".join(repr(label) for label in listed)


def _check_pins_reachable(
    source_schema: Type[BaseModel],
    exec_schema: Type[BaseModel],
    pins: Dict[str, Any],
    modes: FrozenSet[str],
    tool_name: str,
) -> None:
    """A pinned field has to survive into the view the runtime executes.

    The pin is merged into that view and revalidated against it, and the view
    forbids extras, so a pin the ``Mode`` filtering removed does not go quiet or
    arrive un-pinned: it fails *every* call with a validation error naming a
    field the caller never set. This used to be reachable and silent at
    declaration, because the value check below skipped a field it could not
    find.

    Two ways to get here, wanting different answers. A field marked
    ``response_only`` or ``disabled`` is refused whatever the mode, so no label
    fixes it and the pin is the mistake. A field carrying a custom ``Mode`` is
    refused only at the labels that do not name it, so the pin and the mode are
    each defensible on their own and it is the pair that is not.
    """
    from charter.types.errors import DeclarationError

    missing = sorted(path for path in pins if path not in exec_schema.model_fields)
    if not missing:
        return

    listed = ", ".join(repr(path) for path in missing)
    verb = "is" if len(missing) == 1 else "are"

    def withheld_at_every_mode(path: str) -> bool:
        field = source_schema.model_fields.get(path)
        return field is not None and not should_include_field(field, None, None)

    if all(withheld_at_every_mode(path) for path in missing):
        raise DeclarationError(
            f"pin: {tool_name!r} pins {listed}, which {verb} withheld from the model "
            f"at every mode, so the value would be rejected on every call. A field "
            f"marked Mode('response_only') or Mode('disabled') cannot be pinned. If "
            f"the API does accept it, send it with static_body/static_query on the "
            f"factory, which puts a constant on the wire without a schema field.",
            docs="tools/projections",
        )
    raise DeclarationError(
        f"{_labels(modes)} withholds {listed}, which {tool_name!r} pins. A pinned field "
        f"has to survive the modes that resolve the view, or the value it sends is "
        f"rejected on every call.",
        docs="tools/projections",
    )


def _check_pin_values(exec_schema: Type[BaseModel], pins: Dict[str, Any]) -> None:
    """A pinned value has to satisfy the field it is pinned to.

    Checked against the *executed* view, not the declared one, because that is
    where a ``Format`` field carries its semantic type: ``raw`` is a base64
    string on the wire and an ``EmailContent`` here, and the pin is written in
    the second of those.

    Every pinned field is present here: :func:`_check_pins_reachable` runs first
    and refuses the tool otherwise.
    """
    from pydantic import TypeAdapter

    from charter.types.errors import DeclarationError

    for path, value in pins.items():
        field = exec_schema.model_fields[path]
        try:
            TypeAdapter(field.annotation).validate_python(value)
        except Exception as exc:
            raise DeclarationError(
                f"pin: the value for {path!r} does not satisfy that field: {exc}",
                docs="tools/projections",
            ) from exc


def _check_schema_resolvable(
    args_schema: Type[BaseModel],
    name: str,
    verified: Optional[Dict[int, Any]] = None,
) -> None:
    """Every model the schema reaches can resolve its own annotations.

    Deriving the view on first use moved every error :func:`create_llm_schema`
    raises out of construction and into whichever agent run touches the tool
    first, where it arrives as a raw ``PydanticUndefinedAnnotation`` rather than
    a :class:`~charter.types.errors.DeclarationError` naming the declaration that
    is wrong. This puts the one that actually happens back where it was.

    A model whose annotations name something not in scope — a forward reference
    to a class that was renamed, a ``model_rebuild()`` the pack forgot — is left
    by pydantic with ``__pydantic_complete__`` False, and it stays usable enough
    to declare a tool with and unusable the moment anything asks for a schema.
    That is the shape that once left 17 Linear tools unable to emit a schema at
    all, and it is cheap to see coming: walking the source models is a read of
    ``model_fields`` per model on the *graph*, where each appears once — 6.5ms
    for Linear's 145 tools, 25ms across all 566 the shipped packs declare.

    It is not a promise that nothing else can fail late. It is the failure mode
    that has happened, caught where its cause is written.

    ``verified`` is the factory's memo of models already cleared. Without one the
    check is per tool, and a pack whose tools share a large graph pays for it
    once each: Linear's 145 tools re-walk the same filter graph and it comes to
    208ms rather than 6.5ms. Entries hold the class, so the id they are keyed by
    cannot be recycled — and they never need invalidating, because
    ``__pydantic_complete__`` only ever goes False to True.
    """
    from charter.types.errors import DeclarationError

    stack: List[Type[BaseModel]] = [args_schema]
    # id -> the class, so an entry keeps alive the object its key is the address
    # of. A set of bare ids would let CPython hand one out again.
    seen: Dict[int, Type[BaseModel]] = {}
    while stack:
        model = stack.pop()
        key = id(model)
        if key in seen or (verified is not None and key in verified):
            continue
        seen[key] = model
        if not getattr(model, "__pydantic_complete__", True):
            raise DeclarationError(
                f"{name}: {model.__name__} cannot resolve its own annotations, so "
                f"no view of this tool can be built. A forward reference names "
                f"something not in scope — call {model.__name__}.model_rebuild() "
                f"once every class it refers to is defined.",
                docs="reference/errors#declarationerror",
            )
        for field in model.model_fields.values():
            stack.extend(_models_in(field.annotation))

    if verified is not None:
        # Written only once the whole walk has cleared, so a walk that raised
        # part way through leaves nothing behind claiming to have been checked.
        verified.update(seen)


def _models_in(annotation: Any) -> Sequence[Type[BaseModel]]:
    """Every model an annotation reaches, through any container.

    Deliberately *every* one, where :func:`charter.derive._unwrap` takes the
    first: that one resolves a path a person typed, and the first member is the
    one they meant. This one is a completeness check, so a model it does not
    reach is a model nobody checked — a silent hole in a guard is worse than no
    guard, and ``Union[Draft, Published]`` would be exactly that.

    No depth bound for the same reason. An annotation is a finite tree and every
    step strips a layer, so the walk ends on its own; a bound would turn one
    nested deeper than it into something the check skips without saying so.
    """
    if get_origin(annotation) is None:
        # The overwhelmingly common shape, and it runs once per field of every
        # model of every tool at import. Answered without building anything.
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return (annotation,)
        return ()

    found: List[Type[BaseModel]] = []
    stack: List[Any] = [annotation]
    while stack:
        current = stack.pop()
        if get_origin(current) is not None:
            stack.extend(
                arg for arg in get_args(current) if arg is not type(None) and arg is not Ellipsis
            )
        elif isinstance(current, type) and issubclass(current, BaseModel):
            found.append(current)
    return found


def _measure(value: Any) -> Optional[int]:
    """Compact-JSON size of ``value``, or ``None`` if it will not serialise.

    Both sides of the trimming figure go through this one function, so the
    payload and what the model receives are measured the same way. Comparing a
    compact response body against a pretty-printed dict would inflate the saving
    with whitespace, which is the easiest way to make this number a lie.
    """
    try:
        return len(json.dumps(value, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        return None


class Tool:
    """An API endpoint declared as a Pydantic schema.

    The schema is the contract: ``Path``/``Query``/``Body`` markers say where each
    field goes, ``Format`` says how it is encoded, ``Mode`` says who may see it,
    and ``Case`` says how its key is spelled on the wire.

    ``pagination`` declares where this API keeps its cursor, so a caller can page
    without knowing the convention. It declares the location; it does not loop.

    ``body_format`` is ``"json"`` unless the API wants
    ``application/x-www-form-urlencoded`` (Stripe, Twilio, OAuth2 token
    endpoints). ``static_query`` and ``static_headers`` are values sent verbatim
    on every request — an Azure ``api-version``, a ``Notion-Version``.

    ``envelope`` declares how the API reports failure inside a 200 response —
    some do, and a runtime that trusts the status line hands those back as
    successes. See :class:`~charter.types.envelope.Envelope`.

    ``expiry_leeway_seconds`` is how dead a bearer token has to be before the
    runtime refuses to send it. It is a last guard, not a refresh policy —
    keeping credentials fresh is the provider's job, and
    :class:`~charter.auth.OAuth2Client` renews well before this. Ten seconds covers
    clock skew and the request itself; rejecting a token the server still calls
    valid for a minute would be the runtime overruling the server.

    ``on_call`` receives a :class:`~charter.observability.ToolCall` after every
    invocation — what it cost, what it returned, and whether it reached the
    network at all. There is no default sink and no ambient registry: a tool
    reports to whoever was named when it was built, or to nobody.

    ``pack`` names the tool's namespace — ``"gsheets"``, ``"stripe"``, your own
    ``"acme"``. It answers a different question from the two fields it sits
    between, and all three are needed: ``provider`` is *which credential*
    (gmail, gcalendar, gsheets, gdocs and gdrive all authenticate as ``"google"``),
    ``base_url`` is *which host* (gmail, calendar, sheets and docs use four
    different ones; Drive shares Calendar's), and
    ``pack`` is *which namespace*. It is what
    :func:`~charter.naming.qualified_names` builds ``<pack>__<tool>`` from when
    several packs are assembled into one tool surface and their names would
    otherwise collide — ``products_list`` exists in both Stripe and Shopify.

    Left unset, a tool simply cannot be qualified; nothing else changes.

    ``quota_cost`` records what one call costs against the provider's *own* rate
    limit, in that provider's units (Gmail bills ``messages.send`` at 100 and
    ``messages.list`` at 5; Calendar bills every request at 1). It is metadata
    today — nothing in the runtime enforces it — but it is the input a budget
    policy needs, and it is expensive to re-derive endpoint by endpoint later.

    ``prune`` and ``pins`` are what :meth:`derived` sets, and are the one pair of
    constructor arguments normally reached through a method rather than written:
    a projection is easier to declare by what it keeps than by listing the paths
    it removes.

    Build one directly, or — more usually — from
    :func:`~charter.factories.api_key_tool_factory` /
    :func:`~charter.factories.oauth_tool_factory`, which carry the per-API defaults.

    Example::

        class GetWeather(BaseModel):
            city: Annotated[str, Path()]
            units: Annotated[Optional[str], Query()] = "metric"

        tool = Tool(
            name="get_current_weather",
            description="Get current weather for a city.",
            method="GET",
            url_template="data/2.5/weather/{city}",
            args_schema=GetWeather,
            base_url="https://api.openweathermap.org/",
            api_key_headers={"x-api-key": os.environ["OPENWEATHER_API_KEY"]},
        )

        await tool.ainvoke(city="Tokyo")
    """

    def __init__(
        self,
        *,
        name: str,
        method: HTTPMethod,
        url_template: str,
        args_schema: Type[BaseModel],
        base_url: BaseUrl,
        description: str = "",
        action_label: Optional[str] = None,
        body_case: KeyCase = "camel",
        query_case: KeyCase = "snake",
        path_case: KeyCase = "snake",
        timeout: int = 20,
        mode: Optional[str] = None,
        session_mode: Optional[str] = None,
        pack: Optional[str] = None,
        provider: Optional[str] = None,
        scopes: Optional[Sequence[str]] = None,
        quota_cost: Optional[int] = None,
        quota_doc_url: Optional[str] = None,
        api_key_headers: Optional[ApiKeyHeaders] = None,
        credential_provider: Optional[CredentialProvider] = None,
        build_request: Optional[Callable[[BaseModel], TransportOverride]] = None,
        response_handler: Optional[ResponseHandler] = None,
        envelope: Optional[Envelope] = None,
        pagination: Optional[Pagination] = None,
        body_format: BodyFormat = "json",
        query_format: QueryFormat = "repeat",
        static_query: Optional[Dict[str, Any]] = None,
        static_headers: Optional[Dict[str, str]] = None,
        static_body: Optional[Dict[str, Any]] = None,
        on_call: Optional[CallSink] = None,
        expiry_leeway_seconds: int = 10,
        credential_statuses: Optional[Iterable[int]] = None,
        follow_redirects: bool = False,
        prune: Optional[Iterable[str]] = None,
        pins: Optional[Dict[str, Any]] = None,
        llm_cache: Optional[Dict[Any, Any]] = None,
    ) -> None:
        self.name = name
        self.description = description
        # Written out rather than inferred: a bare attribute widens a
        # Literal-typed parameter to str, and derived() and the executor both
        # pass these back into signatures that declare the Literals.
        self.method: HTTPMethod = method
        self.url_template = url_template
        self.base_url = base_url
        self.action_label = action_label
        self.body_case: KeyCase = body_case
        self.query_case: KeyCase = query_case
        self.path_case: KeyCase = path_case
        self.timeout = timeout
        # Two ends of one marker, kept apart on purpose. `mode` is the label the
        # *author* declared, and it says which operation this tool is: `create`
        # replaces and `update` merges, and no deployment changes that.
        # `session_mode` is the label a *deployment* resolved it at, and it says
        # which surface this conversation is — a tier, a region, a scope. Both
        # are in force at once; see `Tool.modes`.
        self.mode = mode
        self.session_mode = session_mode
        self.pack = pack
        self.provider = provider
        self.scopes = list(scopes) if scopes else []
        self.quota_cost = quota_cost
        self.quota_doc_url = quota_doc_url
        self.api_key_headers = api_key_headers
        self.credential_provider = credential_provider
        self.envelope = envelope
        self.pagination = pagination
        self.body_format: BodyFormat = body_format
        self.query_format: QueryFormat = query_format
        self.static_query = dict(static_query) if static_query else None
        self.static_headers = dict(static_headers) if static_headers else None
        self.static_body = dict(static_body) if static_body is not None else None
        self.on_call = on_call
        self.expiry_leeway_seconds = expiry_leeway_seconds
        self.credential_statuses = (
            frozenset(credential_statuses) if credential_statuses is not None else None
        )
        self.follow_redirects = follow_redirects

        self.args_schema: Type[BaseModel] = args_schema

        # Kept on the tool, not only handed to the executor, because `derived`
        # rebuilds a Tool and a projection that quietly lost the pack's response
        # handler would return a different shape from the tool it narrowed.
        self._build_request = build_request
        self._response_handler = response_handler
        self._prune: frozenset = frozenset(prune or ())
        self._pins: Dict[str, Any] = dict(pins or {})

        # The LLM view is derived once and kept for the life of the tool. A
        # library has no deploy boundary to invalidate a cache against.
        #
        # Building it is cheap for one tool, and that was assumed to mean cheap
        # for a pack - which is wrong wherever tools share a type graph. Linear's
        # 128 tools reach the same filters over and over: constructing them
        # called `create_llm_schema` 16,149 times and spent 28 seconds of import
        # doing it. `llm_cache` is the caller-owned store that function already
        # documents; a pack factory owns one, so a type no prune reaches is built
        # once for the pack instead of once per tool. Entries are keyed by the
        # source class's identity and hold a reference to it, so the id cannot be
        # recycled underneath them.
        #
        # Derived on first use rather than at construction. Even sharing one
        # cache, building 128 views is about half of what importing the Linear
        # pack costs, and a session exposes a handful of tools - the rest is
        # paid for and never looked at. What stays eager is everything that can
        # fail: `derived()` resolves its keep/drop paths before a Tool exists,
        # and a pinned tool still builds its exec view below, so a bad pin is
        # still a construction-time error.
        self._llm_cache = llm_cache
        self._llm_schema_built: Optional[Type[BaseModel]] = None
        self._exec_schema_built: Optional[Type[BaseModel]] = None
        self._json_schema: Optional[Dict[str, Any]] = None

        # Deriving on first use moved the build off the import thread and onto
        # whichever one calls first - and a tool is a process-wide object that
        # several of them reach at once. `Tool.invoke` is synchronous, so every
        # threaded host puts it there: a WSGI worker pool, LangChain running a
        # sync agent through an executor, `to_openai_tools` documented to run
        # inside the turn loop. Without this, two threads first-touching one
        # tool both build, and the second overwrites the view the first already
        # handed out. Reentrant because the pinned path reaches the LLM view
        # through the same guard.
        self._schema_lock = threading.RLock()

        # Deferring the build deferred every error the build can raise, and the
        # one that happens is a schema whose annotations do not resolve. Checked
        # here, on the source graph, so it is still a DeclarationError naming the
        # pack's own class at the line that declared the tool rather than a bare
        # PydanticUndefinedAnnotation out of an agent run. Costs a read of
        # `model_fields` per model on the graph: about 35ms across all 566 tools
        # the shipped packs declare.
        _check_schema_resolvable(args_schema, name, getattr(llm_cache, "verified", None))

        # The label itself, before anything resolves against it. An empty one
        # reads as "no mode at all" everywhere downstream, which is the widest
        # view rather than the narrowest — the one direction a deployer's label
        # must never move egress.
        _check_mode(mode, f"on tool {name!r}")
        _check_mode(session_mode, f"on tool {name!r}")

        # And the label against what the API demands. `Mode` moves visibility
        # and requiredness is a separate axis, so a label can take a required
        # field out of the view and leave a tool that constructs, validates, and
        # is rejected on every call. `derived(drop=...)` already refuses that
        # removal; reached through a mode it went unchecked.
        _check_required_at_mode(args_schema, self.modes, self._prune, name)

        # Pinned fields are absent from the view the model fills in and present
        # in the one the runtime executes, so a pinned value goes through the
        # same Format transform, body unwrapping and key casing as a supplied
        # one. Routing them separately looked simpler and was wrong twice: a
        # pinned `Format` field reached the wire un-encoded, and a pinned single
        # body field arrived wrapped in its own field name instead of becoming
        # the body.
        if self._pins:
            _check_pins_reachable(args_schema, self._exec_schema, self._pins, self.modes, name)
            _check_pin_values(self._exec_schema, self._pins)

        # build_request is auto-generated from the *original* schema: it is the
        # one that still carries the wire types the Format markers describe.
        self._executor = ToolExecutor(
            method=method,
            url_template=url_template,
            base_url=base_url,
            original_schema=args_schema,
            body_case=body_case,
            query_case=query_case,
            path_case=path_case,
            timeout=timeout,
            credential_provider=credential_provider,
            provider=provider or "",
            api_key_headers=api_key_headers,
            build_request=build_request,
            response_handler=response_handler,
            envelope=envelope,
            body_format=body_format,
            query_format=query_format,
            static_query=self.static_query,
            static_headers=self.static_headers,
            static_body=self.static_body,
            expiry_leeway_seconds=expiry_leeway_seconds,
            credential_statuses=credential_statuses,
            follow_redirects=follow_redirects,
        )

    # -----------------------------------------------------
    # Warm-up
    # -----------------------------------------------------

    @property
    def modes(self) -> FrozenSet[str]:
        """The labels in force for this tool: the author's, and a deployment's.

        The set every view is filtered against. A field carrying a custom
        ``Mode`` is offered when one of these names it, so a tool declared
        ``mode="create"`` and resolved by a session at ``"pro"`` keeps the fields
        that make it a create and gains the ones that make it pro.

        Empty means no partition is in force, which is the *widest* view and not
        the narrowest: a custom label is inert when there is nothing to match it
        against. That one rule is why a first label narrows and a second only
        ever widens. See :func:`~charter.execution.schema.in_force`.
        """
        return in_force((self.mode, self.session_mode))

    def prepare(self) -> Tool:
        """Build everything this tool derives lazily, now. Returns the tool.

        The views and the JSON schema are derived on first use, which is what
        keeps importing a pack cheap — a session exposes a handful of a pack's
        tools and the rest are never asked for. The cost does not vanish, it
        moves to whoever asks first, and on a recursive schema it is seconds
        rather than milliseconds: the first call to a cold ``linear.issues_list``
        spends about 1.8s building the filter graph before it validates anything.

        That is the wrong place for it twice over. It lands inside a request
        rather than at startup, and :meth:`ainvoke` is a coroutine, so on an
        async host that is 1.8 seconds during which nothing else on that event
        loop runs. Call this for the tools a process will actually expose, while it is
        still starting up::

            from charter.packs.linear import TOOLS

            for tool in TOOLS:           # at import, or in a readiness hook
                tool.prepare()

        Idempotent and cheap to repeat: a prepared tool returns immediately.
        Safe to call from several threads, and worth calling from only one — the
        threads will queue on the same build rather than duplicating it.

        :meth:`ainvoke` builds what it needs off the event loop if this was never
        called, so skipping it costs latency on one call, not correctness. What
        it cannot do anything about is a *synchronous* caller on the loop's
        thread: :func:`~charter.adapters.openai.to_openai_tools` is documented to
        run inside the turn loop and calls :meth:`to_json_schema`, which blocks
        wherever it is called from.
        """
        self._build_views()
        self.to_json_schema()
        return self

    def _build_views(self) -> Tuple[Type[BaseModel], Type[BaseModel]]:
        """Derive the model-facing view, and the executed one if this tool pins.

        The two builds a call needs, and not :meth:`to_json_schema`, which costs
        another 40ms on a large tool and is of no use to a call. Taken under the
        lock together, so a thread waiting on a pinned tool waits once.

        Both are returned rather than built and discarded: deriving them is a
        property access, and a bare one reads as a line that does nothing.
        """
        with self._schema_lock:
            llm = self._llm_schema
            return llm, (self._exec_schema if self._pins else llm)

    @property
    def _views_ready(self) -> bool:
        """Whether a call can proceed without building anything."""
        return self._llm_schema_built is not None and (
            not self._pins or self._exec_schema_built is not None
        )

    # -----------------------------------------------------
    # Introspection
    # -----------------------------------------------------

    def llm_schema(self) -> Type[BaseModel]:
        """The model the LLM fills in: mode-filtered and semantically typed.

        Differs from ``args_schema`` in that ``Mode("response_only")`` fields are
        gone and ``Format`` fields carry their semantic type (``EmailContent``
        rather than a base64 string).
        """
        return self._llm_schema

    @property
    def _llm_schema(self) -> Type[BaseModel]:
        """The model-facing view, built once on first use."""
        built = self._llm_schema_built
        if built is not None:
            return built
        with self._schema_lock:
            # Read again under the guard: the thread that waited for it must use
            # what the first one built, not build a second copy and publish that
            # over a view other callers are already holding.
            built = self._llm_schema_built
            if built is None:
                built = create_llm_schema(
                    self.args_schema,
                    mode=self.modes,
                    prune=self._prune or None,
                    cache=self._llm_cache,
                )
                self._llm_schema_built = built
            return built

    @_llm_schema.setter
    def _llm_schema(self, schema: Type[BaseModel]) -> None:
        """Substituting the view is how the conformance suite proves itself.

        `test_conformance_is_not_vacuous` strips a validator out of a tool's view
        and asserts the suite notices. That was a plain attribute before it was
        derived on demand, and a property without a setter would have made the
        suite unfalsifiable rather than merely awkward to test.
        """
        self._llm_schema_built = schema
        self._json_schema = None

    @property
    def _exec_schema(self) -> Type[BaseModel]:
        """The view the runtime executes: the LLM view plus the pinned fields."""
        if not self._pins:
            return self._llm_schema
        built = self._exec_schema_built
        if built is not None:
            return built
        with self._schema_lock:
            built = self._exec_schema_built
            if built is None:
                built = create_llm_schema(
                    self.args_schema,
                    mode=self.modes,
                    prune=(self._prune - set(self._pins)) or None,
                    cache=self._llm_cache,
                )
                self._exec_schema_built = built
            return built

    @_exec_schema.setter
    def _exec_schema(self, schema: Type[BaseModel]) -> None:
        self._exec_schema_built = schema

    def paths(
        self,
        under: str = "",
        *,
        depth: Optional[int] = 1,
        by_cost: bool = False,
    ) -> Union[List[str], List[PathCost]]:
        """The paths a projection can name, one level at a time.

            >>> gdocs.documents_batch_update.paths()
            ['document_id', 'body']
            >>> gdocs.documents_batch_update.paths("body.requests")
            ['insert_text', 'replace_all_text', 'update_text_style', ...]

        Without this, ``keep`` is guesswork — which is the whole argument for
        naming fields as strings rather than importing their classes, so it ships
        with them. Drill down by passing a prefix; ``depth=None`` returns the
        whole subtree, all 258 paths of a Docs batch update included.

        Paths pruned from this tool are gone, along with everything beneath them,
        so what comes back is what is still there to narrow.

        ``by_cost=True`` prices each one instead, most expensive first, as
        :class:`~charter.derive.PathCost` pairs::

            >>> linear.search_issues_full.paths("variables", by_cost=True)
            [PathCost(path='filter', tokens=46630),
             PathCost(path='first', tokens=50), ...]

        Which is the part a name alone cannot tell you, and the reason a list of
        eight names was not enough on its own. ``search_issues_full`` costs 47,026
        tokens, one recursive filter is 46,630 of them, and ``drop={"filter"}``
        leaves a 396-token tool — a 119-fold reduction hiding behind a field name
        that looks no more expensive than ``term`` or ``team_id``.

        The figure is measured, not estimated: each path is actually pruned and
        the schema regenerated, so it is what ``drop`` will do. That costs one
        schema generation per path, so only the level being returned is priced —
        drill down with ``under`` rather than pricing a whole subtree at once.

        A cost can be zero, which means ``Mode`` already removed the path and a
        projection naming it would be inert, or negative, which means dropping it
        splits a shared ``$def`` and makes the tool *larger*. Both are real
        answers rather than measurement noise, and both are worth having before
        the projection ships; :func:`~charter.derive.path_costs` has the numbers.
        """
        from charter.derive import PathCost, path_costs, schema_paths

        pruned = self._prune
        # Asked of the level wanted, not filtered out of the whole schema. The
        # difference is not a micro-optimisation: `search_issues_full` has 2,271,553
        # paths, and the eight this returns for `under="variables"` used to cost
        # ten seconds of building the other 2,271,545 and throwing them away.
        absolute = [
            p
            for p in schema_paths(self.args_schema, under=under, depth=depth)
            if p not in pruned and not any(p.startswith(f"{q}.") for q in pruned)
        ]
        live = [p[len(under) + 1 :] for p in absolute] if under else absolute

        if not by_cost:
            return live

        costs = path_costs(self.args_schema, absolute, mode=self.modes, prune=pruned)
        priced = [PathCost(rel, costs[full]) for rel, full in zip(live, absolute, strict=True)]
        return sorted(priced, key=lambda pc: -pc.tokens)

    def derived(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        keep: Optional[Iterable[Any]] = None,
        drop: Optional[Iterable[Any]] = None,
        pin: Optional[Dict[str, Any]] = None,
        action_label: Optional[str] = None,
    ) -> Tool:
        """This tool, narrowed — a projection of the same contract.

        The tool underneath is unchanged: same URL, same credentials, same
        validators, same ``extra="forbid"``. What narrows is the view the model
        is given, which is what makes the restriction mechanical rather than
        advisory — an argument outside the projection fails validation before a
        request is built.

        One edit, two effects: what the tool can do, and how much of the context
        window it occupies. A schema is in the prompt on every turn before the
        model has read the task, so the second is not a side benefit of the
        first — on a schema that refers back to itself it decides whether the
        tool is callable at all.

        ``keep`` selects within the sibling group it names. Keeping three members
        of the Docs ``Request`` union drops the other thirty and leaves
        ``document_id`` alone::

            edit_text = gdocs.documents_batch_update.derived(
                name="documents_edit_text",
                keep={"insert_text", "delete_content_range", "replace_all_text"},
            )

        ``drop`` removes a path outright. ``pin`` removes it from the view the
        model fills in and keeps it in the one the runtime executes, so the field
        is neither visible to the model nor reachable by it, and its value is
        indistinguishable on the wire from one passed by hand::

            search_docs = gdrive.files_list.derived(
                name="search_documents",
                pin={"q": "mimeType='application/vnd.google-apps.document'"},
            )

        Selectors are dotted paths, unambiguous field names, or the model class a
        field is annotated with; :meth:`paths` lists them. Projections compose —
        deriving from a projection narrows what is left.

        Nothing here is a new capability: a projection can only ever remove. That
        is the property that makes it safe to hand to whoever owns the deployment
        rather than the pack.

        Raises:
            DeclarationError: a selector names nothing, names several things,
                would drop a field the API requires, or pins a field ``Mode``
                keeps out of the view the runtime executes, where the value
                would be rejected on every call.
        """
        from charter.derive import check_pin_routing, plan_projection

        prune, pins = plan_projection(self.args_schema, keep=keep, drop=drop, pin=pin)
        check_pin_routing(self.args_schema, pins)

        return self._copy(
            name=name,
            description=description if description is not None else self.description,
            action_label=action_label or self.action_label,
            session_mode=self.session_mode,
            prune=self._prune | prune,
            pins={**self._pins, **pins},
        )

    def with_mode(self, mode: Optional[str]) -> Tool:
        """This tool, resolved at a deployment's :class:`~charter.Mode`.

        The same tool under one more label: same name, same URL, same
        credentials, same projections, and a view built by filtering the same
        declarations against ``mode`` **as well as** the one the tool was
        declared with. Passing a label that changes nothing returns the tool
        itself, so the views it has already built are reused rather than
        duplicated.

        This is the deployer's end of a lever the pack author declared. A pack
        that marks a field ``Mode("pro")`` has written down which surface it
        belongs to; a deployer holding that pack decides which surface this
        conversation is::

            pro = [t.with_mode("pro") for t in reports.TOOLS]

        Usually reached through :class:`~charter.ToolSession`, which takes a
        ``mode`` and does this to every tool it is given.

        **It adds a label, it does not replace one.** The two ends of ``Mode``
        answer different questions. The author's ``mode=`` says which *operation*
        this tool is — ``create`` replaces and ``update`` merges — and that is
        not a deployment decision. A deployment's label says which *surface* this
        conversation is. Replacing the first with the second made a session mode
        silently delete the operation: at ``"pro"``, ``forms_create`` stopped
        being a create, and which fields it lost depended on whether its author
        happened to use ``Mode`` for operations — which is not something a
        deployer can be asked to predict, pack by pack. Both are in force at
        once, so a label a deployment passes only ever *adds* the fields carrying
        it, whatever the pack did. :attr:`modes` is the resolved pair.

        ``with_mode(None)`` clears a deployment's label and leaves the author's,
        which is the tool as the pack ships it.

        **Not a projection.** :meth:`derived` can only ever remove, which is what
        makes it safe to hand to whoever owns the deployment. This adds, so
        relative to the tool it came from it widens: ``with_mode("max")`` offers
        the fields labelled ``max`` on top of what was already there. What it
        cannot do at any label is reach a field the author marked
        ``Mode("response_only")`` or ``Mode("disabled")``, because those are
        refused without consulting the mode at all. The author's floor holds, and
        now so does the author's partition.

        Raises:
            DeclarationError: if ``mode`` is not a label — an empty string is
                refused rather than read as ``None``, because ``None`` is the
                widest view and not the narrowest; if the resolved labels hide a
                field this tool pins, since the pinned value would then have
                nowhere to go; or if they hide a field the API requires, since
                the request would go out without it. All three would return a
                tool that cannot work, so none of them returns a tool.
        """
        # Before the shortcut below, not after: an empty label changes nothing
        # in force, so it would take that early return and never reach the check
        # in `Tool.__init__` — which is how a refusal turns into a silent no-op.
        _check_mode(mode, f"on tool {self.name!r}")

        if mode == self.session_mode:
            return self

        # Only that one test, and deliberately not "the labels in force would be
        # the same anyway". Asking for the label a tool was *declared* with does
        # produce an identical view, so returning `self` would save a build — and
        # would leave `session_mode` unset on those tools and set on the ones
        # beside them, so `egress_map` would report one deployment two ways
        # depending on which labels a pack happened to use internally. An audit
        # artifact must not vary with a coincidence, and the saving is three
        # schema builds on the widest pack that has any.

        return self._copy(
            name=self.name,
            description=self.description,
            action_label=self.action_label,
            session_mode=mode,
            prune=self._prune,
            pins=self._pins,
        )

    def _copy(
        self,
        *,
        name: str,
        description: str,
        action_label: Optional[str],
        session_mode: Optional[str],
        prune: frozenset,
        pins: Dict[str, Any],
    ) -> Tool:
        """This tool again, with the six things a variant is allowed to change.

        ``mode`` is not among them. It is the author's statement of which
        operation this tool is, and a variant of a create is still a create — a
        deployment's label lands on ``session_mode`` and both stay in force.

        One copy path, shared by :meth:`derived` and :meth:`with_mode`, because
        the failure mode of two is a constructor argument added to one of them.
        A projection that quietly lost the pack's response handler would return a
        different shape from the tool it narrowed, and that has happened.
        """
        return Tool(
            name=name,
            description=description,
            method=self.method,
            url_template=self.url_template,
            args_schema=self.args_schema,
            base_url=self.base_url,
            action_label=action_label,
            body_case=self.body_case,
            query_case=self.query_case,
            path_case=self.path_case,
            timeout=self.timeout,
            mode=self.mode,
            session_mode=session_mode,
            pack=self.pack,
            provider=self.provider,
            scopes=self.scopes,
            quota_cost=self.quota_cost,
            quota_doc_url=self.quota_doc_url,
            api_key_headers=self.api_key_headers,
            credential_provider=self.credential_provider,
            build_request=self._build_request,
            response_handler=self._response_handler,
            envelope=self.envelope,
            pagination=self.pagination,
            body_format=self.body_format,
            query_format=self.query_format,
            static_query=self.static_query,
            static_headers=self.static_headers,
            static_body=self.static_body,
            on_call=self.on_call,
            expiry_leeway_seconds=self.expiry_leeway_seconds,
            credential_statuses=self.credential_statuses,
            follow_redirects=self.follow_redirects,
            prune=prune,
            pins=pins,
            # A variant reads the same type graph as the tool it came from, so
            # it reads the same store. Only subtrees no prune path reaches are
            # shared, which is exactly the set an extra prune cannot change -
            # the condition `path_costs` already relies on to price a level.
            # Dropped here, every projection rebuilt the graph alone: Linear
            # ships 17 of them, and the pack's own curated list tools are all
            # projections, so the tools most likely to be exposed were the ones
            # paying full price. A mode variant needs it for the same reason one
            # step out: the store keys on the mode, so a whole session's worth of
            # tools at one mode build their shared models once between them
            # rather than once each.
            llm_cache=self._llm_cache,
        )

    def to_json_schema(self) -> Dict[str, Any]:
        """This tool as an OpenAI-style function definition.

        Generated once and copied out. ``model_json_schema`` is not cheap on a
        schema with a deep ``$defs`` graph — 40ms per tool across Linear, whose
        filters reach themselves — and :func:`~charter.adapters.openai.to_openai_tools`
        is documented to run *inside* the turn loop, so the generation would
        otherwise be paid again every turn.

        The copy is what keeps that safe. Adapters hand ``parameters`` straight
        out by reference, and tightening a returned schema — dropping a property,
        trimming ``required``, adding a vendor key — is an ordinary thing to do
        with one; against a shared dict it would edit the tool itself, for every
        later call and every other caller. Copying costs about 4% of generating.
        """
        cached = self._json_schema
        if cached is None:
            # Under the same guard as the view, for the same reason: this runs
            # inside the turn loop, so on a threaded host several turns reach a
            # cold tool at once and would each pay the 40ms generation.
            with self._schema_lock:
                cached = self._json_schema
                if cached is None:
                    cached = {
                        "name": self.name,
                        "description": self.description,
                        "parameters": llm_json_schema(self._llm_schema),
                    }
                    self._json_schema = cached
        return copy.deepcopy(cached)

    def to_json_summary(self) -> Dict[str, Any]:
        """This tool's capability, without its parameters.

        The counterpart to :meth:`to_json_schema` for progressive disclosure. An
        agent needs every tool's *existence* to plan and only the parameters of
        the tools it decides to call, and the two cost wildly different amounts:
        across the packs shipped here the full schemas come to about 71,000
        tokens and these summaries to about 3,300.

        The description is kept whole. Reducing it to its first sentence saves
        around 1,500 tokens of that 71,000 and throws away the sentences a pack
        author wrote to prevent a wrong call — "only the title is honoured",
        "order the requests back-to-front" — which is the wrong trade at any
        ratio.
        """
        return {"name": self.name, "description": self.description}

    # -----------------------------------------------------
    # Execution
    # -----------------------------------------------------

    async def ainvoke(
        self,
        args: Optional[Dict[str, Any]] = None,
        /,
        *,
        headers: Optional[Mapping[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs: Any,
    ) -> Any:
        """Validate the arguments, build the request, send it, return the result.

        Accepts a positional dict, keyword arguments, or both::

            await tool.ainvoke({"city": "Tokyo", "units": "metric"})
            await tool.ainvoke(city="Tokyo", units="metric")
            await tool.ainvoke({"city": "Tokyo"}, units="metric")

        Pass ``client`` to reuse an ``httpx.AsyncClient`` across calls.

        ``headers`` carries values the *host application* decides for this one
        call — an ``Idempotency-Key``, a ``Stripe-Account`` naming which connected
        account to act as, a correlation id. It is keyword-only and structurally
        separate from ``args``, so a model filling in tool arguments can never
        set a header.

        Charter does not generate these values, and that is deliberate: an
        idempotency key minted fresh on every call is worse than none, because
        the point is that a retry sends the *same* key. Charter does not own retries,
        so it does not own the key — this is a channel, not a feature.

            key = str(uuid4())            # yours, and stable across your retries
            await tool.ainvoke(args, headers={"Idempotency-Key": key})

        (Sharp edge: like ``client``, this shadows a schema field literally named
        ``headers``. Pass such a field in the positional dict.)

        Every call is measured, including the ones that fail: see ``on_call`` and
        :mod:`charter.observability`.

        Raises:
            ToolValidationError: the arguments do not satisfy the schema. The
                message is written to be handed back to the model verbatim.
            CredentialError: credentials missing, expired, or rejected (401 by
                default — see ``credential_statuses``).
            APIError: any other non-success response.
            TransformError: a ``Format`` transform failed.
        """
        resolved = {**(args or {}), **kwargs}

        # Validation runs here, before the executor, so a call the model got
        # wrong never reaches the network. That makes this — not the executor —
        # the only place a record can be minted that counts those calls.
        probe = CallProbe(observed=self._observed())
        started = perf_counter()
        result: Any = None
        error: Optional[BaseException] = None
        try:
            if not self._views_ready:
                # Derived on first use, which on a recursive schema is seconds
                # of pure CPU. Inline, that holds the event loop for all of it:
                # a cold Linear tool measured 1,634ms without a tick, and every
                # call already in flight on that loop waited it out. `to_thread`
                # copies the context, so `collecting` still sees what happens
                # inside. `Tool.prepare()` is how a host stops paying this
                # inside a request at all.
                build_started = perf_counter()
                try:
                    await asyncio.to_thread(self._build_views)
                finally:
                    # In a `finally` for the same reason as `validate_ms` below:
                    # a build that spent four seconds and then raised spent them.
                    probe.schema_ms = (perf_counter() - build_started) * 1000

            # Timed from here, so `validate_ms` measures validating this call
            # and not the one-off build above it. Charging the build to
            # validation put a 1,630ms outlier in the field a host watches to
            # find out whether the model is sending malformed arguments.
            validate_started = perf_counter()
            try:
                tool_input = validate_input(self._llm_schema, resolved, tool_name=self.name)
                if self._pins:
                    # Re-validated with the pins merged in, which is also what
                    # makes a `ConflictsWith` naming a pinned field still fire.
                    tool_input = validate_input(
                        self._exec_schema,
                        {**tool_input.model_dump(exclude_none=True), **self._pins},
                        tool_name=self.name,
                    )
            finally:
                probe.validate_ms = (perf_counter() - validate_started) * 1000

            result = await self._executor.execute(
                tool_input,
                tool_name=self.name,
                headers=headers,
                client=client,
                probe=probe,
            )
            return result
        except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised
            error = exc
            raise
        finally:
            self._report(
                probe=probe,
                args=resolved,
                result=result,
                error=error,
                total_ms=(perf_counter() - started) * 1000,
            )

    def invoke(
        self,
        args: Optional[Dict[str, Any]] = None,
        /,
        *,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Synchronous :meth:`ainvoke`.

        Runs the coroutine with ``asyncio.run``, so it cannot be called from a
        thread that already has a running event loop — inside async code, await
        :meth:`ainvoke` instead.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                f"Tool.invoke() cannot be called while an event loop is running "
                f"(tool {self.name!r}). Use 'await tool.ainvoke(...)' instead."
            )
        return asyncio.run(self.ainvoke(args, headers=headers, **kwargs))

    # -----------------------------------------------------
    # Measurement
    # -----------------------------------------------------

    def _observed(self) -> bool:
        """Whether anything is listening closely enough to justify sizing payloads.

        Timings cost a few clock reads and are always taken. Sizes cost a
        serialisation of the arguments and of the result, so they are only paid
        for when a sink or an INFO log handler will actually read them.
        """
        return (
            self.on_call is not None or bool(current_sinks()) or logger.isEnabledFor(logging.INFO)
        )

    def _sinks(self) -> tuple:
        """The tool's own sink and any :func:`~charter.collecting` is holding.

        Deduplicated by identity: passing a pack's own ``on_call`` to
        ``collecting`` as well should record a call once, not twice.
        """
        sinks = list(current_sinks())
        if self.on_call is not None and not any(s is self.on_call for s in sinks):
            sinks.insert(0, self.on_call)
        return tuple(sinks)

    def _report(
        self,
        *,
        probe: CallProbe,
        args: Dict[str, Any],
        result: Any,
        error: Optional[BaseException],
        total_ms: float,
    ) -> None:
        """Emit the record. Never raises: a call must not fail on the way out."""
        try:
            call = ToolCall.from_probe(
                tool=self.name,
                provider=self.provider,
                method=self.method,
                url_template=self.url_template,
                probe=probe,
                error=error,
                total_ms=total_ms,
                args_bytes=_measure(args) if probe.observed else None,
                context_bytes=(_measure(result) if probe.observed and error is None else None),
            )

            if logger.isEnabledFor(logging.INFO):
                # The rendered line is the message so a plain handler prints
                # something readable; the record rides along for a structured one.
                logger.info(format_call_line(call), extra={"charter_call": call})

            for sink in self._sinks():
                try:
                    sink(call)
                except Exception:
                    # One broken sink must not silence the others, and must not
                    # fail the call it was only supposed to describe.
                    logger.debug("charter call sink failed for %s", self.name, exc_info=True)
        except Exception:  # pragma: no cover - defensive
            # A broken sink or an unserialisable payload is a reporting problem.
            # It must never turn a working tool call into a failing one.
            logger.debug("charter could not record a call for %s", self.name, exc_info=True)

    def __getstate__(self) -> Dict[str, Any]:
        """Everything but the lock, which no copy of a tool should share.

        A ``threading.RLock`` cannot be copied or pickled, so holding one made
        ``copy.deepcopy(tool)`` — which worked before the view was derived
        lazily — raise ``cannot pickle '_thread.RLock' object``. A copy is a
        separate object that guards its own build, so the lock is dropped here
        and remade in :meth:`__setstate__` rather than carried across.
        """
        state = self.__dict__.copy()
        state.pop("_schema_lock", None)
        return state

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self.__dict__.update(state)
        self._schema_lock = threading.RLock()

    def __repr__(self) -> str:
        return (
            f"Tool(name={self.name!r}, method={self.method!r}, url_template={self.url_template!r})"
        )
