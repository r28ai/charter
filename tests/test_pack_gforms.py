"""Google Forms pack — six endpoints, two collections, and one resource whose
required fields depend on which of them you are calling."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from charter import Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.packs import gforms
from charter.packs.gforms.types.form_responses.models import FormResponse
from charter.packs.gforms.types.forms.models import Form, Image, Item, Question
from charter.packs.gforms.types.forms.requests import Request

API = "https://forms.googleapis.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gforms.configure(StaticTokenProvider("tok"))


def _validate(tool: Tool, args: Dict[str, Any]):
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


def _text_item(title: str = "How did it go?") -> Dict[str, Any]:
    return {"title": title, "question_item": {"question": {"text_question": {}}}}


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_six_tools():
    assert len(gforms.TOOLS) == 6
    assert {t.name for t in gforms.TOOLS} == {
        "forms_create",
        "forms_get",
        "forms_batch_update",
        "forms_set_publish_settings",
        "forms_responses_get",
        "forms_responses_list",
    }


def test_every_tool_builds_its_schemas():
    for tool in gforms.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_the_request_union_covers_every_documented_edit():
    """Six kinds is what Google documents; a subset would be a lie."""
    assert set(Request.model_fields) == {
        "update_form_info",
        "update_settings",
        "create_item",
        "move_item",
        "delete_item",
        "update_item",
    }


def test_the_item_union_covers_every_documented_kind():
    assert {
        "question_item",
        "question_group_item",
        "page_break_item",
        "text_item",
        "image_item",
        "video_item",
    } <= set(Item.model_fields)


def test_the_question_union_covers_every_documented_kind():
    assert {
        "choice_question",
        "text_question",
        "scale_question",
        "date_question",
        "time_question",
        "file_upload_question",
        "row_question",
        "rating_question",
    } <= set(Question.model_fields)


def test_google_query_parameters_are_camel_cased():
    """`page_token` would be accepted, ignored, and return page one forever."""
    for tool in gforms.TOOLS:
        assert tool.query_case == "camel", tool.name


def test_only_the_list_endpoint_declares_pagination():
    paging = {t.name for t in gforms.TOOLS if t.pagination is not None}
    assert paging == {"forms_responses_list"}


def test_reading_responses_asks_for_the_scope_the_body_scope_does_not_cover():
    """`forms.body` does not reach the responses collection. Two tools say so."""
    for tool in (gforms.forms_responses_get, gforms.forms_responses_list):
        assert tool.scopes == ["https://www.googleapis.com/auth/forms.responses.readonly"]
    for tool in (gforms.forms_create, gforms.forms_get, gforms.forms_batch_update):
        assert tool.scopes == ["https://www.googleapis.com/auth/forms.body"]


# -----------------------------------------------------
# Enums, asserted against Google's values rather than against themselves
# -----------------------------------------------------


def _literal_values(model, field: str):
    """The string set of a Literal, however it is wrapped.

    `Optional[Literal[...]]` and `Optional[List[Literal[...]]]` both occur, so
    the search is a walk rather than one unwrapping.
    """
    from typing import get_args

    def find(annotation):
        values = get_args(annotation)
        if values and all(isinstance(v, str) for v in values):
            return set(values)
        for inner in values:
            found = find(inner)
            if found:
                return found
        return None

    found = find(model.model_fields[field].annotation)
    assert found, f"{model.__name__}.{field} is not a Literal"
    return found


def test_every_closed_enum_holds_the_full_documented_set():
    from charter.packs.gforms.types.forms.models import (
        ChoiceQuestion,
        FileUploadQuestion,
        FormSettings,
        MediaProperties,
        Option,
        RatingQuestion,
    )

    assert _literal_values(ChoiceQuestion, "type") == {
        "CHOICE_TYPE_UNSPECIFIED",
        "RADIO",
        "CHECKBOX",
        "DROP_DOWN",
    }
    assert _literal_values(Option, "go_to_action") == {
        "GO_TO_ACTION_UNSPECIFIED",
        "NEXT_SECTION",
        "RESTART_FORM",
        "SUBMIT_FORM",
    }
    assert _literal_values(MediaProperties, "alignment") == {
        "ALIGNMENT_UNSPECIFIED",
        "LEFT",
        "RIGHT",
        "CENTER",
    }
    assert _literal_values(RatingQuestion, "icon_type") == {
        "RATING_ICON_TYPE_UNSPECIFIED",
        "STAR",
        "HEART",
        "THUMB_UP",
    }
    assert _literal_values(FormSettings, "email_collection_type") == {
        "EMAIL_COLLECTION_TYPE_UNSPECIFIED",
        "DO_NOT_COLLECT",
        "VERIFIED",
        "RESPONDER_INPUT",
    }
    assert _literal_values(FileUploadQuestion, "types") == {
        "FILE_TYPE_UNSPECIFIED",
        "ANY",
        "DOCUMENT",
        "PRESENTATION",
        "SPREADSHEET",
        "DRAWING",
        "PDF",
        "IMAGE",
        "VIDEO",
        "AUDIO",
    }


# -----------------------------------------------------
# The oneofs, enforced against the input the model actually fills in
# -----------------------------------------------------


def test_a_batch_request_setting_no_edit_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(gforms.forms_batch_update, {"form_id": "f1", "body": {"requests": [{}]}})


def test_a_batch_request_setting_two_edits_is_rejected():
    """Google answers this with a 400 and no useful detail. Charter answers locally."""
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {
                "form_id": "f1",
                "body": {
                    "requests": [
                        {
                            "delete_item": {"location": {"index": 0}},
                            "move_item": {
                                "original_location": {"index": 0},
                                "new_location": {"index": 1},
                            },
                        }
                    ]
                },
            },
        )


def test_an_unknown_edit_name_is_rejected_rather_than_ignored():
    """`Request` declares extra='forbid'; that must survive into the LLM view."""
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {"form_id": "f1", "body": {"requests": [{"duplicate_item": {"index": 1}}]}},
        )


def test_an_item_with_no_kind_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {
                "form_id": "f1",
                "body": {
                    "requests": [
                        {"create_item": {"item": {"title": "x"}, "location": {"index": 0}}}
                    ]
                },
            },
        )


def test_a_question_with_two_kinds_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {
                "form_id": "f1",
                "body": {
                    "requests": [
                        {
                            "create_item": {
                                "item": {
                                    "title": "x",
                                    "question_item": {
                                        "question": {
                                            "text_question": {},
                                            "date_question": {"include_year": True},
                                        }
                                    },
                                },
                                "location": {"index": 0},
                            }
                        }
                    ]
                },
            },
        )


def test_a_location_with_no_index_is_rejected():
    """`where` is a required union with one member, so an empty location is a 400."""
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {"form_id": "f1", "body": {"requests": [{"delete_item": {"location": {}}}]}},
        )


def test_the_two_write_controls_cannot_be_sent_together():
    """`control` is a oneof, declared as a ConflictsWith rather than written out."""
    with pytest.raises(ToolValidationError) as excinfo:
        _validate(
            gforms.forms_batch_update,
            {
                "form_id": "f1",
                "body": {
                    "requests": [{"delete_item": {"location": {"index": 0}}}],
                    "write_control": {
                        "required_revision_id": "r1",
                        "target_revision_id": "r0",
                    },
                },
            },
        )
    assert "requiredRevisionId" in str(excinfo.value)


def test_an_option_cannot_navigate_two_ways_at_once():
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_batch_update,
            {
                "form_id": "f1",
                "body": {
                    "requests": [
                        {
                            "create_item": {
                                "item": {
                                    "title": "Pick one",
                                    "question_item": {
                                        "question": {
                                            "choice_question": {
                                                "type": "RADIO",
                                                "options": [
                                                    {
                                                        "value": "Yes",
                                                        "go_to_action": "NEXT_SECTION",
                                                        "go_to_section_id": "abc",
                                                    }
                                                ],
                                            }
                                        }
                                    },
                                },
                                "location": {"index": 0},
                            }
                        }
                    ]
                },
            },
        )


def test_accepting_responses_while_unpublished_is_refused_locally():
    """Google documents this combination as an error. It never has to leave."""
    with pytest.raises(ToolValidationError):
        _validate(
            gforms.forms_set_publish_settings,
            {
                "form_id": "f1",
                "body": {
                    "publish_settings": {
                        "publish_state": {
                            "is_published": False,
                            "is_accepting_responses": True,
                        }
                    }
                },
            },
        )


def test_unpublishing_entirely_is_allowed():
    _validate(
        gforms.forms_set_publish_settings,
        {
            "form_id": "f1",
            "body": {
                "publish_settings": {
                    "publish_state": {
                        "is_published": False,
                        "is_accepting_responses": False,
                    }
                }
            },
        },
    )


def test_a_well_formed_batch_passes():
    _validate(
        gforms.forms_batch_update,
        {
            "form_id": "f1",
            "body": {
                "requests": [
                    {"create_item": {"item": _text_item(), "location": {"index": 0}}},
                    {
                        "update_form_info": {
                            "info": {"description": "Filled in after the release."},
                            "update_mask": ["description"],
                        }
                    },
                ]
            },
        },
    )


# -----------------------------------------------------
# One resource, two operations that disagree about it
# -----------------------------------------------------


def test_update_form_info_does_not_demand_a_title():
    """Changing only the description must not mean reading the form to echo its
    title back. `Info.title` is Required on the resource and the masked update
    relaxes it — which is what `partial_of` is for."""
    info = (
        gforms.forms_batch_update.llm_schema()
        .model_fields["body"]
        .annotation.model_fields["requests"]
        .annotation.__args__[0]
        .model_fields["update_form_info"]
    )
    update_info = _optional_model(info).model_fields["info"]
    assert not _optional_model(update_info).model_fields["title"].is_required()


def _optional_model(field):
    """The model behind an `Optional[Model]` field."""
    from typing import get_args

    annotation = field.annotation
    for candidate in (annotation, *get_args(annotation)):
        if hasattr(candidate, "model_fields"):
            return candidate
    raise AssertionError(f"no model on {field}")


def test_create_is_offered_the_document_title_and_not_the_description():
    """forms.create copies the document title and refuses the description."""
    body = gforms.forms_create.llm_schema().model_fields["body"].annotation
    info = body.model_fields["info"].annotation
    assert "document_title" in info.model_fields
    assert "description" not in info.model_fields


def test_batch_update_is_offered_the_description_and_not_the_document_title():
    """A batchUpdate cannot modify documentTitle; Drive owns it."""
    schema = json.dumps(gforms.forms_batch_update.to_json_schema())
    assert "documentTitle" not in schema
    assert "description" in schema


# -----------------------------------------------------
# Egress
# -----------------------------------------------------


def test_the_model_is_never_shown_a_server_set_field():
    schema = json.dumps([t.to_json_schema() for t in gforms.TOOLS])
    for withheld in ("contentUri", "revisionId", "responderUri", "linkedSheetId"):
        assert withheld not in schema, withheld


def test_the_response_only_markers_are_declared_where_google_says_output_only():
    assert _withheld(Image, "content_uri")
    for name in ("form_id", "revision_id", "responder_uri", "linked_sheet_id"):
        assert _withheld(Form, name), name
    for name in FormResponse.model_fields:
        assert _withheld(FormResponse, name), name


def _withheld(model, field: str) -> bool:
    from charter.types import Mode

    return any(
        isinstance(m, Mode) and "response_only" in m.modes
        for m in model.model_fields[field].metadata
    )


def test_the_egress_map_names_the_reason_for_every_withheld_field():
    from charter import egress_map

    reasons = {
        entry["reason"]
        for tool in egress_map(gforms.TOOLS).values()
        for entry in tool.get("withheld", [])
    }
    assert reasons <= {"response_only", "mode=create", "mode=update"}


# -----------------------------------------------------
# The wire
# -----------------------------------------------------


@respx.mock
async def test_create_posts_only_the_info_google_honours():
    route = respx.post(f"{API}v1/forms").mock(
        return_value=httpx.Response(200, json={"formId": "f1"})
    )

    await gforms.forms_create.ainvoke(
        body={"info": {"title": "Q3 survey", "document_title": "q3-survey"}},
        unpublished=True,
    )

    assert json.loads(route.calls.last.request.content) == {
        "info": {"title": "Q3 survey", "documentTitle": "q3-survey"}
    }
    assert dict(route.calls.last.request.url.params) == {"unpublished": "true"}


@respx.mock
async def test_the_no_argument_call_sends_nothing_it_was_not_asked_to():
    """Everything the schema defaults into a request shows up on this line."""
    route = respx.get(f"{API}v1/forms/f1/responses").mock(
        return_value=httpx.Response(200, json={"responses": []})
    )

    await gforms.forms_responses_list.ainvoke(form_id="f1")

    request = route.calls.last.request
    assert request.url.params == httpx.QueryParams()
    assert not request.content


@respx.mock
async def test_list_sends_googles_own_query_parameter_names():
    """`page_size` would be accepted, ignored, and return the default page."""
    route = respx.get(f"{API}v1/forms/f1/responses").mock(
        return_value=httpx.Response(200, json={"responses": []})
    )

    await gforms.forms_responses_list.ainvoke(
        form_id="f1",
        filter="timestamp >= 2026-01-01T00:00:00Z",
        page_size=100,
        page_token="tok-2",
    )

    assert dict(route.calls.last.request.url.params) == {
        "filter": "timestamp >= 2026-01-01T00:00:00Z",
        "pageSize": "100",
        "pageToken": "tok-2",
    }


@respx.mock
async def test_batch_update_posts_to_the_colon_suffixed_url_camel_cased():
    route = respx.post(f"{API}v1/forms/f1:batchUpdate").mock(
        return_value=httpx.Response(200, json={"replies": [{}]})
    )

    await gforms.forms_batch_update.ainvoke(
        form_id="f1",
        body={
            "include_form_in_response": True,
            "requests": [
                {
                    "create_item": {
                        "item": {
                            "title": "Pick one",
                            "question_item": {
                                "question": {
                                    "required": True,
                                    "choice_question": {
                                        "type": "RADIO",
                                        "options": [{"value": "Yes"}, {"value": "No"}],
                                    },
                                }
                            },
                        },
                        "location": {"index": 0},
                    }
                }
            ],
            "write_control": {"required_revision_id": "rev-1"},
        },
    )

    assert route.calls.last.request.url.path == "/v1/forms/f1:batchUpdate"
    sent = json.loads(route.calls.last.request.content)
    assert sent["includeFormInResponse"] is True
    assert sent["writeControl"] == {"requiredRevisionId": "rev-1"}
    assert sent["requests"][0]["createItem"] == {
        "item": {
            "title": "Pick one",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [{"value": "Yes"}, {"value": "No"}],
                    },
                }
            },
        },
        "location": {"index": 0},
    }


@respx.mock
async def test_set_publish_settings_posts_to_its_colon_suffixed_url():
    route = respx.post(f"{API}v1/forms/f1:setPublishSettings").mock(
        return_value=httpx.Response(200, json={"formId": "f1"})
    )

    await gforms.forms_set_publish_settings.ainvoke(
        form_id="f1",
        body={
            "publish_settings": {
                "publish_state": {"is_published": True, "is_accepting_responses": True}
            }
        },
    )

    assert json.loads(route.calls.last.request.content) == {
        "publishSettings": {"publishState": {"isPublished": True, "isAcceptingResponses": True}}
    }


# -----------------------------------------------------
# Format round-trips
# -----------------------------------------------------


@respx.mock
async def test_a_field_mask_reaches_the_wire_comma_joined_and_camel_cased():
    """`Format("field_mask")` is the transform; the model fills in paths."""
    route = respx.post(f"{API}v1/forms/f1:batchUpdate").mock(
        return_value=httpx.Response(200, json={})
    )

    await gforms.forms_batch_update.ainvoke(
        form_id="f1",
        body={
            "requests": [
                {
                    "update_settings": {
                        "settings": {"quiz_settings": {"is_quiz": True}},
                        "update_mask": ["quizSettings.isQuiz"],
                    }
                }
            ]
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["requests"][0]["updateSettings"]["updateMask"] == "quizSettings.isQuiz"


@respx.mock
async def test_a_field_mask_also_accepts_the_wire_shorthand():
    route = respx.post(f"{API}v1/forms/f1:setPublishSettings").mock(
        return_value=httpx.Response(200, json={"formId": "f1"})
    )

    await gforms.forms_set_publish_settings.ainvoke(
        form_id="f1",
        body={
            "publish_settings": {
                "publish_state": {"is_published": True, "is_accepting_responses": False}
            },
            "update_mask": "publishState",
        },
    )

    assert json.loads(route.calls.last.request.content)["updateMask"] == "publishState"


# -----------------------------------------------------
# Credentials
# -----------------------------------------------------


@respx.mock
async def test_an_unconfigured_pack_raises_before_any_request(monkeypatch):
    from charter import CredentialError

    monkeypatch.setattr(gforms._credentials, "_provider", None)
    route = respx.route().mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(CredentialError, match="configure"):
        await gforms.forms_get.ainvoke(form_id="f1")
    assert not route.called


# -----------------------------------------------------
# The form response is deliberately untrimmed
# -----------------------------------------------------


def _form_payload() -> Dict[str, Any]:
    return {
        "formId": "f1",
        "revisionId": "00000001",
        "responderUri": "https://docs.google.com/forms/d/e/abc/viewform",
        "info": {"title": "Q3 survey", "documentTitle": "q3-survey"},
        "items": [
            {
                "itemId": "1a2b",
                "title": "How did it go?",
                "questionItem": {"question": {"questionId": "3c4d", "textQuestion": {}}},
            }
        ],
    }


@respx.mock
async def test_get_returns_the_form_exactly_as_google_sent_it():
    """Google's documented way to edit an item is to read it, change it and write
    it back with the same IDs. A projection would break that round trip, so this
    tool has no response handler and the test says why."""
    payload = _form_payload()
    respx.get(f"{API}v1/forms/f1").mock(return_value=httpx.Response(200, json=payload))

    assert await gforms.forms_get.ainvoke(form_id="f1") == payload


@respx.mock
async def test_an_item_read_back_from_get_validates_as_an_update():
    """The round trip the previous test protects, actually run."""
    payload = _form_payload()
    respx.get(f"{API}v1/forms/f1").mock(return_value=httpx.Response(200, json=payload))

    form = await gforms.forms_get.ainvoke(form_id="f1")
    item = dict(form["items"][0])
    item["title"] = "How did the release go?"

    _validate(
        gforms.forms_batch_update,
        {
            "form_id": "f1",
            "body": {
                "requests": [
                    {
                        "update_item": {
                            "item": item,
                            "location": {"index": 0},
                            "update_mask": ["title"],
                        }
                    }
                ]
            },
        },
    )


# -----------------------------------------------------
# Trimming the responses collection
# -----------------------------------------------------


def _answer_payload() -> Dict[str, Any]:
    return {
        "responseId": "r1",
        "formId": "f1",
        "createTime": "2026-09-01T10:00:00Z",
        "lastSubmittedTime": "2026-09-01T10:04:00Z",
        "respondentEmail": "someone@example.com",
        "totalScore": 2,
        "answers": {
            "3c4d": {
                "questionId": "3c4d",
                "textAnswers": {"answers": [{"value": "Smoothly"}]},
            },
            "5e6f": {
                "questionId": "5e6f",
                "grade": {"score": 0, "correct": False},
                "textAnswers": {"answers": [{"value": "Red"}, {"value": "Blue"}]},
            },
            "7g8h": {
                "questionId": "7g8h",
                "fileUploadAnswers": {
                    "answers": [
                        {"fileId": "d1", "fileName": "notes.pdf", "mimeType": "application/pdf"}
                    ]
                },
            },
        },
    }


@respx.mock
async def test_answers_are_flattened_and_keyed_by_question():
    respx.get(f"{API}v1/forms/f1/responses/r1").mock(
        return_value=httpx.Response(200, json=_answer_payload())
    )

    result = await gforms.forms_responses_get.ainvoke(form_id="f1", response_id="r1")

    assert result["responseId"] == "r1"
    assert result["respondentEmail"] == "someone@example.com"
    assert result["answers"]["3c4d"]["values"] == ["Smoothly"]
    assert result["answers"]["5e6f"]["values"] == ["Red", "Blue"]
    assert result["answers"]["7g8h"]["files"] == [
        {"fileId": "d1", "fileName": "notes.pdf", "mimeType": "application/pdf"}
    ]


@respx.mock
async def test_a_wrong_answer_is_not_reported_as_an_ungraded_one():
    """`correct: False` and `score: 0` are answers, not absences."""
    respx.get(f"{API}v1/forms/f1/responses/r1").mock(
        return_value=httpx.Response(200, json=_answer_payload())
    )

    result = await gforms.forms_responses_get.ainvoke(form_id="f1", response_id="r1")

    assert result["answers"]["5e6f"]["grade"] == {"score": 0, "correct": False}


@respx.mock
async def test_an_answer_shape_the_handler_does_not_know_is_reported_not_dropped():
    """A projection drops what it cannot find. Google's `value` union can grow,
    and an empty answer that reads as complete is the failure worth avoiding."""
    payload = {
        "responseId": "r1",
        "answers": {"9i0j": {"questionId": "9i0j", "videoAnswers": {"answers": []}}},
    }
    respx.get(f"{API}v1/forms/f1/responses/r1").mock(return_value=httpx.Response(200, json=payload))

    result = await gforms.forms_responses_get.ainvoke(form_id="f1", response_id="r1")

    assert result["answers"]["9i0j"]["unrecognizedAnswer"] == {"videoAnswers": {"answers": []}}


@respx.mock
async def test_trimming_a_page_of_responses_is_a_large_reduction():
    page = {
        "responses": [
            {
                "responseId": f"r{i}",
                "createTime": "2026-09-01T10:00:00Z",
                "lastSubmittedTime": "2026-09-01T10:00:00Z",
                "answers": {
                    f"q{j}": {
                        "questionId": f"q{j}",
                        "textAnswers": {"answers": [{"value": "Yes"}]},
                    }
                    for j in range(8)
                },
            }
            for i in range(40)
        ],
        "nextPageToken": "tok-2",
    }
    respx.get(f"{API}v1/forms/f1/responses").mock(return_value=httpx.Response(200, json=page))

    result = await gforms.forms_responses_list.ainvoke(form_id="f1")

    before, after = len(json.dumps(page)), len(json.dumps(result))
    assert len(result["responses"]) == 40
    assert after < before * 0.6, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_the_paging_signal_survives_the_trim():
    """Drop nextPageToken and the walk stops on page one while reporting success."""
    respx.get(f"{API}v1/forms/f1/responses").mock(
        return_value=httpx.Response(200, json={"responses": [], "nextPageToken": "tok-2"})
    )

    result = await gforms.forms_responses_list.ainvoke(form_id="f1")

    assert result == {"responses": [], "nextPageToken": "tok-2"}


@respx.mock
async def test_an_empty_last_page_comes_back_empty_rather_than_absent():
    respx.get(f"{API}v1/forms/f1/responses").mock(return_value=httpx.Response(200, json={}))

    assert await gforms.forms_responses_list.ainvoke(form_id="f1") == {"responses": []}


def test_a_two_page_walk_advances_and_then_terminates():
    pagination = gforms.forms_responses_list.pagination
    assert pagination is not None

    first = pagination.next_page_args({"responses": [{}], "nextPageToken": "tok-2"}, {})
    assert first == {"pageToken": "tok-2"}
    # Google omits the token on the last page, which is the stop signal.
    assert pagination.next_page_args({"responses": [{}]}, first) is None


# -----------------------------------------------------
# Context cost
# -----------------------------------------------------


def test_batch_update_carries_the_item_graph_and_we_know_what_it_costs():
    """Six edits, but every question type rides inside create_item and
    update_item. ~28KB of JSON schema is the price; asserted loosely so it fails
    if the schema doubles, which is the change worth noticing."""
    size = len(json.dumps(gforms.forms_batch_update.to_json_schema()))
    assert 18_000 < size < 40_000, f"batchUpdate schema is now {size} chars"


def test_the_other_five_tools_stay_small():
    for tool in gforms.TOOLS:
        if tool is gforms.forms_batch_update:
            continue
        assert len(json.dumps(tool.to_json_schema())) < 4_000, tool.name
