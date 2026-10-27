# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma events operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import Field, model_validator

from charter.packs.luma.types.common import (
    AccessLevel,
    ApprovalStatus,
    BlastRecipientGroupInput,
    Discount,
    EventsGuestsAddApprovalStatus,
    EventsGuestsAddGuest,
    EventsGuestsSendInvitesGuest,
    EventTaxConfig,
    FeedbackEmail,
    Font,
    GeoAddressJson,
    RegistrationQuestion,
    SortColumn,
    SortDirection,
    Status,
    Theme,
    Ticket,
    TicketsToAddItem,
    TicketTypeCreateInput,
    Visibility,
)
from charter.types import Body, ConflictsWith, Gloss, Mode, Query
from charter.types.model import PackModel

__all__ = [
    "EventsGetRequest",
    "EventsGuestsGetRequest",
    "EventsGuestsListRequest",
    "EventsCouponsListRequest",
    "EventsTicketTypesListRequest",
    "EventsTicketTypesGetRequest",
    "EventsBlastsListRequest",
    "EventsBlastsGetRequest",
    "EventsCreateRequest",
    "EventsUpdateRequest",
    "EventsGuestsUpdateStatusRequest",
    "EventsGuestsUpdateTicketsRequest",
    "EventsGuestsSendInvitesRequest",
    "EventsGuestsAddRequest",
    "EventsHostsAddRequest",
    "EventsHostsUpdateRequest",
    "EventsHostsRemoveRequest",
    "EventsCouponsCreateRequest",
    "EventsCouponsUpdateRequest",
    "EventsTicketTypesCreateRequest",
    "EventsTicketTypesUpdateRequest",
    "EventsTicketTypesDeleteRequest",
    "EventsBlastsCreateRequest",
    "EventsBlastsUpdateRequest",
    "EventsBlastsDeleteRequest",
    "EventsCancelRequestRequest",
    "EventsCancelRequest",
]


class EventsGetRequest(PackModel):
    """Get Event

    Return details about an event. For events you manage (`access: "manage"`), this includes
    full detail, host contact info, and a breakdown of guest counts by status. For public
    events you don’t manage (`access: "view"`), only the fields a regular event-page visitor
    could see are returned.

    API Reference: https://docs.luma.com/reference/get_v1-events-get
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Query(),
    ]


class EventsGuestsGetRequest(PackModel):
    """Get Guest

    Get detailed information for an event guest by looking them up by their ID. This
    supports looking them up by different parameters.

    This response includes `event_ticket_orders`, which includes `coupon_info` when a coupon
    was applied.

    API Reference: https://docs.luma.com/reference/get_v1-events-guests-get
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Query(),
    ]
    id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Guest identifier — the guest ID (gst-), a ticket key, a guest key "
                "(g-), or the user's email."
            ),
        ),
        Query(),
    ]


class EventsGuestsListRequest(PackModel):
    """List Guests

    Get list of guests who have registered or been invited to an event.

    This list response includes guest summaries and `event_tickets`, but not order-level
    details like `event_ticket_orders`. Use `/v1/events/guests/get` when you need detailed
    ticket order data for a specific guest.

    API Reference: https://docs.luma.com/reference/get_v1-events-guests-list
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Query(),
    ]
    approval_status: Annotated[
        Optional[ApprovalStatus],
        Field(None),
        Query(),
        Gloss("Only guests with this status. Omit for every status."),
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
        Optional[SortColumn],
        Field(None),
        Query(),
        Gloss("The column to sort guests by."),
    ]
    sort_direction: Annotated[
        Optional[SortDirection],
        Field(None),
        Query(),
        Gloss("Sort order. The `nulls last` variants put entries with no value at the end."),
    ]


class EventsCouponsListRequest(PackModel):
    """List Event Coupons

    List all coupons that have been created for an event.

    API Reference: https://docs.luma.com/reference/get_v1-events-coupons-list
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
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


class EventsTicketTypesListRequest(PackModel):
    """List Ticket Types

    List all ticket types for an event

    API Reference: https://docs.luma.com/reference/get_v1-events-ticket-types-list
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Query(),
    ]
    include_hidden: Annotated[
        Optional[str],
        Field(None, description="Include hidden ticket types"),
        Query(),
    ]


class EventsTicketTypesGetRequest(PackModel):
    """Get Ticket Type

    Get a single ticket type by ID

    API Reference: https://docs.luma.com/reference/get_v1-events-ticket-types-get
    """

    event_ticket_type_id: Annotated[
        str,
        Field(..., description="Ticket type ID, this usually starts with ttype-"),
        Query(),
    ]


class EventsBlastsListRequest(PackModel):
    """List Blasts

    List the blasts (emails to guests) on an event, newest first. Sent blasts include
    `recipient_count` and `email_open_count`.

    API Reference: https://docs.luma.com/reference/get_v1-events-blasts-list
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Query(),
    ]


class EventsBlastsGetRequest(PackModel):
    """Get Blast

    Get a blast by ID.

    API Reference: https://docs.luma.com/reference/get_v1-events-blasts-get
    """

    blast_id: Annotated[
        str,
        Field(..., description="Blast ID, this usually starts with ep-"),
        Query(),
    ]


class EventsCreateRequest(PackModel):
    """Create Event

    API Reference: https://docs.luma.com/reference/post_v1-events-create
    """

    confirmation_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the confirmation email, sent when a registration is "
                "confirmed, including when you approve a guest. Supports Markdown "
                "formatting. Leave this field out to keep the current message or use "
                "the default email for a new event. To remove your message, use an "
                'empty string (`""`). Guests will still receive the standard email.'
            ),
        ),
        Body(),
    ]
    pending_approval_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the email sent to guests awaiting approval or joining "
                "the waitlist. Supports Markdown formatting. Leave this field out to "
                "keep the current message or use the default email for a new event. To "
                'remove your message, use an empty string (`""`). Guests will still '
                "receive the standard email."
            ),
        ),
        Body(),
    ]
    declined_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the email sent when you decline a guest's "
                "registration. Supports Markdown formatting. Leave this field out to "
                "keep the current message or use the default email for a new event. To "
                'remove your message, use an empty string (`""`). Guests will still '
                "receive the standard email."
            ),
        ),
        Body(),
    ]
    can_register_for_multiple_tickets: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether a guest can register for multiple tickets in one registration "
                "(Group Registration). When `true`, each ticket counts toward "
                "`max_capacity`."
            ),
        ),
        Body(),
    ]
    cover_url: Annotated[
        Optional[str],
        Field(
            None,
            pattern=r"^https:\/\/images\.lumacdn\.com\/.*",
            description=(
                "Specify an image that has been uploaded to the Luma CDN. You can "
                "upload an image after getting an upload URL from the Luma API, or pick"
                " one from Luma’s cover gallery with `/v1/images/search`."
            ),
        ),
        Body(),
    ]
    create_meeting: Annotated[
        Optional[Literal["zoom", "google-meet"]],
        Field(
            None,
            description=(
                "Create a new Zoom meeting or Google Meet with the Zoom or Google "
                "account the user has connected to Luma, and use its join link as the "
                "event's `meeting_url`. Fails if that account isn't connected. On "
                "update, replaces the current link; only the event's creator can create"
                " a Zoom meeting. Can't be combined with `meeting_url` or "
                "`geo_address_json`."
            ),
        ),
        Body(),
        ConflictsWith(
            "meeting_url",
            "geo_address_json",
            reason=(
                "Luma makes the join link itself. Send meeting_url instead to use your own "
                "link, or geo_address_json alone for an in-person event."
            ),
        ),
    ]
    description_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Format your text with Markdown. For images, request an upload URL from"
                " `/v1/images/create-upload-url`, upload the image, and use the "
                "returned `file_url` in `![alt](url)`. Image URLs must be hosted on "
                "images.lumacdn.com. To embed a YouTube, Vimeo, or Loom video, put its "
                "URL on a line of its own. Embedded Luma event cards aren't supported."
            ),
        ),
        Body(),
    ]
    end_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    font: Annotated[
        Optional[Font],
        Field(
            None,
            description=(
                "Font for the event name and headings on the event page. Setting a "
                "`theme` without a `font` applies the theme’s default font; pass `null`"
                " to clear the font and use the standard font. Fonts may be retired "
                "over time — a retired font stops being accepted here, and event pages "
                "still using one fall back to the standard font."
            ),
        ),
        Body(),
    ]
    geo_address_json: Annotated[
        Optional[GeoAddressJson],
        Field(
            None,
            description=(
                "In-person location. Use `{ type: 'manual', address }` with a free-text"
                " address, `{ type: 'google', place_id }` with a Google Places ID, or "
                "`{ type: 'lookup', query }` to search Google Maps and use the top "
                "result. Leave out for online events."
            ),
        ),
        Body(),
    ]
    location_visibility: Annotated[
        Optional[Literal["public", "guests-only"]],
        Field(
            None,
            description=(
                "Set to `guests-only` to hide the precise location from people who "
                "haven't been approved — they'll see only the city and approximate "
                "area. Defaults to `public`."
            ),
        ),
        Body(),
    ]
    max_capacity: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "Once an event hits the max capacity, the event will be marked as sold "
                "out and registration will automatically be closed.\n"
                "\n"
                "If the event has a waitlist (`waitlist_status` is `enabled`), new "
                "registrations join the waitlist instead of being closed.\n"
                "\n"
                "If `can_register_for_multiple_tickets` is `true`, each ticket will "
                "count towards the max capacity."
            ),
        ),
        Body(),
    ]
    meeting_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Join link for online events (Zoom, Google Meet, etc.). To have Luma "
                "create one, use `create_meeting` instead. Can't be combined with "
                "`geo_address_json`."
            ),
        ),
        Body(),
        ConflictsWith(
            "geo_address_json", reason="An event has a join link or an in-person address, not both."
        ),
    ]
    name: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("The event's name."),
    ]
    name_requirement: Annotated[
        Optional[Literal["full-name", "first-last"]],
        Field(
            None,
            description=(
                "How to collect guest names: `full-name` uses a single field; "
                "`first-last` uses separate first and last name fields. Enabling "
                "`first-last` requires Luma Plus on the event's calendar."
            ),
        ),
        Body(),
    ]
    phone_number_requirement: Annotated[
        Optional[Literal["optional", "required"]],
        Field(None),
        Body(),
        Gloss("Whether registration collects a phone number, as optional or required."),
    ]
    registration_open: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to accept registrations. Set to `false` to close registration "
                "so new guests can't sign up. Defaults to `true`."
            ),
        ),
        Body(),
    ]
    registration_questions: Annotated[
        Optional[List[RegistrationQuestion]],
        Field(None),
        Body(),
        Gloss(
            "Questions guests answer when they register. Each names its `question_type`"
            " and the fields that type takes."
        ),
    ]
    reminders_disabled: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "By default, Luma will send reminders before the event. Turn off if "
                "you'd like more control over event communications."
            ),
        ),
        Body(),
    ]
    feedback_email: Annotated[
        Optional[FeedbackEmail],
        Field(
            None,
            description=(
                "Settings for the post-event feedback email sent to guests. If not "
                "specified on create, inherits from calendar defaults."
            ),
        ),
        Body(),
    ]
    show_guest_list: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "When the guest list is shown, approved guests will be able to see who "
                "else is going to the event."
            ),
        ),
        Body(),
    ]
    slug: Annotated[
        Optional[str],
        Field(
            None,
            min_length=3,
            max_length=50,
            description=(
                "The URL slug for the event. If the slug is `aloha`, the URL will be "
                "`https://luma.com/aloha`. If the slug is not available, the event "
                "creation will fail.\n"
                "\n"
                "You can use `/v1/entities/lookup` to check if a slug is available."
            ),
        ),
        Body(),
    ]
    start_at: Annotated[
        str,
        Field(..., description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    theme: Annotated[
        Optional[Theme],
        Field(
            None,
            description=(
                "Theme for the event page. Themes may be retired over time — a retired "
                "theme stops being accepted here, and event pages still using one fall "
                "back to `standard`. Setting a theme also applies the theme’s default "
                "font unless you pass `font`."
            ),
        ),
        Body(),
    ]
    timezone: Annotated[
        str,
        Field(
            ...,
            description=(
                "IANA Timezone, e.g. America/New_York. "
                "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
            ),
        ),
        Body(),
    ]
    tint_color: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Accent color for the event page, as a 3 or 6-digit hex code like "
                "`#bb2dc7`. We adjust the shade as needed so text and buttons stay "
                "accessible against the background."
            ),
        ),
        Body(),
    ]
    visibility: Annotated[
        Optional[Visibility],
        Field(None),
        Body(),
        Gloss("Who can find and view the event."),
    ]
    waitlist_status: Annotated[
        Optional[Literal["disabled", "enabled"]],
        Field(
            None,
            description=(
                "`enabled` if the event has a waitlist. New registrations join the "
                "waitlist once the event reaches capacity."
            ),
        ),
        Body(),
    ]
    ticket_types: Annotated[
        Optional[List[TicketTypeCreateInput]],
        Field(
            None,
            min_length=1,
            max_length=200,
            description=(
                "Ticket types to create the event with. When provided, these replace "
                "the default ticket — the event is created with exactly these ticket "
                "types. When omitted, the event gets a single free ticket named "
                "`Standard`. Paid ticket types require the calendar to have a connected"
                " Stripe account. To change ticket types after creation, use the ticket"
                " type endpoints."
            ),
        ),
        Body(),
    ]


class EventsUpdateRequest(PackModel):
    """Update Event

    API Reference: https://docs.luma.com/reference/post_v1-events-update
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    suppress_email: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "If true, Luma will not email guests when updating the event name, "
                "time, or location. Guests still get a push notification for a changed "
                "time or location."
            ),
        ),
        Body(),
    ]
    suppress_notifications: Annotated[
        Optional[bool],
        Field(None, description="Use `suppress_email` instead."),
        Mode("disabled"),
        Body(),
    ]
    tax_config: Annotated[
        Optional[EventTaxConfig],
        Field(
            None,
            description=(
                "Tax added on top of ticket prices for this event only, overriding the "
                "calendar’s tax setting. Pass `null` to go back to the calendar’s "
                "setting. Requires Luma Pro on the event’s calendar. Only affects new "
                "purchases."
            ),
        ),
        Body(),
    ]
    confirmation_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the confirmation email, sent when a registration is "
                "confirmed, including when you approve a guest. Supports Markdown "
                "formatting. Leave this field out to keep the current message or use "
                "the default email for a new event. To remove your message, use an "
                'empty string (`""`). Guests will still receive the standard email.'
            ),
        ),
        Body(),
    ]
    pending_approval_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the email sent to guests awaiting approval or joining "
                "the waitlist. Supports Markdown formatting. Leave this field out to "
                "keep the current message or use the default email for a new event. To "
                'remove your message, use an empty string (`""`). Guests will still '
                "receive the standard email."
            ),
        ),
        Body(),
    ]
    declined_email_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Your message in the email sent when you decline a guest's "
                "registration. Supports Markdown formatting. Leave this field out to "
                "keep the current message or use the default email for a new event. To "
                'remove your message, use an empty string (`""`). Guests will still '
                "receive the standard email."
            ),
        ),
        Body(),
    ]
    can_register_for_multiple_tickets: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether a guest can register for multiple tickets in one registration "
                "(Group Registration). When `true`, each ticket counts toward "
                "`max_capacity`."
            ),
        ),
        Body(),
    ]
    cover_url: Annotated[
        Optional[str],
        Field(
            None,
            pattern=r"^https:\/\/images\.lumacdn\.com\/.*",
            description=(
                "Specify an image that has been uploaded to the Luma CDN. You can "
                "upload an image after getting an upload URL from the Luma API, or pick"
                " one from Luma’s cover gallery with `/v1/images/search`."
            ),
        ),
        Body(),
    ]
    create_meeting: Annotated[
        Optional[Literal["zoom", "google-meet"]],
        Field(
            None,
            description=(
                "Create a new Zoom meeting or Google Meet with the Zoom or Google "
                "account the user has connected to Luma, and use its join link as the "
                "event's `meeting_url`. Fails if that account isn't connected. On "
                "update, replaces the current link; only the event's creator can create"
                " a Zoom meeting. Can't be combined with `meeting_url` or "
                "`geo_address_json`."
            ),
        ),
        Body(),
        ConflictsWith(
            "meeting_url",
            "geo_address_json",
            reason=(
                "Luma makes the join link itself. Send meeting_url instead to use your own "
                "link, or geo_address_json alone for an in-person event."
            ),
        ),
    ]
    description_md: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Format your text with Markdown. For images, request an upload URL from"
                " `/v1/images/create-upload-url`, upload the image, and use the "
                "returned `file_url` in `![alt](url)`. Image URLs must be hosted on "
                "images.lumacdn.com. To embed a YouTube, Vimeo, or Loom video, put its "
                "URL on a line of its own. Embedded Luma event cards aren't supported."
            ),
        ),
        Body(),
    ]
    end_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    font: Annotated[
        Optional[Font],
        Field(
            None,
            description=(
                "Font for the event name and headings on the event page. Setting a "
                "`theme` without a `font` applies the theme’s default font; pass `null`"
                " to clear the font and use the standard font. Fonts may be retired "
                "over time — a retired font stops being accepted here, and event pages "
                "still using one fall back to the standard font."
            ),
        ),
        Body(),
    ]
    geo_address_json: Annotated[
        Optional[GeoAddressJson],
        Field(
            None,
            description=(
                "In-person location. Use `{ type: 'manual', address }` with a free-text"
                " address, `{ type: 'google', place_id }` with a Google Places ID, or "
                "`{ type: 'lookup', query }` to search Google Maps and use the top "
                "result. Leave out for online events."
            ),
        ),
        Body(),
    ]
    location_visibility: Annotated[
        Optional[Literal["public", "guests-only"]],
        Field(
            None,
            description=(
                "Set to `guests-only` to hide the precise location from people who "
                "haven't been approved — they'll see only the city and approximate "
                "area. Defaults to `public`."
            ),
        ),
        Body(),
    ]
    max_capacity: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "Once an event hits the max capacity, the event will be marked as sold "
                "out and registration will automatically be closed.\n"
                "\n"
                "If the event has a waitlist (`waitlist_status` is `enabled`), new "
                "registrations join the waitlist instead of being closed.\n"
                "\n"
                "If `can_register_for_multiple_tickets` is `true`, each ticket will "
                "count towards the max capacity."
            ),
        ),
        Body(),
    ]
    meeting_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Join link for online events (Zoom, Google Meet, etc.). To have Luma "
                "create one, use `create_meeting` instead. Can't be combined with "
                "`geo_address_json`."
            ),
        ),
        Body(),
        ConflictsWith(
            "geo_address_json", reason="An event has a join link or an in-person address, not both."
        ),
    ]
    name: Annotated[
        Optional[str],
        Field(None),
        Body(),
        Gloss("The event's new name. Omit to keep it."),
    ]
    name_requirement: Annotated[
        Optional[Literal["full-name", "first-last"]],
        Field(
            None,
            description=(
                "How to collect guest names: `full-name` uses a single field; "
                "`first-last` uses separate first and last name fields. Enabling "
                "`first-last` requires Luma Plus on the event's calendar."
            ),
        ),
        Body(),
    ]
    phone_number_requirement: Annotated[
        Optional[Literal["optional", "required"]],
        Field(None),
        Body(),
        Gloss("Whether registration collects a phone number, as optional or required."),
    ]
    registration_open: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to accept registrations. Set to `false` to close registration "
                "so new guests can't sign up. Defaults to `true`."
            ),
        ),
        Body(),
    ]
    registration_questions: Annotated[
        Optional[List[RegistrationQuestion]],
        Field(None),
        Body(),
        Gloss(
            "Questions guests answer when they register. Each names its `question_type`"
            " and the fields that type takes."
        ),
    ]
    reminders_disabled: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "By default, Luma will send reminders before the event. Turn off if "
                "you'd like more control over event communications."
            ),
        ),
        Body(),
    ]
    feedback_email: Annotated[
        Optional[FeedbackEmail],
        Field(
            None,
            description=(
                "Settings for the post-event feedback email sent to guests. If not "
                "specified on create, inherits from calendar defaults."
            ),
        ),
        Body(),
    ]
    show_guest_list: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "When the guest list is shown, approved guests will be able to see who "
                "else is going to the event."
            ),
        ),
        Body(),
    ]
    slug: Annotated[
        Optional[str],
        Field(
            None,
            min_length=3,
            max_length=50,
            description=(
                "The URL slug for the event. If the slug is `aloha`, the URL will be "
                "`https://luma.com/aloha`. If the slug is not available, the event "
                "creation will fail.\n"
                "\n"
                "You can use `/v1/entities/lookup` to check if a slug is available."
            ),
        ),
        Body(),
    ]
    start_at: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Body(),
    ]
    theme: Annotated[
        Optional[Theme],
        Field(
            None,
            description=(
                "Theme for the event page. Themes may be retired over time — a retired "
                "theme stops being accepted here, and event pages still using one fall "
                "back to `standard`. Setting a theme also applies the theme’s default "
                "font unless you pass `font`."
            ),
        ),
        Body(),
    ]
    timezone: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "IANA Timezone, e.g. America/New_York. "
                "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
            ),
        ),
        Body(),
    ]
    tint_color: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Accent color for the event page, as a 3 or 6-digit hex code like "
                "`#bb2dc7`. We adjust the shade as needed so text and buttons stay "
                "accessible against the background."
            ),
        ),
        Body(),
    ]
    visibility: Annotated[
        Optional[Visibility],
        Field(None),
        Body(),
        Gloss("Who can find and view the event."),
    ]
    waitlist_status: Annotated[
        Optional[Literal["disabled", "enabled"]],
        Field(
            None,
            description=(
                "`enabled` if the event has a waitlist. New registrations join the "
                "waitlist once the event reaches capacity."
            ),
        ),
        Body(),
    ]


class EventsGuestsUpdateStatusRequest(PackModel):
    """Update Guest Status

    Update a guest’s status. Set `status` to `approved` ("Going"), `declined`,
    `pending_approval`, or `waitlist`. Use `should_refund` to refund a paid guest when
    moving them out of an approved state. Use `message` to include a personal note in the
    email we send the guest. To send a soft invite that guests can accept, use
    `/v1/events/guests/send-invites` instead.

    API Reference: https://docs.luma.com/reference/post_v1-events-guests-update-status
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    guest_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Guest identifier — the guest ID (gst-), a ticket key, a guest key "
                "(g-), or the user's email."
            ),
        ),
        Body(),
    ]
    status: Annotated[
        Status,
        Field(...),
        Body(),
        Gloss('The guest\'s new status. `approved` is "Going".'),
    ]
    should_refund: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "If you are moving a guest who has paid to `declined`, `waitlist`, or "
                "`pending_approval`, should we refund their payment? Defaults to false."
            ),
        ),
        Body(),
    ]
    send_email: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Optional. Whether Luma should email the guest about the status change."
                " Defaults to true. Set to false if your integration sends its own "
                "notifications."
            ),
        ),
        Body(),
    ]
    message: Annotated[
        Optional[str],
        Field(
            None,
            max_length=200,
            description=(
                "Optional. Personal message included in the email we send the guest "
                "about the status change. Max of 200 characters. Can't be combined with"
                " `send_email: false`."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _no_message_without_email(self) -> EventsGuestsUpdateStatusRequest:
        """``message`` rides in the status email: "Can't be combined with `send_email: false`"."""
        if self.message is not None and self.send_email is False:
            raise ValueError(
                "message is included in the email Luma sends about the status change, so "
                "it cannot be combined with send_email: false. Drop message, or let Luma "
                "send the email."
            )
        return self


class EventsGuestsUpdateTicketsRequest(PackModel):
    """Update Guest Tickets

    Add or remove tickets from an existing guest. Added tickets are complimentary. Removed
    tickets are invalidated and, if `should_refund` is set, refunded for what the guest paid
    for them; otherwise no money moves. You can’t change tickets for guests with pending
    payment holds. Administrative ticket changes can exceed event or ticket-type capacity.

    API Reference: https://docs.luma.com/reference/post_v1-events-guests-update-tickets
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    guest_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Guest identifier — the guest ID (gst-), a ticket key, a guest key "
                "(g-), or the user's email."
            ),
        ),
        Body(),
    ]
    ticket_ids_to_remove: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Existing ticket IDs to invalidate. At least one valid ticket must "
                "remain on the guest. Pass `should_refund` to refund the removed "
                "tickets."
            ),
        ),
        Body(),
        Gloss("Defaults to `[]` when omitted."),
    ]
    should_refund: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Optional. Refund each removed paid ticket for what the guest paid for "
                "it. The guest stays registered with their remaining tickets. The "
                "refund is limited to what's left on the order beyond the tickets the "
                "guest keeps, so a partial refund already issued from the dashboard "
                "isn't paid out again. Crypto payments can't be refunded this way. "
                "Defaults to false."
            ),
        ),
        Body(),
    ]
    tickets_to_add: Annotated[
        Optional[List[TicketsToAddItem]],
        Field(
            None,
            description=(
                "Complimentary tickets to grant. Each entry creates a new $0 "
                "administrative ticket, even when the ticket type is normally paid."
            ),
        ),
        Body(),
        Gloss("Defaults to `[]` when omitted."),
    ]
    send_email: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Optional. Whether Luma may email the guest about the ticket change, "
                "including the refund receipt when `should_refund` is set. Defaults to "
                "true and still respects their notification preferences. This only "
                "controls email — the guest still gets an in-app notification, and push"
                " follows their preferences."
            ),
        ),
        Body(),
    ]


class EventsGuestsSendInvitesRequest(PackModel):
    """Send Invites

    Send guests an invite to an event. We'll send an email, and if their phone number is
    linked to their Luma account, they'll also receive an SMS. Invites are sent in the
    background; the response lists any guests that will be skipped because they unsubscribed
    from your calendar, were removed by an admin, or blocked you.

    API Reference: https://docs.luma.com/reference/post_v1-events-guests-send-invites
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    guests: Annotated[
        List[EventsGuestsSendInvitesGuest],
        Field(
            ...,
            description=(
                "Information about the guests you want to invite to the event. If a "
                "user already has a name, this will not overwrite their name."
            ),
        ),
        Body(),
    ]
    message: Annotated[
        Optional[str],
        Field(
            None,
            max_length=200,
            description=(
                "Personalize the message that will be included in the invite. Max of "
                "200 characters."
            ),
        ),
        Body(),
    ]


class EventsGuestsAddRequest(PackModel):
    """Add Guests

    Add guests to the event. By default, guests are added with the status "Going" (approved)
    and receive one ticket of the default ticket type. Use the `ticket` or `tickets`
    parameter to specify custom ticket assignments. Get available ticket types using
    `/v1/events/ticket-types/list`. Use `approval_status` to add guests as pending approval
    or on the waitlist instead of immediately approved. Use `registration_answers` on each
    guest to record answers to the event's registration questions — question IDs come from
    the `registration_questions` field of Get Event. Guests are added in the background; the
    response lists any guests that will be skipped because they unsubscribed from your
    calendar, were removed by an admin, or blocked you.

    API Reference: https://docs.luma.com/reference/post_v1-events-guests-add
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    guests: Annotated[
        List[EventsGuestsAddGuest],
        Field(...),
        Body(),
        Gloss("The guests to add, each by email."),
    ]
    ticket: Annotated[
        Optional[Ticket],
        Field(
            None,
            description=(
                "Optional. Assign a single ticket of the specified type to each guest. "
                "Cannot be used with `tickets` parameter."
            ),
        ),
        Body(),
        ConflictsWith("tickets", reason="Use tickets alone to give each guest several tickets."),
    ]
    tickets: Annotated[
        Optional[List[Ticket]],
        Field(
            None,
            description=(
                "Optional. Assign multiple tickets to each guest. Each guest receives "
                "all tickets in the array. Use this to add multiple tickets of the same"
                " or different types. Cannot be used with `ticket` parameter."
            ),
        ),
        Body(),
    ]
    approval_status: Annotated[
        Optional[EventsGuestsAddApprovalStatus],
        Field(
            None,
            description=(
                "Optional. Status to assign to each added guest. Defaults to `approved`"
                ' ("Going"). Use `pending_approval` to add guests for host review, or '
                "`waitlist` to add to the event waitlist. To send a soft invite that "
                "guests can accept, use `/v1/events/guests/send-invites` instead."
            ),
        ),
        Body(),
    ]
    send_email: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Optional. Whether Luma should email each added guest. Defaults to "
                "true. Set to false if your integration sends its own notifications."
            ),
        ),
        Body(),
    ]


class EventsHostsAddRequest(PackModel):
    """Add Host

    Add a host to an event. This works for both managers and check-in staff — use the
    access_level parameter to control permissions.

    API Reference: https://docs.luma.com/reference/post_v1-events-hosts-add
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    email: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("Email of the person to make a host."),
    ]
    access_level: Annotated[
        Optional[AccessLevel],
        Field(None, description="Defaults to manager."),
        Body(),
    ]
    is_visible: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether the host is shown on the event page. Defaults to true, except "
                "for `check-in` hosts, which are never shown — passing `true` with "
                "`check-in` is an error."
            ),
        ),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Name of the host you are adding. If they already have a Luma profile, "
                "this will be ignored."
            ),
        ),
        Body(),
    ]


class EventsHostsUpdateRequest(PackModel):
    """Update Host

    Update a host's permissions or visibility on an event. Use this to change a host between
    check-in and manager access levels. The event creator's access level cannot be changed.

    API Reference: https://docs.luma.com/reference/post_v1-events-hosts-update
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    email: Annotated[
        str,
        Field(..., description="Email of the host to update."),
        Body(),
    ]
    access_level: Annotated[
        Optional[AccessLevel],
        Field(
            None,
            description=(
                'The new access level for the host. One of "none", "check-in", or '
                '"manager". The event creator’s access level cannot be changed.'
            ),
        ),
        Body(),
    ]
    is_visible: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether the host is shown on the event page. `check-in` hosts are "
                "never shown: changing a host to `check-in` hides them, and passing "
                "`true` with `check-in` is an error."
            ),
        ),
        Body(),
    ]


class EventsHostsRemoveRequest(PackModel):
    """Remove Host

    Remove a host from an event. The event creator cannot be removed.

    API Reference: https://docs.luma.com/reference/post_v1-events-hosts-remove
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    email: Annotated[
        str,
        Field(..., description="Email of the host to remove."),
        Body(),
    ]


class EventsCouponsCreateRequest(PackModel):
    """Create Coupon

    Create a coupon that can be applied when a guest is registering for an event. Restrict
    it to a ticket type with `event_ticket_type_id` — when that ticket type is hidden, this
    creates an unlock (access) code. You are not able to edit the coupon terms after it has
    been created.

    API Reference: https://docs.luma.com/reference/post_v1-events-coupons-create
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
    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    event_ticket_type_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Optional. Restrict the coupon to a single ticket type. If that ticket "
                "type is hidden, the coupon acts as an unlock (access) code that "
                "reveals the ticket during registration. Pair a hidden ticket type that"
                " has Require Approval turned off with an unlock code to let invited "
                "guests register and pay directly, skipping the Apply to Attend step. "
                "For a code that unlocks the ticket without changing the price, set the"
                " discount to 0% (`percent_off: 0`)."
            ),
        ),
        Body(),
    ]


class EventsCouponsUpdateRequest(PackModel):
    """Update Coupon

    API Reference: https://docs.luma.com/reference/post_v1-events-coupons-update
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
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


class EventsTicketTypesCreateRequest(PackModel):
    """Create Ticket Type

    Create a new ticket type for an event. Paid ticket types require the calendar to have a
    connected Stripe account.

    API Reference: https://docs.luma.com/reference/post_v1-events-ticket-types-create
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    name: Annotated[
        str,
        Field(..., min_length=1, max_length=30),
        Body(),
        Gloss("The ticket type's name, as guests see it."),
    ]
    require_approval: Annotated[
        Optional[bool],
        Field(None),
        Body(),
        Gloss("Whether a guest registering with this ticket waits for host approval."),
    ]
    is_hidden: Annotated[
        Optional[bool],
        Field(None),
        Body(),
        Gloss(
            "Whether the ticket type is hidden from the event page. A coupon restricted"
            " to a hidden ticket type unlocks it."
        ),
    ]
    description: Annotated[
        Optional[str],
        Field(None, max_length=1000),
        Body(),
        Gloss("A description shown with the ticket type."),
    ]
    valid_start_at: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z\n"
                "ISO 8601 Date. For example, 2025-09-01"
            ),
        ),
        Body(),
    ]
    valid_end_at: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z\n"
                "ISO 8601 Date. For example, 2025-09-01"
            ),
        ),
        Body(),
    ]
    max_capacity: Annotated[
        Optional[float],
        Field(None),
        Body(),
        Gloss("The most tickets of this type that can be issued."),
    ]
    max_per_guest: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "Luma Pro calendars only. The most tickets of this type each guest can "
                "hold, across all their registrations. `null` means no limit."
            ),
        ),
        Body(),
    ]
    type: Annotated[
        Literal["free", "paid"],
        Field(...),
        Body(),
        Gloss(
            "`free`, or `paid` with a price in `cents`. Paid ticket types need the "
            "calendar's Stripe account connected."
        ),
    ]
    cents: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=9007199254740991,
            description=(
                "Price in the currency's minor unit (e.g. 2500 for $25.00). Required "
                "for paid ticket types."
            ),
        ),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(
            None, description="ISO 4217 currency code like `usd`. Required for paid ticket types."
        ),
        Body(),
    ]
    is_flexible: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Pay-what-you-want pricing: guests choose an amount of at least `min_cents`."
            ),
        ),
        Body(),
    ]
    min_cents: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=9007199254740991,
            description=(
                "Minimum amount for pay-what-you-want pricing, in the currency's minor unit."
            ),
        ),
        Body(),
    ]


class EventsTicketTypesUpdateRequest(PackModel):
    """Update Ticket Type

    Update an existing ticket type configuration

    API Reference: https://docs.luma.com/reference/post_v1-events-ticket-types-update
    """

    event_ticket_type_id: Annotated[
        str,
        Field(..., description="Ticket type ID, this usually starts with ttype-"),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(None, min_length=1, max_length=30),
        Body(),
        Gloss("The ticket type's new name. Omit to keep it."),
    ]
    require_approval: Annotated[
        Optional[bool],
        Field(None),
        Body(),
        Gloss("Whether a guest registering with this ticket waits for host approval."),
    ]
    is_hidden: Annotated[
        Optional[bool],
        Field(None),
        Body(),
        Gloss(
            "Whether the ticket type is hidden from the event page. A coupon restricted"
            " to a hidden ticket type unlocks it."
        ),
    ]
    description: Annotated[
        Optional[str],
        Field(None, max_length=1000),
        Body(),
        Gloss("A description shown with the ticket type."),
    ]
    valid_start_at: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z\n"
                "ISO 8601 Date. For example, 2025-09-01"
            ),
        ),
        Body(),
    ]
    valid_end_at: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z\n"
                "ISO 8601 Date. For example, 2025-09-01"
            ),
        ),
        Body(),
    ]
    max_capacity: Annotated[
        Optional[float],
        Field(None),
        Body(),
        Gloss("The most tickets of this type that can be issued."),
    ]
    max_per_guest: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "Luma Pro calendars only. The most tickets of this type each guest can "
                "hold, across all their registrations. `null` means no limit."
            ),
        ),
        Body(),
    ]
    type: Annotated[
        Optional[Literal["free", "paid"]],
        Field(None),
        Body(),
        Gloss(
            "`free`, or `paid` with a price in `cents`. Paid ticket types need the "
            "calendar's Stripe account connected."
        ),
    ]
    cents: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=9007199254740991,
            description=(
                "Price in the currency's minor unit (e.g. 2500 for $25.00). Required "
                "for paid ticket types."
            ),
        ),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(
            None, description="ISO 4217 currency code like `usd`. Required for paid ticket types."
        ),
        Body(),
    ]
    is_flexible: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Pay-what-you-want pricing: guests choose an amount of at least `min_cents`."
            ),
        ),
        Body(),
    ]
    min_cents: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=9007199254740991,
            description=(
                "Minimum amount for pay-what-you-want pricing, in the currency's minor unit."
            ),
        ),
        Body(),
    ]


class EventsTicketTypesDeleteRequest(PackModel):
    """Delete Ticket Type

    Soft delete a ticket type. Guests already registered with it keep their tickets. Cannot
    delete the last visible ticket type.

    API Reference: https://docs.luma.com/reference/post_v1-events-ticket-types-delete
    """

    event_ticket_type_id: Annotated[
        str,
        Field(..., description="Ticket type ID, this usually starts with ttype-"),
        Body(envelop=True),
    ]


class EventsBlastsCreateRequest(PackModel):
    """Create Blast

    Email a message to an event's guests now, or at `scheduled_for`. Blasts go out in the
    background, count against the calendar's send limit, and can't be recalled once sent.
    Returns the blast with `status: scheduled` until it's sent. Limited to 10 blasts per 5
    minutes.

    API Reference: https://docs.luma.com/reference/post_v1-events-blasts-create
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    recipient_groups: Annotated[
        Optional[List[BlastRecipientGroupInput]],
        Field(
            None,
            min_length=1,
            description=(
                "Who gets the blast. Defaults to going (`approved`) guests across every"
                " ticket type."
            ),
        ),
        Body(),
    ]
    scheduled_for: Annotated[
        Optional[str],
        Field(
            None,
            description="When to send, as an ISO 8601 datetime in the future. Omit to send now.",
        ),
        Body(),
    ]
    subject: Annotated[
        Optional[str],
        Field(
            None,
            max_length=200,
            description=(
                "Email subject line. Omit for the default, “New message in {event name}”."
            ),
        ),
        Body(),
    ]
    content_md: Annotated[
        str,
        Field(..., min_length=1, description="The message, in markdown. Sent as the email body."),
        Body(),
    ]


class EventsBlastsUpdateRequest(PackModel):
    """Update Blast

    Edit a blast. Only the fields you pass change. Before a blast is sent, everything can
    change. After it's sent, only `subject` and `content_md` can, which updates the post on
    the event page but not the emails already delivered. Blasts under review can't be
    edited.

    API Reference: https://docs.luma.com/reference/post_v1-events-blasts-update
    """

    blast_id: Annotated[
        str,
        Field(..., description="Blast ID, this usually starts with ep-"),
        Body(),
    ]
    recipient_groups: Annotated[
        Optional[List[BlastRecipientGroupInput]],
        Field(
            None, min_length=1, description="New audience. Only for blasts that haven't been sent."
        ),
        Body(),
    ]
    scheduled_for: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "New send time, as an ISO 8601 datetime in the future. Only for blasts "
                "that haven't been sent."
            ),
        ),
        Body(),
    ]
    subject: Annotated[
        Optional[str],
        Field(
            None,
            max_length=200,
            description=(
                "Email subject line. Omit for the default, “New message in {event name}”."
            ),
        ),
        Body(),
    ]
    content_md: Annotated[
        Optional[str],
        Field(None, min_length=1, description="The message, in markdown. Sent as the email body."),
        Body(),
    ]


class EventsBlastsDeleteRequest(PackModel):
    """Delete Blast

    Delete a blast. Deleting a scheduled blast cancels the send. Deleting a sent blast
    removes the post from the event page, but the emails already delivered stay delivered.

    API Reference: https://docs.luma.com/reference/post_v1-events-blasts-delete
    """

    blast_id: Annotated[
        str,
        Field(..., description="Blast ID, this usually starts with ep-"),
        Body(envelop=True),
    ]


class EventsCancelRequestRequest(PackModel):
    """Request Event Cancellation

    Request a cancellation token for an event. Canceling an event is irreversible — it
    notifies all guests, processes refunds, and permanently deletes the event. Because of
    this, cancellation uses a two-step flow: first request a token here, then pass it to
    /events/cancel to execute. The token expires after 15 minutes.

    API Reference: https://docs.luma.com/reference/post_v1-events-cancel-request
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(envelop=True),
    ]


class EventsCancelRequest(PackModel):
    """Cancel Event

    Cancel an event. You must first call /events/cancel/request to get a cancellation_token,
    then pass it here. This is irreversible — the event will be deleted, all guests will be
    notified, and refunds will be processed if should_refund is true. For paid events, you
    must specify should_refund.

    API Reference: https://docs.luma.com/reference/post_v1-events-cancel
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    cancellation_token: Annotated[
        str,
        Field(..., description="The cancellation token returned from the request endpoint."),
        Body(),
    ]
    should_refund: Annotated[
        Optional[bool],
        Field(
            None,
            description="Whether to refund paid guests. Required if the event has paid guests.",
        ),
        Body(),
    ]
