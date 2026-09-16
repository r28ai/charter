"""
Request schemas for the Comments collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.execution.schema import partial_of
from charter.types import Body, Path, Query

from .._shared import FILE_ID, PageToken
from .models import Comment

COMMENT_ID = "The ID of the comment."
PAGE_SIZE = (
    "The maximum number of comments to return. The service may return fewer than "
    "this value. If unspecified, at most 20 comments will be returned. The "
    "maximum value is 100; values above 100 will be coerced to 100."
)
INCLUDE_DELETED = (
    "Whether to include deleted comments. Deleted comments will not include "
    "their original content."
)
START_MODIFIED_TIME = (
    "The minimum value of 'modifiedTime' for the result comments (RFC 3339 "
    "date-time)."
)
COMMENT_FIELDS = (
    "Required. The `fields` parameter must be set. To return the exact fields "
    "you need, see Return specific fields. Example: "
    "`comments(id,content,author,createdTime,modifiedTime,resolved,replies(id,content,author,createdTime,action))`."
)


class CommentsListRequest(BaseModel):
    """
    Lists a file's comments. Required: The `fields` parameter must be set.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/list
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    fields: Annotated[str, Field(..., description=COMMENT_FIELDS), Query()]
    include_deleted: Annotated[
        Optional[bool], Field(None, description=INCLUDE_DELETED), Query()
    ] = None
    page_size: Annotated[
        Optional[int], Field(None, ge=1, le=100, description=PAGE_SIZE), Query()
    ] = None
    page_token: PageToken = None
    start_modified_time: Annotated[
        Optional[str], Field(None, description=START_MODIFIED_TIME), Query()
    ] = None


class CommentsCreateRequest(BaseModel):
    """
    Creates a comment on a file. Required: The `fields` parameter must be set.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/create
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment: Annotated[
        Comment,
        Field(..., description="The comment to create."),
        Body(),
    ]
    fields: Annotated[str, Field(..., description=COMMENT_FIELDS), Query()]


PatchComment = partial_of(
    Comment,
    name="PatchComment",
    doc="""Request body for Drive `comments.update`.

    Create requires `content`; patch leaves out what it is not changing, so it
    needs nothing. Derived rather than written out, so the field descriptions
    have one home.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/update
    """,
)


class CommentsUpdateRequest(BaseModel):
    """
    Updates a comment with patch semantics. Required: The `fields` parameter
    must be set.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/update
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
    comment: Annotated[
        PatchComment,  # type: ignore[valid-type]
        Field(
            ...,
            description=(
                "The comment resource. Only populate fields you want to modify; "
                "typically `content`."
            ),
        ),
        Body(),
    ]
    fields: Annotated[str, Field(..., description=COMMENT_FIELDS), Query()]


class CommentsDeleteRequest(BaseModel):
    """
    Deletes a comment.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments/delete
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
