from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

from .._common import PAGE_TOKEN_DESCRIPTION, USER_ID_DESCRIPTION
from .models import Message, MessageFormat


class MessagesListRequest(BaseModel):
    """Input schema for Gmail `users.messages.list` endpoint.
    
    Lists the messages in the user's mailbox.
    
    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list
    """
    
    # Path parameter
    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    
    # Query parameters
    maxResults: Annotated[
        Optional[int],
        Field(
            100,
            ge=1,
            le=500,
            description="Maximum number of messages to return. This field defaults to 100. The maximum allowed value for this field is 500.",
        ),
        Query(),
    ]
    pageToken: Annotated[
        Optional[str],
        Field(
            None,
            description=PAGE_TOKEN_DESCRIPTION,
        ),
        Query(),
    ]
    q: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only return messages matching the specified query. Supports the same query format as the Gmail search box. "
                "For example, \"from:someuser@example.com rfc822msgid:<somemsgid@example.com> is:unread\". "
                "Parameter cannot be used when accessing the api using the gmail.metadata scope."
            ),
        ),
        Query(),
    ]
    labelIds: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Only return messages with labels that match all of the specified label IDs. Messages in a thread might have labels that other messages in the same thread don't have.",
        ),
        Query(),
    ]
    includeSpamTrash: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include messages from SPAM and TRASH in the results.",
        ),
        Query(),
    ]


class MessagesGetRequest(BaseModel):
    """Input schema for Gmail `users.messages.get` endpoint.

    Gets the specified message.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get
    """

    # Path parameters
    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(
            ...,
            description=(
                "The ID of the message to retrieve. This ID is usually retrieved using messages.list. "
                "The ID is also contained in the result when a message is inserted (messages.insert) "
                "or imported (messages.import)."
            ),
        ),
        Path(),
    ]

    # Query parameters
    format: Annotated[
        Optional[MessageFormat],
        Field(
            None,
            description=(
                "The format to return the message in. Gmail applies 'full' when this is absent. "
                "'minimal' returns only email message ID and labels; does not return the email headers, body, or payload. "
                "'full' returns the full email message data with body content parsed in the payload field; the raw field is not used. "
                "'raw' returns the full email message data with body content in the raw field as a base64url encoded string; "
                "the payload field is not used. "
                "'metadata' returns only email message ID, labels, and email headers. "
                "'full' and 'raw' cannot be used when accessing the api using the gmail.metadata scope."
            ),
        ),
        Query(),
    ]
    metadataHeaders: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "When given and format is METADATA, only include headers specified. "
                "Gmail ignores it under any other format."
            ),
        ),
        Query(),
    ]


class ModifyMessageRequest(BaseModel):
    """
    Request body for Gmail `users.messages.modify` endpoint.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/modify
    """

    add_label_ids: Optional[List[str]] = Field(
        None,
        max_length=100,
        description="A list of IDs of labels to add to this message. You can add up to 100 labels with each update."
    )
    remove_label_ids: Optional[List[str]] = Field(
        None,
        max_length=100,
        description="A list of IDs of labels to remove from this message. You can remove up to 100 labels with each update."
    )



class BatchModifyMessagesRequest(BaseModel):
    """
    Request body for Gmail `users.messages.batchModify` endpoint.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify
    """

    ids: List[str] = Field(
        ...,
        max_length=1000,
        description="The IDs of the messages to modify. There is a limit of 1000 ids per request."
    )
    add_label_ids: Optional[List[str]] = Field(
        None,
        description="A list of label IDs to add to messages."
    )
    remove_label_ids: Optional[List[str]] = Field(
        None,
        description="A list of label IDs to remove from messages."
    )



class MessagesModifyRequest(BaseModel):
    """Input schema for Gmail `users.messages.modify` endpoint.
    
    Modifies the labels on the specified message.
    
    API Reference: https://developers.google.com/gmail/api/reference/rest/v1/users.messages/modify
    """
    
    # Path parameters
    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(
            ...,
            description="The ID of the message to modify.",
        ),
        Path(),
    ]
    
    # Request body
    body: Annotated[
        ModifyMessageRequest,
        Field(..., description="The modify request body."),
        Body(),
    ]
    
    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class MessagesBatchModifyRequest(BaseModel):
    """Input schema for Gmail `users.messages.batchModify` endpoint.
    
    Modifies the labels on the specified messages.
    
    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify
    """
    
    # Path parameter
    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    
    # Request body
    body: Annotated[
        BatchModifyMessagesRequest,
        Field(..., description="The batch modify request body."),
        Body(),
    ]
    
    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class MessagesSendRequest(BaseModel):
    """Input schema for Gmail `users.messages.send`.

    This mirrors the Message resource with minimal required fields. The API accepts
    a `raw` RFC-822 message string, but we expose both a `raw` field and a structured
    `message` for convenience. At least one of them must be provided.
    
    API Reference: https://developers.google.com/gmail/api/reference/rest/v1/users.messages/send
    """

    # Path parameter
    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]

    # Request body (single Body field)
    body: Annotated[
        Message,
        Field(..., description="The email message data."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }
    