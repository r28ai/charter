# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Google Calendar — the Events collection, and the calendars to run it against.

    from charter import StaticTokenProvider
    from charter.packs import gcalendar

    gcalendar.configure(StaticTokenProvider(access_token))
    await gcalendar.events_list.ainvoke(calendar_id="primary")

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gcalendar.response_handlers import (
    extract_calendar,
    extract_calendar_metadata,
    extract_calendars,
    extract_event,
    extract_events,
)
from charter.packs.gcalendar.types.calendar.actions import CalendarsGetRequest
from charter.packs.gcalendar.types.calendar_list.actions import (
    CalendarListGetRequest,
    CalendarListListRequest,
)
from charter.packs.gcalendar.types.event.actions import (
    EventsDeleteRequest,
    EventsGetRequest,
    EventsImportRequest,
    EventsInsertRequest,
    EventsInstancesRequest,
    EventsListRequest,
    EventsMoveRequest,
    EventsPatchRequest,
    EventsQuickAddRequest,
    EventsUpdateRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://www.googleapis.com/"
# Google list endpoints page with an opaque nextPageToken.
GOOGLE_PAGINATION = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")

QUOTA_DOC_URL = "https://developers.google.com/workspace/calendar/api/guides/quota"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
# Neither calendarList nor calendars is an events resource, and `calendar.events`
# does not reach either of them.
CALENDAR_LIST_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

_credentials = DeferredCredentialProvider("gcalendar", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_calendar = oauth_tool_factory(
    pack="gcalendar",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google's query parameters are camelCase (`maxResults`, `singleEvents`),
    # like its bodies. Without this the default snake casing sends `max_results`,
    # which Google silently ignores — the worst kind of wrong, because the call
    # succeeds and returns unfiltered results.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    # Pagination is a property of a list endpoint, not of the API: declaring it
    # on the factory labels every retrieve and write with a cursor parameter
    # they do not accept. It is declared per tool below.
)

events_insert = _calendar(
    name="events_insert",
    # `write`, so Event.i_cal_uid — marked Mode("import") — stays hidden here.
    # A custom mode narrows the view only for a tool that declares one; on a tool
    # with no mode it is inert, so hiding the field takes a mode on both sides.
    mode="write",
    args_schema=EventsInsertRequest,
    method="POST",
    url_template="calendar/v3/calendars/{calendar_id}/events",
    description="Create a calendar event; returns details of the event.",
    action_label="Saves an event to the calendar.",
    quota_cost=1,
    response_handler=extract_event,
)

events_list = _calendar(
    name="events_list",
    args_schema=EventsListRequest,
    method="GET",
    url_template="calendar/v3/calendars/{calendar_id}/events",
    description="List events matching a given search filter.",
    action_label="Reads the calendar.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_events,
)

events_delete = _calendar(
    name="events_delete",
    args_schema=EventsDeleteRequest,
    method="DELETE",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}",
    description="Delete an event from the calendar.",
    action_label="Deletes an event from the calendar.",
    quota_cost=1,
)

calendar_list_list = _calendar(
    name="calendar_list_list",
    args_schema=CalendarListListRequest,
    method="GET",
    url_template="calendar/v3/users/{user_id}/calendarList",
    description="List the calendars on the user's calendar list.",
    action_label="Reads the list of calendars.",
    scopes_override=CALENDAR_LIST_SCOPES,
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_calendars,
)


events_get = _calendar(
    name="events_get",
    args_schema=EventsGetRequest,
    method="GET",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}",
    description="Get one event by its ID.",
    action_label="Reads an event.",
    quota_cost=1,
    response_handler=extract_event,
)

events_update = _calendar(
    name="events_update",
    # `write`, so Event.i_cal_uid — marked Mode("import") — stays hidden here.
    # A custom mode narrows the view only for a tool that declares one; on a tool
    # with no mode it is inert, so hiding the field takes a mode on both sides.
    mode="write",
    args_schema=EventsUpdateRequest,
    method="PUT",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}",
    description=(
        "Replace an event in full. Every field is overwritten, so anything omitted is "
        "cleared — use events_patch to change part of an event."
    ),
    action_label="Replaces an event.",
    quota_cost=1,
    response_handler=extract_event,
)

events_patch = _calendar(
    name="events_patch",
    # `write`, so Event.i_cal_uid — marked Mode("import") — stays hidden here.
    # A custom mode narrows the view only for a tool that declares one; on a tool
    # with no mode it is inert, so hiding the field takes a mode on both sides.
    mode="write",
    args_schema=EventsPatchRequest,
    method="PATCH",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}",
    description=(
        "Change part of an event. Send only the fields being changed; the rest keep "
        "their stored values."
    ),
    action_label="Updates an event.",
    quota_cost=1,
    response_handler=extract_event,
)

events_move = _calendar(
    name="events_move",
    args_schema=EventsMoveRequest,
    method="POST",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}/move",
    description=(
        "Move an event to another calendar, changing its organizer. Only events with an "
        "eventType of default can be moved."
    ),
    action_label="Moves an event to another calendar.",
    quota_cost=1,
    response_handler=extract_event,
)

events_quick_add = _calendar(
    name="events_quick_add",
    args_schema=EventsQuickAddRequest,
    method="POST",
    url_template="calendar/v3/calendars/{calendar_id}/events/quickAdd",
    description=(
        "Create an event from a plain-text description such as "
        "'Appointment at Somewhere on June 3rd 10am-10:25am'. Google parses the time "
        "and title; use events_insert when the fields are already known."
    ),
    action_label="Saves an event to the calendar.",
    quota_cost=1,
    response_handler=extract_event,
)

events_import = _calendar(
    name="events_import",
    args_schema=EventsImportRequest,
    method="POST",
    url_template="calendar/v3/calendars/{calendar_id}/events/import",
    description=(
        "Import an event that already exists elsewhere, keeping its iCalUID so the two "
        "copies stay identifiable as the same event. Only events with an eventType of "
        "default may be imported."
    ),
    action_label="Imports an event into the calendar.",
    # Reveals Event.i_cal_uid, which every other endpoint hides.
    mode="import",
    quota_cost=1,
    response_handler=extract_event,
)

events_instances = _calendar(
    name="events_instances",
    args_schema=EventsInstancesRequest,
    method="GET",
    url_template="calendar/v3/calendars/{calendar_id}/events/{event_id}/instances",
    description=(
        "List the individual occurrences of a recurring event, each with its own event "
        "ID that can be updated or deleted on its own."
    ),
    action_label="Reads the occurrences of a recurring event.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_events,
)

calendar_list_get = _calendar(
    name="calendar_list_get",
    args_schema=CalendarListGetRequest,
    method="GET",
    url_template="calendar/v3/users/me/calendarList/{calendar_id}",
    description="Get one calendar from the user's calendar list, with their access role for it.",
    action_label="Reads a calendar list entry.",
    scopes_override=CALENDAR_LIST_SCOPES,
    quota_cost=1,
    response_handler=extract_calendar,
)

calendars_get = _calendar(
    name="calendars_get",
    args_schema=CalendarsGetRequest,
    method="GET",
    url_template="calendar/v3/calendars/{calendar_id}",
    description=(
        "Get a calendar's own metadata, including the time zone its events are read "
        "against. Use this before writing a naive dateTime rather than assuming a zone."
    ),
    action_label="Reads calendar settings.",
    scopes_override=CALENDAR_LIST_SCOPES,
    quota_cost=1,
    response_handler=extract_calendar_metadata,
)

TOOLS: list[Tool] = [
    events_get,
    events_list,
    events_instances,
    events_insert,
    events_update,
    events_patch,
    events_move,
    events_quick_add,
    events_import,
    events_delete,
    calendar_list_list,
    calendar_list_get,
    calendars_get,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "CALENDAR_LIST_SCOPES",
    "QUOTA_DOC_URL",
    "GOOGLE_PAGINATION",
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
]
