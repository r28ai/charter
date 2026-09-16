"""Projections — `Tool.derived`, and the guarantees that make one safe to hand out.

A projection may only ever *remove*. Every test here is ultimately about that:
what it removes, that removal is enforced rather than suggested, that it cannot
remove something the API needs, and that whoever reviews the boundary can read
what was removed.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from charter import PathCost, Tool
from charter.discovery import schema_tokens
from charter.egress import egress_map
from charter.packs import gcalendar, gdocs, gdrive
from charter.packs.gdocs.types.requests import InsertTextRequest
from charter.types.errors import DeclarationError, ToolValidationError
from charter.types.markers import Body, Case, Format, Path, Query, WireName

BASE = "https://api.example.com/"

TEXT = {"insert_text", "delete_content_range", "replace_all_text"}


class Search(BaseModel):
    account: Annotated[str, Field(description="Account."), Path()]
    q: Annotated[Optional[str], Field(None, description="Filter."), Query()]
    i_cal_uid: Annotated[Optional[str], Field(None), Query(), WireName("iCalUID")]
    tag: Annotated[Optional[str], Field(None), Query(), Case("pascal")]
    payload: Annotated[Optional[dict], Field(None), Body()]


class Formatted(BaseModel):
    user_id: Annotated[str, Path()]
    raw: Annotated[Optional[str], Field(None), Body(), Format("rfc822_base64")]


class Unwrapping(BaseModel):
    parent: Annotated[str, Path()]
    document: Annotated[Optional[dict], Field(None), Body()]


def _formatted() -> Tool:
    return Tool(name="send", method="POST", url_template="v1/{user_id}/send",
                args_schema=Formatted, base_url=BASE, api_key_headers={"k": "v"})


def _unwrapping() -> Tool:
    return Tool(name="create", method="POST", url_template="v1/{parent}/docs",
                args_schema=Unwrapping, base_url=BASE, api_key_headers={"k": "v"})


def _tool(**overrides) -> Tool:
    kwargs = dict(
        name="search",
        description="Search.",
        method="GET",
        url_template="v1/{account}/search",
        args_schema=Search,
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
        query_case="camel",
    )
    kwargs.update(overrides)
    return Tool(**kwargs)  # type: ignore[arg-type]


# -----------------------------------------------------
# keep / drop
# -----------------------------------------------------


def test_keep_narrows_the_union_and_leaves_the_rest_of_the_tool_alone():
    edit = gdocs.documents_batch_update.derived(name="documents_edit_text", keep=TEXT)

    assert set(edit.paths("body.requests")) == TEXT
    # The point of scoping `keep` to its own sibling group: the fields you did
    # not mention are still there, so the tool is still callable.
    assert edit.paths() == ["document_id", "body"]
    assert "write_control" in edit.paths("body")


def test_keep_is_what_it_costs_in_context():
    full = len(json.dumps(gdocs.documents_batch_update.to_json_schema()))
    edit = gdocs.documents_batch_update.derived(name="edit", keep=TEXT)
    assert len(json.dumps(edit.to_json_schema())) < full * 0.3


def test_a_dropped_capability_is_refused_not_ignored():
    """The difference between a projection and a sentence in a prompt."""
    edit = gdocs.documents_batch_update.derived(name="edit", keep=TEXT)
    with pytest.raises(ToolValidationError):
        edit.invoke(
            document_id="d",
            body={"requests": [{"insert_table": {"rows": 2, "columns": 2}}]},
        )


def test_a_projection_keeps_the_validators_of_the_schema_it_narrowed():
    """The oneof rule is the contract; narrowing the union must not relax it."""
    edit = gdocs.documents_batch_update.derived(name="edit", keep=TEXT)
    with pytest.raises(ToolValidationError):
        edit.invoke(
            document_id="d",
            body={
                "requests": [
                    {
                        "insert_text": {"text": "a", "location": {"index": 1}},
                        "replace_all_text": {"replace_text": "b"},
                    }
                ]
            },
        )


def test_drop_removes_one_path():
    lean = gdocs.documents_batch_update.derived(name="lean", drop={"write_control"})
    assert "write_control" not in lean.paths("body")
    assert "requests" in lean.paths("body")


def test_projections_compose():
    edit = gdocs.documents_batch_update.derived(name="edit", keep=TEXT)
    narrower = edit.derived(name="insert_only", keep={"insert_text"})
    assert narrower.paths("body.requests") == ["insert_text"]


def test_pruning_one_branch_does_not_reach_an_identical_type_in_another():
    """`Location` sits under most Docs requests; they must stay independent."""
    t = gdocs.documents_batch_update.derived(
        name="t", keep={"insert_text", "insert_page_break"}
    )
    t = t.derived(name="t2", drop={"body.requests.insert_text.location"})
    assert "location" not in t.paths("body.requests.insert_text")
    assert "location" in t.paths("body.requests.insert_page_break")


# -----------------------------------------------------
# pin
# -----------------------------------------------------


@respx.mock
def test_pin_leaves_the_schema_and_still_reaches_the_wire():
    route = respx.get(f"{BASE}v1/acct_1/search").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    pinned = _tool().derived(name="scoped", pin={"account": "acct_1", "q": "mine"})

    assert "account" not in pinned.llm_schema().model_fields
    assert "q" not in pinned.llm_schema().model_fields

    pinned.invoke()
    assert route.calls.last.request.url.params["q"] == "mine"
    assert route.calls.last.request.url.path == "/v1/acct_1/search"


@respx.mock
def _wire(tool: Tool, **args) -> httpx.Request:
    """The request a tool actually sends, which is the only thing worth asserting.

    The first version of these tests read `static_query` and `url_template` off
    the tool instead. Both bugs this file now pins got through that: asserting
    the mechanism agrees with itself proves nothing about the wire.
    """
    respx.route().mock(return_value=httpx.Response(200, json={}))
    tool.invoke(**args)
    return respx.calls.last.request


def test_a_pinned_value_and_a_supplied_one_are_identical_on_the_wire():
    """The invariant the whole design rests on. Checked per marker kind."""
    for field, value, supplied_with in (
        ("i_cal_uid", "x", {"account": "a"}),  # Query + WireName
        ("tag", "x", {"account": "a"}),  # Query + Case
        ("payload", {"k": 1}, {"account": "a"}),  # Body
        ("account", "acct_1", {}),  # Path
    ):
        base = _tool()
        supplied = _wire(base, **{field: value}, **supplied_with)
        pinned = _wire(base.derived(name="p", pin={field: value}), **supplied_with)
        assert supplied.url.raw_path == pinned.url.raw_path, field
        assert supplied.content == pinned.content, field


def test_a_pinned_path_value_is_escaped_by_the_runtime():
    """Not by a second copy of the escaping table beside it."""
    request = _wire(_tool().derived(name="scoped", pin={"account": "a/b"}))
    assert request.url.raw_path == b"/v1/a%2Fb/search"


def test_a_pinned_format_field_is_encoded_not_sent_raw():
    """Regression: a pin used to skip the transform and send the semantic value."""
    message = {"to": ["a@b.c"], "subject": "hi", "body": "x"}
    pinned = _wire(_formatted().derived(name="p", pin={"raw": message}), user_id="u")
    supplied = _wire(_formatted(), user_id="u", raw=message)
    sent = json.loads(pinned.content)
    assert isinstance(sent["raw"], str), "semantic value reached the wire unencoded"
    assert pinned.content == supplied.content


def test_a_pinned_single_body_field_still_unwraps():
    """Regression: a pin used to arrive wrapped in its own field name."""
    body = {"title": "T"}
    pinned = _wire(_unwrapping().derived(name="p", pin={"document": body}), parent="p")
    assert json.loads(pinned.content) == body


def test_a_pin_that_does_not_satisfy_its_field_is_refused_at_declaration():
    with pytest.raises(DeclarationError, match="does not satisfy"):
        _formatted().derived(name="bad", pin={"raw": {"subject": "no recipient"}})


def test_pin_refuses_a_nested_path():
    with pytest.raises(DeclarationError, match="nested"):
        gdocs.documents_batch_update.derived(name="x", pin={"body.requests": []})


def test_pin_supplies_a_required_field_that_keep_would_otherwise_strand():
    pinned = _tool().derived(name="scoped", pin={"account": "acct_1"})
    assert "account" not in pinned.llm_schema().model_fields


# -----------------------------------------------------
# declaration errors — the reader is the person who wrote the projection
# -----------------------------------------------------


def test_dropping_a_required_field_is_refused_at_declaration():
    with pytest.raises(DeclarationError, match="required by the API"):
        _tool().derived(name="broken", drop={"account"})


def test_an_ambiguous_short_name_names_its_candidates():
    with pytest.raises(DeclarationError, match="matches 19 paths") as exc:
        gdocs.documents_batch_update.derived(name="x", drop={"index"})
    assert "insert_text.location.index" in str(exc.value)


def test_an_unknown_selector_says_so():
    with pytest.raises(DeclarationError, match="not a field"):
        gdocs.documents_batch_update.derived(name="x", keep={"insert_txt"})


def test_a_short_name_resolves_when_it_is_unambiguous():
    edit = gdocs.documents_batch_update.derived(name="x", keep={"insert_text"})
    assert edit.paths("body.requests") == ["insert_text"]


def test_a_model_class_selects_the_field_it_types():
    edit = gdocs.documents_batch_update.derived(name="x", keep={InsertTextRequest})
    assert edit.paths("body.requests") == ["insert_text"]


# -----------------------------------------------------
# what the projection carries across
# -----------------------------------------------------


def test_a_projection_is_the_same_tool_underneath():
    src = gdocs.documents_batch_update
    edit = src.derived(name="documents_edit_text", keep=TEXT)

    assert edit.base_url == src.base_url
    assert edit.method == src.method
    assert edit.pack == src.pack
    assert edit.provider == src.provider
    assert edit.scopes == src.scopes
    assert edit.credential_provider is src.credential_provider
    assert edit.quota_cost == src.quota_cost
    assert edit.args_schema is src.args_schema


def test_a_projection_keeps_the_response_handler_it_narrowed():
    src = gdocs.documents_get
    assert src._response_handler is not None
    assert src.derived(name="x", drop={"suggestions_view_mode"})._response_handler is (
        src._response_handler
    )


def test_description_and_action_label_can_be_restated():
    edit = gdocs.documents_batch_update.derived(
        name="edit", keep=TEXT, description="Text only.", action_label="Edits text."
    )
    assert edit.description == "Text only."
    assert edit.action_label == "Edits text."
    # and default to the tool's own
    assert gdocs.documents_batch_update.derived(name="e2", keep=TEXT).description == (
        gdocs.documents_batch_update.description
    )


# -----------------------------------------------------
# the artifact
# -----------------------------------------------------


def test_the_egress_map_reports_what_the_projection_removed():
    edit = gdocs.documents_batch_update.derived(name="documents_edit_text", keep=TEXT)
    entry = egress_map([edit])["documents_edit_text"]

    withheld = {w["field"]: w["reason"] for w in entry["withheld"]}
    assert withheld["body.requests.insert_table"] == "projection"
    assert not any(f.startswith("body.requests.insert_table.") for f in withheld)
    assert "body.requests.insert_text" in entry["visible"]


def test_the_egress_map_reports_a_pin_with_its_value():
    scoped = gdrive.files_list.derived(
        name="search_documents",
        pin={"q": "mimeType='application/vnd.google-apps.document'"},
    )
    entry = egress_map([scoped])["search_documents"]

    assert "google-apps.document" in entry["pinned"]["q"]
    pinned = [w for w in entry["withheld"] if w["field"] == "q"]
    assert pinned and pinned[0]["reason"] == "pinned"
    assert "q" not in entry["visible"]


def test_paths_lists_one_level_and_forgets_a_pruned_branch():
    t = gdocs.documents_batch_update
    assert t.paths() == ["document_id", "body"]
    assert len(t.paths("body.requests")) == 33

    edit = t.derived(name="edit", keep=TEXT)
    assert len(edit.paths(depth=None)) < len(t.paths(depth=None))
    assert not any(p.startswith("insert_table") for p in edit.paths("body.requests", depth=None))


def test_paths_by_cost_prices_the_level_it_returns_most_expensive_first():
    priced = gdocs.documents_batch_update.paths(by_cost=True)

    assert all(isinstance(pc, PathCost) for pc in priced)
    assert [pc.path for pc in priced] == ["body", "document_id"]
    assert [pc.tokens for pc in priced] == sorted((pc.tokens for pc in priced), reverse=True)
    assert priced[0].tokens > 50 * priced[1].tokens


def test_paths_by_cost_returns_the_same_paths_as_paths():
    t = gdocs.documents_batch_update
    for under in ("", "body", "body.requests"):
        assert sorted(pc.path for pc in t.paths(under, by_cost=True)) == sorted(t.paths(under))


def test_a_priced_path_is_what_dropping_it_actually_saves():
    """The number is measured, not estimated, so `drop` has to reproduce it."""
    t = gdocs.documents_batch_update
    total = schema_tokens(t)

    for pc in t.paths("body.requests", by_cost=True)[:3]:
        narrowed = t.derived(name="x", drop={f"body.requests.{pc.path}"})
        assert schema_tokens(narrowed) == total - pc.tokens


def test_a_required_path_is_priced_even_though_dropping_it_is_refused():
    """`pin` is the answer for a required field, and the price is how you choose it."""
    t = gdocs.documents_batch_update
    requests = next(pc for pc in t.paths("body", by_cost=True) if pc.path == "requests")

    assert requests.tokens > 0
    with pytest.raises(DeclarationError, match="required by the API"):
        t.derived(name="x", drop={"body.requests"})


def test_prices_do_not_sum_to_the_branch_they_sit_under():
    """A `$def` two siblings share survives either one leaving, so both price cheap."""
    t = gdocs.documents_batch_update
    members = t.paths("body.requests", by_cost=True)
    branch = next(pc for pc in t.paths("body", by_cost=True) if pc.path == "requests")

    assert sum(pc.tokens for pc in members) < branch.tokens


def test_a_negative_price_is_a_drop_that_makes_the_tool_larger():
    """Pruning inside a shared model splits its `$def`, and the tool grows.

    `Location` sits under most Docs requests as one `$def`. Pruning a field of it
    under one request makes that request's copy differ from every other, so the
    generator emits two. The projection narrows what the model may do and costs
    tokens for it, which is exactly the thing a caller needs told in advance.
    """
    t = gdocs.documents_batch_update
    total = schema_tokens(t)
    priced = {pc.path: pc.tokens for pc in t.paths("body.requests.insert_text", depth=None, by_cost=True)}

    assert priced["location.index"] < 0

    grown = t.derived(name="x", drop={"body.requests.insert_text.location.index"})
    assert schema_tokens(grown) == total - priced["location.index"] > total

    defs = set(grown.to_json_schema()["parameters"]["$defs"])
    assert "Location_LLM" not in defs
    assert len([d for d in defs if d.endswith("Location_LLM__1") or d.endswith("Location_LLM__2")]) == 2


def test_a_zero_price_is_a_path_mode_already_removed():
    """`paths` walks the declared schema, so it lists what `Mode` hides.

    The two calendar tools differ only in mode, and pricing is what tells them
    apart: on the tool that hides the field there is nothing left to drop.
    """
    insert, importing = gcalendar.events_insert, gcalendar.events_import
    assert "event.i_cal_uid" in insert.paths(depth=None)
    assert "event.i_cal_uid" in importing.paths(depth=None)

    hidden = next(pc for pc in insert.paths("event", by_cost=True) if pc.path == "i_cal_uid")
    shown = next(pc for pc in importing.paths("event", by_cost=True) if pc.path == "i_cal_uid")

    assert hidden.tokens == 0
    assert shown.tokens > 0

    # Which is to say: the projection the zero predicts is a no-op.
    inert = insert.derived(name="x", drop={"event.i_cal_uid"})
    assert inert.to_json_schema()["parameters"] == insert.to_json_schema()["parameters"]


def test_pricing_does_not_disturb_the_tool_it_prices():
    """`path_costs` builds throwaway schemas; the tool keeps the one it had."""
    t = gdocs.documents_batch_update
    before, schema, paths = t.to_json_schema(), t.llm_schema(), t.paths(depth=None)

    t.paths(by_cost=True)
    t.paths("body.requests", by_cost=True)

    assert t.to_json_schema() == before
    assert t.llm_schema() is schema
    assert t.paths(depth=None) == paths
    assert t._prune == frozenset()


def test_pricing_a_mode_carrying_tool_measures_that_mode(mode="write"):
    """The baseline has to be the tool's own view, not the unfiltered schema."""
    t = gcalendar.events_insert
    assert t.mode == mode
    total = schema_tokens(t)

    for pc in t.paths("event", by_cost=True)[:5]:
        narrowed = t.derived(name="x", drop={f"event.{pc.path}"})
        assert schema_tokens(narrowed) == total - pc.tokens


def test_prices_are_measured_against_the_projection_doing_the_asking():
    """A projection prices what is left of it, not what the tool it came from had."""
    t = gdocs.documents_batch_update
    lean = t.derived(name="lean", keep={"insert_text"})

    assert schema_tokens(lean) < schema_tokens(t)
    assert [pc.path for pc in lean.paths("body.requests", by_cost=True)] == ["insert_text"]
    assert next(pc for pc in lean.paths(by_cost=True) if pc.path == "body").tokens < next(
        pc for pc in t.paths(by_cost=True) if pc.path == "body"
    ).tokens


def test_keep_at_two_levels_does_not_let_one_level_delete_the_other():
    """`write_control` is a sibling of `requests`, whose subtree is also kept."""
    t = gdocs.documents_batch_update.derived(
        name="x", keep={"insert_text", "write_control"}
    )
    assert t.paths("body.requests") == ["insert_text"]
    assert "write_control" in t.paths("body")


def test_keeping_only_a_sibling_of_a_required_branch_is_refused():
    with pytest.raises(DeclarationError, match="required by the API"):
        gdocs.documents_batch_update.derived(name="x", keep={"write_control"})


@respx.mock
def test_keep_and_pin_apply_together():
    route = respx.get(f"{BASE}v1/acct_1/search").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    scoped = _tool().derived(
        name="scoped", drop={"tag", "payload"}, pin={"account": "acct_1", "q": "mine"}
    )
    assert set(scoped.llm_schema().model_fields) == {"i_cal_uid"}

    scoped.invoke(i_cal_uid="z")
    params = route.calls.last.request.url.params
    assert params["q"] == "mine" and params["iCalUID"] == "z"


# -----------------------------------------------------
# Drilling in does not reopen a cycle the root walk closed
# -----------------------------------------------------


def test_drilling_into_a_recursive_field_lists_what_the_root_walk_lists():
    """``under`` starts the walk lower down; it does not start it fresh.

    The cycle guard is per branch and holds the models on the path so far, so a
    field whose type is already its own ancestor is not listed again. Starting at
    ``under`` with an empty guard threw that ancestry away, and the same tool then
    gave two answers about the same prefix: ``paths("body.filter.and_")`` offered
    27 children of a filter that is its own parent, while ``paths("", depth=4)``
    showed that prefix has none.

    Checked against the root walk rather than against a fixed list, because the
    root walk is the definition — what ``under`` returns has to be the slice of
    it that starts there.
    """
    from charter.packs import gmail, notion

    for tool, prefix in (
        (notion.data_sources_query, "body.filter.and_"),
        (gmail.messages_send, "body.payload.parts"),
    ):
        deep = [p for p in tool.paths("", depth=8) if p.startswith(f"{prefix}.")]
        assert tool.paths(prefix) == [p[len(prefix) + 1 :] for p in deep], (
            f"{tool.name}: paths({prefix!r}) disagrees with the root walk"
        )
        # And the shape that makes it a test: the prefix is reachable, and the
        # root walk closes it.
        assert prefix in tool.paths("", depth=8)
        assert deep == []


def test_under_still_reaches_a_branch_that_is_not_a_cycle():
    """The guard closes a repeat, not everything below ``under``."""
    t = gdocs.documents_batch_update

    assert t.paths("body") == ["requests", "write_control"]
    assert len(t.paths("body.requests")) == 33
    assert "location" in t.paths("body.requests.insert_text")

    # Absolute paths, so what comes back is usable as a selector as it stands.
    from charter.derive import schema_paths

    assert schema_paths(t.args_schema, under="body", depth=1) == [
        "body.requests",
        "body.write_control",
    ]


def test_the_ancestry_handed_to_the_walk_is_the_path_that_was_walked():
    """``_descend`` returns the models passed through, in order, target excluded.

    The target is left out because :func:`walk_paths` adds it on entry; including
    it would make every ``under`` return nothing at all, which is a failure that
    looks exactly like the cycle guard working.
    """
    from charter.derive import _descend

    t = gdocs.documents_batch_update
    schema = t.args_schema

    root, ancestry = _descend(schema, "")
    assert root is schema and ancestry == ()

    body, ancestry = _descend(schema, "body")
    assert ancestry == (id(schema),)
    assert body is not schema

    _, deeper = _descend(schema, "body.requests")
    assert deeper == (id(schema), id(body))

    assert _descend(schema, "body.nope") is None
    assert _descend(schema, "document_id") is None, "a str is not a model"


def test_keep_still_prunes_below_a_field_that_is_its_own_ancestor():
    """The listing changed; the enforcement must not.

    `keep` resolves a selector and prunes its siblings, and it asked for those
    siblings through the same function that prints a path listing. Once that
    listing started applying the cycle guard from the root, the sibling lookup
    inherited it and answered "no siblings" under any model that is its own
    ancestor. `keep` then pruned nothing and handed back the whole tool, silently
    granting everything the deployer had just asked to remove:
    `keep={"body.filter.and_.checkbox"}` on `data_sources_query` went from a
    3,383-byte projection to the full 21,849-byte tool.

    A projection may only ever remove, and one that quietly removes nothing is
    the failure this module exists to prevent. The two questions are answered
    separately now: `paths()` lists, `_siblings` reads the parent's fields.
    """
    from charter.packs import notion

    tool = notion.data_sources_query
    plain = tool.derived(name="plain", keep={"body.filter.checkbox"})
    cyclic = tool.derived(name="cyclic", keep={"body.filter.and_.checkbox"})

    # The same 26 siblings are pruned either way: `and_` is that same filter.
    assert len(plain._prune) == len(cyclic._prune) == 26
    assert "body.filter.and_.checkbox" not in cyclic._prune

    # And the enforcement is real, not just recorded: a dropped sibling is gone
    # from the view the model fills in, so reaching for it fails validation
    # before a request is built.
    for narrowed in (plain, cyclic):
        assert len(json.dumps(narrowed.to_json_schema())) < len(
            json.dumps(tool.to_json_schema())
        ) or narrowed._prune, "the projection removed nothing"
        with pytest.raises(ToolValidationError):
            narrowed.invoke({"data_source_id": "d", "filter": {"phone_number": {}}})

    # The listing, meanwhile, stays consistent with the root walk.
    assert tool.paths("body.filter.and_") == []


def test_siblings_reads_the_parent_rather_than_walking_the_schema():
    """One level has nothing to guard against, and the guard is what broke it."""
    from charter.derive import _siblings
    from charter.packs import notion

    schema = notion.data_sources_query.args_schema

    # Identical whether or not the parent repeats on its own path.
    direct = [p.rpartition(".")[2] for p in _siblings(schema, "body.filter.checkbox")]
    cyclic = [p.rpartition(".")[2] for p in _siblings(schema, "body.filter.and_.checkbox")]
    assert direct == cyclic and len(direct) == 27

    # Absolute paths, carrying the parent they were asked about.
    assert all(p.startswith("body.filter.and_.") for p in _siblings(schema, "body.filter.and_.x"))
    assert _siblings(schema, "nope.nope") == []

    # A top-level path has the root's fields as siblings, unprefixed.
    top = _siblings(schema, "data_source_id")
    assert "data_source_id" in top and all("." not in p for p in top)
