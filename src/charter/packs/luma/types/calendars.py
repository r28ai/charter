# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma calendars operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import Field

from charter.packs.luma.types.common import (
    CalendarsContactsListSortColumn,
    CalendarsEventsAddBody,
    Color,
    Discount,
    EventDefaults,
    EventsGuestsSendInvitesGuest,
    LaunchStatus,
    Location,
    MembershipStatus,
    SortDirection,
)
from charter.types import Body, Gloss, Mode, Query
from charter.types.model import PackModel

__all__ = [
    "CalendarsGetRequest",
    "CalendarsEventsListRequest",
    "CalendarsContactTagsListRequest",
    "CalendarsEventTagsListRequest",
    "CalendarsAdminsListRequest",
    "CalendarsEventsLookupRequest",
    "CalendarsContactsListRequest",
    "CalendarsCouponsListRequest",
    "CalendarsCouponsCreateRequest",
    "CalendarsCouponsUpdateRequest",
    "CalendarsContactsImportRequest",
    "CalendarsContactsBlockRequest",
    "CalendarsContactsRemoveRequest",
    "CalendarsContactsRestoreRequest",
    "CalendarsContactTagsCreateRequest",
    "CalendarsContactTagsUpdateRequest",
    "CalendarsContactTagsDeleteRequest",
    "CalendarsContactTagsApplyRequest",
    "CalendarsContactTagsUnapplyRequest",
    "CalendarsEventTagsCreateRequest",
    "CalendarsEventTagsUpdateRequest",
    "CalendarsEventTagsDeleteRequest",
    "CalendarsEventTagsApplyRequest",
    "CalendarsEventTagsUnapplyRequest",
    "CalendarsEventsAddRequest",
    "CalendarsEventsApproveRequest",
    "CalendarsEventsRejectRequest",
    "CalendarsAdminsAddRequest",
    "CalendarsUpdateRequest",
]


class CalendarsGetRequest(PackModel):
    """Get Calendar

    Get information about the calendar.

    API Reference: https://docs.luma.com/reference/get_v1-calendars-get
    """


class CalendarsEventsListRequest(PackModel):
    """List Events

    Every event and API key on Luma is managed by a [Luma
    Calendar](https://help.luma.com/p/luma-calendar-overview). By default this lists the
    events your Calendar manages.

    Each event includes an `access` field. Pass `access=manage&access=view` to also return
    events that are listed on the Calendar but managed elsewhere — those come back with
    `access: "view"`, their location obfuscated to city level, and host-only fields like
    `meeting_url`, `registration_questions`, and `feedback_email` omitted. Private events
    the Calendar doesn't manage are never returned.

    API Reference: https://docs.luma.com/reference/get_v1-calendars-events-list
    """

    before: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Query(),
    ]
    after: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Query(),
    ]
    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]
    platforms: Annotated[
        Optional[List[Literal["luma", "external"]]],
        Field(
            None,
            description=(
                "Which event platforms to include. Defaults to `luma` for backwards "
                "compatibility. Pass as repeated query params, e.g. "
                "`?platforms=luma&platforms=external`."
            ),
        ),
        Query(),
    ]
    sort_column: Annotated[
        Optional[Literal["start_at"]],
        Field(None),
        Query(),
        Gloss("The column to sort events by."),
    ]
    sort_direction: Annotated[
        Optional[SortDirection],
        Field(None),
        Query(),
        Gloss("Sort order. The `nulls last` variants put entries with no value at the end."),
    ]
    status: Annotated[
        Optional[Literal["approved", "pending"]],
        Field(None, description="Filter by calendar submission status. Defaults to `approved`."),
        Query(),
    ]
    access: Annotated[
        Optional[List[Literal["manage", "view"]]],
        Field(
            None,
            description=(
                "Which access values to include (`manage`, `view`). Defaults to "
                "`manage`, returning only events the Calendar manages. Pass as repeated"
                " query params, e.g. `?access=manage&access=view`. Include `view` to "
                "also return events that are listed on the Calendar but managed "
                'elsewhere — those entries come back with `access: "view"`, their '
                "location obfuscated to city level, and host-only fields like "
                "`meeting_url`, `registration_questions`, and `feedback_email` omitted."
            ),
        ),
        Query(),
    ]


class CalendarsContactTagsListRequest(PackModel):
    """List Contact Tags

    API Reference: https://docs.luma.com/reference/get_v1-calendars-contact-tags-list
    """


class CalendarsEventTagsListRequest(PackModel):
    """List Event Tags

    API Reference: https://docs.luma.com/reference/get_v1-calendars-event-tags-list
    """


class CalendarsAdminsListRequest(PackModel):
    """List Calendar Admins

    List all admins for the calendar.

    API Reference: https://docs.luma.com/reference/get_v1-calendars-admins-list
    """


class CalendarsEventsLookupRequest(PackModel):
    """Lookup Event

    See if an event already exists on the calendar. This is useful when figuring out if you
    want to submit an event to the calendar.

    API Reference: https://docs.luma.com/reference/get_v1-calendars-events-lookup
    """

    platform: Annotated[
        Optional[Literal["external", "luma"]],
        Field(None),
        Query(),
        Gloss("`luma` to look the event up by `event_id`, `external` to look it up by `url`."),
    ]
    url: Annotated[
        Optional[str],
        Field(None),
        Query(),
        Gloss("The event's URL, for an event hosted outside Luma (`platform: external`)."),
    ]
    event_id: Annotated[
        Optional[str],
        Field(None, description="Event ID, this usually starts with evt-"),
        Query(),
    ]
    event_api_id: Annotated[
        Optional[str],
        Field(None, description="Use `event_id` instead."),
        Mode("disabled"),
        Query(),
    ]


class CalendarsContactsListRequest(PackModel):
    """List Contacts

    API Reference: https://docs.luma.com/reference/get_v1-calendars-contacts-list
    """

    query: Annotated[
        Optional[str],
        Field(None, description="Search over names and emails."),
        Query(),
    ]
    tags: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Tag names or tag IDs to filter contacts. Pass as repeated query "
                "params, e.g. `?tags=vip&tags=sponsor`. Returns contacts who have any "
                "of the specified tags."
            ),
        ),
        Query(),
    ]
    calendar_membership_tier_id: Annotated[
        Optional[str],
        Field(None),
        Query(),
        Gloss("Only contacts in this membership tier."),
    ]
    membership_status: Annotated[
        Optional[MembershipStatus],
        Field(
            None,
            description="This is relevant for Calendar Memberships but not relevant otherwise.",
        ),
        Query(),
    ]
    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]
    sort_column: Annotated[
        Optional[CalendarsContactsListSortColumn],
        Field(None),
        Query(),
        Gloss("The column to sort contacts by."),
    ]
    sort_direction: Annotated[
        Optional[SortDirection],
        Field(None),
        Query(),
        Gloss("Sort order. The `nulls last` variants put entries with no value at the end."),
    ]


class CalendarsCouponsListRequest(PackModel):
    """List Calendar Coupons

    List all coupons that have been created for a calendar.

    API Reference: https://docs.luma.com/reference/get_v1-calendars-coupons-list
    """

    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]


class CalendarsCouponsCreateRequest(PackModel):
    """Create Coupon

    Create a coupon that can be applied to any event that is managed by the calendar. Be
    careful not to have the same code on an event and on the calendar.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-coupons-create
    """

    code: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=20,
            description=(
                "This is the code that the user will enter on the event page. It is not"
                " case sensitive. Maximum 20 characters."
            ),
        ),
        Body(),
    ]
    remaining_count: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=1000000,
            description=(
                "Number of times the coupon can be used. Set to 1000000 for unlimited uses."
            ),
        ),
        Body(),
    ]
    valid_start_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    valid_end_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    discount: Annotated[
        Discount,
        Field(...),
        Body(),
        Gloss(
            "A percentage off (`discount_type: percent`) or a fixed amount off in a "
            "currency (`discount_type: amount`)."
        ),
    ]


class CalendarsCouponsUpdateRequest(PackModel):
    """Update Coupon

    API Reference: https://docs.luma.com/reference/post_v1-calendars-coupons-update
    """

    code: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("The coupon's code, which is how this call finds the coupon to change."),
    ]
    remaining_count: Annotated[
        Optional[int],
        Field(None, ge=-9007199254740991, le=9007199254740991),
        Body(),
        Gloss("Number of times the coupon can still be used. Set to 1000000 for unlimited uses."),
    ]
    valid_start_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    valid_end_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]


class CalendarsContactsImportRequest(PackModel):
    """Import Contacts

    Import contacts to your calendar to easily invite them to events and send them
    newsletters.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contacts-import
    """

    contacts: Annotated[
        List[EventsGuestsSendInvitesGuest],
        Field(
            ...,
            description=(
                "Information about the contacts you want to import. You can include a "
                "name and email. Note that we will not set the name of a user once it "
                "has already been set."
            ),
        ),
        Body(),
    ]
    tags: Annotated[
        Optional[List[str]],
        Field(None, description="Tag IDs or tag names to apply to the contacts."),
        Body(),
    ]


class CalendarsContactsBlockRequest(PackModel):
    """Block Contact

    Block a contact so they can’t follow your calendar or join its events. They stop
    receiving your invites and newsletters until you restore them.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contacts-block
    """

    contact_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Contact ID (the `id` from contacts/list, usually starts with usr-). "
                "Provide this or email."
            ),
        ),
        Body(),
    ]
    email: Annotated[
        Optional[str],
        Field(None, description="Email of the contact. Provide this or contact_id."),
        Body(),
    ]


class CalendarsContactsRemoveRequest(PackModel):
    """Remove Contact

    Remove a contact from your calendar. They stop receiving your invites and newsletters
    but can follow again on their own later.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contacts-remove
    """

    contact_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Contact ID (the `id` from contacts/list, usually starts with usr-). "
                "Provide this or email."
            ),
        ),
        Body(),
    ]
    email: Annotated[
        Optional[str],
        Field(None, description="Email of the contact. Provide this or contact_id."),
        Body(),
    ]


class CalendarsContactsRestoreRequest(PackModel):
    """Restore Contact

    Restore a blocked or removed contact, returning them to your active contacts.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contacts-restore
    """

    contact_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Contact ID (the `id` from contacts/list, usually starts with usr-). "
                "Provide this or email."
            ),
        ),
        Body(),
    ]
    email: Annotated[
        Optional[str],
        Field(None, description="Email of the contact. Provide this or contact_id."),
        Body(),
    ]


class CalendarsContactTagsCreateRequest(PackModel):
    """Create Contact Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contact-tags-create
    """

    name: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("The tag's name."),
    ]
    color: Annotated[
        Optional[Color],
        Field(None),
        Body(),
        Gloss("The tag's color."),
    ]


class CalendarsContactTagsUpdateRequest(PackModel):
    """Update Contact Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contact-tags-update
    """

    tag_id: Annotated[
        str,
        Field(..., description="Tag ID, this usually starts with tag-"),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(None),
        Body(),
        Gloss("The tag's new name. Omit to keep it."),
    ]
    color: Annotated[
        Optional[Color],
        Field(None),
        Body(),
        Gloss("The tag's new color. Omit to keep it."),
    ]


class CalendarsContactTagsDeleteRequest(PackModel):
    """Delete Contact Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contact-tags-delete
    """

    tag_id: Annotated[
        str,
        Field(..., description="Tag ID, this usually starts with tag-"),
        Body(envelop=True),
    ]


class CalendarsContactTagsApplyRequest(PackModel):
    """Apply Contact Tag

    Apply a tag to existing calendar contacts. This will not create new contacts.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contact-tags-apply
    """

    tag: Annotated[
        str,
        Field(..., description="Tag ID (e.g., 'tag-123') or tag name"),
        Body(),
    ]
    user_ids: Annotated[
        Optional[List[str]],
        Field(None, description="Array of user IDs to apply the tag to"),
        Body(),
    ]
    emails: Annotated[
        Optional[List[str]],
        Field(None, description="Array of email addresses to apply the tag to"),
        Body(),
    ]


class CalendarsContactTagsUnapplyRequest(PackModel):
    """Unapply Contact Tag

    Unapply a tag from calendar contacts. Only affects existing contacts.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-contact-tags-unapply
    """

    tag: Annotated[
        str,
        Field(..., description="Tag ID (e.g., 'tag-123') or tag name"),
        Body(),
    ]
    user_ids: Annotated[
        Optional[List[str]],
        Field(None, description="Array of user IDs to remove the tag from"),
        Body(),
    ]
    emails: Annotated[
        Optional[List[str]],
        Field(None, description="Array of email addresses to remove the tag from"),
        Body(),
    ]


class CalendarsEventTagsCreateRequest(PackModel):
    """Create Event Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-event-tags-create
    """

    name: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("The tag's name."),
    ]
    color: Annotated[
        Optional[Color],
        Field(None),
        Body(),
        Gloss("The tag's color."),
    ]


class CalendarsEventTagsUpdateRequest(PackModel):
    """Update Event Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-event-tags-update
    """

    tag_id: Annotated[
        str,
        Field(..., description="Tag ID, this usually starts with tag-"),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(None),
        Body(),
        Gloss("The tag's new name. Omit to keep it."),
    ]
    color: Annotated[
        Optional[Color],
        Field(None),
        Body(),
        Gloss("The tag's new color. Omit to keep it."),
    ]


class CalendarsEventTagsDeleteRequest(PackModel):
    """Delete Event Tag

    API Reference: https://docs.luma.com/reference/post_v1-calendars-event-tags-delete
    """

    tag_id: Annotated[
        str,
        Field(..., description="Tag ID, this usually starts with tag-"),
        Body(envelop=True),
    ]


class CalendarsEventTagsApplyRequest(PackModel):
    """Apply Event Tag

    Apply a tag to events on the calendar.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-event-tags-apply
    """

    tag: Annotated[
        str,
        Field(..., description="Tag ID (e.g., 'tag-123') or tag name"),
        Body(),
    ]
    event_ids: Annotated[
        List[str],
        Field(..., min_length=1, description="Array of event IDs to apply the tag to"),
        Body(),
    ]


class CalendarsEventTagsUnapplyRequest(PackModel):
    """Unapply Event Tag

    Unapply a tag from events on the calendar.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-event-tags-unapply
    """

    tag: Annotated[
        str,
        Field(..., description="Tag ID (e.g., 'tag-123') or tag name"),
        Body(),
    ]
    event_ids: Annotated[
        List[str],
        Field(..., min_length=1, description="Array of event IDs to remove the tag from"),
        Body(),
    ]


class CalendarsEventsAddRequest(PackModel):
    """Add Event

    Add or submit an existing event (on Luma or on an external platform) to the Luma
    calendar. By default, events added by a calendar manager are approved immediately. Use
    `submission_mode: "pending"` to keep the submission pending.

    On calendars with `require-manage-access`, submitting a Luma event you manage can also
    grant the target calendar manage access once the submission is approved.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-events-add
    """

    body: Annotated[
        CalendarsEventsAddBody,
        Field(...),
        Body(),
        Gloss(
            "The event to add: a Luma event by `event_id` (`platform: luma`), or one "
            "hosted elsewhere by its `url`, name and time (`platform: external`)."
        ),
    ]


class CalendarsEventsApproveRequest(PackModel):
    """Approve Event

    Approve a pending event submission on your calendar. The event becomes visible on the
    calendar and the submitter is notified.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-events-approve
    """

    calendar_event_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Calendar event ID (starts with `calev-`). You can also pass the Luma "
                "event ID (starts with `evt-`) — we'll resolve it to the active "
                "submission on your calendar."
            ),
        ),
        Body(envelop=True),
    ]


class CalendarsEventsRejectRequest(PackModel):
    """Reject Event

    Reject a pending event submission on your calendar. The submitter is only emailed when
    you pass `notify_submitter: true` or a `message`.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-events-reject
    """

    calendar_event_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Calendar event ID (starts with `calev-`). You can also pass the Luma "
                "event ID (starts with `evt-`) — we'll resolve it to the active "
                "submission on your calendar."
            ),
        ),
        Body(),
    ]
    message: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Optional message to email the submitter explaining the rejection. "
                "Passing a message notifies the submitter."
            ),
        ),
        Body(),
    ]
    notify_submitter: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Email the submitter that their event wasn’t included. Defaults to "
                "`false`, unless you pass a `message`."
            ),
        ),
        Body(),
    ]


class CalendarsAdminsAddRequest(PackModel):
    """Add Calendar Admins

    Add admins to the calendar. Existing admins are skipped. On a Luma Plus calendar, adds
    that need more paid admin seats are rejected — add those admins in the Luma app, where
    the seat charge can be confirmed.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-admins-add
    """

    emails: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            max_length=20,
            description=(
                "Emails of the people to make admins. Anyone without a Luma account "
                "gets one. New admins are emailed."
            ),
        ),
        Body(envelop=True),
    ]


class CalendarsUpdateRequest(PackModel):
    """Update Calendar

    Update a calendar's settings. Only the provided fields are changed. Pass null or an
    empty string to clear the website or a social handle.

    API Reference: https://docs.luma.com/reference/post_v1-calendars-update
    """

    calendar_id: Annotated[
        str,
        Field(..., description="Calendar ID, this usually starts with cal-."),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(None, description="Name of the calendar."),
        Body(),
    ]
    launch_status: Annotated[
        Optional[LaunchStatus],
        Field(
            None,
            description=(
                "Calendar status: launched means Active; coming-soon shows a "
                "placeholder page; archived stops new follows and visitor event "
                "submissions."
            ),
        ),
        Body(),
    ]
    slug: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "URL slug for the calendar page (e.g. 'my-community' → lu.ma/my-community)."
            ),
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="Short description of the calendar."),
        Body(),
    ]
    avatar_url: Annotated[
        Optional[str],
        Field(None, description="Specify an image that has been uploaded to the Luma CDN."),
        Body(),
    ]
    tint_color: Annotated[
        Optional[str],
        Field(None, description="Tint color for the calendar in hex format (e.g. '#E3CBEF')."),
        Body(),
    ]
    website: Annotated[
        Optional[str],
        Field(None, description="Website URL. `https://` is added if missing."),
        Body(),
    ]
    instagram_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Instagram handle or profile URL (e.g. 'luma' or 'https://instagram.com/luma')."
            ),
        ),
        Body(),
    ]
    twitter_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "X (Twitter) handle or profile URL (e.g. '@luma' or 'https://x.com/luma')."
            ),
        ),
        Body(),
    ]
    youtube_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "YouTube handle or channel URL (e.g. '@luma' or 'https://youtube.com/@luma')."
            ),
        ),
        Body(),
    ]
    tiktok_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "TikTok handle or profile URL (e.g. '@luma' or 'https://tiktok.com/@luma')."
            ),
        ),
        Body(),
    ]
    linkedin_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "LinkedIn company or profile URL (e.g. 'https://linkedin.com/company/luma')."
            ),
        ),
        Body(),
    ]
    location: Annotated[
        Optional[Location],
        Field(
            None,
            description=(
                "City the calendar is based in. Use `{ type: 'lookup', query }` to "
                "search Google Maps for a city, or `{ type: 'google', place_id }` with "
                "a city's Google Places ID. The calendar's timezone and coordinate come"
                " from the city. Pass `null` to clear it."
            ),
        ),
        Body(),
    ]
    event_defaults: Annotated[
        Optional[EventDefaults],
        Field(
            None,
            description=(
                "Settings new events on this calendar start with. Only the provided "
                "fields change, and existing events aren't affected. `visibility: "
                "'members-only'` requires a membership tier on the calendar."
            ),
        ),
        Body(),
    ]
