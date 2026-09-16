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
    print(report["messages_send"]["withheld"])
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Type, Union, get_args, get_origin

from pydantic import BaseModel

from charter.execution.schema import should_include_field
from charter.tool import Tool
from charter.types.markers import Mode

__all__ = ["egress_map", "format_egress_map"]

_MAX_DEPTH = 12


def _unwrap(annotation: Any) -> Any:
    """``Optional[X]`` / ``List[X]`` / ``Dict[K, X]`` -> ``X``, as far as it goes.

    The dict case is the one an auditor would miss: a map of name to model hides
    a whole subtree behind a container that is not a list, and without it the
    map reports a field as a leaf and says nothing about what is under it.
    """
    if get_origin(annotation) is Union:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if non_none:
            return _unwrap(non_none[0])
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if args:
            return _unwrap(args[0])
    if get_origin(annotation) is dict:
        args = get_args(annotation)
        if len(args) == 2:
            return _unwrap(args[1])
    return annotation


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
    mode: Optional[str],
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
                withheld.append(
                    {"field": path, "reason": "pinned", "value": repr(pins[path])}
                )
            else:
                withheld.append({"field": path, "reason": "projection"})
            continue
        if not should_include_field(field, mode, parent_modes):
            withheld.append({"field": path, "reason": _reason(field)})
            continue

        visible.append(path)

        nested = _unwrap(field.annotation)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            field_modes = next(
                (m.modes for m in field.metadata if isinstance(m, Mode)), None
            ) or parent_modes
            _walk(
                nested,
                mode,
                f"{path}.",
                seen,
                depth + 1,
                visible,
                withheld,
                field_modes,
                prune,
                pins,
            )


def egress_map(tools: Iterable[Tool]) -> Dict[str, Dict[str, Any]]:
    """What each tool can and cannot expose to the model.

    For every tool, walks the schema it was declared with and splits every field —
    at every nesting depth — into what reaches the model and what is withheld
    from it, with the reason taken from the declaration.

    Returns a plain dict, so it serialises straight to JSON for an audit trail::

        {
          "messages_send": {
            "provider": "google",
            "visible":  ["user_id", "body", "body.raw", ...],
            "withheld": [{"field": "body.id", "reason": "response_only"}, ...],
          },
          ...
        }
    """
    report: Dict[str, Dict[str, Any]] = {}
    for tool in tools:
        visible: List[str] = []
        withheld: List[Dict[str, str]] = []
        _walk(
            tool.args_schema,
            tool.mode,
            "",
            set(),
            0,
            visible,
            withheld,
            None,
            tool._prune,
            tool._pins,
        )
        report[tool.name] = {
            "provider": tool.provider,
            "method": tool.method,
            "url_template": tool.url_template,
            "mode": tool.mode,
            "visible": visible,
            "withheld": withheld,
            "pinned": {path: repr(value) for path, value in tool._pins.items()},
        }
    return report


def format_egress_map(tools: Iterable[Tool]) -> str:
    """:func:`egress_map` rendered for a human reading a review."""
    report = egress_map(tools)
    lines: List[str] = []
    for name, entry in report.items():
        lines.append(f"{name}  ({entry['method']} {entry['url_template']})")
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
