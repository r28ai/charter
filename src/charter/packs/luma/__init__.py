# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Luma — 74 tools over the Luma public API: events, guests, ticket types, coupons,
blasts, calendars, contacts, tags, memberships, webhooks and organizations.

    from charter.packs import luma

    luma.configure(api_key="...")
    event = await luma.events_get.ainvoke(event_id="evt-...")
    going = await luma.events_guests_list.ainvoke(
        event_id="evt-...", approval_status="approved"
    )

``configure()`` is optional if ``$LUMA_API_KEY`` is set. The key travels in Luma's
``x-luma-api-key`` header, and the API needs a Luma Plus subscription.

What the review found that the spec does not say:

**A key is one calendar.** Luma scopes a calendar API key to the calendar it was
made on — "each key only grants access to the calendar it was created on" — so
the ``calendars_*`` tools act on that calendar, and only ``calendars_update`` asks
for its ID. An organization API key reaches the ``organizations_*`` tools, and Luma
documents choosing one of the organization's calendars with an
``x-luma-calendar-id`` header when approving or rejecting a submission. Which
calendar a call acts on is the host's decision, not the model's, so that header
is ``ainvoke(args, headers={"x-luma-calendar-id": "cal-..."})`` and never a tool
argument. The docs do not say which other endpoints an organization key may call,
so the pack declares no kinds of credential rather than guess.

**Reads are GETs with query parameters; every write is a POST.** Luma versions
each route on its own, so ``/v1/`` and ``/v2/`` sit side by side and the version
is part of each tool's URL. Arrays in a query repeat the key
(``?platforms=luma&platforms=external``), as Luma documents.

**Failure is a status code.** Luma documents ``429`` past the rate limit — 200
requests a minute per calendar key or OAuth token, 500 per organization key —
and nothing that answers ``200`` on failure, so there is no ``Envelope``.

**Pages are cursors.** ``next_cursor`` comes back, ``pagination_cursor`` takes it,
and ``has_more`` says whether to continue; declared on the ten list tools that page.

Known limits, named rather than hidden:

* **``null`` cannot be sent.** Charter omits an unset field and never sends
  ``null``, so what Luma clears with ``null`` — an event's ``font``, a registration
  question's library ``source``, a calendar's ``location``, a ticket type's
  ``max_per_guest`` limit — can be set through these tools but not cleared.
* **Uploading an image is two steps, and the second is not a tool.**
  ``images_create_upload_url`` returns an ``upload_url`` to ``PUT`` the bytes to,
  which is a file transfer to Luma's CDN rather than an API call.
* **Two tools are large.** ``events_create`` and ``events_update`` are about 22KB
  of schema each, most of it themes, fonts and the thirteen kinds of registration
  question. Narrow them with ``tool.derived(keep=...)`` where an agent needs less.
* **Deprecated fields are withheld.** ``suppress_notifications`` (replaced by
  ``suppress_email``) and the ``event_api_id`` lookups are ``Mode("disabled")``.

Drafted by ``scripts/openapi_to_pack.py`` from
https://public-api.luma.com/openapi.json, then reviewed by hand.
"""

from __future__ import annotations

from typing import Optional

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider, configure_key_or_provider
from charter.packs.luma.types import (
    CalendarsAdminsAddRequest,
    CalendarsAdminsListRequest,
    CalendarsContactsBlockRequest,
    CalendarsContactsImportRequest,
    CalendarsContactsListRequest,
    CalendarsContactsRemoveRequest,
    CalendarsContactsRestoreRequest,
    CalendarsContactTagsApplyRequest,
    CalendarsContactTagsCreateRequest,
    CalendarsContactTagsDeleteRequest,
    CalendarsContactTagsListRequest,
    CalendarsContactTagsUnapplyRequest,
    CalendarsContactTagsUpdateRequest,
    CalendarsCouponsCreateRequest,
    CalendarsCouponsListRequest,
    CalendarsCouponsUpdateRequest,
    CalendarsEventsAddRequest,
    CalendarsEventsApproveRequest,
    CalendarsEventsListRequest,
    CalendarsEventsLookupRequest,
    CalendarsEventsRejectRequest,
    CalendarsEventTagsApplyRequest,
    CalendarsEventTagsCreateRequest,
    CalendarsEventTagsDeleteRequest,
    CalendarsEventTagsListRequest,
    CalendarsEventTagsUnapplyRequest,
    CalendarsEventTagsUpdateRequest,
    CalendarsGetRequest,
    CalendarsUpdateRequest,
    EntitiesLookupRequest,
    EventsBlastsCreateRequest,
    EventsBlastsDeleteRequest,
    EventsBlastsGetRequest,
    EventsBlastsListRequest,
    EventsBlastsUpdateRequest,
    EventsCancelRequest,
    EventsCancelRequestRequest,
    EventsCouponsCreateRequest,
    EventsCouponsListRequest,
    EventsCouponsUpdateRequest,
    EventsCreateRequest,
    EventsGetRequest,
    EventsGuestsAddRequest,
    EventsGuestsGetRequest,
    EventsGuestsListRequest,
    EventsGuestsSendInvitesRequest,
    EventsGuestsUpdateStatusRequest,
    EventsGuestsUpdateTicketsRequest,
    EventsHostsAddRequest,
    EventsHostsRemoveRequest,
    EventsHostsUpdateRequest,
    EventsTicketTypesCreateRequest,
    EventsTicketTypesDeleteRequest,
    EventsTicketTypesGetRequest,
    EventsTicketTypesListRequest,
    EventsTicketTypesUpdateRequest,
    EventsUpdateRequest,
    ImagesCreateUploadUrlRequest,
    ImagesSearchRequest,
    MembershipsMembersAddRequest,
    MembershipsMembersUpdateStatusRequest,
    MembershipsTiersListRequest,
    OrganizationsAdminsListRequest,
    OrganizationsCalendarsCreateRequest,
    OrganizationsCalendarsListRequest,
    OrganizationsEventsListRequest,
    OrganizationsEventsTransferCalendarRequest,
    PlacesSearchRequest,
    UsersGetSelfRequest,
    WebhooksCreateRequest,
    WebhooksDeleteRequest,
    WebhooksGetRequest,
    WebhooksListRequest,
    WebhooksUpdateRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://public-api.luma.com/"
QUOTA_DOC_URL = "https://docs.luma.com/reference/rate-limits"

LUMA_PAGINATION = Pagination(
    cursor_field="next_cursor",
    cursor_param="pagination_cursor",
    more_field="has_more",
)

_credentials = DeferredCredentialProvider("luma", env_var="LUMA_API_KEY")


def configure(
    api_key: Optional[str] = None,
    *,
    credential_provider: Optional[CredentialProvider] = None,
) -> None:
    """Supply the Luma API credential for this pack's tools, or a provider of one per call."""
    configure_key_or_provider(_credentials, api_key, credential_provider)


_luma = oauth_tool_factory(
    pack="luma",
    base_url=BASE_URL,
    provider="luma",
    credential_provider=_credentials,
    body_case="snake",
    query_case="snake",
    path_case="snake",
    token_header="x-luma-api-key",
    quota_doc_url=QUOTA_DOC_URL,
)

events_get = _luma(
    name="events_get",
    args_schema=EventsGetRequest,
    method="GET",
    url_template="v1/events/get",
    description=(
        'Return details about an event. For events you manage (`access: "manage"`), '
        "this includes full detail, host contact info, and a breakdown of guest counts "
        'by status. For public events you don’t manage (`access: "view"`), only the '
        "fields a regular event-page visitor could see are returned."
    ),
    action_label="Get Event",
)

calendars_get = _luma(
    name="calendars_get",
    args_schema=CalendarsGetRequest,
    method="GET",
    url_template="v1/calendars/get",
    description="Get information about the calendar.",
    action_label="Get Calendar",
)

calendars_events_list = _luma(
    name="calendars_events_list",
    args_schema=CalendarsEventsListRequest,
    method="GET",
    url_template="v1/calendars/events/list",
    description=(
        "Every event and API key on Luma is managed by a [Luma "
        "Calendar](https://help.luma.com/p/luma-calendar-overview). By default this "
        "lists the events your Calendar manages.\n"
        "\n"
        "Each event includes an `access` field. Pass `access=manage&access=view` to "
        "also return events that are listed on the Calendar but managed elsewhere — "
        'those come back with `access: "view"`, their location obfuscated to city '
        "level, and host-only fields like `meeting_url`, `registration_questions`, and "
        "`feedback_email` omitted. Private events the Calendar doesn't manage are never"
        " returned."
    ),
    action_label="List Events",
    pagination_override=LUMA_PAGINATION,
)

events_guests_get = _luma(
    name="events_guests_get",
    args_schema=EventsGuestsGetRequest,
    method="GET",
    url_template="v1/events/guests/get",
    description=(
        "Get detailed information for an event guest by looking them up by their ID. "
        "This supports looking them up by different parameters.\n"
        "\n"
        "This response includes `event_ticket_orders`, which includes `coupon_info` "
        "when a coupon was applied."
    ),
    action_label="Get Guest",
)

events_guests_list = _luma(
    name="events_guests_list",
    args_schema=EventsGuestsListRequest,
    method="GET",
    url_template="v1/events/guests/list",
    description=(
        "Get list of guests who have registered or been invited to an event.\n"
        "\n"
        "This list response includes guest summaries and `event_tickets`, but not "
        "order-level details like `event_ticket_orders`. Use `/v1/events/guests/get` "
        "when you need detailed ticket order data for a specific guest."
    ),
    action_label="List Guests",
    pagination_override=LUMA_PAGINATION,
)

users_get_self = _luma(
    name="users_get_self",
    args_schema=UsersGetSelfRequest,
    method="GET",
    url_template="v1/users/get-self",
    description="Get the Luma user the API key belongs to. The quickest check that a key works.",
    action_label="Get Self",
)

calendars_contact_tags_list = _luma(
    name="calendars_contact_tags_list",
    args_schema=CalendarsContactTagsListRequest,
    method="GET",
    url_template="v1/calendars/contact-tags/list",
    description=(
        "List the contact tags on the calendar, with the IDs that apply, unapply, "
        "update and delete them."
    ),
    action_label="List Contact Tags",
)

calendars_event_tags_list = _luma(
    name="calendars_event_tags_list",
    args_schema=CalendarsEventTagsListRequest,
    method="GET",
    url_template="v1/calendars/event-tags/list",
    description=(
        "List the event tags on the calendar, with the IDs that apply, unapply, update "
        "and delete them."
    ),
    action_label="List Event Tags",
)

calendars_admins_list = _luma(
    name="calendars_admins_list",
    args_schema=CalendarsAdminsListRequest,
    method="GET",
    url_template="v1/calendars/admins/list",
    description="List all admins for the calendar.",
    action_label="List Calendar Admins",
)

entities_lookup = _luma(
    name="entities_lookup",
    args_schema=EntitiesLookupRequest,
    method="GET",
    url_template="v1/entities/lookup",
    description=(
        "Look up an event or calendar by its slug, Luma URL, or permanent public path "
        "such as `event/evt-...`, `e/evt-...`, or `calendar/cal-...`. URL query "
        "parameters and fragments are ignored."
    ),
    action_label="Lookup Entity",
)

places_search = _luma(
    name="places_search",
    args_schema=PlacesSearchRequest,
    method="GET",
    url_template="v1/places/search",
    description=(
        "Search Google Maps for a place and get up to 5 candidates. Pass the chosen "
        '`place_id` as `geo_address_json: { type: "google", place_id }` when creating '
        "or updating an event."
    ),
    action_label="Search Places",
)

images_search = _luma(
    name="images_search",
    args_schema=ImagesSearchRequest,
    method="GET",
    url_template="v1/images/search",
    description=(
        "Search Luma’s gallery of stock event cover images by keyword. Pass the chosen "
        "`image_url` as `cover_url` when creating or updating an event — gallery images"
        " don’t need to be uploaded first."
    ),
    action_label="Search Cover Images",
    pagination_override=LUMA_PAGINATION,
)

calendars_events_lookup = _luma(
    name="calendars_events_lookup",
    args_schema=CalendarsEventsLookupRequest,
    method="GET",
    url_template="v1/calendars/events/lookup",
    description=(
        "See if an event already exists on the calendar. This is useful when figuring "
        "out if you want to submit an event to the calendar."
    ),
    action_label="Lookup Event",
)

calendars_contacts_list = _luma(
    name="calendars_contacts_list",
    args_schema=CalendarsContactsListRequest,
    method="GET",
    url_template="v1/calendars/contacts/list",
    description=(
        "List the calendar's contacts, optionally narrowed by search text, contact "
        "tags, or membership tier and status, and sorted by the column you choose."
    ),
    action_label="List Contacts",
    pagination_override=LUMA_PAGINATION,
)

events_coupons_list = _luma(
    name="events_coupons_list",
    args_schema=EventsCouponsListRequest,
    method="GET",
    url_template="v1/events/coupons/list",
    description="List all coupons that have been created for an event.",
    action_label="List Event Coupons",
    pagination_override=LUMA_PAGINATION,
)

calendars_coupons_list = _luma(
    name="calendars_coupons_list",
    args_schema=CalendarsCouponsListRequest,
    method="GET",
    url_template="v1/calendars/coupons/list",
    description="List all coupons that have been created for a calendar.",
    action_label="List Calendar Coupons",
    pagination_override=LUMA_PAGINATION,
)

events_ticket_types_list = _luma(
    name="events_ticket_types_list",
    args_schema=EventsTicketTypesListRequest,
    method="GET",
    url_template="v1/events/ticket-types/list",
    description="List all ticket types for an event",
    action_label="List Ticket Types",
)

events_ticket_types_get = _luma(
    name="events_ticket_types_get",
    args_schema=EventsTicketTypesGetRequest,
    method="GET",
    url_template="v1/events/ticket-types/get",
    description="Get a single ticket type by ID",
    action_label="Get Ticket Type",
)

events_blasts_list = _luma(
    name="events_blasts_list",
    args_schema=EventsBlastsListRequest,
    method="GET",
    url_template="v1/events/blasts/list",
    description=(
        "List the blasts (emails to guests) on an event, newest first. Sent blasts "
        "include `recipient_count` and `email_open_count`."
    ),
    action_label="List Blasts",
)

events_blasts_get = _luma(
    name="events_blasts_get",
    args_schema=EventsBlastsGetRequest,
    method="GET",
    url_template="v1/events/blasts/get",
    description="Get a blast by ID.",
    action_label="Get Blast",
)

memberships_tiers_list = _luma(
    name="memberships_tiers_list",
    args_schema=MembershipsTiersListRequest,
    method="GET",
    url_template="v1/memberships/tiers/list",
    description="List the calendar's membership tiers, including hidden ones (see is_hidden).",
    action_label="List Membership Tiers",
    pagination_override=LUMA_PAGINATION,
)

webhooks_list = _luma(
    name="webhooks_list",
    args_schema=WebhooksListRequest,
    method="GET",
    url_template="v1/webhooks/list",
    description="List all webhook endpoints for the calendar.",
    action_label="List Webhooks",
    pagination_override=LUMA_PAGINATION,
)

webhooks_get = _luma(
    name="webhooks_get",
    args_schema=WebhooksGetRequest,
    method="GET",
    url_template="v2/webhooks/get",
    description="Get details about a specific webhook endpoint.",
    action_label="Get Webhook",
)

organizations_admins_list = _luma(
    name="organizations_admins_list",
    args_schema=OrganizationsAdminsListRequest,
    method="GET",
    url_template="v1/organizations/admins/list",
    description="List all admins for the organization.",
    action_label="List Organization Admins",
)

organizations_calendars_list = _luma(
    name="organizations_calendars_list",
    args_schema=OrganizationsCalendarsListRequest,
    method="GET",
    url_template="v1/organizations/calendars/list",
    description="List all calendars belonging to the organization.",
    action_label="List Organization Calendars",
    pagination_override=LUMA_PAGINATION,
)

organizations_events_list = _luma(
    name="organizations_events_list",
    args_schema=OrganizationsEventsListRequest,
    method="GET",
    url_template="v1/organizations/events/list",
    description=(
        "List all events across all calendars belonging to the organization. Events are"
        " deduplicated if they appear on multiple calendars within the organization."
    ),
    action_label="List Organization Events",
    pagination_override=LUMA_PAGINATION,
)

events_create = _luma(
    name="events_create",
    args_schema=EventsCreateRequest,
    method="POST",
    url_template="v1/events/create",
    description=(
        "Create an event on the calendar. A name, a start time and a timezone are "
        "required; location, tickets, registration questions, theme and the rest are "
        "optional. Returns the new event's ID."
    ),
    action_label="Create Event",
)

events_update = _luma(
    name="events_update",
    args_schema=EventsUpdateRequest,
    method="POST",
    url_template="v1/events/update",
    description=(
        "Update an event by its ID. Send only what should change: a field left out "
        "keeps its current value."
    ),
    action_label="Update Event",
)

events_guests_update_status = _luma(
    name="events_guests_update_status",
    args_schema=EventsGuestsUpdateStatusRequest,
    method="POST",
    url_template="v1/events/guests/update-status",
    description=(
        'Update a guest’s status. Set `status` to `approved` ("Going"), `declined`, '
        "`pending_approval`, or `waitlist`. Use `should_refund` to refund a paid guest "
        "when moving them out of an approved state. Use `message` to include a personal"
        " note in the email we send the guest. To send a soft invite that guests can "
        "accept, use `/v1/events/guests/send-invites` instead."
    ),
    action_label="Update Guest Status",
)

events_guests_update_tickets = _luma(
    name="events_guests_update_tickets",
    args_schema=EventsGuestsUpdateTicketsRequest,
    method="POST",
    url_template="v1/events/guests/update-tickets",
    description=(
        "Add or remove tickets from an existing guest. Added tickets are complimentary."
        " Removed tickets are invalidated and, if `should_refund` is set, refunded for "
        "what the guest paid for them; otherwise no money moves. You can’t change "
        "tickets for guests with pending payment holds. Administrative ticket changes "
        "can exceed event or ticket-type capacity."
    ),
    action_label="Update Guest Tickets",
)

events_guests_send_invites = _luma(
    name="events_guests_send_invites",
    args_schema=EventsGuestsSendInvitesRequest,
    method="POST",
    url_template="v1/events/guests/send-invites",
    description=(
        "Send guests an invite to an event. We'll send an email, and if their phone "
        "number is linked to their Luma account, they'll also receive an SMS. Invites "
        "are sent in the background; the response lists any guests that will be skipped"
        " because they unsubscribed from your calendar, were removed by an admin, or "
        "blocked you."
    ),
    action_label="Send Invites",
)

events_guests_add = _luma(
    name="events_guests_add",
    args_schema=EventsGuestsAddRequest,
    method="POST",
    url_template="v1/events/guests/add",
    description=(
        'Add guests to the event. By default, guests are added with the status "Going" '
        "(approved) and receive one ticket of the default ticket type. Use the `ticket`"
        " or `tickets` parameter to specify custom ticket assignments. Get available "
        "ticket types using `/v1/events/ticket-types/list`. Use `approval_status` to "
        "add guests as pending approval or on the waitlist instead of immediately "
        "approved. Use `registration_answers` on each guest to record answers to the "
        "event's registration questions — question IDs come from the "
        "`registration_questions` field of Get Event. Guests are added in the "
        "background; the response lists any guests that will be skipped because they "
        "unsubscribed from your calendar, were removed by an admin, or blocked you."
    ),
    action_label="Add Guests",
)

events_hosts_add = _luma(
    name="events_hosts_add",
    args_schema=EventsHostsAddRequest,
    method="POST",
    url_template="v1/events/hosts/add",
    description=(
        "Add a host to an event. This works for both managers and check-in staff — use "
        "the access_level parameter to control permissions."
    ),
    action_label="Add Host",
)

events_hosts_update = _luma(
    name="events_hosts_update",
    args_schema=EventsHostsUpdateRequest,
    method="POST",
    url_template="v1/events/hosts/update",
    description=(
        "Update a host's permissions or visibility on an event. Use this to change a "
        "host between check-in and manager access levels. The event creator's access "
        "level cannot be changed."
    ),
    action_label="Update Host",
)

events_hosts_remove = _luma(
    name="events_hosts_remove",
    args_schema=EventsHostsRemoveRequest,
    method="POST",
    url_template="v1/events/hosts/remove",
    description="Remove a host from an event. The event creator cannot be removed.",
    action_label="Remove Host",
)

events_coupons_create = _luma(
    name="events_coupons_create",
    args_schema=EventsCouponsCreateRequest,
    method="POST",
    url_template="v1/events/coupons/create",
    description=(
        "Create a coupon that can be applied when a guest is registering for an event. "
        "Restrict it to a ticket type with `event_ticket_type_id` — when that ticket "
        "type is hidden, this creates an unlock (access) code. You are not able to edit"
        " the coupon terms after it has been created."
    ),
    action_label="Create Coupon",
)

events_coupons_update = _luma(
    name="events_coupons_update",
    args_schema=EventsCouponsUpdateRequest,
    method="POST",
    url_template="v1/events/coupons/update",
    description=(
        "Change how many more times an event coupon can be used, or the window it is "
        "valid in. Its discount cannot be changed after it is created."
    ),
    action_label="Update Coupon",
)

calendars_coupons_create = _luma(
    name="calendars_coupons_create",
    args_schema=CalendarsCouponsCreateRequest,
    method="POST",
    url_template="v1/calendars/coupons/create",
    description=(
        "Create a coupon that can be applied to any event that is managed by the "
        "calendar. Be careful not to have the same code on an event and on the "
        "calendar."
    ),
    action_label="Create Coupon",
)

calendars_coupons_update = _luma(
    name="calendars_coupons_update",
    args_schema=CalendarsCouponsUpdateRequest,
    method="POST",
    url_template="v1/calendars/coupons/update",
    description=(
        "Change how many more times a calendar coupon can be used, or the window it is "
        "valid in. Its discount cannot be changed after it is created."
    ),
    action_label="Update Coupon",
)

calendars_contacts_import = _luma(
    name="calendars_contacts_import",
    args_schema=CalendarsContactsImportRequest,
    method="POST",
    url_template="v1/calendars/contacts/import",
    description=(
        "Import contacts to the calendar, so they can be invited to events and sent newsletters."
    ),
    action_label="Import Contacts",
)

calendars_contacts_block = _luma(
    name="calendars_contacts_block",
    args_schema=CalendarsContactsBlockRequest,
    method="POST",
    url_template="v1/calendars/contacts/block",
    description=(
        "Block a contact so they can’t follow your calendar or join its events. They "
        "stop receiving your invites and newsletters until you restore them."
    ),
    action_label="Block Contact",
)

calendars_contacts_remove = _luma(
    name="calendars_contacts_remove",
    args_schema=CalendarsContactsRemoveRequest,
    method="POST",
    url_template="v1/calendars/contacts/remove",
    description=(
        "Remove a contact from your calendar. They stop receiving your invites and "
        "newsletters but can follow again on their own later."
    ),
    action_label="Remove Contact",
)

calendars_contacts_restore = _luma(
    name="calendars_contacts_restore",
    args_schema=CalendarsContactsRestoreRequest,
    method="POST",
    url_template="v1/calendars/contacts/restore",
    description="Restore a blocked or removed contact, returning them to your active contacts.",
    action_label="Restore Contact",
)

calendars_contact_tags_create = _luma(
    name="calendars_contact_tags_create",
    args_schema=CalendarsContactTagsCreateRequest,
    method="POST",
    url_template="v1/calendars/contact-tags/create",
    description="Create a contact tag on the calendar. Returns its ID.",
    action_label="Create Contact Tag",
)

calendars_contact_tags_update = _luma(
    name="calendars_contact_tags_update",
    args_schema=CalendarsContactTagsUpdateRequest,
    method="POST",
    url_template="v1/calendars/contact-tags/update",
    description="Rename a contact tag or change its color.",
    action_label="Update Contact Tag",
)

calendars_contact_tags_delete = _luma(
    name="calendars_contact_tags_delete",
    args_schema=CalendarsContactTagsDeleteRequest,
    method="POST",
    url_template="v1/calendars/contact-tags/delete",
    description="Delete a contact tag from the calendar.",
    action_label="Delete Contact Tag",
)

calendars_contact_tags_apply = _luma(
    name="calendars_contact_tags_apply",
    args_schema=CalendarsContactTagsApplyRequest,
    method="POST",
    url_template="v1/calendars/contact-tags/apply",
    description="Apply a tag to existing calendar contacts. This will not create new contacts.",
    action_label="Apply Contact Tag",
)

calendars_contact_tags_unapply = _luma(
    name="calendars_contact_tags_unapply",
    args_schema=CalendarsContactTagsUnapplyRequest,
    method="POST",
    url_template="v1/calendars/contact-tags/unapply",
    description="Unapply a tag from calendar contacts. Only affects existing contacts.",
    action_label="Unapply Contact Tag",
)

calendars_event_tags_create = _luma(
    name="calendars_event_tags_create",
    args_schema=CalendarsEventTagsCreateRequest,
    method="POST",
    url_template="v1/calendars/event-tags/create",
    description="Create an event tag on the calendar. Returns its ID.",
    action_label="Create Event Tag",
)

calendars_event_tags_update = _luma(
    name="calendars_event_tags_update",
    args_schema=CalendarsEventTagsUpdateRequest,
    method="POST",
    url_template="v1/calendars/event-tags/update",
    description="Rename an event tag or change its color.",
    action_label="Update Event Tag",
)

calendars_event_tags_delete = _luma(
    name="calendars_event_tags_delete",
    args_schema=CalendarsEventTagsDeleteRequest,
    method="POST",
    url_template="v1/calendars/event-tags/delete",
    description="Delete an event tag from the calendar.",
    action_label="Delete Event Tag",
)

calendars_event_tags_apply = _luma(
    name="calendars_event_tags_apply",
    args_schema=CalendarsEventTagsApplyRequest,
    method="POST",
    url_template="v1/calendars/event-tags/apply",
    description="Apply a tag to events on the calendar.",
    action_label="Apply Event Tag",
)

calendars_event_tags_unapply = _luma(
    name="calendars_event_tags_unapply",
    args_schema=CalendarsEventTagsUnapplyRequest,
    method="POST",
    url_template="v1/calendars/event-tags/unapply",
    description="Unapply a tag from events on the calendar.",
    action_label="Unapply Event Tag",
)

calendars_events_add = _luma(
    name="calendars_events_add",
    args_schema=CalendarsEventsAddRequest,
    method="POST",
    url_template="v1/calendars/events/add",
    description=(
        "Add or submit an existing event (on Luma or on an external platform) to the "
        "Luma calendar. By default, events added by a calendar manager are approved "
        'immediately. Use `submission_mode: "pending"` to keep the submission pending.\n'
        "\n"
        "On calendars with `require-manage-access`, submitting a Luma event you manage "
        "can also grant the target calendar manage access once the submission is "
        "approved."
    ),
    action_label="Add Event",
)

calendars_events_approve = _luma(
    name="calendars_events_approve",
    args_schema=CalendarsEventsApproveRequest,
    method="POST",
    url_template="v1/calendars/events/approve",
    description=(
        "Approve a pending event submission on your calendar. The event becomes visible"
        " on the calendar and the submitter is notified."
    ),
    action_label="Approve Event",
)

calendars_events_reject = _luma(
    name="calendars_events_reject",
    args_schema=CalendarsEventsRejectRequest,
    method="POST",
    url_template="v1/calendars/events/reject",
    description=(
        "Reject a pending event submission on your calendar. The submitter is only "
        "emailed when you pass `notify_submitter: true` or a `message`."
    ),
    action_label="Reject Event",
)

images_create_upload_url = _luma(
    name="images_create_upload_url",
    args_schema=ImagesCreateUploadUrlRequest,
    method="POST",
    url_template="v1/images/create-upload-url",
    description=(
        "Get a URL to upload a JPEG or PNG to Luma's CDN. PUT the image to the returned"
        " upload_url, then use file_url as an event's cover_url or in its "
        "description_md."
    ),
    action_label="Create Upload URL",
)

events_ticket_types_create = _luma(
    name="events_ticket_types_create",
    args_schema=EventsTicketTypesCreateRequest,
    method="POST",
    url_template="v1/events/ticket-types/create",
    description=(
        "Create a new ticket type for an event. Paid ticket types require the calendar "
        "to have a connected Stripe account."
    ),
    action_label="Create Ticket Type",
)

events_ticket_types_update = _luma(
    name="events_ticket_types_update",
    args_schema=EventsTicketTypesUpdateRequest,
    method="POST",
    url_template="v1/events/ticket-types/update",
    description="Update an existing ticket type configuration",
    action_label="Update Ticket Type",
)

events_ticket_types_delete = _luma(
    name="events_ticket_types_delete",
    args_schema=EventsTicketTypesDeleteRequest,
    method="POST",
    url_template="v1/events/ticket-types/delete",
    description=(
        "Soft delete a ticket type. Guests already registered with it keep their "
        "tickets. Cannot delete the last visible ticket type."
    ),
    action_label="Delete Ticket Type",
)

events_blasts_create = _luma(
    name="events_blasts_create",
    args_schema=EventsBlastsCreateRequest,
    method="POST",
    url_template="v1/events/blasts/create",
    description=(
        "Email a message to an event's guests now, or at `scheduled_for`. Blasts go out"
        " in the background, count against the calendar's send limit, and can't be "
        "recalled once sent. Returns the blast with `status: scheduled` until it's "
        "sent. Limited to 10 blasts per 5 minutes."
    ),
    action_label="Create Blast",
)

events_blasts_update = _luma(
    name="events_blasts_update",
    args_schema=EventsBlastsUpdateRequest,
    method="POST",
    url_template="v1/events/blasts/update",
    description=(
        "Edit a blast. Only the fields you pass change. Before a blast is sent, "
        "everything can change. After it's sent, only `subject` and `content_md` can, "
        "which updates the post on the event page but not the emails already delivered."
        " Blasts under review can't be edited."
    ),
    action_label="Update Blast",
)

events_blasts_delete = _luma(
    name="events_blasts_delete",
    args_schema=EventsBlastsDeleteRequest,
    method="POST",
    url_template="v1/events/blasts/delete",
    description=(
        "Delete a blast. Deleting a scheduled blast cancels the send. Deleting a sent "
        "blast removes the post from the event page, but the emails already delivered "
        "stay delivered."
    ),
    action_label="Delete Blast",
)

memberships_members_add = _luma(
    name="memberships_members_add",
    args_schema=MembershipsMembersAddRequest,
    method="POST",
    url_template="v1/memberships/members/add",
    description=(
        "Add a user to a membership tier. For paid tiers, set skip_payment to true if "
        "you are handling payment externally."
    ),
    action_label="Add Member to Tier",
)

memberships_members_update_status = _luma(
    name="memberships_members_update_status",
    args_schema=MembershipsMembersUpdateStatusRequest,
    method="POST",
    url_template="v1/memberships/members/update-status",
    description=(
        "Update a member's membership status. Approving a paid tier member captures "
        "their payment. Declining cancels any active subscription."
    ),
    action_label="Update Member Status",
)

webhooks_create = _luma(
    name="webhooks_create",
    args_schema=WebhooksCreateRequest,
    method="POST",
    url_template="v2/webhooks/create",
    description="Create a new webhook endpoint to receive event notifications.",
    action_label="Create Webhook",
)

webhooks_update = _luma(
    name="webhooks_update",
    args_schema=WebhooksUpdateRequest,
    method="POST",
    url_template="v2/webhooks/update",
    description="Update a webhook endpoint's event types or status (active/paused).",
    action_label="Update Webhook",
)

webhooks_delete = _luma(
    name="webhooks_delete",
    args_schema=WebhooksDeleteRequest,
    method="POST",
    url_template="v1/webhooks/delete",
    description="Delete a webhook endpoint.",
    action_label="Delete Webhook",
)

events_cancel_request = _luma(
    name="events_cancel_request",
    args_schema=EventsCancelRequestRequest,
    method="POST",
    url_template="v1/events/cancel/request",
    description=(
        "Request a cancellation token for an event. Canceling an event is irreversible "
        "— it notifies all guests, processes refunds, and permanently deletes the "
        "event. Because of this, cancellation uses a two-step flow: first request a "
        "token here, then pass it to /events/cancel to execute. The token expires after"
        " 15 minutes."
    ),
    action_label="Request Event Cancellation",
)

events_cancel = _luma(
    name="events_cancel",
    args_schema=EventsCancelRequest,
    method="POST",
    url_template="v1/events/cancel",
    description=(
        "Cancel an event. You must first call /events/cancel/request to get a "
        "cancellation_token, then pass it here. This is irreversible — the event will "
        "be deleted, all guests will be notified, and refunds will be processed if "
        "should_refund is true. For paid events, you must specify should_refund."
    ),
    action_label="Cancel Event",
)

calendars_admins_add = _luma(
    name="calendars_admins_add",
    args_schema=CalendarsAdminsAddRequest,
    method="POST",
    url_template="v1/calendars/admins/add",
    description=(
        "Add admins to the calendar. Existing admins are skipped. On a Luma Plus "
        "calendar, adds that need more paid admin seats are rejected — add those admins"
        " in the Luma app, where the seat charge can be confirmed."
    ),
    action_label="Add Calendar Admins",
)

calendars_update = _luma(
    name="calendars_update",
    args_schema=CalendarsUpdateRequest,
    method="POST",
    url_template="v1/calendars/update",
    description=(
        "Update a calendar's settings. Only the provided fields are changed. Pass null "
        "or an empty string to clear the website or a social handle."
    ),
    action_label="Update Calendar",
)

organizations_calendars_create = _luma(
    name="organizations_calendars_create",
    args_schema=OrganizationsCalendarsCreateRequest,
    method="POST",
    url_template="v2/organizations/calendars/create",
    description=(
        "Create a new calendar within the organization. The calendar will be managed by"
        " the API key owner."
    ),
    action_label="Create Calendar",
)

organizations_events_transfer_calendar = _luma(
    name="organizations_events_transfer_calendar",
    args_schema=OrganizationsEventsTransferCalendarRequest,
    method="POST",
    url_template="v1/organizations/events/transfer-calendar",
    description=(
        "Transfer an event from its current managing calendar to a different calendar "
        "within the organization. The event's managing calendar changes to the "
        "destination calendar. Both the source and destination calendars must belong to"
        " the organization."
    ),
    action_label="Transfer Event Calendar",
)

TOOLS: list[Tool] = [
    events_get,
    calendars_get,
    calendars_events_list,
    events_guests_get,
    events_guests_list,
    users_get_self,
    calendars_contact_tags_list,
    calendars_event_tags_list,
    calendars_admins_list,
    entities_lookup,
    places_search,
    images_search,
    calendars_events_lookup,
    calendars_contacts_list,
    events_coupons_list,
    calendars_coupons_list,
    events_ticket_types_list,
    events_ticket_types_get,
    events_blasts_list,
    events_blasts_get,
    memberships_tiers_list,
    webhooks_list,
    webhooks_get,
    organizations_admins_list,
    organizations_calendars_list,
    organizations_events_list,
    events_create,
    events_update,
    events_guests_update_status,
    events_guests_update_tickets,
    events_guests_send_invites,
    events_guests_add,
    events_hosts_add,
    events_hosts_update,
    events_hosts_remove,
    events_coupons_create,
    events_coupons_update,
    calendars_coupons_create,
    calendars_coupons_update,
    calendars_contacts_import,
    calendars_contacts_block,
    calendars_contacts_remove,
    calendars_contacts_restore,
    calendars_contact_tags_create,
    calendars_contact_tags_update,
    calendars_contact_tags_delete,
    calendars_contact_tags_apply,
    calendars_contact_tags_unapply,
    calendars_event_tags_create,
    calendars_event_tags_update,
    calendars_event_tags_delete,
    calendars_event_tags_apply,
    calendars_event_tags_unapply,
    calendars_events_add,
    calendars_events_approve,
    calendars_events_reject,
    images_create_upload_url,
    events_ticket_types_create,
    events_ticket_types_update,
    events_ticket_types_delete,
    events_blasts_create,
    events_blasts_update,
    events_blasts_delete,
    memberships_members_add,
    memberships_members_update_status,
    webhooks_create,
    webhooks_update,
    webhooks_delete,
    events_cancel_request,
    events_cancel,
    calendars_admins_add,
    calendars_update,
    organizations_calendars_create,
    organizations_events_transfer_calendar,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "LUMA_PAGINATION",
    "events_get",
    "calendars_get",
    "calendars_events_list",
    "events_guests_get",
    "events_guests_list",
    "users_get_self",
    "calendars_contact_tags_list",
    "calendars_event_tags_list",
    "calendars_admins_list",
    "entities_lookup",
    "places_search",
    "images_search",
    "calendars_events_lookup",
    "calendars_contacts_list",
    "events_coupons_list",
    "calendars_coupons_list",
    "events_ticket_types_list",
    "events_ticket_types_get",
    "events_blasts_list",
    "events_blasts_get",
    "memberships_tiers_list",
    "webhooks_list",
    "webhooks_get",
    "organizations_admins_list",
    "organizations_calendars_list",
    "organizations_events_list",
    "events_create",
    "events_update",
    "events_guests_update_status",
    "events_guests_update_tickets",
    "events_guests_send_invites",
    "events_guests_add",
    "events_hosts_add",
    "events_hosts_update",
    "events_hosts_remove",
    "events_coupons_create",
    "events_coupons_update",
    "calendars_coupons_create",
    "calendars_coupons_update",
    "calendars_contacts_import",
    "calendars_contacts_block",
    "calendars_contacts_remove",
    "calendars_contacts_restore",
    "calendars_contact_tags_create",
    "calendars_contact_tags_update",
    "calendars_contact_tags_delete",
    "calendars_contact_tags_apply",
    "calendars_contact_tags_unapply",
    "calendars_event_tags_create",
    "calendars_event_tags_update",
    "calendars_event_tags_delete",
    "calendars_event_tags_apply",
    "calendars_event_tags_unapply",
    "calendars_events_add",
    "calendars_events_approve",
    "calendars_events_reject",
    "images_create_upload_url",
    "events_ticket_types_create",
    "events_ticket_types_update",
    "events_ticket_types_delete",
    "events_blasts_create",
    "events_blasts_update",
    "events_blasts_delete",
    "memberships_members_add",
    "memberships_members_update_status",
    "webhooks_create",
    "webhooks_update",
    "webhooks_delete",
    "events_cancel_request",
    "events_cancel",
    "calendars_admins_add",
    "calendars_update",
    "organizations_calendars_create",
    "organizations_events_transfer_calendar",
]
