"""Egress control — the audit artifact, and the guarantee behind it."""

from __future__ import annotations

import json
from typing import Annotated, Dict, List, Optional, Union

import pytest
from pydantic import BaseModel

from charter import Body, Mode, Path, Query, ToolSession, report_key
from charter.egress import _MAX_DEPTH, _members, _unwrap, egress_map, format_egress_map
from charter.packs import (
    firecrawl,
    gcalendar,
    gdocs,
    gdrive,
    gforms,
    github,
    gmail,
    granola,
    gsheets,
    linear,
    notion,
    shopify,
    slack,
    stripe,
    tavily,
)
from charter.types.errors import DeclarationError

# Every shipped pack, not a sample of them. The round-trip checks below are the
# only thing standing between a declaration and what a model is handed, and the
# seven packs this used to name happened to exclude the one whose self-referential
# `OutputSchemaProperty` the two walks still stop on at different depths.
ALL_PACKS = [
    firecrawl,
    gcalendar,
    gdocs,
    gdrive,
    gforms,
    github,
    gmail,
    granola,
    gsheets,
    linear,
    notion,
    shopify,
    slack,
    stripe,
    tavily,
]


class Draft(BaseModel):
    draft_field: Annotated[Optional[str], Body()] = None


class Published(BaseModel):
    published_field: Annotated[Optional[str], Body()] = None


class Risky(BaseModel):
    b: Annotated[Optional[str], Body()] = None
    hidden: Annotated[Optional[str], Body(), Mode("response_only")] = None


class EitherSafe(BaseModel):
    either: Annotated[Optional[Union[Draft, Published]], Body()] = None


class EitherRisky(BaseModel):
    either: Annotated[Optional[Union[Draft, Risky]], Body()] = None


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


def emitted_paths(model, prefix="", seen=frozenset(), depth=0, out=None):
    """Every dotted path in a *built* LLM view.

    The map enumerates paths by walking the source schema; this enumerates them
    by walking the model Pydantic actually generated. Comparing the two is the
    round trip, and it means something only if both stop in the same places —
    so the depth bound and the per-branch cycle set here are :func:`_walk`'s,
    not a second opinion about where a walk should end.

    Checking only the top level, which is what these two tests did until a
    review walked the rest, is the one shape that cannot fail: every hole found
    so far was a container the two walks disagreed about, and a container is
    never at depth 0.
    """
    if out is None:
        out = set()
    if depth > _MAX_DEPTH or id(model) in seen:
        return out
    seen = seen | {id(model)}
    for name, field in model.model_fields.items():
        path = f"{prefix}{name}"
        out.add(path)
        nested = _unwrap(field.annotation)
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            emitted_paths(nested, f"{path}.", seen, depth + 1, out)
        # A union the builder kept whole offers every member's fields.
        for member in _members(nested):
            emitted_paths(member, f"{path}.", seen, depth + 1, out)
    return out


def test_withheld_fields_are_absent_from_the_llm_schema():
    """The map is not a separate opinion — it reports the type the model gets."""
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            offered = emitted_paths(tool.llm_schema())
            withheld = {item["field"] for item in report[report_key(tool)]["withheld"]}
            assert not (withheld & offered), (
                f"{tool.name}: {sorted(withheld & offered)[:5]} reported withheld "
                "but present in the LLM schema"
            )


def test_every_visible_field_is_in_the_llm_schema():
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            offered = emitted_paths(tool.llm_schema())
            visible = set(report[report_key(tool)]["visible"])
            assert visible <= offered, (
                f"{tool.name}: {sorted(visible - offered)[:5]} reported visible "
                "and absent from the type the model gets"
            )


def test_the_map_names_every_field_the_model_is_offered():
    """Neither half of the round trip on its own says the map is complete.

    "Nothing withheld is offered" and "nothing visible is missing" both hold of
    a map that simply stops early — which is what it did wherever a `Format`
    field retyped a subtree, since the map walked the wire type and the model
    was handed the semantic one. The set the model can fill in has to be the
    set the map lists, in both directions.
    """
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            entry = report[report_key(tool)]
            offered = emitted_paths(tool.llm_schema())
            missing = offered - set(entry["visible"])
            assert not missing, (
                f"{tool.name}: {sorted(missing)[:5]} handed to the model and named "
                "nowhere in the map"
            )


def test_gmail_send_withholds_the_entire_mime_tree():
    """The flagship case: Gmail returns payload, and never accepts it."""
    entry = egress_map(gmail.TOOLS)["gmail__messages_send"]
    withheld = {w["field"] for w in entry["withheld"]}

    visible = set(entry["visible"])

    assert "body.payload" in withheld
    assert "body.id" in withheld
    assert "body.raw" in visible

    # `raw` is a `Format` field: the model is offered an `EmailContent`, not the
    # base64 MIME string the API takes, and the map names that subtree because
    # the model can fill in every field of it.
    assert {"body.raw.to", "body.raw.subject", "body.raw.body"} <= visible

    # The message *resource* is what is withheld, and the handful of fields the
    # model gets is the send surface plus that email. Counting the two sides
    # against each other used to stand in for this, and it only ever passed
    # because the eleven `EmailContent` fields were missing from the visible
    # side — the map under-reporting its way into looking restrictive.
    resource = {f for f in visible if f.startswith("body.") and not f.startswith("body.raw")}
    assert resource == {"body.threadId"}, sorted(resource)


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_every_shipped_tool_has_an_egress_entry(pack):
    report = egress_map(pack.TOOLS)
    assert set(report) == {report_key(t) for t in pack.TOOLS}
    # One row per tool handed in, not one per name. A pack cannot collide
    # with itself, but the count is the assertion that nothing is dropped.
    assert len(report) == len(pack.TOOLS)
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


# -----------------------------------------------------
# The mode a deployment resolved
# -----------------------------------------------------


class Tiered(BaseModel):
    account_id: Annotated[str, Path()]
    raw_events: Annotated[Optional[str], Body(), Mode("pro, max")] = None
    model_weights: Annotated[Optional[str], Body(), Mode("max")] = None
    etag: Annotated[Optional[str], Body(), Mode("response_only")] = None


def _tiered(mode=None):
    from charter import Tool, ToolSession

    tool = Tool(
        name="reports_create",
        method="POST",
        url_template="v1/{account_id}",
        args_schema=Tiered,
        base_url="https://api.example.com/",
        api_key_headers={"x-api-key": "k"},
        pack="rep",
    )
    return list(ToolSession([tool], mode=mode, progressive=False).tools.values())


def test_the_map_reports_the_mode_the_session_resolved():
    """Otherwise the feature is not auditable, and so is not finished.

    The map is the artifact a security review reads, and it reads the same
    declarations the runtime executes. A session that narrows a surface and an
    audit that still reports the wide one is worse than no narrowing, because
    the review passes on a document describing a deployment that does not exist.
    """
    entry = egress_map(_tiered("pro"))["rep__reports_create"]
    assert entry["session_mode"] == "pro"
    assert entry["modes"] == ["pro"]
    assert entry["visible"] == ["account_id", "raw_events"]

    reasons = {w["field"]: w["reason"] for w in entry["withheld"]}
    assert reasons == {"model_weights": "mode=max", "etag": "response_only"}


def test_a_narrower_mode_withholds_more_and_says_which_label_did_it():
    entry = egress_map(_tiered("free"))["rep__reports_create"]
    assert entry["visible"] == ["account_id"]
    reasons = {w["field"]: w["reason"] for w in entry["withheld"]}
    assert reasons["raw_events"] == "mode=max,pro"
    assert reasons["model_weights"] == "mode=max"


def test_format_egress_map_renders_a_resolved_mode():
    text = format_egress_map(_tiered("pro"))
    assert "+ raw_events" in text
    assert "- model_weights  [mode=max]" in text
    assert "- etag  [response_only]" in text


def test_no_resolved_mode_widens_past_the_declaration():
    """Every label, including ones the author never wrote, and the floor holds."""
    for mode in (None, "free", "pro", "max", "response_only", "disabled", "whatever"):
        entry = egress_map(_tiered(mode))["rep__reports_create"]
        assert "etag" not in entry["visible"], f"mode={mode!r} widened egress"


def test_a_session_maps_straight_from_the_tools_it_holds():
    """The call the mode docs send a reviewer to has to be the call that works.

    `ToolSession.tools` is a dict keyed by the published name, and both audit
    maps took an iterable — so `egress_map(session.tools)` iterated the *keys*
    and died on `'str' object has no attribute 'pack'`, which names neither the
    mistake nor the fix. A surface assembled for one conversation is the thing
    worth auditing, so the map takes it in the shape a session holds it.
    """
    from charter.conflicts import conflict_map

    session = ToolSession(_tiered("pro"), mode="pro", progressive=False)

    from_map = egress_map(session.tools)
    from_list = egress_map(session.tools.values())
    assert from_map == from_list
    assert from_map["rep__reports_create"]["session_mode"] == "pro"

    # The mapping's own keys are discarded either way: a report is keyed by
    # `report_key`, so handing in a differently-keyed map cannot move a row.
    renamed = {f"row-{i}": t for i, t in enumerate(session.tools.values())}
    assert egress_map(renamed) == from_map

    # And the same for the other audit artifact, which has the same shape for
    # the same reason.
    assert conflict_map(session.tools) == conflict_map(list(session.tools.values()))


def test_the_map_cannot_drift_from_the_view_at_any_mode():
    """The two existing drift checks, run again once a mode is resolving.

    The map walks `args_schema` and the model is handed `llm_schema`, so they are
    two walks of the same declarations and nothing but agreement makes the map an
    audit artifact. A mode variant is a third thing that could disagree with
    either, and it is the one a deployment ships.
    """
    for pack in (gmail, gcalendar, stripe):
        for mode in (None, "write", "create", "update", "pro"):
            variants = [tool.with_mode(mode) for tool in pack.TOOLS]
            report = egress_map(variants)
            for tool in variants:
                entry = report[report_key(tool)]
                assert entry["session_mode"] == mode
                assert entry["mode"] == tool.mode, "the pack's own label was overwritten"
                assert entry["modes"] == sorted(tool.modes)
                offered = emitted_paths(tool.llm_schema())
                withheld = {w["field"] for w in entry["withheld"]}
                visible = set(entry["visible"])
                assert not (withheld & offered), (
                    f"{tool.name} at mode={mode!r}: {sorted(withheld & offered)} reported "
                    "withheld and handed to the model anyway"
                )
                assert visible <= offered, (
                    f"{tool.name} at mode={mode!r}: {sorted(visible - offered)} reported "
                    "visible and absent from the type the model gets"
                )


def test_a_mode_reaches_every_depth_and_stops_at_a_withheld_subtree():
    """Nested, inside a list, and cascaded onto children that carry no marker.

    Mode filtering is applied by one walk with the root's mode, so the shallow
    case passing says little about the deep one. A subtree the mode withholds is
    reported whole and not walked into, which is what keeps the map honest about
    a branch the model cannot reach at all.
    """

    class Leaf(BaseModel):
        always: Annotated[Optional[str], Body()] = None
        pro_only: Annotated[Optional[str], Body(), Mode("pro")] = None
        never: Annotated[Optional[str], Body(), Mode("response_only")] = None

    class Mid(BaseModel):
        leaf: Annotated[Optional[Leaf], Body()] = None
        leaves: Annotated[Optional[List[Leaf]], Body()] = None
        pro_subtree: Annotated[Optional[Leaf], Body(), Mode("pro")] = None

    class Root(BaseModel):
        user_id: Annotated[str, Path()] = "me"
        mid: Annotated[Optional[Mid], Body()] = None

    def at(mode):
        entry = egress_map([_tool(args_schema=Root).with_mode(mode)])["t"]
        return entry["visible"], {w["field"]: w["reason"] for w in entry["withheld"]}

    visible, withheld = at("free")
    assert "mid.leaf.always" in visible and "mid.leaves.always" in visible
    assert withheld["mid.leaf.pro_only"] == "mode=pro"
    assert withheld["mid.leaves.pro_only"] == "mode=pro"
    # Withheld whole, and not walked into: no child of it is reported either way.
    assert withheld["mid.pro_subtree"] == "mode=pro"
    assert not any(f.startswith("mid.pro_subtree.") for f in visible)

    visible, withheld = at("pro")
    assert "mid.leaf.pro_only" in visible and "mid.leaves.pro_only" in visible
    # The cascade: a child carrying no marker inherits the parent's label.
    assert "mid.pro_subtree.always" in visible

    # `response_only` is refused at every depth and at every label.
    for mode in (None, "free", "pro"):
        visible, withheld = at(mode)
        assert not any(f.endswith(".never") for f in visible)


# -----------------------------------------------------
# One row per tool
# -----------------------------------------------------


def test_a_surface_of_several_packs_keeps_every_tool():
    """The map keyed on the bare name and lost the tools that shared one.

    Across the fifteen shipped packs sixteen names collide: `comments_list`
    alone is declared by gdrive, linear and notion. Mapping one assembled
    surface produced 529 rows for 549 tools and named none of the twenty it
    dropped, which is the one failure an audit artifact must not have, because
    the reviewer cannot catch it by reading the artifact.
    """
    from charter.packs import gdrive, notion

    tools = [*gmail.TOOLS, *gdrive.TOOLS, *notion.TOOLS, *stripe.TOOLS]
    report = egress_map(tools)

    assert len(report) == len(tools)
    assert set(report) == {report_key(t) for t in tools}
    assert {"gdrive__comments_list", "notion__comments_list"} <= set(report)

    # Each row still says which tool it is without parsing the key apart.
    for key, entry in report.items():
        assert key.endswith(entry["name"])
        assert entry["pack"] and entry["pack"] in key


def test_two_tools_that_would_share_a_row_raise_rather_than_overwrite():
    """Silently keeping the second is how twenty rows went missing."""
    from charter import Tool

    def hand_built(name):
        return Tool(
            name=name,
            method="GET",
            url_template="v1/x",
            args_schema=Outer,
            base_url="https://api.example.com/",
            api_key_headers={"x-api-key": "k"},
        )

    # No pack to qualify with, so two of one name is the case nothing can resolve.
    with pytest.raises(DeclarationError, match="Two tools report under 'dup'"):
        egress_map([hand_built("dup"), hand_built("dup")])

    # Distinct names are fine, and a pack-less tool keeps its bare name.
    assert set(egress_map([hand_built("a"), hand_built("b")])) == {"a", "b"}


def test_a_pack_less_tool_is_still_mappable():
    """`qualified_name` refuses one; the report must not, or the artifact is out
    of reach of the hand-built tool the quickstart teaches."""
    entry = egress_map([_tool()])["t"]
    assert entry["name"] == "t" and entry["pack"] is None


# -----------------------------------------------------
# The four the round trip was not wide enough to catch
# -----------------------------------------------------


def _nested_list_tool(hidden, name="t"):
    secret_type = (
        Annotated[Optional[str], Body(), Mode("response_only")]
        if hidden
        else Annotated[Optional[str], Body()]
    )

    class Cell(BaseModel):
        text: Annotated[str, Body()]
        secret: secret_type = None

    class Row(BaseModel):
        cells: Annotated[List[List[Cell]], Body()] = []

    class Req(BaseModel):
        row: Annotated[Optional[Row], Body()] = None

    return _tool(name=name, args_schema=Req)


def test_a_mode_survives_two_container_layers():
    """`List[List[Model]]` — the shape that put Notion's rich text in the prompt.

    The view was rewritten one container layer at a time, so the inner
    annotation kept pointing at the wire model and `Mode` stopped applying
    under it. The map, which unwraps every layer, reported the filtering that
    was not happening: `RichText.plain_text` and `.href` were withheld on paper
    and offered on three Notion tools.
    """
    tool = _nested_list_tool(hidden=True)
    entry = egress_map([tool])["t"]

    assert "row.cells.text" in entry["visible"]
    assert {"field": "row.cells.secret", "reason": "response_only"} in entry["withheld"]
    assert "row.cells.secret" not in emitted_paths(tool.llm_schema())

    # The wire model stops being referenced at all, rather than sitting in
    # `$defs` beside the filtered one waiting to be pointed at again.
    defs = tool.llm_schema().model_json_schema()["$defs"]
    assert all(name.endswith("_LLM") for name in defs), sorted(defs)


def test_a_projection_survives_two_container_layers():
    """The same hole, reached by prune instead of Mode.

    Worse than the Mode half, because a projection is a claim a deployment
    makes at the moment it narrows a tool: `drop` reported the field gone and
    handed it over anyway.
    """
    tool = _nested_list_tool(hidden=False, name="base").derived(name="t", drop=["row.cells.secret"])
    entry = egress_map([tool])["t"]

    assert {"field": "row.cells.secret", "reason": "projection"} in entry["withheld"]
    assert "row.cells.secret" not in emitted_paths(tool.llm_schema())


def test_a_format_field_is_reported_as_the_type_the_model_fills_in():
    """`Format` retypes the field, so the wire type is not what to report.

    Gmail's `body.raw` is a base64 MIME string on the wire and an
    `EmailContent` in the view. Reporting the annotation described a leaf while
    the model was being offered eleven fields under it.
    """
    entry = egress_map(gmail.TOOLS)["gmail__messages_send"]
    visible = set(entry["visible"])

    assert {"body.raw.to", "body.raw.cc", "body.raw.subject"} <= visible
    # And nothing under it is claimed as controlled: the builder substitutes the
    # semantic type and carries neither Mode nor prune inside it, so a `withheld`
    # row there would be a filter that is not running.
    assert not [w for w in entry["withheld"] if w["field"].startswith("body.raw.")]


def test_a_union_of_several_models_keeps_every_member():
    """Choosing a member is not narrowing the view, it is losing half the type."""
    tool = _tool(args_schema=EitherSafe)
    visible = set(egress_map([tool])["t"]["visible"])

    # Both halves reach the model, so the map names both halves.
    assert {"either.draft_field", "either.published_field"} <= visible
    assert visible <= emitted_paths(tool.llm_schema())


def test_every_union_member_is_filtered_in_its_own_right():
    """Keeping every member is only half of it; each still has to be rewritten.

    The two wrong answers sit either side of this. Taking the first member
    filtered it and dropped the rest. Keeping the union whole and unrewritten
    keeps the rest and filters none of them, which puts a `response_only` field
    in the prompt.
    """
    tool = _tool(args_schema=EitherRisky)
    entry = egress_map([tool])["t"]

    assert "either.draft_field" in entry["visible"]
    assert "either.b" in entry["visible"]
    assert {"field": "either.hidden", "reason": "response_only"} in entry["withheld"]
    assert "either.hidden" not in emitted_paths(tool.llm_schema())

    defs = tool.llm_schema().model_json_schema()["$defs"]
    assert all(name.endswith("_LLM") for name in defs), sorted(defs)


def test_the_benign_union_a_shipped_pack_declares_is_still_allowed():
    """Firecrawl's `Optional[Union[bool, RedactPIIOptions]]` carries no markers.

    The guard refuses a hole, not a union. Refusing the shape outright would
    have broken five shipped tools to fix nothing.
    """
    entry = egress_map(firecrawl.TOOLS)["firecrawl__scrape"]
    assert "redact_pii" in entry["visible"]


class MemberA(BaseModel):
    shared: Annotated[Optional[str], Body()] = None


class MemberB(BaseModel):
    shared: Annotated[Optional[str], Body(), Mode("response_only")] = None
    only_b: Annotated[Optional[str], Body(), Mode("response_only")] = None


class SharedNames(BaseModel):
    f: Annotated[Optional[Union[MemberA, MemberB]], Body()] = None


def test_union_members_sharing_a_field_name_get_one_row():
    """Members share a path prefix, so the same field name is the same path.

    Firecrawl's three monitor targets all carry `id` and `type`, which listed 76
    paths twice on two tools once each member was walked in its own right.
    """
    entry = egress_map([_tool(args_schema=SharedNames)])["t"]
    assert entry["visible"].count("f.shared") == 1
    assert [w["field"] for w in entry["withheld"]].count("f.only_b") == 1


def test_a_field_one_union_member_offers_is_visible_not_withheld():
    """Where two members disagree about a shared name, visible wins.

    The model chooses the member, so a field `MemberA` offers is a field it can
    send whatever `MemberB` declares about its own field of that name. Reporting
    it withheld is the one error this module exists to prevent, and reporting it
    both ways makes the artifact contradict itself.
    """
    entry = egress_map([_tool(args_schema=SharedNames)])["t"]
    withheld = {w["field"] for w in entry["withheld"]}

    assert "f.shared" in entry["visible"]
    assert "f.shared" not in withheld
    # The member that withholds it does not get to claim a control that is not
    # running, but its own withheld field is still reported.
    assert "f.only_b" in withheld
    assert not (set(entry["visible"]) & withheld)


def test_visible_and_withheld_are_disjoint_in_every_shipped_pack():
    """The invariant, over the packs rather than one fixture.

    `test_visible_and_withheld_never_overlap` asserts this on a two-model
    fixture that has no union in it, which is the one shape that cannot break it.
    """
    for pack in ALL_PACKS:
        report = egress_map(pack.TOOLS)
        for tool in pack.TOOLS:
            entry = report[report_key(tool)]
            overlap = set(entry["visible"]) & {w["field"] for w in entry["withheld"]}
            assert not overlap, f"{tool.name}: {sorted(overlap)[:5]} reported both ways"
            assert len(entry["visible"]) == len(set(entry["visible"])), (
                f"{tool.name}: duplicate rows in visible"
            )
