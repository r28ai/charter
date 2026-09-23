"""Google Docs pack — the widest schema here, and the oneof that must survive it."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from charter import Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.packs import gdocs
from charter.packs.gdocs.types.requests import Request

API = "https://docs.googleapis.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gdocs.configure(StaticTokenProvider("tok"))


def _validate(tool: Tool, args: Dict[str, Any]):
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_three_tools():
    assert len(gdocs.TOOLS) == 3
    assert {t.name for t in gdocs.TOOLS} == {
        "documents_get",
        "documents_create",
        "documents_batch_update",
    }


def test_every_tool_builds_its_schemas():
    for tool in gdocs.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_the_request_union_covers_the_whole_editing_surface():
    """Thirty-three edits is what Google documents; a subset would be a lie."""
    assert len(Request.model_fields) == 33


def test_google_query_parameters_are_camel_cased():
    """`include_tabs_content` would be silently ignored by Google."""
    for tool in gdocs.TOOLS:
        assert tool.query_case == "camel", tool.name


# -----------------------------------------------------
# The oneof, which used to be dropped
# -----------------------------------------------------


def test_a_batch_request_setting_no_edit_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            gdocs.documents_batch_update,
            {"document_id": "d1", "body": {"requests": [{}]}},
        )


def test_a_batch_request_setting_two_edits_is_rejected():
    """Google answers this with a 400 and no useful detail. Charter answers locally."""
    with pytest.raises(ToolValidationError):
        _validate(
            gdocs.documents_batch_update,
            {
                "document_id": "d1",
                "body": {
                    "requests": [
                        {
                            "insert_text": {"text": "a", "location": {"index": 1}},
                            "delete_content_range": {"range": {"start_index": 1, "end_index": 2}},
                        }
                    ]
                },
            },
        )


def test_an_unknown_edit_name_is_rejected_rather_than_ignored():
    """`Request` declares extra='forbid'; that must survive into the LLM view.

    Without it a typo — `insertText` misspelled, an invented edit — would be
    dropped silently, and the batch would apply nothing while reporting success.
    """
    with pytest.raises(ToolValidationError):
        _validate(
            gdocs.documents_batch_update,
            {"document_id": "d1", "body": {"requests": [{"insert_emoji": {"text": "x"}}]}},
        )


def test_the_nested_oneof_inside_an_edit_is_also_enforced():
    """insert_text takes a location OR an end_of_segment_location, never both."""
    for bad in (
        {"text": "hello"},
        {
            "text": "hello",
            "location": {"index": 1},
            "end_of_segment_location": {"segment_id": ""},
        },
    ):
        with pytest.raises(ToolValidationError):
            _validate(
                gdocs.documents_batch_update,
                {"document_id": "d1", "body": {"requests": [{"insert_text": bad}]}},
            )


def test_a_well_formed_batch_passes():
    _validate(
        gdocs.documents_batch_update,
        {
            "document_id": "d1",
            "body": {
                "requests": [
                    {"insert_text": {"text": "Hello", "location": {"index": 1}}},
                    {
                        "replace_all_text": {
                            "replace_text": "2026",
                            "contains_text": {"text": "2025", "match_case": True},
                        }
                    },
                ]
            },
        },
    )


# -----------------------------------------------------
# The wire
# -----------------------------------------------------


@respx.mock
async def test_batch_update_posts_to_the_colon_suffixed_url():
    route = respx.post(f"{API}v1/documents/doc123:batchUpdate").mock(
        return_value=httpx.Response(200, json={"documentId": "doc123", "replies": [{}]})
    )

    await gdocs.documents_batch_update.ainvoke(
        document_id="doc123",
        body={"requests": [{"insert_text": {"text": "Hello", "location": {"index": 1}}}]},
    )

    assert route.called
    assert route.calls.last.request.url.path == "/v1/documents/doc123:batchUpdate"


@respx.mock
async def test_edits_arrive_camel_cased_as_google_expects():
    route = respx.post(f"{API}v1/documents/d1:batchUpdate").mock(
        return_value=httpx.Response(200, json={})
    )

    await gdocs.documents_batch_update.ainvoke(
        document_id="d1",
        body={
            "requests": [
                {
                    "insert_text": {
                        "text": "Hello",
                        "end_of_segment_location": {"segment_id": ""},
                    }
                },
                {
                    "update_text_style": {
                        "text_style": {"bold": True},
                        "fields": "bold",
                        "range": {"start_index": 1, "end_index": 6},
                    }
                },
            ],
            "write_control": {"required_revision_id": "rev-1"},
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["requests"][0] == {
        "insertText": {"text": "Hello", "endOfSegmentLocation": {"segmentId": ""}}
    }
    assert sent["requests"][1]["updateTextStyle"]["textStyle"] == {"bold": True}
    assert sent["requests"][1]["updateTextStyle"]["range"] == {
        "startIndex": 1,
        "endIndex": 6,
    }
    assert sent["writeControl"] == {"requiredRevisionId": "rev-1"}


@respx.mock
async def test_documents_get_sends_its_query_parameters_camel_cased():
    route = respx.get(f"{API}v1/documents/d1").mock(
        return_value=httpx.Response(200, json={"documentId": "d1"})
    )

    await gdocs.documents_get.ainvoke(
        document_id="d1",
        include_tabs_content=True,
        suggestions_view_mode="PREVIEW_WITHOUT_SUGGESTIONS",
    )

    params = dict(route.calls.last.request.url.params)
    assert params == {
        "includeTabsContent": "true",
        "suggestionsViewMode": "PREVIEW_WITHOUT_SUGGESTIONS",
    }


@respx.mock
async def test_documents_create_sends_only_the_title():
    route = respx.post(f"{API}v1/documents").mock(
        return_value=httpx.Response(200, json={"documentId": "new", "title": "Q3 review"})
    )

    await gdocs.documents_create.ainvoke(body={"title": "Q3 review"})

    assert json.loads(route.calls.last.request.content) == {"title": "Q3 review"}


# -----------------------------------------------------
# Context cost — measured, since it decides whether this is usable
# -----------------------------------------------------


def test_the_batch_update_schema_is_large_and_we_know_by_how_much():
    """Complete coverage of a 33-member union is not free.

    ~31KB of JSON schema is roughly 8,000 tokens spent before the model reads
    the task. The number is asserted loosely so it fails if the schema doubles,
    which is the change worth noticing.
    """
    size = len(json.dumps(gdocs.documents_batch_update.to_json_schema()))
    assert 20_000 < size < 45_000, f"batchUpdate schema is now {size} chars"


def test_the_other_two_tools_stay_small():
    for tool in (gdocs.documents_get, gdocs.documents_create):
        assert len(json.dumps(tool.to_json_schema())) < 3_000, tool.name


# -----------------------------------------------------
# Egress
# -----------------------------------------------------


def test_the_model_is_never_shown_a_server_set_field():
    for tool in gdocs.TOOLS:
        fields = set(tool.llm_schema().model_fields)
        assert not fields & {"document_id_out", "revision_id", "suggestions_view_mode_out"}
    create = set(gdocs.documents_create.llm_schema().model_fields["body"].annotation.model_fields)
    # documents.create honours only the title; nothing else should be offered.
    assert create == {"title"}


# -----------------------------------------------------
# Trimming
# -----------------------------------------------------
#
# This pack shipped without response handlers. An *empty* document came back at
# 10,502 bytes, of which namedStyles was 4,210 and a duplicate `tabs` block
# another 5,161; documents_get and documents_create were together about a
# quarter of the whole context budget of a 760-run harness campaign.


def _doc(content, **top):
    """A document in the shape Docs actually returns."""
    payload = {
        "title": "trim-probe",
        "documentId": "1HTY-E5LGMXtG8YguQDEIaEFZ2YsFMST",
        "revisionId": "ANLCKQn3sOrHuAZkcysA52uB31qkce5s",
        "suggestionsViewMode": "PREVIEW_WITHOUT_SUGGESTIONS",
        "documentStyle": {
            "background": {"color": {}},
            "pageSize": {
                "height": {"magnitude": 841.8, "unit": "PT"},
                "width": {"magnitude": 595.2, "unit": "PT"},
            },
            "marginTop": {"magnitude": 72, "unit": "PT"},
        },
        "namedStyles": {
            "styles": [
                {
                    "namedStyleType": f"HEADING_{i}",
                    "textStyle": {
                        "fontSize": {"magnitude": 20 - i, "unit": "PT"},
                        "weightedFontFamily": {"fontFamily": "Arial", "weight": 400},
                    },
                    "paragraphStyle": {"direction": "LEFT_TO_RIGHT", "spaceAbove": {"unit": "PT"}},
                }
                for i in range(1, 7)
            ]
        },
        "body": {"content": content},
    }
    payload.update(top)
    return payload


def _para(start, end, text, style="NORMAL_TEXT", **extra):
    run = {
        "startIndex": start,
        "endIndex": end,
        "textRun": {"content": text, "textStyle": extra.pop("textStyle", {})},
    }
    return {
        "startIndex": start,
        "endIndex": end,
        "paragraph": {
            "elements": [run],
            "paragraphStyle": {"namedStyleType": style, "direction": "LEFT_TO_RIGHT"},
            **extra,
        },
    }


@respx.mock
async def test_get_keeps_the_text_and_drops_the_typography():
    doc = _doc(
        [
            {"endIndex": 1, "sectionBreak": {"sectionStyle": {"sectionType": "CONTINUOUS"}}},
            _para(1, 20, "Deployment Runbook\n", "HEADING_1"),
            _para(20, 71, "Freeze merges. Tag the release.\n"),
        ]
    )
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    result = await gdocs.documents_get.ainvoke(document_id="d1")

    assert result["title"] == "trim-probe"
    assert result["documentId"] == "1HTY-E5LGMXtG8YguQDEIaEFZ2YsFMST"
    assert [c["text"] for c in result["content"]] == [
        "Deployment Runbook\n",
        "Freeze merges. Tag the release.\n",
    ]

    for dropped in ("namedStyles", "documentStyle", "suggestionsViewMode", "body"):
        assert dropped not in result, dropped


@respx.mock
async def test_edits_remain_possible_because_indices_survive():
    """batchUpdate addresses text by character index; trimming it away would
    read nicely and make the document uneditable."""
    doc = _doc([_para(1, 20, "Deployment Runbook\n"), _para(20, 71, "Freeze merges.\n")])
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    result = await gdocs.documents_get.ainvoke(document_id="d1")

    assert result["content"][0]["startIndex"] == 1
    assert result["content"][0]["endIndex"] == 20
    assert result["endIndex"] == 71  # where an append goes
    assert result["revisionId"], "batchUpdate takes this as a write precondition"


@respx.mock
async def test_a_heading_keeps_its_style_and_body_text_does_not():
    doc = _doc([_para(1, 10, "Title\n", "HEADING_1"), _para(10, 20, "Body\n", "NORMAL_TEXT")])
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    content = (await gdocs.documents_get.ainvoke(document_id="d1"))["content"]
    assert content[0]["style"] == "HEADING_1"
    assert "style" not in content[1]


@respx.mock
async def test_a_link_is_content_and_survives_the_style_it_lives_in():
    doc = _doc([_para(1, 10, "the runbook", textStyle={"link": {"url": "https://example.com/rb"}})])
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    content = (await gdocs.documents_get.ainvoke(document_id="d1"))["content"]
    assert content[0]["links"] == [{"text": "the runbook", "url": "https://example.com/rb"}]


@respx.mock
async def test_a_table_becomes_rows_of_cell_text():
    def cell(text):
        return {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": text, "textStyle": {}}}]}}
            ]
        }

    table = {
        "startIndex": 1,
        "endIndex": 40,
        "table": {
            "tableRows": [
                {"tableCells": [cell("Name"), cell("Owner")]},
                {"tableCells": [cell("billing"), cell("Sam")]},
            ]
        },
    }
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=_doc([table])))

    content = (await gdocs.documents_get.ainvoke(document_id="d1"))["content"]
    assert content[0]["table"] == [["Name", "Owner"], ["billing", "Sam"]]


@respx.mock
async def test_tabs_are_trimmed_not_dropped():
    """documents_get advertises include_tabs_content, so tab text must survive;
    what must not is the 4KB of typography each tab repeats."""
    doc = _doc(
        [_para(1, 5, "a\n")],
        tabs=[
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1", "index": 0},
                "documentTab": {
                    "body": {"content": [_para(1, 12, "Second tab\n")]},
                    "namedStyles": {"styles": [{"namedStyleType": "HEADING_1"}] * 6},
                    "documentStyle": {"marginTop": {"magnitude": 72}},
                },
            }
        ],
    )
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    tabs = (await gdocs.documents_get.ainvoke(document_id="d1"))["tabs"]
    assert tabs[0]["tabId"] == "t.0"
    assert tabs[0]["content"][0]["text"] == "Second tab\n"
    assert "namedStyles" not in json.dumps(tabs)


@respx.mock
async def test_trimming_is_a_large_reduction():
    """Context economy is the point; a regression here is the defect."""
    doc = _doc([_para(i * 10 + 1, i * 10 + 11, f"line {i}\n") for i in range(40)])
    respx.get(f"{API}v1/documents/d1").mock(return_value=httpx.Response(200, json=doc))

    result = await gdocs.documents_get.ainvoke(document_id="d1")
    before, after = len(json.dumps(doc)), len(json.dumps(result))
    assert len(result["content"]) == 40
    assert after < before * 0.55, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_create_returns_the_id_the_caller_needs_next():
    respx.post(f"{API}v1/documents").mock(return_value=httpx.Response(200, json=_doc([])))
    result = await gdocs.documents_create.ainvoke(body={"title": "trim-probe"})
    assert result["documentId"] == "1HTY-E5LGMXtG8YguQDEIaEFZ2YsFMST"
    assert "namedStyles" not in result
