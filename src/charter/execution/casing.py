# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Key-case conversion for the wire.

Schemas are written in snake_case; APIs rarely are. Keys are converted on the
way out, honouring the cascade:

    ``WireName`` > Field ``Case()`` > Schema ``__case__`` > Endpoint override > Factory default

Only *keys* are converted — values are passed through untouched.

Two ways in. :class:`DictKeyParser` converts a bare dict against one case, which
is all a payload with no schema behind it — a transformed body, a free-form
``Dict[str, Any]`` — can be given. :func:`key_plan` reads the cascade off a
model *graph* first, and :func:`convert_with_plan` then applies it at every
depth.

The second exists because the first cannot see past the top level. Once a model
is dumped to a dict, every marker on it is gone: a nested model's ``__case__``
and a nested field's ``Case()`` had nothing left to act on, so the two lowest
levels of the documented cascade were silently inert below the root — including
in the "Schema-level override (nested model)" example in
``docs/tools/key-case-cascade.md``, which described a conversion that did not
happen. ``WireName`` had been given a special case for the one shape that hurt
most (the unwrapped body), which fixed a third of the problem and left
``Case()`` on the field beside it still ignored. A plan built from the graph
answers all of it once.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, Union, get_args, get_origin
from weakref import WeakKeyDictionary

from pydantic import BaseModel

from charter.types.errors import DeclarationError
from charter.types.markers import Case, WireName

__all__ = ["DictKeyParser", "KeyPlan", "key_plan", "plan_for", "convert_with_plan"]

# Maps KeyCase values to converter functions (snake -> target).
# "snake" is identity (no conversion needed).
_CONVERTERS: Dict[str, Callable[[str], str]] = {}  # populated after class definition


class DictKeyParser:
    """Converts snake_case keys to camel/pascal/kebab, recursively."""

    @staticmethod
    def _snake2camel(snake_str: str) -> str:
        """Convert snake_case string to camelCase."""
        components = snake_str.split("_")
        return components[0] + "".join(x.capitalize() for x in components[1:])

    @staticmethod
    def _snake2pascal(snake_str: str) -> str:
        """Convert snake_case string to PascalCase."""
        return "".join(x.capitalize() for x in snake_str.split("_"))

    @staticmethod
    def _snake2kebab(snake_str: str) -> str:
        """Convert snake_case string to kebab-case."""
        return snake_str.replace("_", "-")

    @classmethod
    def convert_key(cls, key: str, case: str) -> str:
        """Convert a single snake_case key to the target case."""
        if case == "snake":
            return key
        converter = _CONVERTERS.get(case)
        if converter is None:
            raise DeclarationError(f"Unknown case: {case!r}", docs="tools/key-case-cascade")
        return converter(key)

    @classmethod
    def convert_keys_recursive(
        cls,
        data: dict,
        case: str,
        *,
        field_cases: Optional[Dict[str, str]] = None,
        schema_case: Optional[str] = None,
        wire_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Convert dictionary keys from snake_case to the target case.

        Supports per-field overrides via ``field_cases`` (field_name -> case) and
        schema-level overrides via ``schema_case``.

        Priority: ``wire_names[key]`` > ``field_cases[key]`` > ``schema_case`` >
        ``case`` (caller default). A wire name is not a convention, so it wins
        over all of them.

        Note that ``field_cases`` and ``schema_case`` apply at the top level only;
        nested dicts recurse with the plain ``case``. Field-level markers name a
        field on *this* schema, so they would be meaningless keyed against a
        nested object's field names.
        """
        if case == "snake" and not field_cases and not schema_case and not wire_names:
            return data

        effective_default = schema_case or case

        new_dict = {}
        for key, value in data.items():
            # Determine effective case for this key
            verbatim = (wire_names or {}).get(key)
            if verbatim is not None:
                new_key = verbatim
            else:
                effective_case = (field_cases or {}).get(key) or effective_default
                new_key = cls.convert_key(key, effective_case)
            if isinstance(value, dict):
                value = cls.convert_keys_recursive(value, case)
            elif isinstance(value, list):
                value = [
                    cls.convert_keys_recursive(item, case) if isinstance(item, dict) else item
                    for item in value
                ]
            new_dict[new_key] = value
        return new_dict


_CONVERTERS.update(
    {
        "camel": DictKeyParser._snake2camel,
        "pascal": DictKeyParser._snake2pascal,
        "kebab": DictKeyParser._snake2kebab,
    }
)


# -----------------------------------------------------
# The cascade, read off a model graph
# -----------------------------------------------------


class KeyPlan:
    """How one model's keys are spelled, and how its nested models' keys are.

    ``keys`` is the answer for every field this model declares, already resolved
    through the whole cascade, so applying it is a lookup rather than a decision.
    ``case`` covers keys that are not fields of this model at all — what a
    ``Format`` transform produced, or a free-form ``Dict[str, Any]``. ``default``
    is the endpoint's own case, carried down for the same reason: ``__case__``
    says "all keys in *that model*", so it governs that model's fields and
    nothing underneath them.

    ``wildcard`` marks a level whose keys are *data* rather than field names —
    a ``Dict[str, Item]``, where the keys were chosen by whoever filled the
    request in. Nothing there can be looked up, so the keys take ``case`` and
    every value takes the wildcard plan. Without this the item model's plan was
    applied one level too high: a map key that happened to match one of the
    item's field names got that field's ``WireName`` or ``Case``, and the
    values below — the actual ``Item``s — got no plan at all, which is the same
    defect this file exists to fix, one container further in.
    """

    __slots__ = ("case", "default", "keys", "nested", "wildcard")

    def __init__(self, case: str, default: str) -> None:
        self.case = case
        self.default = default
        self.keys: Dict[str, str] = {}
        self.nested: Dict[str, KeyPlan] = {}
        self.wildcard: Optional[KeyPlan] = None


_CONFLICT = object()

# Plans already built, by model and endpoint case.
#
# Building one walks the whole type graph, and the wire layer asks for a body
# plan and a query plan on every single request — about 1.4ms each on a schema
# the size of `linear.issues_list`, which would be pure per-call CPU added to a
# path that was previously linear in the *payload* rather than in the schema.
# A plan is derived from class declarations, which do not change, so it is built
# once and kept.
#
# Weak on the key, so a plan lives exactly as long as the model it describes:
# the views are generated classes owned by a `Tool`, and a strong map would pin
# every one ever built for the life of the process. Two threads racing a cold
# entry both build and one wins, which costs a duplicated walk and never a wrong
# answer — the loser's plan is equal to the winner's, and neither is published
# before it is complete.
_PLANS: WeakKeyDictionary[type, Dict[str, KeyPlan]] = WeakKeyDictionary()


def plan_for(
    annotation: Any,
    default_case: str,
    *,
    _memo: Optional[Dict[Any, KeyPlan]] = None,
) -> Optional[KeyPlan]:
    """The plan for whatever sits *at* this annotation's position, or ``None``.

    ``None`` means "no declaration to read here" — a scalar, a ``Dict[str, Any]``
    — and the caller falls back to plain case conversion, which is what those
    keys always got.

    Containers are resolved structurally rather than by collecting the models
    they happen to contain, because where a plan applies depends on the
    container. A ``List[Item]`` applies ``Item``'s plan to each element, so the
    list and the element share one; a ``Dict[str, Item]`` does not, because the
    mapping's own keys belong to nobody. Collecting models and ignoring the
    shape around them conflated the two.

    Annotations are finite trees, so this terminates on its own; model cycles
    are :func:`key_plan`'s to handle, and it does.
    """
    origin = get_origin(annotation)

    if origin is Union:
        parts = [
            resolved
            for arg in get_args(annotation)
            if arg is not type(None)
            for resolved in (plan_for(arg, default_case, _memo=_memo),)
            if resolved is not None
        ]
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else _merge(parts)

    if origin in (list, set, tuple, frozenset):
        args = [arg for arg in get_args(annotation) if arg is not Ellipsis]
        return plan_for(args[0], default_case, _memo=_memo) if args else None

    if origin is dict:
        args = get_args(annotation)
        inner = plan_for(args[1], default_case, _memo=_memo) if len(args) > 1 else None
        if inner is None:
            # Nothing declared below, so the whole subtree is plain conversion —
            # which is what it would get anyway. Say so with None rather than
            # building a wrapper that changes nothing.
            return None
        mapping = KeyPlan(default_case, default_case)
        mapping.wildcard = inner
        return mapping

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return key_plan(annotation, default_case, _memo=_memo)

    return None


def key_plan(
    model: Type[BaseModel],
    default_case: str,
    *,
    _memo: Optional[Dict[Any, KeyPlan]] = None,
) -> KeyPlan:
    """Resolve the key cascade for ``model`` and everything below it.

    Built once per (model, endpoint case) and kept — see :data:`_PLANS`. The
    per-walk memo is separate and is also what makes a self-referential schema
    terminate: the node joins it before its fields are walked, so a type that
    reaches itself reaches the same plan object rather than recursing forever.

    A field annotated with several models — a union — contributes a key only
    where they agree on it. Disagreement falls back to this level's case, which
    is the behaviour before any of this existed, and is the only answer that
    does not depend on which half of the union a given call happened to send.
    """
    is_root = _memo is None
    if is_root:
        try:
            built = _PLANS.get(model)
        except TypeError:  # pragma: no cover - a model that cannot be weak-referenced
            built = None
        if built is not None and default_case in built:
            return built[default_case]

    memo = _memo if _memo is not None else {}
    level_case = getattr(model, "__case__", None) or default_case
    cache_key = (id(model), default_case)
    cached = memo.get(cache_key)
    if cached is not None:
        return cached

    plan = KeyPlan(level_case, default_case)
    memo[cache_key] = plan

    for name, field in model.model_fields.items():
        wire = next((m.name for m in field.metadata if isinstance(m, WireName)), None)
        if wire is None:
            field_case = next((m.case for m in field.metadata if isinstance(m, Case)), None)
            wire = DictKeyParser.convert_key(name, field_case or level_case)
        plan.keys[name] = wire

        # The nested plan is built against the *endpoint* default, not this
        # level's case: `__case__` is scoped to the model that declares it.
        child = plan_for(field.annotation, default_case, _memo=memo)
        if child is not None:
            plan.nested[name] = child

    if is_root:
        # Published only now, with the whole graph below it built. A cyclic
        # schema's descendants already hold this object; nothing outside this
        # walk can reach it until here.
        try:
            _PLANS.setdefault(model, {})[default_case] = plan
        except TypeError:  # pragma: no cover - a model that cannot be weak-referenced
            pass

    return plan


def _merge(plans: List[KeyPlan]) -> KeyPlan:
    """One plan for a union of models, keeping only what they agree on."""
    merged = KeyPlan(plans[0].case, plans[0].default)
    first = plans[0].wildcard
    if all(plan.wildcard is first for plan in plans):
        merged.wildcard = first
    resolved: Dict[str, Any] = {}
    for plan in plans:
        for field, wire in plan.keys.items():
            if resolved.setdefault(field, wire) != wire:
                resolved[field] = _CONFLICT
        for field, child in plan.nested.items():
            merged.nested.setdefault(field, child)
    merged.keys = {f: w for f, w in resolved.items() if w is not _CONFLICT}
    return merged


def convert_with_plan(data: Any, plan: Optional[KeyPlan], case: str) -> Any:
    """Convert ``data``'s keys against ``plan``, recursing into what it covers.

    ``plan`` may be ``None``, which is what a payload with no schema behind it
    gets: the keys are converted against ``case`` and nothing else, exactly as
    :meth:`DictKeyParser.convert_keys_recursive` would. Below a field the plan
    does cover, the nested plan takes over — which is the whole point, and the
    thing a dict walked on its own cannot do.
    """
    if isinstance(data, list):
        return [convert_with_plan(item, plan, case) for item in data]
    if not isinstance(data, dict):
        return data
    if plan is None:
        return {
            DictKeyParser.convert_key(key, case): convert_with_plan(value, None, case)
            for key, value in data.items()
        }
    if plan.wildcard is not None:
        # These keys are data. Convert them the way an undeclared key is
        # converted, and hand every value the plan its model does have.
        return {
            DictKeyParser.convert_key(key, plan.case): convert_with_plan(
                value, plan.wildcard, plan.default
            )
            for key, value in data.items()
        }
    return {
        plan.keys.get(key) or DictKeyParser.convert_key(key, plan.case): convert_with_plan(
            value, plan.nested.get(key), plan.default
        )
        for key, value in data.items()
    }
