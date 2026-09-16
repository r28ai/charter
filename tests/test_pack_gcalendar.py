"""Google Calendar pack — wire behaviour and response trimming.

The trimming tests carry a floor, not just a shape assertion. This pack shipped
without response handlers and returned 18% less than the API gave it, against
60-97% for the packs that had them; a scenario run put 176KB of calendar into a
model's context in one call. A ratio that silently regresses is the defect, so
it is asserted.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from charter import Tool
from charter.auth import StaticTokenProvider
from charter.packs import gcalendar

API = "https://www.googleapis.com/"
EVENTS = f"{API}calendar/v3/calendars/primary/events"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gcalendar.configure(StaticTokenProvider("ya29.test"))


def event(**overrides):
    """One event in the shape Calendar actually returns."""
    base = {
        "kind": "calendar#event",
        "etag": '"3577638930493150"',
        "id": "nu0mcl77vq3pf7e31cvq9g9qes",
        "status": "confirmed",
        "htmlLink": "https://www.google.com/calendar/event?eid=" + "b" * 60,
        "created": "2026-09-07T22:17:45.000Z",
        "updated": "2026-09-07T22:17:45.246Z",
        "summary": "Budget sync",
        "creator": {"email": "someone@example.com", "self": True},
        "organizer": {"email": "someone@example.com", "self": True},
        "start": {"dateTime": "2026-09-14T12:00:00Z", "timeZone": "Europe/Paris"},
        "end": {"dateTime": "2026-09-14T12:30:00Z", "timeZone": "Europe/Paris"},
        "iCalUID": "nu0mcl77vq3pf7e31cvq9g9qes@google.com",
        "sequence": 0,
        "reminders": {"useDefault": True},
        "eventType": "default",
    }
    base.update(overrides)
    return base


def events_payload(n, **top):
    payload = {
        "kind": "calendar#events",
        "etag": '"p32of'.ljust(20, "x") + '"',
        "summary": "someone@example.com",
        "updated": "2026-09-07T22:17:45.000Z",
        "timeZone": "Europe/Paris",
        "accessRole": "owner",
        "defaultReminders": [{"method": "popup", "minutes": 30}],
        "items": [event(id=f"evt{i}") for i in range(n)],
    }
    payload.update(top)
    return payload


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_every_documented_endpoint():
    """Named against the API's own method list rather than counted.

    A count passes the day someone adds a tool and forgets one; this fails until
    the pack covers what the v3 Events, CalendarList and Calendars references
    document. `events_watch` is deliberately absent — it registers a push
    notification channel, which needs a public HTTPS endpoint Charter has no
    business assuming.
    """
    assert {t.name for t in gcalendar.TOOLS} == {
        "events_get",
        "events_list",
        "events_instances",
        "events_insert",
        "events_update",
        "events_patch",
        "events_move",
        "events_quick_add",
        "events_import",
        "events_delete",
        "calendar_list_list",
        "calendar_list_get",
        "calendars_get",
    }
    assert all(isinstance(t, Tool) for t in gcalendar.TOOLS)


def test_every_tool_with_something_to_trim_has_a_handler():
    """A read without a handler is how this pack leaked 176KB into a context.

    ``events_delete`` is the only tool absent, because it returns an empty body.
    Asserted as "everything but", so a tool added later is covered by default
    rather than by whoever remembers to extend a list.
    """
    trimming = {t.name for t in gcalendar.TOOLS if t._executor._response_handler}
    assert trimming == {t.name for t in gcalendar.TOOLS} - {"events_delete"}


# -----------------------------------------------------
# Trimming
# -----------------------------------------------------


@respx.mock
async def test_list_trimming_keeps_what_an_agent_acts_on():
    respx.get(EVENTS).mock(return_value=httpx.Response(200, json=events_payload(1)))

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    item = result["items"][0]

    assert item["id"] == "evt0"
    assert item["summary"] == "Budget sync"
    assert item["start"] == {"dateTime": "2026-09-14T12:00:00Z", "timeZone": "Europe/Paris"}
    assert item["end"]["dateTime"] == "2026-09-14T12:30:00Z"

    # provenance an agent cannot act on is gone
    for dropped in ("htmlLink", "iCalUID", "etag", "kind", "created", "updated",
                    "sequence", "reminders", "eventType", "creator"):
        assert dropped not in item, dropped

    # a self-organised event does not spend bytes naming the organiser
    assert "organizer" not in item
    # "confirmed" is the default; its absence carries the same information
    assert "status" not in item


@respx.mock
async def test_the_signals_that_are_only_sometimes_present_survive():
    rich = event(
        status="cancelled",
        description="Bring the Q4 deck",
        location="Room 4",
        recurringEventId="abc123",
        organizer={"email": "sam@example.com", "self": False},
        attendees=[{"email": "sam@example.com", "responseStatus": "accepted",
                    "displayName": "Sam", "id": "x" * 40}],
    )
    respx.get(EVENTS).mock(return_value=httpx.Response(200, json=events_payload(0, items=[rich])))

    item = (await gcalendar.events_list.ainvoke(calendar_id="primary"))["items"][0]

    assert item["status"] == "cancelled"
    assert item["description"] == "Bring the Q4 deck"
    assert item["location"] == "Room 4"
    assert item["recurringEventId"] == "abc123"
    assert item["organizer"] == "sam@example.com"
    assert item["attendees"] == [{"email": "sam@example.com", "responseStatus": "accepted"}]


@respx.mock
async def test_all_day_events_keep_their_date():
    all_day = event(start={"date": "2026-09-14"}, end={"date": "2026-09-15"})
    respx.get(EVENTS).mock(return_value=httpx.Response(200, json=events_payload(0, items=[all_day])))

    item = (await gcalendar.events_list.ainvoke(calendar_id="primary"))["items"][0]
    assert item["start"] == {"date": "2026-09-14"}
    assert item["end"] == {"date": "2026-09-15"}


@respx.mock
async def test_paging_survives_trimming():
    payload = events_payload(2, nextPageToken="CAcSB2V2ZW50Mg")
    respx.get(EVENTS).mock(return_value=httpx.Response(200, json=payload))

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    assert result["nextPageToken"] == "CAcSB2V2ZW50Mg"
    # the calendar's default zone disambiguates a naive dateTime in an item
    assert result["timeZone"] == "Europe/Paris"


@respx.mock
async def test_trimming_is_a_large_reduction():
    """Context economy is the point; a regression here is the defect."""
    payload = events_payload(60)
    respx.get(EVENTS).mock(return_value=httpx.Response(200, json=payload))

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    before, after = len(json.dumps(payload)), len(json.dumps(result))

    assert len(result["items"]) == 60
    assert after < before * 0.4, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_insert_returns_a_trimmed_event_that_keeps_its_id():
    """The id is what the caller needs next; trimming must not take it."""
    respx.post(EVENTS).mock(return_value=httpx.Response(200, json=event()))

    result = await gcalendar.events_insert.ainvoke(
        calendar_id="primary",
        event={"summary": "Budget sync",
               "start": {"dateTime": "2026-09-14T12:00:00Z"},
               "end": {"dateTime": "2026-09-14T12:30:00Z"}},
    )
    assert result["id"] == "nu0mcl77vq3pf7e31cvq9g9qes"
    assert result["summary"] == "Budget sync"
    assert "htmlLink" not in result


@respx.mock
async def test_calendar_list_trimming_keeps_the_primary_flag():
    payload = {
        "kind": "calendar#calendarList",
        "etag": '"x"',
        "items": [
            {"kind": "calendar#calendarListEntry", "etag": '"y"', "id": "primary-id",
             "summary": "someone@example.com", "timeZone": "Europe/Paris",
             "colorId": "14", "backgroundColor": "#9fe1e7", "foregroundColor": "#000000",
             "selected": True, "accessRole": "owner", "primary": True,
             "conferenceProperties": {"allowedConferenceSolutionTypes": ["hangoutsMeet"]}},
        ],
    }
    respx.get(f"{API}calendar/v3/users/me/calendarList").mock(
        return_value=httpx.Response(200, json=payload)
    )

    item = (await gcalendar.calendar_list_list.ainvoke(user_id="me"))["items"][0]
    assert item == {
        "id": "primary-id",
        "summary": "someone@example.com",
        "primary": True,
        "selected": True,
        "accessRole": "owner",
        "timeZone": "Europe/Paris",
    }


# -----------------------------------------------------
# dateTime and timeZone must agree
# -----------------------------------------------------
#
# These two fields can contradict each other, and when they do the API does not
# say so: for a single event it uses the offset and ignores timeZone. A model
# given both fills in both, because the API's own description of dateTime says
# an offset is required "unless a time zone is explicitly specified in timeZone",
# which reads as an invitation to supply the pair.
#
# Measured over 110 harness runs this was the largest single source of wrong
# answers on the calendar scenarios: the Charter arm scored 3/7 on
# sheet_to_calendar sending `2026-09-14T08:45:00Z` with timeZone Europe/Paris,
# while the arm with no schema at all scored 7/7 — it never saw two fields to
# fill. The schema made the model worse than no schema, so the schema closes it.


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(dict(date_time="2026-09-14T08:45:00+02:00", time_zone="Europe/Paris"), id="offset agrees"),
        pytest.param(dict(date_time="2026-09-14T08:45:00", time_zone="Europe/Paris"), id="naive time plus its zone"),
        pytest.param(dict(date_time="2026-09-14T08:45:00Z"), id="offset with no zone"),
        pytest.param(dict(date_time="2026-09-14T08:45:00Z", time_zone="Not/AZone"), id="zone we cannot resolve"),
        pytest.param(dict(date="2026-09-14", time_zone="Europe/Paris"), id="all-day"),
    ],
)
def test_a_time_that_does_not_contradict_itself_is_accepted(payload):
    from charter.packs.gcalendar.types.event.models import EventDateTime

    assert EventDateTime.model_validate(payload)


@pytest.mark.parametrize(
    "when,zone,lands,correction",
    [
        ("2026-09-14T08:45:00Z", "Europe/Paris", "10:45", "+02:00"),
        ("2026-01-14T08:45:00Z", "Europe/Paris", "09:45", "+01:00"),
        ("2026-09-14T12:00:00+05:00", "America/New_York", "03:00", "-04:00"),
    ],
)
def test_an_offset_that_contradicts_the_zone_is_refused(when, zone, lands, correction):
    """The message is written for a model: it names where the event would land
    and the exact string that would put it where the caller meant. The winter
    case is not a duplicate — it pins that the comparison is against the zone's
    offset *at that instant*, not a fixed one, so DST cannot make it wrong."""
    import pydantic

    from charter.packs.gcalendar.types.event.models import EventDateTime

    with pytest.raises(pydantic.ValidationError) as exc:
        EventDateTime.model_validate(dict(date_time=when, time_zone=zone))

    message = str(exc.value)
    assert zone in message
    assert f"land at {lands} {zone}" in message
    assert correction in message


@respx.mock
async def test_the_contradiction_never_reaches_the_api():
    """It is refused before a request goes out, so the wrong event is not
    created and then found later — which is how it read back as deliberate."""
    from charter.types.errors import ToolValidationError

    route = respx.post(EVENTS).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    with pytest.raises(ToolValidationError) as exc:
        await gcalendar.events_insert.ainvoke(
            {
                "calendarId": "primary",
                "event": {
                    "summary": "Standup",
                    "start": {"dateTime": "2026-09-14T08:45:00Z", "timeZone": "Europe/Paris"},
                    "end": {"dateTime": "2026-09-14T09:00:00Z", "timeZone": "Europe/Paris"},
                },
            }
        )
    assert not route.called
    assert "Europe/Paris" in str(exc.value)


def test_the_message_closes_the_escape_that_does_not_work():
    """Offered two ways out, a model took the third: it dropped `timeZone` and
    kept `Z`. That is legal and non-contradictory, so nothing can refuse it a
    second time — and it still creates the event at the wrong instant. Measured:
    one run corrected three events and left a fourth at 09:00Z, producing a
    duplicate. An error that leaves a plausible wrong move available gets taken.
    """
    import pydantic

    from charter.packs.gcalendar.types.event.models import EventDateTime

    with pytest.raises(pydantic.ValidationError) as exc:
        EventDateTime.model_validate(
            dict(date_time="2026-09-14T09:00:00Z", time_zone="Europe/Paris")
        )
    message = str(exc.value)
    assert "send dateTime 2026-09-14T09:00:00+02:00" in message
    assert "Do not fix this by removing timeZone" in message
    assert "still creates the event at 11:00 Europe/Paris" in message


# -----------------------------------------------------
# The rules the documentation states across parameters
# -----------------------------------------------------
#
# Each of these is a 400 the model would otherwise have to interpret from the
# outside. They are asserted against `llm_schema()` — the input that actually
# needs checking — because a rule enforced only on the wire schema never sees
# what the model sent.


def _camel(field: str) -> str:
    head, *rest = field.split("_")
    return head + "".join(p.capitalize() for p in rest)


def _list_schema(**kwargs):
    return gcalendar.events_list.llm_schema().model_validate(
        {"calendarId": "primary", **kwargs}
    )


def test_a_sync_token_may_not_be_narrowed():
    """An incremental sync continues the query its token came from."""
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="cannot be combined with syncToken"):
        _list_schema(syncToken="tok", q="standup")

    # Every conflict at once, not one per round trip.
    with pytest.raises(pydantic.ValidationError) as exc:
        _list_schema(syncToken="tok", orderBy="updated", timeMin="2026-09-14T00:00:00Z")
    assert "orderBy" in str(exc.value) and "timeMin" in str(exc.value)


def test_a_sync_token_may_not_hide_deletions():
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="showDeleted cannot be False"):
        _list_schema(syncToken="tok", showDeleted=False)
    assert _list_schema(syncToken="tok", showDeleted=True)


def test_ordering_by_start_time_requires_single_events():
    """A recurring event has no single start time to order by."""
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="only available when singleEvents"):
        _list_schema(orderBy="startTime")
    assert _list_schema(orderBy="startTime", singleEvents=True)
    assert _list_schema(orderBy="updated")


def test_the_time_window_must_be_able_to_match_something():
    import pydantic

    with pytest.raises(pydantic.ValidationError, match="must be smaller than timeMax"):
        _list_schema(timeMin="2026-09-14T18:00:00Z", timeMax="2026-09-14T09:00:00Z")
    assert _list_schema(timeMin="2026-09-14T09:00:00Z", timeMax="2026-09-14T18:00:00Z")


def test_importing_without_an_ical_uid_is_refused():
    """`iCalUID` is required by import and by no other endpoint, so the rule sits
    on the operation rather than on the Event resource — `events_insert`
    documents id and iCalUID as alternatives."""
    import pydantic

    event = {
        "summary": "Kickoff",
        "start": {"dateTime": "2026-09-14T09:00:00+02:00"},
        "end": {"dateTime": "2026-09-14T09:45:00+02:00"},
    }
    schema = gcalendar.events_import.llm_schema()
    with pytest.raises(pydantic.ValidationError, match="iCalUID is required"):
        schema.model_validate({"calendarId": "primary", "event": event})
    assert schema.model_validate(
        {"calendarId": "primary", "event": {**event, "iCalUID": "abc@example.com"}}
    )
    # The same event inserts without one.
    assert gcalendar.events_insert.llm_schema().model_validate(
        {"calendarId": "primary", "event": event}
    )


# -----------------------------------------------------
# The new endpoints, on the wire
# -----------------------------------------------------


@respx.mock
async def test_quick_add_sends_its_text_as_a_query_parameter():
    route = respx.post(f"{EVENTS}/quickAdd").mock(
        return_value=httpx.Response(200, json={"id": "e1", "summary": "Lunch"})
    )
    await gcalendar.events_quick_add.ainvoke(
        {"calendarId": "primary", "text": "Lunch tomorrow 1pm", "sendUpdates": "none"}
    )
    request = route.calls[0].request
    assert request.url.params["text"] == "Lunch tomorrow 1pm"
    assert request.url.params["sendUpdates"] == "none"
    assert not request.content, "quickAdd takes no body"


@respx.mock
async def test_move_sends_the_destination_as_a_query_parameter():
    route = respx.post(f"{EVENTS}/evt1/move").mock(
        return_value=httpx.Response(200, json={"id": "evt1"})
    )
    await gcalendar.events_move.ainvoke(
        {"calendarId": "primary", "eventId": "evt1", "destination": "team@example.com"}
    )
    assert route.calls[0].request.url.params["destination"] == "team@example.com"


@respx.mock
async def test_patch_sends_only_what_it_was_given():
    """The point of PATCH: no read-then-echo just to keep the other fields."""
    route = respx.patch(f"{EVENTS}/evt1").mock(
        return_value=httpx.Response(200, json={"id": "evt1"})
    )
    await gcalendar.events_patch.ainvoke(
        {"calendarId": "primary", "eventId": "evt1", "event": {"summary": "Renamed"}}
    )
    assert json.loads(route.calls[0].request.content) == {"summary": "Renamed"}


@respx.mock
async def test_a_patch_body_mandates_nothing_while_the_put_beside_it_does():
    body = gcalendar.events_patch.llm_schema().model_fields["event"].annotation
    assert [n for n, f in body.model_fields.items() if f.is_required()] == []

    put_body = gcalendar.events_update.llm_schema().model_fields["event"].annotation
    assert sorted(n for n, f in put_body.model_fields.items() if f.is_required()) == ["end", "start"]


@respx.mock
async def test_calendars_get_reads_the_zone_events_are_written_against():
    respx.get("https://www.googleapis.com/calendar/v3/calendars/primary").mock(
        return_value=httpx.Response(
            200,
            json={
                "kind": "calendar#calendar",
                "etag": '"abc"',
                "id": "primary",
                "summary": "Nathan",
                "timeZone": "Europe/Paris",
            },
        )
    )
    result = await gcalendar.calendars_get.ainvoke(calendar_id="primary")
    assert result == {"id": "primary", "summary": "Nathan", "timeZone": "Europe/Paris"}
    assert "etag" not in result and "kind" not in result


# -----------------------------------------------------
# Deprecated parameters are not offered
# -----------------------------------------------------


def test_the_parameters_google_ignores_are_hidden_from_the_model():
    """`sendNotifications` and `alwaysIncludeEmail` are documented as deprecated
    and ignored. A parameter the API will not act on is a turn the model can
    waste composing it."""
    for tool in gcalendar.TOOLS:
        offered = set(tool.to_json_schema()["parameters"].get("properties") or {})
        assert "sendNotifications" not in offered, tool.name
        assert "alwaysIncludeEmail" not in offered, tool.name

    # Still reachable from Python, where the caller can read the deprecation.
    from charter.packs.gcalendar.types.event.actions import EventsGetRequest

    assert "always_include_email" in EventsGetRequest.model_fields


@respx.mock
async def test_ical_uid_reaches_the_wire_under_the_name_google_documents():
    """It reached it as `iCalUid` for as long as this pack has existed.

    Google ignores query parameters it does not recognise, so `events_list`
    filtering by iCalUID matched nothing, returned the whole unfiltered list, and
    answered 200 every time. The same misspelling made `events_import` unable to
    send the one field that endpoint mandates. `WireName` is what corrects it;
    asserted on the bytes, because reading the schema is what missed it.
    """
    listed = respx.get(url__regex=r".*/events\?.*").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    await gcalendar.events_list.ainvoke(
        {"calendarId": "primary", "iCalUID": "abc@example.com"}
    )
    assert listed.calls[0].request.url.params["iCalUID"] == "abc@example.com"

    imported = respx.post(f"{EVENTS}/import").mock(
        return_value=httpx.Response(200, json={"id": "e1"})
    )
    await gcalendar.events_import.ainvoke(
        {
            "calendarId": "primary",
            "event": {
                "iCalUID": "abc@example.com",
                "start": {"dateTime": "2026-09-14T09:00:00+02:00"},
                "end": {"dateTime": "2026-09-14T09:45:00+02:00"},
            },
        }
    )
    assert json.loads(imported.calls[0].request.content)["iCalUID"] == "abc@example.com"


def test_only_import_offers_ical_uid():
    """Requiredness and visibility are different axes. `events_insert` documents
    id and iCalUID as alternatives, so offering both there invites sending both;
    `events_import` mandates it. A custom Mode makes visibility follow the
    operation rather than the resource."""
    def body_fields(tool):
        return set(tool.llm_schema().model_fields["event"].annotation.model_fields)

    assert "i_cal_uid" in body_fields(gcalendar.events_import)
    for tool in (gcalendar.events_insert, gcalendar.events_update, gcalendar.events_patch):
        assert "i_cal_uid" not in body_fields(tool), tool.name


def test_access_role_holds_the_whole_documented_enum():
    """A closed Literal narrower than the API's enum rejects a valid call, and
    the model cannot tell that from the API refusing it. This one was missing
    `writerWithoutPrivateAccess` while its own description listed it."""
    import typing

    from charter.packs.gcalendar.types.calendar_list.models import AccessRole

    assert set(typing.get_args(AccessRole)) == {
        "freeBusyReader",
        "owner",
        "reader",
        "writer",
        "writerWithoutPrivateAccess",
    }
    described = gcalendar.calendar_list_list.to_json_schema()["parameters"]["properties"][
        "minAccessRole"
    ]["description"]
    for value in typing.get_args(AccessRole):
        assert value in described, f"{value} is accepted but not described"


@respx.mock
async def test_the_sync_token_message_names_what_the_request_would_send():
    """The rule and the wire name must not be maintained twice.

    Written out as pairs, `("i_cal_uid", "iCalUID")` restated what the field's
    own `WireName` declares, so changing one would leave the error naming a
    parameter that is no longer sent. This asserts the two agree by sending each
    excluded field and reading the parameter name off the wire.
    """
    from charter.types import ConflictsWith

    schema = gcalendar.events_list.llm_schema()
    excluded = {
        name
        for name, f in schema.model_fields.items()
        if any(isinstance(m, ConflictsWith) for m in f.metadata)
    }
    values = {
        "i_cal_uid": "a@b",
        "order_by": "updated",
        "private_extended_property": ["k=v"],
        "q": "standup",
        "shared_extended_property": ["k=v"],
        "time_min": "2026-09-14T00:00:00Z",
        "time_max": "2026-09-15T00:00:00Z",
        "updated_min": "2026-09-14T00:00:00Z",
    }
    assert set(values) == excluded, "a field declared ConflictsWith without a case here"

    route = respx.get(url__regex=r".*/events\?.*").mock(
        return_value=httpx.Response(200, json={"items": []})
    )
    for field, value in values.items():
        published = schema.model_fields[field].alias or _camel(field)
        await gcalendar.events_list.ainvoke({"calendarId": "primary", published: value})
        sent = set(route.calls[-1].request.url.params)

        # The name the message would use, derived the way the synthesised check
        # derives it, must be the name the request actually sends.
        with pytest.raises(Exception) as exc:
            schema.model_validate({"calendarId": "primary", "syncToken": "t", published: value})
        named = str(exc.value)
        assert any(p in named for p in sent - {"calendarId"}), (
            f"the message names none of {sent - {'calendarId'}}"
        )


# -----------------------------------------------------
# calendarList.list states the same rule about syncToken
# -----------------------------------------------------
#
# It had no test before or after being rewritten to use ConflictsWith — removing
# the marker left the suite green, which is how the missing
# `showOwnOrganizationOnly` parameter survived in the first place: the validator
# named it, the schema had no such field, and nothing exercised either.


def _calendar_list_schema(**kwargs):
    return gcalendar.calendar_list_list.llm_schema().model_validate(kwargs)


def test_a_calendar_list_sync_token_may_not_be_narrowed():
    import pydantic

    with pytest.raises(pydantic.ValidationError) as exc:
        _calendar_list_schema(syncToken="t", minAccessRole="reader")
    assert "minAccessRole cannot be combined with syncToken" in str(exc.value)

    with pytest.raises(pydantic.ValidationError) as exc:
        _calendar_list_schema(syncToken="t", showOwnOrganizationOnly=True)
    assert "showOwnOrganizationOnly cannot be combined with syncToken" in str(exc.value)

    assert _calendar_list_schema(syncToken="t")
    assert _calendar_list_schema(minAccessRole="reader")


def test_a_calendar_list_sync_token_may_not_hide_what_it_reports():
    import pydantic

    for flag in ("showDeleted", "showHidden"):
        with pytest.raises(pydantic.ValidationError, match="cannot be False alongside syncToken"):
            _calendar_list_schema(syncToken="t", **{flag: False})
        assert _calendar_list_schema(syncToken="t", **{flag: True})


def test_the_rule_covers_every_parameter_the_documentation_names():
    """Four parameters, and `showOwnOrganizationOnly` was missing from the schema
    entirely while the validator claimed to guard it."""
    from charter.types import ConflictsWith

    fields = gcalendar.calendar_list_list.llm_schema().model_fields
    declared = {
        name for name, f in fields.items()
        if any(isinstance(m, ConflictsWith) for m in f.metadata)
    }
    assert declared == {"min_access_role", "show_own_organization_only"}
    assert {"show_deleted", "show_hidden", "sync_token"} <= set(fields)


# -----------------------------------------------------
# The description cap — the pack's largest measured payload
# -----------------------------------------------------


def _meet_boilerplate() -> str:
    """The conferencing block a calendar client pastes into `description`."""
    return (
        "<br><br>-::~:~::~:~:~::~:~::~::~:~::-<br>Join with Google Meet: "
        "<a href=\"https://meet.google.com/abc-defg-hij\">meet.google.com/abc-defg-hij"
        "</a><br>Or dial: (US) +1 555-555-5555 PIN: 123456789#<br>More phone numbers: "
        "<a href=\"https://tel.meet/abc-defg-hij?pin=1234567890123\">https://tel.meet/"
        "abc-defg-hij?pin=1234567890123</a><br><br>Learn more about Meet at: "
        "<a href=\"https://support.google.com/a/users/answer/9282720\">"
        "https://support.google.com/a/users/answer/9282720</a><br><br>"
        "Please do not edit this section.<br>-::~:~::~:~:~::~:~::~::~:~::-<br>"
    )


def _event_with_long_description(i: int) -> dict:
    return {
        "id": f"evt{i}",
        "status": "confirmed",
        "summary": "Weekly sync",
        "description": "Agenda: ship the thing." + _meet_boilerplate(),
        "hangoutLink": "https://meet.google.com/abc-defg-hij",
        "start": {"dateTime": f"2026-09-1{i}T10:00:00+01:00", "timeZone": "Europe/London"},
        "end": {"dateTime": f"2026-09-1{i}T10:30:00+01:00", "timeZone": "Europe/London"},
        "iCalUID": f"evt{i}@google.com",
        "etag": '"3456789012345678"',
        "htmlLink": f"https://www.google.com/calendar/event?eid={i}",
        "created": "2026-01-01T00:00:00.000Z",
        "updated": "2026-09-01T00:00:00.000Z",
        "creator": {"email": "ada@example.com", "self": True},
        "organizer": {"email": "ada@example.com", "self": True},
        "sequence": 0,
        "reminders": {"useDefault": True},
        "eventType": "default",
    }


@respx.mock
async def test_the_list_caps_the_description_and_says_so():
    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(
            200, json={"items": [_event_with_long_description(1)], "timeZone": "Europe/London"}
        )
    )

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    event = result["items"][0]

    assert event["description_truncated"] is True
    assert event["description"].startswith("Agenda: ship the thing.")
    assert "events_get" in event["description"]
    assert len(event["description"]) < 400


@respx.mock
async def test_the_join_link_survives_the_cap():
    """The one actionable thing inside the conferencing block is read out as a
    field, so capping the prose cannot lose it."""
    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(
            200, json={"items": [_event_with_long_description(1)]}
        )
    )
    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    assert result["items"][0]["conferenceUrl"] == "https://meet.google.com/abc-defg-hij"


@respx.mock
async def test_a_non_meet_conference_is_read_out_of_entry_points():
    event = _event_with_long_description(1)
    del event["hangoutLink"]
    event["conferenceData"] = {
        "conferenceId": "zoom-1",
        "conferenceSolution": {"name": "Zoom Meeting"},
        "entryPoints": [
            {"entryPointType": "phone", "uri": "tel:+15555555555", "label": "+1 555"},
            {"entryPointType": "video", "uri": "https://zoom.us/j/123", "label": "zoom.us"},
        ],
    }
    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": [event]})
    )
    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    assert result["items"][0]["conferenceUrl"] == "https://zoom.us/j/123"


@respx.mock
async def test_a_short_description_is_not_touched():
    event = _event_with_long_description(1)
    event["description"] = "Bring the roadmap."
    event.pop("hangoutLink")
    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": [event]})
    )
    result = await gcalendar.events_list.ainvoke(calendar_id="primary")
    assert result["items"][0]["description"] == "Bring the roadmap."
    assert "description_truncated" not in result["items"][0]


@respx.mock
async def test_events_get_keeps_the_description_whole():
    """The list caps; the single-event call is the escape hatch, and the id it
    needs was in the capped item."""
    event = _event_with_long_description(1)
    respx.get(f"{API}calendar/v3/calendars/primary/events/evt1").mock(
        return_value=httpx.Response(200, json=event)
    )

    result = await gcalendar.events_get.ainvoke(calendar_id="primary", event_id="evt1")

    assert result["description"] == event["description"]
    assert "description_truncated" not in result


@respx.mock
async def test_a_page_of_conferencing_events_is_a_large_reduction():
    raw = {
        "kind": "calendar#events",
        "etag": '"p32ofplf5o8bfe0g"',
        "summary": "ada@example.com",
        "updated": "2026-09-13T00:00:00.000Z",
        "timeZone": "Europe/London",
        "accessRole": "owner",
        "defaultReminders": [{"method": "popup", "minutes": 10}],
        "items": [_event_with_long_description(i) for i in range(20)],
    }
    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json=raw)
    )

    result = await gcalendar.events_list.ainvoke(calendar_id="primary")

    # This page is 25KB, which is the measured average for this endpoint, and
    # it trims 45% where it used to trim 18%. The floor is set below what is
    # achieved rather than at it: the rest of what survives is the event, and a
    # cap tuned down to make this number rounder would start removing agendas.
    assert len(json.dumps(result)) < len(json.dumps(raw)) * 0.6


@respx.mock
async def test_the_cap_pays_most_on_the_payload_that_caused_it():
    """The average page is 23KB; one measured call reached 176KB. The cap is a
    fixed cost per event, so the worse the payload the more it takes off."""
    fat = _event_with_long_description(1)
    # A description with a pasted agenda, a thread of notes and the conferencing
    # block — the shape behind the outlier.
    fat["description"] = ("Notes from last week. " * 200) + _meet_boilerplate()
    raw = {"items": [dict(fat, id=f"evt{i}") for i in range(20)]}

    respx.get(f"{API}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json=raw)
    )
    result = await gcalendar.events_list.ainvoke(calendar_id="primary")

    # 88% here against 45% on an average page, and above the 79% median the
    # rest of the catalog trims at.
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 8
    # And the agent is told the text was cut, with the call that recovers it.
    assert result["items"][0]["description_truncated"] is True
