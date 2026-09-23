# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Format, Mode

# Gmail's shared `Format` enum, which `users.messages.get` and `users.drafts.get`
# both take. It is spelled `MessageFormat` here because `Format` in this module
# is the Charter marker. `users.threads.get` documents its own narrower set —
# see `thread.models.Format` — so the two are deliberately separate literals.
MessageFormat = Literal["minimal", "full", "raw", "metadata"]


class Header(BaseModel):
    """A single header within an RFC-822 message part.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages#MessagePart
    """

    name: str = Field(
        ..., description="The name of the header before the : separator. For example, To."
    )
    value: str = Field(
        ...,
        description="The value of the header after the : separator. For example, someuser@example.com.",
    )


class MessagePartBody(BaseModel):
    """
    The body of a single MIME message part.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments#MessagePartBody
    """

    attachmentId: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "When present, contains the ID of an external attachment that can be "
                "retrieved in a separate messages.attachments.get request. When not present, "
                "the entire content of the message part body is contained in the data field."
            ),
        ),
        Mode("response_only"),
    ]
    size: Annotated[
        Optional[int],
        Field(
            None,
            description=("Number of bytes for the message part data (encoding notwithstanding)."),
        ),
        Mode("response_only"),
    ]
    data: Annotated[
        str,
        Field(
            ...,
            description=(
                "The body data of a MIME message part as a base64url encoded string."
                " May be empty for MIME container types that have no message body or"
                " when the body data is sent as a separate attachment. An attachment ID is"
                " present if the body data is contained in a separate attachment."
            ),
        ),
        Format("base64url"),
        Mode("response_only"),
    ]


class MessagePart(BaseModel):
    """A single MIME message part."""

    partId: Annotated[
        Optional[str],
        Field(None, description="The immutable ID of the message part."),
        Mode("response_only"),
    ]
    mimeType: Annotated[
        Optional[str],
        Field(None, description="The MIME type of the message part."),
        Mode("response_only"),
    ]
    filename: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The filename of the attachment. "
                "Only present if this message part represents an attachment."
            ),
        ),
        Mode("response_only"),
    ]
    headers: Annotated[
        Optional[List[Header]],
        Field(
            None,
            description=(
                "List of headers on this message part. "
                "For the top-level part representing the entire message payload, "
                "it will contain the standard RFC 2822 email headers such as To, From, and Subject."
            ),
        ),
        Mode("response_only"),
    ]
    body: Annotated[
        Optional[MessagePartBody],
        Field(
            None,
            description=(
                "The message part body for this part, which may be empty for container MIME message parts."
            ),
        ),
        Mode("response_only"),
    ]
    parts: Annotated[
        Optional[List[MessagePart]],
        Field(
            None,
            description=(
                "The child MIME message parts of this part. "
                "This only applies to container MIME message parts, for example multipart/*. "
                "For non- container MIME message part types, such as text/plain, this field is empty. "
                "For more information, see RFC 1521."
            ),
        ),
        Mode("response_only"),
    ]


MessagePart.model_rebuild()


class ClassificationLabelFieldValue(BaseModel):
    """
    Field values for a classification label.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages#Message.ClassificationLabelFieldValue
    """

    fieldId: str = Field(
        ...,
        description="Required. The field ID for the Classification Label Value. Maps to the ID  field of the Google Drive Label.Field object.",
    )
    selection: str = Field(
        ...,
        description="Selection choice ID for the selection option. Should only be set if the  field type is SELECTION in the Google Drive Label.Field object.  Maps to the id field of the Google Drive  Label.Field.SelectionOptions resource.",
    )


class ClassificationLabelValue(BaseModel):
    """
    Classification Labels applied to the email message. Classification Labels are different from Gmail inbox labels.
    Only used for Google Workspace accounts. Learn more about classification labels: https://support.google.com/a/answer/9292382.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages#Message.ClassificationLabelValue
    """

    labelId: str = Field(
        ...,
        description="Required. The canonical or raw alphanumeric classification label ID. Maps to the ID  field of the Google Drive Label resource.",
    )
    fields: List[ClassificationLabelFieldValue] = Field(
        ..., description="Field values for the given classification label ID."
    )


class ListMessagesResponse(BaseModel):
    """
    Response model for users.messages.list.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
    """

    messages: Annotated[
        Optional[List[Message]],
        Field(
            None,
            description="List of messages. Note that each message resource contains only an id and a threadId. Additional message details can be fetched using the messages.get method.",
        ),
        Mode("response_only"),
    ]
    next_page_token: Annotated[
        Optional[str],
        Field(None, description="Token to retrieve the next page of results in the list."),
        Mode("response_only"),
    ]
    result_size_estimate: Annotated[
        Optional[int],
        Field(None, description="Estimated total number of results."),
        Mode("response_only"),
    ]


class Message(BaseModel):
    """
    An email message.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages#Message
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The immutable ID of the message."),
        Mode("response_only"),
    ]
    threadId: Optional[str] = Field(
        None,
        description=(
            "The ID of the thread the message belongs to. To add a message or draft to a thread, the following criteria must be met: "
            "1. The requested threadId must be specified on the Message or Draft.Message you supply with your request. "
            "2. The References and In-Reply-To headers must be set in compliance with the RFC 2822 standard. "
            "3. The Subject headers must match."
        ),
    )
    labelIds: Annotated[
        Optional[List[str]],
        Field(None, description="List of IDs of labels applied to this message."),
        Mode("response_only"),
    ]
    snippet: Annotated[
        Optional[str],
        Field(None, description="A short part of the message text."),
        Mode("response_only"),
    ]
    history_id: Annotated[
        Optional[str],
        Field(None, description="The ID of the last history record that modified this message."),
        Mode("response_only"),
    ]
    internalDate: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The internal message creation timestamp (epoch ms), which determines ordering in the inbox. "
                "For normal SMTP-received email, this represents the time the message was originally accepted by Google, "
                "which is more reliable than the Date header. However, for API-migrated mail, it can be configured by client to be based on the Date header."
            ),
        ),
        Mode("response_only"),
    ]
    payload: Annotated[
        Optional[MessagePart],
        Field(None, description="The parsed email structure in the message parts."),
        Mode("response_only"),
    ]
    sizeEstimate: Annotated[
        Optional[int],
        Field(None, description="Estimated size in bytes of the message."),
        Mode("response_only"),
    ]
    raw: Annotated[
        str,
        Field(
            ...,
            description=(
                "The entire email message in an RFC 2822 formatted and base64url encoded string. "
                "Returned in messages.get and drafts.get responses when the format=RAW parameter is supplied."
            ),
        ),
        Format("rfc822_base64"),
        Mode("request_only"),
    ]
    classificationLabelValues: Annotated[
        Optional[List[ClassificationLabelValue]],
        Field(
            None,
            description=(
                "Classification Label values on the message. Available Classification Label schemas can be queried using the Google Drive Labels API. "
                "Each classification label ID must be unique. If duplicate IDs are provided, only one will be retained, and the selection is arbitrary. "
                "Only used for Google Workspace accounts."
            ),
        ),
        Mode("response_only"),
    ]


ListMessagesResponse.model_rebuild()
