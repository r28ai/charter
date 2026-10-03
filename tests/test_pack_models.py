"""Importing a pack builds none of its models; using one builds it.

Each check runs in a fresh interpreter, because whether a model is built depends
on everything the process did before — and the rest of the suite validates
plenty.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from pydantic import BaseModel, Field

from charter.types.model import DEFERRED, PackModel, fields_resolved, resolve_forward_refs

pytestmark = pytest.mark.skipif(not DEFERRED, reason="this pydantic builds models at definition")


def _fresh(code: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


def test_importing_a_pack_builds_none_of_its_models():
    """Stripe declares no forward references, so nothing in it has a reason to build."""
    result = _fresh(
        "import json, pydantic, charter.packs.stripe as s, charter.packs.stripe.types as t\n"
        "models = [c for c in vars(t).values() if isinstance(c, type)"
        " and issubclass(c, pydantic.BaseModel) and c.__module__.startswith('charter.packs.stripe')]\n"
        "print(json.dumps({'models': len(models), 'built': sum(c.__pydantic_complete__ for c in models)}))"
    )
    assert result["models"] > 50
    assert result["built"] == 0


def test_a_recursive_module_builds_only_what_it_must_and_still_validates():
    """Linear's filters rebuilt all 61 models at import, each regenerating the cycle.

    Only the ones whose fields did not resolve at definition need it, and the rest
    still validate a nested filter once something uses them.
    """
    result = _fresh(
        "import json\n"
        "import charter.packs.linear.types.filters as f\n"
        "import pydantic\n"
        "models = [c for c in vars(f).values() if isinstance(c, type)"
        " and issubclass(c, pydantic.BaseModel) and c.__module__ == f.__name__]\n"
        "built = sum(c.__pydantic_complete__ for c in models)\n"
        "resolved = all(c.__pydantic_complete__ or c.__pydantic_fields_complete__ for c in models)\n"
        "f.IssueFilter.model_validate({'and': [{'team': {'issues': {'some': {'title': {'eq': 'x'}}}}}]})\n"
        "print(json.dumps({'models': len(models), 'built': built, 'resolved': resolved}))"
    )
    assert result["resolved"], "a filter model was left with unresolved fields"
    assert result["built"] < result["models"], "every filter model was built at import"


def test_resolve_forward_refs_leaves_a_resolved_model_deferred():
    class Leaf(PackModel):
        value: int = Field(0, description="A value.")

    class Holder(PackModel):
        later: Later = Field(..., description="Defined afterwards.")  # noqa: F821

    class Later(PackModel):
        n: int = 0

    assert fields_resolved(Leaf) and not Leaf.__pydantic_complete__
    assert not fields_resolved(Holder)

    resolve_forward_refs(Leaf, Holder)

    assert not Leaf.__pydantic_complete__, "a resolved model was built anyway"
    assert Holder.__pydantic_complete__
    assert Holder.model_validate({"later": {"n": 2}}).later.n == 2


def test_a_plain_model_counts_as_resolved_once_built():
    class Plain(BaseModel):
        value: int = 0

    assert fields_resolved(Plain)


def test_resolve_forward_refs_rebuilds_dependencies_first_and_only_what_it_was_given():
    """Rebuilt parent-first, each rebuild regenerated its children; children first, it reuses them."""
    order = []

    class Parent(PackModel):
        child: Child = Field(..., description="Defined afterwards.")  # noqa: F821

    class Child(PackModel):
        grandchild: Grandchild = Field(..., description="Defined afterwards.")  # noqa: F821

    class Grandchild(PackModel):
        n: int = 0

    class Unrelated(PackModel):
        child: Child = Field(..., description="Not passed in.")

    for model in (Parent, Child):
        original = model.model_rebuild

        def recording(*args, _model=model, _original=original, **kwargs):
            order.append(_model.__name__)
            # One frame deeper than the helper expects: look one further up.
            kwargs["_parent_namespace_depth"] = kwargs.get("_parent_namespace_depth", 2) + 1
            return _original(*args, **kwargs)

        model.model_rebuild = recording  # type: ignore[method-assign]

    resolve_forward_refs(Parent, Child, Grandchild)

    assert order == ["Child", "Parent"]
    assert Parent.model_validate({"child": {"grandchild": {"n": 3}}}).child.grandchild.n == 3
    assert not Unrelated.__pydantic_complete__, "a model it was not given was built"
