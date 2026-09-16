"""Request schemas for Linear's label operations.

Labels come in two kinds and they are different resources: ``issueLabels`` tag
issues, ``projectLabels`` tag projects. A label with no ``team_id`` belongs to
the whole workspace; one with a ``team_id`` belongs to that team alone.

Linear *retires* a label rather than deleting it where the label is still in
use, which is why ``issue_label_update`` carries ``retired_at``.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import IssueLabelFilter
from charter.types import Body

__all__ = [
    "IssueLabelsListRequest",
    "IssueLabelGetRequest",
    "IssueLabelCreateRequest",
    "IssueLabelUpdateRequest",
    "IssueLabelDeleteRequest",
    "ProjectLabelsListRequest",
]


class IssueLabelsListVariables(PageVariables):
    """Variables for the ``issueLabels`` connection."""

    filter: Optional[IssueLabelFilter] = Field(
        default=None, description="Narrow the labels returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived labels in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class IssueLabelsListRequest(BaseModel):
    """List issue labels."""

    variables: Annotated[
        IssueLabelsListVariables,
        Field(default_factory=IssueLabelsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class IssueLabelGetVariables(BaseModel):
    """Variables for the ``issueLabel`` query."""

    id: str = Field(..., description="The label's UUID.")


class IssueLabelGetRequest(BaseModel):
    """Get one issue label."""

    variables: Annotated[
        IssueLabelGetVariables,
        Field(..., description="Which label to fetch."),
        Body(envelop=True),
    ]


class IssueLabelCreateInput(BaseModel):
    """The input to ``issueLabelCreate``."""

    name: str = Field(..., description="The name of the label.")
    color: Optional[str] = Field(
        None, description="The color of the label, as a hex string such as '#4ea7fc'."
    )
    description: Optional[str] = Field(
        None, description="The description of the label."
    )
    team_id: Optional[str] = Field(
        None,
        description=(
            "The team associated with the label. Omit it for a label the whole "
            "workspace can use."
        ),
    )
    parent_id: Optional[str] = Field(
        None, description="The identifier of the parent label group."
    )
    is_group: Optional[bool] = Field(
        None, description="Whether the label is considered to be a group."
    )
    retired_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the label was retired. Set to null to restore a "
            "retired label. This schema cannot send null — absent means unchanged."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class IssueLabelCreateVariables(BaseModel):
    """Variables for the ``issueLabelCreate`` mutation."""

    input: IssueLabelCreateInput = Field(..., description="The label to create.")


class IssueLabelCreateRequest(BaseModel):
    """Create a label."""

    variables: Annotated[
        IssueLabelCreateVariables,
        Field(..., description="The label to create."),
        Body(envelop=True),
    ]


class IssueLabelUpdateInput(BaseModel):
    """The fields ``issueLabelUpdate`` changes. All optional."""

    name: Optional[str] = Field(None, description="The name of the label.")
    color: Optional[str] = Field(
        None, description="The color of the label, as a hex string such as '#4ea7fc'."
    )
    description: Optional[str] = Field(
        None, description="The description of the label."
    )
    parent_id: Optional[str] = Field(
        None, description="The identifier of the parent label group."
    )
    is_group: Optional[bool] = Field(
        None, description="Whether the label is considered to be a group."
    )
    retired_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the label was retired, as an ISO 8601 timestamp. "
            "Retiring keeps the label on the issues that already carry it while "
            "taking it out of the picker."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> IssueLabelUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("issueLabelUpdate needs at least one field to change.")
        return self


class IssueLabelUpdateVariables(BaseModel):
    """Variables for the ``issueLabelUpdate`` mutation."""

    id: str = Field(..., description="The label's UUID.")
    input: IssueLabelUpdateInput = Field(..., description="The fields to change.")


class IssueLabelUpdateRequest(BaseModel):
    """Update a label."""

    variables: Annotated[
        IssueLabelUpdateVariables,
        Field(..., description="The label to update."),
        Body(envelop=True),
    ]


class IssueLabelDeleteVariables(BaseModel):
    """Variables for the ``issueLabelDelete`` mutation."""

    id: str = Field(..., description="The label's UUID.")


class IssueLabelDeleteRequest(BaseModel):
    """Delete a label."""

    variables: Annotated[
        IssueLabelDeleteVariables,
        Field(..., description="The label to delete."),
        Body(envelop=True),
    ]


class ProjectLabelsListVariables(PageVariables):
    """Variables for the ``projectLabels`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived labels in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class ProjectLabelsListRequest(BaseModel):
    """List the labels that tag projects."""

    variables: Annotated[
        ProjectLabelsListVariables,
        Field(default_factory=ProjectLabelsListVariables, description="Paging."),
        Body(envelop=True),
    ]
