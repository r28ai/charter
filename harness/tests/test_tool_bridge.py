"""
Every pack tool the harness can hand a model must survive the trip into Inspect.

Offline. Nothing here touches a credential or the network: the bridge is a pure
projection of ``Tool.to_json_schema()``, and this pins that the projection loses
nothing a model needs — every declared property keeps a type, nested objects
keep their fields, and the withheld tools are really withheld.
"""

from __future__ import annotations

import importlib
import json

import pytest
import respx
from charter.packs import gmail, stripe
from httpx import Response
from inspect_ai.tool import ToolError
from inspect_ai.tool._tool_def import tool_def_fields

from charter_harness.arms.charter_arm import (
    EXCLUDED_TOOLS,
    CharterArm,
    charter_tooldef,
    normalize,
    pack_tools,
)
from charter_harness.arms.raw_arm import RawArm
from charter_harness.settings import PROVIDERS, Settings, Wiring

PACKS = sorted(PROVIDERS)
ALL_TOOLS = [(p, t) for p in PACKS for t in importlib.import_module(f"charter.packs.{p}").TOOLS]


def _ids(pair):
    pack, tool = pair
    return f"{pack}.{tool.name}"


def _typed(prop: dict, defs: dict | None = None) -> bool:
    """Whether the model can tell what this property accepts.

    A ``$ref`` counts, provided the definition it names is present. The bridge
    used to inline every reference, so a typed property meant a property with a
    ``type`` written on it; under pass-through the type is one hop away, which is
    the form the SDK emits and the provider resolves.
    """
    if ref := prop.get("$ref"):
        return ref.rsplit("/", 1)[-1] in (defs or {})
    return bool(prop.get("type") or prop.get("anyOf") or prop.get("enum"))


@pytest.mark.parametrize("pair", ALL_TOOLS, ids=_ids)
def test_every_tool_converts_with_every_property_typed(pair):
    pack, tool = pair
    tooldef = charter_tooldef(tool)
    assert tooldef.name == tool.name
    assert tooldef.description == tool.description
    original = tool.to_json_schema()["parameters"]
    assert set(tooldef.parameters.properties) == set(original.get("properties", {}))
    assert tooldef.parameters.required == list(original.get("required", []))
    defs = getattr(tooldef.parameters, "$defs", None) or {}
    for name, prop in tooldef.parameters.properties.items():
        assert _typed(prop.model_dump(exclude_none=True), defs), f"{tool.name}.{name} lost its type"
    # Inspect refuses, at generate time, any top-level parameter without a
    # description. Run its own check here so the refusal happens offline.
    tool_def_fields(tooldef.as_tool())


@pytest.mark.parametrize("pack", PACKS)
def test_raw_arm_tools_pass_inspect_validation(pack):
    wiring = Wiring(settings=Settings(shopify_shop="x.myshopify.com"))
    for tooldef in RawArm().tools([pack], wiring):
        tool_def_fields(tooldef.as_tool())
        assert tooldef.max_output == 0
        assert tooldef.description.count("\n- ") >= 1, (
            "the endpoint list must be derived, not empty"
        )


def test_nested_models_keep_their_fields():
    """The flagship case: EmailContent under drafts_create.body.message.raw.

    It is reached through ``$defs`` now rather than inlined in place, so the
    assertion follows the reference. What must not change is that the model can
    still see ``to``/``subject``/``body`` - that is what makes the pack's
    semantic-to-wire compilation visible rather than a base64 blob.
    """
    params = charter_tooldef(gmail.drafts_create).parameters.model_dump(exclude_none=True)
    defs = params.get("$defs", {})
    email = next(
        (d for n, d in defs.items() if {"to", "subject", "body"} <= set(d.get("properties", {}))),
        None,
    )
    assert email is not None, f"EmailContent not among $defs: {sorted(defs)}"
    assert email["type"] == "object"


def test_normalize_folds_what_inspect_lacks_and_keeps_refs():
    """``$ref``/``$defs`` reach the model untouched; only unsupported forms fold.

    The arm used to expand every reference. That is why a 188KB Linear tool
    became 115MB, and why the Charter arm was measured against a schema no SDK
    user is handed. Fireworks resolves ``$ref`` itself, so the references stay.
    """
    schema = {
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {"child": {"$ref": "#/$defs/Node"}, "name": {"type": "string"}},
            },
            "Kind": {"const": "a", "type": "string"},
        },
        "properties": {
            "root": {"$ref": "#/$defs/Node", "description": "the root"},
            "kind": {"$ref": "#/$defs/Kind"},
            "either": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        },
    }
    out = normalize(schema)
    # The definitions and the references that point at them both survive.
    assert out["$defs"]["Node"]["properties"]["child"] == {"$ref": "#/$defs/Node"}
    assert out["properties"]["root"] == {"$ref": "#/$defs/Node", "description": "the root"}
    # A cycle is no longer something to bottom out: nothing is expanded.
    assert out["$defs"]["Kind"]["enum"] == ["a"] and "const" not in out["$defs"]["Kind"]
    assert "anyOf" in out["properties"]["either"] and "oneOf" not in out["properties"]["either"]


def test_definitions_reach_the_tool_params():
    """A ``$ref`` with no ``$defs`` beside it is a schema the model cannot resolve."""
    params = charter_tooldef(gmail.drafts_create).parameters.model_dump(exclude_none=True)
    original = gmail.drafts_create.to_json_schema()["parameters"]
    if original.get("$defs"):
        assert set(params["$defs"]) == set(original["$defs"])
    for name, prop in params["properties"].items():
        if "$ref" in prop:
            assert prop["$ref"].rsplit("/", 1)[-1] in params["$defs"], name


_SCALARS = ("string", "integer", "number", "boolean", "null")


def _scalar_leaves(node, path=""):
    """Every scalar leaf in a schema document, wherever it is declared.

    Walks ``$defs`` as well as ``properties`` and resolves nothing. Expanding to
    compare would rebuild the blow-up the bridge exists to avoid: naively
    inlining Linear's 77 mutually recursive definitions produces 115MB, which is
    what made this suite take half an hour to run.
    """
    if not isinstance(node, dict):
        return
    if node.get("type") in _SCALARS and "properties" not in node:
        yield path, node["type"]
    for key in ("properties", "$defs"):
        for name, child in (node.get(key) or {}).items():
            yield from _scalar_leaves(child, f"{path}.{name}")
    if "items" in node:
        yield from _scalar_leaves(node["items"], f"{path}[]")
    for i, child in enumerate(node.get("anyOf") or node.get("oneOf") or []):
        yield from _scalar_leaves(child, f"{path}|{i}")


@pytest.mark.parametrize("pair", ALL_TOOLS, ids=_ids)
def test_deep_fields_keep_their_scalar_types(pair):
    """Regression: the inliner once cut everything past a dozen dict levels to a bare
    object, so ``issues_list.variables.filter.team.key.eq`` reached the model typed
    as ``object`` and the model dutifully sent objects. Every leaf the pack declares
    as a scalar must still be a scalar after the bridge, at any depth.

    Under pass-through the depth is in ``$defs`` rather than in the properties
    tree, so both sides are walked as documents and a reference is followed by
    neither. What is pinned is that no declared scalar is lost or retyped."""
    pack, tool = pair
    original = tool.to_json_schema()["parameters"]
    bridged = charter_tooldef(tool).parameters.model_dump(exclude_none=True)
    got = dict(_scalar_leaves(bridged))
    lost = {p: (t, got.get(p)) for p, t in _scalar_leaves(original) if got.get(p) != t}
    assert not lost, f"{pack}.{tool.name}: scalar leaves degraded: {dict(list(lost.items())[:5])}"


def test_the_linear_filter_comparators_are_strings():
    """The concrete case from the phase-1 logs, followed through ``$defs``.

    ``team.key.eq`` is a string. It reached the model as an object once, because
    the inliner truncated at depth and the model sent objects to match. The path
    is now three references deep rather than three dicts deep, so the test
    follows them; what it pins is unchanged."""
    from charter.packs import linear

    params = charter_tooldef(
        next(t for t in linear.TOOLS if t.name == "issues_list")
    ).parameters.model_dump(exclude_none=True)
    defs = params["$defs"]

    def deref(node):
        """Past a nullable ``anyOf`` wrapper and one reference, to the definition."""
        if "anyOf" in node:
            node = next(o for o in node["anyOf"] if o.get("type") != "null")
        return defs[node["$ref"].rsplit("/", 1)[-1]]

    # The pack narrows `issues_list`'s filter, so the team condition arrives as
    # `TeamFilter_LLM` with the two comparators a list is narrowed by. The
    # property under test - a comparator is a string, not an object - is the
    # same one, on the fields that survive the projection.
    team = defs["TeamFilter_LLM"]["properties"]
    for comparator in ("key", "name"):
        eq = deref(team[comparator])["properties"]["eq"]
        assert {o.get("type") for o in eq["anyOf"]} == {"string", "null"}, (
            f"team.{comparator}.eq is {eq}"
        )


def test_withheld_tools_never_reach_the_model():
    for pack, name in EXCLUDED_TOOLS:
        assert name not in {t.name for t in pack_tools(pack)}
    names = {d.name for d in CharterArm().tools(["gmail", "slack"], Wiring(settings=Settings()))}
    # Qualified as <pack>__<tool>, so assert on the qualified name: a bare
    # "messages_send" is absent from this set whether or not it is withheld,
    # which would make the check pass for the wrong reason.
    assert "gmail__messages_send" not in names
    assert "slack__search_messages" not in names
    assert "gmail__drafts_create" in names and "slack__chat_post_message" in names


def test_inspect_truncation_is_disabled_on_every_tooldef():
    assert all(charter_tooldef(t).max_output == 0 for _, t in ALL_TOOLS)


@respx.mock
async def test_a_charter_error_becomes_a_tool_error_the_model_can_read():
    stripe.configure(api_key="sk_test_x")
    respx.get("https://api.stripe.com/v1/customers/cus_missing").mock(
        return_value=Response(404, json={"error": {"message": "No such customer"}})
    )
    tooldef = charter_tooldef(stripe.customers_retrieve)
    with pytest.raises(ToolError) as excinfo:
        await tooldef.tool(customer="cus_missing")
    assert "404" in str(excinfo.value)


async def test_validation_failures_do_not_reach_the_network():
    tooldef = charter_tooldef(stripe.customers_retrieve)
    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://api.stripe.com/v1/customers/").mock(return_value=Response(200))
        with pytest.raises(ToolError):
            await tooldef.tool()  # missing the required `customer`
        assert not mock.calls


@respx.mock
async def test_a_successful_call_returns_json_text():
    """What the model receives is the pack's trimmed view, rendered as JSON text.

    Asserted on a bucket rather than on ``object``: ``trim_balance`` drops
    ``object`` and ``livemode`` by design, so pinning those would pin the absence
    of the trimming this arm exists to measure."""
    stripe.configure(api_key="sk_test_x")
    respx.get("https://api.stripe.com/v1/balance").mock(
        return_value=Response(
            200,
            json={
                "object": "balance",
                "livemode": False,
                "available": [{"amount": 1200, "currency": "usd", "source_types": {"card": 1200}}],
            },
        )
    )
    tooldef = charter_tooldef(stripe.balance_retrieve)
    out = await tooldef.tool()
    payload = json.loads(out)
    assert payload["available"] == [{"amount": 1200, "currency": "usd"}]
    assert "object" not in payload and "livemode" not in payload
