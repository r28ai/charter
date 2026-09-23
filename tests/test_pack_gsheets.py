"""Google Sheets pack — values wire contract and spreadsheet response trimming.

The values endpoints are already lean and deliberately have no handler. The
spreadsheet resource is not: ``spreadsheetTheme`` and ``defaultFormat`` are
1.3KB of font and cell styling on a 1.7KB payload whose useful half is a title,
a time zone, and the sheet names an A1 range is built from.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.egress import egress_map
from charter.packs import gsheets
from charter.packs.gsheets.types.spreadsheets.models import (
    ChartData,
    ChartSpec,
    CommentAnchor,
    ConditionalFormatRule,
    ConditionValue,
    DeveloperMetadataLocation,
    EmbeddedObjectPosition,
    PivotValue,
    Post,
    Sheet,
    Spreadsheet,
)
from charter.packs.gsheets.types.spreadsheets.requests import Request
from charter.packs.gsheets.types.values.models import (
    DataFilter,
    DateTimeRenderOption,
    Dimension,
    InsertDataOption,
    ValueInputOption,
    ValueRange,
    ValueRenderOption,
)

API = "https://sheets.googleapis.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gsheets.configure(StaticTokenProvider("tok"))


def spreadsheet(**top):
    payload = {
        "spreadsheetId": "1AbC",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/1AbC/edit",
        "properties": {
            "title": "trim-probe",
            "locale": "en_US",
            "autoRecalc": "ON_CHANGE",
            "timeZone": "Etc/GMT",
            "defaultFormat": {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "padding": {"top": 2, "right": 3, "bottom": 2, "left": 3},
                "verticalAlignment": "BOTTOM",
                "wrapStrategy": "OVERFLOW_CELL",
                "textFormat": {
                    "foregroundColor": {},
                    "fontFamily": "arial,sans,sans-serif",
                    "fontSize": 10,
                    "bold": False,
                    "italic": False,
                },
            },
            "spreadsheetTheme": {
                "primaryFontFamily": "Arial",
                "themeColors": [
                    {"colorType": t, "color": {"rgbColor": {"red": 0.1}}}
                    for t in (
                        "TEXT",
                        "BACKGROUND",
                        "ACCENT1",
                        "ACCENT2",
                        "ACCENT3",
                        "ACCENT4",
                        "ACCENT5",
                        "ACCENT6",
                        "LINK",
                    )
                ],
            },
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Sheet1",
                    "index": 0,
                    "sheetType": "GRID",
                    "gridProperties": {"rowCount": 1000, "columnCount": 26},
                }
            }
        ],
    }
    payload.update(top)
    return payload


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_every_documented_endpoint():
    """Named against the API's own method list rather than counted.

    A count passes the day someone adds a tool and forgets one; this fails until
    the pack covers what the v4 reference documents — the four ``spreadsheets``
    methods, ``spreadsheets.sheets.copyTo``, the ten ``spreadsheets.values``
    methods, and both ``spreadsheets.developerMetadata`` methods.
    """
    assert {t.name for t in gsheets.TOOLS} == {
        "spreadsheets_values_get",
        "spreadsheets_values_update",
        "spreadsheets_values_append",
        "spreadsheets_values_clear",
        "spreadsheets_values_batch_get",
        "spreadsheets_values_batch_update",
        "spreadsheets_values_batch_clear",
        "values_batch_get_by_data_filter",
        "values_batch_update_by_data_filter",
        "values_batch_clear_by_data_filter",
        "spreadsheets_create",
        "spreadsheets_get",
        "spreadsheets_batch_update",
        "spreadsheets_sheets_copy_to",
        "spreadsheets_get_by_data_filter",
        "spreadsheets_developer_metadata_get",
        "spreadsheets_developer_metadata_search",
    }
    assert all(isinstance(t, Tool) for t in gsheets.TOOLS)


def test_only_the_spreadsheet_resource_tools_trim():
    """A handler on values.get would save tens of bytes and add a way to be wrong.

    batch_update is in the set because it returns the spreadsheet resource too,
    under include_spreadsheet_in_response — the same object the other three
    trim, and the one case where the flag is what makes the payload large.
    """
    trimming = {t.name for t in gsheets.TOOLS if t._executor._response_handler}
    assert trimming == {
        "spreadsheets_create",
        "spreadsheets_get",
        "spreadsheets_get_by_data_filter",
        "spreadsheets_batch_update",
    }


def test_closed_literals_hold_the_api_enums():
    assert set(Dimension.__args__) == {"DIMENSION_UNSPECIFIED", "ROWS", "COLUMNS"}
    assert set(ValueRenderOption.__args__) == {
        "FORMATTED_VALUE",
        "UNFORMATTED_VALUE",
        "FORMULA",
    }
    assert set(DateTimeRenderOption.__args__) == {"SERIAL_NUMBER", "FORMATTED_STRING"}
    assert set(InsertDataOption.__args__) == {"OVERWRITE", "INSERT_ROWS"}
    assert set(ValueInputOption.__args__) == {
        "INPUT_VALUE_OPTION_UNSPECIFIED",
        "RAW",
        "USER_ENTERED",
    }


def test_value_range_range_is_optional():
    """Range lives on the path for get/update/append; the body must not mandate it."""
    ValueRange(values=[["Ada"]])


def test_value_range_does_not_copy_the_documented_rows_default():
    dumped = ValueRange(values=[["Ada"]]).model_dump(exclude_none=True)
    assert "major_dimension" not in dumped


def test_data_filter_is_a_union():
    DataFilter(a1_range="Sheet1!A1:B2")
    with pytest.raises(ValidationError):
        DataFilter()
    with pytest.raises(ValidationError):
        DataFilter(a1_range="A1", grid_range={"sheet_id": 0})


def test_data_filter_union_survives_into_llm_schema():
    """A rule enforced only against the wire schema never reaches the model."""
    schema = gsheets.values_batch_clear_by_data_filter.llm_schema()
    with pytest.raises(ValidationError):
        schema(spreadsheetId="s1", dataFilters=[{}])
    schema(spreadsheetId="s1", dataFilters=[{"a1Range": "Sheet1!A1"}])


# -----------------------------------------------------
# Trimming
# -----------------------------------------------------


@respx.mock
async def test_get_keeps_what_builds_a_range_and_drops_the_styling():
    respx.get(f"{API}v4/spreadsheets/1AbC").mock(
        return_value=httpx.Response(200, json=spreadsheet())
    )

    result = await gsheets.spreadsheets_get.ainvoke(spreadsheet_id="1AbC")

    assert result["spreadsheetId"] == "1AbC"
    assert result["properties"] == {"title": "trim-probe", "locale": "en_US", "timeZone": "Etc/GMT"}
    assert result["sheets"] == [
        {
            "sheetId": 0,
            "title": "Sheet1",
            "index": 0,
            "sheetType": "GRID",
            "gridProperties": {"rowCount": 1000, "columnCount": 26},
        }
    ]
    blob = json.dumps(result)
    assert "spreadsheetTheme" not in blob
    assert "defaultFormat" not in blob


@respx.mock
async def test_trimming_is_a_large_reduction():
    payload = spreadsheet()
    respx.get(f"{API}v4/spreadsheets/1AbC").mock(return_value=httpx.Response(200, json=payload))

    result = await gsheets.spreadsheets_get.ainvoke(spreadsheet_id="1AbC")
    before, after = len(json.dumps(payload)), len(json.dumps(result))
    assert after < before * 0.5, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_values_get_is_left_alone():
    """Nothing to trim, so nothing may be lost."""
    payload = {
        "range": "Sheet1!A1:C3",
        "majorDimension": "ROWS",
        "values": [["Title", "Start"], ["Kickoff", "2026-09-14 09:00"]],
    }
    respx.get(f"{API}v4/spreadsheets/1AbC/values/Sheet1%21A1%3AC3").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await gsheets.spreadsheets_values_get.ainvoke(
        spreadsheet_id="1AbC", range="Sheet1!A1:C3"
    )
    assert result == payload


# -----------------------------------------------------
# Wire
# -----------------------------------------------------


@respx.mock
async def test_values_get_with_only_required_args_sends_no_query():
    route = respx.get(f"{API}v4/spreadsheets/s1/values/A1").mock(
        return_value=httpx.Response(200, json={"values": []})
    )

    await gsheets.spreadsheets_values_get.ainvoke(spreadsheet_id="s1", range="A1")

    assert dict(route.calls.last.request.url.params) == {}


@respx.mock
async def test_values_update_is_put_and_unwraps_the_value_range():
    route = respx.put(f"{API}v4/spreadsheets/s1/values/Sheet1!A1").mock(
        return_value=httpx.Response(200, json={"updatedCells": 2})
    )

    await gsheets.spreadsheets_values_update.ainvoke(
        spreadsheet_id="s1",
        range="Sheet1!A1",
        value_input_option="USER_ENTERED",
        value_range={"values": [["Ada", 36]]},
    )

    request = route.calls.last.request
    assert request.method == "PUT"
    assert dict(request.url.params) == {"valueInputOption": "USER_ENTERED"}
    assert json.loads(request.content) == {"values": [["Ada", 36]]}


@respx.mock
async def test_values_append_omits_undocumented_body_defaults():
    """A copied ROWS default is a different request from the one the docs describe."""
    route = respx.post(f"{API}v4/spreadsheets/s1/values/Sheet1!A1:append").mock(
        return_value=httpx.Response(200, json={"updates": {"updatedRows": 1}})
    )

    await gsheets.spreadsheets_values_append.ainvoke(
        spreadsheet_id="s1",
        range="Sheet1!A1",
        value_input_option="RAW",
        value_range={"values": [["Ada"]]},
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {"values": [["Ada"]]}
    assert "majorDimension" not in body
    params = dict(route.calls.last.request.url.params)
    assert params == {"valueInputOption": "RAW"}


@respx.mock
async def test_values_clear_posts_an_empty_body():
    route = respx.post(f"{API}v4/spreadsheets/s1/values/Sheet1!A1:C10:clear").mock(
        return_value=httpx.Response(200, json={"clearedRange": "Sheet1!A1:C10"})
    )

    await gsheets.spreadsheets_values_clear.ainvoke(spreadsheet_id="s1", range="Sheet1!A1:C10")

    request = route.calls.last.request
    assert request.method == "POST"
    assert request.content in (b"", b"null", b"{}") or json.loads(request.content) == {}


@respx.mock
async def test_values_batch_get_repeats_ranges_under_the_documented_query_name():
    route = respx.get(f"{API}v4/spreadsheets/s1/values:batchGet").mock(
        return_value=httpx.Response(200, json={"valueRanges": []})
    )

    await gsheets.spreadsheets_values_batch_get.ainvoke(
        spreadsheet_id="s1",
        ranges=["Sheet1!A1:B2", "Sheet1!C1:D2"],
        value_render_option="FORMULA",
    )

    params = parse_qs(route.calls.last.request.url.query.decode())
    assert params["ranges"] == ["Sheet1!A1:B2", "Sheet1!C1:D2"]
    assert params["valueRenderOption"] == ["FORMULA"]
    assert "value_render_option" not in params


@respx.mock
async def test_values_batch_update_sends_camel_case_and_plain_arrays():
    route = respx.post(f"{API}v4/spreadsheets/s1/values:batchUpdate").mock(
        return_value=httpx.Response(200, json={"totalUpdatedCells": 2})
    )

    await gsheets.spreadsheets_values_batch_update.ainvoke(
        spreadsheet_id="s1",
        value_input_option="USER_ENTERED",
        data=[{"range": "Sheet1!A1", "values": [["Ada", "36"]]}],
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": "Sheet1!A1", "values": [["Ada", "36"]]}],
    }


@respx.mock
async def test_values_batch_clear_keeps_the_ranges_key():
    route = respx.post(f"{API}v4/spreadsheets/s1/values:batchClear").mock(
        return_value=httpx.Response(200, json={"clearedRanges": ["Sheet1!A1:B2"]})
    )

    await gsheets.spreadsheets_values_batch_clear.ainvoke(
        spreadsheet_id="s1", ranges=["Sheet1!A1:B2"]
    )

    assert json.loads(route.calls.last.request.content) == {"ranges": ["Sheet1!A1:B2"]}


@respx.mock
async def test_values_batch_get_by_data_filter_body_names():
    route = respx.post(f"{API}v4/spreadsheets/s1/values:batchGetByDataFilter").mock(
        return_value=httpx.Response(200, json={"valueRanges": []})
    )

    await gsheets.values_batch_get_by_data_filter.ainvoke(
        spreadsheet_id="s1",
        data_filters=[{"a1_range": "Sheet1!A1:B2"}],
        major_dimension="COLUMNS",
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {
        "dataFilters": [{"a1Range": "Sheet1!A1:B2"}],
        "majorDimension": "COLUMNS",
    }


@respx.mock
async def test_values_batch_update_by_data_filter_proto_json():
    route = respx.post(f"{API}v4/spreadsheets/s1/values:batchUpdateByDataFilter").mock(
        return_value=httpx.Response(200, json={"totalUpdatedCells": 1})
    )

    await gsheets.values_batch_update_by_data_filter.ainvoke(
        spreadsheet_id="s1",
        value_input_option="RAW",
        data=[
            {
                "data_filter": {"a1_range": "Sheet1!A1"},
                "values": [["Ada"]],
            }
        ],
    )

    body = json.loads(route.calls.last.request.content)
    assert body["valueInputOption"] == "RAW"
    assert body["data"] == [
        {
            "dataFilter": {"a1Range": "Sheet1!A1"},
            "values": [["Ada"]],
        }
    ]


@respx.mock
async def test_values_batch_clear_by_data_filter_keeps_the_key():
    route = respx.post(f"{API}v4/spreadsheets/s1/values:batchClearByDataFilter").mock(
        return_value=httpx.Response(200, json={"clearedRanges": ["Sheet1!A1:B2"]})
    )

    await gsheets.values_batch_clear_by_data_filter.ainvoke(
        spreadsheet_id="s1",
        data_filters=[{"a1_range": "Sheet1!A1:B2"}],
    )

    assert json.loads(route.calls.last.request.content) == {
        "dataFilters": [{"a1Range": "Sheet1!A1:B2"}]
    }


def _validate(tool: Tool, args: dict):
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


def test_the_request_union_covers_the_whole_editing_surface():
    """Seventy-four edits is what Google documents; a subset would be a lie."""
    assert len(Request.model_fields) == 74


def test_a_batch_request_setting_no_edit_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            gsheets.spreadsheets_batch_update,
            {"spreadsheet_id": "s1", "requests": [{}]},
        )


def test_a_batch_request_setting_two_edits_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            gsheets.spreadsheets_batch_update,
            {
                "spreadsheet_id": "s1",
                "requests": [
                    {
                        "add_sheet": {"properties": {"title": "A"}},
                        "delete_sheet": {"sheet_id": 0},
                    }
                ],
            },
        )


def test_an_unknown_edit_name_is_rejected_rather_than_ignored():
    with pytest.raises(ToolValidationError):
        _validate(
            gsheets.spreadsheets_batch_update,
            {"spreadsheet_id": "s1", "requests": [{"insert_emoji": {}}]},
        )


def test_a_well_formed_batch_passes():
    _validate(
        gsheets.spreadsheets_batch_update,
        {
            "spreadsheet_id": "s1",
            "requests": [
                {"add_sheet": {"properties": {"title": "Q3"}}},
                {
                    "repeat_cell": {
                        "range": {"sheet_id": 0, "start_row_index": 0, "end_row_index": 1},
                        "cell": {"user_entered_format": {"horizontal_alignment": "CENTER"}},
                        "fields": {"paths": ["userEnteredFormat.horizontalAlignment"]},
                    }
                },
            ],
        },
    )


def test_update_cells_area_oneof_is_enforced():
    for bad in (
        {"rows": [], "fields": {"paths": ["userEnteredValue"]}},
        {
            "rows": [],
            "fields": {"paths": ["userEnteredValue"]},
            "start": {"sheet_id": 0, "row_index": 0, "column_index": 0},
            "range": {"sheet_id": 0},
        },
    ):
        with pytest.raises(ToolValidationError):
            _validate(
                gsheets.spreadsheets_batch_update,
                {"spreadsheet_id": "s1", "requests": [{"update_cells": bad}]},
            )


def test_google_query_parameters_are_camel_cased():
    for tool in gsheets.TOOLS:
        assert tool.query_case == "camel", tool.name


# -----------------------------------------------------
# The spreadsheet resource, against the reference
# -----------------------------------------------------


def test_every_schema_in_the_pack_builds():
    """A type module that forgets an import produces a model nothing can use.

    ``responses.py`` used ``Annotated`` and ``Mode`` without importing either, so
    three models carried an unresolved forward reference: they imported, they
    exported, and they raised the moment anything asked for their schema. Nothing
    in the pack's tool graph reaches them, so nothing failed.
    """
    from pydantic import BaseModel

    from charter.packs.gsheets.types.spreadsheets import actions, models, requests, responses
    from charter.packs.gsheets.types.values import actions as v_actions
    from charter.packs.gsheets.types.values import models as v_models

    for module in (models, requests, responses, actions, v_models, v_actions):
        for obj in vars(module).values():
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                obj.model_json_schema()  # raises if a forward reference is unresolved


def test_chart_data_groups_and_aggregates_the_source_it_reads():
    """``group_rule`` and ``aggregate_type`` are not in the ``type`` union.

    The oneof holds ``source_range`` and ``column_reference`` alone; the other two
    say how a data source chart buckets and aggregates whichever it reads. Sweeping
    all four into one mutual exclusion rejected the documented shape locally, which
    is the failure a model cannot tell from the API refusing the call.
    """
    ChartData(
        source_range={"sources": [{"sheet_id": 0}]},
        group_rule={"histogram_rule": {"interval": 5}},
        aggregate_type="SUM",
    )

    with pytest.raises(ValidationError):
        ChartData(group_rule={"histogram_rule": {"interval": 5}})
    with pytest.raises(ValidationError):
        ChartData(
            source_range={"sources": [{"sheet_id": 0}]},
            column_reference={"name": "revenue"},
        )


def test_developer_metadata_location_is_a_union():
    DeveloperMetadataLocation(sheet_id=0)
    with pytest.raises(ValidationError):
        DeveloperMetadataLocation(spreadsheet=True, sheet_id=0)


@pytest.mark.parametrize(
    "model",
    [ChartSpec, ConditionValue, ConditionalFormatRule, EmbeddedObjectPosition, PivotValue],
)
def test_a_union_the_reference_calls_exactly_one_rejects_none(model):
    """``At most one`` accepts the empty object the API answers 400 for.

    Five of these read ``exactly one ... must be set`` in the reference and were
    enforced as ``at most one``, which is the round trip a local rule exists to
    avoid: the model sends a ChartSpec carrying a title and no chart, and learns
    why from Google rather than from the schema.
    """
    with pytest.raises(ValidationError):
        model()


def test_setting_two_members_of_such_a_union_is_still_rejected():
    ConditionValue(user_entered_value="10")
    with pytest.raises(ValidationError):
        ConditionValue(user_entered_value="10", relative_date="PAST_MONTH")
    EmbeddedObjectPosition(new_sheet=True)
    with pytest.raises(ValidationError):
        EmbeddedObjectPosition(new_sheet=True, sheet_id=0)


def test_a_post_offers_only_the_three_fields_a_caller_writes():
    """Eight of Post's eleven fields are ``Output only`` in the reference."""
    entry = egress_map(gsheets.TOOLS)["gsheets__spreadsheets_create"]
    prefix = "spreadsheet.comments.head_post."

    visible = {f[len(prefix) :] for f in entry["visible"] if f.startswith(prefix)}
    withheld = {
        e["field"][len(prefix) :] for e in entry["withheld"] if e["field"].startswith(prefix)
    }

    assert visible == {"content", "assignee_email", "comment_action"}
    assert withheld == {
        "post_id",
        "content_html",
        "author",
        "create_time",
        "update_time",
        "deleted",
        "from_imported_spreadsheet",
        "from_copied_spreadsheet",
    }
    # ...and the wire model still carries every one of them.
    assert len(Post.model_fields) == 11


def test_post_content_carries_the_documented_length_limit():
    Post(content="x" * 2048)
    with pytest.raises(ValidationError):
        Post(content="x" * 2049)
    with pytest.raises(ValidationError):
        Post(assignee_email="x" * 2049)


def test_the_preview_comment_surface_is_modelled():
    """``comments``, ``commentsViewMode`` and ``commentAnchors`` were all missing."""
    Spreadsheet(comments=[{"comment_id": "c1", "head_post": {"content": "hi"}}])
    Sheet(comment_anchors=[{"range": {"sheet_id": 0}}])
    CommentAnchor(range={"sheet_id": 0})

    withheld = {
        entry["field"]
        for entry in egress_map(gsheets.TOOLS)["gsheets__spreadsheets_create"]["withheld"]
    }
    assert "spreadsheet.comments_view_mode" in withheld
    assert "spreadsheet.sheets.comment_anchors.anchor_id" in withheld


@respx.mock
async def test_copy_to_unwraps_the_destination_id_under_the_documented_key():
    route = respx.post(f"{API}v4/spreadsheets/src/sheets/0:copyTo").mock(
        return_value=httpx.Response(200, json={"sheetId": 1, "title": "Sheet1"})
    )

    await gsheets.spreadsheets_sheets_copy_to.ainvoke(
        spreadsheet_id="src",
        sheet_id=0,
        body={"destination_spreadsheet_id": "dst"},
    )

    request = route.calls.last.request
    assert request.method == "POST"
    assert json.loads(request.content) == {"destinationSpreadsheetId": "dst"}


@respx.mock
async def test_get_by_data_filter_posts_camel_case_filters():
    route = respx.post(f"{API}v4/spreadsheets/s1:getByDataFilter").mock(
        return_value=httpx.Response(200, json=spreadsheet())
    )

    await gsheets.spreadsheets_get_by_data_filter.ainvoke(
        spreadsheet_id="s1",
        data_filters=[{"a1_range": "Sheet1!A1:B2"}],
        include_grid_data=True,
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {
        "dataFilters": [{"a1Range": "Sheet1!A1:B2"}],
        "includeGridData": True,
    }


@respx.mock
async def test_get_repeats_ranges_under_the_documented_query_name():
    route = respx.get(f"{API}v4/spreadsheets/s1").mock(
        return_value=httpx.Response(200, json=spreadsheet())
    )

    await gsheets.spreadsheets_get.ainvoke(
        spreadsheet_id="s1",
        ranges=["Sheet1!A1:B2", "Sheet2!A1"],
        include_grid_data=True,
    )

    params = parse_qs(route.calls.last.request.url.query.decode())
    assert params["ranges"] == ["Sheet1!A1:B2", "Sheet2!A1"]
    assert params["includeGridData"] == ["true"]
    assert "include_grid_data" not in params


@respx.mock
async def test_batch_update_omits_preview_comments_view_mode_when_unset():
    route = respx.post(f"{API}v4/spreadsheets/s1:batchUpdate").mock(
        return_value=httpx.Response(200, json={"spreadsheetId": "s1", "replies": [{}]})
    )

    await gsheets.spreadsheets_batch_update.ainvoke(
        spreadsheet_id="s1",
        requests=[{"add_sheet": {"properties": {"title": "New"}}}],
    )

    body = json.loads(route.calls.last.request.content)
    assert body == {"requests": [{"addSheet": {"properties": {"title": "New"}}}]}
    assert "commentsViewMode" not in body


@respx.mock
async def test_developer_metadata_get_interpolates_both_path_parts():
    route = respx.get(f"{API}v4/spreadsheets/s1/developerMetadata/7").mock(
        return_value=httpx.Response(200, json={"metadataId": 7, "metadataKey": "owner"})
    )

    result = await gsheets.spreadsheets_developer_metadata_get.ainvoke(
        spreadsheet_id="s1", metadata_id=7
    )

    assert route.calls.last.request.content == b""
    assert result["metadataKey"] == "owner"


@respx.mock
async def test_developer_metadata_search_keeps_its_body_key():
    """One ``Body()`` field is unwrapped to the root — here that posts a bare array.

    ``Body(envelop=True)`` is what keeps ``dataFilters`` as the object key the
    reference documents.
    """
    route = respx.post(f"{API}v4/spreadsheets/s1/developerMetadata:search").mock(
        return_value=httpx.Response(200, json={"matchedDeveloperMetadata": []})
    )

    await gsheets.spreadsheets_developer_metadata_search.ainvoke(
        spreadsheet_id="s1",
        data_filters=[{"developer_metadata_lookup": {"metadata_key": "owner"}}],
    )

    assert json.loads(route.calls.last.request.content) == {
        "dataFilters": [{"developerMetadataLookup": {"metadataKey": "owner"}}]
    }


@respx.mock
async def test_create_with_only_a_title_unwraps_the_spreadsheet():
    route = respx.post(f"{API}v4/spreadsheets").mock(
        return_value=httpx.Response(200, json=spreadsheet())
    )

    await gsheets.spreadsheets_create.ainvoke(spreadsheet={"properties": {"title": "Q3"}})

    assert json.loads(route.calls.last.request.content) == {"properties": {"title": "Q3"}}


@respx.mock
async def test_batch_update_trims_the_spreadsheet_it_is_asked_to_return():
    """include_spreadsheet_in_response sends back the resource with its theme."""
    raw = {
        "spreadsheetId": "S1",
        "replies": [{}, {"addSheet": {"properties": {"sheetId": 2, "title": "Q3"}}}],
        "updatedSpreadsheet": {
            "spreadsheetId": "S1",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/S1/edit",
            "properties": {
                "title": "Books",
                "locale": "en_US",
                "timeZone": "Europe/London",
                "autoRecalc": "ON_CHANGE",
                "defaultFormat": {
                    "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                    "padding": {"top": 2, "right": 3, "bottom": 2, "left": 3},
                    "textFormat": {"fontFamily": "arial,sans,sans-serif", "fontSize": 10},
                    "verticalAlignment": "BOTTOM",
                    "wrapStrategy": "OVERFLOW_CELL",
                },
                "spreadsheetTheme": {
                    "primaryFontFamily": "Arial",
                    "themeColors": [
                        {"colorType": t, "color": {"rgbColor": {"red": 0.1}}}
                        for t in (
                            "TEXT",
                            "BACKGROUND",
                            "ACCENT1",
                            "ACCENT2",
                            "ACCENT3",
                            "ACCENT4",
                            "ACCENT5",
                            "ACCENT6",
                            "LINK",
                        )
                    ],
                },
            },
            "sheets": [
                {
                    "properties": {
                        "sheetId": 0,
                        "title": "Sheet1",
                        "index": 0,
                        "sheetType": "GRID",
                        "gridProperties": {"rowCount": 1000, "columnCount": 26},
                    }
                }
            ],
        },
    }
    respx.post(f"{API}v4/spreadsheets/S1:batchUpdate").mock(
        return_value=httpx.Response(200, json=raw)
    )

    result = await gsheets.spreadsheets_batch_update.ainvoke(
        spreadsheet_id="S1",
        requests=[{"add_sheet": {"properties": {"title": "Q3"}}}],
        include_spreadsheet_in_response=True,
    )

    # The replies are the answer and pass through, positions intact.
    assert result["replies"][1]["addSheet"]["properties"]["title"] == "Q3"
    assert result["replies"][0] == {}
    # The resource is trimmed the way spreadsheets.get trims it.
    assert result["updatedSpreadsheet"]["properties"] == {
        "title": "Books",
        "locale": "en_US",
        "timeZone": "Europe/London",
    }
    assert "spreadsheetTheme" not in json.dumps(result)
    assert "defaultFormat" not in json.dumps(result)


@respx.mock
async def test_batch_update_without_the_flag_is_just_the_replies():
    raw = {"spreadsheetId": "S1", "replies": [{}]}
    respx.post(f"{API}v4/spreadsheets/S1:batchUpdate").mock(
        return_value=httpx.Response(200, json=raw)
    )
    result = await gsheets.spreadsheets_batch_update.ainvoke(
        spreadsheet_id="S1", requests=[{"add_sheet": {"properties": {"title": "Q4"}}}]
    )
    assert result == {"spreadsheetId": "S1", "replies": [{}]}
