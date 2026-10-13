# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""The complex types and enumerations several Outlook resources share.

Enumerations are taken from the Microsoft Graph v1.0 CSDL
(https://graph.microsoft.com/v1.0/$metadata), which is what Graph validates
against; descriptions are the reference pages' own.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, List, Literal, Optional

from pydantic import ConfigDict, Field, model_validator

from charter.types import Gloss, WireName
from charter.types.model import PackModel

__all__ = [
    "AttachmentType",
    "BodyType",
    "CategoryColor",
    "DateTimeTimeZone",
    "DayOfWeek",
    "EmailAddress",
    "ExchangeIdFormat",
    "FollowupFlag",
    "FollowupFlagStatus",
    "Importance",
    "InferenceClassificationType",
    "InternetMessageHeader",
    "ItemBody",
    "MultiValueLegacyExtendedProperty",
    "OpenTypeExtension",
    "Recipient",
    "SingleValueLegacyExtendedProperty",
]

# https://learn.microsoft.com/en-us/graph/api/resources/message#properties
Importance = Literal["low", "normal", "high"]
# https://learn.microsoft.com/en-us/graph/api/resources/itembody
BodyType = Literal["text", "html"]
# https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassificationoverride
InferenceClassificationType = Literal["focused", "other"]
# https://learn.microsoft.com/en-us/graph/api/resources/followupflag
FollowupFlagStatus = Literal["notFlagged", "complete", "flagged"]
# https://learn.microsoft.com/en-us/graph/api/resources/outlookcategory — `none`
# and the 25 presets, which Outlook maps to Red, Orange, Brown, ... DarkCranberry.
CategoryColor = Literal[
    "none",
    "preset0",
    "preset1",
    "preset2",
    "preset3",
    "preset4",
    "preset5",
    "preset6",
    "preset7",
    "preset8",
    "preset9",
    "preset10",
    "preset11",
    "preset12",
    "preset13",
    "preset14",
    "preset15",
    "preset16",
    "preset17",
    "preset18",
    "preset19",
    "preset20",
    "preset21",
    "preset22",
    "preset23",
    "preset24",
]
# https://learn.microsoft.com/en-us/graph/api/resources/workinghours
DayOfWeek = Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
# https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem
AttachmentType = Literal["file", "item", "reference"]
# https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids#exchangeidformat-values
ExchangeIdFormat = Literal["entryId", "ewsId", "immutableEntryId", "restId", "restImmutableEntryId"]


class EmailAddress(PackModel):
    """The name and email address of a contact or message recipient.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/emailaddress
    """

    address: str = Field(..., description="The email address of the person or entity.")
    name: Optional[str] = Field(None, description="The display name of the person or entity.")


class Recipient(PackModel):
    """Represents information about a user in the sending or receiving end of an event, message or group post.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/recipient
    """

    email_address: EmailAddress = Field(..., description="The recipient's email address.")


class ItemBody(PackModel):
    """Represents properties of the body of an item, such as a message, event or group post.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/itembody
    """

    content: Optional[str] = Field(None, description="The content of the item.")
    content_type: Optional[BodyType] = Field(
        None, description="The type of the content. Possible values are `text` and `html`."
    )


class DateTimeTimeZone(PackModel):
    """Describes the date, time, and time zone of a point in time.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/datetimetimezone
    """

    date_time: str = Field(
        ...,
        description=(
            "A single point of time in a combined date and time representation "
            "(`{date}T{time}`; for example, `2017-08-29T04:00:00.0000000`)."
        ),
    )
    time_zone: Optional[str] = Field(
        None,
        description=(
            'Represents a time zone, for example, "Pacific Standard Time". '
            "See below for more possible values."
        ),
    )


class FollowupFlag(PackModel):
    """Allows setting a flag in an item for the user to follow up on later.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/followupflag
    """

    completed_date_time: Optional[DateTimeTimeZone] = Field(
        None, description="The date and time that the follow-up was finished."
    )
    due_date_time: Optional[DateTimeTimeZone] = Field(
        None,
        description=(
            "The date and time that the follow-up is to be finished. Note: To set the due "
            "date, you must also specify the `startDateTime`; otherwise, you get a "
            "`400 Bad Request` response."
        ),
    )
    flag_status: Optional[FollowupFlagStatus] = Field(
        None,
        description=(
            "The status for follow-up for an item. Possible values are `notFlagged`, "
            "`complete`, and `flagged`."
        ),
    )
    start_date_time: Optional[DateTimeTimeZone] = Field(
        None, description="The date and time that the follow-up is to begin."
    )

    @model_validator(mode="after")
    def _due_needs_a_start(self) -> FollowupFlag:
        if self.due_date_time is not None and self.start_date_time is None:
            raise ValueError("dueDateTime needs startDateTime too; Graph answers 400 without it")
        return self


class InternetMessageHeader(PackModel):
    """A key-value pair that represents an Internet message header, as defined by RFC5322.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/internetmessageheader
    """

    name: str = Field(..., description="Represents the key in a key-value pair.")
    value: str = Field(..., description="The value in a key-value pair.")


_EXTENDED_PROPERTY_ID = (
    "For each property in the collection, specify this to identify the property. It "
    "must follow one of the supported formats. See Outlook extended properties "
    "overview for more information. Required."
)

# The id formats are on the extended properties overview, two pages from the
# operations that need them. A model guessing at them writes a plain name.
_ID_FORMAT = Gloss(
    "An id reads `{type} {guid} Name {name}`, for example "
    "`String {66f5a359-4659-4830-9070-00047ec6ac6e} Name Color`; a multi-value type "
    "ends in Array, as in `StringArray`."
)


class SingleValueLegacyExtendedProperty(PackModel):
    """An extended property that contains a single value.

    API Reference: https://learn.microsoft.com/en-us/graph/api/singlevaluelegacyextendedproperty-post-singlevalueextendedproperties
    """

    id: Annotated[str, Field(..., description=_EXTENDED_PROPERTY_ID), _ID_FORMAT]
    value: str = Field(
        ...,
        description=(
            "For each property in the singleValueExtendedProperties collection, specify "
            "the property value. Required."
        ),
    )


class MultiValueLegacyExtendedProperty(PackModel):
    """An extended property that contains a collection of values.

    API Reference: https://learn.microsoft.com/en-us/graph/api/multivaluelegacyextendedproperty-post-multivalueextendedproperties
    """

    id: Annotated[str, Field(..., description=_EXTENDED_PROPERTY_ID), _ID_FORMAT]
    value: List[str] = Field(
        ...,
        description=(
            "For each property in the multiValueExtendedProperties collection, specify "
            "the property value. Required."
        ),
    )


class OpenTypeExtension(PackModel):
    """An open extension: an extension name and any custom name-value pairs.

    Graph stores the custom data as the extension's own properties, beside
    ``extensionName``, so they are extra fields here rather than a nested
    object. Their names are data, not field names, and travel exactly as
    written — this model's keys are spelled as-is, which is why the two it
    declares carry their wire names.

    API Reference: https://learn.microsoft.com/en-us/graph/api/opentypeextension-post-opentypeextension
    """

    __case__: ClassVar[str] = "snake"

    odata_type: Annotated[
        Literal["microsoft.graph.openTypeExtension"],
        Field("microsoft.graph.openTypeExtension", description="microsoft.graph.openTypeExtension"),
        WireName("@odata.type"),
    ]
    extension_name: Annotated[
        str,
        Field(..., description="A unique text identifier for an open type data extension."),
        WireName("extensionName"),
    ]

    model_config = ConfigDict(extra="allow")
