"""Routes and media-typed bodies — one operation, one tool, whatever shape it takes.

Two shapes the wire contract used to push into a second tool. An operation an
API serves at more than one path — Graph's messages at `/me/messages` and at
`/me/mailFolders/{id}/messages` — and an operation that takes its body in more
than one format — Graph's `sendMail`, JSON or base64 MIME. Both are now
declared on the one tool, and neither is visible to the model as anything but
an optional argument.
"""

from __future__ import annotations

import base64
import email
import json
from typing import Annotated, Any, Dict, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, ValidationError

from charter import Body, ConflictsWith, Format, Path, Query, Tool, ToolValidationError, WireName
from charter.conflicts import conflict_map
from charter.observability import ToolCall
from charter.types.errors import DeclarationError
from charter.types.markers import declared_body_fields

BASE = "https://api.example.com/"


def _tool(schema: type[BaseModel], url_template: Any, method: str = "GET", **kw: Any) -> Tool:
    return Tool(
        name="t",
        pack="wire",
        method=method,  # type: ignore[arg-type]
        url_template=url_template,
        args_schema=schema,
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
        **kw,
    )


# -----------------------------------------------------
# Routes
# -----------------------------------------------------


class ListMessages(BaseModel):
    folder_id: Annotated[Optional[str], Path()] = None
    top: Annotated[Optional[int], Query()] = None


ROUTES = ("me/mailFolders/{folder_id}/messages", "me/messages")


@respx.mock
async def test_a_call_goes_to_the_first_route_it_fills():
    route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))
    tool = _tool(ListMessages, ROUTES)

    await tool.ainvoke(top=5)
    await tool.ainvoke(folder_id="inbox", top=5)

    assert [str(call.request.url) for call in route.calls] == [
        f"{BASE}me/messages?top=5",
        f"{BASE}me/mailFolders/inbox/messages?top=5",
    ]


def test_the_model_sees_an_optional_argument_and_no_route():
    tool = _tool(ListMessages, ROUTES)
    parameters = tool.to_json_schema()["parameters"]
    assert "folderId" in parameters["properties"]
    assert "folderId" not in parameters.get("required", [])
    assert "messages" not in json.dumps(parameters)


def test_a_single_template_is_still_the_tools_route():
    tool = _tool(ListMessages, "me/messages")
    assert tool.url_templates == ("me/messages",)
    assert tool.url_template == "me/messages"


def test_the_first_route_is_the_one_everything_with_room_for_one_shows():
    tool = _tool(ListMessages, ROUTES)
    assert tool.url_templates == ROUTES
    assert tool.url_template == ROUTES[0]
    assert tool.derived(name="narrow", keep={"top"}).url_templates == ROUTES


@respx.mock
async def test_the_record_names_the_route_the_call_took():
    respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))
    seen: list[ToolCall] = []
    tool = _tool(ListMessages, ROUTES, on_call=seen.append)

    await tool.ainvoke(top=1)
    await tool.ainvoke(folder_id="inbox")

    assert [call.url_template for call in seen] == ["me/messages", ROUTES[0]]


@respx.mock
async def test_a_path_value_cannot_reach_another_route():
    """Escaping is per value, so `../` stays inside the segment it was given."""
    route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))
    with pytest.raises(ToolValidationError, match=r"'\.\.'"):
        await _tool(ListMessages, ROUTES).ainvoke(folder_id="../../users/x")
    assert not route.called


@respx.mock
async def test_a_wire_named_path_field_routes_under_its_wire_name():
    class Zones(BaseModel):
        standard: Annotated[Optional[str], Path(), WireName("TimeZoneStandard")] = None

    route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200, json={}))
    tool = _tool(Zones, ("zones(standard='{TimeZoneStandard}')", "zones"))
    await tool.ainvoke()
    await tool.ainvoke(standard="Iana")
    assert [call.request.url.path for call in route.calls] == ["/zones", "/zones(standard='Iana')"]


def test_a_route_naming_a_field_that_is_not_a_path_is_refused():
    with pytest.raises(DeclarationError, match=r"\{top\}"):
        _tool(ListMessages, ("me/{top}/messages", "me/mailFolders/{folder_id}/messages", "me"))


def test_a_route_an_earlier_one_always_wins_is_refused():
    with pytest.raises(DeclarationError, match="can never be chosen"):
        _tool(ListMessages, ("me/messages", "me/mailFolders/{folder_id}/messages"))


def test_a_last_route_some_calls_cannot_fill_is_refused():
    class Scoped(BaseModel):
        folder_id: Annotated[Optional[str], Path()] = None
        user_id: Annotated[Optional[str], Path()] = None

    with pytest.raises(DeclarationError, match="some calls would have no route"):
        _tool(Scoped, ("users/{user_id}/mailFolders/{folder_id}", "me/mailFolders/{folder_id}"))


def test_a_path_field_no_route_uses_is_refused():
    class Stray(BaseModel):
        folder_id: Annotated[Optional[str], Path()] = None
        user_id: Annotated[Optional[str], Path()] = None

    with pytest.raises(DeclarationError, match="appear in none of its routes"):
        _tool(Stray, ROUTES)


def test_a_required_path_field_can_be_in_every_route():
    class Scoped(BaseModel):
        message_id: Annotated[str, Path()]
        user_id: Annotated[Optional[str], Path()] = None

    tool = _tool(Scoped, ("users/{user_id}/messages/{message_id}", "me/messages/{message_id}"))
    assert len(tool.url_templates) == 2


# -----------------------------------------------------
# A body in another media type
# -----------------------------------------------------


class SendMail(BaseModel):
    message: Annotated[Optional[Dict[str, Any]], Body()] = None
    save_to_sent_items: Annotated[Optional[bool], Body()] = None
    mime: Annotated[Optional[str], Format("mime_base64"), Body(media_type="text/plain")] = None


class CreateMessage(BaseModel):
    folder_id: Annotated[Optional[str], Path()] = None
    subject: Annotated[Optional[str], Body()] = None
    mime: Annotated[Optional[str], Body(media_type="text/plain")] = None


@respx.mock
async def test_the_json_alternative_is_the_json_body_it_always_was():
    route = respx.post(f"{BASE}me/sendMail").mock(return_value=httpx.Response(202))
    await _tool(SendMail, "me/sendMail", "POST").ainvoke(
        message={"subject": "Hi"}, save_to_sent_items=False
    )
    request = route.calls.last.request
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {"message": {"subject": "Hi"}, "saveToSentItems": False}


@respx.mock
async def test_the_media_typed_alternative_is_the_whole_body_in_its_type():
    route = respx.post(f"{BASE}me/sendMail").mock(return_value=httpx.Response(202))
    await _tool(SendMail, "me/sendMail", "POST").ainvoke(
        mime={"to": "ada@example.com", "subject": "Hi", "body": "Hello"}
    )
    request = route.calls.last.request
    assert request.headers["content-type"] == "text/plain"
    message = email.message_from_bytes(base64.b64decode(request.content, validate=True))
    assert message["To"] == "ada@example.com"
    assert message.get_payload(decode=True).decode().strip() == "Hello"


@respx.mock
async def test_a_text_field_without_a_format_is_sent_as_written():
    route = respx.post(f"{BASE}me/messages").mock(return_value=httpx.Response(201, json={}))
    await _tool(
        CreateMessage, ("me/mailFolders/{folder_id}/messages", "me/messages"), "POST"
    ).ainvoke(mime="RnJvbTogYUBiLmNvbQ==")
    assert route.calls.last.request.content == b"RnJvbTogYUBiLmNvbQ=="


def test_a_media_typed_field_does_not_change_how_the_json_body_unwraps():
    """`subject` is the only JSON body field either way, so it would unwrap."""
    assert declared_body_fields(CreateMessage) == 1
    assert declared_body_fields(SendMail) == 2


def test_the_model_cannot_send_both_and_is_told_why_in_one_message():
    llm = _tool(SendMail, "me/sendMail", "POST").llm_schema()
    with pytest.raises(ValidationError, match="whole request body, sent as text/plain") as info:
        llm(
            message={"subject": "Hi"},
            save_to_sent_items=True,
            mime={"to": "a@b.com", "subject": "s", "body": "b"},
        )
    assert "message" in str(info.value) and "saveToSentItems" in str(info.value)


@respx.mock
async def test_input_that_skipped_the_view_is_refused_rather_than_trimmed():
    from charter.execution.http import call_api

    route = respx.post(f"{BASE}me/messages").mock(return_value=httpx.Response(201, json={}))
    with pytest.raises(ToolValidationError, match="cannot be combined with subject"):
        await call_api(
            method="POST",
            url_template="me/messages",
            tool_input=CreateMessage(subject="Hi", mime="raw"),
            base_url=BASE,
        )
    assert not route.called


def test_the_audit_lists_the_exclusion_the_marker_implies():
    rules = conflict_map([_tool(SendMail, "me/sendMail", "POST")])["wire_t"]
    implied = next(rule for rule in rules if rule["field"] == "mime")
    assert {other["field"] for other in implied["excludes"]} == {"message", "save_to_sent_items"}


def test_a_field_is_enveloped_or_the_whole_body_not_both():
    with pytest.raises(DeclarationError, match="one or the other"):
        Body(envelop=True, media_type="text/plain")


def test_a_conflict_declared_on_a_format_field_is_enforced():
    """The Format pass moves a field's markers onto its retyped annotation, and
    the conflict check used to read them off the view, where they were gone."""

    class Encoded(BaseModel):
        text: Annotated[Optional[str], Body()] = None
        blob: Annotated[
            Optional[str], Format("base64"), Body(), ConflictsWith("text", reason="One body.")
        ] = None

    llm = _tool(Encoded, "x", "POST").llm_schema()
    with pytest.raises(ValidationError, match="cannot be combined with text"):
        llm(text="a", blob="b")
