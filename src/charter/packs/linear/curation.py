"""Which filter conditions a tool offers a model.

Linear's filter inputs are a mirror of the API: ``IssueFilter`` carries every
sendable condition, and it reaches itself through ``and_``, ``or_``, ``parent``
and ``children``. That is right for the type and wrong for the tool. Rendered as
a schema, one list tool is 187KB across 77 definitions, and the recursion is what
makes it so.

The size is not the reason to narrow it. Measured on the ``linear_triage`` task
at temperature 0, over three models and thirty generations per cell:

===========================================  =============  =============  =============
tool as the model sees it                    glm-5p3-flash  deepseek-v4p1  nemotron-3.5
===========================================  =============  =============  =============
no filter at all (the field pruned away)              0/30           0/30           0/30
the whole 187KB mirror                               22/30       rejected       rejected
a curated filter, 15KB                               28/30          30/30           4/30
===========================================  =============  =============  =============

Two findings, and the second is the one that shaped this module. A model handed
the full mirror uses the filter about seven times in ten; handed a curated one it
uses it every time. And two of the three models **reject the request outright**
rather than degrade.

What they reject is the **recursion, not the size**. The same three models accept
``gsheets.spreadsheets_batch_update`` at 195,275 bytes - larger than the mirror -
because nothing in it refers back to itself, and they accept
``tavily.research_create``, whose one recursive type resolves shallowly. A cycle
has no depth to resolve to, and the provider rejects the whole request past depth
50, so one unusable tool takes every other tool in that request with it.

The top row is what a benchmark harness produced by deleting the recursive field
to get under that limit: a model that never filters and pages the whole team 250
issues at a time instead.

The policy below is deliberately mechanical, because per-tool taste across
sixteen tools is how a rule becomes sixteen rules:

* **keep** a field whose type is a comparator - the entity's own scalars, which
  is what a list is narrowed by most of the time;
* **keep** one level into a single-valued relation, and only its identifying
  comparators - ``team.key``, ``assignee.email``, ``state.type``;
* **drop** ``and_``/``or_``, a relation back to the filter's own entity
  (``TeamFilter.parent`` is a team), and every collection relation except
  ``labels``.
  Filtering teams by their issues is a query, not a list filter. Labels are the
  exception because "issues tagged bug" is how people actually narrow a list.

Nothing is lost. Every narrowed tool keeps an undiminished twin - ``*_full`` -
which carries the complete filter and is deliberately absent from ``TOOLS``, so a
caller who needs boolean composition can reach for it by name while no model is
handed a schema it may not be able to accept.
"""

from __future__ import annotations

from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

__all__ = ["list_filter_paths", "filter_roots", "COLLECTION_RELATIONS_KEPT", "IDENTIFYING_COMPARATORS"]

#: Collection relations worth one level of narrowing power. See the module docstring.
COLLECTION_RELATIONS_KEPT = frozenset({"labels"})

#: What identifies the thing on the other side of a relation.
IDENTIFYING_COMPARATORS = frozenset(
    {
        "id",
        "name",
        "key",
        "email",
        "type",
        "number",
        "title",
        "display_name",
        "identifier",
        "slug_id",
        "label",
    }
)


def _unwrap(annotation: Any) -> Any:
    """``Optional[X]`` -> ``X``; anything else unchanged."""
    if get_origin(annotation) is Union:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0] if args else None
    return annotation


def _is_model(value: Any) -> bool:
    return isinstance(value, type) and issubclass(value, BaseModel)


def filter_roots(args_schema: type[BaseModel]) -> list[tuple[str, type[BaseModel]]]:
    """Every filter-typed field a tool accepts, as ``(path, model)``.

    A filter is not always ``variables.filter``. ``custom_view_create`` saves a
    query as a view, so it carries four of them - ``filter_data``,
    ``project_filter_data``, ``initiative_filter_data`` and
    ``feed_item_filter_data`` - one level deeper, on ``variables.input``. Looking
    for filters by *type* rather than by name finds all of them and does not
    care where the next one turns up.

    The walk descends through container models only, never into a filter, and
    stops at depth three: past that, anything named ``*Filter`` is the recursion
    rather than an argument.
    """
    found: list[tuple[str, type[BaseModel]]] = []
    frontier: list[tuple[str, type[BaseModel]]] = [("", args_schema)]
    for _ in range(3):
        next_frontier: list[tuple[str, type[BaseModel]]] = []
        for prefix, model in frontier:
            for name, field in model.model_fields.items():
                annotation = _unwrap(field.annotation)
                if not _is_model(annotation):
                    continue
                path = f"{prefix}{name}"
                class_name = annotation.__name__
                if class_name.endswith("Filter") and not class_name.endswith(
                    "CollectionFilter"
                ):
                    found.append((path, annotation))
                else:
                    next_frontier.append((f"{path}.", annotation))
        frontier = next_frontier
    return found


def list_filter_paths(args_schema: type[BaseModel]) -> frozenset[str]:
    """The ``keep`` paths for every filter a tool accepts, empty if it has none.

    Empty is meaningful: a tool carrying no filter needs no projection, and
    passing an empty ``keep`` to :meth:`~charter.tool.Tool.derived` would narrow
    it to nothing.
    """
    paths: set[str] = set()
    for root, model in filter_roots(args_schema):
        paths.update(f"{root}.{leaf}" for leaf in _curate(model))
    return frozenset(paths)


def _curate(model: type[BaseModel]) -> list[str]:
    """The conditions kept from one filter, relative to that filter."""
    kept: list[str] = []
    for name, field in model.model_fields.items():
        annotation = _unwrap(field.annotation)
        if name in ("and_", "or_"):
            continue
        if get_origin(annotation) is list or not _is_model(annotation):
            continue
        class_name = annotation.__name__
        if class_name.endswith("Comparator"):
            kept.append(name)
        elif class_name.endswith("CollectionFilter"):
            if name in COLLECTION_RELATIONS_KEPT:
                kept.extend(
                    f"{name}.{inner}"
                    for inner in annotation.model_fields
                    if inner in IDENTIFYING_COMPARATORS
                )
        elif class_name.endswith("Filter"):
            if _same_entity(class_name, model.__name__):
                continue
            kept.extend(
                f"{name}.{inner}"
                for inner in annotation.model_fields
                if inner in IDENTIFYING_COMPARATORS
            )
    return kept


def _same_entity(relation: str, filter_name: str) -> bool:
    """Is this relation the filter pointing back at its own entity?

    ``TeamFilter.parent`` is a ``NullableTeamFilter``, and ``IssueLabelFilter``
    has one too. It is the recursion wearing a different name, and keeping it
    projects the same type twice with different fields - which pydantic then has
    to disambiguate, putting a module path where the reference wants a type name.
    """
    return relation.removeprefix("Nullable") == filter_name.removeprefix("Nullable")
