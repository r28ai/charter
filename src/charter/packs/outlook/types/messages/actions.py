# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for the message operations, one per Graph operation.

Two shapes Graph uses here are declared on the operation rather than split into
tools. Listing and creating messages are served at ``/me/messages`` and at
``/me/mailFolders/{id}/messages``: one tool each, with an optional
``folder_id``, and the runtime picks the route. And seven operations take their
body as JSON *or* as a base64 MIME document: the ``mime`` field is
``Body(media_type="text/plain")``, which makes it the whole body when set and
excludes the JSON fields beside it.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Format, Gloss, Header, Path, Query, WireName
from charter.types.model import PackModel

from .._common import FOLDER_ID_DESCRIPTION, MESSAGE_ID_DESCRIPTION
from .._odata import Count, DeltaLink, Expand, NextLink, OrderBy, Select
from ..common import Recipient
from .models import Message

__all__ = [
    "MessageForwardRequest",
    "MessageIdRequest",
    "MessageMoveRequest",
    "MessageReplyRequest",
    "MessagesCreateRequest",
    "MessagesDeltaRequest",
    "MessagesGetRequest",
    "MessagesListRequest",
    "MessagesUpdateRequest",
    "SendMailRequest",
]

MessageId = Annotated[str, Field(..., description=MESSAGE_ID_DESCRIPTION), Path()]
FolderId = Annotated[str, Field(..., description=FOLDER_ID_DESCRIPTION), Path()]

MessagesTop = Annotated[
    Optional[int],
    Field(
        None,
        ge=1,
        le=1000,
        description=(
            "Use the $top query parameter to specify the number of items to be included in "
            "the result. The default page size is 10 messages. Use `$top` to customize the "
            "page size, within the range of 1 and 1000."
        ),
    ),
    Query(),
    WireName("$top"),
]

_MIME = Annotated[
    Optional[str],
    Field(
        None,
        description=(
            "The MIME content, with the applicable Internet message headers, all encoded "
            "in base64 format in the request body."
        ),
    ),
    Format("mime_base64"),
    Body(media_type="text/plain"),
]


def _has_body(message: Optional[BaseModel]) -> bool:
    return message is not None and getattr(message, "body", None) is not None


# -----------------------------------------------------
# Read
# -----------------------------------------------------


class MessagesListRequest(PackModel):
    """List the messages in the signed-in user's mailbox, or in one of its folders.

    Without ``folder_id`` the list spans the whole mailbox, including the
    Deleted Items and Clutter folders.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0
    """

    folder_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                FOLDER_ID_DESCRIPTION + " Omit it to get the messages in the whole mailbox, "
                "including the Deleted Items and Clutter folders."
            ),
        ),
        Path(),
    ]
    top: MessagesTop
    filter: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Use the $filter query parameter to get just a subset of a collection. When "
                "using `$filter` and `$orderby` in the same query to get messages: properties "
                "that appear in `$orderby` must also appear in `$filter`; properties that "
                "appear in `$orderby` are in the same order as in `$filter`; and properties "
                "that are present in `$orderby` appear in `$filter` before any properties "
                "that aren't."
            ),
        ),
        Query(),
        WireName("$filter"),
        Gloss(
            "OData syntax, strings in single quotes with any inside doubled: "
            "`isRead eq false`, `from/emailAddress/address eq 'ada@example.com'`. One "
            "conversation is `conversationId eq '<conversationId>'`."
        ),
    ]
    orderby: OrderBy
    search: Annotated[
        Optional[str],
        Field(
            None,
            pattern=r'^".*"$',
            description=(
                "When you search messages without specifying message properties, the search "
                "targets these default properties: from, subject, and body. Alternatively, "
                "you can search messages by specifying message property names that Keyword "
                "Query Language (KQL) syntax recognizes: attachment, bcc, body, cc, from, "
                "hasAttachment, importance, kind, participants, received, recipients, sent, "
                "size, subject, to. Search results are sorted by the date and time the "
                "message was sent. A `$search` request returns up to 1,000 results."
            ),
        ),
        Query(),
        WireName("$search"),
        Gloss(
            'Wrap the whole query in double quotes, as Graph requires: "pizza" or '
            '"from:ada subject:invoice".'
        ),
    ]
    select: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Use the $select query parameter to return a subset of properties for a "
                "resource. With $select, you can specify a subset or a superset of the "
                "default properties. For example, `from,subject` returns only the from and "
                "subject properties."
            ),
        ),
        Query(),
        WireName("$select"),
        Gloss(
            "A list leaves each message's full body out. Select `uniqueBody` to get each "
            "one's own text — what it adds to the thread, without the quoted history."
        ),
    ]
    expand: Expand
    count: Count
    next_link: NextLink


class MessagesGetRequest(PackModel):
    """Retrieve the properties and relationships of a message object.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-get?view=graph-rest-1.0
    """

    message_id: MessageId
    select: Select
    expand: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Use the $expand query string parameter to include the expanded resource or "
                "collection referenced by a single relationship (navigation property) in "
                "your results."
            ),
        ),
        Query(),
        WireName("$expand"),
        Gloss(
            "`attachments` lists them. This is the one way to get an extended property: "
            "`singleValueExtendedProperties($filter=id eq 'String {guid} Name Color')`, or "
            "`multiValueExtendedProperties(...)` for one that holds an array. Open "
            "extensions need a filter naming one too, or Graph answers 400: "
            "`extensions($filter=id eq 'com.contoso.roster')`."
        ),
    ]


class MessageIdRequest(PackModel):
    """A request that names one message and sends nothing else.

    Shared by getting a message's MIME content, sending a draft, deleting and
    permanently deleting.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/message
    """

    message_id: MessageId


class MessagesDeltaRequest(PackModel):
    """Get a set of messages added, deleted, or updated in a specified folder.

    The first call returns the folder's messages a page at a time; the last
    page carries a ``delta_link`` instead of a ``next_link``. Pass that back as
    ``next_link`` on a later call to get only what changed since.

    ``$top`` is deliberately absent: on a delta round it does not size the page,
    it ends the round, and the messages past it are never returned.
    ``max_page_size`` is the page size.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0
    """

    folder_id: FolderId
    change_type: Annotated[
        Optional[Literal["created", "updated", "deleted"]],
        Field(
            None,
            description=(
                "A custom query option to filter the delta response based on the type of "
                "change. Supported values are `created`, `updated`, or `deleted`."
            ),
        ),
        Query(),
    ]
    select: Select
    # Not `$top`, which Graph lists among the options delta supports. On a delta
    # round it ends the round: `$top=2` on a folder of twelve messages returned two
    # and a delta link, and following that link returned nothing, so the other ten
    # were never delivered. The page size is the `Prefer` header the reference
    # gives, which pages through all twelve.
    max_page_size: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "The maximum number of messages in each page of the response, sent as "
                "the `Prefer: odata.maxpagesize={x}` request header."
            ),
        ),
        Header("Prefer", template="odata.maxpagesize={}"),
        Gloss(
            "The page size, not a limit: the round still returns every message, a page at a time."
        ),
    ]
    filter: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The only supported `$filter` expressions are "
                "`$filter=receivedDateTime+ge+{value}` or `$filter=receivedDateTime+gt+{value}`."
            ),
        ),
        Query(),
        WireName("$filter"),
    ]
    orderby: Annotated[
        Optional[Literal["receivedDateTime desc"]],
        Field(
            None,
            description=(
                "The only supported `$orderby` expression is `$orderby=receivedDateTime+desc`. "
                "If you don't include an `$orderby` expression, the return order is not "
                "guaranteed."
            ),
        ),
        Query(),
        WireName("$orderby"),
    ]
    next_link: DeltaLink


# -----------------------------------------------------
# Write
# -----------------------------------------------------


class MessagesCreateRequest(PackModel):
    """Create a draft of a new message in either JSON or MIME format.

    By default, this operation saves the draft in the Drafts folder;
    ``folder_id`` creates it in another folder. Give either ``message`` or
    ``mime``.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-post-messages?view=graph-rest-1.0
    """

    folder_id: Annotated[
        Optional[str],
        Field(
            None,
            description=FOLDER_ID_DESCRIPTION + " Omit it to save the draft in the Drafts folder.",
        ),
        Path(),
    ]
    message: Annotated[
        Optional[Message],
        Field(None, description="A JSON representation of the message object."),
        Body(),
    ]
    mime: _MIME

    @model_validator(mode="after")
    def _a_message_in_one_format(self) -> MessagesCreateRequest:
        if self.message is None and self.mime is None:
            raise ValueError("give the draft as message (JSON) or as mime")
        return self


class MessagesUpdateRequest(PackModel):
    """Update the properties of a message object.

    Every property is optional: existing properties that aren't included keep
    their previous values. Recipients, subject, body, internetMessageId and the
    extended properties are updatable only while the message is a draft.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-update?view=graph-rest-1.0
    """

    message_id: MessageId
    message: Annotated[
        Message,
        Field(..., description="The values for relevant fields that should be updated."),
        Body(),
    ]


class MessageMoveRequest(PackModel):
    """Move or copy a message to another folder within the user's mailbox.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-move?view=graph-rest-1.0
    """

    message_id: MessageId
    destination_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "The destination folder ID, or a well-known folder name. For a list of "
                "supported well-known folder names, see mailFolder resource type."
            ),
        ),
        Body(),
        Gloss("`archive` is the Archive folder, `deleteditems` is Deleted Items."),
    ]


# -----------------------------------------------------
# Send, reply, forward — JSON or MIME
# -----------------------------------------------------


class SendMailRequest(PackModel):
    """Send the message specified in the request body using either JSON or MIME format.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0
    """

    message: Annotated[
        Optional[Message],
        Field(None, description="The message to send. Required."),
        Body(),
    ]
    save_to_sent_items: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Indicates whether to save the message in Sent Items. Specify it only if the "
                "parameter is false; default is true. Optional."
            ),
        ),
        Body(),
    ]
    mime: _MIME

    @model_validator(mode="after")
    def _a_message_with_recipients(self) -> SendMailRequest:
        if self.mime is not None:
            return self
        if self.message is None:
            raise ValueError("give the message as message (JSON) or as mime")
        m = self.message
        if not (m.to_recipients or m.cc_recipients or m.bcc_recipients):
            raise ValueError(
                "message needs at least one of toRecipients, ccRecipients or bccRecipients"
            )
        return self


class MessageReplyRequest(PackModel):
    """Reply, or reply all, to a message using either JSON or MIME format.

    Serves reply, replyAll, createReply and createReplyAll, which take the same
    parameters. In JSON, give a comment or the reply's own properties.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-reply?view=graph-rest-1.0
    """

    message_id: MessageId
    comment: Annotated[
        Optional[str],
        Field(None, description="A comment to include. Can be an empty string."),
        Body(),
    ]
    message: Annotated[
        Optional[Message],
        Field(None, description="Any writeable properties to update in the reply message."),
        Body(),
    ]
    mime: _MIME

    @model_validator(mode="after")
    def _comment_or_body(self) -> MessageReplyRequest:
        if self.comment is not None and _has_body(self.message):
            raise ValueError(
                "specify either comment or message.body, not both; Graph answers 400 to both"
            )
        return self


class MessageForwardRequest(PackModel):
    """Forward a message using either JSON or MIME format.

    Serves forward and createForward, which take the same parameters. In JSON,
    name the recipients once, in ``to_recipients`` or in ``message``.

    API Reference: https://learn.microsoft.com/en-us/graph/api/message-forward?view=graph-rest-1.0
    """

    message_id: MessageId
    comment: Annotated[
        Optional[str],
        Field(None, description="A comment to include. Can be an empty string."),
        Body(),
    ]
    to_recipients: Annotated[
        Optional[List[Recipient]],
        Field(None, description="The list of recipients."),
        Body(),
    ]
    message: Annotated[
        Optional[Message],
        Field(None, description="Any writeable properties to update in the forwarded message."),
        Body(),
    ]
    mime: _MIME

    @model_validator(mode="after")
    def _graphs_two_exclusions(self) -> MessageForwardRequest:
        if self.mime is not None:
            return self
        if self.comment is not None and _has_body(self.message):
            raise ValueError(
                "specify either comment or message.body, not both; Graph answers 400 to both"
            )
        in_message = self.message is not None and bool(self.message.to_recipients)
        if bool(self.to_recipients) == in_message:
            raise ValueError(
                "specify the recipients once: either toRecipients or message.toRecipients. "
                "Graph answers 400 to both and to neither"
            )
        return self
