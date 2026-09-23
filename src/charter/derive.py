# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Projections — a tool narrowed by whoever deploys it.

``Mode`` narrows by a label the pack author declared on a field, so it reaches
only what that author thought to label. This is the other lever, and it needs
nothing from the pack at all. Whoever holds the tool did not write
``documents_batch_update`` and cannot edit it, but they are the one who knows
that *this* agent may insert text and must never delete a range::

    edit_text = gdocs.documents_batch_update.derived(
        name="documents_edit_text",
        keep={"insert_text", "delete_content_range", "replace_all_text"},
    )

The result is the same tool: same URL, same credentials, same validators, same
``extra="forbid"``. Only the view narrows — and because the narrowing is applied
to the schema rather than described in a prompt, an agent that reaches for
``insert_table`` gets a :class:`ToolValidationError`, not a silent success.

Two operations, and the difference matters:

``keep`` / ``drop``
    Which *capabilities* survive. Google's ``documents`` scope grants every edit
    in the API as one indivisible grant; there is no scope for "may edit text,
    may not delete content". The union member is the capability, so pruning it
    is the only place that permission can be expressed.

``pin``
    Which *values* the model may not choose. A pinned field leaves the schema the
    model fills in and stays in the one the runtime executes, so it is neither
    visible to the model nor reachable by it, and its value is indistinguishable
    on the wire from one supplied by hand — same ``Format`` transform, same body
    unwrapping, same key casing, same escaping.
    ``pin={"q": "mimeType='application/vnd.google-apps.document'"}`` is a search
    the agent cannot widen.

Both print in :func:`~charter.egress.egress_map`, which is the point: a
restriction nobody can read is not a control, and the map is generated from the
same declarations the runtime executes.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel

from charter.execution.schema import (
    ModeLabels,
    SchemaStore,
    create_llm_schema,
    llm_json_schema,
)
from charter.types.errors import DeclarationError
from charter.types.markers import Body, Path, Query

__all__ = [
    "PathCost",
    "check_pin_routing",
    "find_paths",
    "path_costs",
    "plan_projection",
    "resolve_path",
    "schema_paths",
    "walk_paths",
]

_MAX_DEPTH = 8

# Matches collected before a search gives up on counting. High enough that every
# terminating schema in the catalogue is counted exactly (the worst is 19), low
# enough that a cyclic one stops in milliseconds.
_AMBIGUITY_LIMIT = 200


def _unwrap(annotation: Any) -> Any:
    """``Optional[X]`` / ``List[X]`` -> ``X``, as far as it goes."""
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if non_none:
            return _unwrap(non_none[0])
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if args:
            return _unwrap(args[0])
    return annotation


def walk_paths(
    schema: Type[BaseModel],
    *,
    prefix: str = "",
    max_depth: Optional[int] = None,
    _seen: Tuple[int, ...] = (),
    _depth: int = 0,
) -> Iterator[str]:
    """Every addressable dotted path in ``schema``, depth-first, lazily.

    Lazy because the eager list is not always affordable. The path set is a tree
    unrolling of the model *graph*, so where the graph has cycles the tree is
    enormous even though the graph is small: Linear's ``search_issues_full`` has 77
    generated models and 2,271,553 paths. Every one of them is genuinely
    addressable, so the list is not wrong, only unaffordable to build when the
    caller wanted one level or one match.

    ``max_depth`` counts levels below ``prefix``: 1 yields the immediate fields
    and descends no further. The absolute ceiling is :data:`_MAX_DEPTH`.

    The cycle guard stays per branch, and deliberately. A model reached from two
    fields is addressable under both, and collapsing that to one would make the
    second unselectable. What the guard prevents is a path revisiting a model
    already on its *own* ancestry, which is what would not terminate.
    """
    if _depth > _MAX_DEPTH or id(schema) in _seen:
        return
    if max_depth is not None and _depth >= max_depth:
        return
    _seen = _seen + (id(schema),)
    for name, field in schema.model_fields.items():
        path = f"{prefix}{name}"
        yield path
        nested = _unwrap(field.annotation)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            yield from walk_paths(
                nested,
                prefix=f"{path}.",
                max_depth=max_depth,
                _seen=_seen,
                _depth=_depth + 1,
            )


def _model_at(schema: Type[BaseModel], path: str) -> Optional[Type[BaseModel]]:
    """The model a dotted path names, or None if the path is not one."""
    found = _descend(schema, path)
    return found[0] if found else None


def _descend(
    schema: Type[BaseModel], path: str
) -> Optional[Tuple[Type[BaseModel], Tuple[int, ...]]]:
    """The model a dotted path names, and the models passed through to reach it.

    The ancestry is what :func:`walk_paths` needs in order to start somewhere
    other than the root and still apply the same cycle guard. Without it the walk
    begins believing nothing is above it, so a model already on the path reopens
    and the listing unrolls a cycle the root walk stops at: ``paths("body.filter.
    and_")`` on the Notion query listed 27 children under a prefix that
    ``paths("", depth=4)`` said had none.

    Returned as ids rather than classes for the same reason the guard holds ids —
    two distinct models can compare equal, and identity is the question being
    asked. The target is not included: :func:`walk_paths` adds it on entry.
    """
    if not path:
        return schema, ()
    model: Any = schema
    trail: List[int] = []
    for segment in path.split("."):
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            return None
        field = model.model_fields.get(segment)
        if field is None:
            return None
        trail.append(id(model))
        model = _unwrap(field.annotation)
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        return None
    return model, tuple(trail)


def schema_paths(
    schema: Type[BaseModel],
    *,
    prefix: str = "",
    under: str = "",
    depth: Optional[int] = None,
) -> List[str]:
    """Every addressable dotted path in ``schema``, depth-first.

    The list a projection selects from, and what :meth:`Tool.paths` prints. A
    list of models contributes its members without brackets, so the path names
    what is being narrowed rather than where it sits in an array.

    ``under`` starts the walk at one field and ``depth`` limits how far below it
    the walk goes, both of which are worth reaching for rather than filtering
    afterwards. Filtering afterwards is what :meth:`Tool.paths` used to do, and
    on a recursive schema it built 2.3 million paths to return eight of them.

    Paths come back absolute, ``under`` included, so they are usable as
    selectors as they stand.

    ``depth`` is measured from ``under`` rather than from the root, so drilling
    into a deep field reaches its children rather than finding the
    :data:`_MAX_DEPTH` ceiling already spent. That is the one behavioural
    difference from filtering a whole-schema walk afterwards, and it only shows
    below the eighth level.

    What ``under`` does *not* do is start the walk with a clean slate. The models
    passed through to reach it are handed to the cycle guard, so a field whose
    type is already on its own path is as closed here as it is at the root — one
    listing, reachable two ways. Starting fresh made it two: ``paths("body.
    filter.and_")`` on ``notion.data_sources_query`` offered 27 children of a
    filter that is its own parent, while ``paths("", depth=4)`` showed none, and
    the same disagreement appeared under ``gmail.messages_send``'s nested parts
    and every ``gsheets`` ``Value``. Those paths are still addressable — ``drop``
    resolves and applies them — but pruning inside a model its siblings share is
    the negative-cost case, so a listing that led with them was leading with the
    drop you should not make.
    """
    found = _descend(schema, under)
    if found is None:
        return []
    root, ancestry = found
    return list(
        walk_paths(
            root,
            prefix=f"{prefix}{under}." if under else prefix,
            max_depth=depth,
            _seen=ancestry,
        )
    )


class PathCost(NamedTuple):
    """One path, and what the schema loses when it goes.

    Prints as a pair, so a sorted list of these reads as a bill::

        [PathCost(path='filter', tokens=46630), PathCost(path='first', tokens=50)]
    """

    path: str
    tokens: int


def path_costs(
    schema: Type[BaseModel],
    paths: Iterable[str],
    *,
    mode: ModeLabels = None,
    prune: FrozenSet[str] = frozenset(),
) -> Dict[str, int]:
    """What each path costs: tokens the generated schema loses without it.

    Measured rather than estimated. Each path is pruned for real and the
    resulting JSON schema re-measured, so the figure is the one ``drop`` will
    actually produce — a guess from subtree size would be wrong in both
    directions, over-counting a ``$def`` that other fields still reference and
    under-counting a small field whose type drags a large one in behind it.

    Four consequences worth stating rather than smoothing over. None is a defect
    in the measurement; each is something ``drop`` really does, and reporting it
    is the only way the caller finds out before shipping the projection.

    - **The costs do not sum to the total.** Where two fields share a ``$def``,
      dropping either alone leaves it in place, so both measure cheap and
      dropping both is worth more than the sum of the parts. The 33 members of
      the Docs ``Request`` union price at 6,827 between them and the branch they
      sit in costs 7,807.
    - **A cost can be negative, and then the drop is a mistake.** Pruning inside
      a model that several siblings share splits one ``$def`` into per-path
      copies. ``drop`` on ``body.requests.insert_text.location.index`` turns one
      ``Location_LLM`` into two and takes the Docs tool from 8,183 tokens to
      8,435 — a projection that narrows what the model may do and costs 252
      tokens for the privilege. Worth knowing before, not after.
    - **A cost of zero means the path is not in the view at all.** ``Mode``
      already removed it, so a projection naming it would be inert.
      ``events_insert`` prices ``event.i_cal_uid`` at 0 because ``mode="write"``
      hides it; ``events_import``, which reveals it, prices the same path at 103.
    - **A required path is priced anyway.** ``drop`` would refuse it, but the
      number is what says whether ``pin`` is worth reaching for, so refusing to
      report it would hide the answer behind the question.

    One schema generation per path, which is why :meth:`Tool.paths` measures only
    the level it returns rather than the whole subtree.
    """
    from charter.discovery import json_tokens

    paths = list(paths)
    if not paths:
        # Drilling under a leaf asks for nothing, and the baseline alone is a
        # full schema generation — 40 seconds on a Linear tool, for an empty
        # dict either way.
        return {}

    # One store across every generation below. The schemas differ only in which
    # single path is pruned, so every model that path cannot reach is built once
    # instead of once per path: `search_issues_full` priced its `variables` level in
    # 14.7s and now does it in a fraction of that, with the same numbers, because
    # the work removed was rebuilding seventy-odd models that were never going to
    # differ. It is local to this call and dropped on return.
    shared = SchemaStore()
    base = json_tokens(
        llm_json_schema(create_llm_schema(schema, mode=mode, prune=prune or None, cache=shared))
    )
    costs: Dict[str, int] = {}
    for path in paths:
        without = json_tokens(
            llm_json_schema(
                create_llm_schema(schema, mode=mode, prune=(prune | {path}), cache=shared)
            )
        )
        costs[path] = base - without
    return costs


def _child_models(schema: Type[BaseModel]) -> Dict[str, Type[BaseModel]]:
    """Field name -> the model it is annotated with, for the fields that have one."""
    out: Dict[str, Type[BaseModel]] = {}
    for name, field in schema.model_fields.items():
        nested = _unwrap(field.annotation)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            out[name] = nested
    return out


def find_paths(
    schema: Type[BaseModel],
    match: Callable[[str, Any], bool],
    *,
    limit: int = 0,
) -> List[str]:
    """Paths whose own field satisfies ``match``, depth-first, at most ``limit``.

    The expensive question a selector asks is not "where is this field" but "is
    there more than one of it", and answering it by listing every path is what
    made ``derived(drop={"filter"})`` take ten seconds on Linear.

    Two things make it cheap. Branches that cannot reach a match are never
    entered, worked out on the model *graph* where each model appears once
    rather than on the path tree where it appears once per route: 77 nodes
    against 2,271,553 paths. And the walk stops at ``limit``.

    ``limit`` is set where it is (:data:`_AMBIGUITY_LIMIT`) so that a schema
    which terminates is counted exactly and one that does not is merely bounded.
    Nineteen fields are named ``index`` in the Docs batch update, and the error
    that says nineteen is more useful than the error that says several; a cyclic
    schema reaches the limit long before it would finish, and there the exact
    number was never going to be worth the wait.

    Pruning a branch that contains no match cannot lose one, so the paths that
    come back, and their order, are what a full walk would have produced.
    """
    graph: Dict[int, Tuple[Type[BaseModel], Dict[str, Type[BaseModel]]]] = {}
    stack = [schema]
    while stack:
        model = stack.pop()
        if id(model) in graph:
            continue
        children = _child_models(model)
        graph[id(model)] = (model, children)
        stack.extend(children.values())

    # The models that own a match, then everything that can reach one.
    live = {
        key
        for key, (model, _) in graph.items()
        if any(match(name, field) for name, field in model.model_fields.items())
    }
    growing = True
    while growing:
        growing = False
        for key, (_, children) in graph.items():
            if key not in live and any(id(c) in live for c in children.values()):
                live.add(key)
                growing = True

    out: List[str] = []

    def walk(model: Type[BaseModel], prefix: str, seen: Tuple[int, ...], depth: int) -> bool:
        """True once ``limit`` is reached, to unwind the recursion."""
        if depth > _MAX_DEPTH or id(model) in seen:
            return False
        seen = seen + (id(model),)
        for name, field in model.model_fields.items():
            path = f"{prefix}{name}"
            if match(name, field):
                out.append(path)
                if limit and len(out) >= limit:
                    return True
            nested = _unwrap(field.annotation)
            if (
                isinstance(nested, type)
                and issubclass(nested, BaseModel)
                and id(nested) in live
                and walk(nested, f"{path}.", seen, depth + 1)
            ):
                return True
        return False

    if id(schema) in live:
        walk(schema, "", (), 0)
    return out


def _field_at(schema: Type[BaseModel], path: str) -> Any:
    """The ``FieldInfo`` a canonical path names, or None."""
    model: Any = schema
    field = None
    for segment in path.split("."):
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            return None
        field = model.model_fields.get(segment)
        if field is None:
            return None
        model = _unwrap(field.annotation)
    return field


def _class_paths(schema: Type[BaseModel], target: type, *, limit: int = 0) -> List[str]:
    """Paths whose field is annotated with ``target``."""
    return find_paths(schema, lambda _name, field: _unwrap(field.annotation) is target, limit=limit)


def _count(found: List[str]) -> str:
    """How many were found, or that the search stopped counting.

    A search that fills :data:`_AMBIGUITY_LIMIT` did not finish, so reporting its
    length as the answer would state a number that is merely where the walk gave
    up."""
    return f"more than {_AMBIGUITY_LIMIT}" if len(found) > _AMBIGUITY_LIMIT else str(len(found))


def resolve_path(schema: Type[BaseModel], selector: Any, *, where: str) -> str:
    """One selector -> one canonical dotted path.

    Accepts the full path, an unambiguous trailing segment, or the model class a
    field is annotated with. The short form is what makes this usable: of the 33
    members of the Docs ``Request`` union every one is unique by its own name,
    while ``index`` names nineteen different fields — so the ambiguity lands
    exactly where a short name was the wrong way to say it, and the error names
    the candidates rather than guessing.
    """
    if isinstance(selector, type) and issubclass(selector, BaseModel):
        matches = _class_paths(schema, selector, limit=_AMBIGUITY_LIMIT + 1)
        if not matches:
            raise DeclarationError(
                f"{where}: no field on {schema.__name__} is a {selector.__name__}.",
                docs="tools/projections",
            )
        if len(matches) > 1:
            raise DeclarationError(
                f"{where}: {selector.__name__} is the type of {_count(matches)} fields "
                f"({', '.join(matches[:6])}). Name the one you mean as a path.",
                docs="tools/projections",
            )
        return matches[0]

    if not isinstance(selector, str) or not selector.strip():
        raise DeclarationError(
            f"{where}: expected a dotted path, a field name, or a model class; got {selector!r}.",
            docs="tools/projections",
        )

    selector = selector.strip()
    # A full path is answered by walking it, not by searching for it. This is the
    # form `Tool.paths` prints and the form generated code passes, and it costs
    # one dict lookup per segment against a walk that can run to millions.
    if _field_at(schema, selector) is not None:
        return selector

    # A trailing segment has to be searched for. `find_paths` prunes to branches
    # that can reach one and stops at the limit, so a name that is unique is
    # confirmed cheaply and one that is not is counted where counting terminates.
    tail = find_paths(schema, lambda name, _field: name == selector, limit=_AMBIGUITY_LIMIT + 1)
    if len(tail) == 1:
        return tail[0]
    if len(tail) > 1:
        shown = ", ".join(tail[:6]) + (f", … ({_count(tail)} total)" if len(tail) > 6 else "")
        raise DeclarationError(
            f"{where}: {selector!r} matches {_count(tail)} paths ({shown}). Write the full path.",
            docs="tools/projections",
        )

    near: List[str] = []
    for path in walk_paths(schema, max_depth=3):
        if selector in path:
            near.append(path)
            if len(near) >= 6:
                break
    hint = f" Did you mean: {', '.join(near)}?" if near else ""
    raise DeclarationError(
        f"{where}: {selector!r} is not a field of {schema.__name__}.{hint} "
        "Tool.paths() lists them.",
        docs="tools/projections",
    )


def _siblings(schema: Type[BaseModel], path: str) -> List[str]:
    """Every path sharing this one's parent, itself included.

    The parent's own fields, read off the model. Not :func:`schema_paths`, and
    that distinction is load-bearing: ``schema_paths`` applies the cycle guard
    from the root, so under a model that is its own ancestor it answers with
    nothing. That is right for a *listing*, which should say the same thing
    wherever it is asked from. It is wrong here, where the caller already holds a
    concrete path and is asking which of its siblings ``keep`` must prune.

    Routing this through the listing silently turned ``keep`` into a no-op for
    any selector below a cycle: ``keep={"body.filter.and_.checkbox"}`` on
    ``notion.data_sources_query`` pruned 0 paths and handed back the whole
    21,849-byte tool instead of a 3,383-byte one. A projection that quietly grants
    everything is the one failure this module exists to prevent, so the two
    questions are answered separately.

    One level, so there is nothing to guard against: a walk that never descends
    cannot revisit anything."""
    parent, _, _ = path.rpartition(".")
    model = _model_at(schema, parent)
    if model is None:
        return []
    prefix = f"{parent}." if parent else ""
    return [f"{prefix}{name}" for name in model.model_fields]


def plan_projection(
    schema: Type[BaseModel],
    *,
    keep: Optional[Iterable[Any]] = None,
    drop: Optional[Iterable[Any]] = None,
    pin: Optional[Dict[str, Any]] = None,
) -> Tuple[frozenset, Dict[str, Any]]:
    """Resolve a projection to the set of paths to prune and the pins to apply.

    ``keep`` narrows *within the sibling group it names* rather than deleting
    everything else: keeping ``body.requests.insert_text`` drops the other 32
    members of that union and leaves ``document_id`` and ``body.write_control``
    alone. Anything else would make the first ``keep`` anyone writes produce a
    tool that cannot be called.
    """
    prune: Set[str] = set()
    pins: Dict[str, Any] = {}

    for selector in drop or ():
        prune.add(resolve_path(schema, selector, where="drop"))

    kept = [resolve_path(schema, s, where="keep") for s in keep or ()]
    for path in kept:
        for sibling in _siblings(schema, path):
            if sibling not in kept and not any(k.startswith(f"{sibling}.") for k in kept):
                prune.add(sibling)
    prune -= set(kept)
    for path in kept:
        # An ancestor of a kept path is how you reach it; pruning one because a
        # sibling rule caught it would delete the branch being kept.
        parts = path.split(".")
        for i in range(1, len(parts)):
            prune.discard(".".join(parts[:i]))

    for selector, value in (pin or {}).items():
        path = resolve_path(schema, selector, where="pin")
        if "." in path:
            raise DeclarationError(
                f"pin: {path!r} is nested, and a pin is merged in at the top level "
                "of the request model. Pin a top-level field, or use drop and "
                "supply the value in build_request.",
                docs="tools/projections",
            )
        pins[path] = value
        prune.add(path)

    _check_required(schema, prune, pins)
    return frozenset(prune), pins


def _check_required(schema: Type[BaseModel], prune: Set[str], pins: Dict[str, Any]) -> None:
    """A pruned field the API demands leaves a tool that cannot be called.

    Caught here rather than at the first 400: the declaration is wrong, its author
    is reading this, and ``pin`` is the answer whenever the value is known.
    """
    for path in sorted(prune):
        if path in pins:
            continue
        field = _field_at(schema, path)
        if field is not None and field.is_required():
            raise DeclarationError(
                f"{path!r} is required by the API, so dropping it leaves a tool that "
                f"cannot be called. Pin a value for it instead: pin={{{path.rpartition('.')[2]!r}: ...}}.",
                docs="tools/projections",
            )


def check_pin_routing(schema: Type[BaseModel], pins: Dict[str, Any]) -> None:
    """Every pinned field has somewhere to go.

    Values are not routed here. A pin is merged into the model the runtime
    executes, so it travels the path a supplied value travels and picks up the
    same ``Format`` transform, body unwrapping and key casing. What is worth
    catching at declaration is the field that has no marker at all, which would
    otherwise be dropped in silence.
    """
    for path in pins:
        field = _field_at(schema, path)
        marker = next(
            (m for m in getattr(field, "metadata", []) if isinstance(m, (Path, Query, Body))),
            None,
        )
        if marker is None:
            raise DeclarationError(
                f"pin: {path!r} carries no Path()/Query()/Body() marker, so there is "
                "nowhere to send it.",
                docs="tools/projections",
            )
