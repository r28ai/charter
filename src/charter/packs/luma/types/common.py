# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Models shared by the luma requests: the spec's component schemas and the
objects it declares inline, one class per shape.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field, model_validator

from charter.types import Gloss, Mode
from charter.types.model import PackModel

__all__ = [
    "GeoAddressJsonManual",
    "GeoAddressJsonGoogle",
    "GeoAddressJsonLookup",
    "Source",
    "RegistrationQuestionAgreeCheck",
    "RegistrationQuestionCompany",
    "RegistrationQuestionGithub",
    "RegistrationQuestionInstagram",
    "RegistrationQuestionLinkedin",
    "RegistrationQuestionPhoneNumber",
    "RegistrationQuestionSelect",
    "RegistrationQuestionTelegram",
    "RegistrationQuestionText",
    "RegistrationQuestionTwitter",
    "RegistrationQuestionUrl",
    "RegistrationQuestionYoutube",
    "TermsLink",
    "TermsText",
    "Terms",
    "RegistrationQuestionTerms",
    "FeedbackEmail",
    "TicketTypeCreateInput",
    "EventTaxConfig",
    "TicketsToAddItem",
    "EventsGuestsSendInvitesGuest",
    "RegistrationAnswerInputValue",
    "RegistrationAnswerInput",
    "EventsGuestsAddGuest",
    "Ticket",
    "DiscountPercent",
    "Currency",
    "DiscountAmount",
    "CalendarsEventsAddBodyExternalGeoAddressJson",
    "CalendarsEventsAddBodyExternal",
    "CalendarsEventsAddBodyLuma",
    "BlastRecipientGroupInputStatus",
    "BlastRecipientGroupInput",
    "RegistrationAnswerAgreeCheck",
    "RegistrationAnswerCompany",
    "RegistrationAnswerPhoneNumber",
    "RegistrationAnswerSelect",
    "RegistrationAnswerSelect2",
    "RegistrationAnswerTerms",
    "QuestionType",
    "RegistrationAnswerGithub",
    "RegistrationAnswerUrl",
    "LocationGoogle",
    "LocationLookup",
    "EventDefaultsFeedbackEmail",
    "Visibility",
    "EventDefaults",
    "SortDirection",
    "ApprovalStatus",
    "SortColumn",
    "MembershipStatus",
    "CalendarsContactsListSortColumn",
    "Font",
    "GeoAddressJson",
    "RegistrationQuestion",
    "Theme",
    "Status",
    "EventsGuestsAddApprovalStatus",
    "AccessLevel",
    "Discount",
    "Color",
    "CalendarsEventsAddBody",
    "EventType",
    "LaunchStatus",
    "Location",
    "OrganizationsCalendarsCreateLocation",
]


class GeoAddressJsonManual(PackModel):
    """Stores the address text as-is, without geocoding."""

    type: Annotated[
        Literal["manual"],
        Field(...),
    ]
    address: Annotated[
        str,
        Field(...),
    ]


class GeoAddressJsonGoogle(PackModel):
    """Resolves a Google Maps Place ID into a full address."""

    type: Annotated[
        Literal["google"],
        Field(...),
    ]
    place_id: Annotated[
        str,
        Field(...),
    ]
    description: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                'Extra directions shown alongside the address, e.g. "Suite 36" or '
                '"Enter through the side door".'
            ),
        ),
    ]


class GeoAddressJsonLookup(PackModel):
    """Searches Google Maps for `query` and uses the top result. If nothing matches, the query is stored as a manual address."""

    type: Annotated[
        Literal["lookup"],
        Field(...),
    ]
    query: Annotated[
        str,
        Field(..., min_length=1),
    ]
    description: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                'Extra directions shown alongside the address, e.g. "Suite 36" or '
                '"Enter through the side door".'
            ),
        ),
    ]


class Source(PackModel):
    """Declared inline in the spec: ``RegistrationQuestionAgreeCheck.source``."""

    type: Annotated[
        Literal["calendar"],
        Field(...),
    ]
    calendar_api_id: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]


class RegistrationQuestionAgreeCheck(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_agree-check``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["agree-check"],
        Field(...),
    ]


class RegistrationQuestionCompany(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_company``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["company"],
        Field(...),
    ]
    collect_job_title: Annotated[
        Optional[bool],
        Field(None),
    ]
    job_title_label: Annotated[
        Optional[str],
        Field(None),
    ]


class RegistrationQuestionGithub(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_github``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["github"],
        Field(...),
    ]


class RegistrationQuestionInstagram(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_instagram``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["instagram"],
        Field(...),
    ]


class RegistrationQuestionLinkedin(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_linkedin``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["linkedin"],
        Field(...),
    ]


class RegistrationQuestionPhoneNumber(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_phone-number``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["phone-number"],
        Field(...),
    ]


class RegistrationQuestionSelect(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_select``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["select"],
        Field(...),
    ]
    options: Annotated[
        List[str],
        Field(..., max_length=250),
    ]
    multiple: Annotated[
        Optional[bool],
        Field(None, description="When true, guests can pick more than one option."),
    ]


class RegistrationQuestionTelegram(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_telegram``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["telegram"],
        Field(...),
    ]


class RegistrationQuestionText(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_text``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["text"],
        Field(...),
    ]
    multiline: Annotated[
        Optional[bool],
        Field(None, description="When true, guests get a multi-line text area."),
    ]


class RegistrationQuestionTwitter(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_twitter``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["twitter"],
        Field(...),
    ]


class RegistrationQuestionUrl(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_url``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["url"],
        Field(...),
    ]


class RegistrationQuestionYoutube(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_youtube``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    source: Annotated[
        Optional[Source],
        Field(
            None,
            description=(
                "Send `null` to detach a library copy so it no longer follows the library."
            ),
        ),
    ]
    question_type: Annotated[
        Literal["youtube"],
        Field(...),
    ]


class TermsLink(PackModel):
    """Declared inline in the spec: ``RegistrationQuestionTerms.terms_link``."""

    content_type: Annotated[
        Literal["link"],
        Field(...),
    ]
    url: Annotated[
        str,
        Field(...),
    ]
    collect_signature: Annotated[
        bool,
        Field(...),
    ]


class TermsText(PackModel):
    """Declared inline in the spec: ``RegistrationQuestionTerms.terms_text``."""

    content_type: Annotated[
        Literal["text"],
        Field(...),
    ]
    content_md: Annotated[
        str,
        Field(
            ...,
            description=(
                "Markdown content for the terms. Luma converts this to rich text internally."
            ),
        ),
    ]
    collect_signature: Annotated[
        bool,
        Field(...),
    ]
    require_review: Annotated[
        Optional[bool],
        Field(None, description="When true, guests must open the hosted terms before accepting."),
    ]


Terms = Union[TermsText, TermsLink]


class RegistrationQuestionTerms(PackModel):
    """Declared inline in the spec: ``RegistrationQuestion.RegistrationQuestion_terms``."""

    id: Annotated[
        str,
        Field(...),
    ]
    label: Annotated[
        str,
        Field(...),
    ]
    required: Annotated[
        bool,
        Field(...),
    ]
    question_type: Annotated[
        Literal["terms"],
        Field(...),
    ]
    terms: Annotated[
        Terms,
        Field(...),
    ]


class FeedbackEmail(PackModel):
    """Settings for the post-event feedback email sent to guests. If not specified on create, inherits from calendar defaults."""

    enabled: Annotated[
        bool,
        Field(..., description="Whether to send the feedback email."),
    ]
    delay: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "How long after the event ends to send the feedback email. Defaults to "
                "PT0M (immediately). Maximum is P30D. A negative duration (e.g. -PT30M)"
                " sends it before the event ends — at most P1D before, and never before"
                " the event starts."
            ),
        ),
    ]


class TicketTypeCreateInput(PackModel):
    """``TicketTypeCreateInput`` in the spec."""

    name: Annotated[
        str,
        Field(..., min_length=1, max_length=30),
    ]
    require_approval: Annotated[
        Optional[bool],
        Field(None),
    ]
    is_hidden: Annotated[
        Optional[bool],
        Field(None),
    ]
    description: Annotated[
        Optional[str],
        Field(None, max_length=1000),
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
    ]
    max_capacity: Annotated[
        Optional[float],
        Field(None),
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
    ]
    type: Annotated[
        Literal["free", "paid"],
        Field(...),
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
    ]
    currency: Annotated[
        Optional[str],
        Field(
            None, description="ISO 4217 currency code like `usd`. Required for paid ticket types."
        ),
    ]
    is_flexible: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Pay-what-you-want pricing: guests choose an amount of at least `min_cents`."
            ),
        ),
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
    ]


class EventTaxConfig(PackModel):
    """``EventTaxConfig`` in the spec."""

    tax_percent: Annotated[
        float,
        Field(...),
    ]
    tax_name: Annotated[
        str,
        Field(..., min_length=2, max_length=30),
    ]


class TicketsToAddItem(PackModel):
    """Declared inline in the spec: ``EventsGuestsUpdateTicketsRequest.tickets_to_addItem``."""

    event_ticket_type_id: Annotated[
        str,
        Field(..., description="Ticket type ID, this usually starts with ttype-"),
    ]


class EventsGuestsSendInvitesGuest(PackModel):
    """Declared inline in the spec: ``EventsGuestsSendInvitesRequest.guest``."""

    email: Annotated[
        str,
        Field(...),
    ]
    name: Annotated[
        Optional[str],
        Field(None),
    ]


class RegistrationAnswerInputValue(PackModel):
    """Declared inline in the spec: ``RegistrationAnswerInput.value``."""

    company: Annotated[
        Optional[str],
        Field(None),
    ]
    job_title: Annotated[
        Optional[str],
        Field(None),
    ]


class RegistrationAnswerInput(PackModel):
    """``RegistrationAnswerInput`` in the spec."""

    question_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "ID of one of the event's registration questions. Question IDs are "
                "returned in the `registration_questions` field of Get Event."
            ),
        ),
    ]
    value: Annotated[
        Union[str, bool, List[str], RegistrationAnswerInputValue],
        Field(
            ...,
            description=(
                "The guest's answer. Use a string for `text` (including multiline "
                "text), `select` without `multiple: true`, `url`, `phone-number`, and "
                "social handles; an array of strings for `select` with `multiple: "
                "true`; a boolean for `agree-check`; and an object with `company` and "
                "`job_title` for `company` questions."
            ),
        ),
    ]


class EventsGuestsAddGuest(PackModel):
    """Information about the guests you want to add to the event. If a user already has a name, this will not overwrite their name."""

    email: Annotated[
        str,
        Field(...),
    ]
    name: Annotated[
        Optional[str],
        Field(None),
    ]
    registration_answers: Annotated[
        Optional[List[RegistrationAnswerInput]],
        Field(
            None,
            description=(
                "Optional. The guest's answers to the event's registration questions. "
                "If the guest is already registered with answers, their existing "
                "answers are kept."
            ),
        ),
    ]


class Ticket(PackModel):
    """Declared inline in the spec: ``EventsGuestsAddRequest.ticket``."""

    event_ticket_type_id: Annotated[
        str,
        Field(...),
    ]


class DiscountPercent(PackModel):
    """Declared inline in the spec: ``EventsCouponsCreateRequest.discount_percent``."""

    discount_type: Annotated[
        Literal["percent"],
        Field(...),
    ]
    percent_off: Annotated[
        float,
        Field(..., ge=0, le=100),
    ]


Currency = Literal[
    "solana_sol",
    "solana_usdc",
    "aed",
    "afn",
    "all",
    "amd",
    "ang",
    "aoa",
    "ars",
    "aud",
    "awg",
    "azn",
    "bam",
    "bbd",
    "bdt",
    "bgn",
    "bhd",
    "bif",
    "bmd",
    "bnd",
    "bob",
    "brl",
    "bsd",
    "bwp",
    "byn",
    "bzd",
    "cad",
    "cdf",
    "chf",
    "clp",
    "cny",
    "cop",
    "crc",
    "cve",
    "czk",
    "djf",
    "dkk",
    "dop",
    "dzd",
    "egp",
    "etb",
    "eur",
    "fjd",
    "fkp",
    "gbp",
    "gel",
    "ghs",
    "gip",
    "gmd",
    "gnf",
    "gtq",
    "gyd",
    "hkd",
    "hnl",
    "htg",
    "huf",
    "idr",
    "ils",
    "inr",
    "isk",
    "jmd",
    "jod",
    "jpy",
    "kes",
    "kgs",
    "khr",
    "kmf",
    "krw",
    "kwd",
    "kyd",
    "kzt",
    "lak",
    "lbp",
    "lkr",
    "lrd",
    "lsl",
    "mad",
    "mdl",
    "mga",
    "mkd",
    "mmk",
    "mnt",
    "mop",
    "mur",
    "mvr",
    "mwk",
    "mxn",
    "myr",
    "mzn",
    "nad",
    "ngn",
    "nio",
    "nok",
    "npr",
    "nzd",
    "omr",
    "pab",
    "pen",
    "pgk",
    "php",
    "pkr",
    "pln",
    "pyg",
    "qar",
    "ron",
    "rsd",
    "rub",
    "rwf",
    "sar",
    "sbd",
    "scr",
    "sek",
    "sgd",
    "shp",
    "sle",
    "sos",
    "srd",
    "std",
    "szl",
    "thb",
    "tjs",
    "tnd",
    "top",
    "try",
    "ttd",
    "twd",
    "tzs",
    "uah",
    "ugx",
    "usd",
    "uyu",
    "uzs",
    "vnd",
    "vuv",
    "wst",
    "xaf",
    "xcd",
    "xof",
    "xpf",
    "yer",
    "zar",
    "zmw",
]


class DiscountAmount(PackModel):
    """Declared inline in the spec: ``EventsCouponsCreateRequest.discount_amount``."""

    discount_type: Annotated[
        Literal["amount"],
        Field(...),
    ]
    cents_off: Annotated[
        float,
        Field(..., ge=0),
    ]
    currency: Annotated[
        Currency,
        Field(...),
    ]


CalendarsEventsAddBodyExternalGeoAddressJson = Union[
    GeoAddressJsonManual, GeoAddressJsonGoogle, GeoAddressJsonLookup
]


class CalendarsEventsAddBodyExternal(PackModel):
    """Declared inline in the spec: ``CalendarsEventsAdd.body_external``."""

    platform: Annotated[
        Literal["external"],
        Field(...),
    ]
    submission_mode: Annotated[
        Optional[Literal["auto", "pending"]],
        Field(
            None,
            description=(
                "`auto` approves the event immediately. `pending` keeps the event "
                "pending for calendar admin approval."
            ),
        ),
        Gloss("Defaults to `auto` when omitted."),
    ]
    url: Annotated[
        str,
        Field(...),
    ]
    name: Annotated[
        str,
        Field(...),
    ]
    start_at: Annotated[
        str,
        Field(..., description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
    ]
    duration_interval: Annotated[
        str,
        Field(..., description="ISO 8601 Duration. For example, PT2H"),
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
    ]
    geo_address_json: Annotated[
        Optional[CalendarsEventsAddBodyExternalGeoAddressJson],
        Field(None),
    ]
    host: Annotated[
        Optional[str],
        Field(None),
    ]


class CalendarsEventsAddBodyLuma(PackModel):
    """Declared inline in the spec: ``CalendarsEventsAdd.body_luma``."""

    platform: Annotated[
        Literal["luma"],
        Field(...),
    ]
    submission_mode: Annotated[
        Optional[Literal["auto", "pending"]],
        Field(
            None,
            description=(
                "`auto` approves the event immediately. `pending` keeps the event "
                "pending for calendar admin approval."
            ),
        ),
        Gloss("Defaults to `auto` when omitted."),
    ]
    event_id: Annotated[
        Optional[str],
        Field(None, description="Event ID, this usually starts with evt-"),
    ]
    event_api_id: Annotated[
        Optional[str],
        Field(None, description="Use `event_id` instead."),
        Mode("disabled"),
    ]


BlastRecipientGroupInputStatus = Literal[
    "approved", "checked_in", "pending_approval", "waitlist", "invited"
]


class BlastRecipientGroupInput(PackModel):
    """``BlastRecipientGroupInput`` in the spec."""

    status: Annotated[
        BlastRecipientGroupInputStatus,
        Field(
            ..., description="`approved` means going; `checked_in` means checked in at the event."
        ),
    ]
    event_ticket_type_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only guests holding a valid ticket of this type. Omit to reach every "
                "ticket type. Can't be combined with `invited`, since invitees hold no "
                "tickets."
            ),
        ),
    ]

    @model_validator(mode="after")
    def _invitees_hold_no_tickets(self) -> BlastRecipientGroupInput:
        """Luma: "Can't be combined with `invited`, since invitees hold no tickets." """
        if self.status == "invited" and self.event_ticket_type_id is not None:
            raise ValueError(
                "event_ticket_type_id cannot be combined with status: invited, since "
                "invitees hold no tickets. Drop event_ticket_type_id to reach every invitee."
            )
        return self


class RegistrationAnswerAgreeCheck(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_agree-check``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        bool,
        Field(...),
    ]
    question_type: Annotated[
        Literal["agree-check"],
        Field(...),
    ]


class RegistrationAnswerCompany(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_company``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        RegistrationAnswerInputValue,
        Field(...),
    ]
    question_type: Annotated[
        Literal["company"],
        Field(...),
    ]


class RegistrationAnswerPhoneNumber(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_phone-number``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        str,
        Field(...),
    ]
    question_type: Annotated[
        Literal["phone-number"],
        Field(...),
    ]


class RegistrationAnswerSelect(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_select``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        str,
        Field(...),
    ]
    question_type: Annotated[
        Literal["select"],
        Field(...),
    ]
    multiple: Annotated[
        Optional[Literal[False]],
        Field(None),
    ]


class RegistrationAnswerSelect2(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_select_2``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        List[str],
        Field(...),
    ]
    question_type: Annotated[
        Literal["select"],
        Field(...),
    ]
    multiple: Annotated[
        Literal[True],
        Field(...),
    ]


class RegistrationAnswerTerms(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_terms``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        Union[str, Literal[True]],
        Field(...),
    ]
    question_type: Annotated[
        Literal["terms"],
        Field(...),
    ]


QuestionType = Literal["github", "instagram", "linkedin", "telegram", "text", "twitter", "youtube"]


class RegistrationAnswerGithub(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_github``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        str,
        Field(...),
    ]
    question_type: Annotated[
        QuestionType,
        Field(...),
    ]
    multiline: Annotated[
        Optional[bool],
        Field(None),
    ]


class RegistrationAnswerUrl(PackModel):
    """Declared inline in the spec: ``MembershipsMembersAddRequest.registration_answer_url``."""

    label: Annotated[
        str,
        Field(...),
    ]
    question_id: Annotated[
        str,
        Field(...),
    ]
    value: Annotated[
        str,
        Field(...),
    ]
    question_type: Annotated[
        Literal["url"],
        Field(...),
    ]


class LocationGoogle(PackModel):
    """Resolves a Google Maps Place ID for a city."""

    type: Annotated[
        Literal["google"],
        Field(...),
    ]
    place_id: Annotated[
        str,
        Field(..., min_length=1),
    ]


class LocationLookup(PackModel):
    """Searches Google Maps for a city matching `query` (e.g. "Miami Beach, FL") and uses the top result."""

    type: Annotated[
        Literal["lookup"],
        Field(...),
    ]
    query: Annotated[
        str,
        Field(..., min_length=1),
    ]


class EventDefaultsFeedbackEmail(PackModel):
    """Whether new events send the post-event feedback email. Each event can override this with its own `feedback_email`."""

    enabled: Annotated[
        bool,
        Field(...),
    ]


Visibility = Literal["public", "members-only", "private"]


class EventDefaults(PackModel):
    """Settings new events on this calendar start with. Only the provided fields change, and existing events aren't affected. `visibility: 'members-only'` requires a membership tier on the calendar."""

    visibility: Annotated[
        Optional[Visibility],
        Field(
            None,
            description=(
                "Visibility of new events. `members-only` requires a membership tier on"
                " the calendar."
            ),
        ),
    ]
    show_guest_list: Annotated[
        Optional[bool],
        Field(None, description="Whether new events show their guest list."),
    ]
    feedback_email: Annotated[
        Optional[EventDefaultsFeedbackEmail],
        Field(
            None,
            description=(
                "Whether new events send the post-event feedback email. Each event can "
                "override this with its own `feedback_email`."
            ),
        ),
    ]


SortDirection = Literal["asc", "desc", "asc nulls last", "desc nulls last"]


ApprovalStatus = Literal[
    "approved", "session", "pending_approval", "invited", "declined", "waitlist"
]


SortColumn = Literal["name", "email", "created_at", "registered_at", "checked_in_at"]


MembershipStatus = Literal["approved", "pending", "approved-pending-payment", "declined"]


CalendarsContactsListSortColumn = Literal[
    "created_at", "event_checked_in_count", "event_approved_count", "name", "revenue_usd_cents"
]


Font = Literal[
    "alternate",
    "alverata",
    "avant-garde",
    "beaufort",
    "berkeley",
    "blithe",
    "caslon",
    "degular",
    "departure",
    "factoria",
    "futura",
    "garamond",
    "geist-mono",
    "google",
    "ivy-mode",
    "ivy-presto",
    "museo",
    "neuzeit",
    "new-spirit",
    "poster",
    "roc-grotesk",
    "season",
    "snpro",
    "strenuous",
    "pearl",
]


GeoAddressJson = Union[GeoAddressJsonManual, GeoAddressJsonGoogle, GeoAddressJsonLookup]


RegistrationQuestion = Union[
    RegistrationQuestionAgreeCheck,
    RegistrationQuestionCompany,
    RegistrationQuestionGithub,
    RegistrationQuestionInstagram,
    RegistrationQuestionLinkedin,
    RegistrationQuestionPhoneNumber,
    RegistrationQuestionSelect,
    RegistrationQuestionTelegram,
    RegistrationQuestionText,
    RegistrationQuestionTwitter,
    RegistrationQuestionUrl,
    RegistrationQuestionYoutube,
    RegistrationQuestionTerms,
]


Theme = Literal[
    "standard",
    "cross",
    "diamond",
    "falling-leaves",
    "fireworks",
    "floral",
    "grain-dark",
    "grain-light",
    "grid",
    "bats",
    "holiday-diwali",
    "holiday-foliage",
    "holiday-hanukkah",
    "holiday-pie",
    "holiday-santa",
    "holiday-sweater",
    "holiday-turkey",
    "hypnotic",
    "celebrate-dark",
    "celebrate-light",
    "clouds",
    "impressionist",
    "starry",
    "aurora",
    "rain-dark",
    "rain-light",
    "arcade",
    "seaside-dark",
    "seaside-light",
    "paper-dark",
    "paper-light",
    "tiles-dark",
    "tiles-light",
    "rothko-dark",
    "rothko-light",
    "riso-dark",
    "riso-light",
    "pegboard-dark",
    "pegboard-light",
    "glass-dark",
    "glass-light",
    "knit-dark",
    "knit-light",
    "denim-dark",
    "denim-light",
    "banknote-dark",
    "banknote-light",
    "life",
    "matrix",
    "particles-bokeh",
    "particles-champagne",
    "plus",
    "iridescent-dark",
    "iridescent-light",
    "polkadot",
    "pool-dark",
    "pool-light",
    "snake",
    "blocks",
    "snow-dark",
    "snow-light",
    "space-war",
    "sunny-shades",
    "tamagotchi",
    "warp",
    "wave",
    "zigzag",
]


Status = Literal["approved", "declined", "pending_approval", "waitlist"]


EventsGuestsAddApprovalStatus = Literal["approved", "pending_approval", "waitlist"]


AccessLevel = Literal["none", "check-in", "manager"]


Discount = Union[DiscountPercent, DiscountAmount]


Color = Literal["cranberry", "barney", "red", "green", "blue", "purple", "yellow", "orange"]


CalendarsEventsAddBody = Union[CalendarsEventsAddBodyExternal, CalendarsEventsAddBodyLuma]


EventType = Literal[
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
]


LaunchStatus = Literal["launched", "coming-soon", "archived"]


Location = Union[LocationGoogle, LocationLookup]


OrganizationsCalendarsCreateLocation = Union[LocationGoogle, LocationLookup]
