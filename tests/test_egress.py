"""Egress control — the audit artifact, and the guarantee behind it."""

from __future__ import annotations

import json
from typing import Annotated, Dict, List, Optional

import pytest
from pydantic import BaseModel

from charter import Body, Mode, Path, Query
from charter.egress import egress_map, format_egress_map
from charter.packs import (
    firecrawl,
    gcalendar,
    gmail,
    gsheets,
    notion,
    slack,
    stripe,
)

ALL_PACKS = [gmail, gcalendar, gsheets, slack, stripe, firecrawl, notion]


class Inner(BaseModel):
    shown: Annotated[Optional[str], Body()] = None
    hidden: Annotated[Optional[str], Body(), Mode("response_only")] = None
    never: Annotated[Optional[str], Body(), Mode("disabled")] = None


class Outer(BaseModel):
    user_id: Annotated[str, Path()] = "me"
    nested: Annotated[Optional[Inner], Body()] = None
    dropped: Annotated[Optional[Inner], Body(), Mode("response_only")] = None


def _tool(**kw):
    from charter import Tool

    base = dict(
        name="t",
        method="POST",
        url_template="v1/{user_id}",
        args_schema=Outer,
        base_url="https://api.example.com/",
        api_key_headers={"x-api-key": "k"},
    )
    base.update(kw)
    return Tool(**base)


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_egress_map_splits_visible_from_withheld():
    entry = egress_map([_tool()])["t"]
    assert "user_id" in entry["visible"]
    assert "nested" in entry["visible"]
    assert "nested.shown" in entry["visible"]

    withheld = {w["field"]: w["reason"] for w in entry["withheld"]}
    assert withheld["nested.hidden"] == "response_only"
    assert withheld["nested.never"] == "disabled"
    assert withheld["dropped"] == "response_only"


def test_a_withheld_subtree_is_not_walked_into():
    """A response_only parent hides its children by hiding itself."""
    entry = egress_map([_tool()])["t"]
    assert not any(f.startswith("dropped.") for f in entry["visible"])


def test_visible_and_withheld_never_overlap():
    entry = egress_map([_tool()])["t"]
    withheld = {w["field"] for w in entry["withheld"]}
    assert not (set(entry["visible"]) & withheld)


def test_entry_carries_the_routing_facts_an_auditor_wants():
    entry = egress_map([_tool(provider="google", mode="create")])["t"]
    assert entry["provider"] == "google"
    assert entry["method"] == "POST"
    assert entry["url_template"] == "v1/{user_id}"
    assert entry["mode"] == "create"


def test_report_is_json_serialisable():
    """It is an audit artifact; it has to leave the process."""
    json.dumps(egress_map(gmail.TOOLS))


def test_self_referential_schema_terminates():
    class Node(BaseModel):
        name: Annotated[str, Body()]
        child: Annotated[Optional[Node], Body()] = None

    Node.model_rebuild()
    entry = egress_map([_tool(args_schema=Node)])["t"]
    assert "name" in entry["visible"]


# -----------------------------------------------------
# The guarantee it documents
# -----------------------------------------------------


def test_withheld_fields_are_absent_from_the_llm_schema():
    """The map is not a separate opinion — it reports the type the model gets."""
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            top_level = set(tool.llm_schema().model_fields)
            for item in report[tool.name]["withheld"]:
                if "." not in item["field"]:
                    assert item["field"] not in top_level, (
                        f"{tool.name}: {item['field']} reported withheld but present "
                        "in the LLM schema"
                    )


def test_every_visible_top_level_field_is_in_the_llm_schema():
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            top_level = set(tool.llm_schema().model_fields)
            for field in report[tool.name]["visible"]:
                if "." not in field:
                    assert field in top_level


def test_gmail_send_withholds_the_entire_mime_tree():
    """The flagship case: Gmail returns payload, and never accepts it."""
    entry = egress_map(gmail.TOOLS)["messages_send"]
    withheld = {w["field"] for w in entry["withheld"]}

    assert "body.payload" in withheld
    assert "body.id" in withheld
    assert "body.raw" in entry["visible"]
    # The model sees a handful of fields, not the whole resource.
    assert len(entry["visible"]) < len(entry["withheld"])


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_every_shipped_tool_has_an_egress_entry(pack):
    report = egress_map(pack.TOOLS)
    assert set(report) == {t.name for t in pack.TOOLS}
    for name, entry in report.items():
        assert isinstance(entry["visible"], list)
        assert isinstance(entry["withheld"], list)
        # A parameterless endpoint is legitimate (Stripe GET /v1/balance takes
        # nothing), so an empty visible list is not an error — but it must then
        # withhold nothing either, or the map is describing a field that vanished.
        if not entry["visible"]:
            assert not entry["withheld"], f"{name} withholds fields but exposes none"


# -----------------------------------------------------
# Rendering
# -----------------------------------------------------


def test_format_egress_map_is_readable():
    text = format_egress_map([gmail.messages_send])
    assert "messages_send" in text
    assert "visible to the model" in text
    assert "withheld" in text
    assert "[response_only]" in text


def test_query_and_path_fields_are_reported_too():
    class Mixed(BaseModel):
        city: Annotated[str, Path()]
        units: Annotated[Optional[str], Query()] = None
        secret: Annotated[Optional[str], Query(), Mode("disabled")] = None

    entry = egress_map([_tool(args_schema=Mixed, url_template="v1/{city}")])["t"]
    assert {"city", "units"} <= set(entry["visible"])
    assert "secret" in {w["field"] for w in entry["withheld"]}


def test_lists_of_nested_models_are_walked():
    class Item(BaseModel):
        ok: Annotated[Optional[str], Body()] = None
        no: Annotated[Optional[str], Body(), Mode("response_only")] = None

    class Holder(BaseModel):
        items: Annotated[Optional[List[Item]], Body()] = None

    entry = egress_map([_tool(args_schema=Holder)])["t"]
    assert "items.ok" in entry["visible"]
    assert "items.no" in {w["field"] for w in entry["withheld"]}


def test_models_reached_as_a_dict_value_are_walked():
    """A map of name to model is still a model, and Mode still applies inside it.

    ``create_llm_schema`` walked nested models and lists of them, and copied a
    ``Dict[str, Model]`` across whole — so every ``response_only`` field under
    one was offered to the model. Notion's page ``properties`` is that shape, and
    a third of its value types are computed by the server and rejected on write.
    """

    class Value(BaseModel):
        ok: Annotated[Optional[str], Body()] = None
        computed: Annotated[Optional[str], Body(), Mode("response_only")] = None

    class Holder(BaseModel):
        properties: Annotated[Optional[Dict[str, Value]], Body()] = None

    entry = egress_map([_tool(args_schema=Holder)])["t"]
    assert "properties.ok" in entry["visible"]
    assert "properties.computed" in {w["field"] for w in entry["withheld"]}
