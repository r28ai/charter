# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's attachment operations.

An attachment links an issue to something outside Linear — a pull request, a
Slack thread, a Zendesk ticket, a URL. Linear deduplicates them by URL, so
creating an attachment whose ``url`` already exists on the issue updates that
attachment rather than adding a second one.

``attachmentsForURL`` is the reverse lookup, and is the tool to reach for when
the question is "is this PR already linked to an issue?".

**``title`` is required on update.** Linear's ``AttachmentUpdateInput`` declares
it non-null, so unlike every other update body in this pack, this one mandates a
field. That is the API's rule rather than an oversight here: read the attachment
first if you only mean to change its subtitle.

API Reference: https://linear.app/developers/attachments
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.packs.linear.types.common import JSONObject, PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import AttachmentFilter
from charter.types import Body

__all__ = [
    "AttachmentsListRequest",
    "AttachmentGetRequest",
    "AttachmentsForUrlRequest",
    "AttachmentCreateRequest",
    "AttachmentUpdateRequest",
    "AttachmentDeleteRequest",
]


class AttachmentsListVariables(PageVariables):
    """Variables for the ``attachments`` connection."""

    filter: Optional[AttachmentFilter] = Field(
        default=None, description="Narrow the attachments returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include attachments on archived issues."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class AttachmentsListRequest(BaseModel):
    """List attachments."""

    variables: Annotated[
        AttachmentsListVariables,
        Field(default_factory=AttachmentsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class AttachmentGetVariables(BaseModel):
    """Variables for the ``attachment`` query."""

    id: str = Field(..., description="The attachment's UUID.")


class AttachmentGetRequest(BaseModel):
    """Get one attachment."""

    variables: Annotated[
        AttachmentGetVariables,
        Field(..., description="Which attachment to fetch."),
        Body(envelop=True),
    ]


class AttachmentsForUrlVariables(PageVariables):
    """Variables for the ``attachmentsForURL`` query."""

    url: str = Field(..., description="The external URL to look up.")


class AttachmentsForUrlRequest(BaseModel):
    """Find the attachments that link to a given URL."""

    variables: Annotated[
        AttachmentsForUrlVariables,
        Field(..., description="The URL to look up."),
        Body(envelop=True),
    ]


class AttachmentCreateInput(BaseModel):
    """The input to ``attachmentCreate``.

    Creating an attachment whose ``url`` is already attached to the issue
    updates the existing one instead of adding a duplicate.
    """

    issue_id: str = Field(..., description="The issue to associate the attachment with.")
    title: str = Field(..., description="The attachment title.")
    url: str = Field(..., description="The attachment URL.")
    subtitle: Optional[str] = Field(None, description="The attachment subtitle.")
    icon_url: Optional[str] = Field(None, description="An icon to display with the attachment.")
    comment_body: Optional[str] = Field(
        None, description="Create a comment with the given markdown body alongside the attachment."
    )
    group_by_source: Optional[bool] = Field(
        None,
        description="Whether to group attachments from the same source.",
    )
    metadata: Optional[JSONObject] = Field(
        None, description="Attachment metadata object with string and number values."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )


class AttachmentCreateVariables(BaseModel):
    """Variables for the ``attachmentCreate`` mutation."""

    input: AttachmentCreateInput = Field(..., description="The attachment to create.")


class AttachmentCreateRequest(BaseModel):
    """Link an issue to something outside Linear."""

    variables: Annotated[
        AttachmentCreateVariables,
        Field(..., description="The attachment to create."),
        Body(envelop=True),
    ]


class AttachmentUpdateInput(BaseModel):
    """The fields ``attachmentUpdate`` changes.

    ``title`` is required — Linear declares it non-null on this input.
    """

    title: str = Field(..., description="The attachment title.")
    subtitle: Optional[str] = Field(None, description="The attachment subtitle.")
    icon_url: Optional[str] = Field(None, description="An icon to display with the attachment.")
    metadata: Optional[JSONObject] = Field(
        None, description="Attachment metadata object with string and number values."
    )


class AttachmentUpdateVariables(BaseModel):
    """Variables for the ``attachmentUpdate`` mutation."""

    id: str = Field(..., description="The attachment's UUID.")
    input: AttachmentUpdateInput = Field(..., description="The fields to change.")


class AttachmentUpdateRequest(BaseModel):
    """Update an attachment."""

    variables: Annotated[
        AttachmentUpdateVariables,
        Field(..., description="The attachment to update."),
        Body(envelop=True),
    ]


class AttachmentDeleteVariables(BaseModel):
    """Variables for the ``attachmentDelete`` mutation."""

    id: str = Field(..., description="The attachment's UUID.")


class AttachmentDeleteRequest(BaseModel):
    """Remove an attachment."""

    variables: Annotated[
        AttachmentDeleteVariables,
        Field(..., description="The attachment to remove."),
        Body(envelop=True),
    ]
