# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""The message resource, split where Graph's operations disagree about it.

:class:`MessageContent` is what a caller writes — recipients, subject, body,
flag — and is the whole of a message attached to another one.
:class:`Message` adds what Graph alone sets, marked ``response_only`` so the
model is never offered it, and the three collections a message can only be
given when it is created: file attachments, open extensions and custom Internet
headers. Those carry ``Mode("create")``, so a tool that patches a draft
(``mode="update"``) does not offer them, and Graph does not get the chance to
refuse them.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import Field

from charter.types import Format, Gloss, Mode, WireName
from charter.types.model import PackModel

from ..common import (
    FollowupFlag,
    Importance,
    InferenceClassificationType,
    InternetMessageHeader,
    ItemBody,
    MultiValueLegacyExtendedProperty,
    OpenTypeExtension,
    Recipient,
    SingleValueLegacyExtendedProperty,
)

__all__ = ["FileAttachment", "MessageContent", "Message"]

_TIMESTAMP = (
    "The date and time information uses ISO 8601 format and is always in UTC time. "
    "For example, midnight UTC on Jan 1, 2014 is `2014-01-01T00:00:00Z`."
)


class FileAttachment(PackModel):
    """A file (such as a text file or Word document) attached to a message.

    ``content_bytes`` takes the file's text and is base64-encoded on the way
    out: a model has text to give, not bytes.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/fileattachment
    """

    odata_type: Annotated[
        Literal["#microsoft.graph.fileAttachment"],
        Field("#microsoft.graph.fileAttachment", description="#microsoft.graph.fileAttachment"),
        WireName("@odata.type"),
    ]
    name: str = Field(
        ...,
        description=(
            "The name representing the text that is displayed below the icon representing "
            "the embedded attachment and doesn't need to be the actual file name."
        ),
    )
    content_bytes: Annotated[
        str,
        Field(..., description="The base64-encoded contents of the file."),
        Format("base64"),
        Gloss(
            "Give the file's text as it is. It is base64-encoded on the way out; encoding it yourself sends it twice."
        ),
    ]
    content_type: Optional[str] = Field(None, description="The content type of the attachment.")
    content_id: Optional[str] = Field(
        None, description="The ID of the attachment in the Exchange store."
    )
    is_inline: Optional[bool] = Field(
        None, description="Set to `true` if the attachment is an inline attachment."
    )


class MessageContent(PackModel):
    """The writable properties of a message.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/message#properties
    """

    bcc_recipients: Optional[List[Recipient]] = Field(
        None, description="The Bcc: recipients for the message."
    )
    body: Optional[ItemBody] = Field(
        None,
        description="The body of the message. It can be in HTML or text format.",
    )
    categories: Optional[List[str]] = Field(
        None, description="The categories associated with the message."
    )
    cc_recipients: Optional[List[Recipient]] = Field(
        None, description="The Cc: recipients for the message."
    )
    flag: Optional[FollowupFlag] = Field(
        None,
        description=(
            "Indicates the status, start date, due date, or completion date for the message."
        ),
    )
    from_: Annotated[
        Optional[Recipient],
        Field(
            None,
            description=(
                "The owner of the mailbox from which the message is sent. In most cases, "
                "this value is the same as the sender property, except for sharing or "
                "delegation scenarios. The value must correspond to the actual mailbox used."
            ),
        ),
        WireName("from"),
    ]
    importance: Optional[Importance] = Field(
        None,
        description="The importance of the message. The possible values are: `low`, `normal`, and `high`.",
    )
    inference_classification: Optional[InferenceClassificationType] = Field(
        None,
        description=(
            "The classification of the message for the user, based on inferred relevance "
            "or importance, or on an explicit override. The possible values are: `focused` "
            "or `other`."
        ),
    )
    internet_message_id: Optional[str] = Field(
        None, description="The message ID in the format specified by RFC2822."
    )
    is_delivery_receipt_requested: Optional[bool] = Field(
        None, description="Indicates whether a read receipt is requested for the message."
    )
    is_read: Optional[bool] = Field(
        None, description="Indicates whether the message has been read."
    )
    is_read_receipt_requested: Optional[bool] = Field(
        None, description="Indicates whether a read receipt is requested for the message."
    )
    reply_to: Optional[List[Recipient]] = Field(
        None, description="The email addresses to use when replying."
    )
    sender: Optional[Recipient] = Field(
        None,
        description=(
            "The account that is used to generate the message. In most cases, this value "
            "is the same as the from property. You can set this property to a different "
            "value when sending a message from a shared mailbox, for a shared calendar, or "
            "as a delegate. In any case, the value must correspond to the actual mailbox used."
        ),
    )
    subject: Optional[str] = Field(None, description="The subject of the message.")
    to_recipients: Optional[List[Recipient]] = Field(
        None, description="The To: recipients for the message."
    )


class Message(MessageContent):
    """A message in a mailFolder.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/message
    """

    # --- writable, beyond the content -------------------------------------
    single_value_extended_properties: Optional[List[SingleValueLegacyExtendedProperty]] = Field(
        None,
        description=(
            "The collection of single-value extended properties defined for the message. Nullable."
        ),
    )
    multi_value_extended_properties: Optional[List[MultiValueLegacyExtendedProperty]] = Field(
        None,
        description=(
            "The collection of multi-value extended properties defined for the message. Nullable."
        ),
    )

    # --- only when the message is created ----------------------------------
    attachments: Annotated[
        Optional[List[FileAttachment]],
        Field(None, description="The fileAttachment attachments for the message."),
        Mode("create"),
    ]
    extensions: Annotated[
        Optional[List[OpenTypeExtension]],
        Field(
            None, description="The collection of open extensions defined for the message. Nullable."
        ),
        Mode("create"),
    ]
    internet_message_headers: Annotated[
        Optional[List[InternetMessageHeader]],
        Field(
            None,
            description=(
                "A collection of message headers defined by RFC5322. The set includes "
                "message headers indicating the network path taken by a message from the "
                "sender to the recipient. It can also contain custom message headers that "
                "hold app data for the message. Requires `$select` to retrieve."
            ),
        ),
        Mode("create"),
    ]

    # --- set by Graph ------------------------------------------------------
    id: Annotated[
        Optional[str],
        Field(None, description="Unique identifier for the message."),
        Mode("response_only"),
    ]
    body_preview: Annotated[
        Optional[str],
        Field(
            None,
            description="The first 255 characters of the message body. It is in text format.",
        ),
        Mode("response_only"),
    ]
    change_key: Annotated[
        Optional[str],
        Field(None, description="The version of the message."),
        Mode("response_only"),
    ]
    conversation_id: Annotated[
        Optional[str],
        Field(None, description="The ID of the conversation the email belongs to."),
        Mode("response_only"),
    ]
    conversation_index: Annotated[
        Optional[str],
        Field(None, description="Indicates the position of the message within the conversation."),
        Mode("response_only"),
    ]
    created_date_time: Annotated[
        Optional[str],
        Field(None, description=f"The date and time the message was created. {_TIMESTAMP}"),
        Mode("response_only"),
    ]
    has_attachments: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Indicates whether the message has attachments. This property doesn't "
                "include inline attachments, so if a message contains only inline "
                "attachments, this property is false."
            ),
        ),
        Mode("response_only"),
    ]
    is_draft: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Indicates whether the message is a draft. A message is a draft if it "
                "hasn't been sent yet."
            ),
        ),
        Mode("response_only"),
    ]
    last_modified_date_time: Annotated[
        Optional[str],
        Field(None, description=f"The date and time the message was last changed. {_TIMESTAMP}"),
        Mode("response_only"),
    ]
    parent_folder_id: Annotated[
        Optional[str],
        Field(None, description="The unique identifier for the message's parent mailFolder."),
        Mode("response_only"),
    ]
    received_date_time: Annotated[
        Optional[str],
        Field(None, description=f"The date and time the message was received. {_TIMESTAMP}"),
        Mode("response_only"),
    ]
    sent_date_time: Annotated[
        Optional[str],
        Field(None, description=f"The date and time the message was sent. {_TIMESTAMP}"),
        Mode("response_only"),
    ]
    unique_body: Annotated[
        Optional[ItemBody],
        Field(
            None,
            description=(
                "The part of the body of the message that is unique to the current message. "
                "uniqueBody is not returned by default but can be retrieved for a given "
                "message by use of the `?$select=uniqueBody` query. It can be in HTML or "
                "text format."
            ),
        ),
        Mode("response_only"),
    ]
    web_link: Annotated[
        Optional[str],
        Field(None, description="The URL to open the message in Outlook on the web."),
        Mode("response_only"),
    ]
