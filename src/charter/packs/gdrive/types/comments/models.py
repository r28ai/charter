"""
Comment and Reply resources.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

from ..common import User

ReplyAction = Literal["resolve", "reopen"]


class QuotedFileContent(BaseModel):
    """
    The file content to which the comment refers, typically within the anchor
    region. For a text file, for example, this would be the text at the location
    of the comment.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments#Comment.QuotedFileContent
    """

    mime_type: Optional[str] = Field(None, description="The MIME type of the quoted content.")
    value: Optional[str] = Field(
        None,
        description=(
            "The quoted content itself. This is interpreted as plain text if set "
            "through the API."
        ),
    )


class Reply(BaseModel):
    """
    A reply to a comment on a file. Some resource methods (such as
    `replies.update`) require a `replyId`. Use the `replies.list` method to
    retrieve the ID for a reply.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies#Reply
    """

    content: Optional[str] = Field(
        None,
        description=(
            "The plain text content of the reply. This field is used for setting "
            "the content, while `htmlContent` should be displayed. This field is "
            "required by the `create` method if no `action` value is specified."
        ),
    )
    action: Optional[ReplyAction] = Field(
        None,
        description=(
            "The action the reply performed to the parent comment. The supported "
            "values are: `resolve`, `reopen`."
        ),
    )

    id: Annotated[
        Optional[str],
        Field(None, description="Output only. The ID of the reply."),
        Mode("response_only"),
    ] = None
    kind: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Identifies what kind of resource this is. Value: the "
                'fixed string `"drive#reply"`.'
            ),
        ),
        Mode("response_only"),
    ] = None
    created_time: Annotated[
        Optional[str],
        Field(
            None,
            description="The time at which the reply was created (RFC 3339 date-time).",
        ),
        Mode("response_only"),
    ] = None
    modified_time: Annotated[
        Optional[str],
        Field(
            None,
            description="The last time the reply was modified (RFC 3339 date-time).",
        ),
        Mode("response_only"),
    ] = None
    author: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. The author of the reply. The author's email address "
                "and permission ID won't be populated."
            ),
        ),
        Mode("response_only"),
    ] = None
    html_content: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The content of the reply with HTML formatting.",
        ),
        Mode("response_only"),
    ] = None
    deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the reply has been deleted. A deleted reply "
                "has no content."
            ),
        ),
        Mode("response_only"),
    ] = None
    mentioned_email_addresses: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Output only. A list of email addresses for users mentioned in this "
                "comment. If no users are mentioned, the list is empty."
            ),
        ),
        Mode("response_only"),
    ] = None
    assignee_email_address: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The email address of the user assigned to this "
                "comment. If no user is assigned, the field is unset."
            ),
        ),
        Mode("response_only"),
    ] = None


class Comment(BaseModel):
    """
    A comment on a file. Some resource methods (such as `comments.update`)
    require a `commentId`. Use the `comments.list` method to retrieve the ID
    for a comment in a file.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/comments#Comment
    """

    content: str = Field(
        ...,
        description=(
            "The plain text content of the comment. This field is used for setting "
            "the content, while `htmlContent` should be displayed."
        ),
    )
    anchor: Optional[str] = Field(
        None,
        description=(
            "A region of the document represented as a JSON string. For details on "
            "defining anchor properties, refer to Manage comments and replies."
        ),
    )
    quoted_file_content: Optional[QuotedFileContent] = Field(
        None,
        description=(
            "The file content to which the comment refers, typically within the "
            "anchor region. For a text file, for example, this would be the text "
            "at the location of the comment."
        ),
    )

    id: Annotated[
        Optional[str],
        Field(None, description="Output only. The ID of the comment."),
        Mode("response_only"),
    ] = None
    kind: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Identifies what kind of resource this is. Value: the "
                'fixed string `"drive#comment"`.'
            ),
        ),
        Mode("response_only"),
    ] = None
    created_time: Annotated[
        Optional[str],
        Field(
            None,
            description="The time at which the comment was created (RFC 3339 date-time).",
        ),
        Mode("response_only"),
    ] = None
    modified_time: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The last time the comment or any of its replies was modified "
                "(RFC 3339 date-time)."
            ),
        ),
        Mode("response_only"),
    ] = None
    author: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "Output only. The author of the comment. The author's email address "
                "and permission ID will not be populated."
            ),
        ),
        Mode("response_only"),
    ] = None
    html_content: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The content of the comment with HTML formatting.",
        ),
        Mode("response_only"),
    ] = None
    deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the comment has been deleted. A deleted "
                "comment has no content."
            ),
        ),
        Mode("response_only"),
    ] = None
    resolved: Annotated[
        Optional[bool],
        Field(
            None,
            description="Output only. Whether the comment has been resolved by one of its replies.",
        ),
        Mode("response_only"),
    ] = None
    replies: Annotated[
        Optional[List[Reply]],
        Field(
            None,
            description=(
                "Output only. The full list of replies to the comment in "
                "chronological order."
            ),
        ),
        Mode("response_only"),
    ] = None
    mentioned_email_addresses: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Output only. A list of email addresses for users mentioned in this "
                "comment. If no users are mentioned, the list is empty."
            ),
        ),
        Mode("response_only"),
    ] = None
    assignee_email_address: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The email address of the user assigned to this "
                "comment. If no user is assigned, the field is unset."
            ),
        ),
        Mode("response_only"),
    ] = None
