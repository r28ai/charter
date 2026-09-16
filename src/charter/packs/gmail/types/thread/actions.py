from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

from .._common import PAGE_TOKEN_DESCRIPTION, USER_ID_DESCRIPTION
from .models import Format


class ThreadsListRequest(BaseModel):
    """Input schema for the Gmail `users.threads.list` endpoint.

    API: https://developers.google.com/gmail/api/reference/rest/v1/users.threads/list
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
            10,
            ge=1,
            le=500,
            description="Maximum number of threads to return (default 100, max 500).",
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
            description="Only return threads matching this Gmail search query string.",
        ),
        Query(),
    ]
    labelIds: Annotated[
        Optional[List[str]],
        Field(None, description="Return only threads with all of these label IDs."),
        Query(),
    ]
    includeSpamTrash: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include threads from SPAM and TRASH in the results.",
        ),
        Query(),
    ]

class ThreadsGetRequest(BaseModel):
    """Input schema for the Gmail `users.threads.get` endpoint.

    API: https://developers.google.com/gmail/api/reference/rest/v1/users.threads/get
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
        Field(..., description="The unique ID of the Gmail thread to retrieve."),
        Path(),
    ]

    # Query parameters
    format: Annotated[
        Optional[Format],
        Field(
            None,
            description="The format to return the messages in.",
        ),
        Query(),
    ]
    metadataHeaders: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="When format is 'METADATA', only include these headers in the response.",
        ),
        Query(),
    ]


class ModifyThreadRequest(BaseModel):
    """
    Request body for Gmail `users.threads.modify` endpoint.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/modify
    """

    add_label_ids: Optional[List[str]] = Field(
        None,
        max_length=100,
        description="A list of IDs of labels to add to this thread. You can add up to 100 labels with each update."
    )
    remove_label_ids: Optional[List[str]] = Field(
        None,
        max_length=100,
        description="A list of IDs of labels to remove from this thread. You can remove up to 100 labels with each update."
    )


class ThreadsModifyRequest(BaseModel):
    """Input schema for the Gmail `users.threads.modify` endpoint.

    Modifies the labels applied to the thread. This applies to all messages in
    the thread.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/modify
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
        Field(..., description="The ID of the thread to modify."),
        Path(),
    ]

    # Request body
    body: Annotated[
        ModifyThreadRequest,
        Field(..., description="The modify request body."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class ThreadsTrashRequest(BaseModel):
    """Input schema for the Gmail `users.threads.trash` endpoint.

    Moves the specified thread to the trash. Any messages that belong to the
    thread are also moved to the trash.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/trash
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
        Field(..., description="The ID of the thread to Trash."),
        Path(),
    ]


class ThreadsUntrashRequest(BaseModel):
    """Input schema for the Gmail `users.threads.untrash` endpoint.

    Removes the specified thread from the trash. Any messages that belong to
    the thread are also removed from the trash.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/untrash
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
        Field(..., description="The ID of the thread to remove from Trash."),
        Path(),
    ]


class ThreadsDeleteRequest(BaseModel):
    """Input schema for the Gmail `users.threads.delete` endpoint.

    Immediately and permanently deletes the specified thread. Any messages that
    belong to the thread are also deleted. This operation cannot be undone.
    Prefer `threads_trash` instead.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.threads/delete
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
        Field(..., description="ID of the Thread to delete."),
        Path(),
    ]
