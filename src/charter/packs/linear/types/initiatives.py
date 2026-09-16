"""Request schemas for Linear's initiative operations.

An initiative groups projects into something longer-running than a project and
larger than a team. It is what Linear replaced roadmaps with: the whole
``roadmap`` family — ``roadmaps``, ``roadmapCreate``, ``roadmapUpdate``,
``roadmapArchive`` and the rest — is marked deprecated in the schema, so none of
it is a tool here.

Like a project, an initiative carries *status updates*: ``initiativeUpdate`` is
the mutation that edits the initiative, while ``initiativeUpdateCreate`` posts a
note on one. Linear's naming, mirrored rather than improved on.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import (
    Day,
    FrequencyResolutionType,
    PageVariables,
    PaginationOrderBy,
)
from charter.packs.linear.types.filters import InitiativeFilter
from charter.packs.linear.types.projects import DateResolutionType, ProjectHealth
from charter.types import Body

__all__ = [
    "InitiativesListRequest",
    "InitiativeGetRequest",
    "InitiativeCreateRequest",
    "InitiativeUpdateRequest",
    "InitiativeDeleteRequest",
    "InitiativeArchiveRequest",
    "InitiativeUnarchiveRequest",
    "InitiativeToProjectCreateRequest",
    "InitiativeToProjectDeleteRequest",
    "InitiativeUpdatesListRequest",
    "InitiativeUpdateCreateRequest",
    "InitiativeStatus",
]


InitiativeStatus = Literal["Planned", "Proposed", "Active", "Completed", "Canceled"]
"""Where an initiative is in its life. Capitalised exactly as Linear's enum is."""


class InitiativesListVariables(PageVariables):
    """Variables for the ``initiatives`` connection."""

    filter: Optional[InitiativeFilter] = Field(
        default=None, description="Narrow the initiatives returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived initiatives in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class InitiativesListRequest(BaseModel):
    """List initiatives."""

    variables: Annotated[
        InitiativesListVariables,
        Field(default_factory=InitiativesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class InitiativeGetVariables(BaseModel):
    """Variables for the ``initiative`` query."""

    id: str = Field(..., description="The initiative's UUID.")


class InitiativeGetRequest(BaseModel):
    """Get one initiative."""

    variables: Annotated[
        InitiativeGetVariables,
        Field(..., description="Which initiative to fetch."),
        Body(envelop=True),
    ]


class InitiativeCreateInput(BaseModel):
    """The input to ``initiativeCreate``."""

    name: str = Field(..., description="The name of the initiative.")
    description: Optional[str] = Field(
        None, description="The description of the initiative."
    )
    content: Optional[str] = Field(
        None, description="The initiative content as markdown."
    )
    status: Optional[InitiativeStatus] = Field(
        None, description="The status of the initiative."
    )
    owner_id: Optional[str] = Field(
        None, description="The owner of the initiative."
    )
    lead_team_id: Optional[str] = Field(
        None, description="The identifier of the team leading the initiative."
    )
    label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the labels associated with this initiative."
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        le=4,
        description=(
            "The priority of the initiative. 0 = No priority, 1 = Urgent, "
            "2 = High, 3 = Medium, 4 = Low."
        ),
    )
    target_date: Optional[str] = Field(
        None, description="The estimated completion date of the initiative, as `YYYY-MM-DD`."
    )
    target_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the initiative's estimated completion date."
    )
    icon: Optional[str] = Field(None, description="The icon of the initiative.")
    color: Optional[str] = Field(
        None, description="The color of the initiative, as a hex string."
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order of the initiative within the workspace."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description=(
            "The sort order of the initiative within the workspace, when ordered "
            "by priority."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class InitiativeCreateVariables(BaseModel):
    """Variables for the ``initiativeCreate`` mutation."""

    input: InitiativeCreateInput = Field(..., description="The initiative to create.")


class InitiativeCreateRequest(BaseModel):
    """Create an initiative."""

    variables: Annotated[
        InitiativeCreateVariables,
        Field(..., description="The initiative to create."),
        Body(envelop=True),
    ]


class InitiativeUpdateInput(BaseModel):
    """The fields the ``initiativeUpdate`` mutation changes. All optional.

    This edits the initiative. To post a status update *on* one, use
    ``initiative_update_create``.
    """

    name: Optional[str] = Field(None, description="The name of the initiative.")
    description: Optional[str] = Field(
        None, description="The description of the initiative."
    )
    content: Optional[str] = Field(
        None, description="The initiative content as markdown."
    )
    status: Optional[InitiativeStatus] = Field(
        None, description="The status of the initiative."
    )
    owner_id: Optional[str] = Field(None, description="The owner of the initiative.")
    lead_team_id: Optional[str] = Field(
        None, description="The identifier of the team leading the initiative."
    )
    label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the labels associated with this initiative."
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        le=4,
        description=(
            "The priority of the initiative. 0 = No priority, 1 = Urgent, "
            "2 = High, 3 = Medium, 4 = Low."
        ),
    )
    target_date: Optional[str] = Field(
        None, description="The estimated completion date of the initiative, as `YYYY-MM-DD`."
    )
    target_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the initiative's estimated completion date."
    )
    icon: Optional[str] = Field(None, description="The icon of the initiative.")
    color: Optional[str] = Field(
        None, description="The color of the initiative, as a hex string."
    )
    trashed: Optional[bool] = Field(
        None, description="Whether the initiative has been trashed."
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order of the initiative within the workspace."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description=(
            "The sort order of the initiative within the workspace, when ordered "
            "by priority."
        ),
    )
    update_reminder_frequency: Optional[float] = Field(
        None,
        description=(
            "The frequency at which to prompt for initiative updates. When not "
            "set, reminders are inherited from workspace settings."
        ),
    )
    update_reminder_frequency_in_weeks: Optional[float] = Field(
        None,
        description=(
            "The n-weekly frequency at which to prompt for initiative updates. "
            "When not set, reminders are inherited from workspace settings."
        ),
    )
    frequency_resolution: Optional[FrequencyResolutionType] = Field(
        None,
        description=(
            "The resolution type for the update reminder frequency (e.g., weekly, "
            "biweekly)."
        ),
    )
    update_reminders_day: Optional[Day] = Field(
        None, description="The day of the week on which to prompt for initiative updates."
    )
    update_reminders_hour: Optional[int] = Field(
        None,
        ge=0,
        le=23,
        description="The hour of the day (0-23) at which to prompt for initiative updates.",
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> InitiativeUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("initiativeUpdate needs at least one field to change.")
        return self


class InitiativeUpdateVariables(BaseModel):
    """Variables for the ``initiativeUpdate`` mutation."""

    id: str = Field(..., description="The initiative's UUID.")
    input: InitiativeUpdateInput = Field(..., description="The fields to change.")


class InitiativeUpdateRequest(BaseModel):
    """Update an initiative."""

    variables: Annotated[
        InitiativeUpdateVariables,
        Field(..., description="The initiative to update."),
        Body(envelop=True),
    ]


class InitiativeIdVariables(BaseModel):
    """Variables for the initiative mutations that take only an id."""

    id: str = Field(..., description="The initiative's UUID.")


class InitiativeDeleteRequest(BaseModel):
    """Move an initiative to the trash."""

    variables: Annotated[
        InitiativeIdVariables,
        Field(..., description="The initiative to delete."),
        Body(envelop=True),
    ]


class InitiativeArchiveRequest(BaseModel):
    """Archive an initiative."""

    variables: Annotated[
        InitiativeIdVariables,
        Field(..., description="The initiative to archive."),
        Body(envelop=True),
    ]


class InitiativeUnarchiveRequest(BaseModel):
    """Restore an archived initiative."""

    variables: Annotated[
        InitiativeIdVariables,
        Field(..., description="The initiative to restore."),
        Body(envelop=True),
    ]


class InitiativeToProjectCreateInput(BaseModel):
    """The input to ``initiativeToProjectCreate`` — puts a project in an initiative."""

    initiative_id: str = Field(..., description="The identifier of the initiative.")
    project_id: str = Field(..., description="The identifier of the project.")
    sort_order: Optional[float] = Field(
        None, description="The sort order of the project within the initiative."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class InitiativeToProjectCreateVariables(BaseModel):
    """Variables for the ``initiativeToProjectCreate`` mutation."""

    input: InitiativeToProjectCreateInput = Field(
        ..., description="The project to add to the initiative."
    )


class InitiativeToProjectCreateRequest(BaseModel):
    """Add a project to an initiative."""

    variables: Annotated[
        InitiativeToProjectCreateVariables,
        Field(..., description="The link to create."),
        Body(envelop=True),
    ]


class InitiativeToProjectDeleteVariables(BaseModel):
    """Variables for the ``initiativeToProjectDelete`` mutation."""

    id: str = Field(
        ...,
        description=(
            "The UUID of the initiative-to-project link, not of the project. It "
            "comes back from `initiative_get`."
        ),
    )


class InitiativeToProjectDeleteRequest(BaseModel):
    """Remove a project from an initiative."""

    variables: Annotated[
        InitiativeToProjectDeleteVariables,
        Field(..., description="The link to remove."),
        Body(envelop=True),
    ]


class InitiativeUpdatesListVariables(PageVariables):
    """Variables for the ``initiativeUpdates`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived updates in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class InitiativeUpdatesListRequest(BaseModel):
    """Read the status updates posted on initiatives."""

    variables: Annotated[
        InitiativeUpdatesListVariables,
        Field(default_factory=InitiativeUpdatesListVariables, description="Paging."),
        Body(envelop=True),
    ]


class InitiativeUpdateCreateInput(BaseModel):
    """The input to ``initiativeUpdateCreate`` — a status post on an initiative."""

    initiative_id: str = Field(
        ..., description="The initiative to associate the update with."
    )
    body: Optional[str] = Field(
        None, description="The content of the initiative update in markdown format."
    )
    health: Optional[ProjectHealth] = Field(
        None, description="The health of the initiative at the time of the update."
    )
    is_diff_hidden: Optional[bool] = Field(
        None,
        description=(
            "Whether the diff between the current update and the previous one "
            "should be hidden."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class InitiativeUpdateCreateVariables(BaseModel):
    """Variables for the ``initiativeUpdateCreate`` mutation."""

    input: InitiativeUpdateCreateInput = Field(
        ..., description="The status update to post."
    )


class InitiativeUpdateCreateRequest(BaseModel):
    """Post a status update on an initiative."""

    variables: Annotated[
        InitiativeUpdateCreateVariables,
        Field(..., description="The status update to post."),
        Body(envelop=True),
    ]
