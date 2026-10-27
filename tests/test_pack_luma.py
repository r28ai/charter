"""Luma pack — drafted from Luma's OpenAPI document, then reviewed.

``scripts/openapi_to_pack.py`` wrote the draft and the review edited it, so these
tests pin both halves: that the transcription lands on the wire the way Luma
documents it, and that what the review added (the conflict rules, the two
validators, the descriptions the spec left blank) reaches the input a model
actually fills.

Luma is snake_case in the query and the body alike, reads its key from
``x-luma-api-key`` rather than ``Authorization``, and repeats a key for an array
in the query. Each of those is checked against the bytes on the wire, because a
wrong spelling of any of them is a request Luma may answer without complaint.
"""

from __future__ import annotations

import json
from typing import get_args

import httpx
import pydantic
import pytest
import respx

from charter import CredentialError
from charter.packs import luma

API = "https://public-api.luma.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("LUMA_API_KEY", raising=False)
    luma.configure(api_key="secret-luma-test-key")


# -----------------------------------------------------
# The wire
# -----------------------------------------------------


@respx.mock
async def test_the_query_parameter_names_are_the_ones_luma_documents():
    route = respx.get(url__startswith=f"{API}v1/events/guests/list").mock(
        return_value=httpx.Response(200, json={"entries": [], "has_more": False})
    )
    await luma.events_guests_list.ainvoke(
        event_id="evt-1",
        approval_status="pending_approval",
        sort_column="registered_at",
        sort_direction="desc nulls last",
        pagination_limit=50,
    )
    query = dict(route.calls[0].request.url.params)
    assert set(query) == {
        "event_id",
        "approval_status",
        "sort_column",
        "sort_direction",
        "pagination_limit",
    }
    assert query["sort_direction"] == "desc nulls last"


@respx.mock
async def test_an_array_in_the_query_repeats_its_key():
    """Luma: "Pass as repeated query params, e.g. `?platforms=luma&platforms=external`"."""
    route = respx.get(url__startswith=f"{API}v1/calendars/events/list").mock(
        return_value=httpx.Response(200, json={"entries": [], "has_more": False})
    )
    await luma.calendars_events_list.ainvoke(
        platforms=["luma", "external"], access=["manage", "view"]
    )
    params = route.calls[0].request.url.params
    assert params.get_list("platforms") == ["luma", "external"]
    assert params.get_list("access") == ["manage", "view"]


@respx.mock
async def test_a_post_body_is_snake_case_with_its_nested_objects():
    route = respx.post(f"{API}v1/events/create").mock(
        return_value=httpx.Response(200, json={"id": "evt-1"})
    )
    await luma.events_create.ainvoke(
        name="Launch night",
        start_at="2026-11-02T18:00:00.000Z",
        timezone="America/New_York",
        geo_address_json={"type": "google", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"},
        feedback_email={"enabled": True, "delay": "PT1H"},
        max_capacity=120,
    )
    assert json.loads(route.calls[0].request.content) == {
        "name": "Launch night",
        "start_at": "2026-11-02T18:00:00.000Z",
        "timezone": "America/New_York",
        "geo_address_json": {"type": "google", "place_id": "ChIJN1t_tDeuEmsRUsoyG83frY4"},
        "feedback_email": {"enabled": True, "delay": "PT1H"},
        "max_capacity": 120,
    }


@respx.mock
async def test_a_body_that_is_a_union_is_sent_as_the_member_chosen():
    """`calendars/events/add` takes one of two documents, told apart by `platform`.

    It is declared as a single `body` field, which unwraps: Luma reads the
    member's own keys at the root, not under `body`.
    """
    route = respx.post(f"{API}v1/calendars/events/add").mock(
        return_value=httpx.Response(200, json={})
    )
    await luma.calendars_events_add.ainvoke(
        body={
            "platform": "external",
            "url": "https://example.com/meetup",
            "name": "Meetup",
            "start_at": "2026-11-02T18:00:00.000Z",
            "duration_interval": "PT2H",
            "timezone": "Europe/London",
        }
    )
    assert json.loads(route.calls[0].request.content) == {
        "platform": "external",
        "url": "https://example.com/meetup",
        "name": "Meetup",
        "start_at": "2026-11-02T18:00:00.000Z",
        "duration_interval": "PT2H",
        "timezone": "Europe/London",
    }


def test_a_union_member_is_chosen_by_its_tag_not_by_its_shape():
    """A Luma submission names an `event_id`; it must not validate as an external one."""
    body = luma.calendars_events_add.llm_schema()(
        body={"platform": "luma", "event_id": "evt-1"}
    ).body
    assert type(body).__name__.startswith("CalendarsEventsAddBodyLuma")
    with pytest.raises(pydantic.ValidationError):
        luma.calendars_events_add.llm_schema()(body={"platform": "luma", "url": "https://x.y"})


@respx.mock
async def test_the_key_goes_out_bare_in_lumas_own_header():
    route = respx.get(f"{API}v1/users/get-self").mock(
        return_value=httpx.Response(200, json={"id": "usr-1"})
    )
    await luma.users_get_self.ainvoke()
    headers = route.calls[0].request.headers
    assert headers["x-luma-api-key"] == "secret-luma-test-key"
    assert "authorization" not in headers


@respx.mock
async def test_an_organization_key_chooses_its_calendar_per_call_not_per_argument():
    """`x-luma-calendar-id` is the host's to send, so it is a call header."""
    assert "calendar_id" not in luma.calendars_events_approve.llm_schema().model_fields
    route = respx.post(f"{API}v1/calendars/events/approve").mock(
        return_value=httpx.Response(200, json={})
    )
    await luma.calendars_events_approve.ainvoke(
        {"calendar_event_id": "calev-1"}, headers={"x-luma-calendar-id": "cal-1"}
    )
    assert route.calls[0].request.headers["x-luma-calendar-id"] == "cal-1"


async def test_an_unconfigured_pack_refuses_before_sending(monkeypatch):
    from charter.packs.luma import _credentials

    monkeypatch.setattr(_credentials, "_provider", None)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.route(url__startswith=API)
        with pytest.raises(CredentialError, match="LUMA_API_KEY"):
            await luma.users_get_self.ainvoke()
        assert not route.called


# Every argument some tool requires, with a value Luma would accept.
_REQUIRED = {
    "event_id": "evt-1",
    "id": "x-1",
    "slug": "aloha",
    "query": "coffee",
    "event_ticket_type_id": "ttype-1",
    "blast_id": "blast-1",
    "name": "Launch",
    "start_at": "2026-11-02T18:00:00.000Z",
    "timezone": "America/New_York",
    "guest_id": "gst-1",
    "status": "approved",
    "guests": [{"email": "ada@example.com"}],
    "email": "ada@example.com",
    "code": "SAVE10",
    "discount": {"discount_type": "percent", "percent_off": 10},
    "contacts": [{"email": "ada@example.com"}],
    "tag_id": "tag-1",
    "tag": "vip",
    "event_ids": ["evt-1"],
    "body": {"platform": "luma", "event_id": "evt-1"},
    "calendar_event_id": "calev-1",
    "type": "free",
    "content_md": "Doors at six.",
    "membership_tier_id": "tier-1",
    "user_id": "usr-1",
    "url": "https://example.com/hook",
    "event_types": ["*"],
    "cancellation_token": "token-1",
    "emails": ["ada@example.com"],
    "calendar_id": "cal-1",
}


@pytest.mark.parametrize("tool", luma.TOOLS, ids=lambda t: t.name)
@respx.mock
async def test_the_no_argument_call_sends_nothing_it_was_not_asked_to(tool):
    """Everything a schema defaults into the request shows up here.

    Luma documents defaults — `submission_mode: auto`, `send_email: true`,
    `platforms: luma` — and the generator puts none of them on a field: a
    default on the schema goes out on every call, which is a different request
    from the one Luma describes. They reach the model as a `Gloss` instead.
    """
    route = respx.route(method=tool.method, url__startswith=API).mock(
        return_value=httpx.Response(200, json={})
    )
    args = {
        name: _REQUIRED[name]
        for name, field in tool.args_schema.model_fields.items()
        if field.is_required()
    }
    await tool.ainvoke(args)

    request = route.calls[0].request
    if tool.method == "GET":
        assert dict(request.url.params) == {k: str(v) for k, v in args.items()}
        assert not request.content
    else:
        assert not request.url.params
        sent = json.loads(request.content or b"{}")
        expected = args.pop("body", {}) | args
        assert sent == expected, f"{tool.name} sends {sent}"


def test_the_list_tools_page_on_has_more_not_on_the_cursor():
    """Luma's last page may still carry `next_cursor`; `has_more` is the answer."""
    paging = [t for t in luma.TOOLS if t.pagination]
    assert len(paging) == 10
    pagination = luma.events_guests_list.pagination
    assert pagination is not None
    more = {"entries": [{}], "has_more": True, "next_cursor": "c2"}
    last = {"entries": [{}], "has_more": False, "next_cursor": "c3"}
    assert pagination.next_page_args(more, {}) == {"pagination_cursor": "c2"}
    assert pagination.next_page_args(last, {}) is None


# -----------------------------------------------------
# What the review added, checked on the model's input
# -----------------------------------------------------


@pytest.mark.parametrize("tool", [luma.events_create, luma.events_update], ids=lambda t: t.name)
def test_a_meeting_link_luma_makes_cannot_ride_beside_one_you_send(tool):
    """`create_meeting`: "Can't be combined with `meeting_url` or `geo_address_json`"."""
    llm = tool.llm_schema()
    base = (
        {"name": "x", "start_at": "2026-11-02T18:00:00.000Z", "timezone": "UTC"}
        if tool is luma.events_create
        else {"event_id": "evt-1"}
    )
    # The message spells fields as the published schema does, which is camelCase.
    with pytest.raises(pydantic.ValidationError, match="meetingUrl"):
        llm(**base, create_meeting="zoom", meeting_url="https://zoom.us/j/1")
    with pytest.raises(pydantic.ValidationError, match="geoAddressJson"):
        llm(
            **base,
            meeting_url="https://zoom.us/j/1",
            geo_address_json={"type": "manual", "address": "1 Main St"},
        )
    llm(**base, create_meeting="google-meet")


def test_one_ticket_or_several_but_not_both():
    llm = luma.events_guests_add.llm_schema()
    guests = [{"email": "ada@example.com"}]
    with pytest.raises(pydantic.ValidationError, match="tickets"):
        llm(
            event_id="evt-1",
            guests=guests,
            ticket={"event_ticket_type_id": "ttype-1"},
            tickets=[{"event_ticket_type_id": "ttype-2"}],
        )
    llm(event_id="evt-1", guests=guests, tickets=[{"event_ticket_type_id": "ttype-2"}])


def test_a_status_message_needs_the_status_email():
    llm = luma.events_guests_update_status.llm_schema()
    base = {"event_id": "evt-1", "guest_id": "gst-1", "status": "declined"}
    with pytest.raises(pydantic.ValidationError, match="send_email"):
        llm(**base, message="Sorry, we are full.", send_email=False)
    llm(**base, message="Sorry, we are full.")
    llm(**base, send_email=False)


def test_a_blast_to_invitees_cannot_be_narrowed_by_ticket_type():
    """The rule sits on a nested model, so it must survive into the nested LLM view."""
    llm = luma.events_blasts_create.llm_schema()
    base = {"event_id": "evt-1", "content_md": "Doors at six."}
    with pytest.raises(pydantic.ValidationError, match="invitees"):
        llm(**base, recipient_groups=[{"status": "invited", "event_ticket_type_id": "ttype-1"}])
    llm(**base, recipient_groups=[{"status": "approved", "event_ticket_type_id": "ttype-1"}])


def test_deprecated_fields_are_withheld_from_the_model():
    assert "suppress_notifications" not in luma.events_update.llm_schema().model_fields
    assert "suppress_email" in luma.events_update.llm_schema().model_fields
    assert "event_api_id" not in luma.calendars_events_lookup.llm_schema().model_fields


def test_a_documented_default_is_said_rather_than_sent():
    """`submission_mode` defaults to `auto`; the model is told so in a Gloss."""
    schema = json.dumps(luma.calendars_events_add.to_json_schema())
    assert "Defaults to `auto` when omitted." in schema


def test_an_update_requires_only_what_names_the_thing_updated():
    required = [
        name
        for name, field in luma.events_update.llm_schema().model_fields.items()
        if field.is_required()
    ]
    assert required == ["event_id"]


def test_a_cover_image_must_already_be_on_lumas_cdn():
    """`cover_url` carries Luma's pattern, so a stray URL fails before the request."""
    llm = luma.events_update.llm_schema()
    with pytest.raises(pydantic.ValidationError):
        llm(event_id="evt-1", cover_url="https://example.com/cover.png")
    llm(event_id="evt-1", cover_url="https://images.lumacdn.com/covers/x.png")


# -----------------------------------------------------
# The enums, against Luma's values rather than their own
# -----------------------------------------------------


def test_the_closed_sets_hold_every_value_luma_lists():
    from charter.packs.luma.types import Currency, EventType, Font, SortDirection, Theme

    # 67 on 2026-10-27, two more than the day before: Luma adds themes, and a
    # regeneration that moves this number is that, to be read and re-pinned.
    assert len(get_args(Theme)) == 67
    assert {"standard", "zigzag", "banknote-dark"} <= set(get_args(Theme))
    assert len(get_args(Font)) == 25
    assert {"usd", "eur", "solana_usdc"} <= set(get_args(Currency))
    assert set(get_args(SortDirection)) == {"asc", "desc", "asc nulls last", "desc nulls last"}
    assert set(get_args(EventType)) == {
        "*",
        "calendar.event.added",
        "calendar.event.submitted",
        "calendar.person.subscribed",
        "calendar.person.unsubscribed",
        "event.canceled",
        "event.created",
        "event.updated",
        "guest.registered",
        "guest.refunded",
        "guest.updated",
        "ticket.registered",
    }


def test_every_kind_of_registration_question_is_offered():
    """Thirteen kinds in the spec; a union that dropped one could not create it."""
    from charter.packs.luma.types import RegistrationQuestion

    kinds = {
        member.model_fields["question_type"].annotation.__args__[0]
        for member in get_args(RegistrationQuestion)
    }
    assert kinds == {
        "agree-check",
        "company",
        "github",
        "instagram",
        "linkedin",
        "phone-number",
        "select",
        "telegram",
        "terms",
        "text",
        "twitter",
        "url",
        "youtube",
    }


async def test_each_user_s_call_carries_that_user_s_key(monkeypatch):
    """One key per process would make every user act as whoever configured the pack."""
    from charter.auth import StaticTokenProvider, SubjectProvider, use_subject

    keys = {"ada": "key-for-ada", "grace": "key-for-grace"}
    luma.configure(credential_provider=SubjectProvider(lambda s: StaticTokenProvider(keys[s])))
    with respx.mock:
        route = respx.get(f"{API}v1/users/get-self").mock(return_value=httpx.Response(200, json={}))
        for subject in ("ada", "grace", "ada"):
            with use_subject(subject):
                await luma.users_get_self.ainvoke()
        sent = [call.request.headers["x-luma-api-key"] for call in route.calls]
    assert sent == ["key-for-ada", "key-for-grace", "key-for-ada"]
