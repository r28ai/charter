# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Egress control — what a model is allowed to see.

``Mode`` is usually explained as context economy: drop the fields the model does
not need and the prompt gets cheaper. That is true, and it undersells it.

The LLM view of a schema is computed deterministically, from declarations, before
any request is made. A field marked ``Mode("response_only")`` or
``Mode("disabled")`` is not filtered out of the prompt after the fact — it is
absent from the type the model is given, so it cannot be sent to the model
provider at all. Field-level data minimisation, enforced by construction.

That makes the boundary auditable in a way a prompt never is. :func:`egress_map`
renders the answer to the question every security review asks: *what, exactly,
can the model see?* It reads the same declarations the runtime executes, so it
cannot drift from the truth.

A projection (:meth:`~charter.tool.Tool.derived`) is reported the same way, and
has to be: a restriction the reviewer cannot read is not a control. Fields the
deployment removed are withheld as ``projection``, and a pinned field is withheld
as ``pinned`` *with its value*, since "this agent can only search documents" is
a claim about the value, not the field.

    from charter.egress import egress_map
    from charter.packs import gmail

    report = egress_map(gmail.TOOLS)
    print(report["gmail__messages_send"]["withheld"])
"""

from __future__ import annotations

from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Type,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel

from charter.execution.schema import should_include_field
from charter.naming import _duplicate_row, _rows, report_key
from charter.tool import Tool
from charter.transforms import get_transform
from charter.types.markers import Format, Mode

__all__ = ["egress_map", "format_egress_map"]

_MAX_DEPTH = 12

# A surface to report on: the tools themselves, or a map of published name to
# tool — which is the shape `ToolSession.tools` has, and the one a reviewer
# auditing a conversation actually holds.
Surface = Union[Iterable[Tool], Mapping[str, Tool]]


def _unwrap(annotation: Any) -> Any:
    """``Optional[X]`` / ``List[X]`` / ``Dict[K, X]`` -> ``X``, as far as it goes.

    The dict case is the one an auditor would miss: a map of name to model hides
    a whole subtree behind a container that is not a list, and without it the
    map reports a field as a leaf and says nothing about what is under it.

    Peels every layer, which is what :func:`~charter.execution.schema._llm_type`
    does when it builds the view. The two have to agree: while this one unwrapped
    ``List[List[X]]`` and that one rewrote only the outer layer, the map reported
    Notion's table cells as filtered and the model was handed them whole.
    """
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        # One real member is a nullable field, and the view is built from it.
        # Several is a union the builder rewrites member by member, keeping them
        # all, so there is no single type to unwrap to: `_members` walks each.
        # Picking one here would name that member's subtree and hide the rest.
        if len(non_none) == 1:
            return _unwrap(non_none[0])
        return annotation
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if args:
            return _unwrap(args[0])
    if get_origin(annotation) is dict:
        args = get_args(annotation)
        if len(args) == 2:
            return _unwrap(args[1])
    return annotation


def _members(annotation: Any) -> List[Type[BaseModel]]:
    """The models in a union of several types, each of which the builder rewrites."""
    if get_origin(annotation) is not Union:
        return []
    non_none = [a for a in get_args(annotation) if a is not type(None)]
    if len(non_none) < 2:
        return []
    return [a for a in non_none if isinstance(a, type) and issubclass(a, BaseModel)]


def _retyped(field: Any) -> Optional[Any]:
    """The semantic type a ``Format`` retypes this field to, or ``None``.

    A ``Format`` field is retyped to its transform's semantic type, so the model
    fills in an ``EmailContent`` and never sees the base64 MIME string the API
    takes. Reading ``field.annotation`` instead described the wire type: Gmail's
    ``body.raw`` was reported as one visible leaf while the model was being
    offered eleven fields under it, none of them named anywhere in the map.
    Mirrors the ``format_marker`` branch of
    :func:`~charter.execution.schema._create_llm_schema`.

    Returns ``None`` rather than the annotation, so a caller can tell *retyped
    to the same class* from *not retyped*. Comparing the two types instead reads
    the same either way, and the two are not the same thing: the ``Format``
    branch substitutes and stops, carrying neither ``Mode`` nor prune inside,
    whichever type it lands on. ``FieldMask`` is that case, and would have taken
    the filtering path the day one of its fields was declared non-optional.
    """
    marker = next((m for m in field.metadata if isinstance(m, Format)), None)
    if marker is None:
        return None
    spec = get_transform(marker.transform)
    # No transform, or the abstract `BaseModel` catch-all for transforms that
    # accept many types — either way the author's annotation is what is kept.
    if spec is None or spec.semantic_type is BaseModel:
        return None
    return spec.semantic_type


def _verbatim(
    schema: Type[BaseModel],
    prefix: str,
    seen: Set[int],
    depth: int,
    visible: List[str],
    emitted: Optional[Set[str]] = None,
) -> None:
    """List every path under a type the builder embeds untouched.

    A ``Format``'s semantic type is copied into the view whole: no ``Mode``
    filtering, no prune, nothing. Walking it with :func:`_walk` would apply both
    and report fields as withheld that the model is holding — the exact failure
    the map exists to rule out — so this reports what is there and claims no
    control over it. A union's members are *not* this case: they are each
    rewritten, so `_walk` handles them.
    """
    if depth > _MAX_DEPTH or id(schema) in seen:
        return
    seen = seen | {id(schema)}
    # Carried rather than recomputed from `visible`: the members of a union share
    # a prefix, so two of them naming the same field would list it twice, and
    # rescanning the list at every field to notice makes the walk quadratic.
    if emitted is None:
        emitted = set(visible)
    for name, field in schema.model_fields.items():
        path = f"{prefix}{name}"
        if path not in emitted:
            emitted.add(path)
            visible.append(path)
        # `field.annotation`, not the retyped view: nothing in here is rewritten,
        # so a `Format` on a field of a semantic type is not applied either. The
        # builder never runs over this subtree at all — it substitutes the
        # semantic type and stops — and "verbatim" has to mean the same thing at
        # every depth or this walk invents a retyping of its own.
        nested = _unwrap(field.annotation)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            _verbatim(nested, f"{path}.", seen, depth + 1, visible, emitted)
        for member in _members(nested):
            _verbatim(member, f"{path}.", seen, depth + 1, visible, emitted)


def _merge_branches(
    branch_visible: List[str],
    branch_withheld: List[Dict[str, str]],
    visible: List[str],
    withheld: List[Dict[str, str]],
) -> None:
    """Fold one union's members into the report, one row per path.

    The members of a union share a path prefix, so two of them naming the same
    field produce the same path twice. Firecrawl's three monitor targets all
    carry `id` and `type`, which listed 76 paths twice on two tools.

    Where they disagree, **visible wins**: a field one member offers is a field
    the model can send, by choosing that member, whatever a sibling member
    declares about its own field of that name. Reporting it withheld would be
    the one error this module exists to prevent, and reporting it both ways —
    which is what happened before this function — makes the artifact contradict
    itself and quietly breaks `visible` and `withheld` being disjoint.
    """
    offered = set(visible)
    for path in branch_visible:
        if path not in offered:
            offered.add(path)
            visible.append(path)
    held = {row["field"] for row in withheld}
    for row in branch_withheld:
        field = row["field"]
        if field in offered or field in held:
            continue
        held.add(field)
        withheld.append(row)


def _reason(field: Any) -> str:
    """Why a field is withheld, in the schema's own words."""
    for meta in field.metadata:
        if isinstance(meta, Mode):
            if "disabled" in meta.modes:
                return "disabled"
            if "response_only" in meta.modes:
                return "response_only"
            if meta.modes:
                return f"mode={','.join(sorted(meta.modes))}"
    return "filtered"


def _walk(
    schema: Type[BaseModel],
    modes: FrozenSet[str],
    prefix: str,
    seen: Set[int],
    depth: int,
    visible: List[str],
    withheld: List[Dict[str, str]],
    parent_modes: Optional[set] = None,
    prune: frozenset = frozenset(),
    pins: Optional[Dict[str, Any]] = None,
) -> None:
    if depth > _MAX_DEPTH or id(schema) in seen:
        return
    seen = seen | {id(schema)}
    pins = pins or {}

    for name, field in schema.model_fields.items():
        path = f"{prefix}{name}"
        # A projection is checked before Mode, because it is the narrower claim:
        # "withheld by this deployment" is what a reviewer needs to see, and
        # reporting the author's reason for a field the deployer also removed
        # would credit the wrong decision.
        if path in prune:
            if path in pins:
                withheld.append({"field": path, "reason": "pinned", "value": repr(pins[path])})
            else:
                withheld.append({"field": path, "reason": "projection"})
            continue
        if not should_include_field(field, modes, parent_modes):
            withheld.append({"field": path, "reason": _reason(field)})
            continue

        visible.append(path)

        retyped = _retyped(field)
        nested = _unwrap(field.annotation if retyped is None else retyped)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            if retyped is not None:
                # Retyped by a `Format`. The builder substitutes the semantic
                # type and stops — it never carries `Mode` or prune inside one —
                # so reporting it as controlled would claim a filter that is not
                # running.
                _verbatim(nested, f"{path}.", seen, depth + 1, visible)
                continue
            field_modes = (
                next((m.modes for m in field.metadata if isinstance(m, Mode)), None) or parent_modes
            )
            _walk(
                nested,
                modes,
                f"{path}.",
                seen,
                depth + 1,
                visible,
                withheld,
                field_modes,
                prune,
                pins,
            )
            continue
        # A union of several types keeps every member, and each is rewritten in
        # its own right — so each is walked in its own right, filtering and all.
        # Reporting them verbatim would name fields the members' `Mode` markers
        # do remove.
        members = _members(nested)
        if members:
            field_modes = (
                next((m.modes for m in field.metadata if isinstance(m, Mode)), None) or parent_modes
            )
            branch_visible: List[str] = []
            branch_withheld: List[Dict[str, str]] = []
            for member in members:
                _walk(
                    member,
                    modes,
                    f"{path}.",
                    seen,
                    depth + 1,
                    branch_visible,
                    branch_withheld,
                    field_modes,
                    prune,
                    pins,
                )
            _merge_branches(branch_visible, branch_withheld, visible, withheld)


def egress_map(tools: Surface) -> Dict[str, Dict[str, Any]]:
    """What each tool can and cannot expose to the model.

    For every tool, walks the schema it was declared with and splits every field —
    at every nesting depth — into what reaches the model and what is withheld
    from it, with the reason taken from the declaration.

    Keyed by ``<pack>__<tool>``, or by the bare name for a tool that declares no
    pack. Every tool handed in gets a row: two that would share one raises rather
    than overwriting, because an audit artifact that quietly holds fewer rows than
    it was given is the one failure a reader cannot catch.

    Takes the tools, or a map of name to tool — so the surface a conversation
    resolved maps directly::

        session = ToolSession(reports.TOOLS, mode=plan_of(user))
        report = egress_map(session.tools)

    Returns a plain dict, so it serialises straight to JSON for an audit trail::

        {
          "gmail__messages_send": {
            "name": "messages_send",
            "pack": "gmail",
            "provider": "google",
            "visible":  ["user_id", "body", "body.raw", ...],
            "withheld": [{"field": "body.id", "reason": "response_only"}, ...],
          },
          ...
        }

    Raises:
        DeclarationError: if two tools would occupy one row.
    """
    report: Dict[str, Dict[str, Any]] = {}
    for tool in _rows(tools):
        key = report_key(tool)
        if key in report:
            raise _duplicate_row(key, tool)
        visible: List[str] = []
        withheld: List[Dict[str, str]] = []
        _walk(
            tool.args_schema,
            tool.modes,
            "",
            set(),
            0,
            visible,
            withheld,
            None,
            tool._prune,
            tool._pins,
        )
        report[key] = {
            "name": tool.name,
            "pack": tool.pack,
            "provider": tool.provider,
            "method": tool.method,
            "url_template": tool.url_template,
            # Both ends of `Mode`, because they are different claims and a
            # reviewer needs each: `mode` is the operation the pack declared,
            # `session_mode` is the surface this deployment resolved it at, and
            # `modes` is what actually filtered the view.
            "mode": tool.mode,
            "session_mode": tool.session_mode,
            "modes": sorted(tool.modes),
            "visible": visible,
            "withheld": withheld,
            "pinned": {path: repr(value) for path, value in tool._pins.items()},
        }
    return report


def format_egress_map(tools: Surface) -> str:
    """:func:`egress_map` rendered for a human reading a review."""
    report = egress_map(tools)
    lines: List[str] = []
    for name, entry in report.items():
        at = f"  at {', '.join(entry['modes'])}" if entry["modes"] else ""
        lines.append(f"{name}  ({entry['method']} {entry['url_template']}){at}")
        lines.append(f"  visible to the model ({len(entry['visible'])}):")
        for field in entry["visible"]:
            lines.append(f"    + {field}")
        if entry["withheld"]:
            lines.append(f"  withheld ({len(entry['withheld'])}):")
            for item in entry["withheld"]:
                note = f" = {item['value']}" if "value" in item else ""
                lines.append(f"    - {item['field']}  [{item['reason']}]{note}")
        if entry["pinned"]:
            lines.append(f"  pinned ({len(entry['pinned'])}):")
            for path, value in entry["pinned"].items():
                lines.append(f"    = {path}  {value}")
        lines.append("")
    return "\n".join(lines)
