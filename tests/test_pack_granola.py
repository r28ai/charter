"""Granola pack — a read API with one write surface, and snake_case throughout.

Granola is the pack where the casing check earns its place twice over. Its
query parameters and its bodies are both snake_case, which is neither of
Charter's two defaults acting alone, and the API ignores a query parameter it
does not recognise — so a `createdAfter` that should have been `created_after`
would have answered 200, returned the unfiltered list, and looked like a
working integration for as long as the pack existed. Every assertion about a
parameter name here is made against the bytes on the wire.

The other two things worth pinning are the two response handlers. A transcript
repeats a four-key speaker object once per line, and a note returns its summary
twice in two encodings; both trims have an unhappy path where the field they
project is absent, and a page that lost `hasMore` is a walk that cannot stop.
"""

from __future__ import annotations

import json

import httpx
import pydantic
import pytest
import respx

from charter import CredentialError
from charter.packs import granola

API = "https://public-api.granola.ai/"

# https://docs.granola.ai/api-reference/get-note
MACOS_ITEM = {
    "speaker": {"source": "microphone", "attribution": "me"},
    "text": "I'm done pretending. Greek is the only yoghurt that deserves us.",
    "start_time": "2026-01-27T15:30:00Z",
    "end_time": "2026-01-27T15:30:04Z",
}
IOS_ITEM = {
    "speaker": {"source": "microphone", "diarization_label": "Speaker B"},
    "text": "Finally. Regular yoghurt is just milk that gave up halfway.",
    "start_time": "2026-01-27T15:30:05Z",
    "end_time": "2026-01-27T15:30:09Z",
}
NAMED_ITEM = {
    "speaker": {"source": "speaker", "attribution": "them", "name": "Alice Smith"},
    "text": "The almond milk pivot is not on the agenda.",
    "start_time": "2026-01-27T15:30:10Z",
    "end_time": "2026-01-27T15:30:13Z",
}

NOTE = {
    "id": "not_1d3tmYTlCICgjy",
    "object": "note",
    "title": "Quarterly yoghurt budget review",
    "owner": {"name": "Oat Benson", "email": "oat@granola.ai"},
    "created_at": "2026-01-27T15:30:00Z",
    "updated_at": "2026-01-27T16:45:00Z",
    "web_url": "https://notes.granola.ai/d/f3e45e0f-24cc-480b-9a6c-8b1f5e3d7a2c",
    "calendar_event": {
        "event_title": "Quarterly yoghurt budget review",
        "invitees": [{"email": "raisin@granola.ai"}],
        "organiser": "oat@granola.ai",
        "calendar_event_id": "2su99n6iiik37iiknmb5t4fkfh_20260127T153000Z",
        "scheduled_start_time": "2026-01-27T15:30:00Z",
        "scheduled_end_time": "2026-01-27T16:30:00Z",
    },
    "attendees": [{"name": "Oat Benson", "email": "oat@granola.ai"}],
    "folder_membership": [
        {
            "id": "fol_4y6LduVdwSKC27",
            "object": "folder",
            "name": "Top secret recipes",
            "parent_folder_id": "fol_a74g2hvl98iUHG",
        }
    ],
    "summary_text": "The quarterly yoghurt budget review was a success. " * 20,
    "summary_markdown": "## Quarterly Yoghurt Budget Review\n\n" + "- A success\n" * 20,
    "private_notes_text": "Push back on the dairy forecast.",
    "private_notes_markdown": "- Push back on the **dairy** forecast.",
    "transcript": None,
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
    granola.configure(api_key="grn_test")


# -----------------------------------------------------
# The wire: snake_case in the query and in the body
# -----------------------------------------------------


@respx.mock
async def test_the_query_parameter_names_are_the_ones_granola_documents():
    """Granola ignores a parameter it cannot read, so a misspelling returns 200.

    `created_before`, `created_after`, `updated_after`, `folder_id`, `cursor`
    and `page_size` — all snake, none of them the camelCase the LLM schema
    spells them in.
    """
    route = respx.get(url__startswith=f"{API}v1/notes").mock(
        return_value=httpx.Response(200, json={"notes": [], "hasMore": False, "cursor": None})
    )

    await granola.notes_list.ainvoke(
        created_before="2026-02-01",
        created_after="2026-01-27T15:30:00Z",
        updated_after="2026-01-28",
        folder_id="fol_4y6LduVdwSKC27",
        cursor="eyJjcmVkZW50aWFsfQ==",
        page_size=30,
    )

    query = dict(route.calls[0].request.url.params)
    assert query == {
        "created_before": "2026-02-01",
        "created_after": "2026-01-27T15:30:00Z",
        "updated_after": "2026-01-28",
        "folder_id": "fol_4y6LduVdwSKC27",
        "cursor": "eyJjcmVkZW50aWFsfQ==",
        "page_size": "30",
    }


@respx.mock
async def test_a_post_body_is_snake_case_too():
    route = respx.post(f"{API}v1/webhook-endpoints").mock(
        return_value=httpx.Response(201, json={"id": "whe_2mKr8fQxLp7Ta3"})
    )

    await granola.webhook_endpoints_create.ainvoke(
        url="https://example.com/granola-webhooks",
        scopes=["personal", "public"],
        events=["note.generated"],
        folder_ids=["fol_2mKr8fQxLp7Ta3"],
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com/granola-webhooks",
        "scopes": ["personal", "public"],
        "events": ["note.generated"],
        "folder_ids": ["fol_2mKr8fQxLp7Ta3"],
    }


@respx.mock
async def test_the_key_goes_out_as_a_bearer_token():
    route = respx.get(f"{API}v1/folders").mock(
        return_value=httpx.Response(200, json={"folders": [], "hasMore": False, "cursor": None})
    )
    await granola.folders_list.ainvoke()
    assert route.calls[0].request.headers["authorization"] == "Bearer grn_test"


@pytest.mark.parametrize("tool", granola.TOOLS, ids=lambda t: t.name)
@respx.mock
async def test_the_no_argument_call_sends_nothing_it_was_not_asked_to(tool):
    """Everything a schema defaults into the request shows up on this line.

    Granola documents a default for `page_size` (10, or 50 on the transcript)
    and for `events` (all three). None of them are on the fields: a default
    copied onto a schema is sent on every call, which is a different request
    from the one the documentation describes.
    """
    route = respx.route(method=tool.method, url__startswith=API).mock(
        return_value=httpx.Response(200, json={})
    )

    required = {
        "note_id": "not_1d3tmYTlCICgjy",
        "webhook_endpoint_id": "whe_2mKr8fQxLp7Ta3",
        "url": "https://example.com/granola-webhooks",
        "scopes": ["personal"],
    }
    args = {
        name: required[name]
        for name, field in tool.args_schema.model_fields.items()
        if field.is_required()
    }
    await tool.ainvoke(args)

    request = route.calls[0].request
    assert not request.url.params, f"{tool.name} sends {dict(request.url.params)} unasked"
    body = request.content.decode()
    assert json.loads(body or "{}") == (
        {k: v for k, v in args.items() if k in ("url", "scopes")}
    )


# -----------------------------------------------------
# The enums, against Granola's values rather than their own
# -----------------------------------------------------


def test_the_scope_literal_holds_granolas_three_scopes():
    from typing import get_args

    from charter.packs.granola.types import WebhookScope

    assert set(get_args(WebhookScope)) == {"personal", "public", "workspace"}


def test_the_event_literal_holds_granolas_three_events():
    from typing import get_args

    from charter.packs.granola.types import WebhookEventName

    assert set(get_args(WebhookEventName)) == {
        "note.access_granted",
        "note.edited",
        "note.generated",
    }


def test_include_accepts_only_transcript():
    """Granola documents exactly one value, so the schema offers exactly one."""
    schema = granola.notes_get.to_json_schema()["parameters"]["properties"]["include"]
    allowed = [branch for branch in schema["anyOf"] if branch.get("type") != "null"]
    assert allowed == [{"const": "transcript", "type": "string"}]


def test_speaker_source_is_open_because_granola_says_it_may_grow():
    """The docs name two values and warn against assuming there will only be two.

    A closed `Literal` would start rejecting valid responses the day a third
    arrives, so this one is a `str` while the webhook enums are closed.
    """
    from charter.packs.granola.types import Speaker

    assert Speaker.model_fields["source"].annotation is not None
    Speaker(source="something_granola_added_later")


# -----------------------------------------------------
# The one cross-field rule, checked where input arrives
# -----------------------------------------------------


@pytest.mark.parametrize(
    "tool", [granola.webhook_endpoints_create, granola.webhook_endpoints_update],
    ids=lambda t: t.name,
)
def test_the_workspace_scope_rule_is_enforced_on_llm_input(tool):
    """`llm_schema()` is the model's input, and it is the one that needs checking.

    Granola answers 403 for `["workspace", "personal"]`, on both endpoints. The
    rule is a field validator rather than a `ConflictsWith` because it is about
    one field's contents, not about two fields meeting.
    """
    llm = tool.llm_schema()
    args = (
        {"url": "https://example.com/h"}
        if tool is granola.webhook_endpoints_create
        else {"webhookEndpointId": "whe_2mKr8fQxLp7Ta3"}
    )

    with pytest.raises(pydantic.ValidationError, match="workspace"):
        llm(scopes=["workspace", "personal"], **args)

    llm(scopes=["workspace"], **args)
    llm(scopes=["personal", "public"], **args)


def test_a_patch_body_mandates_nothing_but_its_path_parameter():
    """The whole point of the update endpoint is not having to resend the rest."""
    required = [
        name
        for name, field in granola.webhook_endpoints_update.llm_schema().model_fields.items()
        if field.is_required()
    ]
    assert required == ["webhook_endpoint_id"]


@respx.mock
async def test_an_empty_folder_ids_array_survives_to_the_wire():
    """It is how the update endpoint removes a filter, so it must not be dropped.

    Bodies are dumped with `exclude_none=True`, and `[]` is not `None` — this
    pins the difference, because losing it would turn "clear the filter" into a
    call that changes nothing and reports success.
    """
    route = respx.patch(f"{API}v1/webhook-endpoints/whe_2mKr8fQxLp7Ta3").mock(
        return_value=httpx.Response(200, json={"id": "whe_2mKr8fQxLp7Ta3"})
    )
    await granola.webhook_endpoints_update.ainvoke(
        webhook_endpoint_id="whe_2mKr8fQxLp7Ta3", folder_ids=[]
    )
    assert json.loads(route.calls[0].request.content) == {"folder_ids": []}


def test_an_id_that_is_not_a_granola_id_fails_before_the_request():
    """The quick start warns about this one by name: the web app URL carries a UUID."""
    with pytest.raises(pydantic.ValidationError):
        granola.notes_get.llm_schema()(noteId="f3e45e0f-24cc-480b-9a6c-8b1f5e3d7a2c")


def test_the_egress_map_is_exactly_what_granola_accepts():
    """Read the map as an auditor would: anything visible the API does not take.

    Granola separates its request and response shapes cleanly, so no request
    schema here carries a server-set field and no tool needs a
    `Mode("response_only")` to hide one. That is a claim about the API, and this
    is where it is checked rather than assumed.
    """
    from charter import egress_map

    visible = {
        tool: set(entry["visible"]) for tool, entry in egress_map(granola.TOOLS).items()
    }
    assert visible == {
        "notes_list": {
            "created_before", "created_after", "updated_after",
            "folder_id", "cursor", "page_size",
        },
        "notes_get": {"note_id", "include"},
        "notes_transcript_get": {"note_id", "cursor", "page_size"},
        "folders_list": {"cursor", "page_size"},
        "audit_list": {
            "action", "occurred_before", "occurred_after", "cursor", "page_size",
        },
        "webhook_endpoints_create": {"url", "scopes", "events", "folder_ids"},
        "webhook_endpoints_list": set(),
        "webhook_endpoints_update": {
            "webhook_endpoint_id", "url", "scopes", "events", "folder_ids", "enabled",
        },
        "webhook_endpoints_delete": {"webhook_endpoint_id"},
    }


# -----------------------------------------------------
# Response handlers
# -----------------------------------------------------


@respx.mock
async def test_a_transcript_speaker_collapses_to_the_word_it_spells():
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy/transcript").mock(
        return_value=httpx.Response(200, json={
            "transcript": [MACOS_ITEM, IOS_ITEM, NAMED_ITEM],
            "hasMore": False,
            "cursor": None,
        })
    )

    page = await granola.notes_transcript_get.ainvoke(note_id="not_1d3tmYTlCICgjy")

    assert [item["speaker"] for item in page["transcript"]] == [
        "me",             # attribution, where there is no resolved name
        "Speaker B",      # the anonymous iOS bucket
        "Alice Smith",    # the resolved name wins over the attribution
    ]
    # The text and the timings are what the caller came for, and are untouched.
    assert page["transcript"][0]["text"] == MACOS_ITEM["text"]
    assert page["transcript"][0]["start_time"] == "2026-01-27T15:30:00Z"
    assert page["transcript"][0]["end_time"] == "2026-01-27T15:30:04Z"


@respx.mock
async def test_the_paging_signal_survives_the_trim():
    """A trimmed page that lost `hasMore` is a walk with nothing to stop on."""
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy/transcript").mock(
        return_value=httpx.Response(200, json={
            "transcript": [MACOS_ITEM], "hasMore": True, "cursor": "eyJyb3dfb2Zmc2V0Ijo1MH0=",
        })
    )
    page = await granola.notes_transcript_get.ainvoke(note_id="not_1d3tmYTlCICgjy")
    assert page["hasMore"] is True
    assert page["cursor"] == "eyJyb3dfb2Zmc2V0Ijo1MH0="


@respx.mock
async def test_an_empty_transcript_page_still_reports_whether_more_follows():
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy/transcript").mock(
        return_value=httpx.Response(200, json={
            "transcript": [], "hasMore": False, "cursor": None})
    )
    page = await granola.notes_transcript_get.ainvoke(note_id="not_1d3tmYTlCICgjy")
    assert page == {"transcript": [], "hasMore": False, "cursor": None}


@respx.mock
async def test_a_speaker_granola_could_not_resolve_becomes_none_not_an_empty_object():
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy/transcript").mock(
        return_value=httpx.Response(200, json={
            "transcript": [{"speaker": {}, "text": "Someone said something."}],
            "hasMore": False, "cursor": None})
    )
    page = await granola.notes_transcript_get.ainvoke(note_id="not_1d3tmYTlCICgjy")
    assert page["transcript"][0]["speaker"] is None
    assert page["transcript"][0]["text"] == "Someone said something."


@respx.mock
async def test_a_note_returns_its_summary_once_rather_than_twice():
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(200, json=NOTE)
    )

    note = await granola.notes_get.ainvoke(note_id="not_1d3tmYTlCICgjy")

    assert note["summary_markdown"] == NOTE["summary_markdown"]
    assert "summary_text" not in note
    assert note["private_notes_markdown"] == NOTE["private_notes_markdown"]
    assert "private_notes_text" not in note
    # Everything else is passed through exactly as Granola sent it.
    assert note["title"] == NOTE["title"]
    assert note["attendees"] == NOTE["attendees"]
    assert note["calendar_event"] == NOTE["calendar_event"]
    assert note["folder_membership"] == NOTE["folder_membership"]


@respx.mock
async def test_a_note_with_no_markdown_keeps_the_text_it_does_have():
    """The unhappy path: dropping the twin of a field that is not there.

    `summary_markdown` is nullable and `summary_text` is not, so this is the
    shape where a projection that always dropped the text would hand back a
    note with no summary at all.
    """
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(200, json={
            **NOTE, "summary_markdown": None, "private_notes_markdown": None})
    )

    note = await granola.notes_get.ainvoke(note_id="not_1d3tmYTlCICgjy")

    assert note["summary_text"] == NOTE["summary_text"]
    assert note["private_notes_text"] == NOTE["private_notes_text"]


@respx.mock
async def test_deduplicating_the_summary_is_a_real_reduction():
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(200, json=NOTE)
    )
    note = await granola.notes_get.ainvoke(note_id="not_1d3tmYTlCICgjy")
    assert len(json.dumps(note)) < len(json.dumps(NOTE)) * 0.75


@respx.mock
async def test_an_inline_transcript_is_trimmed_the_same_way():
    route = respx.get(url__startswith=f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(200, json={**NOTE, "transcript": [MACOS_ITEM, NAMED_ITEM]})
    )
    note = await granola.notes_get.ainvoke(
        note_id="not_1d3tmYTlCICgjy", include="transcript"
    )

    # The path interpolates the note id, and `include` is the only parameter.
    assert route.calls[0].request.url.path == "/v1/notes/not_1d3tmYTlCICgjy"
    assert dict(route.calls[0].request.url.params) == {"include": "transcript"}
    assert [item["speaker"] for item in note["transcript"]] == ["me", "Alice Smith"]


@respx.mock
async def test_a_note_without_a_transcript_keeps_its_null():
    """`transcript` is null whenever `include` did not ask for it."""
    respx.get(f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(200, json=NOTE)
    )
    note = await granola.notes_get.ainvoke(note_id="not_1d3tmYTlCICgjy")
    assert note["transcript"] is None


# -----------------------------------------------------
# Audit: a four-way actor union and an open action set
# -----------------------------------------------------


AUDIT_EVENT = {
    "id": "aud_7Kq2mXbT9vRp3L",
    "object": "audit_event",
    "action": "workspace.member_added",
    "occurred_at": "2026-01-27T15:30:00.482Z",
    "collected_at": "2026-01-27T15:30:04.109733Z",
    "actor": {"object": "user", "id": "usr_3nQ8vLpZ2kR7dY", "email": "oat@granola.ai"},
    "data": {"role": "member"},
    "context": {
        "ip_address": "203.0.113.42",
        "user_agent": "Granola/7.400.0 (macOS 15.3)",
        "client_version": "7.400.0",
    },
}


@respx.mock
async def test_the_audit_query_parameter_names_are_the_ones_granola_documents():
    route = respx.get(url__startswith=f"{API}v1/audit").mock(
        return_value=httpx.Response(200, json={"events": [], "hasMore": False, "cursor": None})
    )

    await granola.audit_list.ainvoke(
        action="workspace",
        occurred_after="2026-01-27",
        occurred_before="2026-02-01T00:00:00Z",
        page_size=30,
    )

    assert dict(route.calls[0].request.url.params) == {
        "action": "workspace",
        "occurred_after": "2026-01-27",
        "occurred_before": "2026-02-01T00:00:00Z",
        "page_size": "30",
    }


def test_an_action_filter_must_be_lowercase_the_way_actions_are():
    """Granola's pattern is `^[a-z][a-z0-9_.-]*$`, and it rejects anything else."""
    llm = granola.audit_list.llm_schema()
    llm(action="workspace.member_added")
    with pytest.raises(pydantic.ValidationError):
        llm(action="Workspace.MemberAdded")


def test_the_action_field_is_an_open_set_of_strings():
    """Granola says outright that actions are added over time.

    A closed `Literal` would start rejecting valid responses the first time one
    is, which is the same reason `Speaker.source` is a `str`.
    """
    from charter.packs.granola.types import AuditEvent

    AuditEvent(action="something.granola.added.later")


@pytest.mark.parametrize(
    "actor, expected",
    [
        ({"object": "user", "id": "usr_3nQ8vLpZ2kR7dY", "email": "o@g.ai"}, "UserActor"),
        ({"object": "api_key", "id_suffix": "aB3dE7hK"}, "ApiKeyActor"),
        ({"object": "system"}, "SystemActor"),
        ({"object": "anonymous"}, "AnonymousActor"),
    ],
)
def test_every_actor_variant_resolves_to_its_own_model(actor, expected):
    """`system` and `anonymous` mean different things, so they are different models.

    One optional-everything actor model would parse all four and say nothing
    about which of them happened.
    """
    from charter.packs.granola.types import AuditEvent

    assert type(AuditEvent.model_validate({"actor": actor}).actor).__name__ == expected


@respx.mock
async def test_an_audit_page_comes_back_untrimmed():
    """The IP and the user agent are the content of an audit log, not envelope."""
    route = respx.get(url__startswith=f"{API}v1/audit").mock(
        return_value=httpx.Response(200, json={
            "events": [AUDIT_EVENT], "hasMore": False, "cursor": None})
    )
    page = await granola.audit_list.ainvoke()
    assert page["events"][0] == AUDIT_EVENT
    assert not route.calls[0].request.url.params


@respx.mock
async def test_an_audit_walk_does_not_stop_on_a_short_page():
    """Granola says a page can be shorter than page_size and still not be last.

    The declared pagination reads `hasMore`, so a short page with more to come
    keeps going. A walk that counted events would stop here and miss the rest.
    """
    pages = [
        httpx.Response(200, json={
            "events": [AUDIT_EVENT], "hasMore": True, "cursor": "page-two"}),
        httpx.Response(200, json={"events": [], "hasMore": False, "cursor": None}),
    ]
    respx.get(url__startswith=f"{API}v1/audit").mock(side_effect=pages)

    args = {"page_size": 30}
    walked = 0
    while args is not None:
        page = await granola.audit_list.ainvoke(args)
        walked += 1
        args = granola.audit_list.pagination.next_page_args(page, args)

    assert walked == 2


# -----------------------------------------------------
# Paging, failure, and the credential
# -----------------------------------------------------


@respx.mock
async def test_a_two_page_walk_advances_and_then_stops():
    pages = [
        httpx.Response(200, json={
            "notes": [{"id": "not_1d3tmYTlCICgjy"}], "hasMore": True, "cursor": "page-two"}),
        httpx.Response(200, json={
            "notes": [{"id": "not_2d3tmYTlCICgjz"}], "hasMore": False, "cursor": "stale"}),
    ]
    route = respx.get(url__startswith=f"{API}v1/notes").mock(side_effect=pages)

    args = {"page_size": 1}
    seen = []
    while args is not None:
        page = await granola.notes_list.ainvoke(args)
        seen.extend(page["notes"])
        args = granola.notes_list.pagination.next_page_args(page, args)

    assert [n["id"] for n in seen] == ["not_1d3tmYTlCICgjy", "not_2d3tmYTlCICgjz"]
    assert dict(route.calls[1].request.url.params)["cursor"] == "page-two"


def test_only_the_endpoints_that_page_say_they_do():
    """`webhook_endpoints_list` returns the whole list at once — no cursor at all."""
    paging = {t.name for t in granola.TOOLS if t.pagination is not None}
    assert paging == {
        "notes_list", "notes_transcript_get", "folders_list", "audit_list",
    }


def test_no_envelope_because_granola_answers_with_a_status_code():
    """Declared by its absence, and pinned so that adding one is a deliberate act."""
    assert all(tool.envelope is None for tool in granola.TOOLS)


@respx.mock
async def test_a_413_is_raised_rather_than_handed_to_the_model():
    """`TRANSCRIPT_TOO_LARGE` is the one status worth knowing by name here."""
    from charter import APIError

    respx.get(url__startswith=f"{API}v1/notes/not_1d3tmYTlCICgjy").mock(
        return_value=httpx.Response(413, json={"error": "TRANSCRIPT_TOO_LARGE"})
    )
    with pytest.raises(APIError) as raised:
        await granola.notes_get.ainvoke(note_id="not_1d3tmYTlCICgjy", include="transcript")
    assert raised.value.status_code == 413


@respx.mock
async def test_an_unconfigured_pack_fails_before_any_request(monkeypatch):
    monkeypatch.delenv("GRANOLA_API_KEY", raising=False)
    granola._headers._api_key = None
    route = respx.get(url__startswith=API)

    with pytest.raises(CredentialError):
        await granola.notes_list.ainvoke()
    assert not route.called
