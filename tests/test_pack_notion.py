"""
The Notion pack — the bytes on the wire, and the rules that never reach it.

Notion is the pack where key casing is not a convention question but a
correctness one: a page's ``properties`` map is keyed by whatever someone typed
in Notion, so any conversion at all would rewrite a user's column names. Several
of the assertions below exist only to hold that still.
"""

from __future__ import annotations

import json
from typing import get_args

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import CredentialError
from charter.auth import StaticTokenProvider
from charter.packs import notion
from charter.packs.notion.response_handlers import trim_blocks, trim_page, trim_pages
from charter.packs.notion.types.blocks.models import Block, CodeLanguage, LeafBlock, NestedBlock
from charter.packs.notion.types.common import NotionColor, SelectColor
from charter.packs.notion.types.pages.models import RollupFunction

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    notion.configure(StaticTokenProvider("ntn_test"))
    yield
    monkeypatch.setattr(notion._credentials, "_provider", None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


# -----------------------------------------------------
# The constants every call carries
# -----------------------------------------------------


@respx.mock
async def test_every_request_pins_the_api_version():
    """`Notion-Version` is required on every request; omitting it is a 400."""
    route = respx.get("https://api.notion.com/v1/users/me").mock(
        return_value=httpx.Response(200, json={"object": "user", "id": "u1", "type": "bot"})
    )
    await notion.users_retrieve_me.ainvoke({})
    request = route.calls.last.request
    assert request.headers["Notion-Version"] == "2026-03-11"
    assert request.headers["Authorization"] == "Bearer ntn_test"


def test_the_version_is_not_a_field_the_model_can_set():
    """It is a constant, so it lives on the factory and not in a schema."""
    for tool in notion.TOOLS:
        assert "notion_version" not in tool.llm_schema().model_fields
        assert "version" not in tool.llm_schema().model_fields


def test_the_pack_declares_no_envelope():
    """Notion reports failure with a status code, so there is nothing to unwrap."""
    assert all(tool.envelope is None for tool in notion.TOOLS)


# -----------------------------------------------------
# Query parameters, by the names Notion documents
# -----------------------------------------------------


@respx.mock
async def test_a_get_sends_the_query_parameters_notion_documents():
    route = respx.get("https://api.notion.com/v1/blocks/b1/children").mock(
        return_value=httpx.Response(200, json={"results": [], "has_more": False})
    )
    await notion.blocks_children_list.ainvoke(
        {"block_id": "b1", "page_size": 50, "start_cursor": "cur"}
    )
    params = route.calls.last.request.url.params
    # snake_case, not the camelCase default a Google-shaped pack would send.
    assert params["page_size"] == "50"
    assert params["start_cursor"] == "cur"


@respx.mock
async def test_a_list_query_parameter_repeats_rather_than_joining():
    route = respx.get("https://api.notion.com/v1/pages/p1").mock(
        return_value=httpx.Response(200, json={"object": "page", "id": "p1"})
    )
    await notion.pages_retrieve.ainvoke(
        {"page_id": "p1", "filter_properties": ["abc", "def"]}
    )
    assert route.calls.last.request.url.params.get_list("filter_properties") == ["abc", "def"]


# -----------------------------------------------------
# Bodies
# -----------------------------------------------------


@respx.mock
async def test_a_post_sends_the_body_notion_documents():
    route = respx.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"object": "page", "id": "p1"})
    )
    await notion.pages_create.ainvoke(
        {
            "body": {
                "parent": {"data_source_id": "ds1"},
                "properties": {
                    "Name": {"title": [{"type": "text", "text": {"content": "Ship it"}}]}
                },
                "children": [
                    {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "hi"}}]}}
                ],
            }
        }
    )
    body = json.loads(route.calls.last.request.content)
    assert body["parent"] == {"data_source_id": "ds1"}
    assert body["properties"]["Name"]["title"][0]["text"]["content"] == "Ship it"
    assert body["children"][0]["paragraph"]["rich_text"][0]["text"]["content"] == "hi"


@respx.mock
async def test_a_user_named_property_survives_the_wire_verbatim():
    """The `properties` map is keyed by whatever someone typed into Notion.

    Any key conversion at all would rewrite it — `Due Date` into `dueDate`,
    `due_date` or `DueDate` — and Notion would answer that no such property
    exists. This is why the factory sets `body_case="snake"`: snake is the
    identity conversion, so the keys pass through untouched.
    """
    route = respx.patch("https://api.notion.com/v1/pages/p1").mock(
        return_value=httpx.Response(200, json={"object": "page", "id": "p1"})
    )
    await notion.pages_update.ainvoke(
        {
            "page_id": "p1",
            "body": {
                "properties": {
                    "Due Date": {"date": {"start": "2026-01-01"}},
                    "in progress": {"checkbox": True},
                    "URL": {"url": "https://example.com"},
                }
            },
        }
    )
    body = json.loads(route.calls.last.request.content)
    assert sorted(body["properties"]) == ["Due Date", "URL", "in progress"]


@respx.mock
async def test_a_compound_filter_sends_the_keywords_python_will_not_allow():
    """`and` and `or` are Python keywords, so the fields are `and_` and `or_`.

    They reach the wire under Notion's own spelling through a model serializer
    that ``create_llm_schema`` carries onto the generated view. A ``WireName``
    cannot do it: key conversion applies per-field markers at the top level of a
    body, and a filter is nested inside one. If this ever regresses the filter
    is silently ignored and the query returns every row.
    """
    route = respx.post("https://api.notion.com/v1/data_sources/ds1/query").mock(
        return_value=httpx.Response(200, json={"results": [], "has_more": False})
    )
    await notion.data_sources_query.ainvoke(
        {
            "data_source_id": "ds1",
            "body": {
                "filter": {
                    "and": [
                        {"property": "Status", "status": {"equals": "Done"}},
                        {"or": [
                            {"property": "Cost", "number": {"greater_than": 5}},
                            {"property": "Tags", "multi_select": {"contains": "urgent"}},
                        ]},
                    ]
                },
                "sorts": [{"property": "Cost", "direction": "descending"}],
            },
        }
    )
    body = json.loads(route.calls.last.request.content)
    assert "and" in body["filter"] and "and_" not in body["filter"]
    nested = body["filter"]["and"][1]
    assert "or" in nested and "or_" not in nested
    assert nested["or"][0]["number"] == {"greater_than": 5}
    assert body["sorts"] == [{"property": "Cost", "direction": "descending"}]


# -----------------------------------------------------
# The no-argument call
# -----------------------------------------------------


@respx.mock
async def test_search_with_no_arguments_sends_an_empty_body():
    """Everything a schema defaults into a request shows up on this line."""
    route = respx.post("https://api.notion.com/v1/search").mock(
        return_value=httpx.Response(200, json={"results": [], "has_more": False})
    )
    await notion.search.ainvoke({})
    assert json.loads(route.calls.last.request.content) == {}


@respx.mock
async def test_a_query_with_no_filter_sends_an_empty_body():
    route = respx.post("https://api.notion.com/v1/data_sources/ds1/query").mock(
        return_value=httpx.Response(200, json={"results": [], "has_more": False})
    )
    await notion.data_sources_query.ainvoke({"data_source_id": "ds1"})
    assert json.loads(route.calls.last.request.content) == {}


@respx.mock
async def test_listing_users_with_no_arguments_sends_no_query_string():
    route = respx.get("https://api.notion.com/v1/users").mock(
        return_value=httpx.Response(200, json={"results": [], "has_more": False})
    )
    await notion.users_list.ainvoke({})
    assert str(route.calls.last.request.url) == "https://api.notion.com/v1/users"


# -----------------------------------------------------
# Enums, against the API's own values
# -----------------------------------------------------


def test_the_colour_enum_carries_notions_whole_palette():
    """Ten hues as text and again as highlights, plus both defaults.

    ``default_background`` is the one a reader drops when transcribing this by
    eye — it is in the API's ``apiColor`` and not in the prose table.
    """
    values = set(get_args(NotionColor))
    hues = {"gray", "brown", "orange", "yellow", "green", "blue", "purple", "pink", "red"}
    assert values == {"default", "default_background"} | hues | {
        f"{hue}_background" for hue in hues
    }
    assert len(values) == 20


def test_a_select_option_has_no_background_colours():
    """An option is a chip, so there is no text-versus-highlight distinction."""
    assert set(get_args(SelectColor)) == {
        "default", "gray", "brown", "orange", "yellow",
        "green", "blue", "purple", "pink", "red",
    }


def test_the_code_language_enum_is_the_full_set():
    """Ninety values, several of which are not identifiers.

    Transcriptions of this list run short — the prose page and two independent
    readings of it produced around sixty-five. These are asserted against the
    values rather than against a count alone, because a count is satisfied by
    ninety wrong strings.
    """
    languages = set(get_args(CodeLanguage))
    assert len(languages) == 90
    # The ones a shorter list drops, and the shapes that are easy to normalise away.
    for spelled in ("plain text", "ascii art", "llvm ir", "notion formula",
                    "visual basic", "java/c/c++/c#", "c#", "c++", "f#",
                    "objective-c", "vb.net", "matlab", "mathematica", "solidity"):
        assert spelled in languages


def test_the_rollup_functions_are_all_twenty_four():
    assert len(set(get_args(RollupFunction))) == 24
    for name in ("show_unique", "percent_per_group", "count_per_group", "show_original"):
        assert name in get_args(RollupFunction)


# -----------------------------------------------------
# The nesting Notion actually accepts
# -----------------------------------------------------


def test_the_block_tiers_match_notions_three_request_schemas():
    """31 kinds at the top, 29 one level down, 28 at the bottom.

    Notion accepts two levels of nesting per request and publishes a schema per
    tier. A `column` and a `column_list` exist only at the top; a `table` needs
    rows, so it cannot sit at the bottom where nothing has children.
    """
    common = {
        "object", "type", "id", "parent", "created_time", "created_by",
        "last_edited_time", "last_edited_by", "has_children", "archived",
    }
    read_only = {"child_page", "child_database", "link_preview", "unsupported"}

    def writable(model):
        return set(model.model_fields) - common - read_only

    assert len(writable(Block)) == 31
    assert len(writable(NestedBlock)) == 29
    assert len(writable(LeafBlock)) == 28
    assert {"column", "column_list"} <= writable(Block)
    assert not {"column", "column_list"} & writable(NestedBlock)
    assert "table" in writable(NestedBlock)
    assert "table" not in writable(LeafBlock)


def test_the_bottom_tier_holds_no_children():
    """Which is what stops a tree too deep for one request being composed."""
    for field in LeafBlock.model_fields.values():
        assert "children" not in str(field.annotation)


# -----------------------------------------------------
# Cross-field rules, against the LLM view
# -----------------------------------------------------


def test_a_block_may_name_only_one_kind():
    schema = notion.blocks_children_append.llm_schema()
    with pytest.raises(ValidationError, match="exactly one of"):
        schema.model_validate(
            {"block_id": "b1", "body": {"children": [{"divider": {}, "breadcrumb": {}}]}}
        )


def test_a_block_type_must_name_the_content_it_carries():
    schema = notion.blocks_children_append.llm_schema()
    with pytest.raises(ValidationError, match="does not name"):
        schema.model_validate(
            {"block_id": "b1", "body": {"children": [{"type": "code", "divider": {}}]}}
        )


def test_a_page_cannot_take_both_blocks_and_markdown():
    """Declared with ConflictsWith, so the runtime builds the check."""
    schema = notion.pages_create.llm_schema()
    with pytest.raises(ValidationError, match="cannot be combined"):
        schema.model_validate(
            {
                "body": {
                    "parent": {"page_id": "p1"},
                    "markdown": "# hi",
                    "children": [{"divider": {}}],
                }
            }
        )


def test_a_comment_must_be_addressed():
    schema = notion.comments_create.llm_schema()
    with pytest.raises(ValidationError, match="discussion_id"):
        schema.model_validate({"body": {"rich_text": [{"text": {"content": "hi"}}]}})


def test_a_comment_cannot_both_start_and_join_a_discussion():
    schema = notion.comments_create.llm_schema()
    with pytest.raises(ValidationError, match="cannot be combined"):
        schema.model_validate(
            {
                "body": {
                    "parent": {"page_id": "p1"},
                    "discussion_id": "d1",
                    "markdown": "hi",
                }
            }
        )


def test_a_filter_condition_needs_the_property_it_applies_to():
    schema = notion.data_sources_query.llm_schema()
    with pytest.raises(ValidationError, match="needs `property`"):
        schema.model_validate(
            {"data_source_id": "ds1", "body": {"filter": {"number": {"equals": 1}}}}
        )


def test_an_external_url_upload_needs_the_url():
    schema = notion.file_uploads_create.llm_schema()
    with pytest.raises(ValidationError, match="external_url"):
        schema.model_validate({"body": {"mode": "external_url"}})


def test_a_sort_takes_a_property_or_a_timestamp_but_not_both():
    schema = notion.data_sources_query.llm_schema()
    with pytest.raises(ValidationError, match="exactly one"):
        schema.model_validate(
            {
                "data_source_id": "ds1",
                "body": {
                    "sorts": [
                        {"property": "Cost", "timestamp": "created_time", "direction": "ascending"}
                    ]
                },
            }
        )


# -----------------------------------------------------
# Server-set fields never reach the model
# -----------------------------------------------------


def test_computed_properties_are_hidden_from_a_write():
    """A rollup or a formula sent on a write is a 400, so it is not offered."""
    body = notion.pages_update.llm_schema().model_fields["body"].annotation
    value = body.model_fields["properties"].annotation
    # Dict[str, PagePropertyValue_LLM] -> the value model
    property_model = value.__args__[0].__args__[1]
    for hidden in (
        "formula", "rollup", "unique_id", "created_time", "created_by",
        "last_edited_time", "last_edited_by",
    ):
        assert hidden not in property_model.model_fields
    for offered in ("title", "rich_text", "select", "status", "date", "relation"):
        assert offered in property_model.model_fields


def test_notion_hosted_files_are_never_offered_on_a_write():
    """`file` is a signed URL Notion issues; a caller attaches a `file_upload`."""
    schema = notion.pages_create.llm_schema()
    rendered = json.dumps(schema.model_json_schema())
    assert "expiry_time" not in rendered


def test_read_only_block_types_are_absent_from_a_write():
    schema = notion.blocks_children_append.llm_schema()
    body = schema.model_fields["body"].annotation
    block = body.model_fields["children"].annotation.__args__[0]
    for hidden in ("child_page", "child_database", "link_preview", "unsupported"):
        assert hidden not in block.model_fields


def test_the_egress_map_offers_nothing_notion_would_refuse():
    from charter import format_egress_map

    rendered = format_egress_map(notion.TOOLS)
    assert "pages_create" in rendered
    assert "expiry_time" not in rendered


# -----------------------------------------------------
# Pagination
# -----------------------------------------------------


def test_every_list_endpoint_pages_and_nothing_else_does():
    paging = {tool.name for tool in notion.TOOLS if tool.pagination is not None}
    assert paging == {
        "users_list",
        "search",
        "pages_retrieve_property_item",
        "blocks_children_list",
        "data_sources_query",
        "data_sources_templates_list",
        "comments_list",
        "file_uploads_list",
        "custom_emojis_list",
    }


def test_a_two_page_walk_terminates_on_has_more():
    """Notion keeps sending a cursor on the last page, so `has_more` decides."""
    pagination = notion.NOTION_PAGINATION
    first = {"results": [{"id": "a"}], "next_cursor": "cur", "has_more": True}
    assert pagination.next_page_args(first, {}) == {"start_cursor": "cur"}

    last = {"results": [{"id": "b"}], "next_cursor": "cur", "has_more": False}
    assert pagination.next_page_args(last, {"start_cursor": "cur"}) is None


def test_a_body_paginated_walk_reaches_into_the_body():
    """Search and query carry their cursor inside the body argument."""
    pagination = notion.NOTION_BODY_PAGINATION
    args = pagination.next_page_args(
        {"results": [], "next_cursor": "cur", "has_more": True}, {"data_source_id": "ds1"}
    )
    assert args == {"data_source_id": "ds1", "body": {"start_cursor": "cur"}}


@respx.mock
async def test_a_handler_keeps_the_paging_markers_it_was_given():
    route = respx.post("https://api.notion.com/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"object": "page", "id": "p1", "properties": {}}],
                "next_cursor": "cur",
                "has_more": True,
            },
        )
    )
    result = await notion.search.ainvoke({})
    assert route.calls.call_count == 1
    assert result["has_more"] is True
    assert result["next_cursor"] == "cur"


# -----------------------------------------------------
# Response handlers, including the paths that are not happy
# -----------------------------------------------------


async def test_a_page_is_flattened_to_the_values_a_reader_would_quote():
    page = {
        "object": "page",
        "id": "p1",
        "url": "https://notion.so/p1",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "Ship "}, {"plain_text": "it"}]},
            "Status": {"type": "select", "select": {"name": "Done", "color": "green"}},
            "Due": {"type": "date", "date": {"start": "2026-01-01", "end": "2026-01-05"}},
            "Owner": {"type": "people", "people": [{"object": "user", "id": "u1"}]},
            "Score": {"type": "formula", "formula": {"type": "number", "number": 7}},
        },
    }
    assert await trim_page(page) == {
        "id": "p1",
        "title": "Ship it",
        "url": "https://notion.so/p1",
        "properties": {
            "Status": "Done",
            "Due": "2026-01-01 → 2026-01-05",
            "Owner": ["u1"],
            "Score": 7,
        },
    }


async def test_an_empty_page_of_results_is_still_a_page_of_results():
    assert await trim_pages({"results": [], "has_more": False}) == {
        "results": [],
        "has_more": False,
    }


async def test_a_formula_notion_could_not_evaluate_says_so():
    """Dropping it would read as an empty column rather than an unknown one."""
    page = {
        "id": "p1",
        "properties": {"Score": {"type": "formula", "formula": {"type": "unsupported"}}},
    }
    assert (await trim_page(page))["properties"]["Score"] == "unsupported"


async def test_a_property_type_added_later_is_passed_through_rather_than_dropped():
    page = {"id": "p1", "properties": {"New": {"type": "sentiment", "sentiment": {"x": 1}}}}
    assert (await trim_page(page))["properties"]["New"] == {"x": 1}


async def test_an_async_page_creation_returns_the_task_rather_than_an_empty_page():
    """A projection would hand back a page object with every field missing."""
    task = {"object": "async_task", "id": "t1", "status": "queued"}
    assert await trim_page(task) == task


async def test_a_block_listing_keeps_what_says_the_read_was_incomplete():
    response = {
        "results": [
            {
                "id": "b1",
                "type": "toggle",
                "toggle": {"rich_text": [{"plain_text": "More"}]},
                "has_children": True,
            }
        ],
        "has_more": False,
    }
    assert await trim_blocks(response) == {
        "results": [{"id": "b1", "type": "toggle", "text": "More", "has_children": True}],
        "has_more": False,
    }


async def test_a_search_result_that_is_not_a_page_keeps_its_own_shape():
    response = {
        "results": [{"object": "data_source", "id": "ds1", "title": [{"plain_text": "Tasks"}]}],
        "has_more": False,
    }
    trimmed = await trim_pages(response)
    assert trimmed["results"][0]["title"] == "Tasks"
    assert trimmed["results"][0]["object"] == "data_source"


def test_no_response_handler_reads_a_status():
    """Failure is the runtime's business; a handler only ever sees a success."""
    import inspect

    from charter.packs.notion import response_handlers

    source = inspect.getsource(response_handlers)
    assert "status_code" not in source


# -----------------------------------------------------
# Credentials
# -----------------------------------------------------


@respx.mock
async def test_an_unconfigured_pack_raises_before_it_sends_anything(monkeypatch):
    monkeypatch.setattr(notion._credentials, "_provider", None)
    route = respx.get("https://api.notion.com/v1/users/me")
    with pytest.raises(CredentialError) as excinfo:
        await notion.users_retrieve_me.ainvoke({})
    assert route.call_count == 0
    assert "NOTION_API_KEY" in str(excinfo.value)


# -----------------------------------------------------
# The failure a deferred annotation hides
# -----------------------------------------------------


def test_every_field_resolved_and_knows_where_it_goes():
    """A missing import does not raise here — it makes a field required.

    These modules use `from __future__ import annotations`, so an annotation is
    a string pydantic resolves against the module namespace. When a name is not
    there, the field keeps a `ForwardRef` instead: no location marker, so it is
    not read as a query parameter, and no default, so the model is made to
    supply it on every call. Schemas still build and the suite still passes.

    It happened twice while writing this pack, both times because a marker was
    imported for a field added later — `Query` in the data source module and
    `Literal` in the pages module. Nothing else in the suite would have caught
    either one, so the check is here.
    """
    from pydantic import BaseModel

    from charter.types.markers import Body, Path, Query

    unresolved, unplaced, seen = [], [], set()

    def walk(model, trail):
        if model in seen or not (isinstance(model, type) and issubclass(model, BaseModel)):
            return
        seen.add(model)
        for name, field in model.model_fields.items():
            if "ForwardRef" in repr(field.annotation):
                unresolved.append(f"{trail}.{name}")
            for outer in [field.annotation, *getattr(field.annotation, "__args__", ())]:
                for inner in [outer, *getattr(outer, "__args__", ())]:
                    if isinstance(inner, type) and issubclass(inner, BaseModel):
                        walk(inner, f"{trail}.{name}")

    for tool in notion.TOOLS:
        for name, field in tool.args_schema.model_fields.items():
            if not any(isinstance(m, (Body, Path, Query)) for m in field.metadata):
                unplaced.append(f"{tool.name}.{name}")
        walk(tool.args_schema, tool.name)

    assert not unresolved, f"annotations that never resolved: {unresolved}"
    assert not unplaced, f"top-level fields with no Path/Query/Body marker: {unplaced}"
