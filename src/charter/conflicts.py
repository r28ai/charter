"""
Exclusion rules — which parameters an API refuses together.

:class:`~charter.types.markers.ConflictsWith` puts each rule on the field it is
about, so adding a parameter cannot forget it and removing one cannot leave it
behind. That is the right place to *declare* a rule and the wrong place to *read*
the set of them: "what does this pack refuse together?" becomes a walk over every
field rather than a glance at one list.

This is that glance, reconstructed from the declarations the runtime enforces, so
it cannot drift from them::

    from charter.conflicts import format_conflicts
    from charter.packs import gcalendar

    print(format_conflicts(gcalendar.TOOLS))

The same shape as :func:`~charter.egress.egress_map`, and for the same reason: a
property enforced by construction is only auditable if something will print it.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from pydantic import BaseModel

from charter.execution.schema import _api_name
from charter.tool import Tool
from charter.types.markers import ConflictsWith

__all__ = ["conflict_map", "format_conflicts"]


def _rules(model: type[BaseModel]) -> List[Dict[str, Any]]:
    """Every ConflictsWith on ``model``, with both halves named as the API names them."""
    names = {name: _api_name(name, info) for name, info in model.model_fields.items()}
    out: List[Dict[str, Any]] = []
    for field, info in model.model_fields.items():
        for marker in info.metadata:
            if not isinstance(marker, ConflictsWith):
                continue
            out.append(
                {
                    "field": field,
                    "api_name": names.get(field, field),
                    # A conflict may name a field this schema does not declare;
                    # reported rather than resolved, because a rule that can
                    # never fire is the defect this report exists to surface.
                    "excludes": [
                        {"field": other, "api_name": names.get(other, other), "declared": other in names}
                        for other in marker.fields
                    ],
                    "reason": marker.reason,
                }
            )
    return out


def conflict_map(tools: Iterable[Tool]) -> Dict[str, List[Dict[str, Any]]]:
    """The exclusion rules each tool declares, by tool name.

    Returns a plain dict, so it serialises straight to JSON for a review::

        {
          "events_list": [
            {"field": "i_cal_uid", "api_name": "iCalUID",
             "excludes": [{"field": "sync_token", "api_name": "syncToken", "declared": true}],
             "reason": "An incremental sync continues ..."},
            ...
          ]
        }

    Only tools that declare a conflict appear. Reads the schema the tool was
    declared with, so a field withheld from the model by ``Mode`` is still
    reported: the rule binds the request, not the prompt.
    """
    report: Dict[str, List[Dict[str, Any]]] = {}
    for tool in tools:
        rules = _rules(tool.args_schema)
        if rules:
            report[tool.name] = rules
    return report


def format_conflicts(tools: Iterable[Tool]) -> str:
    """:func:`conflict_map` rendered for a human reading a review.

    Grouped by what is excluded rather than by the field declaring it, because
    that is the question being asked: one line per rule, and the parameters it
    refuses beside it.
    """
    report = conflict_map(tools)
    if not report:
        return "no exclusion rules declared"

    lines: List[str] = []
    for tool, rules in report.items():
        lines.append(tool)
        grouped: Dict[str, Dict[str, Any]] = {}
        for rule in rules:
            for other in rule["excludes"]:
                entry = grouped.setdefault(
                    other["api_name"],
                    {"fields": [], "reason": rule["reason"], "declared": other["declared"]},
                )
                entry["fields"].append(rule["api_name"])
        for target, entry in grouped.items():
            missing = "" if entry["declared"] else "  [NOT A FIELD OF THIS SCHEMA]"
            lines.append(f"  {target}{missing} refuses {len(entry['fields'])}:")
            for field in sorted(entry["fields"]):
                lines.append(f"    - {field}")
            if entry["reason"]:
                lines.append(f"    why: {entry['reason']}")
        lines.append("")
    return "\n".join(lines)
