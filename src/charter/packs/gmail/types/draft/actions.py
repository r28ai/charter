from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

from .._common import PAGE_TOKEN_DESCRIPTION, USER_ID_DESCRIPTION
from ..message.models import MessageFormat
from .models import Draft


class SendDraftRequest(BaseModel):
    """Request body for Gmail `users.drafts.send`.

    The endpoint documents its body as a Draft, but the only field it reads is
    the id of the draft to send — the content was fixed when the draft was
    saved. `Draft.id` is `Mode("response_only")` because create and update are
    the operations that would otherwise be offered it, so the send body is
    declared here with the id required instead.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/send
    """

    id: str = Field(..., description="The immutable ID of the draft to send.")


class DraftsCreateRequest(BaseModel):
    """Input schema for Gmail `users.drafts.create` (save draft).

    API: https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/create
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]

    body: Annotated[
        Draft,
        Field(..., description="The draft to create."),
        Body(),
    ]


class DraftsGetRequest(BaseModel):
    """Input schema for Gmail `users.drafts.get` endpoint.

    Gets the specified draft.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/get
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
        Field(..., description="The ID of the draft to retrieve."),
        Path(),
    ]

    # Query parameters
    format: Annotated[
        Optional[MessageFormat],
        Field(
            None,
            description=(
                "The format to return the draft in. Gmail applies 'full' when this is absent. "
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


class DraftsListRequest(BaseModel):
    """Input schema for Gmail `users.drafts.list` endpoint.

    Lists the drafts in the user's mailbox.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/list
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
            None,
            ge=1,
            le=500,
            description=(
                "Maximum number of drafts to return. Gmail returns 100 when this is absent. "
                "The maximum allowed value for this field is 500."
            ),
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
                "Only return draft messages matching the specified query. Supports the same query format "
                "as the Gmail search box. For example, "
                "\"from:someuser@example.com rfc822msgid:<somemsgid@example.com> is:unread\"."
            ),
        ),
        Query(),
    ]
    includeSpamTrash: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include drafts from SPAM and TRASH in the results.",
        ),
        Query(),
    ]


class DraftsUpdateRequest(BaseModel):
    """Input schema for Gmail `users.drafts.update` endpoint.

    Replaces a draft's content. The new content is whole: whatever the saved
    draft held before is gone, so send the message you want the draft to be,
    not the part of it that changed.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/update
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
        Field(..., description="The ID of the draft to update."),
        Path(),
    ]

    # Request body
    body: Annotated[
        Draft,
        Field(..., description="The draft's replacement content."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class DraftsDeleteRequest(BaseModel):
    """Input schema for Gmail `users.drafts.delete` endpoint.

    Immediately and permanently deletes the specified draft. Does not simply
    trash it.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/delete
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
        Field(..., description="The ID of the draft to delete."),
        Path(),
    ]


class DraftsSendRequest(BaseModel):
    """Input schema for Gmail `users.drafts.send` endpoint.

    Sends the specified, existing draft to the recipients in the To, Cc, and
    Bcc headers.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/send
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
        SendDraftRequest,
        Field(..., description="The draft to send."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }
