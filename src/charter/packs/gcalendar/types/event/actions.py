# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the Events collection.

API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events

Descriptions are the API's own words rather than a summary of them: they are the
only guide the model has, and paraphrasing them is how a pack drifts from the
documentation it was written against. Where several endpoints share a parameter,
the text lives in one constant below and is applied at each use, so a rewording
by the vendor is one edit rather than nine.
"""

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.execution.schema import partial_of
from charter.types import Body, ConflictsWith, Mode, Path, Query, WireName

from .._shared import CALENDAR_ID
from .models import Event

# ──────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────

SendUpdates = Literal["all", "externalOnly", "none"]
EventTypes = Literal[
    "birthday",
    "default",
    "focusTime",
    "fromGmail",
    "outOfOffice",
    "workingLocation",
]
OrderBy = Literal["startTime", "updated"]

# ──────────────────────────────────────────────────────────
# Descriptions shared between endpoints
# ──────────────────────────────────────────────────────────

EVENT_ID = "Event identifier."
MAX_ATTENDEES = (
    "The maximum number of attendees to include in the response. If there are more "
    "than the specified number of attendees, only the participant is returned. Optional."
)
TIME_ZONE = (
    "Time zone used in the response. Optional. The default is the time zone of the calendar."
)
ALWAYS_INCLUDE_EMAIL = (
    "Deprecated and ignored. A value will always be returned in the email field for "
    "the organizer, creator and attendees, even if no real email address is available "
    "(i.e. a generated, non-working value will be provided)."
)
CONFERENCE_DATA_VERSION = (
    "Version number of conference data supported by the API client. Version 0 assumes "
    "no conference data support and ignores conference data in the event's body. "
    "Version 1 enables support for copying of ConferenceData as well as for creating "
    "new conferences using the createRequest field of conferenceData. The default is 0. "
    "Acceptable values are 0 to 1, inclusive."
)
EVENT_LABEL_VERSION = (
    "Version number of the event label feature supported by the API client. Version 0 "
    "assumes no event label support and processes the colorId field for color "
    "management. Version 1 enables support for event labels, and processes the "
    "eventLabelId in the event's body. In this case, the colorId field is ignored. "
    "The default is 0. Acceptable values are 0 to 1, inclusive."
)
SUPPORTS_ATTACHMENTS = (
    "Whether API client performing operation supports event attachments. Optional. "
    "The default is False."
)
SEND_UPDATES = (
    "Guests who should receive notifications about the change. Acceptable values are: "
    '"all" (notifications are sent to all guests), "externalOnly" (notifications are '
    'sent to non-Google Calendar guests only), "none" (no notifications are sent; for '
    "calendar migration tasks, consider using the Events.import method instead)."
)
SEND_NOTIFICATIONS = (
    "Deprecated. Please use sendUpdates instead. Whether to send notifications about "
    "the change. Note that some emails might still be sent even if you set the value "
    "to false. The default is false."
)
MAX_RESULTS = (
    "Maximum number of events returned on one result page. The number of events in the "
    "resulting page may be less than this value, or none at all, even if there are more "
    "events matching the query. Incomplete pages can be detected by a non-empty "
    "nextPageToken field in the response. By default the value is 250 events. The page "
    "size can never be larger than 2500 events. Optional."
)
PAGE_TOKEN = "Token specifying which result page to return. Optional."

# Why syncToken refuses the eight parameters that carry ConflictsWith below.
# Declared on each of them rather than listed here, so adding a parameter cannot
# forget the rule and removing one cannot leave it naming a field that is gone.
SYNC_TOKEN_REASON = (
    "An incremental sync continues the query the token came from, so the filters "
    "have to be the ones already in effect. Drop syncToken to run a fresh query, "
    "or drop the others to continue the sync."
)
_NoSyncToken = ConflictsWith("sync_token", reason=SYNC_TOKEN_REASON)


_CalendarId = Annotated[str, Field(..., description=CALENDAR_ID), Path()]
_EventId = Annotated[str, Field(..., description=EVENT_ID), Path()]
_RecurringEventId = Annotated[str, Field(..., description="Recurring event identifier."), Path()]


# `sendNotifications` and `alwaysIncludeEmail` are documented as deprecated and
# ignored. Mode("disabled") keeps them out of the model's view — a parameter the
# API will not act on is a call the model can waste a turn composing — while the
# field stays in the wire schema for anyone driving the tool from Python.
_SendNotifications = Annotated[
    Optional[bool],
    Field(None, description=SEND_NOTIFICATIONS),
    Query(),
    Mode("disabled"),
]
_AlwaysIncludeEmail = Annotated[
    Optional[bool],
    Field(None, description=ALWAYS_INCLUDE_EMAIL),
    Query(),
    Mode("disabled"),
]
_SendUpdates = Annotated[Optional[SendUpdates], Field(None, description=SEND_UPDATES), Query()]
_MaxAttendees = Annotated[Optional[int], Field(None, ge=1, description=MAX_ATTENDEES), Query()]
_TimeZone = Annotated[Optional[str], Field(None, description=TIME_ZONE), Query()]
_ConferenceDataVersion = Annotated[
    Optional[int], Field(None, ge=0, le=1, description=CONFERENCE_DATA_VERSION), Query()
]
_EventLabelVersion = Annotated[
    Optional[int], Field(None, ge=0, le=1, description=EVENT_LABEL_VERSION), Query()
]
_SupportsAttachments = Annotated[
    Optional[bool], Field(None, description=SUPPORTS_ATTACHMENTS), Query()
]


# ──────────────────────────────────────────────────────────
# Reading
# ──────────────────────────────────────────────────────────


class EventsGetRequest(BaseModel):
    """
    Returns an event based on its Google Calendar ID.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/get
    """

    calendar_id: _CalendarId
    event_id: _EventId

    always_include_email: _AlwaysIncludeEmail = None
    max_attendees: _MaxAttendees = None
    time_zone: _TimeZone = None


class EventsListRequest(BaseModel):
    """
    Returns events on the specified calendar.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/list
    """

    calendar_id: _CalendarId

    always_include_email: _AlwaysIncludeEmail = None
    event_types: Annotated[
        Optional[List[EventTypes]],
        Field(
            None,
            description=(
                "Event types to return. Optional. This parameter can be repeated "
                "multiple times to return events of different types. If unset, returns "
                'all event types. Acceptable values are: "birthday" (special all-day '
                'events with an annual recurrence), "default" (regular events), '
                '"focusTime" (focus time events), "fromGmail" (events from Gmail), '
                '"outOfOffice" (out of office events), "workingLocation" (working '
                "location events)."
            ),
        ),
        Query(),
    ]
    i_cal_uid: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specifies an event ID in the iCalendar format to be provided in the "
                "response. Optional. Use this if you want to search for an event by its "
                "iCalendar ID."
            ),
        ),
        Query(),
        _NoSyncToken,
        # snake_to_camel would send `iCalUid`, which Google ignores — the filter
        # was dropped and the unfiltered list came back with a 200.
        WireName("iCalUID"),
    ]
    max_attendees: _MaxAttendees = None
    max_results: Annotated[
        Optional[int], Field(None, ge=1, le=2500, description=MAX_RESULTS), Query()
    ]
    order_by: Annotated[
        Optional[OrderBy],
        Field(
            None,
            description=(
                "The order of the events returned in the result. Optional. The default "
                'is an unspecified, stable order. Acceptable values are: "startTime" '
                "(order by the start date/time, ascending; this is only available when "
                "querying single events, i.e. the parameter singleEvents is True), "
                '"updated" (order by last modification time, ascending).'
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    page_token: Annotated[Optional[str], Field(None, description=PAGE_TOKEN), Query()]
    private_extended_property: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Extended properties constraint specified as propertyName=value. Matches "
                "only private properties. This parameter might be repeated multiple times "
                "to return events that match all given constraints."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    q: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Free text search terms to find events that match these terms in the "
                "following fields: summary, description, location, attendee's displayName, "
                "attendee's email, organizer's displayName, organizer's email, "
                "workingLocationProperties.officeLocation.buildingId, "
                "workingLocationProperties.officeLocation.deskId, "
                "workingLocationProperties.officeLocation.label, "
                "workingLocationProperties.customLocation.label. These search terms also "
                "match predefined keywords against all display title translations of "
                "working location, out-of-office, and focus-time events. Optional."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    shared_extended_property: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Extended properties constraint specified as propertyName=value. Matches "
                "only shared properties. This parameter might be repeated multiple times "
                "to return events that match all given constraints."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    show_deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                'Whether to include deleted events (with status equals "cancelled") in '
                "the result. Cancelled instances of recurring events (but not the "
                "underlying recurring event) will still be included if showDeleted and "
                "singleEvents are both False. If showDeleted and singleEvents are both "
                "True, only single instances of deleted events (but not the underlying "
                "recurring events) are returned. Optional. The default is False."
            ),
        ),
        Query(),
    ]
    show_hidden_invitations: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to include hidden invitations in the result. Optional. The "
                "default is False."
            ),
        ),
        Query(),
    ]
    single_events: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to expand recurring events into instances and only return single "
                "one-off events and instances of recurring events, but not the underlying "
                "recurring events themselves. Optional. The default is False."
            ),
        ),
        Query(),
    ]
    sync_token: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Token obtained from the nextSyncToken field returned on the last page of "
                "results from the previous list request. It makes the result of this list "
                "request contain only entries that have changed since then. All events "
                "deleted since the previous list request will always be in the result set "
                "and it is not allowed to set showDeleted to False. There are several "
                "query parameters that cannot be specified together with nextSyncToken to "
                "ensure consistency of the client state. These are: iCalUID, orderBy, "
                "privateExtendedProperty, q, sharedExtendedProperty, timeMin, timeMax, "
                "updatedMin. All other query parameters should be the same as for the "
                "initial synchronization to avoid undefined behavior. If the syncToken "
                "expires, the server will respond with a 410 GONE response code and the "
                "client should clear its storage and perform a full synchronization "
                "without any syncToken. Optional. The default is to return all entries."
            ),
        ),
        Query(),
    ]
    time_max: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Upper bound (exclusive) for an event's start time to filter by. Optional. "
                "The default is not to filter by start time. Must be an RFC3339 timestamp "
                "with mandatory time zone offset, for example, 2011-06-03T10:00:00-07:00, "
                "2011-06-03T10:00:00Z. Milliseconds may be provided but are ignored. If "
                "timeMin is set, timeMax must be greater than timeMin."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    time_min: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Lower bound (exclusive) for an event's end time to filter by. Optional. "
                "The default is not to filter by end time. Must be an RFC3339 timestamp "
                "with mandatory time zone offset, for example, 2011-06-03T10:00:00-07:00, "
                "2011-06-03T10:00:00Z. Milliseconds may be provided but are ignored. If "
                "timeMax is set, timeMin must be smaller than timeMax."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    time_zone: _TimeZone = None
    updated_min: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Lower bound for an event's last modification time (as a RFC3339 "
                "timestamp) to filter by. When specified, entries deleted since this time "
                "will always be included regardless of showDeleted. Optional. The default "
                "is not to filter by last modification time."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]

    @model_validator(mode="after")
    def _sync_token_may_not_hide_what_it_reports(self) -> "EventsListRequest":
        """The half of the syncToken rule that is not an exclusion.

        Which parameters it refuses is declared by ``ConflictsWith`` on each of
        them. This is the other shape: two flags that may be set, but not to
        False.
        """
        if self.sync_token is None:
            return self
        if self.show_deleted is False:
            raise ValueError(
                "showDeleted cannot be False alongside syncToken: an incremental sync "
                "always reports the events deleted since the token was issued, and hiding "
                "them would make the result silently incomplete."
            )
        return self

    @model_validator(mode="after")
    def _start_time_order_needs_single_events(self) -> "EventsListRequest":
        if self.order_by == "startTime" and not self.single_events:
            raise ValueError(
                'orderBy="startTime" is only available when singleEvents is True, because '
                "a recurring event has no single start time to order by. Set "
                "singleEvents=true, or order by updated."
            )
        return self

    @model_validator(mode="after")
    def _the_window_must_be_a_window(self) -> "EventsListRequest":
        if self.time_min is not None and self.time_max is not None:
            if self.time_min >= self.time_max:
                raise ValueError(
                    f"timeMin ({self.time_min.isoformat()}) must be smaller than timeMax "
                    f"({self.time_max.isoformat()}); as given the window is empty and no "
                    f"event can match it."
                )
        return self


class EventsInstancesRequest(BaseModel):
    """
    Returns instances of the specified recurring event.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/instances
    """

    calendar_id: _CalendarId
    event_id: _RecurringEventId

    always_include_email: _AlwaysIncludeEmail = None
    max_attendees: _MaxAttendees = None
    max_results: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=2500,
            description=(
                "Maximum number of events returned on one result page. By default the "
                "value is 250 events. The page size can never be larger than 2500 events. "
                "Optional."
            ),
        ),
        Query(),
    ]
    original_start: Annotated[
        Optional[str],
        Field(None, description="The original start time of the instance in the result. Optional."),
        Query(),
    ]
    page_token: Annotated[Optional[str], Field(None, description=PAGE_TOKEN), Query()]
    show_deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                'Whether to include deleted events (with status equals "cancelled") in the '
                "result. Cancelled instances of recurring events will still be included if "
                "singleEvents is False. Optional. The default is False."
            ),
        ),
        Query(),
    ]
    time_max: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Upper bound (exclusive) for an event's start time to filter by. Optional. "
                "The default is not to filter by start time. Must be an RFC3339 timestamp "
                "with mandatory time zone offset."
            ),
        ),
        Query(),
    ]
    time_min: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Lower bound (inclusive) for an event's end time to filter by. Optional. "
                "The default is not to filter by end time. Must be an RFC3339 timestamp "
                "with mandatory time zone offset."
            ),
        ),
        Query(),
    ]
    time_zone: _TimeZone = None


# ──────────────────────────────────────────────────────────
# Writing
# ──────────────────────────────────────────────────────────


class EventsInsertRequest(BaseModel):
    """
    Creates an event.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/insert
    """

    calendar_id: _CalendarId

    conference_data_version: _ConferenceDataVersion = None
    event_label_version: _EventLabelVersion = None
    max_attendees: _MaxAttendees = None
    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None
    supports_attachments: _SupportsAttachments = None

    event: Annotated[Event, Field(..., description="The event to insert."), Body()]


class EventsUpdateRequest(BaseModel):
    """
    Updates an event. This method does not support patch semantics and always
    updates the entire event resource; to do a partial update, use `events_patch`.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/update
    """

    calendar_id: _CalendarId
    event_id: _EventId

    always_include_email: _AlwaysIncludeEmail = None
    conference_data_version: _ConferenceDataVersion = None
    event_label_version: _EventLabelVersion = None
    max_attendees: _MaxAttendees = None
    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None
    supports_attachments: _SupportsAttachments = None

    event: Annotated[
        Event,
        Field(
            ...,
            description=(
                "The event, in full. This replaces the stored event, so any field left "
                "out is cleared rather than kept — use events_patch to change part of an "
                "event."
            ),
        ),
        Body(),
    ]


# PUT replaces and PATCH merges, so the body that mandates start and end is the
# wrong body for the endpoint whose purpose is not having to send them. Derived
# rather than written out beside `Event`: descriptions, constraints, markers and
# the dateTime/timeZone validator all come across, and none of them acquires a
# second home to drift from.
PatchEvent = partial_of(Event, name="PatchEvent")


class EventsPatchRequest(BaseModel):
    """
    Updates an event. This method supports patch semantics: the provided fields
    are merged into the existing event.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/patch
    """

    calendar_id: _CalendarId
    event_id: _EventId

    always_include_email: _AlwaysIncludeEmail = None
    conference_data_version: _ConferenceDataVersion = None
    event_label_version: _EventLabelVersion = None
    max_attendees: _MaxAttendees = None
    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None
    supports_attachments: _SupportsAttachments = None

    event: Annotated[
        PatchEvent,  # type: ignore[valid-type]
        Field(
            ...,
            description=(
                "The fields to change. Anything left out keeps its stored value, so send "
                "only what is being changed."
            ),
        ),
        Body(),
    ]


class EventsImportRequest(BaseModel):
    """
    Imports an event. This operation is used to add a private copy of an existing
    event to a calendar. Only events with an `eventType` of `default` may be imported.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/import
    """

    calendar_id: _CalendarId

    conference_data_version: _ConferenceDataVersion = None
    event_label_version: _EventLabelVersion = None
    supports_attachments: _SupportsAttachments = None

    event: Annotated[
        Event,
        Field(
            ...,
            description=(
                "The event to import. iCalUID is required in addition to start and end: "
                "it is what identifies the same event across calendaring systems, which "
                "is the whole point of importing rather than inserting."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _import_requires_ical_uid(self) -> "EventsImportRequest":
        """``iCalUID`` is required by this endpoint and by no other.

        `Event` cannot mandate it: `events_insert` documents that the id and the
        iCalUID are alternatives and only one should be supplied at creation
        time, so requiring it on the resource would break the endpoint next door.
        The requirement belongs to the operation, so it is checked here.
        """
        if not getattr(self.event, "i_cal_uid", None):
            raise ValueError(
                "iCalUID is required when importing an event. It is the identifier the "
                "event carries across calendaring systems, as defined in RFC5545; note "
                "that it is not the same as id. To create a new event instead, use "
                "events_insert, which assigns one."
            )
        return self


class EventsMoveRequest(BaseModel):
    """
    Moves an event to another calendar, i.e. changes an event's organizer. Note
    that only `default` events can be moved; `birthday`, `focusTime`,
    `fromGmail`, `outOfOffice` and `workingLocation` events cannot be moved.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/move
    """

    calendar_id: Annotated[
        str,
        Field(
            ...,
            description="Calendar identifier of the source calendar where the event currently is on.",
        ),
        Path(),
    ]
    event_id: _EventId

    destination: Annotated[
        str,
        Field(
            ...,
            description="Calendar identifier of the target calendar where the event is to be moved to.",
        ),
        Query(),
    ]
    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None


class EventsQuickAddRequest(BaseModel):
    """
    Creates an event based on a simple text string.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/quickAdd
    """

    calendar_id: _CalendarId

    text: Annotated[
        str,
        Field(..., min_length=1, description="The text describing the event to be created."),
        Query(),
    ]
    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None


class EventsDeleteRequest(BaseModel):
    """
    Deletes an event.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events/delete
    """

    calendar_id: _CalendarId
    event_id: _EventId

    send_notifications: _SendNotifications = None
    send_updates: _SendUpdates = None
