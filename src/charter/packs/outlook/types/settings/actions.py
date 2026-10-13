# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for mailbox settings, and the languages and time zones they accept.

Mailbox settings cannot be created or deleted, only read and patched, and two
of the properties Graph returns — ``archiveFolder`` and ``userPurpose`` — are
not among the seven the update accepts, so they are withheld from the model.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from charter.types import Body, Gloss, Mode, Path, WireName
from charter.types.model import PackModel

from ..common import DateTimeTimeZone, DayOfWeek

__all__ = [
    "AutomaticRepliesSetting",
    "CustomTimeZone",
    "DaylightTimeZoneOffset",
    "LocaleInfo",
    "MailboxSettings",
    "MailboxSettingsGetRequest",
    "MailboxSettingsUpdateRequest",
    "NoArgumentsRequest",
    "StandardTimeZoneOffset",
    "SupportedTimeZonesRequest",
    "TimeZoneBase",
    "WorkingHours",
]

AutomaticRepliesStatus = Literal["disabled", "alwaysEnabled", "scheduled"]
ExternalAudienceScope = Literal["none", "contactsOnly", "all"]
DelegateMeetingMessageDeliveryOptions = Literal[
    "sendToDelegateAndInformationToPrincipal",
    "sendToDelegateAndPrincipal",
    "sendToDelegateOnly",
]
UserPurpose = Literal[
    "user", "linked", "shared", "room", "equipment", "others", "unknownFutureValue"
]

# Graph's own example spelling of an Edm.TimeOfDay. A bare `08` is refused with
# "Cannot convert the literal '08' to the expected type 'Edm.TimeOfDay'".
_TIME_OF_DAY = Gloss("A time of day written HH:MM:SS.fffffff, for example `08:00:00.0000000`.")


class AutomaticRepliesSetting(PackModel):
    """Configuration settings to automatically notify the sender of an incoming email with a message from the signed-in user.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/automaticrepliessetting
    """

    external_audience: Optional[ExternalAudienceScope] = Field(
        None,
        description=(
            "The set of audience external to the signed-in user's organization who will "
            "receive the ExternalReplyMessage, if Status is AlwaysEnabled or Scheduled. The "
            "possible values are: `none`, `contactsOnly`, `all`."
        ),
    )
    external_reply_message: Optional[str] = Field(
        None,
        description=(
            "The automatic reply to send to the specified external audience, if Status is "
            "AlwaysEnabled or Scheduled."
        ),
    )
    internal_reply_message: Optional[str] = Field(
        None,
        description=(
            "The automatic reply to send to the audience internal to the signed-in user's "
            "organization, if Status is AlwaysEnabled or Scheduled."
        ),
    )
    scheduled_end_date_time: Optional[DateTimeTimeZone] = Field(
        None,
        description="The date and time that automatic replies are set to end, if Status is set to Scheduled.",
    )
    scheduled_start_date_time: Optional[DateTimeTimeZone] = Field(
        None,
        description="The date and time that automatic replies are set to begin, if Status is set to Scheduled.",
    )
    status: Optional[AutomaticRepliesStatus] = Field(
        None,
        description=(
            "Configurations status for automatic replies. The possible values are: "
            "`disabled`, `alwaysEnabled`, `scheduled`."
        ),
    )


class LocaleInfo(PackModel):
    """Information about the locale, including the preferred language and country/region, of the signed-in user.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/localeinfo
    """

    locale: Optional[str] = Field(
        None,
        description=(
            "A locale representation for the user, which includes the user's preferred "
            'language and country/region. For example, "en-us". The language component '
            "follows 2-letter codes as defined in ISO 639-1, and the country component "
            "follows 2-letter codes as defined in ISO 3166-1 alpha-2."
        ),
    )
    # Graph refuses it in an update — "The property name 'DisplayName' is read
    # only and not settable", against the live API — so the model is not offered
    # it, and writing back the language it read is refused here, naming the field,
    # rather than by a 400.
    display_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A name representing the user's locale in natural language, for example, "
                '"English (United States)".'
            ),
        ),
        Mode("response_only"),
    ]


class StandardTimeZoneOffset(PackModel):
    """Represents the start time of standard time in a time zone.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/standardtimezoneoffset
    """

    day_occurrence: Optional[int] = Field(
        None,
        description=(
            "Represents the nth occurrence of the day of week that the transition from "
            "daylight saving time to standard time occurs."
        ),
    )
    day_of_week: Optional[DayOfWeek] = Field(
        None,
        description=(
            "Represents the day of the week when the transition from daylight saving time to "
            "standard time."
        ),
    )
    month: Optional[int] = Field(
        None,
        ge=1,
        le=12,
        description=(
            "Represents the month of the year when the transition from daylight saving time "
            "to standard time occurs."
        ),
    )
    time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Represents the time of day when the transition from daylight saving time to "
                "standard time occurs."
            ),
        ),
        _TIME_OF_DAY,
    ]
    year: Optional[int] = Field(
        None,
        description=(
            "Represents how frequently in terms of years the change from daylight saving "
            "time to standard time occurs. For example, a value of 0 means every year."
        ),
    )


class DaylightTimeZoneOffset(PackModel):
    """Represents the start time of daylight saving time in a time zone.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/daylighttimezoneoffset
    """

    daylight_bias: Optional[int] = Field(
        None,
        description=(
            "The time offset from Coordinated Universal Time (UTC) for daylight saving time. "
            "This value is in minutes."
        ),
    )
    day_occurrence: Optional[int] = Field(
        None,
        description=(
            "Represents the nth occurrence of the day of week that the transition from "
            "standard time to daylight saving time occurs."
        ),
    )
    day_of_week: Optional[DayOfWeek] = Field(
        None,
        description=(
            "Represents the day of the week when the transition from standard time to "
            "daylight saving time occurs."
        ),
    )
    month: Optional[int] = Field(
        None,
        ge=1,
        le=12,
        description=(
            "Represents the month of the year when the transition from standard time to "
            "daylight saving time occurs."
        ),
    )
    time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Represents the time of day when the transition from standard time to daylight "
                "saving time occurs."
            ),
        ),
        _TIME_OF_DAY,
    ]
    year: Optional[int] = Field(
        None,
        description=(
            "Represents how frequently in terms of years the change from standard time to "
            "daylight saving time occurs. For example, a value of 0 means every year."
        ),
    )


class TimeZoneBase(PackModel):
    """The basic representation of a time zone.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/timezonebase
    """

    odata_type: Annotated[
        Literal["#microsoft.graph.timeZoneBase"],
        Field("#microsoft.graph.timeZoneBase", description="#microsoft.graph.timeZoneBase"),
        WireName("@odata.type"),
    ]
    name: Optional[str] = Field(
        None,
        description=(
            "The name of a time zone. It can be a standard time zone name such as "
            '"Hawaii-Aleutian Standard Time", or "Customized Time Zone" for a custom time zone.'
        ),
    )


class CustomTimeZone(PackModel):
    """Represents a time zone where the transition from standard to daylight saving time, or vice versa is not standard.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/customtimezone
    """

    odata_type: Annotated[
        Literal["#microsoft.graph.customTimeZone"],
        Field("#microsoft.graph.customTimeZone", description="#microsoft.graph.customTimeZone"),
        WireName("@odata.type"),
    ]
    bias: Optional[int] = Field(
        None,
        description=(
            "The time offset of the time zone from Coordinated Universal Time (UTC). This "
            "value is in minutes. Time zones that are ahead of UTC have a positive offset; "
            "time zones that are behind UTC have a negative offset."
        ),
    )
    daylight_offset: Optional[DaylightTimeZoneOffset] = Field(
        None,
        description="Specifies when the time zone switches from standard time to daylight saving time.",
    )
    name: Optional[str] = Field(None, description="The name of the custom time zone.")
    standard_offset: Optional[StandardTimeZoneOffset] = Field(
        None,
        description="Specifies when the time zone switches from daylight saving time to standard time.",
    )


class WorkingHours(PackModel):
    """Represents the days of the week and hours in a specific time zone that the user works.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/workinghours
    """

    days_of_week: Optional[List[DayOfWeek]] = Field(
        None, description="The days of the week on which the user works."
    )
    end_time: Annotated[
        Optional[str],
        Field(None, description="The time of the day that the user stops working."),
        _TIME_OF_DAY,
    ]
    start_time: Annotated[
        Optional[str],
        Field(None, description="The time of the day that the user starts working."),
        _TIME_OF_DAY,
    ]
    time_zone: Optional[Union[TimeZoneBase, CustomTimeZone]] = Field(
        None, description="The time zone to which the working hours apply."
    )


class MailboxSettings(PackModel):
    """Settings for the primary mailbox of a user.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/mailboxsettings
    """

    automatic_replies_setting: Optional[AutomaticRepliesSetting] = Field(
        None,
        description=(
            "Configuration settings to automatically notify the sender of an incoming email "
            "with a message from the signed-in user. You can set such notifications for only "
            "a future date range."
        ),
    )
    date_format: Optional[str] = Field(None, description="The date format for the user's mailbox.")
    delegate_meeting_message_delivery_options: Optional[DelegateMeetingMessageDeliveryOptions] = (
        Field(
            None,
            description=(
                "If the user has a calendar delegate, this specifies whether the delegate, "
                "mailbox owner, or both receive meeting messages and meeting responses. The "
                "possible values are: `sendToDelegateAndInformationToPrincipal`, "
                "`sendToDelegateAndPrincipal`, `sendToDelegateOnly`."
            ),
        )
    )
    language: Optional[LocaleInfo] = Field(
        None,
        description=(
            "The locale information for the user, including the preferred language and "
            "country/region."
        ),
    )
    time_format: Optional[str] = Field(None, description="The time format for the user's mailbox.")
    time_zone: Optional[str] = Field(
        None, description="The default time zone for the user's mailbox."
    )
    working_hours: Optional[WorkingHours] = Field(
        None, description="The hours, days of a week, and time zone that the user works."
    )
    archive_folder: Annotated[
        Optional[str],
        Field(None, description="Folder ID of an archive folder for the user."),
        Mode("response_only"),
    ]
    user_purpose: Annotated[
        Optional[UserPurpose],
        Field(
            None,
            description=(
                "The purpose of the mailbox. Differentiates a mailbox for a single user from a "
                "shared mailbox and equipment mailbox in Exchange Online."
            ),
        ),
        Mode("response_only"),
    ]


class NoArgumentsRequest(PackModel):
    """A request that takes no arguments at all: the path is the whole of it.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0
    """


class MailboxSettingsGetRequest(PackModel):
    """Get the user's mailboxSettings. You can view all mailbox settings, or get specific settings.

    No ``$select``: Graph answers with every setting whatever it names, so a
    model offered one asks for less and is handed the lot. Specific settings are
    separate paths (``/me/mailboxSettings/timeZone``), not a query option.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-get-mailboxsettings?view=graph-rest-1.0
    """


class MailboxSettingsUpdateRequest(PackModel):
    """Enable, configure, or disable one or more settings as part of a user's mailboxSettings.

    You cannot create or delete any mailbox settings.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-update-mailboxsettings?view=graph-rest-1.0
    """

    settings: Annotated[
        MailboxSettings,
        Field(..., description="The values for the relevant properties that should be updated."),
        Body(),
    ]


class SupportedTimeZonesRequest(PackModel):
    """Get the list of time zones that are supported for the user, as configured on the user's mailbox server.

    API Reference: https://learn.microsoft.com/en-us/graph/api/outlookuser-supportedtimezones?view=graph-rest-1.0
    """

    time_zone_standard: Annotated[
        Optional[Literal["Windows", "Iana"]],
        Field(
            None,
            description=(
                "A time zone format. Supported values are: `Windows`, and `Iana`. Optional; "
                "the Windows format is the default."
            ),
        ),
        Path(),
    ]
