"""
The Charter arm: a pack's tools, as the model sees them through the boundary.

Nothing is re-declared here. Each Inspect ``ToolDef`` is built from the same
``Tool.to_json_schema()`` the OpenAI/LangChain/MCP adapters use, and each call
goes through ``Tool.ainvoke`` — validation, casing, Format transforms, Mode
filtering, envelope detection, response trimming, all of it. The only work this
module does is the projection Inspect needs:

- ``$ref``/``$defs`` are inlined, because Inspect's ``JSONSchema`` model has no
  reference support (nested Pydantic models such as ``EmailContent`` emit them).
- A ``CharterError`` becomes a ``ToolError`` so the model reads the message and
  the run continues — the same thing the LangChain and MCP adapters do.
- Every call reports to the sample's :class:`~charter_harness.arms.ledger.Ledger`
  through the tool's public ``on_call`` sink.

Two tools are withheld from the model on every scenario: ``gmail.messages_send``
(the harness runs against a real mailbox and must never send) and
``slack.search_messages`` (needs a user token the harness does not hold). The
raw arm's guard refuses the matching endpoints, so both arms see the same set.
"""

from __future__ import annotations

import copy
import importlib
import json
from collections.abc import Sequence
from typing import Any, Union, get_args, get_origin

from charter.tool import Tool
from charter.types.errors import CharterError
from inspect_ai.tool import ToolDef, ToolError, ToolParams
from inspect_ai.util import JSONSchema
from pydantic import BaseModel

from charter_harness._client import shared_client
from charter_harness.arms.base import register
from charter_harness.arms.ledger import record_charter_call
from charter_harness.arms.ownership import record_charter_creation
from charter_harness.context import run_context
from charter_harness.settings import Wiring


def _open_inspect_schema() -> None:
    """Let Inspect's schema models carry ``$defs`` and ``$ref``.

    ``JSONSchema`` declares a fixed field set and no ``extra``, so pydantic drops
    both on validation - which is the only reason this arm ever flattened a
    schema. Flattening is not free: it is what turned a 188KB Linear tool into
    115MB, and it means every Charter-arm number was measured against a tool
    surface no SDK user is given.

    Fireworks accepts ``$defs``/``$ref`` in a tool schema and the model resolves
    them, so the flattening bought nothing. Opening the model here is invasive,
    and the alternative is worse: benchmarking a projection of the product rather
    than the product.
    """
    from pydantic import ConfigDict

    for model in (JSONSchema, ToolParams):
        if model.model_config.get("extra") == "allow":
            continue
        model.model_config = ConfigDict(**{**dict(model.model_config), "extra": "allow"})
        model.model_rebuild(force=True)


_open_inspect_schema()

__all__ = [
    "EXCLUDED_TOOLS",
    "normalize",
    "to_tool_params",
    "charter_tooldef",
    "recursive_paths",
    "pack_tools",
    "CharterArm",
]

# (pack, tool) pairs the model never gets, on either arm.
#
# Gmail has *two* ways to send, and withholding only the obvious one is how the
# guarantee gets lost: `drafts_send` posts an existing draft and reaches the same
# recipients as `messages_send`. The harness runs against a real mailbox whose
# owner's one hard rule is that nothing leaves it.
#
# GitHub's two notification writes are withheld for a different reason, and the
# reason is the comparison rather than safety alone. Guard rule 2 confines GitHub
# writes to `<owner>/harness-*`, and these two touch the account instead of a
# repository, so the guard refuses them on the raw arm while the Charter arm was
# still offering them. That breaks the invariant the guard exists to enforce —
# both arms reach the same endpoints — which every arm-to-arm number depends on.
# Withholding them keeps the arms identical and the account's real notifications
# untouched. The two GET tools stay: reading notifications changes nothing.
EXCLUDED_TOOLS: frozenset[tuple[str, str]] = frozenset(
    {
        ("gmail", "messages_send"),
        ("gmail", "drafts_send"),
        ("slack", "search_messages"),
        ("github", "notifications_mark_read"),
        ("github", "notifications_mark_thread_read"),
    }
)


def normalize(schema: dict[str, Any]) -> dict[str, Any]:
    """``schema`` with the constructs Inspect cannot express folded into ones it can.

    ``oneOf`` becomes ``anyOf``, a single-element ``allOf`` is merged into its
    parent, and ``const`` becomes a one-value ``enum``. ``$ref`` and ``$defs``
    are left exactly as the SDK emitted them - that is the point.
    """

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "oneOf":
                out["anyOf"] = walk(value)
            elif key == "allOf" and isinstance(value, list) and len(value) == 1:
                inner = walk(value[0])
                if isinstance(inner, dict):
                    for k, v in inner.items():
                        out.setdefault(k, v)
            elif key == "const":
                out["enum"] = [value]
            else:
                out[key] = walk(value)
        return out

    return walk(copy.deepcopy(schema))


def _describe(name: str, prop: dict[str, Any], tool: str) -> dict[str, Any]:
    """Refuse a parameter the pack ships without a description.

    This used to substitute the title pydantic derived from the field name, so a
    missing description became "Singleevents" and the run continued. Every
    measurement taken against gcalendar was taken that way: nineteen of its
    parameters had no description at all, the arm quietly supplied one, and the
    numbers were attributed to a schema the SDK does not emit.

    Every pack now describes every parameter, so the substitution has nothing
    left to do and only conceals the next regression. Inspect refuses an
    undescribed parameter anyway; this refuses it with the name of the field."""
    if prop.get("description"):
        return prop
    raise ValueError(
        f"{tool}.{name} has no description. The harness will not stand one in: "
        f"the model would be measured against a schema the SDK does not emit. "
        f"Describe the field in the pack."
    )


def to_tool_params(parameters: dict[str, Any], tool: str = "?") -> ToolParams:
    """An OpenAI-style ``parameters`` object as Inspect ``ToolParams``."""
    flat = normalize(parameters)
    properties = {
        name: JSONSchema.model_validate(_describe(name, prop, tool))
        for name, prop in (flat.get("properties") or {}).items()
    }
    params = ToolParams(
        properties=properties,
        required=list(flat.get("required") or []),
        additionalProperties=False,
    )
    # The definitions the properties' ``$ref``s point at. Without them the
    # references dangle and the model is handed a schema it cannot resolve.
    if defs := flat.get("$defs"):
        setattr(params, "$defs", defs)
    return params


def _render(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


# A tool's schema is fixed for the life of the process, but Inspect re-resolves
# the tool source on every turn of the react loop, so without this the arm rebuilt
# every schema each turn - 10s per turn for linear's 128 tools.
#
# Keyed on the projection as well as the name. `pack.tool` alone is not a key: a
# projection keeps the name of the tool it narrowed, so `linear.issues_list` names
# two different schemas once `pack_tools` has projected the pack, and whichever
# was built first was served for both.
_PARAMS: dict[tuple[str, str, frozenset, tuple], ToolParams] = {}


def _params_key(tool: Tool) -> tuple[str, str, frozenset, tuple]:
    return (
        tool.pack or "?",
        tool.name,
        tool._prune,
        tuple(sorted((k, repr(v)) for k, v in tool._pins.items())),
    )


def charter_tooldef(tool: Tool, *, name: str | None = None) -> ToolDef:
    """One Charter tool as an Inspect ``ToolDef``. The model's view is the SDK's view.

    ``name`` overrides the model-facing name; the arm uses it only when two packs
    in one scenario declare the same tool name (``products_list`` exists in both
    stripe and shopify), which no function-calling API can carry unqualified.
    """
    definition = tool.to_json_schema()
    cache_key = _params_key(tool)
    params = _PARAMS.get(cache_key)
    if params is None:
        params = to_tool_params(definition["parameters"], definition["name"])
        _PARAMS[cache_key] = params

    # Inspect binds a tool call's arguments to the callable's signature, and the
    # one shape it passes straight through is literally `**kwargs: Any`.
    async def call(**kwargs: Any) -> str:
        try:
            result = await tool.ainvoke(kwargs, client=shared_client())
            # An id the agent just made is an id the agent may unmake.
            record_charter_creation(tool.pack, tool.name, result)
            return _render(result)
        except CharterError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:  # httpx timeouts and the like: the model hears about it
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    call.__name__ = name or tool.name
    return ToolDef(
        call,
        name=name or definition["name"],
        description=definition["description"],
        parameters=params,
        # Inspect truncates tool output at 16 KB by default. Both arms disable
        # that: the Charter arm's outputs are already trimmed by the packs, and
        # the raw arm applies its own documented cap.
        max_output=0,
    )


# The name a pack's recursion-carrying fields share.
#
# Linear's GraphQL filters are mutually referential: 56 of the pack's 77
# definitions sit in a cycle, so one filter argument pulls in the whole graph and
# the schema comes to 188KB. Fireworks then refuses the tool outright - "schema
# depth exceeds maximum limit of 50" - so projecting it away is not an
# optimisation, it is the difference between the tool being callable and not.
#
# A substring rather than a field name, because the name is not one name.
# `search_issues` carries `variables.filter`; `custom_view_create` carries
# `filter_data`, `project_filter_data`, `initiative_filter_data` and
# `feed_item_filter_data` a level deeper. Matching the literal `filter` left that
# one tool at 193KB - the single tool in the pack that would still have taken
# down any run whose model happened to load it.
#
# Every other fat tool measured here is wide but finite - gcalendar's events
# (34KB, 21 defs), gdocs' batch update (33KB, 51), gsheets' (195KB, 201),
# notion's blocks (66KB, 73) - and is left alone. Width is not the problem;
# recursion is.
#
# A projection can only ever remove, so this narrows what the model may ask for
# and never widens it.
RECURSIVE_FIELD: dict[str, str] = {"linear": "filter"}

# Only tools whose schema is actually large are projected. Deriving is not free,
# and 111 of Linear's 128 tools are small enough that the recursion never reaches
# them - narrowing those would remove arguments for no gain.
_PROJECT_OVER_BYTES = 50_000

_PROJECTED: dict[str, list[Tool]] = {}


def _inner(annotation: Any) -> Any:
    """``Optional[X]`` / ``list[X]`` -> ``X``, as far as it goes."""
    if get_origin(annotation) is Union:
        rest = [a for a in get_args(annotation) if a is not type(None)]
        if rest:
            return _inner(rest[0])
    if get_origin(annotation) is list:
        if args := get_args(annotation):
            return _inner(args[0])
    return annotation


def recursive_paths(schema: type[BaseModel], marker: str, *, max_depth: int = 4) -> set[str]:
    """Dotted paths to the shallowest fields whose names carry ``marker``.

    Shallowest, because dropping a parent takes its children with it and naming a
    path that is already gone raises.

    Walked over the request model rather than the generated JSON schema, for two
    reasons that both cost a debugging round to find. The JSON schema carries
    *wire* names - ``filterData``, not ``filter_data`` - and a projection selects
    on field names, so paths read off it are rejected as fields of no model. And
    generating it is the expensive step this is trying to stay cheap enough to
    run on every tool.

    Breadth-first with one global ``seen`` set, so a model reached from two
    places is walked at its shallowest reach and never twice. That guard is the
    whole cost difference: :func:`charter.derive.schema_paths` re-expands a model
    once per branch that reaches it, which on Linear's mutually referential
    filters is 2.3 million paths and ten seconds per tool.
    """
    marker = marker.lower()
    level: list[tuple[str, Any]] = [("", schema)]
    seen: set[int] = {id(schema)}
    for _ in range(max_depth):
        hits: set[str] = set()
        nxt: list[tuple[str, Any]] = []
        for prefix, model in level:
            for name, field in model.model_fields.items():
                path = f"{prefix}.{name}" if prefix else name
                if marker in name.lower():
                    hits.add(path)
                    continue
                nested = _inner(field.annotation)
                if (
                    isinstance(nested, type)
                    and issubclass(nested, BaseModel)
                    and id(nested) not in seen
                ):
                    seen.add(id(nested))
                    nxt.append((path, nested))
        if hits:
            return hits
        if not nxt:
            break
        level = nxt
    return set()


def pack_tools(pack: str) -> list[Tool]:
    """The tools of one pack minus the withheld ones, with the ledger sink attached."""
    if (cached := _PROJECTED.get(pack)) is not None:
        return cached
    module = importlib.import_module(f"charter.packs.{pack}")
    marker = RECURSIVE_FIELD.get(pack)
    tools: list[Tool] = []
    for tool in module.TOOLS:
        if (pack, tool.name) in EXCLUDED_TOOLS:
            continue
        # Candidates first, size second: the size check generates the schema, and
        # that is the ten-second step. 111 of Linear's 128 tools never name a
        # filter at all and never pay for it.
        if marker and (paths := recursive_paths(tool.args_schema, marker)):
            if len(json.dumps(tool.to_json_schema()["parameters"])) > _PROJECT_OVER_BYTES:
                try:
                    tool = tool.derived(name=tool.name, drop=paths)
                except CharterError:
                    pass  # a required field: the tool keeps its full schema
        tool.on_call = record_charter_call
        tools.append(tool)
    _PROJECTED[pack] = tools
    return tools


def model_facing_names(packs: Sequence[str]) -> dict[tuple[str, str], str]:
    """(pack, tool) -> the name the model sees: ``<pack>__<tool>``, always.

    Always qualified, via :func:`charter.qualified_names` — the harness is the
    surface that assembles several packs into one namespace, which is the layer
    that owns qualification. A scenario drawing on one pack still gets qualified
    names here, unlike an adapter's :func:`~charter.naming.resolve_names`,
    because the arms must name a tool the same way whatever else is loaded: the
    guard's index and every recorded call are keyed on that name.
    """
    from charter import qualified_names

    return {
        (tool.pack or pack, tool.name): name
        for pack in packs
        for name, tool in qualified_names(pack_tools(pack)).items()
    }


class CharterArm:
    name = "charter"

    def tools(self, packs: Sequence[str], wiring: Wiring) -> list[ToolDef]:
        names = model_facing_names(packs)
        defs: list[ToolDef] = []
        index: dict[str, list[str]] = {}
        for pack in packs:
            for tool in pack_tools(pack):
                shown = names[(pack, tool.name)]
                defs.append(charter_tooldef(tool, name=shown))
                index[shown] = [pack, tool.name]
        ctx = run_context()
        ctx.arm = self.name
        ctx.tool_index = index
        return defs


register(CharterArm())
