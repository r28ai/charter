# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
``PackModel``, the base of every model a pack declares: built on first use.

Pydantic builds a model's validator when its class statement runs, so importing
a pack built every model in it, used or not. That was most of a pack's import
time — 5.2s of the 5.9s the engineering family took to serve its first tool
list, for 59 of the 550 tools the packs declare — and an MCP client that starts
its turn while servers are still starting (Codex does) saw no tools at all.

Deferred, a class statement only collects its fields, and the validator is built
the first time anything validates, serializes or asks for a JSON schema. What a
model *declares* is unchanged; only when pydantic does the work moves.

Deferral needs pydantic to say whether a model's fields resolved without
building it, which ``__pydantic_fields_complete__`` does from 2.11. On an older
pydantic models build eagerly, as before.

A forward reference still has to be resolved once every class it names exists,
and :func:`resolve_forward_refs` is the call for that: it rebuilds only a model
whose fields did not resolve, where ``model_rebuild()`` on a deferred model would
build it in full. That difference is the point in a recursive module. Linear's
filters rebuilt 61 models, each regenerating the whole cycle; 40 of them need it.
"""

from __future__ import annotations

import re
import typing
from typing import Any, Dict, List, Sequence, Set

from pydantic import BaseModel, ConfigDict

__all__ = ["DEFERRED", "PackModel", "fields_resolved", "resolve_forward_refs"]

# Whether this pydantic can report resolved fields apart from a built model.
DEFERRED: bool = hasattr(BaseModel, "__pydantic_fields_complete__")


class PackModel(BaseModel):
    """A pack's model: fields collected at definition, validator built on first use."""

    model_config = ConfigDict(defer_build=DEFERRED)


def fields_resolved(model: Any) -> bool:
    """Whether every annotation ``model`` declares names something in scope.

    A built model has resolved fields by definition; a deferred one says so
    itself. Both only ever go from False to True.
    """
    return bool(
        getattr(model, "__pydantic_complete__", True)
        or getattr(model, "__pydantic_fields_complete__", False)
    )


def resolve_forward_refs(*models: type[BaseModel]) -> None:
    """Resolve each model's forward references, now that what they name exists.

    For a module whose models refer to classes defined after them — the call
    that would otherwise be ``model_rebuild()``. Pass every model at once. A
    model whose fields already resolved is left deferred, and the rest are
    rebuilt dependencies first: a rebuild reuses the models already built and
    regenerates the ones that are not, so the order is the cost. Sheets' 57
    unresolved models took 0.94s rebuilt in the module's alphabetical order and
    0.22s this way. Only models passed here are ever rebuilt.

    Names resolve where this is called from, as they would for a direct
    ``model_rebuild()``: pydantic reads the namespace of the frame it is called
    from, which here would otherwise be this function's.
    """
    for model in _dependencies_first(models):
        if not fields_resolved(model):
            model.model_rebuild(_parent_namespace_depth=3)


def _dependencies_first(models: Sequence[type[BaseModel]]) -> List[type[BaseModel]]:
    """``models``, each after the ones among them its fields name.

    Only the order is decided here, so a name it misreads costs time and never
    correctness: pydantic still resolves every annotation itself. An unresolved
    field is a ``ForwardRef`` whose text is searched for the models' names; a
    resolved one is walked for the classes it holds. In a cycle, any order.
    """
    by_name: Dict[str, type[BaseModel]] = {model.__name__: model for model in models}
    word = re.compile(r"[A-Za-z_]\w*")

    def named_by(model: type[BaseModel]) -> Set[type[BaseModel]]:
        found: Set[type[BaseModel]] = set()
        for field in model.model_fields.values():
            stack: List[Any] = [field.annotation]
            while stack:
                annotation = stack.pop()
                if isinstance(annotation, (str, typing.ForwardRef)):
                    text = annotation if isinstance(annotation, str) else annotation.__forward_arg__
                    found.update(by_name[n] for n in word.findall(text) if n in by_name)
                elif (
                    isinstance(annotation, type) and by_name.get(annotation.__name__) is annotation
                ):
                    found.add(annotation)
                else:
                    stack.extend(typing.get_args(annotation))
        found.discard(model)
        return found

    ordered: List[type[BaseModel]] = []
    seen: Set[type[BaseModel]] = set()
    for root in models:
        if root in seen:
            continue
        # Iterative post-order, so a deep graph cannot reach the recursion limit.
        seen.add(root)
        stack = [(root, iter(named_by(root)))]
        while stack:
            model, pending = stack[-1]
            child = next(pending, None)
            if child is None:
                stack.pop()
                ordered.append(model)
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(named_by(child))))
    return ordered
