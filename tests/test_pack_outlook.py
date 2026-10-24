"""Outlook pack — the mail API in Microsoft Graph, one tool per operation.

Four things here are particular to Graph and each is pinned against the bytes
on the wire. The OData options are spelled with a `$` that no case convention
reaches, so a `$top` sent as `top` would be a custom option Graph ignores and
the unfiltered list would come back with a 200. Paging is a whole URL, so a page
walk's second request must carry exactly the link's query. Several operations
are served at more than one path, and the route a call takes must follow from
the arguments alone. And several take their body as JSON or as MIME, where the
MIME goes out as the whole body, in the standard base64 alphabet Graph decodes.

The rest is the pack-writing checklist: every cross-field rule Graph documents
is refused by the view the model fills in, and the handlers say what they could
not decode instead of decoding it badly.
"""

from __future__ import annotations

import base64
import email
import json
from typing import get_args
from urllib.parse import parse_qsl

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import CharterError, CredentialError, ToolValidationError, egress_map
from charter.auth import StaticTokenProvider, scopes_for
from charter.packs import outlook

API = "https://graph.microsoft.com/v1.0/"
EMAIL = {
    "to": "ada@example.com",
    "subject": "Re: Q3 — résumé",
    "body": "Looks good.",
    "in_reply_to": "<parent@example.com>",
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("MICROSOFT_ACCESS_TOKEN", raising=False)
    outlook.configure(StaticTokenProvider("graph-token"))


def _query(request: httpx.Request) -> dict:
    return dict(parse_qsl(request.url.query.decode(), keep_blank_values=True))


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content or b"{}")


def _mime(request: httpx.Request) -> email.message.Message:
    assert request.headers["content-type"] == "text/plain"
    return email.message_from_bytes(base64.b64decode(request.content, validate=True))


# -----------------------------------------------------
# One tool per Graph operation
# -----------------------------------------------------

# (tool, method, routes): Graph's own paths, most specific first.
OPERATIONS = [
    ("messages_list", "GET", ("me/mailFolders/{folder_id}/messages", "me/messages")),
    ("messages_get", "GET", ("me/messages/{message_id}",)),
    ("messages_get_content", "GET", ("me/messages/{message_id}/$value",)),
    ("messages_delta", "GET", ("me/mailFolders/{folder_id}/messages/delta",)),
    ("messages_create", "POST", ("me/mailFolders/{folder_id}/messages", "me/messages")),
    ("messages_update", "PATCH", ("me/messages/{message_id}",)),
    ("messages_delete", "DELETE", ("me/messages/{message_id}",)),
    ("messages_permanent_delete", "POST", ("me/messages/{message_id}/permanentDelete",)),
    ("messages_move", "POST", ("me/messages/{message_id}/move",)),
    ("messages_copy", "POST", ("me/messages/{message_id}/copy",)),
    ("messages_send", "POST", ("me/messages/{message_id}/send",)),
    ("messages_reply", "POST", ("me/messages/{message_id}/reply",)),
    ("messages_reply_all", "POST", ("me/messages/{message_id}/replyAll",)),
    ("messages_forward", "POST", ("me/messages/{message_id}/forward",)),
    ("messages_create_reply", "POST", ("me/messages/{message_id}/createReply",)),
    ("messages_create_reply_all", "POST", ("me/messages/{message_id}/createReplyAll",)),
    ("messages_create_forward", "POST", ("me/messages/{message_id}/createForward",)),
    ("send_mail", "POST", ("me/sendMail",)),
    ("attachments_list", "GET", ("me/messages/{message_id}/attachments",)),
    ("attachments_get", "GET", ("me/messages/{message_id}/attachments/{attachment_id}",)),
    (
        "attachments_get_content",
        "GET",
        ("me/messages/{message_id}/attachments/{attachment_id}/$value",),
    ),
    ("attachments_create", "POST", ("me/messages/{message_id}/attachments",)),
    (
        "attachments_create_upload_session",
        "POST",
        ("me/messages/{message_id}/attachments/createUploadSession",),
    ),
    ("attachments_delete", "DELETE", ("me/messages/{message_id}/attachments/{attachment_id}",)),
    (
        "mail_folders_list",
        "GET",
        ("me/mailFolders/{parent_folder_id}/childFolders", "me/mailFolders"),
    ),
    ("mail_folders_get", "GET", ("me/mailFolders/{folder_id}",)),
    (
        "mail_folders_create",
        "POST",
        ("me/mailFolders/{parent_folder_id}/childFolders", "me/mailFolders"),
    ),
    ("mail_folders_update", "PATCH", ("me/mailFolders/{folder_id}",)),
    ("mail_folders_delete", "DELETE", ("me/mailFolders/{folder_id}",)),
    ("mail_folders_permanent_delete", "POST", ("me/mailFolders/{folder_id}/permanentDelete",)),
    ("mail_folders_move", "POST", ("me/mailFolders/{folder_id}/move",)),
    ("mail_folders_copy", "POST", ("me/mailFolders/{folder_id}/copy",)),
    ("mail_folders_delta", "GET", ("me/mailFolders/delta",)),
    ("master_categories_list", "GET", ("me/outlook/masterCategories",)),
    ("master_categories_get", "GET", ("me/outlook/masterCategories/{category_id}",)),
    ("master_categories_create", "POST", ("me/outlook/masterCategories",)),
    ("master_categories_update", "PATCH", ("me/outlook/masterCategories/{category_id}",)),
    ("master_categories_delete", "DELETE", ("me/outlook/masterCategories/{category_id}",)),
    ("message_rules_list", "GET", ("me/mailFolders/inbox/messageRules",)),
    ("message_rules_get", "GET", ("me/mailFolders/inbox/messageRules/{rule_id}",)),
    ("message_rules_create", "POST", ("me/mailFolders/inbox/messageRules",)),
    ("message_rules_update", "PATCH", ("me/mailFolders/inbox/messageRules/{rule_id}",)),
    ("message_rules_delete", "DELETE", ("me/mailFolders/inbox/messageRules/{rule_id}",)),
    ("mailbox_settings_get", "GET", ("me/mailboxSettings",)),
    ("mailbox_settings_update", "PATCH", ("me/mailboxSettings",)),
    ("supported_languages", "GET", ("me/outlook/supportedLanguages",)),
    (
        "supported_time_zones",
        "GET",
        (
            "me/outlook/supportedTimeZones"
            "(TimeZoneStandard=microsoft.graph.timeZoneStandard'{time_zone_standard}')",
            "me/outlook/supportedTimeZones",
        ),
    ),
    ("inference_overrides_list", "GET", ("me/inferenceClassification/overrides",)),
    ("inference_overrides_create", "POST", ("me/inferenceClassification/overrides",)),
    (
        "inference_overrides_update",
        "PATCH",
        ("me/inferenceClassification/overrides/{override_id}",),
    ),
    (
        "inference_overrides_delete",
        "DELETE",
        ("me/inferenceClassification/overrides/{override_id}",),
    ),
    ("extensions_get", "GET", ("me/messages/{message_id}/extensions/{extension_id}",)),
    ("extensions_create", "POST", ("me/messages/{message_id}/extensions",)),
    ("extensions_delete", "DELETE", ("me/messages/{message_id}/extensions/{extension_id}",)),
    ("get_mail_tips", "POST", ("me/getMailTips",)),
    ("translate_exchange_ids", "POST", ("me/translateExchangeIds",)),
]


def test_each_tool_is_one_graph_operation_and_each_operation_one_tool():
    assert [t.name for t in outlook.TOOLS] == [name for name, _, _ in OPERATIONS]
    for name, method, routes in OPERATIONS:
        tool = getattr(outlook, name)
        assert (tool.method, tool.url_templates) == (method, routes), name
    endpoints = [(t.method, route) for t in outlook.TOOLS for route in t.url_templates]
    assert len(endpoints) == len(set(endpoints)), "two tools serve the same endpoint"


def test_two_resources_are_two_tools_even_when_the_action_has_one_name():
    """A message and a mail folder each have a `permanentDelete`."""
    assert outlook.messages_permanent_delete.url_template.startswith("me/messages/")
    assert outlook.mail_folders_permanent_delete.url_template.startswith("me/mailFolders/")


@pytest.mark.parametrize("tool", outlook.TOOLS, ids=lambda t: t.name)
def test_every_tool_links_the_graph_operation_it_is(tool):
    assert "learn.microsoft.com/en-us/graph/" in (tool.args_schema.__doc__ or "")


# -----------------------------------------------------
# Routes: the arguments choose, the model never names a URL
# -----------------------------------------------------


@pytest.mark.parametrize(
    "tool, args, path",
    [
        ("messages_list", {}, "/v1.0/me/messages"),
        ("messages_list", {"folder_id": "inbox"}, "/v1.0/me/mailFolders/inbox/messages"),
        ("mail_folders_list", {}, "/v1.0/me/mailFolders"),
        (
            "mail_folders_list",
            {"parent_folder_id": "inbox"},
            "/v1.0/me/mailFolders/inbox/childFolders",
        ),
        ("supported_time_zones", {}, "/v1.0/me/outlook/supportedTimeZones"),
        (
            "supported_time_zones",
            {"time_zone_standard": "Iana"},
            "/v1.0/me/outlook/supportedTimeZones"
            "(TimeZoneStandard=microsoft.graph.timeZoneStandard'Iana')",
        ),
    ],
)
@respx.mock
async def test_the_arguments_choose_the_route(tool, args, path):
    route = respx.get(url__startswith=API).mock(return_value=httpx.Response(200, json={}))
    await getattr(outlook, tool).ainvoke(args)
    assert route.calls[0].request.url.path == path


@pytest.mark.parametrize(
    "tool", [t for t in outlook.TOOLS if len(t.url_templates) > 1], ids=lambda t: t.name
)
def test_a_route_is_an_optional_argument_and_nothing_more(tool):
    parameters = tool.to_json_schema()["parameters"]
    text = json.dumps(parameters)
    assert "mailFolders/" not in text and "me/" not in text
    optional = set(parameters["properties"]) - set(parameters.get("required", []))
    assert {"folderId", "parentFolderId", "timeZoneStandard"} & optional


@respx.mock
async def test_create_and_create_in_a_folder_are_one_operation():
    route = respx.post(url__startswith=API).mock(return_value=httpx.Response(201, json={}))
    await outlook.messages_create.ainvoke(message={"subject": "Draft"})
    await outlook.messages_create.ainvoke(folder_id="F1", message={"subject": "Draft"})
    assert [c.request.url.path for c in route.calls] == [
        "/v1.0/me/messages",
        "/v1.0/me/mailFolders/F1/messages",
    ]
    assert all(_body(c.request) == {"subject": "Draft"} for c in route.calls)


# -----------------------------------------------------
# The wire: `$` options, camelCase, and the query on the wire
# -----------------------------------------------------


@respx.mock
async def test_the_odata_options_go_out_with_their_dollar():
    route = respx.get(f"{API}me/mailFolders/inbox/messages").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.messages_list.ainvoke(
        folder_id="inbox",
        top=25,
        filter="receivedDateTime ge 2026-10-01T00:00:00Z",
        orderby="receivedDateTime desc",
        select="subject,from",
        count=True,
    )
    assert _query(route.calls[0].request) == {
        "$top": "25",
        "$filter": "receivedDateTime ge 2026-10-01T00:00:00Z",
        "$orderby": "receivedDateTime desc",
        "$select": "subject,from",
        "$count": "true",
    }


@respx.mock
async def test_custom_query_options_are_camel_case():
    folders = respx.get(f"{API}me/mailFolders").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    delta = respx.get(f"{API}me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.mail_folders_list.ainvoke(include_hidden_folders=True)
    await outlook.messages_delta.ainvoke(folder_id="inbox", change_type="created")
    assert _query(folders.calls[0].request) == {"includeHiddenFolders": "true"}
    assert _query(delta.calls[0].request) == {"changeType": "created"}


@respx.mock
async def test_the_token_goes_out_as_a_bearer_token():
    route = respx.get(f"{API}me/mailboxSettings").mock(return_value=httpx.Response(200, json={}))
    await outlook.mailbox_settings_get.ainvoke()
    assert route.calls[0].request.headers["authorization"] == "Bearer graph-token"


@respx.mock
async def test_reads_ask_for_text_bodies_and_a_host_can_ask_for_html():
    route = respx.get(f"{API}me/messages/M1").mock(return_value=httpx.Response(200, json={}))
    await outlook.messages_get.ainvoke(message_id="M1")
    await outlook.messages_get.ainvoke(
        {"message_id": "M1"}, headers={"Prefer": 'outlook.body-content-type="html"'}
    )
    assert route.calls[0].request.headers["prefer"] == 'outlook.body-content-type="text"'
    assert route.calls[1].request.headers["prefer"] == 'outlook.body-content-type="html"'


@respx.mock
async def test_send_mail_in_json_keeps_the_message_and_the_flag_side_by_side():
    route = respx.post(f"{API}me/sendMail").mock(return_value=httpx.Response(202))
    result = await outlook.send_mail.ainvoke(
        message={
            "subject": "Lunch",
            "body": {"contentType": "text", "content": "Noon?"},
            "toRecipients": [{"emailAddress": {"address": "ada@example.com", "name": "Ada"}}],
            "from": {"emailAddress": {"address": "me@example.com"}},
        },
        save_to_sent_items=False,
    )
    assert result == {}
    request = route.calls[0].request
    assert request.headers["content-type"] == "application/json"
    assert _body(request) == {
        "message": {
            "subject": "Lunch",
            "body": {"contentType": "text", "content": "Noon?"},
            "toRecipients": [{"emailAddress": {"address": "ada@example.com", "name": "Ada"}}],
            "from": {"emailAddress": {"address": "me@example.com"}},
        },
        "saveToSentItems": False,
    }


@respx.mock
async def test_updating_a_message_sends_only_what_changes():
    route = respx.patch(f"{API}me/messages/M1").mock(return_value=httpx.Response(200, json={}))
    flag = {
        "flagStatus": "flagged",
        "startDateTime": {"dateTime": "2026-10-12T09:00:00", "timeZone": "UTC"},
        "dueDateTime": {"dateTime": "2026-10-13T09:00:00", "timeZone": "UTC"},
    }
    color = [{"id": "String {66f5a359-4659-4830-9070-00047ec6ac6e} Name Color", "value": "Green"}]
    await outlook.messages_update.ainvoke(
        message_id="M1",
        message={"isRead": True, "flag": flag, "singleValueExtendedProperties": color},
    )
    assert _body(route.calls[0].request) == {
        "isRead": True,
        "flag": flag,
        "singleValueExtendedProperties": color,
    }


def test_an_action_sized_tool_is_a_projection_of_the_operation():
    """Narrowing is the deployment's lever; the pack ships the operation."""
    mark_read = outlook.messages_update.derived(
        name="mark_read", keep={"message_id", "message.is_read"}
    )
    defs = mark_read.to_json_schema()["parameters"]["$defs"]
    (message,) = [d for name, d in defs.items() if name.startswith("Message")]
    assert set(message["properties"]) == {"isRead"}


@respx.mock
async def test_a_file_attachment_is_base64_encoded_once():
    route = respx.post(f"{API}me/messages/AAMk/attachments").mock(
        return_value=httpx.Response(201, json={})
    )
    await outlook.attachments_create.ainvoke(
        message_id="AAMk", attachment={"name": "notes.txt", "contentBytes": "Quarterly notes"}
    )
    sent = _body(route.calls[0].request)
    assert sent["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert base64.b64decode(sent["contentBytes"]).decode() == "Quarterly notes"


@respx.mock
async def test_an_item_attachment_carries_the_message_and_its_type():
    route = respx.post(f"{API}me/messages/AAMk/attachments").mock(
        return_value=httpx.Response(201, json={})
    )
    await outlook.attachments_create.ainvoke(
        message_id="AAMk",
        attachment={
            "@odata.type": "#microsoft.graph.itemAttachment",
            "name": "The original",
            "item": {"subject": "Q3", "body": {"contentType": "text", "content": "x"}},
        },
    )
    sent = _body(route.calls[0].request)
    assert sent["@odata.type"] == "#microsoft.graph.itemAttachment"
    assert sent["item"]["@odata.type"] == "microsoft.graph.message"
    assert sent["item"]["subject"] == "Q3"


@respx.mock
async def test_the_upload_session_parameter_is_pascal_case_as_documented():
    route = respx.post(f"{API}me/messages/AAMk/attachments/createUploadSession").mock(
        return_value=httpx.Response(
            201,
            json={
                "uploadUrl": "https://outlook.office.com/api/v2.0/Sessions('z')?authtoken=t",
                "expirationDateTime": "2026-10-10T12:00:00Z",
                "nextExpectedRanges": ["0-"],
                "@odata.context": "noise",
            },
        )
    )
    session = await outlook.attachments_create_upload_session.ainvoke(
        message_id="AAMk",
        attachment_item={"attachmentType": "file", "name": "deck.pdf", "size": 5_000_000},
    )
    assert _body(route.calls[0].request) == {
        "AttachmentItem": {"attachmentType": "file", "name": "deck.pdf", "size": 5_000_000}
    }
    assert set(session) == {"uploadUrl", "expirationDateTime", "nextExpectedRanges"}


@respx.mock
async def test_mail_tips_are_pascal_case_and_the_options_one_string():
    route = respx.post(f"{API}me/getMailTips").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.get_mail_tips.ainvoke(
        email_addresses=["dana@example.com"],
        mail_tips_options="automaticReplies, mailboxFullStatus",
    )
    assert _body(route.calls[0].request) == {
        "EmailAddresses": ["dana@example.com"],
        "MailTipsOptions": "automaticReplies, mailboxFullStatus",
    }


def test_mail_tips_options_take_only_the_documented_flags():
    llm = outlook.get_mail_tips.llm_schema()
    with pytest.raises(ValidationError):
        llm(email_addresses=["a@example.com"], mail_tips_options="automaticReplies, everything")
    llm(email_addresses=["a@example.com"], mail_tips_options="totalMemberCount")


@respx.mock
async def test_an_open_extensions_custom_names_travel_as_written():
    """They are data: a camelCase pass would rename `deal_value` behind the caller's back."""
    route = respx.post(f"{API}me/messages/AAMk/extensions").mock(
        return_value=httpx.Response(201, json={})
    )
    await outlook.extensions_create.ainvoke(
        message_id="AAMk",
        extension={
            "extensionName": "Com.Contoso.Referral",
            "companyName": "Wingtip",
            "deal_value": 5,
        },
    )
    assert _body(route.calls[0].request) == {
        "@odata.type": "microsoft.graph.openTypeExtension",
        "extensionName": "Com.Contoso.Referral",
        "companyName": "Wingtip",
        "deal_value": 5,
    }


@respx.mock
async def test_folders_and_search_folders_share_create_and_update():
    created = respx.post(url__startswith=API).mock(return_value=httpx.Response(201, json={}))
    patched = respx.patch(f"{API}me/mailFolders/F1").mock(return_value=httpx.Response(200, json={}))

    await outlook.mail_folders_create.ainvoke(folder={"displayName": "Clients"})
    await outlook.mail_folders_create.ainvoke(
        parent_folder_id="searchfolders",
        folder={
            "displayName": "Weekly digests",
            "sourceFolderIds": ["inbox"],
            "filterQuery": "contains(subject, 'weekly digest')",
        },
    )
    await outlook.mail_folders_update.ainvoke(folder_id="F1", folder={"displayName": "Renamed"})
    await outlook.mail_folders_update.ainvoke(folder_id="F1", folder={"filterQuery": "x"})

    assert [c.request.url.path for c in created.calls] == [
        "/v1.0/me/mailFolders",
        "/v1.0/me/mailFolders/searchfolders/childFolders",
    ]
    assert _body(created.calls[0].request) == {"displayName": "Clients"}
    assert _body(created.calls[1].request)["@odata.type"] == "microsoft.graph.mailSearchFolder"
    assert _body(patched.calls[0].request) == {"displayName": "Renamed"}
    assert _body(patched.calls[1].request) == {
        "@odata.type": "microsoft.graph.mailSearchFolder",
        "filterQuery": "x",
    }


def test_a_search_folder_is_created_under_a_parent():
    with pytest.raises(ValidationError, match="set parent_folder_id"):
        outlook.mail_folders_create.llm_schema()(
            folder={"displayName": "D", "sourceFolderIds": ["inbox"], "filterQuery": "q"}
        )


# -----------------------------------------------------
# JSON or MIME, one operation
# -----------------------------------------------------

MIME_OPERATIONS = [
    ("send_mail", "me/sendMail"),
    ("messages_create", "me/messages"),
    ("messages_reply", "me/messages/M1/reply"),
    ("messages_reply_all", "me/messages/M1/replyAll"),
    ("messages_forward", "me/messages/M1/forward"),
    ("messages_create_reply", "me/messages/M1/createReply"),
    ("messages_create_reply_all", "me/messages/M1/createReplyAll"),
    ("messages_create_forward", "me/messages/M1/createForward"),
]


@pytest.mark.parametrize("name, path", MIME_OPERATIONS)
@respx.mock
async def test_mime_is_the_whole_body_in_standard_base64(name, path):
    route = respx.post(f"{API}{path}").mock(return_value=httpx.Response(202))
    tool = getattr(outlook, name)
    args = {"mime": EMAIL}
    if "message_id" in tool.args_schema.model_fields:
        args["message_id"] = "M1"
    await tool.ainvoke(args)

    message = _mime(route.calls[0].request)
    assert message["To"] == "ada@example.com"
    assert message["In-Reply-To"] == "<parent@example.com>"
    assert "Looks good." in message.get_payload(decode=True).decode()


@pytest.mark.parametrize("name, path", MIME_OPERATIONS)
def test_mime_excludes_every_json_argument(name, path):
    llm = getattr(outlook, name).llm_schema()
    args = {"mime": EMAIL, "message": {"subject": "x"}}
    if "message_id" in llm.model_fields:
        args["message_id"] = "M1"
    with pytest.raises(ValidationError, match="whole request body, sent as text/plain"):
        llm(**args)


@respx.mock
async def test_a_json_reply_is_the_json_it_always_was():
    route = respx.post(f"{API}me/messages/M1/reply").mock(return_value=httpx.Response(202))
    await outlook.messages_reply.ainvoke(message_id="M1", comment="Thanks")
    assert route.calls[0].request.headers["content-type"] == "application/json"
    assert _body(route.calls[0].request) == {"comment": "Thanks"}


# -----------------------------------------------------
# Paging: the link's page, of the link's collection
# -----------------------------------------------------

NEXT = (
    "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"
    "?%24top=2&%24filter=isRead+eq+false&%24skip=12"
)


@respx.mock
async def test_a_two_page_walk_follows_the_link_and_stops():
    route = respx.get(f"{API}me/mailFolders/inbox/messages").mock(
        side_effect=[
            httpx.Response(
                200, json={"value": [{"id": "1"}, {"id": "2"}], "@odata.nextLink": NEXT}
            ),
            httpx.Response(200, json={"value": [{"id": "3"}]}),
        ]
    )
    tool = outlook.messages_list
    args = {"folder_id": "inbox", "top": 2, "filter": "isRead eq false", "select": "subject"}
    pages = [await tool.ainvoke(args)]
    while (args := tool.pagination.next_page_args(pages[-1], args)) is not None:
        pages.append(await tool.ainvoke(args))

    assert [m["id"] for page in pages for m in page["value"]] == ["1", "2", "3"]
    assert pages[0]["next_link"] == NEXT
    # The second request is the link — its own query, and not the `$select` the
    # first page's arguments would have added — at the route the arguments name.
    second = route.calls[1].request
    assert second.url.path == "/v1.0/me/mailFolders/inbox/messages"
    assert _query(second) == {"$top": "2", "$filter": "isRead eq false", "$skip": "12"}


@respx.mock
async def test_a_delta_round_ends_with_a_link_that_starts_the_next():
    delta = (
        "https://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta"
        "?$deltatoken=LztZwWjo5IivWBhyxw5rAKu"
    )
    route = respx.get(f"{API}me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [{"id": "gone", "@removed": {"reason": "deleted"}}],
                "@odata.deltaLink": delta,
            },
        )
    )
    tool = outlook.messages_delta
    page = await tool.ainvoke(folder_id="inbox", change_type="deleted")
    assert page["delta_link"] == delta
    assert page["value"] == [{"id": "gone", "removed": {"reason": "deleted"}}]
    assert tool.pagination.next_page_args(page, {"folder_id": "inbox"}) is None

    await tool.ainvoke(folder_id="inbox", change_type="deleted", next_link=page["delta_link"])
    assert _query(route.calls[1].request) == {"$deltatoken": "LztZwWjo5IivWBhyxw5rAKu"}


def test_a_next_link_must_be_a_graph_link():
    """Only the link's query is ever used, but a link from anywhere else is a mistake."""
    llm = outlook.messages_list.llm_schema()
    for link in (
        "https://evil.example.com/v1.0/me/messages?$skip=10",
        "http://graph.microsoft.com/v1.0/me/messages?$skip=10",
        "https://graph.microsoft.com/beta/me/messages?$skip=10",
    ):
        with pytest.raises(ValidationError, match="next_link a previous page returned"):
            llm(next_link=link)


@pytest.mark.parametrize("tool", [t for t in outlook.TOOLS if t.pagination], ids=lambda t: t.name)
def test_every_paging_tool_takes_its_link_back(tool):
    assert tool.method == "GET"
    assert "next_link" in tool.llm_schema().model_fields


# The folder a page belongs to is in the link's path, written in OData's key
# syntax. Found against the live API: a Drafts link followed with no folder_id
# fetched page two of the whole mailbox, and a delta link sent with another
# folder was 410 SyncStateInvalid.
DRAFTS_PAGE_TWO = (
    "https://graph.microsoft.com/v1.0/me/mailFolders('drafts')/messages"
    "?%24select=subject%2cisDraft&%24top=1&%24skip=1"
)


@respx.mock
async def test_a_link_followed_alone_stays_in_its_folder():
    route = respx.get(f"{API}me/mailFolders/drafts/messages").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.messages_list.ainvoke(next_link=DRAFTS_PAGE_TWO)

    assert route.called
    assert _query(route.calls[0].request) == {
        "$select": "subject,isDraft",
        "$top": "1",
        "$skip": "1",
    }


@respx.mock
async def test_a_whole_mailbox_link_is_not_narrowed_by_a_folder_argument():
    """The link's collection wins over the arguments, as its description says."""
    route = respx.get(f"{API}me/messages").mock(return_value=httpx.Response(200, json={}))
    link = "https://graph.microsoft.com/v1.0/me/messages?%24top=2&%24skip=2"
    await outlook.messages_list.ainvoke(folder_id="drafts", next_link=link)
    assert route.called


@respx.mock
async def test_a_delta_link_goes_back_to_its_own_folder():
    route = respx.get(f"{API}me/mailFolders/sentitems/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders('sentitems')/messages/delta"
        "?$deltatoken=abc"
    )
    await outlook.messages_delta.ainvoke(folder_id="drafts", next_link=link)
    assert _query(route.calls[0].request) == {"$deltatoken": "abc"}


@respx.mock
async def test_a_folder_id_in_a_link_is_sent_as_a_folder_id_argument_would_be():
    """Graph percent-encodes the key in its link; the request is the one a call
    naming that folder makes."""
    folder = "AQMkADAwATM3ZmYAZS0xYmMy-_AAAA=="
    route = respx.get(f"{API}me/mailFolders/{folder}/childFolders").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    link = (
        "https://graph.microsoft.com/v1.0/me/mailFolders(%27AQMkADAwATM3ZmYAZS0xYmMy-_AAAA%3D%3D%27)"
        "/childFolders?%24skip=10"
    )
    await outlook.mail_folders_list.ainvoke(next_link=link)
    await outlook.mail_folders_list.ainvoke(parent_folder_id=folder)

    first, second = route.calls
    assert first.request.url.raw_path.split(b"?")[0] == second.request.url.raw_path
    assert _query(first.request) == {"$skip": "10"}


@respx.mock
async def test_a_link_naming_the_user_rather_than_me_is_followed_at_me():
    route = respx.get(f"{API}me/messages/M1/attachments").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    link = (
        "https://graph.microsoft.com/v1.0/users('outlook_AD90%40outlook.com')"
        "/messages('M1')/attachments?%24skip=10"
    )
    await outlook.attachments_list.ainvoke(message_id="M2", next_link=link)
    assert route.called


@pytest.mark.parametrize(
    "link",
    [
        # Another tool's collection: a folder list is not a page of messages.
        "https://graph.microsoft.com/v1.0/me/mailFolders?%24skip=10",
        # An endpoint no Outlook tool serves.
        "https://graph.microsoft.com/v1.0/me/contacts?%24skip=10",
    ],
)
@respx.mock
async def test_a_link_of_another_collection_is_refused(link):
    with pytest.raises(ToolValidationError, match="not a page of this tool's results"):
        await outlook.messages_list.ainvoke(next_link=link)


@respx.mock
async def test_a_link_cannot_walk_out_of_its_route():
    """The value comes from a link a model can rewrite, so it is escaped like any other."""
    link = "https://graph.microsoft.com/v1.0/me/mailFolders('..')/messages?%24skip=1"
    with pytest.raises(CharterError):
        await outlook.messages_list.ainvoke(next_link=link)
    assert not respx.calls


# -----------------------------------------------------
# Delta: a page size, never a limit
# -----------------------------------------------------


def test_delta_offers_no_top():
    """`$top` on a delta round ends it: two of twelve messages, then a delta link
    that returned nothing, and the other ten were never delivered. Live, against
    Graph."""
    fields = outlook.messages_delta.llm_schema().model_fields
    assert "top" not in fields
    assert "max_page_size" in fields


@respx.mock
async def test_delta_page_size_is_the_prefer_header():
    route = respx.get(f"{API}me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.messages_delta.ainvoke(folder_id="inbox", max_page_size=2, select="subject")

    request = route.calls[0].request
    assert request.headers["prefer"] == "odata.maxpagesize=2"
    assert _query(request) == {"$select": "subject"}


@respx.mock
async def test_delta_page_size_holds_across_the_round():
    route = respx.get(f"{API}me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    link = "https://graph.microsoft.com/v1.0/me/mailFolders('inbox')/messages/delta?$skiptoken=s2"
    await outlook.messages_delta.ainvoke(folder_id="inbox", max_page_size=2, next_link=link)

    request = route.calls[0].request
    assert request.headers["prefer"] == "odata.maxpagesize=2"
    assert _query(request) == {"$skiptoken": "s2"}


@respx.mock
async def test_delta_without_a_page_size_sends_no_prefer():
    route = respx.get(f"{API}me/mailFolders/inbox/messages/delta").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await outlook.messages_delta.ainvoke(folder_id="inbox")
    assert "prefer" not in route.calls[0].request.headers


# -----------------------------------------------------
# Query options Graph accepts and ignores are not offered
# -----------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "ignored"),
    [
        # Each returned the whole collection, live, with the option on the wire.
        ("mailbox_settings_get", {"select"}),
        ("master_categories_list", {"filter"}),
        ("attachments_list", {"top", "filter"}),
    ],
)
def test_an_option_graph_ignores_is_not_offered(tool, ignored):
    fields = set(getattr(outlook, tool).llm_schema().model_fields)
    assert not fields & ignored


# -----------------------------------------------------
# Cross-field rules, against the view the model fills in
# -----------------------------------------------------


def test_send_mail_needs_a_message_with_someone_to_send_it_to():
    llm = outlook.send_mail.llm_schema()
    with pytest.raises(ValidationError, match="message \\(JSON\\) or as mime"):
        llm()
    with pytest.raises(ValidationError, match="at least one of toRecipients"):
        llm(message={"subject": "Nobody"})


def test_a_draft_is_json_or_mime():
    with pytest.raises(ValidationError, match="message \\(JSON\\) or as mime"):
        outlook.messages_create.llm_schema()(folder_id="F1")


@pytest.mark.parametrize(
    "tool",
    [
        outlook.messages_reply,
        outlook.messages_reply_all,
        outlook.messages_create_reply,
        outlook.messages_create_reply_all,
    ],
    ids=lambda t: t.name,
)
def test_a_reply_takes_a_comment_or_a_body_not_both(tool):
    llm = tool.llm_schema()
    with pytest.raises(ValidationError, match="either comment or message.body"):
        llm(message_id="M1", comment="Hi", message={"body": {"content": "Hello"}})
    llm(message_id="M1", comment="Hi")
    llm(message_id="M1", message={"body": {"content": "Hello"}})


@pytest.mark.parametrize(
    "tool", [outlook.messages_forward, outlook.messages_create_forward], ids=lambda t: t.name
)
def test_a_forward_names_its_recipients_exactly_once(tool):
    llm = tool.llm_schema()
    to = [{"emailAddress": {"address": "b@example.com"}}]
    with pytest.raises(ValidationError, match="recipients once"):
        llm(message_id="M1", comment="fyi")
    with pytest.raises(ValidationError, match="recipients once"):
        llm(message_id="M1", to_recipients=to, message={"toRecipients": to})
    llm(message_id="M1", to_recipients=to)
    llm(message_id="M1", message={"toRecipients": to})
    llm(message_id="M1", mime=EMAIL)


def test_a_due_date_needs_a_start_date():
    when = {"dateTime": "2026-10-13T09:00:00", "timeZone": "UTC"}
    with pytest.raises(ValidationError, match="dueDateTime needs startDateTime"):
        outlook.messages_update.llm_schema()(
            message_id="M1", message={"flag": {"dueDateTime": when}}
        )


def test_search_wants_its_query_quoted():
    llm = outlook.messages_list.llm_schema()
    with pytest.raises(ValidationError):
        llm(search="pizza")
    llm(search='"pizza"')


# -----------------------------------------------------
# What the model is offered
# -----------------------------------------------------


def test_create_only_message_fields_are_withheld_from_an_update():
    """Attachments, extensions and custom headers go on a message as it is created."""
    create_only = {"attachments", "extensions", "internet_message_headers"}
    for tool in (outlook.send_mail, outlook.messages_create, outlook.messages_reply):
        message = tool.llm_schema().model_fields["message"].annotation
        message = next(a for a in (message, *get_args(message)) if hasattr(a, "model_fields"))
        assert create_only <= set(message.model_fields), tool.name
    message = outlook.messages_update.llm_schema().model_fields["message"].annotation
    assert not create_only & set(message.model_fields)


def test_server_set_message_fields_never_reach_the_model():
    entry = egress_map([outlook.messages_create])["outlook_messages_create"]
    visible = set(entry["visible"])
    for field in ("id", "change_key", "received_date_time", "is_draft", "web_link", "body_preview"):
        assert f"message.{field}" not in visible, field


_IDS = {
    name: "X1"
    for name in (
        "message_id",
        "folder_id",
        "attachment_id",
        "category_id",
        "rule_id",
        "override_id",
        "extension_id",
    )
}


@pytest.mark.parametrize("tool", outlook.TOOLS, ids=lambda t: t.name)
@respx.mock
async def test_the_no_argument_call_sends_nothing_it_was_not_asked_to(tool):
    """Only the required arguments, and read the URL and query that come out."""
    route = respx.route(method=tool.method, url__startswith=API).mock(
        return_value=httpx.Response(200, json={})
    )
    fillers = {
        "message": {"toRecipients": [{"emailAddress": {"address": "a@example.com"}}]},
        "destination_id": "inbox",
        "attachment": {"name": "a.txt", "contentBytes": "a"},
        "attachment_item": {"attachmentType": "file", "name": "a", "size": 1},
        "folder": {"displayName": "F"},
        "category": {"displayName": "C"},
        "rule": {"displayName": "R", "sequence": 1, "actions": {"markAsRead": True}},
        "settings": {},
        "override": {"classifyAs": "focused", "senderEmailAddress": {"address": "s@example.com"}},
        "extension": {"extensionName": "Com.Example.X"},
        "email_addresses": ["a@example.com"],
        "input_ids": ["A"],
        "source_id_type": "restId",
        "target_id_type": "restImmutableEntryId",
    }
    args = {
        name: _IDS.get(name) or fillers[name]
        for name, field in tool.args_schema.model_fields.items()
        if field.is_required()
    }
    # Tools whose required argument is a choice between two shapes.
    if tool in (outlook.send_mail, outlook.messages_create):
        args["message"] = fillers["message"]
    if tool in (outlook.messages_forward, outlook.messages_create_forward):
        args["to_recipients"] = [{"emailAddress": {"address": "b@example.com"}}]
    if tool in (outlook.master_categories_update, outlook.inference_overrides_update):
        args[next(n for n in ("category", "override") if n in args)] = {}
    await tool.ainvoke(args)

    request = route.calls[0].request
    assert not _query(request), f"{tool.name} sends {_query(request)} unasked"
    assert request.url.path == "/v1.0/" + tool.url_templates[-1].format(**_IDS)


# -----------------------------------------------------
# Enums, against Graph's values
# -----------------------------------------------------


def test_the_enums_hold_graphs_values():
    from charter.packs.outlook.types import common, other, rules, settings

    assert set(get_args(common.Importance)) == {"low", "normal", "high"}
    assert set(get_args(common.FollowupFlagStatus)) == {"notFlagged", "complete", "flagged"}
    assert set(get_args(common.InferenceClassificationType)) == {"focused", "other"}
    assert set(get_args(common.CategoryColor)) == {"none"} | {f"preset{i}" for i in range(25)}
    assert set(get_args(common.ExchangeIdFormat)) == {
        "entryId",
        "ewsId",
        "immutableEntryId",
        "restId",
        "restImmutableEntryId",
    }
    assert set(get_args(rules.actions.MessageActionFlag)) == {
        "any",
        "call",
        "doNotForward",
        "followUp",
        "fyi",
        "forward",
        "noResponseNecessary",
        "read",
        "reply",
        "replyToAll",
        "review",
    }
    assert set(get_args(rules.actions.Sensitivity)) == {
        "normal",
        "personal",
        "private",
        "confidential",
    }
    assert set(get_args(settings.actions.AutomaticRepliesStatus)) == {
        "disabled",
        "alwaysEnabled",
        "scheduled",
    }
    assert set(get_args(settings.actions.ExternalAudienceScope)) == {"none", "contactsOnly", "all"}
    assert len(get_args(common.DayOfWeek)) == 7
    assert len(other.MAIL_TIPS_TYPES) == 10


# -----------------------------------------------------
# Handlers, including the unhappy paths
# -----------------------------------------------------

MESSAGE = {
    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#users('x')/messages/$entity",
    "@odata.etag": 'W/"CQAAABYAAAC4"',
    "id": "AAMk",
    "changeKey": "CQAAABYAAAC4",
    "conversationIndex": "AQHUJ2kx",
    "subject": "9/9/2018: concert",
    "body": {"contentType": "text", "content": "The group represents Nevada."},
    "uniqueBody": {"contentType": "text", "content": "Nevada."},
    "from": {"emailAddress": {"name": "Adele Vance", "address": "adelev@contoso.com"}},
    "toRecipients": [{"emailAddress": {"name": "Alex Wilber", "address": "AlexW@contoso.com"}}],
    "ccRecipients": [],
    "categories": [],
    "flag": {"flagStatus": "notFlagged"},
}


@respx.mock
async def test_a_message_comes_back_without_the_envelope():
    respx.get(f"{API}me/messages/AAMk").mock(return_value=httpx.Response(200, json=MESSAGE))
    message = await outlook.messages_get.ainvoke(message_id="AAMk")
    assert message == {
        "id": "AAMk",
        "subject": "9/9/2018: concert",
        "body": {"contentType": "text", "content": "The group represents Nevada."},
        "uniqueBody": {"contentType": "text", "content": "Nevada."},
        "from": "Adele Vance <adelev@contoso.com>",
        "toRecipients": ["Alex Wilber <AlexW@contoso.com>"],
        "flag": {"flagStatus": "notFlagged"},
    }


@respx.mock
async def test_a_list_drops_full_bodies_keeps_a_selected_unique_body_and_counts():
    route = respx.get(f"{API}me/messages").mock(
        side_effect=[
            httpx.Response(200, json={"value": [MESSAGE], "@odata.count": 1}),
            httpx.Response(200, json={"value": []}),
            httpx.Response(200, json={}),
        ]
    )
    page = await outlook.messages_list.ainvoke(count=True)
    assert "body" not in page["value"][0]
    assert page["value"][0]["uniqueBody"]["content"] == "Nevada."
    assert page["count"] == 1
    assert await outlook.messages_list.ainvoke() == {"value": []}
    assert await outlook.messages_list.ainvoke() == {"value": []}
    assert route.call_count == 3


ATTACHMENT = {
    "@odata.type": "#microsoft.graph.fileAttachment",
    "id": "AAMkAtt",
    "name": "notes.txt",
    "contentType": "text/plain",
    "size": 15,
    "isInline": False,
    "contentBytes": base64.b64encode(b"Quarterly notes").decode(),
}


@respx.mock
async def test_a_text_attachment_is_decoded():
    respx.get(f"{API}me/messages/M1/attachments/A1").mock(
        return_value=httpx.Response(200, json=ATTACHMENT)
    )
    found = await outlook.attachments_get.ainvoke(message_id="M1", attachment_id="A1")
    assert found["content"] == "Quarterly notes"
    assert found["type"] == "fileAttachment"
    assert "contentBytes" not in found


@respx.mock
async def test_a_binary_or_undecodable_attachment_is_described_not_decoded():
    pdf = {**ATTACHMENT, "name": "deck.pdf", "contentType": "application/pdf"}
    latin = {**ATTACHMENT, "contentBytes": base64.b64encode("café".encode("latin-1")).decode()}
    respx.get(f"{API}me/messages/M1/attachments/A1").mock(
        side_effect=[httpx.Response(200, json=pdf), httpx.Response(200, json=latin)]
    )
    for _ in range(2):
        found = await outlook.attachments_get.ainvoke(message_id="M1", attachment_id="A1")
        assert "content" not in found and "contentBytes" not in found
        assert "attachments_get_content" in found["content_omitted"]


@respx.mock
async def test_listed_attachments_carry_no_bytes():
    respx.get(f"{API}me/messages/M1/attachments").mock(
        return_value=httpx.Response(200, json={"value": [ATTACHMENT]})
    )
    page = await outlook.attachments_list.ainvoke(message_id="M1")
    assert page["value"][0]["name"] == "notes.txt"
    assert "contentBytes" not in page["value"][0]


@respx.mock
async def test_raw_contents_are_text_when_text_and_bytes_otherwise():
    respx.get(f"{API}me/messages/M1/attachments/A1/$value").mock(
        side_effect=[
            httpx.Response(200, text="a,b\n1,2\n", headers={"content-type": "text/csv"}),
            httpx.Response(
                200, content=b"%PDF-1.7\x00\xff", headers={"content-type": "application/pdf"}
            ),
        ]
    )
    text = await outlook.attachments_get_content.ainvoke(message_id="M1", attachment_id="A1")
    binary = await outlook.attachments_get_content.ainvoke(message_id="M1", attachment_id="A1")
    assert text == {"content": "a,b\n1,2\n"}
    assert base64.b64decode(binary["content_base64"]) == b"%PDF-1.7\x00\xff"
    assert binary["content_type"] == "application/pdf"


@respx.mock
async def test_mime_comes_back_as_text_or_as_labelled_bytes():
    source = b"From: a@example.com\r\nSubject: Hi\r\n\r\nHello\r\n"
    respx.get(f"{API}me/messages/M1/$value").mock(
        side_effect=[
            httpx.Response(200, content=source, headers={"content-type": "message/rfc822"}),
            httpx.Response(
                200, content=b"Subject: \xff\r\n", headers={"content-type": "message/rfc822"}
            ),
        ]
    )
    assert await outlook.messages_get_content.ainvoke(message_id="M1") == {"mime": source.decode()}
    undecodable = await outlook.messages_get_content.ainvoke(message_id="M1")
    assert base64.b64decode(undecodable["mime_base64"]) == b"Subject: \xff\r\n"


@respx.mock
async def test_odata_annotations_on_properties_are_dropped():
    """`@odata.type` becomes `type`; every other annotation is machinery."""
    respx.get(f"{API}me/messages/M1/extensions/com.contoso.x").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.type": "#microsoft.graph.openTypeExtension",
                "id": "Microsoft.OutlookServices.OpenTypeExtension.com.contoso.x",
                "count@odata.type": "#Int64",
                "count": 3,
                "tags@odata.type": "#Collection(String)",
                "tags": ["a"],
            },
        )
    )
    result = await outlook.extensions_get.ainvoke(message_id="M1", extension_id="com.contoso.x")
    assert result == {
        "type": "openTypeExtension",
        "id": "Microsoft.OutlookServices.OpenTypeExtension.com.contoso.x",
        "count": 3,
        "tags": ["a"],
    }


@respx.mock
async def test_an_expanded_item_attachment_carries_no_navigation_links():
    respx.get(f"{API}me/messages/M1/attachments/A1").mock(
        return_value=httpx.Response(
            200,
            json={
                "@odata.type": "#microsoft.graph.itemAttachment",
                "@odata.mediaContentType": "message/rfc822",
                "id": "A1",
                "item@odata.associationLink": "https://graph.microsoft.com/v1.0/users('u')/messages('')/$ref",
                "item@odata.navigationLink": "https://graph.microsoft.com/v1.0/users('u')/messages('')",
                "item": {"@odata.type": "#microsoft.graph.message", "subject": "inner"},
            },
        )
    )
    result = await outlook.attachments_get.ainvoke(
        message_id="M1", attachment_id="A1", expand="microsoft.graph.itemattachment/item"
    )
    assert result == {
        "type": "itemAttachment",
        "id": "A1",
        "item": {"type": "message", "subject": "inner"},
    }


@respx.mock
async def test_the_settable_part_of_the_language_read_from_settings_is_its_locale():
    """Graph returns an undocumented `lCID` and a read-only `displayName` beside
    the locale. Live, writing the language back as read was a 400 for each in
    turn. `lCID` is dropped from what the model reads; `displayName` is not
    offered, so the update sends the locale and only the locale."""
    respx.get(f"{API}me/mailboxSettings").mock(
        return_value=httpx.Response(
            200,
            json={
                "language": {"locale": "en-US", "displayName": "English (United States)", "lCID": 0}
            },
        )
    )
    patch = respx.patch(f"{API}me/mailboxSettings").mock(return_value=httpx.Response(200, json={}))

    settings = await outlook.mailbox_settings_get.ainvoke()
    assert settings["language"] == {"locale": "en-US", "displayName": "English (United States)"}

    with pytest.raises(ToolValidationError, match="displayName"):
        await outlook.mailbox_settings_update.ainvoke(settings={"language": settings["language"]})
    assert not patch.called

    await outlook.mailbox_settings_update.ainvoke(settings={"language": {"locale": "en-US"}})
    assert _body(patch.calls[0].request) == {"language": {"locale": "en-US"}}


# -----------------------------------------------------
# Credentials and failures
# -----------------------------------------------------


async def test_an_unconfigured_pack_raises_before_any_request(monkeypatch):
    monkeypatch.setattr(outlook._credentials, "_provider", None)
    with respx.mock(assert_all_called=False) as router:
        route = router.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="MICROSOFT_ACCESS_TOKEN"):
            await outlook.messages_list.ainvoke()
        assert not route.called


async def test_the_token_can_come_from_the_environment(monkeypatch):
    monkeypatch.setattr(outlook._credentials, "_provider", None)
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "from-env")
    with respx.mock() as router:
        route = router.get(f"{API}me/messages").mock(
            return_value=httpx.Response(200, json={"value": []})
        )
        await outlook.messages_list.ainvoke()
    assert route.calls[0].request.headers["authorization"] == "Bearer from-env"


@respx.mock
async def test_graph_answers_failure_with_a_status_code_so_there_is_no_envelope():
    assert all(tool.envelope is None for tool in outlook.TOOLS)
    respx.get(f"{API}me/messages/gone").mock(
        return_value=httpx.Response(
            404,
            json={
                "error": {
                    "code": "ErrorItemNotFound",
                    "message": "The specified object was not found in the store.",
                }
            },
        )
    )
    with pytest.raises(Exception, match="not found in the store"):
        await outlook.messages_get.ainvoke(message_id="gone")


def test_each_tool_asks_for_the_least_privileged_permission():
    assert scopes_for([outlook.send_mail]) == [outlook.MAIL_SEND]
    assert scopes_for([outlook.messages_get]) == [outlook.MAIL_READ]
    assert scopes_for([outlook.mail_folders_list]) == [outlook.MAIL_READ_BASIC]
    assert scopes_for([outlook.mailbox_settings_update]) == [outlook.MAILBOX_SETTINGS_READ_WRITE]
    assert scopes_for([outlook.translate_exchange_ids]) == [outlook.USER_READ]


def test_a_reader_and_a_writer_ask_for_the_writer_alone():
    """Mail.ReadWrite reads, so a consent screen does not list Mail.Read beside it."""
    assert scopes_for([outlook.messages_get, outlook.messages_update]) == [outlook.MAIL_READ_WRITE]
    assert (
        scopes_for(outlook.TOOLS)
        == outlook.SCOPES
        == [
            outlook.MAIL_READ_WRITE,
            outlook.MAIL_SEND,
            outlook.MAILBOX_SETTINGS_READ_WRITE,
            outlook.USER_READ,
        ]
    )
