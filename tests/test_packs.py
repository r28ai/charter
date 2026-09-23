"""R6 — the shipped packs.

Every pack must import without credentials, build every schema, and put the
right bytes on the wire. One GET and one POST per pack, against respx.
"""

from __future__ import annotations

import base64
import email
import json
from email.message import EmailMessage
from typing import get_args

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import CredentialError, Tool
from charter.auth import StaticTokenProvider
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
)

ALL_PACKS = [
    gmail,
    gcalendar,
    gdocs,
    gsheets,
    gdrive,
    gforms,
    slack,
    stripe,
    firecrawl,
    github,
    linear,
    shopify,
    notion,
    granola,
]
GOOGLE_PACKS = [gmail, gcalendar, gsheets, gdocs, gdrive, gforms]
# Bearer-token packs, Google and otherwise — they share a configure() shape.
OAUTH_PACKS = [gmail, gcalendar, gsheets, gdocs, gdrive, gforms, slack, github, notion]
API_KEY_PACKS = [firecrawl, stripe, linear, shopify, granola]


def _decode_b64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8")


@pytest.fixture(autouse=True)
def _isolate_pack_credentials(monkeypatch):
    """Packs read env vars lazily; keep the suite independent of the machine."""
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("NOTION_API_KEY", raising=False)


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_pack_exports_tools(pack):
    assert isinstance(pack.TOOLS, list)
    assert pack.TOOLS
    assert all(isinstance(t, Tool) for t in pack.TOOLS)


def test_gmail_ships_at_least_twenty_three_tools():
    assert len(gmail.TOOLS) >= 23


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_every_tool_schema_builds(pack):
    for tool in pack.TOOLS:
        assert tool.llm_schema().model_fields is not None
        fn = tool.to_json_schema()
        assert fn["name"] and fn["parameters"]["type"] == "object"


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_every_tool_has_a_description_and_action_label(pack):
    for tool in pack.TOOLS:
        assert tool.description, f"{tool.name} has no description"
        assert tool.action_label, f"{tool.name} has no action_label"


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_tool_names_are_unique_within_a_pack(pack):
    names = [t.name for t in pack.TOOLS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__)
def test_named_tools_are_the_same_objects_as_in_TOOLS(pack):
    """A reference taken by name must be the tool configure() will reach."""
    for tool in pack.TOOLS:
        assert getattr(pack, tool.name, None) is tool or tool.name in {t.name for t in pack.TOOLS}


@pytest.mark.parametrize("pack", OAUTH_PACKS, ids=lambda p: p.__name__)
def test_oauth_packs_share_one_configure_shape(pack):
    assert callable(pack.configure)
    assert pack.SCOPES
    for tool in pack.TOOLS:
        assert tool.provider is not None
        assert tool.credential_provider is not None
        assert tool.api_key_headers is None


@pytest.mark.parametrize("pack", GOOGLE_PACKS, ids=lambda p: p.__name__)
def test_google_packs_declare_google_scope_urls(pack):
    assert all(s.startswith("https://") for s in pack.SCOPES)
    for tool in pack.TOOLS:
        assert tool.provider == "google"


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
def test_api_key_packs_use_header_auth_only(pack):
    for tool in pack.TOOLS:
        assert tool.api_key_headers is not None
        assert tool.credential_provider is None


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
def test_api_key_packs_resolve_headers_per_request(pack):
    """Not a static dict — a callable the runtime invokes on every call."""
    for tool in pack.TOOLS:
        assert callable(tool.api_key_headers)


# -----------------------------------------------------
# Unconfigured behaviour
# -----------------------------------------------------


# One valid call per pack, used to drive the auth paths.
VALID_CALL = {
    "gmail": (lambda: gmail.messages_list, {"q": "is:unread"}),
    "gcalendar": (lambda: gcalendar.events_list, {"calendar_id": "primary"}),
    "gsheets": (
        lambda: gsheets.spreadsheets_values_get,
        {"spreadsheet_id": "s1", "range": "A1"},
    ),
    "slack": (lambda: slack.conversations_list, {}),
    "stripe": (lambda: stripe.balance_retrieve, {}),
    "firecrawl": (lambda: firecrawl.scrape, {"url": "https://example.com"}),
    "gdocs": (lambda: gdocs.documents_get, {"document_id": "d1"}),
    "gforms": (lambda: gforms.forms_get, {"form_id": "f1"}),
    "gdrive": (lambda: gdrive.files_list, {"q": "trashed = false"}),
    "github": (lambda: github.repos_get, {"owner": "o", "repo": "r"}),
    "linear": (lambda: linear.viewer, {}),
    "shopify": (lambda: shopify.shop_get, {}),
    "notion": (lambda: notion.users_retrieve_me, {}),
    "granola": (lambda: granola.notes_list, {}),
}


def _valid_call(pack):
    get_tool, args = VALID_CALL[pack.__name__.rsplit(".", 1)[-1]]
    return get_tool(), args


@pytest.mark.parametrize("pack", GOOGLE_PACKS, ids=lambda p: p.__name__)
async def test_unconfigured_google_pack_raises_credential_error(pack, monkeypatch):
    monkeypatch.setattr(pack._credentials, "_provider", None)
    tool, args = _valid_call(pack)
    with pytest.raises(CredentialError) as excinfo:
        await tool.ainvoke(args)
    assert "configure" in str(excinfo.value)


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
async def test_unconfigured_api_key_pack_fails_before_any_request(pack, monkeypatch):
    """No doomed request should leave the process."""
    monkeypatch.setattr(pack._headers, "_api_key", None)
    tool, args = _valid_call(pack)
    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="configure"):
            await tool.ainvoke(args)
        assert not route.called


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
async def test_a_tool_added_without_ceremony_is_still_guarded(pack, monkeypatch):
    """The regression that motivated resolving headers in the runtime.

    Previously each tool had to opt in via build_request=_guard(...); a tool
    added without it sent the unconfigured sentinel over the wire."""
    monkeypatch.setattr(pack._headers, "_api_key", None)
    reference, args = _valid_call(pack)

    plain = Tool(
        name="added_later",
        args_schema=reference.args_schema,
        method=reference.method,
        url_template=reference.url_template,
        base_url=reference.base_url,
        api_key_headers=pack._headers,
    )

    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError):
            await plain.ainvoke(args)
        assert not route.called


# How each API-key pack takes its credential, and which header it lands in.
# Most take `api_key` and use Authorization; Shopify needs the store as well,
# because its host is a property of the installation, and puts the token in its
# own header.
CONFIGURE_CALL = {
    "shopify": ({"shop": "my-store", "access_token": "late-key"}, "x-shopify-access-token"),
}
_DEFAULT_CONFIGURE = ({"api_key": "late-key"}, "authorization")


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
async def test_configure_after_construction_reaches_existing_tools(pack, monkeypatch):
    monkeypatch.setattr(pack._headers, "_api_key", None)
    tool, args = _valid_call(pack)
    kwargs, header = CONFIGURE_CALL.get(pack.__name__.rsplit(".", 1)[-1], _DEFAULT_CONFIGURE)
    pack.configure(**kwargs)

    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        await tool.ainvoke(args)
        assert "late-key" in route.calls.last.request.headers[header]


# -----------------------------------------------------
# Gmail — the flagship path
# -----------------------------------------------------


@respx.mock
async def test_gmail_messages_send_produces_a_base64url_raw_body():
    """The demo path: EmailContent in, base64url RFC822 `raw` on the wire."""
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1", "threadId": "t1"})
    )

    result = await gmail.messages_send.ainvoke(
        body={"raw": {"to": "ada@example.com", "subject": "Hi", "body": "Hello"}}
    )

    assert result == {"id": "m1", "threadId": "t1"}
    sent = json.loads(route.calls.last.request.content)
    assert set(sent) == {"raw"}
    assert "=" not in sent["raw"]  # unpadded base64url

    msg = email.message_from_string(_decode_b64url(sent["raw"]))
    assert msg["To"] == "ada@example.com"
    assert msg["Subject"] == "Hi"
    assert "Hello" in msg.get_payload(decode=True).decode()
    assert route.calls.last.request.headers["authorization"] == "Bearer tok"


@respx.mock
async def test_gmail_messages_list_get():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "m1"}]})
    )

    result = await gmail.messages_list.ainvoke(q="is:unread", maxResults=5)

    assert result["messages"] == [{"id": "m1"}]
    params = dict(route.calls.last.request.url.params)
    assert params["q"] == "is:unread"
    assert params["maxResults"] == "5"


def test_gmail_send_schema_shows_email_content_not_base64():
    """What the model sees is the semantic type, not the wire type."""
    body_model = gmail.messages_send.llm_schema().model_fields["body"].annotation
    raw = body_model.model_fields["raw"]
    assert raw.annotation.__name__ == "EmailContent"


def test_gmail_send_schema_hides_response_only_fields():
    body_model = gmail.messages_send.llm_schema().model_fields["body"].annotation
    for hidden in ("id", "labelIds", "snippet", "payload", "sizeEstimate"):
        assert hidden not in body_model.model_fields


# -----------------------------------------------------
# Gmail response handler
# -----------------------------------------------------


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


@respx.mock
async def test_threads_get_response_handler_strips_the_mime_tree():
    gmail.configure(StaticTokenProvider("tok"))
    raw_thread = {
        "id": "t1",
        "historyId": "9",
        "messages": [
            {
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX"],
                "snippet": "hello there",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "headers": [
                        {"name": "From", "value": "ada@example.com"},
                        {"name": "Subject", "value": "Hi"},
                        {"name": "X-Internal-Noise", "value": "drop me"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": _b64("the plain body")},
                        },
                        {
                            "mimeType": "text/html",
                            "body": {"data": _b64("<p>the <b>html</b> body</p>")},
                        },
                        {
                            "mimeType": "application/pdf",
                            "filename": "report.pdf",
                            "body": {"attachmentId": "att1", "size": 4096},
                        },
                    ],
                },
            }
        ],
    }
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/threads/t1").mock(
        return_value=httpx.Response(200, json=raw_thread)
    )

    result = await gmail.threads_get.ainvoke(id="t1")

    assert result["id"] == "t1"
    assert result["historyId"] == "9"
    message = result["messages"][0]

    # text/plain wins over text/html
    assert message["bodyText"] == "the plain body"
    # only the useful headers survive
    assert message["headers"] == {"From": "ada@example.com", "Subject": "Hi"}
    # attachment metadata without the bytes
    assert message["attachments"] == [
        {
            "attachmentId": "att1",
            "filename": "report.pdf",
            "mimeType": "application/pdf",
            "size": 4096,
        }
    ]
    # no base64 blobs anywhere in the output
    assert "data" not in json.dumps(result)


async def test_html_only_message_is_flattened_to_text():
    from charter.packs.gmail.response_handlers import extract_thread_text

    result = await extract_thread_text(
        {
            "id": "t1",
            "messages": [
                {
                    "id": "m1",
                    "payload": {
                        "mimeType": "text/html",
                        "body": {
                            "data": _b64(
                                "<html><head><style>p{color:red}</style></head>"
                                "<body><p>First para</p><p>Second para</p>"
                                "<script>alert(1)</script></body></html>"
                            )
                        },
                    },
                }
            ],
        }
    )

    body = result["messages"][0]["bodyText"]
    assert "First para" in body
    assert "Second para" in body
    assert "color:red" not in body  # style dropped
    assert "alert(1)" not in body  # script dropped
    assert "<p>" not in body  # markup gone


async def test_html_entities_are_decoded():
    from charter import html_to_text

    assert html_to_text("<p>Caf&eacute; &amp; cr&egrave;me</p>") == "Café & crème"


async def test_calendar_parts_are_surfaced_separately():
    from charter.packs.gmail.response_handlers import extract_thread_text

    result = await extract_thread_text(
        {
            "id": "t1",
            "messages": [
                {
                    "id": "m1",
                    "payload": {
                        "mimeType": "multipart/mixed",
                        "parts": [
                            {"mimeType": "text/plain", "body": {"data": _b64("invite")}},
                            {
                                "mimeType": "text/calendar",
                                "body": {"data": _b64("BEGIN:VCALENDAR")},
                            },
                        ],
                    },
                }
            ],
        }
    )
    assert result["messages"][0]["calendar"] == "BEGIN:VCALENDAR"


# -----------------------------------------------------
# Gmail — reading one message, one draft, one label
#
# messages.get was the endpoint agents reached for most and the pack did not
# have: 147 calls' worth of demand against nine tools that could only list ids
# or read a whole thread.
# -----------------------------------------------------


def _raw_rfc822() -> str:
    """A base64url RFC-822 blob — the single field `format=raw` answers with."""
    message = EmailMessage()
    message["From"] = "ada@example.com"
    message["Subject"] = "Hi"
    message["X-Internal-Noise"] = "drop me"
    message.set_content("the plain body")
    message.add_attachment(
        b"%PDF-1.4 binary bytes",
        maintype="application",
        subtype="pdf",
        filename="report.pdf",
    )
    return base64.urlsafe_b64encode(bytes(message)).decode().rstrip("=")


@respx.mock
async def test_gmail_messages_get_reads_one_message_and_drops_the_mime_tree():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "threadId": "t1",
                "labelIds": ["INBOX"],
                "snippet": "hello there",
                "payload": {
                    "mimeType": "multipart/mixed",
                    "headers": [
                        {"name": "From", "value": "ada@example.com"},
                        {"name": "Subject", "value": "Hi"},
                        {"name": "X-Internal-Noise", "value": "drop me"},
                    ],
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": _b64("the plain body")}},
                        {
                            "mimeType": "application/pdf",
                            "filename": "report.pdf",
                            "body": {"attachmentId": "att1", "size": 4096},
                        },
                    ],
                },
            },
        )
    )

    result = await gmail.messages_get.ainvoke(id="m1", format="full")

    assert dict(route.calls.last.request.url.params) == {"format": "full"}
    assert result["bodyText"] == "the plain body"
    assert result["headers"] == {"From": "ada@example.com", "Subject": "Hi"}
    assert result["attachments"] == [
        {
            "attachmentId": "att1",
            "filename": "report.pdf",
            "mimeType": "application/pdf",
            "size": 4096,
        }
    ]
    assert "data" not in json.dumps(result)


async def test_messages_get_reads_the_raw_representation_too():
    """`format=raw` fills `raw` and leaves `payload` empty.

    A handler that only knows the payload tree answers a raw read with an empty
    body and nothing saying why, which is the failure this branch exists for.
    """
    from charter.packs.gmail.response_handlers import extract_message_text

    result = await extract_message_text(
        {"id": "m1", "threadId": "t1", "labelIds": ["INBOX"], "raw": _raw_rfc822()}
    )

    assert result["bodyText"].strip() == "the plain body"
    assert result["headers"] == {"From": "ada@example.com", "Subject": "Hi"}
    # No attachmentId exists in this representation; the metadata still does.
    assert result["attachments"] == [
        {"filename": "report.pdf", "mimeType": "application/pdf", "size": 21}
    ]
    assert "%PDF" not in json.dumps(result)


async def test_a_minimal_read_reports_no_body_rather_than_an_empty_one():
    """`format=minimal` asks for neither headers nor body.

    Returning `bodyText: ""` there would say the message is empty, which is a
    different fact from not having asked for it.
    """
    from charter.packs.gmail.response_handlers import extract_message_text

    result = await extract_message_text(
        {"id": "m1", "threadId": "t1", "labelIds": ["UNREAD"], "snippet": "hello"}
    )

    assert "bodyText" not in result
    assert "headers" not in result
    assert result == {
        "id": "m1",
        "threadId": "t1",
        "labelIds": ["UNREAD"],
        "snippet": "hello",
    }


async def test_a_raw_read_decodes_headers_the_way_the_payload_path_does():
    """RFC 2047 encoded-words, which only the raw representation carries.

    Gmail decodes headers itself in the `payload` form, so without this the two
    representations disagree about the same message: one says `Café`, the other
    says `=?utf-8?b?Q2Fmw6k=?=`.
    """
    from charter.packs.gmail.response_handlers import extract_message_text

    message = EmailMessage()
    message["Subject"] = "Café ☕ résumé"
    message.set_content("the plain body")
    message.add_attachment(
        b"data", maintype="application", subtype="pdf", filename="rapport-café.pdf"
    )
    raw = base64.urlsafe_b64encode(bytes(message)).decode().rstrip("=")

    result = await extract_message_text({"id": "m1", "raw": raw})

    assert result["headers"]["Subject"] == "Café ☕ résumé"
    assert result["attachments"][0]["filename"] == "rapport-café.pdf"
    json.dumps(result)  # header values must survive as plain strings


async def test_a_raw_read_of_a_message_with_no_parts():
    """The common case: a plain text email, no multipart wrapper to walk."""
    from charter.packs.gmail.response_handlers import extract_message_text

    message = EmailMessage()
    message["Subject"] = "Plain"
    message.set_content("just text")
    raw = base64.urlsafe_b64encode(bytes(message)).decode().rstrip("=")

    result = await extract_message_text({"id": "m2", "raw": raw})

    assert result["bodyText"].strip() == "just text"
    assert result["headers"] == {"Subject": "Plain"}
    assert "attachments" not in result


def test_the_message_format_literal_holds_gmails_whole_enum():
    """Gmail's shared Format enum, asserted against its values, not itself."""
    from charter.packs.gmail.types.message.models import MessageFormat

    assert set(get_args(MessageFormat)) == {"minimal", "full", "raw", "metadata"}


def test_threads_get_declares_the_narrower_enum_gmail_documents_for_it():
    """`raw` is not offered on threads.get, to cap the size of one response."""
    from charter.packs.gmail.types.thread.models import Format as ThreadFormat

    assert set(get_args(ThreadFormat)) == {"full", "metadata", "minimal"}


@respx.mock
async def test_gmail_drafts_get_projects_the_message_and_keeps_the_id():
    gmail.configure(StaticTokenProvider("tok"))
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/drafts/d1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "r-123",
                "message": {
                    "id": "m1",
                    "threadId": "t1",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [{"name": "Subject", "value": "Draft subject"}],
                        "body": {"data": _b64("the draft body")},
                    },
                },
            },
        )
    )

    result = await gmail.drafts_get.ainvoke(id="d1")

    # The id is what drafts_update, drafts_send and drafts_delete take next.
    assert result["id"] == "r-123"
    assert result["message"]["bodyText"] == "the draft body"
    assert result["message"]["headers"] == {"Subject": "Draft subject"}
    assert "data" not in json.dumps(result)


@respx.mock
async def test_gmail_drafts_list_get():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/drafts").mock(
        return_value=httpx.Response(200, json={"drafts": [{"id": "d1"}]})
    )

    result = await gmail.drafts_list.ainvoke(q="is:unread", maxResults=5, includeSpamTrash=True)

    assert result["drafts"] == [{"id": "d1"}]
    params = dict(route.calls.last.request.url.params)
    assert params == {"maxResults": "5", "q": "is:unread", "includeSpamTrash": "true"}


def test_drafts_list_walks_googles_cursor_and_stops():
    pagination = gmail.drafts_list.pagination
    assert pagination is not None

    first = {"userId": "me"}
    second = pagination.next_page_args({"drafts": [{"id": "d1"}], "nextPageToken": "p2"}, first)
    assert second == {"userId": "me", "pageToken": "p2"}
    # Google omits the token on the last page.
    assert pagination.next_page_args({"drafts": [{"id": "d2"}]}, second) is None


@respx.mock
async def test_gmail_drafts_update_puts_a_whole_rfc822_message():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.put("https://gmail.googleapis.com/gmail/v1/users/me/drafts/d1").mock(
        return_value=httpx.Response(200, json={"id": "d1", "message": {"id": "m2"}})
    )

    await gmail.drafts_update.ainvoke(
        id="d1",
        body={"message": {"raw": {"to": "ada@example.com", "subject": "Revised", "body": "v2"}}},
    )

    sent = json.loads(route.calls.last.request.content)
    assert set(sent) == {"message"}
    assert set(sent["message"]) == {"raw"}
    msg = email.message_from_string(_decode_b64url(sent["message"]["raw"]))
    assert msg["To"] == "ada@example.com"
    assert msg["Subject"] == "Revised"


@respx.mock
async def test_gmail_drafts_send_posts_the_id_alone():
    """drafts.send takes a Draft, and reads exactly one field of it."""
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/drafts/send").mock(
        return_value=httpx.Response(200, json={"id": "m9", "threadId": "t9"})
    )

    result = await gmail.drafts_send.ainvoke(body={"id": "r-123"})

    assert result == {"id": "m9", "threadId": "t9"}
    assert json.loads(route.calls.last.request.content) == {"id": "r-123"}


def test_drafts_send_asks_for_the_id_and_nothing_else():
    """The draft's content was fixed when it was saved; asking again for a
    message here would invite the model to compose a second one."""
    body_model = gmail.drafts_send.llm_schema().model_fields["body"].annotation
    assert set(body_model.model_fields) == {"id"}
    assert body_model.model_fields["id"].is_required()


def test_drafts_create_and_update_still_withhold_the_draft_id():
    """The id is the server's on the way in for both — the path carries it."""
    for tool in (gmail.drafts_create, gmail.drafts_update):
        body_model = tool.llm_schema().model_fields["body"].annotation
        assert "id" not in body_model.model_fields


@respx.mock
async def test_gmail_labels_get():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/labels/Label_5").mock(
        return_value=httpx.Response(
            200, json={"id": "Label_5", "name": "Receipts", "messagesTotal": 12}
        )
    )

    result = await gmail.labels_get.ainvoke(id="Label_5")

    assert result["name"] == "Receipts"
    assert route.calls.last.request.url.params == httpx.QueryParams()


NEW_GMAIL_CALLS = {
    "threads_trash": {"id": "t1"},
    "threads_delete": {"id": "t1"},
    "labels_delete": {"id": "Label_5"},
    "messages_get": {"id": "m1"},
    "drafts_get": {"id": "d1"},
    "drafts_list": {},
    "drafts_delete": {"id": "d1"},
    "labels_get": {"id": "Label_5"},
}


@pytest.mark.parametrize("name, args", sorted(NEW_GMAIL_CALLS.items()))
@respx.mock
async def test_the_no_argument_call_sends_no_query_parameters(name, args):
    """Everything a schema defaults into the request shows up on this line."""
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.route().mock(return_value=httpx.Response(200, json={}))

    await getattr(gmail, name).ainvoke(dict(args))

    request = route.calls.last.request
    assert dict(request.url.params) == {}, f"{name} sends a parameter nobody asked for"
    assert request.url.path.startswith("/gmail/v1/users/me/")


# -----------------------------------------------------
# Gmail — the rest of the label lifecycle
# -----------------------------------------------------


@respx.mock
async def test_gmail_labels_update_replaces_the_whole_label():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.put("https://gmail.googleapis.com/gmail/v1/users/me/labels/Label_5").mock(
        return_value=httpx.Response(200, json={"id": "Label_5", "name": "Receipts"})
    )

    await gmail.labels_update.ainvoke(
        id="Label_5", body={"name": "Receipts", "labelListVisibility": "labelShow"}
    )

    assert json.loads(route.calls.last.request.content) == {
        "name": "Receipts",
        "labelListVisibility": "labelShow",
    }


@respx.mock
async def test_gmail_labels_patch_sends_only_what_changed():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.patch("https://gmail.googleapis.com/gmail/v1/users/me/labels/Label_5").mock(
        return_value=httpx.Response(200, json={"id": "Label_5"})
    )

    await gmail.labels_patch.ainvoke(
        id="Label_5", body={"color": {"textColor": "#ffffff", "backgroundColor": "#cc3a21"}}
    )

    assert json.loads(route.calls.last.request.content) == {
        "color": {"textColor": "#ffffff", "backgroundColor": "#cc3a21"}
    }


def test_patch_asks_for_no_field_and_update_asks_for_the_name():
    """The difference between the two endpoints is what an absent field means.

    Reusing Label for patch would make `name` required on the one endpoint
    whose point is not having to send it.
    """
    patch_body = gmail.labels_patch.llm_schema().model_fields["body"].annotation
    update_body = gmail.labels_update.llm_schema().model_fields["body"].annotation

    assert [n for n, f in patch_body.model_fields.items() if f.is_required()] == []
    assert [n for n, f in update_body.model_fields.items() if f.is_required()] == ["name"]
    # Both offer the same four writable fields, and nothing Gmail computes.
    writable = {"name", "messageListVisibility", "labelListVisibility", "color"}
    assert set(patch_body.model_fields) == writable
    assert set(update_body.model_fields) == writable


@pytest.mark.parametrize("tool", ["labels_create", "labels_update", "labels_patch"])
def test_a_half_set_colour_is_caught_before_the_request(tool):
    """Gmail documents both colour fields as required to set a colour, and
    answers a half-set one with a 400 the model cannot tell from a bad id."""
    # The rule lives on Color, and has to survive into the view the model fills
    # in — labels_create takes no `id`, so the body model is what all three share.
    body = getattr(gmail, tool).llm_schema().model_fields["body"].annotation

    with pytest.raises(ValidationError, match="both required"):
        body.model_validate({"name": "x", "color": {"textColor": "#ffffff"}})

    # Both together still pass.
    body.model_validate(
        {"name": "x", "color": {"textColor": "#ffffff", "backgroundColor": "#cc3a21"}}
    )


# -----------------------------------------------------
# Gmail — the rest of the thread lifecycle
# -----------------------------------------------------


@respx.mock
async def test_gmail_threads_modify_labels_a_whole_conversation():
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/threads/t1/modify").mock(
        return_value=httpx.Response(200, json={"id": "t1", "messages": []})
    )

    await gmail.threads_modify.ainvoke(
        id="t1", body={"add_label_ids": ["Label_5"], "remove_label_ids": ["UNREAD"]}
    )

    # snake_case in the schema, camelCase on the wire, as messages_modify sends it
    assert json.loads(route.calls.last.request.content) == {
        "addLabelIds": ["Label_5"],
        "removeLabelIds": ["UNREAD"],
    }


@pytest.mark.parametrize("name", ["threads_trash", "threads_untrash"])
@respx.mock
async def test_gmail_thread_trash_toggles_post_an_empty_body(name):
    gmail.configure(StaticTokenProvider("tok"))
    verb = name.split("_")[1]
    route = respx.post(f"https://gmail.googleapis.com/gmail/v1/users/me/threads/t1/{verb}").mock(
        return_value=httpx.Response(200, json={"id": "t1", "messages": []})
    )

    await getattr(gmail, name).ainvoke(id="t1")

    assert route.calls.last.request.content == b""


@respx.mock
async def test_thread_writes_trim_the_conversation_they_return():
    """modify, trash and untrash all answer with the full Thread.

    Left raw that is the same MIME tree threads_get returns, on a call whose
    result the agent mostly ignores.
    """
    gmail.configure(StaticTokenProvider("tok"))
    respx.post("https://gmail.googleapis.com/gmail/v1/users/me/threads/t1/trash").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "t1",
                "messages": [
                    {
                        "id": "m1",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [{"name": "Subject", "value": "Hi"}],
                            "body": {"data": _b64("the plain body")},
                        },
                    }
                ],
            },
        )
    )

    result = await gmail.threads_trash.ainvoke(id="t1")

    assert result["messages"][0]["bodyText"] == "the plain body"
    assert "data" not in json.dumps(result)


def test_only_threads_delete_asks_for_the_full_mailbox_scope():
    """Google covers every other endpoint here with gmail.modify, and requires
    full access for the one delete that cannot be undone. Declared per tool, a
    consent screen asks for it only when that tool is handed out."""
    from charter.auth.flow import scopes_for

    assert gmail.threads_delete.scopes == [gmail.FULL_MAILBOX_SCOPE]
    assert [t.name for t in gmail.TOOLS if gmail.FULL_MAILBOX_SCOPE in t.scopes] == [
        "threads_delete"
    ]

    without = [t for t in gmail.TOOLS if t is not gmail.threads_delete]
    assert scopes_for(without) == gmail.SCOPES
    assert scopes_for(gmail.TOOLS) == [*gmail.SCOPES, gmail.FULL_MAILBOX_SCOPE]


# Every DELETE in the pack: no body, no query, and the id in the path. Gmail
# answers an empty JSON object to all three.
DELETE_TOOLS = {
    "drafts_delete": "drafts/d1",
    "labels_delete": "labels/Label_5",
    "threads_delete": "threads/t1",
}


@pytest.mark.parametrize("name, path", sorted(DELETE_TOOLS.items()))
@respx.mock
async def test_gmail_deletes_send_nothing_but_the_path(name, path):
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.delete(f"https://gmail.googleapis.com/gmail/v1/users/me/{path}").mock(
        return_value=httpx.Response(200, json={})
    )

    await getattr(gmail, name).ainvoke(id=path.split("/")[1])

    request = route.calls.last.request
    assert request.method == "DELETE"
    assert request.content == b""
    assert dict(request.url.params) == {}


# -----------------------------------------------------
# Calendar
# -----------------------------------------------------


@respx.mock
async def test_calendar_events_list_get():
    gcalendar.configure(StaticTokenProvider("tok"))
    route = respx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")

    assert result == {"items": []}
    assert route.calls.last.request.headers["authorization"] == "Bearer tok"


@respx.mock
async def test_calendar_events_insert_post_casing():
    gcalendar.configure(StaticTokenProvider("tok"))
    route = respx.post("https://www.googleapis.com/calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"id": "e1"})
    )

    await gcalendar.events_insert.ainvoke(
        calendar_id="primary",
        event={
            "summary": "Standup",
            "start": {"date_time": "2026-09-01T09:00:00Z"},
            "end": {"date_time": "2026-09-01T09:15:00Z"},
        },
    )

    body = json.loads(route.calls.last.request.content)
    assert body["summary"] == "Standup"
    # snake_case in the schema, camelCase on the wire
    assert "dateTime" in body["start"]


# -----------------------------------------------------
# Sheets
# -----------------------------------------------------


@respx.mock
async def test_sheets_values_get():
    gsheets.configure(StaticTokenProvider("tok"))
    route = respx.get("https://sheets.googleapis.com/v4/spreadsheets/s1/values/Sheet1!A1:C2").mock(
        return_value=httpx.Response(200, json={"values": [["a"]]})
    )

    result = await gsheets.spreadsheets_values_get.ainvoke(
        spreadsheet_id="s1", range="Sheet1!A1:C2"
    )

    assert result == {"values": [["a"]]}
    assert route.called


@respx.mock
async def test_sheets_values_append_sends_proto_json_as_plain_arrays():
    """The Sheets bridge: strict Value types in the schema, plain JSON on the wire."""
    gsheets.configure(StaticTokenProvider("tok"))
    route = respx.post(
        "https://sheets.googleapis.com/v4/spreadsheets/s1/values/Sheet1!A1:append"
    ).mock(return_value=httpx.Response(200, json={"updates": {"updatedRows": 2}}))

    await gsheets.spreadsheets_values_append.ainvoke(
        spreadsheet_id="s1",
        range="Sheet1!A1",
        value_input_option="USER_ENTERED",
        value_range={"range": "Sheet1!A1", "values": [["Name", "Score"], ["Ada", 99]]},
    )

    body = json.loads(route.calls.last.request.content)
    assert body["values"] == [["Name", "Score"], ["Ada", 99]]


# -----------------------------------------------------
# Firecrawl (API key)
# -----------------------------------------------------


@respx.mock
async def test_firecrawl_scrape_post():
    firecrawl.configure(api_key="fc-test")
    route = respx.post("https://api.firecrawl.dev/v2/scrape").mock(
        return_value=httpx.Response(200, json={"data": {"markdown": "# Hi"}})
    )

    result = await firecrawl.scrape.ainvoke(url="https://example.com")

    assert result["data"]["markdown"] == "# Hi"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer fc-test"
    assert json.loads(request.content)["url"] == "https://example.com"


@respx.mock
async def test_firecrawl_search_post():
    firecrawl.configure(api_key="fc-test")
    route = respx.post("https://api.firecrawl.dev/v2/search").mock(
        return_value=httpx.Response(200, json={"data": {"web": []}})
    )

    await firecrawl.search.ainvoke(query="charter python")
    assert json.loads(route.calls.last.request.content)["query"] == "charter python"


def test_api_key_packs_declare_no_format_markers():
    """The pack guards wrap the auto-transformer, so this is not load-bearing —
    but a Format marker appearing here would mean the wire format changed."""
    from charter.types import Format

    for pack in API_KEY_PACKS:
        for tool in pack.TOOLS:
            for field in tool.args_schema.model_fields.values():
                assert not any(isinstance(m, Format) for m in field.metadata)


# -----------------------------------------------------
# Configuration plumbing
# -----------------------------------------------------


async def test_configure_reaches_tools_built_before_it(monkeypatch):
    """Tool identity is stable across configure() — that is the whole design."""
    tool_before = gmail.messages_send
    gmail.configure(StaticTokenProvider("later-token"))
    assert gmail.messages_send is tool_before

    with respx.mock:
        route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send").mock(
            return_value=httpx.Response(200, json={})
        )
        await tool_before.ainvoke(body={"raw": {"to": "a@b.com", "subject": "S", "body": "B"}})

    assert route.calls.last.request.headers["authorization"] == "Bearer later-token"


async def test_google_packs_fall_back_to_the_documented_env_var(monkeypatch):
    monkeypatch.setattr(gcalendar._credentials, "_provider", None)
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "from-env")

    with respx.mock:
        route = respx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events").mock(
            return_value=httpx.Response(200, json={})
        )
        await gcalendar.events_list.ainvoke(calendar_id="primary")

    assert route.calls.last.request.headers["authorization"] == "Bearer from-env"


def test_packs_import_without_bs4_or_other_extras():
    """Response handlers must be stdlib + pydantic + Charter only."""
    import sys

    assert "bs4" not in sys.modules
    assert "BeautifulSoup" not in gmail.extract_thread_text.__module__


# -----------------------------------------------------
# Quota metadata
# -----------------------------------------------------

EXPECTED_QUOTA = {
    "messages_send": 100,
    "drafts_send": 100,
    "messages_batch_modify": 50,
    "threads_get": 40,
    "messages_get": 20,
    "drafts_get": 20,
    "drafts_update": 15,
    "threads_list": 10,
    "threads_modify": 10,
    "threads_untrash": 10,
    "threads_trash": 20,
    "threads_delete": 20,
    "drafts_create": 10,
    "drafts_delete": 10,
    "messages_list": 5,
    "messages_modify": 5,
    "drafts_list": 5,
    "labels_create": 5,
    "labels_update": 5,
    # Google's table lists every labels.* method except patch; this mirrors
    # labels.update, the same write with patch semantics.
    "labels_patch": 5,
    "labels_delete": 5,
    "labels_list": 1,
    "labels_get": 1,
}


def test_gmail_tools_carry_googles_published_quota_costs():
    """These are Gmail's own units, hand-collected per endpoint. Losing them
    means re-deriving every one from the provider's docs."""
    actual = {t.name: t.quota_cost for t in gmail.TOOLS}
    assert actual == EXPECTED_QUOTA


@pytest.mark.parametrize("pack", GOOGLE_PACKS, ids=lambda p: p.__name__)
def test_google_packs_annotate_quota_cost_and_link_the_docs(pack):
    assert pack.QUOTA_DOC_URL.startswith("https://developers.google.com/")
    for tool in pack.TOOLS:
        assert isinstance(tool.quota_cost, int) and tool.quota_cost >= 1, (
            f"{tool.name} has no quota cost"
        )
        assert tool.quota_doc_url == pack.QUOTA_DOC_URL


@pytest.mark.parametrize("pack", API_KEY_PACKS, ids=lambda p: p.__name__)
def test_api_key_packs_declare_no_quota_cost(pack):
    """Upstream had none for these APIs; absent is honest, 0 would not be."""
    for tool in pack.TOOLS:
        assert tool.quota_cost is None


def test_quota_cost_is_metadata_and_does_not_affect_execution():
    """Nothing enforces it yet. It must not silently gate a call."""
    assert gmail.messages_send.quota_cost == 100
    assert not hasattr(gmail.messages_send._executor, "_quota_cost")


# -----------------------------------------------------
# Google query casing
#
# Google's query parameters are camelCase, like its bodies. Three shipped packs
# defaulted to snake_case and sent `max_results`, `valueRenderOption` spelled
# `value_render_option`, and so on. Google ignores unknown query parameters, so
# every call succeeded and every filter was silently dropped — the worst kind of
# wrong, because nothing looks broken.
# -----------------------------------------------------


@pytest.mark.parametrize("pack", GOOGLE_PACKS, ids=lambda p: p.__name__)
def test_google_packs_send_camel_cased_query_parameters(pack):
    for tool in pack.TOOLS:
        assert tool.query_case == "camel", f"{tool.name} would send snake_case"


@respx.mock
async def test_calendar_filters_reach_google_under_the_names_it_documents():
    gcalendar.configure(StaticTokenProvider("tok"))
    route = respx.get("https://www.googleapis.com/calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    await gcalendar.events_list.ainvoke(
        calendar_id="primary", max_results=5, single_events=True, order_by="startTime"
    )

    params = dict(route.calls.last.request.url.params)
    assert params == {"maxResults": "5", "singleEvents": "true", "orderBy": "startTime"}
    assert "max_results" not in params


@respx.mock
async def test_sheets_render_options_reach_google_under_the_names_it_documents():
    gsheets.configure(StaticTokenProvider("tok"))
    route = respx.get("https://sheets.googleapis.com/v4/spreadsheets/s1/values/A1:B2").mock(
        return_value=httpx.Response(200, json={"values": []})
    )

    await gsheets.spreadsheets_values_get.ainvoke(
        spreadsheet_id="s1",
        range="A1:B2",
        value_render_option="UNFORMATTED_VALUE",
        major_dimension="COLUMNS",
    )

    params = dict(route.calls.last.request.url.params)
    assert params == {
        "valueRenderOption": "UNFORMATTED_VALUE",
        "majorDimension": "COLUMNS",
    }


@respx.mock
async def test_gmails_already_camel_field_names_are_unaffected():
    """Gmail names its fields camelCase, so the cascade must be a no-op there."""
    gmail.configure(StaticTokenProvider("tok"))
    route = respx.get("https://gmail.googleapis.com/gmail/v1/users/me/messages").mock(
        return_value=httpx.Response(200, json={"messages": []})
    )

    await gmail.messages_list.ainvoke(user_id="me", q="is:unread", maxResults=5)

    assert dict(route.calls.last.request.url.params) == {"q": "is:unread", "maxResults": "5"}


# -----------------------------------------------------
# Progressive disclosure — the summary projection
# -----------------------------------------------------


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__.rsplit(".", 1)[-1])
def test_a_summary_is_the_schema_minus_its_parameters(pack):
    """`to_json_summary` must agree with `to_json_schema` on everything it keeps.

    Two projections of one declaration that disagree would let an agent plan
    against a name or a description the call does not honour.
    """
    for tool in pack.TOOLS:
        summary, full = tool.to_json_summary(), tool.to_json_schema()
        assert summary == {k: full[k] for k in summary}
        assert set(full) - set(summary) == {"parameters"}


@pytest.mark.parametrize("pack", ALL_PACKS, ids=lambda p: p.__name__.rsplit(".", 1)[-1])
def test_a_summary_keeps_the_whole_description(pack):
    """The description is the half an agent plans with, so it is not truncated.

    Reducing every description to its first sentence saves ~1,500 tokens out of
    ~71,000 and drops the guidance that prevents wrong calls ("only the title is
    honoured", "order the requests back-to-front").
    """
    for tool in pack.TOOLS:
        assert tool.to_json_summary()["description"] == tool.description


def test_summaries_cost_a_fraction_of_the_schemas():
    """The measurement the mechanism exists for, asserted loosely.

    Across the shipped packs the inlined parameter schemas are ~71,000 tokens
    and the summaries ~3,300. The bound is wide so it fails on a regression in
    kind — a summary that starts carrying parameters — not on a pack being added.
    """
    tools = [t for pack in ALL_PACKS for t in pack.TOOLS]
    schemas = sum(len(json.dumps(t.to_json_schema())) for t in tools)
    summaries = sum(len(json.dumps(t.to_json_summary())) for t in tools)
    assert summaries * 10 < schemas, (
        f"summaries are {summaries:,} chars against {schemas:,} of schema"
    )


def test_gmail_trims_every_response_that_has_anything_to_trim():
    """The six without a handler return ids or nothing at all.

    `messages_list` and `drafts_list` answer with ids and no content, the three
    deletes answer with an empty body, and `messages_batch_modify` returns
    nothing. A handler on any of them would save no bytes and add a way to be
    wrong; a *missing* handler anywhere else is how a pack leaks.
    """
    from charter.packs import gmail

    untrimmed = {t.name for t in gmail.TOOLS if not t._executor._response_handler}
    assert untrimmed == {
        "messages_list",
        "drafts_list",
        "messages_batch_modify",
        "threads_delete",
        "drafts_delete",
        "labels_delete",
    }


async def test_gmail_label_lists_drop_the_counters_and_render_hints():
    """A Label carries four counters Gmail recomputes on every read, a colour
    object and two visibility flags. None of it says what the label is."""
    import json

    from charter.packs.gmail.response_handlers import extract_labels

    raw = {
        "labels": [
            {
                "id": f"Label_{i}",
                "name": f"n{i}",
                "type": "user",
                "messagesTotal": 12,
                "messagesUnread": 3,
                "threadsTotal": 9,
                "threadsUnread": 2,
                "color": {"textColor": "#000000", "backgroundColor": "#ffffff"},
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            for i in range(30)
        ]
    }
    out = await extract_labels(raw)
    assert [x["name"] for x in out["labels"]] == [f"n{i}" for i in range(30)]
    assert all(set(x) <= {"id", "name", "type"} for x in out["labels"])
    assert len(json.dumps(out)) < len(json.dumps(raw)) * 0.4


async def test_a_created_label_reads_back_like_a_fetched_one():
    """labels_get, labels_create, labels_update and labels_patch all answer with
    one Label, so they are all projected the same way."""
    from charter.packs import gmail

    handlers = {
        t.name: t._executor._response_handler
        for t in gmail.TOOLS
        if t.name.startswith("labels_") and t._executor._response_handler
    }
    assert set(handlers) == {
        "labels_list",
        "labels_get",
        "labels_create",
        "labels_update",
        "labels_patch",
    }
    assert (
        len({handlers[n] for n in ("labels_get", "labels_create", "labels_update", "labels_patch")})
        == 1
    )
