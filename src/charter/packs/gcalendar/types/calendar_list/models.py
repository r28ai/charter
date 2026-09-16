from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

# All five values calendarList documents. `writerWithoutPrivateAccess` was
# missing, and the field's own description listed it — so a model reading the
# description sent a value the schema then refused, with no way to tell a local
# rejection from the API's.
AccessRole = Literal[
    "freeBusyReader",
    "owner",
    "reader",
    "writer",
    "writerWithoutPrivateAccess",
]
NotificationType = Literal[
    "eventCreation",
    "eventChange",
    "eventCancellation",
    "eventResponse",
    "agenda",
]
ConferenceSolutionType = Literal[
    "eventHangout",
    "eventNamedHangout",
    "hangoutsMeet",
]

# ──────────────────────────────────────────────────────────
# Nested / helper models
# ──────────────────────────────────────────────────────────


class DefaultReminder(BaseModel):
    """Default reminder for events on this calendar."""

    method: Literal["email", "popup"] = Field(
        ...,
        description=(
            "The method used by this reminder. Possible values are: "
            "'email' - Reminders are sent via email. "
            "'popup' - Reminders are sent via a UI popup. "
            "Required when adding a reminder."
        ),
    )
    minutes: int = Field(
        ...,
        ge=0,
        le=40320,
        description=(
            "Number of minutes before the start of the event when the reminder should trigger. "
            "Valid values are between 0 and 40320 (4 weeks in minutes). "
            "Required when adding a reminder."
        ),
    )


class Notification(BaseModel):
    """Notification configuration for a calendar."""

    type: NotificationType = Field(
        ...,
        description=(
            "The type of notification. Possible values are: "
            "'eventCreation' - Notification sent when a new event is put on the calendar. "
            "'eventChange' - Notification sent when an event is changed. "
            "'eventCancellation' - Notification sent when an event is cancelled. "
            "'eventResponse' - Notification sent when an attendee responds to the event invitation. "
            "'agenda' - An agenda with the events of the day (sent out in the morning). "
            "Required when adding a notification."
        ),
    )
    method: Literal["email"] = Field(
        ...,
        description=(
            "The method used to deliver the notification. The possible value is: "
            "'email' - Notifications are sent via email. "
            "Required when adding a notification."
        ),
    )


class NotificationSettings(BaseModel):
    """The notifications that the authenticated user is receiving for this calendar."""
    
    notifications: Optional[List[Notification]] = Field(
        None,
        description="The list of notifications set for this calendar.",
    )


class ConferenceProperties(BaseModel):
    """Conferencing properties for this calendar, for example what types of conferences are allowed."""
    
    allowed_conference_solution_types: Optional[List[ConferenceSolutionType]] = Field(
        None,
        description=(
            "The types of conference solutions that are supported for this calendar. "
            "The possible values are: 'eventHangout', 'eventNamedHangout', 'hangoutsMeet'."
        ),
    )


# ──────────────────────────────────────────────────────────
# CalendarList entry resource
# ──────────────────────────────────────────────────────────


class CalendarListEntry(BaseModel):
    """Single calendar in a user's calendar list.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendarList#resource
    """

    # Read-only fields
    kind: Annotated[
        Optional[Literal["calendar#calendarListEntry"]],
        Field("calendar#calendarListEntry", description='Type of the resource ("calendar#calendarListEntry").'),
        Mode("response_only")
    ]
    etag: Annotated[
        Optional[str],
        Field(None, description="ETag of the resource."),
        Mode("response_only")
    ]
    id: Annotated[
        str,
        Field(..., description="Identifier of the calendar."),
        Mode("response_only")
    ]
    summary: Annotated[
        Optional[str],
        Field(None, description="Title of the calendar. Read-only."),
        Mode("response_only")
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="Description of the calendar. Optional. Read-only."),
        Mode("response_only")
    ]
    location: Annotated[
        Optional[str],
        Field(None, description="Geographic location of the calendar as free-form text. Optional. Read-only."),
        Mode("response_only")
    ]
    time_zone: Annotated[
        Optional[str],
        Field(None, description="The time zone of the calendar. Optional. Read-only."),
        Mode("response_only")
    ]
    access_role: Annotated[
        Optional[AccessRole],
        Field(
            None,
            description=(
                "The effective access role that the authenticated user has on the calendar. Read-only. "
                "Possible values are: "
                "'freeBusyReader' - Provides read access to free/busy information. "
                "'reader' - Provides read access to the calendar. Private events will appear to users with reader access, but event details will be hidden. "
                "'writer' - Provides read and write access to the calendar. Private events will appear to users with writer access, and event details will be visible. "
                "'owner' - Provides ownership of the calendar. This role has all of the permissions of the writer role with the additional ability to see and manipulate ACLs."
            ),
        ),
        Mode("response_only")
    ]
    auto_accept_invitations: Annotated[
        Optional[bool],
        Field(None, description="Whether this calendar automatically accepts invitations. Only valid for resource calendars. Read-only."),
        Mode("response_only")
    ]
    data_owner: Annotated[
        Optional[str],
        Field(None, description="The email of the owner of the calendar. Set only for secondary calendars. Read-only."),
        Mode("response_only")
    ]
    primary: Annotated[
        Optional[bool],
        Field(None, description="Whether the calendar is the primary calendar of the authenticated user. Read-only. Optional. The default is False."),
        Mode("response_only")
    ]
    deleted: Annotated[
        Optional[bool],
        Field(None, description="Whether this calendar list entry has been deleted from the calendar list. Read-only. Optional. The default is False."),
        Mode("response_only")
    ]
    
    # Writable fields
    summary_override: Optional[str] = Field(
        None,
        description="The summary that the authenticated user has set for this calendar. Optional.",
    )
    color_id: Optional[str] = Field(
        None,
        description=(
            "The color of the calendar. This is an ID referring to an entry in the calendar section of the colors definition (see the colors endpoint). "
            "This property is superseded by the backgroundColor and foregroundColor properties and can be ignored when using these properties. Optional."
        ),
    )
    background_color: Optional[str] = Field(
        None,
        description=(
            'The main color of the calendar in the hexadecimal format "#0088aa". '
            "This property supersedes the index-based colorId property. "
            "To set or change this property, you need to specify colorRgbFormat=true in the parameters of the insert, update and patch methods. Optional."
        ),
    )
    foreground_color: Optional[str] = Field(
        None,
        description=(
            'The foreground color of the calendar in the hexadecimal format "#ffffff". '
            "This property supersedes the index-based colorId property. "
            "To set or change this property, you need to specify colorRgbFormat=true in the parameters of the insert, update and patch methods. Optional."
        ),
    )
    hidden: Optional[bool] = Field(
        None,
        description="Whether the calendar has been hidden from the list. Optional. The attribute is only returned when the calendar is hidden, in which case the value is true.",
    )
    selected: Optional[bool] = Field(
        None,
        description="Whether the calendar content shows up in the calendar UI. Optional. The default is False.",
    )
    default_reminders: Optional[List[DefaultReminder]] = Field(
        None,
        description="The default reminders that the authenticated user has for this calendar.",
    )
    notification_settings: Optional[NotificationSettings] = Field(
        None,
        description="The notifications that the authenticated user is receiving for this calendar.",
    )
    
    # Conference properties (read-only based on "what types are supported")
    conference_properties: Annotated[
        Optional[ConferenceProperties],
        Field(None, description="Conferencing properties for this calendar, for example what types of conferences are allowed."),
        Mode("response_only")
    ]


# ──────────────────────────────────────────────────────────
# List response wrapper
# ──────────────────────────────────────────────────────────


class CalendarListResponse(BaseModel):
    """Response model for CalendarList: list."""

    kind: Annotated[
        Optional[Literal["calendar#calendarList"]],
        Field("calendar#calendarList"),
        Mode("response_only")
    ]
    etag: Annotated[
        Optional[str],
        Field(None),
        Mode("response_only")
    ]
    next_page_token: Annotated[
        Optional[str],
        Field(None),
        Mode("response_only")
    ]
    next_sync_token: Annotated[
        Optional[str],
        Field(None),
        Mode("response_only")
    ]
    items: Annotated[
        Optional[List[CalendarListEntry]],
        Field(None),
        Mode("response_only")
    ] 