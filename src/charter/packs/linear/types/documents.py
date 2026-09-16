"""Request schemas for Linear's document operations.

A document is a long-form page that can hang off a project, an initiative, an
issue, a cycle or a team — or off nothing at all. Unlike a comment, Linear does
not require a parent, so the parent fields here are all optional and no
"exactly one" rule applies.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import DocumentFilter
from charter.types import Body

__all__ = [
    "DocumentsListRequest",
    "DocumentGetRequest",
    "DocumentCreateRequest",
    "DocumentUpdateRequest",
    "DocumentDeleteRequest",
    "DocumentUnarchiveRequest",
]


class DocumentsListVariables(PageVariables):
    """Variables for the ``documents`` connection."""

    filter: Optional[DocumentFilter] = Field(
        default=None, description="Narrow the documents returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived documents in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class DocumentsListRequest(BaseModel):
    """List documents."""

    variables: Annotated[
        DocumentsListVariables,
        Field(default_factory=DocumentsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class DocumentGetVariables(BaseModel):
    """Variables for the ``document`` query."""

    id: str = Field(..., description="The document's UUID, or the slug from its URL.")


class DocumentGetRequest(BaseModel):
    """Get one document, with its content."""

    variables: Annotated[
        DocumentGetVariables,
        Field(..., description="Which document to fetch."),
        Body(envelop=True),
    ]


class DocumentCreateInput(BaseModel):
    """The input to ``documentCreate``."""

    title: str = Field(..., description="The title of the document.")
    content: Optional[str] = Field(
        None, description="The document content as markdown."
    )
    project_id: Optional[str] = Field(
        None, description="Related project for the document."
    )
    initiative_id: Optional[str] = Field(
        None, description="Related initiative for the document."
    )
    issue_id: Optional[str] = Field(
        None, description="Related issue for the document."
    )
    cycle_id: Optional[str] = Field(
        None, description="Related cycle for the document."
    )
    team_id: Optional[str] = Field(
        None, description="Related team for the document."
    )
    owner_id: Optional[str] = Field(
        None, description="The owner of the document."
    )
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this document."
    )
    icon: Optional[str] = Field(None, description="The icon of the document.")
    color: Optional[str] = Field(
        None, description="The color of the icon, as a hex string."
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the document."
    )
    release_id: Optional[str] = Field(
        None, description="Related release for the document."
    )
    sort_order: Optional[float] = Field(
        None, description="The order of the item in the resources list."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class DocumentCreateVariables(BaseModel):
    """Variables for the ``documentCreate`` mutation."""

    input: DocumentCreateInput = Field(..., description="The document to create.")


class DocumentCreateRequest(BaseModel):
    """Create a document."""

    variables: Annotated[
        DocumentCreateVariables,
        Field(..., description="The document to create."),
        Body(envelop=True),
    ]


class DocumentUpdateInput(BaseModel):
    """The fields ``documentUpdate`` changes. All optional."""

    title: Optional[str] = Field(None, description="The title of the document.")
    content: Optional[str] = Field(
        None, description="The document content as markdown. Replaces the existing content."
    )
    project_id: Optional[str] = Field(
        None, description="Related project for the document."
    )
    initiative_id: Optional[str] = Field(
        None, description="Related initiative for the document."
    )
    issue_id: Optional[str] = Field(
        None, description="Related issue for the document."
    )
    cycle_id: Optional[str] = Field(
        None, description="Related cycle for the document."
    )
    team_id: Optional[str] = Field(
        None, description="Related team for the document."
    )
    owner_id: Optional[str] = Field(None, description="The owner of the document.")
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this document."
    )
    icon: Optional[str] = Field(None, description="The icon of the document.")
    color: Optional[str] = Field(
        None, description="The color of the icon, as a hex string."
    )
    trashed: Optional[bool] = Field(
        None, description="Whether the document has been trashed."
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the document."
    )
    release_id: Optional[str] = Field(
        None, description="Related release for the document."
    )
    sort_order: Optional[float] = Field(
        None, description="The order of the item in the resources list."
    )
    hidden_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the document was hidden, as an ISO 8601 timestamp. "
            "This schema cannot send null to unhide — absent means unchanged."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> DocumentUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("documentUpdate needs at least one field to change.")
        return self


class DocumentUpdateVariables(BaseModel):
    """Variables for the ``documentUpdate`` mutation."""

    id: str = Field(..., description="The document's UUID.")
    input: DocumentUpdateInput = Field(..., description="The fields to change.")


class DocumentUpdateRequest(BaseModel):
    """Update a document."""

    variables: Annotated[
        DocumentUpdateVariables,
        Field(..., description="The document to update."),
        Body(envelop=True),
    ]


class DocumentIdVariables(BaseModel):
    """Variables for the document mutations that take only an id."""

    id: str = Field(..., description="The document's UUID.")


class DocumentDeleteRequest(BaseModel):
    """Move a document to the trash."""

    variables: Annotated[
        DocumentIdVariables,
        Field(..., description="The document to delete."),
        Body(envelop=True),
    ]


class DocumentUnarchiveRequest(BaseModel):
    """Restore a document from the trash."""

    variables: Annotated[
        DocumentIdVariables,
        Field(..., description="The document to restore."),
        Body(envelop=True),
    ]
