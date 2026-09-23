# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's comment and reaction operations.

**A comment does not only belong to an issue.** Linear's ``CommentCreateInput``
accepts a parent of several kinds — an issue, a project, a project status
update, an initiative, an initiative update, a document, or a post — and
exactly one of them. An earlier version of this pack made ``issue_id`` a
required field, which modelled one of the parents and made the others
unreachable: there was no way to comment on a project at all. The parent is
optional here and a validator holds the "exactly one" rule, so the tool covers
what the API does.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables
from charter.packs.linear.types.filters import CommentFilter
from charter.types import Body

__all__ = [
    "CommentsListRequest",
    "CommentGetRequest",
    "CommentCreateRequest",
    "CommentUpdateRequest",
    "CommentDeleteRequest",
    "CommentResolveRequest",
    "CommentUnresolveRequest",
    "ReactionCreateRequest",
    "ReactionDeleteRequest",
]

# The six things a comment can hang off. Named once so the validator and the
# descriptions cannot drift.
_COMMENT_PARENTS = (
    "issue_id",
    "project_id",
    "project_update_id",
    "initiative_id",
    "initiative_update_id",
    "document_content_id",
    "post_id",
)


class CommentsListVariables(PageVariables):
    """Variables for the ``comments`` connection."""

    filter: Optional[CommentFilter] = Field(
        default=None,
        description=(
            "Narrow the comments returned. To read one issue's thread, filter on "
            "`issue.id.eq` with the issue's UUID."
        ),
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include comments on archived issues."
    )


class CommentsListRequest(BaseModel):
    """Read comments."""

    variables: Annotated[
        CommentsListVariables,
        Field(default_factory=CommentsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class CommentGetVariables(BaseModel):
    """Variables for the ``comment`` query."""

    id: Optional[str] = Field(None, description="The comment's UUID.")
    hash: Optional[str] = Field(
        None, description="The comment's hash, as it appears in a Linear comment URL."
    )

    @model_validator(mode="after")
    def _one_way_of_naming_the_comment(self) -> CommentGetVariables:
        if (self.id is None) == (self.hash is None):
            raise ValueError("Name the comment by `id` or by `hash`, and not both.")
        return self


class CommentGetRequest(BaseModel):
    """Get one comment."""

    variables: Annotated[
        CommentGetVariables,
        Field(..., description="Which comment to fetch."),
        Body(envelop=True),
    ]


class CommentCreateInput(BaseModel):
    """The input to ``commentCreate``.

    Exactly one parent must be given. A comment belongs to an issue, a project,
    a project update, an initiative, an initiative update, a document or a post
    — never to more than one of them.

    API Reference: https://linear.app/developers/graphql
    """

    body: str = Field(..., description="The comment content in markdown format.")
    issue_id: Optional[str] = Field(None, description="The issue to associate the comment with.")
    project_id: Optional[str] = Field(
        None, description="The project to associate the comment with."
    )
    project_update_id: Optional[str] = Field(
        None, description="The project update to associate the comment with."
    )
    initiative_id: Optional[str] = Field(
        None, description="The initiative to associate the comment with."
    )
    initiative_update_id: Optional[str] = Field(
        None, description="The initiative update to associate the comment with."
    )
    document_content_id: Optional[str] = Field(
        None, description="The document content to associate the comment with."
    )
    post_id: Optional[str] = Field(None, description="The post to associate the comment with.")
    parent_id: Optional[str] = Field(
        None,
        description="The parent comment under which to nest this comment, for a threaded reply.",
    )
    quoted_text: Optional[str] = Field(
        None, description="The text that this comment references, for an inline reply."
    )
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this comment."
    )
    do_not_subscribe_to_issue: Optional[bool] = Field(
        None,
        description="Whether to not subscribe the comment's author to the issue.",
    )
    create_on_synced_slack_thread: Optional[bool] = Field(
        None,
        description=(
            "Flag to indicate this comment should be created on the issue's synced "
            "Slack comment thread. If no synced Slack comment thread exists, the "
            "mutation will fail. If there are multiple synced Slack threads on "
            "the issue, the oldest one will be targeted."
        ),
    )
    created_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the comment was created (e.g. if importing from "
            "another system). Must be a time in the past. If none is provided, "
            "the backend will generate the time as now."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_parent(self) -> CommentCreateInput:
        named = [f for f in _COMMENT_PARENTS if getattr(self, f) is not None]
        if len(named) != 1:
            raise ValueError(
                "A comment needs exactly one parent. Give one of "
                + ", ".join(_COMMENT_PARENTS)
                + (f"; got {', '.join(named)}." if named else "; none was given.")
            )
        return self


class CommentCreateVariables(BaseModel):
    """Variables for the ``commentCreate`` mutation."""

    input: CommentCreateInput = Field(..., description="The comment to post.")


class CommentCreateRequest(BaseModel):
    """Post a comment."""

    variables: Annotated[
        CommentCreateVariables,
        Field(..., description="The comment to post."),
        Body(envelop=True),
    ]


class CommentUpdateInput(BaseModel):
    """The fields ``commentUpdate`` changes. All optional."""

    body: Optional[str] = Field(None, description="The comment content in markdown format.")
    quoted_text: Optional[str] = Field(None, description="The text that this comment references.")
    resolving_user_id: Optional[str] = Field(None, description="The user who resolved the comment.")
    resolving_comment_id: Optional[str] = Field(
        None, description="The comment that resolved this thread."
    )
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this comment."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> CommentUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("commentUpdate needs at least one field to change.")
        return self


class CommentUpdateVariables(BaseModel):
    """Variables for the ``commentUpdate`` mutation."""

    id: str = Field(..., description="The comment's UUID.")
    input: CommentUpdateInput = Field(..., description="The fields to change.")


class CommentUpdateRequest(BaseModel):
    """Edit a comment."""

    variables: Annotated[
        CommentUpdateVariables,
        Field(..., description="The comment to edit."),
        Body(envelop=True),
    ]


class CommentDeleteVariables(BaseModel):
    """Variables for the ``commentDelete`` mutation."""

    id: str = Field(..., description="The comment's UUID.")


class CommentDeleteRequest(BaseModel):
    """Delete a comment."""

    variables: Annotated[
        CommentDeleteVariables,
        Field(..., description="The comment to delete."),
        Body(envelop=True),
    ]


class CommentResolveVariables(BaseModel):
    """Variables for the ``commentResolve`` mutation."""

    id: str = Field(..., description="The UUID of the comment thread to resolve.")
    resolving_comment_id: Optional[str] = Field(
        None, description="The UUID of the comment that resolved the thread."
    )


class CommentResolveRequest(BaseModel):
    """Mark a comment thread resolved."""

    variables: Annotated[
        CommentResolveVariables,
        Field(..., description="The thread to resolve."),
        Body(envelop=True),
    ]


class CommentUnresolveVariables(BaseModel):
    """Variables for the ``commentUnresolve`` mutation."""

    id: str = Field(..., description="The UUID of the comment thread to reopen.")


class CommentUnresolveRequest(BaseModel):
    """Reopen a resolved comment thread."""

    variables: Annotated[
        CommentUnresolveVariables,
        Field(..., description="The thread to reopen."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# reactions
# -----------------------------------------------------

_REACTION_TARGETS = (
    "comment_id",
    "issue_id",
    "project_update_id",
    "initiative_update_id",
)


class ReactionCreateInput(BaseModel):
    """The input to ``reactionCreate``.

    Exactly one target must be given, the same way a comment takes exactly one
    parent.

    API Reference: https://linear.app/developers/graphql
    """

    emoji: str = Field(
        ...,
        description="The emoji the reaction represents, by name and without colons, e.g. '+1' or 'tada'.",
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )
    comment_id: Optional[str] = Field(
        None, description="The comment to associate the reaction with."
    )
    issue_id: Optional[str] = Field(None, description="The issue to associate the reaction with.")
    project_update_id: Optional[str] = Field(
        None, description="The project update to associate the reaction with."
    )
    initiative_update_id: Optional[str] = Field(
        None, description="The initiative update to associate the reaction with."
    )

    @model_validator(mode="after")
    def _exactly_one_target(self) -> ReactionCreateInput:
        named = [f for f in _REACTION_TARGETS if getattr(self, f) is not None]
        if len(named) != 1:
            raise ValueError(
                "A reaction needs exactly one target. Give one of "
                + ", ".join(_REACTION_TARGETS)
                + (f"; got {', '.join(named)}." if named else "; none was given.")
            )
        return self


class ReactionCreateVariables(BaseModel):
    """Variables for the ``reactionCreate`` mutation."""

    input: ReactionCreateInput = Field(..., description="The reaction to add.")


class ReactionCreateRequest(BaseModel):
    """React to a comment, issue or update."""

    variables: Annotated[
        ReactionCreateVariables,
        Field(..., description="The reaction to add."),
        Body(envelop=True),
    ]


class ReactionDeleteVariables(BaseModel):
    """Variables for the ``reactionDelete`` mutation."""

    id: str = Field(..., description="The reaction's UUID.")


class ReactionDeleteRequest(BaseModel):
    """Remove a reaction."""

    variables: Annotated[
        ReactionDeleteVariables,
        Field(..., description="The reaction to remove."),
        Body(envelop=True),
    ]
