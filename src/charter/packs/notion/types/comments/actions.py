# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for Notion's comment endpoints.

A comment either starts a discussion on a page or a block, or replies to a
discussion that already exists. Those are different request shapes, and the
validator on the create body holds a call to exactly one of them.

API Reference: https://developers.notion.com/reference/comment-object
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.common import PaginatedQuery, Parent, RichText
from charter.types import Body, ConflictsWith, Path, Query

__all__ = [
    "CommentsCreateRequest",
    "CommentsListRequest",
    "CommentsRetrieveRequest",
    "CommentsUpdateRequest",
    "CommentsDeleteRequest",
]

COMMENT_ID = "The ID of the comment."
MARKDOWN = (
    "The content of the comment as a Markdown string. Comments support inline "
    "formatting only — bold, italic, strikethrough, code, links, inline "
    "equations and mentions. Fenced code blocks, headings, lists, tables and "
    "blockquotes do not become structured blocks."
)


class CommentAttachment(BaseModel):
    """A file attached to a comment.

    API Reference: https://developers.notion.com/reference/create-a-comment
    """

    file_upload_id: str = Field(
        ..., description="The ID of a file upload whose status is `uploaded`."
    )
    type: Optional[Literal["file_upload"]] = Field(None, description="Always `file_upload`.")


class CustomDisplayName(BaseModel):
    """The name a custom-attributed comment is shown under.

    API Reference: https://developers.notion.com/reference/create-a-comment
    """

    name: str = Field(..., description="The display name to use.")


class DisplayName(BaseModel):
    """Who the comment appears to be from.

    API Reference: https://developers.notion.com/reference/create-a-comment
    """

    type: Literal["integration", "user", "custom"] = Field(
        ...,
        description=(
            "Whether the comment is attributed to the integration, to the user the "
            "token acts for, or to a custom name."
        ),
    )
    custom: Optional[CustomDisplayName] = Field(
        None, description="The custom name, when `type` is `custom`."
    )

    @model_validator(mode="after")
    def _named(self):
        if self.type == "custom" and self.custom is None:
            raise ValueError("type='custom' needs `custom` giving the name")
        if self.custom is not None and self.type != "custom":
            raise ValueError(f"`custom` is not read when type is {self.type!r}")
        return self


class CommentCreateBody(BaseModel):
    """The body of a create-comment request.

    Either start a discussion — `parent` naming a page or block — or reply to
    one with `discussion_id`. The content is `rich_text` or `markdown`.

    API Reference: https://developers.notion.com/reference/create-a-comment
    """

    parent: Annotated[
        Optional[Parent],
        Field(
            None,
            description=("The page or block to comment on, starting a new discussion there."),
        ),
        ConflictsWith(
            "discussion_id",
            reason="A reply joins an existing discussion, which already has a parent.",
        ),
    ]
    discussion_id: Optional[str] = Field(
        None, description="The ID of an existing discussion to reply to."
    )
    rich_text: Annotated[
        Optional[List[RichText]],
        Field(None, max_length=100, description="The content of the comment, as rich text."),
        ConflictsWith("markdown", reason="Content comes as rich text or as Markdown, not both."),
    ]
    markdown: Optional[str] = Field(None, description=MARKDOWN)
    attachments: Optional[List[CommentAttachment]] = Field(
        None, max_length=3, description="Files to attach. At most three."
    )
    display_name: Optional[DisplayName] = Field(
        None, description="Who the comment appears to be from."
    )

    @model_validator(mode="after")
    def _addressed(self):
        if self.parent is None and self.discussion_id is None:
            raise ValueError(
                "a comment needs either `parent`, to start a discussion on a page or "
                "block, or `discussion_id`, to reply to one"
            )
        if self.rich_text is None and self.markdown is None:
            raise ValueError("a comment needs `rich_text` or `markdown`")
        return self


class CommentsCreateRequest(BaseModel):
    """Add a comment to a page or block, or reply in a discussion.

    API Reference: https://developers.notion.com/reference/create-a-comment
    """

    body: Annotated[CommentCreateBody, Field(..., description="The comment to post."), Body()]


class CommentsListRequest(PaginatedQuery):
    """List the unresolved comments on a page or block.

    API Reference: https://developers.notion.com/reference/retrieve-a-comment
    """

    block_id: Annotated[
        str,
        Field(
            ...,
            description="The ID of the page or block whose comments to list.",
        ),
        Query(),
    ]


class CommentsRetrieveRequest(BaseModel):
    """Retrieve a single comment.

    API Reference: https://developers.notion.com/reference/retrieve-comment
    """

    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]


class CommentUpdateBody(BaseModel):
    """The body of an update-comment request.

    API Reference: https://developers.notion.com/reference/update-a-comment
    """

    rich_text: Annotated[
        Optional[List[RichText]],
        Field(None, max_length=100, description="The comment's new content, as rich text."),
        ConflictsWith("markdown", reason="Content comes as rich text or as Markdown, not both."),
    ]
    markdown: Optional[str] = Field(None, description=MARKDOWN)


class CommentsUpdateRequest(BaseModel):
    """Edit a comment's content.

    API Reference: https://developers.notion.com/reference/update-a-comment
    """

    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
    body: Annotated[CommentUpdateBody, Field(..., description="The new content."), Body()]


class CommentsDeleteRequest(BaseModel):
    """Delete a comment.

    API Reference: https://developers.notion.com/reference/delete-a-comment
    """

    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
