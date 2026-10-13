# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for a message's attachments: list, read, add, delete.

An attachment is a file, an Outlook item, or a link. Graph creates the first
two through ``POST .../attachments`` and the third through no v1.0 method at
all, so the body here is a two-member union discriminated on ``@odata.type``.
An attached item is modelled as a message; attaching an event or a contact as
an item is not, because those resources belong to the calendar and people APIs.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from charter.types import Body, Path, Query, WireName
from charter.types.model import PackModel

from .._common import MESSAGE_ID_DESCRIPTION
from .._odata import NextLink, Select
from ..common import AttachmentType
from ..messages.models import FileAttachment, MessageContent

__all__ = [
    "AttachedMessage",
    "AttachmentIdRequest",
    "AttachmentItem",
    "AttachmentsGetRequest",
    "AttachmentsCreateRequest",
    "AttachmentsListRequest",
    "ItemAttachment",
    "UploadSessionCreateRequest",
]

MessageId = Annotated[str, Field(..., description=MESSAGE_ID_DESCRIPTION), Path()]
AttachmentId = Annotated[str, Field(..., description="The attachment ID."), Path()]


class AttachedMessage(MessageContent):
    """A message attached to another message, as the item of an itemAttachment.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/itemattachment
    """

    odata_type: Annotated[
        Literal["microsoft.graph.message"],
        Field("microsoft.graph.message", description="microsoft.graph.message"),
        WireName("@odata.type"),
    ]


class ItemAttachment(PackModel):
    """A contact, event, or message that's attached to a user event, message, or post.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/itemattachment
    """

    odata_type: Annotated[
        Literal["#microsoft.graph.itemAttachment"],
        Field("#microsoft.graph.itemAttachment", description="#microsoft.graph.itemAttachment"),
        WireName("@odata.type"),
    ]
    name: str = Field(..., description="The display name of the attachment.")
    item: AttachedMessage = Field(..., description="The attached message or event.")
    content_type: Optional[str] = Field(None, description="The content type of the attachment.")
    is_inline: Optional[bool] = Field(
        None,
        description=(
            "Set to true if the attachment is inline, such as an embedded image within the "
            "body of the item."
        ),
    )


class AttachmentsListRequest(PackModel):
    """Retrieve a list of attachment objects attached to a message.

    No ``$top`` or ``$filter``: Graph accepts both here and returns every
    attachment anyway, so a model asking for one by name would be handed all of
    them as if they matched. ``$select`` is honoured.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0
    """

    message_id: MessageId
    select: Select
    next_link: NextLink


class AttachmentIdRequest(PackModel):
    """Name one attachment: to get its raw contents, or to delete it.

    API Reference: https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0
    """

    message_id: MessageId
    attachment_id: AttachmentId


class AttachmentsGetRequest(AttachmentIdRequest):
    """Read the properties of an attachment; ``$expand`` reaches an attached item.

    API Reference: https://learn.microsoft.com/en-us/graph/api/attachment-get?view=graph-rest-1.0
    """

    select: Select
    expand: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Use `$expand` to get the properties of an item attachment (contact, event, "
                "or message), for example `microsoft.graph.itemattachment/item`."
            ),
        ),
        Query(),
        WireName("$expand"),
    ]


class AttachmentsCreateRequest(PackModel):
    """Add an attachment to a message. The attachment must be under 3 MB.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-post-attachments?view=graph-rest-1.0
    """

    message_id: MessageId
    # FileAttachment first: the runtime's transform pass reads a union through
    # its first member, and that is the member with a field to transform. Not a
    # pydantic discriminated union: the LLM view gives `@odata.type` several
    # accepted spellings, which a discriminator cannot be. Each member's
    # `@odata.type` is a one-value Literal, so only one of them can validate.
    attachment: Annotated[
        Union[FileAttachment, ItemAttachment],
        Field(
            ...,
            description="A JSON representation of the attachment object: a file or an item.",
        ),
        Body(),
    ]


class AttachmentItem(PackModel):
    """Attributes of an item to be attached through an upload session.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/attachmentitem
    """

    attachment_type: AttachmentType = Field(
        ...,
        description="The type of attachment. The possible values are: `file`, `item`, `reference`. Required.",
    )
    name: str = Field(
        ...,
        description=(
            "The display name of the attachment. This can be a descriptive string and "
            "doesn't have to be the actual file name. Required."
        ),
    )
    size: int = Field(..., ge=0, description="The length of the attachment in bytes. Required.")
    content_id: Optional[str] = Field(
        None,
        description=(
            "The CID or Content-Id of the attachment for referencing for the in-line "
            'attachments using the `<img src="cid:contentId">` tag in HTML messages. Optional.'
        ),
    )
    content_type: Optional[str] = Field(
        None, description="The nature of the data in the attachment. Optional."
    )
    is_inline: Optional[bool] = Field(
        None,
        description="`true` if the attachment is an inline attachment; otherwise, `false`. Optional.",
    )


class UploadSessionCreateRequest(PackModel):
    """Create an upload session to attach a file of 3 MB to 150 MB to a message.

    API Reference: https://learn.microsoft.com/en-us/graph/api/attachment-createuploadsession?view=graph-rest-1.0
    """

    message_id: MessageId
    attachment_item: Annotated[
        AttachmentItem,
        Field(
            ...,
            description=(
                "Represents attributes of the item to be uploaded and attached. At minimum, "
                "specify the attachment type (`file`), a name, and the size of the file."
            ),
        ),
        Body(envelop=True),
        WireName("AttachmentItem"),
    ]
