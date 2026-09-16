#
# ⚠️  WHY WE USE `Annotated` HERE
# -------------------------------------------------------------
# Pydantic <2.10 has a bug: if a field's *name* is the same as the
# *type* you annotate it with **and** you pass a `Field(...)` directly
# (e.g. `date: date = Field(...)`), its internal `__repr__` recurses
# endlessly and you hit `RecursionError: maximum recursion depth
# exceeded`.  Using `typing.Annotated[..., Field(...)]` avoids the
# faulty repr path.  See the open issue:
# https://github.com/pydantic/pydantic/issues/7600
# -------------------------------------------------------------


from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from charter.types import Mode, WireName

# ──────────────────────────────────────────────────────────
# Shared / Nested value objects
# ──────────────────────────────────────────────────────────


def _offset_label(delta) -> str:
    """A UTC offset as ``+02:00``, which is how it is written in RFC3339."""
    if delta is None:
        return "none"
    total = int(delta.total_seconds())
    sign = "-" if total < 0 else "+"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


class EventDateTime(BaseModel):
    """Represents the start or end of an event."""
    # Use Annotated + Field to dodge the recursion bug (see header comment).
    date: Annotated[
        Optional[date],
        Field(None, description='The date, in the format "yyyy-mm-dd", if this is an all-day event.')
    ]
    date_time: Optional[datetime] = Field(
        None,
        description=(
            'The time, as a combined date-time value (formatted according to RFC3339). '
            'A time zone offset is required unless a time zone is explicitly specified in timeZone.'
        ),
    )
    time_zone: Optional[str] = Field(
        None,
        description=(
            'The time zone in which the time is specified. (Formatted as an IANA Time Zone Database name, e.g. "Europe/Zurich".) '
            'For recurring events this field is required and specifies the time zone in which the recurrence is expanded. '
            'For single events this field is optional and indicates a custom time zone for the event start/end.'
        ),
    )

    @model_validator(mode="after")
    def _require_date_or_datetime(self) -> EventDateTime:
        if self.date is None and self.date_time is None:
            raise ValueError("Either date or dateTime must be provided.")
        return self

    @model_validator(mode="after")
    def _offset_must_agree_with_time_zone(self) -> EventDateTime:
        """Refuse a ``dateTime`` whose offset contradicts ``timeZone``.

        These two fields can disagree, and when they do the API does not say so:
        for a single event it uses the offset and ignores ``timeZone`` entirely.
        An event sent as ``2026-09-14T08:45:00Z`` with ``timeZone`` of
        ``Europe/Paris`` is created at 10:45 Paris time, two hours from where the
        caller meant, and reads back looking deliberate.

        A model given both fields fills in both, because the API's own
        description of ``dateTime`` says an offset is required unless a time zone
        is specified — which reads as an invitation to supply the pair. Measured
        over 110 runs, that combination was the single largest source of wrong
        answers on the calendar scenarios, and the arm with no schema at all did
        better precisely because it never saw two fields to fill.

        So the disagreement is refused rather than resolved. Which of the two the
        caller meant is not knowable here: ``Z`` may be exactly right and the zone
        merely the display zone. The message names the correction so a model can
        make the choice itself on the next call.

        It also names the escape that does *not* work. Offered "send the local
        offset, or drop the offset and keep timeZone", a model dropped
        ``timeZone`` and kept ``Z`` — legal, no longer contradictory, and still
        the wrong instant, so nothing here could refuse it a second time. An
        error that leaves a plausible wrong move available gets taken.
        """
        if self.date_time is None or self.time_zone is None:
            return self
        if self.date_time.tzinfo is None:
            # The documented pairing: a local time, and the zone it is local to.
            return self
        try:
            named = self.date_time.astimezone(ZoneInfo(self.time_zone)).utcoffset()
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            # Not a zone we can resolve; the API is entitled to its own opinion.
            return self

        supplied = self.date_time.utcoffset()
        if supplied == named:
            return self

        local = self.date_time.astimezone(ZoneInfo(self.time_zone))
        raise ValueError(
            f"dateTime {self.date_time.isoformat()} carries offset "
            f"{_offset_label(supplied)}, but timeZone {self.time_zone!r} is "
            f"{_offset_label(named)} at that moment. The API uses the offset and "
            f"ignores timeZone, so this would land at {local.strftime('%H:%M')} "
            f"{self.time_zone} rather than {self.date_time.strftime('%H:%M')}. "
            f"For that wall-clock time in {self.time_zone}, send dateTime "
            f"{self.date_time.replace(tzinfo=None).isoformat()}"
            f"{_offset_label(named)}. Do not fix this by removing timeZone: "
            f"that is accepted, and still creates the event at "
            f"{local.strftime('%H:%M')} {self.time_zone}."
        )


class Attachment(BaseModel):
    file_url: str = Field(
        ...,
        description=(
            "URL link to the attachment. "
            "For adding Google Drive file attachments use the same format as in alternateLink property of the Files resource in the Drive API. "
            "Required when adding an attachment."
        ),
    )
    file_id: Annotated[
        Optional[str],
        Field(None, description="ID of the attached file. Read-only. For Google Drive files, this is the ID of the corresponding Files resource entry in the Drive API."),
        Mode("response_only"),
    ]
    icon_link: Optional[str] = Field(
        None,
        description="URL link to the attachment's icon. This field can only be modified for custom third-party attachments.",
    )
    mime_type: Annotated[
        Optional[str],
        Field(None, description="Internet media type (MIME type) of the attachment."),
        Mode("response_only"),
    ]
    title: Annotated[
        Optional[str],
        Field(None, description="Attachment title."),
        Mode("response_only"),
    ]


class Attendee(BaseModel):
    email: str = Field(
        ...,
        description=(
            "The attendee's email address, if available. This field must be present when adding an attendee. "
            "It must be a valid email address as per RFC5322. Required when adding an attendee."
        ),
    )
    additional_guests: Optional[int] = Field(
        0,
        ge=0,
        description="Number of additional guests. Optional. The default is 0.",
    )
    comment: Optional[str] = Field(
        None,
        description="The attendee's response comment. Optional.",
    )
    display_name: Optional[str] = Field(
        None,
        description="The attendee's name, if available. Optional.",
    )
    optional: Optional[bool] = Field(
        None,
        description="Whether this is an optional attendee. Optional. The default is False.",
    )
    organizer: Annotated[
        Optional[bool],
        Field(None, description="Whether the attendee is the organizer of the event. Read-only. The default is False."),
        Mode("response_only"),
    ]
    resource: Optional[bool] = Field(
        None,
        description=(
            "Whether the attendee is a resource. Can only be set when the attendee is added to the event for the first time. "
            "Subsequent modifications are ignored. Optional. The default is False."
        ),
    )
    response_status: Optional[
        Literal["needsAction", "declined", "tentative", "accepted"]
    ] = Field(
        None,
        description=(
            "The attendee's response status. Possible values are: "
            '"needsAction" - The attendee has not responded to the invitation (recommended for new events). '
            '"declined" - The attendee has declined the invitation. '
            '"tentative" - The attendee has tentatively accepted the invitation. '
            '"accepted" - The attendee has accepted the invitation. '
            "Warning: If you add an event using the values declined, tentative, or accepted, attendees with certain settings "
            'might have their response reset to needsAction. Furthermore, if more than 200 guests are invited, response status is not propagated.'
        ),
    )
    self_: Annotated[
        Optional[bool],
        Field(None, alias="self", description="Whether this entry represents the calendar on which this copy of the event appears. Read-only. The default is False."),
        Mode("response_only"),
    ]


class BirthdayProperties(BaseModel):
    contact: Annotated[
        Optional[str],
        Field(
            None,
            description='Resource name of the contact this birthday event is linked to. This can be used to fetch contact details from People API. Format: "people/c12345". Read-only.',
        ),
        Mode("response_only"),
    ]
    custom_type_name: Annotated[
        Optional[str],
        Field(
            None,
            description='Custom type label specified for this event. This is populated if birthdayProperties.type is set to "custom". Read-only.',
        ),
        Mode("response_only"),
    ]
    type: Optional[
        Literal["anniversary", "birthday", "custom", "other", "self"]
    ] = Field(
        "birthday",
        description=(
            "Type of birthday or special event. Possible values are: "
            '"anniversary" - An anniversary other than birthday. Always has a contact. '
            '"birthday" - A birthday event. This is the default value. '
            '"custom" - A special date whose label is further specified in the customTypeName field. Always has a contact. '
            '"other" - A special date which does not fall into the other categories, and does not have a custom label. Always has a contact. '
            '"self" - Calendar owner\'s own birthday. Cannot have a contact. '
            'The Calendar API only supports creating events with the type "birthday". The type cannot be changed after the event is created.'
        ),
    )


class Creator(BaseModel):
    """The creator of the event. Read-only."""
    display_name: Optional[str] = Field(None, description="The creator's name, if available.")
    email: Optional[str] = Field(None, description="The creator's email address, if available.")
    id: Optional[str] = Field(None, description="The creator's Profile ID, if available.")
    self_: Annotated[
        Optional[bool],
        Field(None, alias="self", description="Whether the creator corresponds to the calendar on which this copy of the event appears. Read-only. The default is False."),
    ]


class Organizer(BaseModel):
    """The organizer of the event. Read-only, except when importing an event."""
    display_name: Optional[str] = Field(None, description="The organizer's name, if available.")
    email: Optional[str] = Field(
        None,
        description="The organizer's email address, if available. It must be a valid email address as per RFC5322.",
    )
    id: Optional[str] = Field(None, description="The organizer's Profile ID, if available.")
    self_: Annotated[
        Optional[bool],
        Field(None, alias="self", description="Whether the organizer corresponds to the calendar on which this copy of the event appears. Read-only. The default is False."),
    ]


class ConferenceSolutionKey(BaseModel):
    type: Optional[
        Literal["eventHangout", "eventNamedHangout", "hangoutsMeet", "addOn"]
    ] = Field(
        None,
        description=(
            "The conference solution type. If a client encounters an unfamiliar or empty type, it should still be able to display the entry points. "
            "However, it should disallow modifications. The possible values are: "
            '"eventHangout" - Hangouts for consumers (deprecated; existing events may show this conference solution type but new conferences cannot be created). '
            '"eventNamedHangout" - Classic Hangouts for Google Workspace users (deprecated; existing events may show this conference solution type but new conferences cannot be created). '
            '"hangoutsMeet" - Google Meet (http://meet.google.com). '
            '"addOn" - 3P conference providers.'
        ),
    )


class ConferenceSolution(BaseModel):
    """The conference solution, such as Google Meet."""
    icon_uri: Optional[str] = Field(None, description="The user-visible icon for this solution.")
    key: Optional[ConferenceSolutionKey] = Field(
        None,
        description="The key which can uniquely identify the conference solution for this event.",
    )
    name: Optional[str] = Field(None, description="The user-visible name of this solution. Not localized.")


class CreateRequestStatus(BaseModel):
    """The status of the conference create request."""

    # Google marks it Read-only on the reference page, and `createRequest` is a
    # field a caller does send, so the status rode along into the LLM view of
    # every write that can attach a conference. Nothing rejects it; Google
    # ignores it, and the model was offered a field it can only get wrong.
    status_code: Annotated[
        Optional[Literal["pending", "success", "failure"]],
        Mode("response_only"),
        Field(
            None,
            description=(
            "The current status of the conference create request. Read-only. The possible values are: "
            '"pending" - the conference create request is still being processed. '
            '"success" - the conference create request succeeded, the entry points are populated. '
            '"failure" - the conference create request failed, there are no entry points.'
            ),
        ),
    ] = None


class CreateRequest(BaseModel):
    """A request to generate a new conference and attach it to the event."""
    conference_solution_key: Optional[ConferenceSolutionKey] = Field(
        None,
        description="The conference solution, such as Hangouts or Google Meet.",
    )
    request_id: Optional[str] = Field(
        None,
        description=(
            "The client-generated unique ID for this request. Clients should regenerate this ID for every new request. "
            "If an ID provided is the same as for the previous request, the request is ignored."
        ),
    )
    status: Optional[CreateRequestStatus] = Field(
        None,
        description="The status of the conference create request.",
    )


class EntryPoint(BaseModel):
    """Information about individual conference entry points, such as URLs or phone numbers."""
    access_code: Optional[str] = Field(
        None,
        description=(
            "The access code to access the conference. The maximum length is 128 characters. "
            "When creating new conference data, populate only the subset of {meetingCode, accessCode, passcode, password, pin} "
            "fields that match the terminology that the conference provider uses. Only the populated fields should be displayed. Optional."
        ),
    )
    entry_point_type: Optional[
        Literal["video", "phone", "sip", "more"]
    ] = Field(
        None,
        description=(
            "The type of the conference entry point. Possible values are: "
            '"video" - joining a conference over HTTP. A conference can have zero or one video entry point. '
            '"phone" - joining a conference by dialing a phone number. A conference can have zero or more phone entry points. '
            '"sip" - joining a conference over SIP. A conference can have zero or one sip entry point. '
            '"more" - further conference joining instructions, for example additional phone numbers. A conference can have zero or one more entry point. '
            'A conference with only a more entry point is not a valid conference.'
        ),
    )
    label: Optional[str] = Field(
        None,
        description=(
            "The label for the URI. Visible to end users. Not localized. The maximum length is 512 characters. "
            "Examples: for video: meet.google.com/aaa-bbbb-ccc; for phone: +1 123 268 2601; for sip: 12345678@altostrat.com; for more: should not be filled. Optional."
        ),
    )
    meeting_code: Optional[str] = Field(
        None,
        description=(
            "The meeting code to access the conference. The maximum length is 128 characters. "
            "When creating new conference data, populate only the subset of {meetingCode, accessCode, passcode, password, pin} "
            "fields that match the terminology that the conference provider uses. Only the populated fields should be displayed. Optional."
        ),
    )
    passcode: Optional[str] = Field(
        None,
        description=(
            "The passcode to access the conference. The maximum length is 128 characters. "
            "When creating new conference data, populate only the subset of {meetingCode, accessCode, passcode, password, pin} "
            "fields that match the terminology that the conference provider uses. Only the populated fields should be displayed."
        ),
    )
    password: Optional[str] = Field(
        None,
        description=(
            "The password to access the conference. The maximum length is 128 characters. "
            "When creating new conference data, populate only the subset of {meetingCode, accessCode, passcode, password, pin} "
            "fields that match the terminology that the conference provider uses. Only the populated fields should be displayed. Optional."
        ),
    )
    pin: Optional[str] = Field(
        None,
        description=(
            "The PIN to access the conference. The maximum length is 128 characters. "
            "When creating new conference data, populate only the subset of {meetingCode, accessCode, passcode, password, pin} "
            "fields that match the terminology that the conference provider uses. Only the populated fields should be displayed. Optional."
        ),
    )
    uri: Optional[str] = Field(
        None,
        description=(
            "The URI of the entry point. The maximum length is 1300 characters. Format: "
            "for video, http: or https: schema is required. "
            "for phone, tel: schema is required. The URI should include the entire dial sequence (e.g., tel:+12345678900,,,123456789;1234). "
            "for sip, sip: schema is required, e.g., sip:12345678@myprovider.com. "
            "for more, http: or https: schema is required."
        ),
    )


class ConferenceData(BaseModel):
    """The conference-related information, such as details of a Google Meet conference."""
    conference_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the conference. Can be used by developers to keep track of conferences, should not be displayed to users. "
            "The ID value is formed differently for each conference solution type: "
            "eventHangout: ID is not set. (This conference type is deprecated.) "
            "eventNamedHangout: ID is the name of the Hangout. (This conference type is deprecated.) "
            "hangoutsMeet: ID is the 10-letter meeting code, for example aaa-bbbb-ccc. "
            "addOn: ID is defined by the third-party provider. Optional."
        ),
    )
    conference_solution: Optional[ConferenceSolution] = Field(
        None,
        description=(
            "The conference solution, such as Google Meet. Unset for a conference with a failed create request. "
            "Either conferenceSolution and at least one entryPoint, or createRequest is required."
        ),
    )
    create_request: Optional[CreateRequest] = Field(
        None,
        description=(
            "A request to generate a new conference and attach it to the event. The data is generated asynchronously. "
            "To see whether the data is present check the status field. "
            "Either conferenceSolution and at least one entryPoint, or createRequest is required."
        ),
    )
    entry_points: Optional[List[EntryPoint]] = Field(
        None,
        description=(
            "Information about individual conference entry points, such as URLs or phone numbers. "
            "All of them must belong to the same conference. "
            "Either conferenceSolution and at least one entryPoint, or createRequest is required."
        ),
    )
    notes: Optional[str] = Field(
        None,
        description=(
            "Additional notes (such as instructions from the domain administrator, legal notices) to display to the user. "
            "Can contain HTML. The maximum length is 2048 characters. Optional."
        ),
    )
    signature: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The signature of the conference data. Generated on server side. "
                "Unset for a conference with a failed create request. Optional for a conference with a pending create request."
            ),
        ),
        Mode("response_only"),
    ]


class FocusTimeProperties(BaseModel):
    """Focus Time event data. Used if eventType is focusTime."""
    auto_decline_mode: Optional[
        Literal["declineNone", "declineAllConflictingInvitations", "declineOnlyNewConflictingInvitations"]
    ] = Field(
        None,
        description=(
            "Whether to decline meeting invitations which overlap Focus Time events. Valid values are: "
            '"declineNone" - no meeting invitations are declined. '
            '"declineAllConflictingInvitations" - all conflicting meeting invitations that conflict with the event are declined. '
            '"declineOnlyNewConflictingInvitations" - only new conflicting meeting invitations which arrive while the Focus Time event is present are to be declined.'
        ),
    )
    chat_status: Optional[Literal["available", "doNotDisturb"]] = Field(
        None,
        description="The status to mark the user in Chat and related products. This can be available or doNotDisturb.",
    )
    decline_message: Optional[str] = Field(
        None,
        description="Response message to set if an existing event or new invitation is automatically declined by Calendar.",
    )


class OutOfOfficeProperties(BaseModel):
    """Out of office event data. Used if eventType is outOfOffice."""
    auto_decline_mode: Optional[
        Literal["declineNone", "declineAllConflictingInvitations", "declineOnlyNewConflictingInvitations"]
    ] = Field(
        None,
        description=(
            "Whether to decline meeting invitations which overlap Out of office events. Valid values are: "
            '"declineNone" - no meeting invitations are declined. '
            '"declineAllConflictingInvitations" - all conflicting meeting invitations that conflict with the event are declined. '
            '"declineOnlyNewConflictingInvitations" - only new conflicting meeting invitations which arrive while the Out of office event is present are to be declined.'
        ),
    )
    decline_message: Optional[str] = Field(
        None,
        description="Response message to set if an existing event or new invitation is automatically declined by Calendar.",
    )


class OfficeLocation(BaseModel):
    building_id: Optional[str] = Field(
        None,
        description="An optional building identifier. This should reference a building ID in the organization's Resources database.",
    )
    desk_id: Optional[str] = Field(None, description="An optional desk identifier.")
    floor_id: Optional[str] = Field(None, description="An optional floor identifier.")
    floor_section_id: Optional[str] = Field(None, description="An optional floor section identifier.")
    label: Optional[str] = Field(
        None,
        description="The office name that's displayed in Calendar Web and Mobile clients. We recommend you reference a building name in the organization's Resources database.",
    )


class CustomLocation(BaseModel):
    label: Optional[str] = Field(None, description="An optional extra label for additional information.")


class WorkingLocationProperties(BaseModel):
    type: Literal["homeOffice", "officeLocation", "customLocation"] = Field(
        ...,
        description=(
            "Type of the working location. Possible values are: "
            '"homeOffice" - The user is working at home. '
            '"officeLocation" - The user is working from an office. '
            '"customLocation" - The user is working from a custom location. '
            "Any details are specified in a sub-field of the specified name, but this field may be missing if empty. "
            "Required when adding working location properties."
        ),
    )
    custom_location: Optional[CustomLocation] = Field(
        None,
        description="If present, specifies that the user is working from a custom location.",
    )
    home_office: Optional[bool] = Field(
        None,
        description="If present, specifies that the user is working at home.",
    )
    office_location: Optional[OfficeLocation] = Field(
        None,
        description="If present, specifies that the user is working from an office.",
    )


class ExtendedProperties(BaseModel):
    private: Optional[Dict[str, str]] = Field(
        None,
        description="Properties that are private to the copy of the event that appears on this calendar.",
    )
    shared: Optional[Dict[str, str]] = Field(
        None,
        description="Properties that are shared between copies of the event on other attendees' calendars.",
    )


class ReminderOverride(BaseModel):
    method: Literal["email", "popup"] = Field(
        ...,
        description=(
            "The method used by this reminder. Possible values are: "
            '"email" - Reminders are sent via email. '
            '"popup" - Reminders are sent via a UI popup. '
            "Required when adding a reminder."
        ),
    )
    minutes: int = Field(
        ...,
        ge=0,
        le=40320,
        description=(
            "Number of minutes before the start of the event when the reminder should trigger. "
            "Valid values are between 0 and 40320 (4 weeks in minutes). Required when adding a reminder."
        ),
    )


class Reminders(BaseModel):
    use_default: Optional[bool] = Field(
        None,
        description="Whether the default reminders of the calendar apply to the event.",
    )
    overrides: Annotated[
        Optional[List[ReminderOverride]],
        Field(
            max_length=5,
            description=(
                "If the event doesn't use the default reminders, this lists the reminders specific to the event, "
                "or, if not set, indicates that no reminders are set for this event. The maximum number of override reminders is 5."
            ),
        ),
    ]


class EventGadget(BaseModel):
    """A gadget that extends this event. Gadgets are deprecated; this structure is instead only used for returning birthday calendar metadata."""
    display: Optional[Literal["icon", "chip"]] = Field(
        None,
        description=(
            "The gadget's display mode. Deprecated. Possible values are: "
            '"icon" - The gadget displays next to the event\'s title in the calendar view. '
            '"chip" - The gadget displays when the event is clicked.'
        ),
    )
    height: Optional[int] = Field(
        None,
        gt=0,
        description="The gadget's height in pixels. The height must be an integer greater than 0. Optional. Deprecated.",
    )
    icon_link: Optional[str] = Field(
        None,
        description="The gadget's icon URL. The URL scheme must be HTTPS. Deprecated.",
    )
    link: Optional[str] = Field(
        None,
        description="The gadget's URL. The URL scheme must be HTTPS. Deprecated.",
    )
    preferences: Optional[Dict[str, str]] = Field(
        None,
        description="Preferences.",
    )
    title: Optional[str] = Field(None, description="The gadget's title. Deprecated.")
    type: Optional[str] = Field(None, description="The gadget's type. Deprecated.")
    width: Optional[int] = Field(
        None,
        gt=0,
        description="The gadget's width in pixels. The width must be an integer greater than 0. Optional. Deprecated.",
    )


class Source(BaseModel):
    title: Optional[str] = Field(
        None,
        description="Title of the source; for example a title of a web page or an email subject.",
    )
    url: Optional[str] = Field(
        None,
        description="URL of the source pointing to a resource. The URL scheme must be HTTP or HTTPS.",
    )


# ──────────────────────────────────────────────────────────
# Event body
# ──────────────────────────────────────────────────────────


class Event(BaseModel):
    """Google Calendar Event resource.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/events#resource
    """

    # Required fields
    start: EventDateTime = Field(
        ...,
        description="The (inclusive) start time of the event. For a recurring event, this is the start time of the first instance.",
    )
    end: EventDateTime = Field(
        ...,
        description="The (exclusive) end time of the event. For a recurring event, this is the end time of the first instance.",
    )

    # Writable optional fields
    anyone_can_add_self: Optional[bool] = Field(
        None,
        description="Whether anyone can invite themselves to the event (deprecated). Optional. The default is False.",
    )
    color_id: Optional[str] = Field(
        None,
        description="The color of the event. This is an ID referring to an entry in the event section of the colors definition (see the colors endpoint). Optional.",
    )
    description: Optional[str] = Field(
        None,
        description="Description of the event. Can contain HTML. Optional.",
    )
    event_type: Optional[
        Literal[
            "birthday",
            "default",
            "focusTime",
            "fromGmail",
            "outOfOffice",
            "workingLocation",
        ]
    ] = Field(
        None,
        description=(
            "Specific type of the event. This cannot be modified after the event is created. Possible values are: "
            '"birthday" - A special all-day event with an annual recurrence. '
            '"default" - A regular event or not further specified. '
            '"focusTime" - A focus-time event. '
            '"fromGmail" - An event from Gmail. This type of event cannot be created. '
            '"outOfOffice" - An out-of-office event. '
            '"workingLocation" - A working location event.'
        ),
    )
    guests_can_invite_others: Optional[bool] = Field(
        None,
        description="Whether attendees other than the organizer can invite others to the event. Optional. The default is True.",
    )
    guests_can_modify: Optional[bool] = Field(
        None,
        description="Whether attendees other than the organizer can modify the event. Optional. The default is False.",
    )
    guests_can_see_other_guests: Optional[bool] = Field(
        None,
        description="Whether attendees other than the organizer can see who the event's attendees are. Optional. The default is True.",
    )
    id: Optional[str] = Field(
        None,
        pattern=r"^[a-v0-9]+$",
        min_length=5,
        max_length=1024,
        description=(
            "Opaque identifier of the event. When creating new single or recurring events, you can specify their IDs. "
            "Provided IDs must follow these rules: "
            "characters allowed in the ID are those used in base32hex encoding, i.e. lowercase letters a-v and digits 0-9, see section 3.1.2 in RFC2938; "
            "the length of the ID must be between 5 and 1024 characters; "
            "the ID must be unique per calendar. "
            "Due to the globally distributed nature of the system, we cannot guarantee that ID collisions will be detected at event creation time. "
            "To minimize the risk of collisions we recommend using an established UUID algorithm such as one described in RFC4122. "
            "If you do not specify an ID, it will be automatically generated by the server."
        ),
    )
    location: Optional[str] = Field(
        None,
        description="Geographic location of the event as free-form text. Optional.",
    )
    sequence: Optional[int] = Field(None, description="Sequence number as per iCalendar.")
    status: Optional[Literal["confirmed", "tentative", "cancelled"]] = Field(
        None,
        description=(
            "Status of the event. Optional. Possible values are: "
            '"confirmed" - The event is confirmed. This is the default status. '
            '"tentative" - The event is tentatively confirmed. '
            '"cancelled" - The event is cancelled (deleted). The list method returns cancelled events only on incremental sync (when syncToken or updatedMin are specified) or if the showDeleted flag is set to true.'
        ),
    )
    summary: Optional[str] = Field(None, description="Title of the event.")
    transparency: Optional[Literal["opaque", "transparent"]] = Field(
        None,
        description=(
            "Whether the event blocks time on the calendar. Optional. Possible values are: "
            '"opaque" - Default value. The event does block time on the calendar. This is equivalent to setting Show me as to Busy in the Calendar UI. '
            '"transparent" - The event does not block time on the calendar. This is equivalent to setting Show me as to Available in the Calendar UI.'
        ),
    )
    visibility: Optional[
        Literal["default", "public", "private", "confidential"]
    ] = Field(
        None,
        description=(
            "Visibility of the event. Optional. Possible values are: "
            '"default" - Uses the default visibility for events on the calendar. This is the default value. '
            '"public" - The event is public and event details are visible to all readers of the calendar. '
            '"private" - The event is private and only event attendees may view event details. '
            '"confidential" - The event is private. This value is provided for compatibility reasons.'
        ),
    )

    # Writable complex fields
    attachments: Optional[List[Attachment]] = Field(
        None,
        description=(
            "File attachments for the event. In order to modify attachments the supportsAttachments request parameter should be set to true. "
            "There can be at most 25 attachments per event."
        ),
    )
    attendees: Optional[List[Attendee]] = Field(
        None,
        description=(
            "The attendees of the event. See the Events with attendees guide for more information on scheduling events with other calendar users. "
            "Service accounts need to use domain-wide delegation of authority to populate the attendee list."
        ),
    )
    birthday_properties: Optional[BirthdayProperties] = Field(
        None,
        description='Birthday or special event data. Used if eventType is "birthday". Immutable.',
    )
    conference_data: Optional[ConferenceData] = Field(
        None,
        description=(
            "The conference-related information, such as details of a Google Meet conference. "
            "To create new conference details use the createRequest field. "
            "To persist your changes, remember to set the conferenceDataVersion request parameter to 1 for all event modification requests."
        ),
    )
    extended_properties: Optional[ExtendedProperties] = Field(
        None,
        description="Extended properties of the event.",
    )
    focus_time_properties: Optional[FocusTimeProperties] = Field(
        None,
        description="Focus Time event data. Used if eventType is focusTime.",
    )
    gadget: Optional[EventGadget] = Field(
        None,
        description="A gadget that extends this event. Gadgets are deprecated; this structure is instead only used for returning birthday calendar metadata.",
    )
    original_start_time: Optional[EventDateTime] = Field(
        None,
        description=(
            "For an instance of a recurring event, this is the time at which this event would start according to the recurrence data in the recurring event identified by recurringEventId. "
            "It uniquely identifies the instance within the recurring event series even if the instance was moved to a different time. Immutable."
        ),
    )
    out_of_office_properties: Optional[OutOfOfficeProperties] = Field(
        None,
        description="Out of office event data. Used if eventType is outOfOffice.",
    )
    recurrence: Optional[List[str]] = Field(
        None,
        description=(
            "List of RRULE, EXRULE, RDATE and EXDATE lines for a recurring event, as specified in RFC5545. "
            "Note that DTSTART and DTEND lines are not allowed in this field; event start and end times are specified in the start and end fields. "
            "This field is omitted for single events or instances of recurring events."
        ),
    )
    reminders: Optional[Reminders] = Field(
        None,
        description="Information about the event's reminders for the authenticated user. Note that changing reminders does not also change the updated property of the enclosing event.",
    )
    source: Optional[Source] = Field(
        None,
        description="Source from which the event was created. For example, a web page, an email message or any document identifiable by an URL with HTTP or HTTPS scheme. Can only be seen or modified by the creator of the event.",
    )
    working_location_properties: Optional[WorkingLocationProperties] = Field(
        None,
        description="Working location event data.",
    )

    # Read-only fields
    attendees_omitted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether attendees may have been omitted from the event's representation. When retrieving an event, this may be due to a restriction specified by the maxAttendee query parameter. "
                "When updating an event, this can be used to only update the participant's response. Optional. The default is False."
            ),
        ),
        Mode("response_only"),
    ]
    created: Annotated[
        Optional[datetime],
        Field(None, description="Creation time of the event (as a RFC3339 timestamp). Read-only."),
        Mode("response_only"),
    ]
    creator: Annotated[
        Optional[Creator],
        Field(None, description="The creator of the event. Read-only."),
        Mode("response_only"),
    ]
    end_time_unspecified: Annotated[
        Optional[bool],
        Field(
            None,
            description="Whether the end time is actually unspecified. An end time is still provided for compatibility reasons, even if this attribute is set to True. The default is False.",
        ),
        Mode("response_only"),
    ]
    etag: Annotated[
        Optional[str],
        Field(None, description="ETag of the resource."),
        Mode("response_only"),
    ]
    hangout_link: Annotated[
        Optional[str],
        Field(None, description="An absolute link to the Google Hangout associated with this event. Read-only."),
        Mode("response_only"),
    ]
    html_link: Annotated[
        Optional[str],
        Field(None, description="An absolute link to this event in the Google Calendar Web UI. Read-only."),
        Mode("response_only"),
    ]
    # Visible only to `events_import`, which is the one endpoint that requires it.
    # `response_only` was wrong here and hid it from that endpoint too, leaving the
    # model unable to supply a field the API mandates; plain writability is wrong
    # the other way, since insert documents id and iCalUID as alternatives and
    # offering both invites sending both. A custom mode is how visibility follows
    # the operation rather than the resource.
    i_cal_uid: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Event unique identifier as defined in RFC5545. It is used to uniquely identify events across calendaring systems and must be supplied when importing events via the import method. "
                "Note that the iCalUID and the id are not identical and only one of them should be supplied at event creation time."
            ),
        ),
        # snake_to_camel would send `iCalUid`, which Google ignores.
        WireName("iCalUID"),
        Mode("import"),
    ]
    kind: Annotated[
        Optional[Literal["calendar#event"]],
        Field(None, description='Type of the resource ("calendar#event").'),
        Mode("response_only"),
    ]
    locked: Annotated[
        Optional[bool],
        Field(
            None,
            description='Whether this is a locked event copy where no changes can be made to the main event fields "summary", "description", "location", "start", "end" or "recurrence". The default is False. Read-Only.',
        ),
        Mode("response_only"),
    ]
    organizer: Annotated[
        Optional[Organizer],
        Field(
            None,
            description=(
                "The organizer of the event. If the organizer is also an attendee, this is indicated with a separate entry in attendees with the organizer field set to True. "
                "To change the organizer, use the move operation. Read-only, except when importing an event."
            ),
        ),
        Mode("response_only"),
    ]
    private_copy: Annotated[
        Optional[bool],
        Field(
            None,
            description="If set to True, Event propagation is disabled. Note that it is not the same thing as Private event properties. Optional. Immutable. The default is False.",
        ),
        Mode("response_only"),
    ]
    recurring_event_id: Annotated[
        Optional[str],
        Field(None, description="For an instance of a recurring event, this is the id of the recurring event to which this instance belongs. Immutable."),
        Mode("response_only"),
    ]
    updated: Annotated[
        Optional[datetime],
        Field(
            None,
            description="Last modification time of the main event data (as a RFC3339 timestamp). Updating event reminders will not cause this to change. Read-only.",
        ),
        Mode("response_only"),
    ]
