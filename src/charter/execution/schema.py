"""
The LLM's view of a schema.

One schema describes the API exactly; the model should not see all of it. This
module derives the LLM-facing view from the wire schema:

- fields marked ``Mode("response_only")`` / ``Mode("disabled")`` are dropped,
  and modes cascade into nested models;
- fields named in ``prune`` are dropped by dotted path, which is how a deployer
  narrows a tool it did not declare (see :mod:`charter.derive`);
- fields marked ``Format(...)`` are retyped to the transform's *semantic* type,
  so the model fills in an ``EmailContent``, not a base64 MIME blob;
- fields marked ``Gloss(...)`` gain that sentence at the end of their description,
  which is what lets the wire schema's description stay the API's own words;
- every generated model accepts snake_case, camelCase and PascalCase keys
  interchangeably, and repairs a nested object handed over as a JSON string.

HTTP markers are preserved on the generated model, so the result is still a
valid input to :func:`charter.execution.http.call_api`.
"""

from __future__ import annotations

import contextlib
import copy
import json
import sys
import threading
from typing import (
    Annotated,
    Any,
    ClassVar,
    Dict,
    ForwardRef,
    FrozenSet,
    List,
    Optional,
    Type,
    Union,
    cast,
    get_args,
    get_origin,
)

from pydantic import (
    AliasChoices,
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.alias_generators import to_camel, to_pascal, to_snake
from pydantic_core import PydanticUndefined

from charter.transforms import get_transform
from charter.types.markers import ConflictsWith, Format, Gloss, Mode, WireName

__all__ = [
    "LLMBase",
    "SchemaStore",
    "create_llm_schema",
    "partial_of",
    "should_include_field",
]


# Config keys carried from the wire schema onto its LLM view. Only the ones that
# decide whether a wrong input is *rejected* — never the alias machinery, which
# LLMBase owns and which the LLM view depends on.
_CARRIED_CONFIG_KEYS = ("extra", "strict")


def _api_name(field_name: str, field_info: Any) -> str:
    """What the API calls a field, for a message a model has to act on.

    A :class:`~charter.types.markers.WireName` is the API's own spelling and
    absolute, so it wins. Otherwise the published name is used, which is what the
    model was given and therefore what it recognises — the wire spelling depends
    on the factory's casing, which is not knowable here.
    """
    for marker in getattr(field_info, "metadata", []):
        if isinstance(marker, WireName):
            return marker.name
    return to_camel(to_snake(field_name))


def _gloss_text(field_info: Any) -> str:
    """Every :class:`~charter.types.markers.Gloss` on one field, in order.

    Joined rather than first-wins: two glosses on a field is a pack author
    saying two things, and dropping one silently is the failure a reader cannot
    see.
    """
    return " ".join(
        marker.text
        for marker in getattr(field_info, "metadata", [])
        if isinstance(marker, Gloss)
    )


def _conflict_validator(fields: Dict[str, Any]) -> Optional[Any]:
    """Build the check that :class:`~charter.types.markers.ConflictsWith` declares.

    Synthesised rather than written by the pack author, so the rule has exactly
    one home: the field it is about. A list of field names beside a hand-written
    validator is a second place to keep in step, and nothing notices when it
    stops matching.

    Returns ``None`` when no field declares a conflict, so a schema without one
    gains no validator and no cost.
    """
    rules: List[tuple] = []
    for name, (_, info) in fields.items():
        for marker in getattr(info, "metadata", []):
            if isinstance(marker, ConflictsWith):
                rules.append((name, marker.fields, marker.reason))
    if not rules:
        return None

    names = {n: _api_name(n, info) for n, (_, info) in fields.items()}

    def _check(self: Any) -> Any:
        # Grouped by what was excluded, and reported in one go. Raising on the
        # first conflict makes a model fix one parameter, retry, and meet the
        # next — the round trips are the cost the local check exists to avoid.
        grouped: Dict[str, tuple] = {}
        for field, excluded, reason in rules:
            if getattr(self, field, None) is None:
                continue
            for other in excluded:
                if getattr(self, other, None) is None:
                    continue
                offenders, _ = grouped.setdefault(other, (set(), reason))
                offenders.add(names.get(field, field))
        if not grouped:
            return self
        parts = []
        for other, (offenders, reason) in grouped.items():
            clause = (
                f"{', '.join(sorted(offenders))} cannot be combined with "
                f"{names.get(other, other)}."
            )
            parts.append(f"{clause} {reason}".strip())
        raise ValueError(" ".join(parts))

    return model_validator(mode="after")(_check)


def _spellings(name: str) -> AliasChoices:
    """Every spelling of one field name that validation accepts.

    camelCase, PascalCase and snake_case, in that order — the first is what
    names the field in the generated JSON schema, so the advertised spelling
    does not change. Models mix conventions freely inside nested objects, and a
    pack author may have written the field in either convention (Stripe's
    schemas are snake_case, Gmail's are camelCase), so both directions have to
    resolve.

    Listing them explicitly is what makes ``extra="forbid"`` safe: with extras
    refused, the accepted spellings are exactly the declared aliases, and a
    spelling that is merely "also allowed" by ``populate_by_name`` is not one.
    Deduplicated because for a single-word field they collapse to one string,
    and pydantic rejects a repeated choice.
    """
    # Normalise to snake first: pydantic's to_pascal expects snake input, so
    # to_pascal("userId") is "Userid" rather than "UserId" — which would leave a
    # camelCase-authored field without a working PascalCase spelling.
    snake = to_snake(name)
    seen: List[str] = []
    for spelling in (to_camel(snake), to_pascal(snake), snake, name):
        if spelling not in seen:
            seen.append(spelling)
    return AliasChoices(*seen)


class LLMBase(BaseModel):
    """Base class for every generated ``_LLM`` schema.

    ``charter_declared_name`` carries the name of the schema the author actually
    wrote. Errors raised while a request is assembled hold a generated instance,
    and reporting ``SendEmail_LLM`` sends someone looking for a class that
    exists nowhere in their code.

    Two behaviours are inherited by all of them:

    1. ``model_config`` accepts camelCase aliases (``dateTime``), PascalCase
       aliases (``DateTime``), AND snake_case field names (``date_time``)
       interchangeably. LLMs freely mix conventions inside nested objects;
       without this, non-snake keys are silently dropped by Pydantic, leaving
       fields ``None`` and causing a confusing 400 from the API rather than a
       local validation error.

    2. ``model_validator(mode="before")`` coerces JSON-string values into
       dicts/lists for ``BaseModel``/``list``/``dict``-typed fields before field
       validation, which heads off the common mistake of passing a body as a
       JSON string instead of a parsed object. When the string *looks* like JSON
       but will not parse, it raises a syntax-specific message: told only that
       the type is wrong, a model retries with different content and the same
       broken syntax, forever.
    """

    # ClassVar, so pydantic treats it as class data rather than a field the
    # model would then demand on every call.
    charter_declared_name: ClassVar[str] = ""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            # The field's own name is listed explicitly rather than left to
            # populate_by_name. With extra="forbid" the accepted spellings are
            # exactly the declared aliases, so a name that is merely "also
            # allowed" is not enough — `user_id` has to *be* an alias, or the
            # snake_case spelling this docstring promises becomes an error.
            # It goes *last*: the first choice is the one that names the field
            # in the generated JSON schema, and that stays camelCase.
            validation_alias=lambda name: _spellings(name),
        ),
        populate_by_name=True,
        # 3. An argument the schema does not declare is refused rather than
        #    dropped. Pydantic's default is to ignore extras, and for a
        #    tool-calling boundary that is the worst available behaviour: a
        #    model that invents `created` on a list endpoint, or types `emails`
        #    for `email`, gets HTTP 200 and a page of *unfiltered* results with
        #    nothing anywhere saying the filter was discarded. That is not a
        #    failure the agent can see, it is a wrong answer it will trust.
        #    Forbidding extras turns it into a ToolValidationError the model can
        #    read and correct, and makes `additionalProperties: false` appear in
        #    the JSON schema so it mostly does not happen in the first place.
        extra="forbid",
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_string_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        for field_name, field_info in cls.model_fields.items():
            if field_name not in values:
                continue
            value = values[field_name]
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if not (stripped.startswith("{") or stripped.startswith("[")):
                continue
            # Unwrap Optional[X] -> X
            field_type = field_info.annotation
            if get_origin(field_type) is Union:
                args = get_args(field_type)
                non_none = [a for a in args if a is not type(None)]
                if non_none:
                    field_type = non_none[0]
            origin = get_origin(field_type)
            is_model = isinstance(field_type, type) and issubclass(field_type, BaseModel)
            if origin in (list, dict) or field_type in (list, dict) or is_model:
                try:
                    values[field_name] = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"'{field_name}' looks like JSON but is malformed — "
                        f"fix the syntax and retry. Detail: {exc}"
                    ) from exc
        return values


def should_include_field(
    field_info: Any, mode: Optional[str], parent_modes: Optional[set] = None
) -> bool:
    """Whether a field belongs in the LLM view, given the mode and any cascade.

    Special modes, always enforced regardless of the tool's mode:

    - ``disabled``: always exclude
    - ``response_only``: always exclude (output-only fields)
    - ``request_only``: always include (input-only fields)
    """
    # Check for Mode marker on this field
    mode_marker = None
    for metadata in field_info.metadata:
        if isinstance(metadata, Mode):
            mode_marker = metadata
            break

    # If field has explicit mode marker, use it
    if mode_marker:
        # Always exclude: disabled or response_only
        if "disabled" in mode_marker.modes or "response_only" in mode_marker.modes:
            return False

        # Always include: request_only
        if "request_only" in mode_marker.modes:
            return True

        # Otherwise: only keep if mode is specified and matches
        if mode and mode_marker.modes:
            return mode in mode_marker.modes

    # If no explicit mode marker, check parent modes (cascading)
    elif parent_modes:
        # Field inherits parent modes
        if "disabled" in parent_modes or "response_only" in parent_modes:
            return False
        if "request_only" in parent_modes:
            return True
        if mode:
            return mode in parent_modes
        # If no mode specified, include if parent has any non-special modes
        return bool(parent_modes - {"response_only", "disabled", "request_only"})

    # No mode restrictions - include by default
    return True


def _prune_reaches(prune: Optional[FrozenSet[str]], path: str) -> bool:
    """Whether any prune path still lands inside the subtree rooted at ``path``.

    A list of models is addressed without its brackets — ``body.requests`` is a
    ``List[Request]`` and its members are ``body.requests.insert_text`` — because
    the path is a name a person types, and the index is never the thing being
    narrowed.
    """
    if not prune:
        return False
    prefix = f"{path}." if path else ""
    return any(p.startswith(prefix) for p in prune)


def _get_field_modes(field_info: Any) -> set:
    """Extract the modes from a field's ``Mode`` marker."""
    for metadata in field_info.metadata:
        if isinstance(metadata, Mode):
            return metadata.modes
    return set()


def _unbind(func: Any) -> Any:
    """A bound classmethod -> the plain function underneath it.

    Pydantic stores a ``@classmethod`` validator already bound to the class that
    declared it. Re-registering the bound object hands Pydantic a signature with
    ``cls`` already filled in, which it then mis-reads; the underlying function
    is what the decorator wants.
    """
    return getattr(func, "__func__", func)


def _pydantic_decorators(schema: Type[BaseModel]) -> Any:
    """The one private Pydantic attribute Charter reads, reached from one place.

    ``__pydantic_decorators__`` is how a schema's validators are recovered so
    ``_carry_validators`` can put them back on the generated LLM view. Pydantic
    exposes no public equivalent, and this is load-bearing: the alternative to
    reading it is every pack's cross-field rules silently ceasing to apply to
    the input that needs checking.

    It is reached through this function so that a Pydantic release which moves
    or renames it fails here, loudly and once, naming the version — rather than
    returning nothing and leaving ~20 ``oneof`` constraints quietly unenforced.
    """
    decorators = getattr(schema, "__pydantic_decorators__", None)
    if decorators is None:
        from pydantic import VERSION

        raise RuntimeError(
            f"pydantic {VERSION} does not expose __pydantic_decorators__ on "
            f"{schema.__name__}. Charter reads it to carry validators onto the "
            "LLM view; without it every cross-field rule would be dropped "
            "silently. Pin pydantic<3 and open an issue."
        )
    return decorators


def _carry_validators(
    original_schema: Type[BaseModel], kept_fields: set
) -> dict:
    """Re-register ``original_schema``'s validators and serializers for its LLM view.

    ``create_model`` builds a genuinely new class, and neither validators nor
    serializers are fields — so without this they are silently dropped, and
    every cross-field rule a pack author wrote (Google Docs alone declares ~20
    ``oneof`` constraints) stops being enforced on exactly the input that needs
    checking: the model's.

    Field validators whose target fields were filtered out by ``Mode`` are
    skipped rather than carried, since Pydantic rejects a validator that names a
    field the model does not have.

    A **model serializer** is carried for the same reason and costs more when it
    is not: the LLM view is the instance the runtime dumps, so a serializer left
    behind changes the bytes on the wire rather than a check. That is how a
    field Python will not let you name — Notion's compound filter is
    ``{"and": [...]}``, and ``and`` is a keyword — reaches the API under its own
    spelling. ``WireName`` cannot do it, since key conversion carries per-field
    markers at the top level of a body only, and this one is nested inside a
    filter. See ``test_a_nested_serializer_reaches_the_wire``.
    """
    carried: dict = {}
    decorators = _pydantic_decorators(original_schema)

    for name, decorator in decorators.model_serializers.items():
        carried[name] = model_serializer(mode=decorator.info.mode)(
            _unbind(decorator.func)
        )

    for name, decorator in decorators.model_validators.items():
        func = _unbind(decorator.func)
        if decorator.info.mode == "after":
            # An after-validator takes ``self``; the LLM view carries the same
            # field names, so it is duck-compatible with the original.
            carried[name] = model_validator(mode="after")(func)
        else:
            carried[name] = model_validator(mode=decorator.info.mode)(classmethod(func))

    for name, decorator in decorators.field_validators.items():
        targets = tuple(f for f in decorator.info.fields if f in kept_fields)
        if not targets:
            continue
        # cast: info.mode is the same literal set field_validator accepts, but
        # Pydantic types the two independently.
        mode = cast(Any, decorator.info.mode)
        carried[name] = field_validator(*targets, mode=mode)(
            classmethod(_unbind(decorator.func))
        )

    return carried


def _llm_annotation(nested: Any, optional: bool) -> Any:
    """Turn a nested LLM schema (or a parked forward-ref name) into a field type.

    A cycle during the walk parks the generated class's name as a string. Making
    it a :class:`ForwardRef` here is what the list branch already does one level
    down, so both paths hand ``create_model`` the same kind of annotation and
    :func:`_rebuild_generated` has one kind of thing to resolve. ``Optional``
    would convert the string on its own; a required field would not.
    """
    annotation: Any = ForwardRef(nested) if isinstance(nested, str) else nested
    if optional:
        return Optional[annotation]
    return annotation


def _rebuild_generated(seen: dict) -> None:
    """Resolve the forward refs between generated ``_LLM`` models.

    These classes are built by ``create_model`` and bound in no module, so a ref
    to one resolves only where pydantic already has the class in scope. Pydantic
    keeps the classes it is *currently building* in scope, which is enough for a
    cycle that closes inside one model's own build — ``A`` optional-``B``,
    ``B`` optional-``A`` leaves ``A_LLM`` complete — and it is why a two-model
    test looks like it passes. It does not reach the model one level in:
    ``B_LLM`` is left undefined, and a graph whose refs close outside any one
    build leaves the root undefined too. Linear's collection filters are that
    graph, and 17 of its 128 tools could not emit a JSON schema at all.

    So the root call rebuilds every generated model against a namespace of all
    of them. Nothing else here needs them individually complete, but validating
    through the root does, which is why rebuilding the root alone is not enough.
    """
    namespace = {
        model.__name__: model
        for model in seen.values()
        if isinstance(model, type) and issubclass(model, BaseModel)
    }
    for model in namespace.values():
        if getattr(model, "__pydantic_complete__", False):
            continue
        model.model_rebuild(_types_namespace=namespace)


class SchemaStore(dict):
    """A :func:`create_llm_schema` ``cache`` that several threads may share.

    A plain dict was enough while the only sharer was :func:`~charter.derive.path_costs`,
    which fills one and drops it inside a single call. A pack factory's store is
    the other thing entirely: it outlives the import that made it, every tool in
    the pack reads it, and since the view is derived on first use the readers are
    whichever threads reach those tools — which for a synchronous ``Tool.invoke``
    is a WSGI worker pool, or a sync agent on an executor.

    The lock is held across a whole root walk rather than around each read and
    write, because the hazard is not a torn entry. Two walks that interleave each
    build their own copy of a shared subtree and then read each other's, so the
    graph that comes out is spliced from two generations of the same models: on
    ``linear.custom_view_create`` that turned 80 definitions into 136 and a 193KB
    schema into 382KB, on some cold starts and not others. Fireworks refuses a
    Linear tool past a depth of 50 and the refusal takes every other tool in the
    request with it, so a schema that is twice the size on a process which
    happened to start busy is not a slow path — it is an outage that does not
    reproduce.

    Serialising the walks is also *faster*, which is the part worth stating
    plainly: 145 Linear tools first-touched by eight threads take 21.1-22.4s
    without the lock and 7.8-9.2s with it, because the second thread stops
    rebuilding what the first is already building and waits for the memo. Where
    waiting gains nothing — every thread wanting every tool — it is 3.7s either
    way, so there is no shape that pays for this.
    """

    __slots__ = ("lock", "verified")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.lock = threading.RLock()
        # Source models already checked resolvable, by the same owner and for the
        # same lifetime as the generated ones. Keyed by id and holding the class,
        # so the id cannot be recycled underneath the entry — the rule the store
        # itself follows. Sound to keep forever because
        # `__pydantic_complete__` only ever goes False to True: a model that
        # resolved once cannot stop.
        self.verified: Dict[int, Any] = {}

    def __deepcopy__(self, memo: dict) -> SchemaStore:
        """Shared, not copied.

        The store is a memo from a source class to the view it generates, which
        is a fact about those classes rather than state belonging to whoever
        holds it — a factory already shares one across every tool it builds. And
        a lock cannot be deep-copied at all, so copying is what would break
        ``copy.deepcopy(tool)``.
        """
        return self


# One lock for every caller-supplied plain dict, which is coarse on purpose.
# A `dict` cannot carry a lock and cannot be weak-referenced, so there is nowhere
# to keep a per-store one that does not outlive the store or collide after an id
# is recycled. Charter's own stores are `SchemaStore`s and never reach this;
# what does is a dict handed in by a caller, where correctness matters and
# contention does not.
_SHARED_DICT_LOCK = threading.RLock()


def _store_guard(cache: Optional[dict]) -> Any:
    """The lock protecting ``cache`` for the duration of one root walk."""
    if cache is None:
        return contextlib.nullcontext()
    lock = getattr(cache, "lock", None)
    return lock if lock is not None else _SHARED_DICT_LOCK


def create_llm_schema(
    original_schema: Type[BaseModel],
    mode: Optional[str] = None,
    parent_modes: Optional[set] = None,
    prune: Optional[FrozenSet[str]] = None,
    cache: Optional[dict] = None,
    _seen_types: Optional[dict] = None,
    _root_mode: Optional[str] = None,
    _path: str = "",
    _pending: Optional[dict] = None,
) -> Type[BaseModel]:
    """Build the LLM-facing view of ``original_schema``.

    See :func:`_create_llm_schema` for what the walk does. This wrapper exists
    only to hold ``cache``'s lock around a root walk, so that two threads sharing
    a store take turns rather than interleaving two builds of one type graph.
    Nested calls go straight to the walk: they are already inside the guard, on
    the thread that took it.
    """
    if _seen_types is not None or cache is None:
        return _create_llm_schema(
            original_schema,
            mode=mode,
            parent_modes=parent_modes,
            prune=prune,
            cache=cache,
            _seen_types=_seen_types,
            _root_mode=_root_mode,
            _path=_path,
            _pending=_pending,
        )
    with _store_guard(cache):
        return _create_llm_schema(
            original_schema,
            mode=mode,
            parent_modes=parent_modes,
            prune=prune,
            cache=cache,
            _seen_types=_seen_types,
            _root_mode=_root_mode,
            _path=_path,
            _pending=_pending,
        )


def _create_llm_schema(
    original_schema: Type[BaseModel],
    mode: Optional[str] = None,
    parent_modes: Optional[set] = None,
    prune: Optional[FrozenSet[str]] = None,
    cache: Optional[dict] = None,
    _seen_types: Optional[dict] = None,
    _root_mode: Optional[str] = None,
    _path: str = "",
    _pending: Optional[dict] = None,
) -> Type[BaseModel]:
    """Build the LLM-facing view of ``original_schema``.

    Walks the schema and:

    1. filters out fields based on ``Mode`` markers, cascading from the parent;
    2. finds fields with ``Format`` markers;
    3. replaces their types with the semantic type from the transform registry;
    4. appends each ``Gloss`` to the description the model reads;
    5. preserves all field metadata, including the HTTP markers.

    Args:
        original_schema: The schema matching the API documentation.
        mode: Optional mode to filter fields by (e.g. ``"create"``, ``"update"``).
        parent_modes: Modes inherited from a parent field (for cascading).
        prune: Dotted paths to drop, relative to the root — ``"body.requests.
            insert_table"``. Where ``Mode`` is the *author's* lever, declared on
            the field, this is the *deployer's*: the same filtering reached by
            path, for someone holding a tool they did not write.
        cache: A caller-owned store for the generated models a prune cannot
            reach, shared across several calls that differ only in ``prune``.
            Pricing a level with :func:`~charter.derive.path_costs` builds the
            same schema once per path, and on a schema whose types refer to each
            other almost all of it is the same every time: pruning
            ``variables.filter`` changes the models at ``""`` and ``variables``
            and leaves the other seventy-odd identical. Only entries whose
            ``prune_scope`` is None are eligible, which is exactly the condition
            that says no prune path reaches that subtree, so a shared model is
            the model this call would have built. Owned by the caller rather
            than held in module state: it lives as long as the caller wants it
            to, and nothing accumulates between unrelated calls. Written once,
            at the end of the root call: a caller may read the store from another
            thread, and until the walk has resolved its forward references the
            models in it cannot validate anything. A store several threads share
            should be a :class:`SchemaStore`, whose lock keeps two root walks
            from interleaving; a plain dict falls back to one process-wide lock.
        _seen_types: Internal — tracks visited types to handle cycles.
        _root_mode: Internal — the mode from the initial call, kept for nesting.
        _path: Internal — this model's dotted path from the root, for ``prune``.
        _pending: Internal — what this walk will publish into ``cache``, held
            back until the root has completed every model.
    """
    # Initialize seen types dict on first call (maps original type to LLM type)
    is_root = _seen_types is None
    if _seen_types is None:
        _seen_types = {}
        # Staged rather than published as it is built. A generated model is not
        # usable until `_rebuild_generated` has resolved its forward references,
        # which happens once, at the end of the root call — mid-walk, 49 of the
        # 78 models a Linear filter graph produces are still incomplete. A cache
        # the caller keeps outlives this call, so anything published early is
        # visible to whoever holds it: another thread reading the store between
        # those two points, or any later call if this one raises before the
        # rebuild. Either one hands back a model that cannot validate and is
        # memoised as if it could.
        _pending = {} if cache is not None else None

    # Preserve the root mode for all nested types
    if _root_mode is None:
        _root_mode = mode

    # Always use the root mode for nested types so every model in $defs gets the
    # same filtering applied.
    effective_mode = _root_mode

    # A pruned subtree cannot share a cached model with an unpruned one: `Location`
    # sits under nearly every Docs request, and pruning it in one must not reach
    # the others. The path only joins the key while a prune path can still reach
    # this subtree — past that depth the models are identical again, and keeping
    # the path in the key forever would stop a self-referential type terminating.
    prune_scope = _path if _prune_reaches(prune, _path) else None
    cache_key = (
        id(original_schema),
        effective_mode,
        tuple(sorted(parent_modes)) if parent_modes else None,
        prune_scope,
    )
    if cache_key in _seen_types:
        # Return the already-created LLM schema to avoid duplicates and handle cycles
        return _seen_types[cache_key]

    # A model no prune path reaches is the same model on every call, so a caller
    # pricing a level can hand the same one back instead of rebuilding it. It
    # still has to join `_seen_types`: `_rebuild_generated` resolves forward refs
    # against a namespace of everything the walk touched, and a model missing
    # from it is a ref that will not resolve.
    if prune_scope is None and cache is not None and cache_key in cache:
        _source, shared = cache[cache_key]
        _seen_types[cache_key] = shared
        return shared

    # For self-referential types we park a forward reference string here and
    # replace it with the real model once it exists.
    llm_model_name = f"{original_schema.__name__}_LLM"
    _seen_types[cache_key] = llm_model_name

    fields = {}

    for field_name, field_info in original_schema.model_fields.items():
        field_path = f"{_path}.{field_name}" if _path else field_name
        if prune and field_path in prune:
            continue
        if not should_include_field(field_info, effective_mode, parent_modes):
            continue

        # Get this field's modes for cascading to nested types
        field_modes = _get_field_modes(field_info)
        if not field_modes and parent_modes:
            # Inherit parent modes if field has no explicit modes
            field_modes = parent_modes

        format_marker = None
        for metadata in field_info.metadata:
            if isinstance(metadata, Format):
                format_marker = metadata
                break

        if format_marker:
            transform_spec = get_transform(format_marker.transform)

            if transform_spec and transform_spec.semantic_type is not BaseModel:
                # Replace the wire type with the concrete semantic type.
                # Skipped when semantic_type is the abstract BaseModel itself (the
                # catch-all for transforms like proto_json that accept many types);
                # there the original Pydantic type already handles LLM input
                # correctly (e.g. via Value.coerce_primitive), so it is preserved.
                is_optional = get_origin(field_info.annotation) is Union and type(
                    None
                ) in get_args(field_info.annotation)

                semantic_type = transform_spec.semantic_type
                if is_optional:
                    semantic_type = Optional[semantic_type]

                # Preserve ALL metadata including Path/Query/Body markers
                preserved_metadata = list(getattr(field_info, "metadata", []))

                default_value = field_info.default
                if default_value is PydanticUndefined:
                    default_value = ...  # Pydantic's required field marker

                annotated_semantic_type = Annotated[
                    (semantic_type, *preserved_metadata)
                ]

                fields[field_name] = (
                    annotated_semantic_type,
                    Field(
                        default=default_value,
                        description=transform_spec.llm_description
                        or field_info.description,
                        title=getattr(field_info, "title", None),
                        examples=getattr(field_info, "examples", None),
                    ),
                )
            else:
                # No transform found, or semantic_type is abstract BaseModel — keep original.
                fields[field_name] = (field_info.annotation, field_info)
        else:
            # No Format marker; check for a nested model that needs mode cascading.
            field_type = field_info.annotation

            is_optional = False
            if get_origin(field_type) is Union:
                args = get_args(field_type)
                if type(None) in args:
                    is_optional = True
                    field_type = next(arg for arg in args if arg is not type(None))

            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                nested_llm_schema = _create_llm_schema(
                    field_type,
                    mode=effective_mode,
                    parent_modes=field_modes,
                    prune=prune,
                    cache=cache,
                    _seen_types=_seen_types,
                    _root_mode=_root_mode,
                    _path=field_path,
                    _pending=_pending,
                )
                fields[field_name] = (
                    _llm_annotation(nested_llm_schema, is_optional),
                    field_info,
                )
            elif field_type is not None and (
                get_origin(field_type) is list
                or (hasattr(field_type, "__origin__") and field_type.__origin__ is list)
            ):
                list_args = get_args(field_type)
                if list_args:
                    list_item_type = list_args[0]
                    if isinstance(list_item_type, str):
                        # Forward reference — resolve it, or fall back to the original.
                        if list_item_type == original_schema.__name__:
                            nested_llm_schema = llm_model_name  # self-reference
                        else:
                            module = sys.modules[original_schema.__module__]
                            resolved_type = getattr(module, list_item_type, None)
                            if isinstance(resolved_type, type) and issubclass(
                                resolved_type, BaseModel
                            ):
                                nested_llm_schema = _create_llm_schema(
                                    resolved_type,
                                    mode=effective_mode,
                                    parent_modes=field_modes,
                                    prune=prune,
                                    cache=cache,
                                    _seen_types=_seen_types,
                                    _root_mode=_root_mode,
                                    _path=field_path,
                                    _pending=_pending,
                                )
                            else:
                                fields[field_name] = (field_info.annotation, field_info)
                                continue
                    elif isinstance(list_item_type, type) and issubclass(
                        list_item_type, BaseModel
                    ):
                        nested_llm_schema = _create_llm_schema(
                            list_item_type,
                            mode=effective_mode,
                            parent_modes=field_modes,
                            prune=prune,
                            cache=cache,
                            _seen_types=_seen_types,
                            _root_mode=_root_mode,
                            _path=field_path,
                            _pending=_pending,
                        )
                    else:
                        fields[field_name] = (field_info.annotation, field_info)
                        continue

                    if isinstance(nested_llm_schema, str):
                        list_type = List[ForwardRef(nested_llm_schema)]  # type: ignore[misc]
                    else:
                        list_type = List[nested_llm_schema]  # type: ignore[valid-type]
                    if is_optional:
                        list_type = Optional[list_type]
                    fields[field_name] = (list_type, field_info)
                else:
                    fields[field_name] = (field_info.annotation, field_info)
            elif field_type is not None and get_origin(field_type) is dict:
                # A model reached as a dict *value* is still a model, and its
                # Mode markers still apply. Without this branch the subtree is
                # copied across whole and `response_only` stops meaning
                # anything inside it — which is an egress hole rather than an
                # ergonomic one, since a withheld field is the pack's way of
                # keeping something out of a model's context. Notion's page
                # `properties` is the shape that found it: a map of column name
                # to value, where a third of the value types are computed by the
                # server and rejected on write.
                dict_args = get_args(field_type)
                value_type = dict_args[1] if len(dict_args) == 2 else None
                value_optional = False
                if value_type is not None and get_origin(value_type) is Union:
                    value_args = [a for a in get_args(value_type) if a is not type(None)]
                    if len(value_args) == 1:
                        value_optional = len(get_args(value_type)) > 1
                        value_type = value_args[0]
                if isinstance(value_type, type) and issubclass(value_type, BaseModel):
                    nested_llm_schema = _create_llm_schema(
                        value_type,
                        mode=effective_mode,
                        parent_modes=field_modes,
                        prune=prune,
                        cache=cache,
                        _seen_types=_seen_types,
                        _root_mode=_root_mode,
                        _path=field_path,
                        _pending=_pending,
                    )
                    # A cycle anywhere under the value type leaves a forward
                    # reference to a generated class, which resolves nowhere —
                    # those live in no module namespace. The protobuf
                    # `Struct`/`Value` pair reaches itself exactly this way,
                    # one level below the dict. Either symptom means the walk
                    # produced something that cannot stand on its own, so keep
                    # the author's annotation: that is what happened before this
                    # branch existed, and a self-referential type cannot differ
                    # from itself in its modes anyway.
                    if isinstance(nested_llm_schema, str) or not getattr(
                        nested_llm_schema, "__pydantic_complete__", True
                    ):
                        fields[field_name] = (field_info.annotation, field_info)
                        continue
                    value_annotation: Any = nested_llm_schema
                    if value_optional:
                        value_annotation = Optional[value_annotation]
                    dict_type: Any = Dict[dict_args[0], value_annotation]  # type: ignore[valid-type]
                    if is_optional:
                        dict_type = Optional[dict_type]
                    fields[field_name] = (dict_type, field_info)
                else:
                    fields[field_name] = (field_info.annotation, field_info)
            else:
                fields[field_name] = (field_info.annotation, field_info)

    # A WireName names the field for the model as well as for the wire.
    #
    # The description is the API's own text and refers to the field by the API's
    # own name, so publishing a different one asks the model to read `iCalUID`
    # everywhere and send `iCalUid`. The alias is set explicitly, which pydantic
    # gives priority over the generator on LLMBase, and the API's name goes first
    # so it is the one in the JSON schema. The conventional spellings stay
    # accepted, because a model that guesses them should still be understood.
    for field_name, (annotation, field_info) in list(fields.items()):
        wire = next(
            (m.name for m in getattr(field_info, "metadata", []) if isinstance(m, WireName)),
            None,
        )
        if wire is None:
            continue
        # Copied first. `fields` holds the author's own FieldInfo objects, and
        # setting an alias on one reaches back into the schema they declared —
        # which create_llm_schema must never do, and which the mutation test
        # beside it did not catch because it compared field names only.
        field_info = copy.deepcopy(field_info)
        spellings = [wire] + [c for c in _spellings(field_name).choices if c != wire]
        field_info.validation_alias = AliasChoices(*spellings)
        field_info.serialization_alias = wire
        field_info.alias = wire
        fields[field_name] = (annotation, field_info)

    # A Gloss is the pack's own sentence, and this view is the only place it goes.
    #
    # `description` holds the API's words, which is what makes it checkable
    # against the reference page. Appending there would leave the pack's
    # sentence and the API's indistinguishable, and the next regeneration from
    # the docs would take the help away without anyone seeing it go.
    #
    # Glosses are read off the author's schema, not off `fields`: a `Format`
    # field's markers moved onto its annotation above and are no longer on the
    # FieldInfo this loop sees. And the description is passed as the assignment
    # rather than set on the FieldInfo, because pydantic builds a fresh
    # FieldInfo from the one it is handed and keeps a plain attribute assignment
    # only for the instances it marks final. The author's is final and the
    # Format branch's is not, so assigning worked for most fields and silently
    # did nothing for a retyped one. Demoting the FieldInfo into the annotation
    # puts the description in the slot that always wins, copies nothing, and
    # leaves every other attribute on it in force. It runs after the alias pass
    # because that one reads markers off the FieldInfo this one demotes.
    for field_name, (annotation, field_info) in list(fields.items()):
        gloss = _gloss_text(original_schema.model_fields[field_name])
        if not gloss:
            continue
        documented = (field_info.description or "").strip()
        fields[field_name] = (
            Annotated[(annotation, field_info)],
            Field(description=f"{documented} {gloss}" if documented else gloss),
        )

    # Validators are not fields, so create_model would drop them. A schema's
    # cross-field rules are part of its contract — carry them across.
    validators = dict(_carry_validators(original_schema, set(fields)))
    conflicts = _conflict_validator(fields)
    if conflicts is not None:
        validators["_charter_conflicts"] = conflicts
    new_model = create_model(
        llm_model_name,
        __base__=LLMBase,
        __validators__=validators,
        **fields,
    )
    new_model.charter_declared_name = original_schema.__name__

    # Same for the strictness half of model_config. LLMBase owns the alias
    # machinery, so only the keys that decide whether a wrong input is rejected
    # are carried, and they are applied on top rather than replacing the config.
    source_config: Dict[str, Any] = dict(original_schema.model_config)
    carried_config = {
        key: source_config[key] for key in _CARRIED_CONFIG_KEYS if key in source_config
    }
    if carried_config:
        merged: Dict[str, Any] = {**dict(new_model.model_config), **carried_config}
        new_model.model_config = cast(ConfigDict, merged)
        new_model.model_rebuild(force=True)

    # Carry the schema-level case override across to the LLM view; call_api reads
    # it off the instance's class, which is this generated model.
    schema_case = getattr(original_schema, "__case__", None)
    if schema_case is not None:
        new_model.__case__ = schema_case  # type: ignore[attr-defined]

    _seen_types[cache_key] = new_model
    if prune_scope is None and _pending is not None:
        # The source class is stored beside the model it generated, and only to
        # keep it alive. Part of the key is `id(original_schema)`, which is sound
        # for `_seen_types` because the schema graph is alive for that one call,
        # and would not be for a store the caller keeps: let the source be
        # collected and CPython is free to hand its address to an unrelated
        # class, which would then read a model built from something else.
        _pending[cache_key] = (original_schema, new_model)

    # Every parked name is a ForwardRef by the time it reaches `fields`, and a
    # ref resolves against the whole walk rather than this one model, so the
    # self-reference case is no longer special: `_rebuild_generated` is the only
    # place forward references are resolved.
    if is_root:
        _rebuild_generated(_seen_types)
        if cache is not None and _pending:
            # Published here and nowhere else, because this is the first moment
            # a generated model is usable: until `_rebuild_generated` returns,
            # most of a recursive graph still holds unresolved forward refs.
            # Publishing as each model was built put those in the caller's store,
            # where a concurrent reader took one for finished — short-circuiting
            # the walk that would have built its children, then either raising
            # `PydanticUndefinedAnnotation` or memoising a view that raises
            # `not fully defined` on every call the tool is ever given. A walk
            # that raised before the rebuild left the same wreckage behind with
            # no second thread involved.
            #
            # `__pydantic_complete__` is checked rather than assumed: the dict
            # branch above tolerates a model the rebuild cannot finish, and one
            # of those is exactly what must not be shared onward.
            for key, entry in _pending.items():
                if getattr(entry[1], "__pydantic_complete__", False):
                    cache[key] = entry

    return new_model


# -----------------------------------------------------
# Deriving one operation's view of a resource
# -----------------------------------------------------
#
# `partial_of` builds its result with `create_model`, and a class built at
# runtime is invisible to a static checker. So every use site pays one
# suppression to name the derived model in a type expression:
#
#     body: Annotated[
#         PatchLabelRequest,  # type: ignore[valid-type]
#         Field(..., description="The fields to change on the label."),
#         Body(),
#     ]
#
# That is the price of deriving rather than declaring, and it is worth knowing
# there is a shape that avoids it. Relax per *field* instead of per model:
#
#     def relaxed(model: Type[BaseModel], field: str) -> Any:
#         """`model`'s field, with its default set to None."""
#
#     class PatchLabelRequest(BaseModel):
#         name: Optional[str] = relaxed(Label, "name")
#         color: Optional[Color] = relaxed(Label, "color")
#
# A real class, so no suppression and full IDE completion, while the
# descriptions and constraints still have one home on `Label`. It typechecks
# because `relaxed` returns `Any`, the same trick `Field()` uses. The cost is
# restating each field name and annotation, which is arguably right for a patch
# body: it makes the writable surface explicit rather than "whatever the
# resource happens to have".
#
# Not built, because there are two PATCH bodies in the whole corpus and a second
# mechanism for two call sites is worse than one suppression. **The trigger to
# revisit is the suppression count.** Past roughly a dozen derived bodies,
# `relaxed` becomes the better default and `partial_of` becomes the shorthand
# for the simple cases. `grep -rn "type: ignore" src/charter/packs/` is the
# measurement.


def partial_of(
    model: Type[BaseModel],
    *,
    name: Optional[str] = None,
    doc: Optional[str] = None,
) -> Type[BaseModel]:
    """``model`` with every top-level field optional. The body of a PATCH.

    One resource routinely serves create, update and patch, and the operations
    disagree about what is mandatory: Gmail's ``Label`` needs a ``name`` to be
    created or replaced, and needs nothing to be patched. Writing the patch body
    out by hand copies every description into a second place that nothing keeps
    in sync, so it is derived instead::

        PatchLabelRequest = partial_of(Label, name="PatchLabelRequest")

    Descriptions, constraints, ``Field`` metadata and the ``Path``/``Query``/
    ``Body``/``Mode``/``Format`` markers all come across, so the derived model
    routes and validates exactly as its source does — it only stops demanding.

    **Nested models are left alone.** Relaxing a whole tree would quietly drop
    constraints the API still enforces several levels down, and the two patch
    conventions disagree about nesting anyway: JSON Merge Patch (RFC 7396)
    merges a nested object, while Google's replaces it wholesale. Only the
    fields this model declares are relaxed; call ``partial_of`` again on a
    nested model if that one really is partial too.

    Two things a caller should know:

    - Validators come across via the same path ``create_llm_schema`` uses, so a
      cross-field rule survives. A rule of the form "``a`` is required when
      ``b`` is set" therefore still applies — being partial does not mean being
      unconstrained.
    - Charter dumps bodies with ``exclude_none=True``, so an unset field is
      *omitted*, never sent as ``null``. That matches Google-style patch, where
      absent means unchanged. It cannot express RFC 7396's ``null``-means-delete.
    """
    fields: Dict[str, Any] = {}

    for field_name, field_info in model.model_fields.items():
        annotation = field_info.annotation
        already_optional = get_origin(annotation) is Union and type(None) in get_args(
            annotation
        )
        if not already_optional:
            annotation = Optional[annotation]

        # The markers and the constraints both live in `metadata`, and both have
        # to survive: dropping Query() would move the field into the body, and
        # dropping Le(500) would let a value through that the API rejects.
        preserved = list(getattr(field_info, "metadata", []))
        fields[field_name] = (
            Annotated[(annotation, *preserved)] if preserved else annotation,
            Field(
                default=None,
                description=field_info.description,
                title=getattr(field_info, "title", None),
                examples=getattr(field_info, "examples", None),
            ),
        )

    # create_model reads the calling frame for __module__, which would be this
    # one: a pack's model would report charter.execution.schema as its home.
    caller = sys._getframe(1).f_globals.get("__name__", model.__module__)

    return create_model(
        name or f"Partial{model.__name__}",
        __doc__=doc or f"{model.__name__}, with every field optional.",
        __module__=caller,
        __validators__=_carry_validators(model, set(fields)),
        **fields,
    )
