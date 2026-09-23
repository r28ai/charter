# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's project operations.

**Two different things are called a project update.** Linear's mutation
``projectUpdate`` edits a *project*. Linear's resource ``ProjectUpdate`` is a
*status post* written on a project — the weekly "on track, here is what moved"
note — with its own ``projectUpdateCreate``/``projectUpdateUpdate`` mutations
and its own ``projectUpdates`` connection. They are unrelated, and the API gives
them near-identical names.

The tools here mirror the API's names rather than inventing clearer ones, so
that every tool can be checked against the documentation it came from:
``project_update`` edits a project, and ``project_update_create``,
``project_update_update``, ``project_update_get`` and ``project_updates_list``
work on status posts.

**A project's status is an id, not a word.** ``ProjectCreateInput`` and
``ProjectUpdateInput`` both take ``statusId``, a UUID that comes from
``project_statuses_list``. There is no ``state`` field on either input; a pack
that offered one sent a field Linear rejects.

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
from charter.packs.linear.types.filters import (
    ProjectFilter,
    ProjectMilestoneFilter,
    ProjectUpdateFilter,
)
from charter.types import Body

__all__ = [
    "ProjectsListRequest",
    "ProjectGetRequest",
    "ProjectCreateRequest",
    "ProjectUpdateRequest",
    "ProjectDeleteRequest",
    "ProjectUnarchiveRequest",
    "ProjectAddLabelRequest",
    "ProjectRemoveLabelRequest",
    "ProjectStatusesListRequest",
    "ProjectMilestonesListRequest",
    "ProjectMilestoneGetRequest",
    "ProjectMilestoneCreateRequest",
    "ProjectMilestoneUpdateRequest",
    "ProjectMilestoneDeleteRequest",
    "ProjectUpdatesListRequest",
    "ProjectUpdateGetRequest",
    "ProjectUpdateCreateRequest",
    "ProjectUpdateUpdateRequest",
    "ProjectUpdateArchiveRequest",
    "ProjectHealth",
    "DateResolutionType",
]


ProjectHealth = Literal["onTrack", "atRisk", "offTrack"]
"""How a project is reported to be going, on a status update."""

DateResolutionType = Literal["halfYear", "month", "quarter", "year"]
"""How precise a project's start or target date is meant to be read."""


# -----------------------------------------------------
# projects
# -----------------------------------------------------


class ProjectsListVariables(PageVariables):
    """Variables for the ``projects`` connection."""

    filter: Optional[ProjectFilter] = Field(
        default=None, description="Narrow the projects returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived projects in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class ProjectsListRequest(BaseModel):
    """List projects in the workspace."""

    variables: Annotated[
        ProjectsListVariables,
        Field(default_factory=ProjectsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class ProjectGetVariables(BaseModel):
    """Variables for the ``project`` query."""

    id: str = Field(..., description="The project's UUID, or the slug from its URL.")


class ProjectGetRequest(BaseModel):
    """Get one project."""

    variables: Annotated[
        ProjectGetVariables,
        Field(..., description="Which project to fetch."),
        Body(envelop=True),
    ]


class ProjectCreateInput(BaseModel):
    """The input to ``projectCreate``."""

    name: str = Field(..., description="The name of the project.")
    team_ids: List[str] = Field(
        ...,
        min_length=1,
        description="The identifiers of the teams this project is associated with.",
    )
    description: Optional[str] = Field(None, description="The description for the project.")
    content: Optional[str] = Field(None, description="The project content as markdown.")
    status_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the project status. Use `project_statuses_list` to resolve "
            "a name such as 'In Progress' to its UUID."
        ),
    )
    lead_id: Optional[str] = Field(None, description="The identifier of the project lead.")
    member_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the members of this project."
    )
    label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the project labels associated with this project."
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        le=4,
        description=(
            "The priority of the project. 0 = No priority, 1 = Urgent, 2 = High, "
            "3 = Medium, 4 = Low."
        ),
    )
    start_date: Optional[str] = Field(
        None, description="The planned start date of the project, as `YYYY-MM-DD`."
    )
    start_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the project's start date."
    )
    target_date: Optional[str] = Field(
        None, description="The planned target date of the project, as `YYYY-MM-DD`."
    )
    target_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the project's estimated completion date."
    )
    icon: Optional[str] = Field(None, description="The icon of the project.")
    color: Optional[str] = Field(None, description="The color of the project, as a hex string.")
    converted_from_issue_id: Optional[str] = Field(
        None, description="The ID of the issue that was converted into this project."
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the project."
    )
    template_id: Optional[str] = Field(
        None,
        description=(
            "The ID of a project template to apply when creating the project. "
            "Overrides useDefaultTemplate if both are provided."
        ),
    )
    use_default_template: Optional[bool] = Field(
        None,
        description=(
            "When set to true, the default project template of the first team "
            "provided will be applied. If templateId is provided, this will be ignored."
        ),
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order for the project within shared views."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description="The sort order for the project within shared views, when ordered by priority.",
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )


class ProjectCreateVariables(BaseModel):
    """Variables for the ``projectCreate`` mutation."""

    input: ProjectCreateInput = Field(..., description="The project to create.")


class ProjectCreateRequest(BaseModel):
    """Create a project."""

    variables: Annotated[
        ProjectCreateVariables,
        Field(..., description="The project to create."),
        Body(envelop=True),
    ]


class ProjectUpdateInput(BaseModel):
    """The fields the ``projectUpdate`` mutation changes. All optional.

    This edits the project. To post a status update *on* a project, use
    ``project_update_create`` instead.
    """

    name: Optional[str] = Field(None, description="The name of the project.")
    description: Optional[str] = Field(None, description="The description for the project.")
    content: Optional[str] = Field(None, description="The project content as markdown.")
    status_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the project status. Use `project_statuses_list` to resolve "
            "a name such as 'Completed' to its UUID. This is how a project is "
            "closed; there is no separate operation for it."
        ),
    )
    lead_id: Optional[str] = Field(None, description="The identifier of the project lead.")
    member_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the members of this project."
    )
    team_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the teams this project is associated with."
    )
    label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the project labels associated with this project."
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        le=4,
        description=(
            "The priority of the project. 0 = No priority, 1 = Urgent, 2 = High, "
            "3 = Medium, 4 = Low."
        ),
    )
    start_date: Optional[str] = Field(
        None, description="The planned start date of the project, as `YYYY-MM-DD`."
    )
    start_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the project's start date."
    )
    target_date: Optional[str] = Field(
        None, description="The planned target date of the project, as `YYYY-MM-DD`."
    )
    target_date_resolution: Optional[DateResolutionType] = Field(
        None, description="The resolution of the project's estimated completion date."
    )
    completed_at: Optional[str] = Field(
        None, description="The time at which the project was moved into completed state."
    )
    canceled_at: Optional[str] = Field(
        None, description="The time at which the project was moved into canceled state."
    )
    icon: Optional[str] = Field(None, description="The icon of the project.")
    color: Optional[str] = Field(None, description="The color of the project, as a hex string.")
    trashed: Optional[bool] = Field(None, description="Whether the project has been trashed.")
    converted_from_issue_id: Optional[str] = Field(
        None, description="The ID of the issue from which that project is created."
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the project."
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order for the project in shared views."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description="The sort order for the project within shared views, when ordered by priority.",
    )
    slack_new_issue: Optional[bool] = Field(
        None, description="Whether to send new issue notifications to Slack."
    )
    slack_issue_comments: Optional[bool] = Field(
        None, description="Whether to send new issue comment notifications to Slack."
    )
    slack_issue_statuses: Optional[bool] = Field(
        None, description="Whether to send issue status update notifications to Slack."
    )
    update_reminder_frequency: Optional[float] = Field(
        None,
        description=(
            "The frequency at which to prompt for project updates. When not set, "
            "reminders are inherited from workspace settings."
        ),
    )
    update_reminder_frequency_in_weeks: Optional[float] = Field(
        None,
        description=(
            "The n-weekly frequency at which to prompt for project updates. When "
            "not set, reminders are inherited from workspace settings."
        ),
    )
    frequency_resolution: Optional[FrequencyResolutionType] = Field(
        None,
        description=(
            "The resolution type for the update reminder frequency (e.g., weekly, biweekly)."
        ),
    )
    update_reminders_day: Optional[Day] = Field(
        None, description="The day of the week on which to prompt for project updates."
    )
    update_reminders_hour: Optional[int] = Field(
        None,
        ge=0,
        le=23,
        description="The hour of the day (0-23) at which to prompt for project updates.",
    )
    project_update_reminders_paused_until_at: Optional[str] = Field(
        None,
        description=(
            "The time until which project update reminders are paused, as an ISO "
            "8601 timestamp. This schema cannot send null to resume reminders — "
            "absent means unchanged."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> ProjectUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("projectUpdate needs at least one field to change.")
        return self


class ProjectUpdateVariables(BaseModel):
    """Variables for the ``projectUpdate`` mutation."""

    id: str = Field(..., description="The project's UUID, or the slug from its URL.")
    input: ProjectUpdateInput = Field(..., description="The fields to change.")


class ProjectUpdateRequest(BaseModel):
    """Update a project."""

    variables: Annotated[
        ProjectUpdateVariables,
        Field(..., description="The project to update."),
        Body(envelop=True),
    ]


class ProjectDeleteVariables(BaseModel):
    """Variables for the ``projectDelete`` mutation."""

    id: str = Field(..., description="The project's UUID.")


class ProjectDeleteRequest(BaseModel):
    """Move a project to the trash."""

    variables: Annotated[
        ProjectDeleteVariables,
        Field(..., description="The project to delete."),
        Body(envelop=True),
    ]


class ProjectUnarchiveVariables(BaseModel):
    """Variables for the ``projectUnarchive`` mutation."""

    id: str = Field(..., description="The project's UUID.")


class ProjectUnarchiveRequest(BaseModel):
    """Restore a project from the trash."""

    variables: Annotated[
        ProjectUnarchiveVariables,
        Field(..., description="The project to restore."),
        Body(envelop=True),
    ]


class ProjectLabelLinkVariables(BaseModel):
    """Variables for ``projectAddLabel`` and ``projectRemoveLabel``."""

    id: str = Field(..., description="The project's UUID.")
    label_id: str = Field(..., description="The project label's UUID.")


class ProjectAddLabelRequest(BaseModel):
    """Add one label to a project."""

    variables: Annotated[
        ProjectLabelLinkVariables,
        Field(..., description="The project and the label."),
        Body(envelop=True),
    ]


class ProjectRemoveLabelRequest(BaseModel):
    """Remove one label from a project."""

    variables: Annotated[
        ProjectLabelLinkVariables,
        Field(..., description="The project and the label."),
        Body(envelop=True),
    ]


class ProjectStatusesListRequest(BaseModel):
    """List the statuses a project can be in."""

    variables: Annotated[
        PageVariables,
        Field(default_factory=PageVariables, description="Paging."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# milestones
# -----------------------------------------------------


class ProjectMilestonesListVariables(PageVariables):
    """Variables for the ``projectMilestones`` connection."""

    filter: Optional[ProjectMilestoneFilter] = Field(
        default=None, description="Narrow the milestones returned, usually to one project."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived milestones in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class ProjectMilestonesListRequest(BaseModel):
    """List project milestones."""

    variables: Annotated[
        ProjectMilestonesListVariables,
        Field(default_factory=ProjectMilestonesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class ProjectMilestoneGetVariables(BaseModel):
    """Variables for the ``projectMilestone`` query."""

    id: str = Field(..., description="The milestone's UUID.")


class ProjectMilestoneGetRequest(BaseModel):
    """Get one project milestone."""

    variables: Annotated[
        ProjectMilestoneGetVariables,
        Field(..., description="Which milestone to fetch."),
        Body(envelop=True),
    ]


class ProjectMilestoneCreateInput(BaseModel):
    """The input to ``projectMilestoneCreate``."""

    name: str = Field(..., description="The name of the project milestone.")
    project_id: str = Field(..., description="Related project for the project milestone.")
    description: Optional[str] = Field(
        None, description="The description of the project milestone."
    )
    target_date: Optional[str] = Field(
        None, description="The planned target date of the project milestone, as `YYYY-MM-DD`."
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order for the project milestone within a project."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )


class ProjectMilestoneCreateVariables(BaseModel):
    """Variables for the ``projectMilestoneCreate`` mutation."""

    input: ProjectMilestoneCreateInput = Field(..., description="The milestone to create.")


class ProjectMilestoneCreateRequest(BaseModel):
    """Create a project milestone."""

    variables: Annotated[
        ProjectMilestoneCreateVariables,
        Field(..., description="The milestone to create."),
        Body(envelop=True),
    ]


class ProjectMilestoneUpdateInput(BaseModel):
    """The fields ``projectMilestoneUpdate`` changes. All optional."""

    name: Optional[str] = Field(None, description="The name of the project milestone.")
    description: Optional[str] = Field(
        None, description="The description of the project milestone."
    )
    project_id: Optional[str] = Field(
        None, description="Related project for the project milestone."
    )
    target_date: Optional[str] = Field(
        None, description="The planned target date of the project milestone, as `YYYY-MM-DD`."
    )
    sort_order: Optional[float] = Field(
        None, description="The sort order for the project milestone within a project."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> ProjectMilestoneUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("projectMilestoneUpdate needs at least one field to change.")
        return self


class ProjectMilestoneUpdateVariables(BaseModel):
    """Variables for the ``projectMilestoneUpdate`` mutation."""

    id: str = Field(..., description="The milestone's UUID.")
    input: ProjectMilestoneUpdateInput = Field(..., description="The fields to change.")


class ProjectMilestoneUpdateRequest(BaseModel):
    """Update a project milestone."""

    variables: Annotated[
        ProjectMilestoneUpdateVariables,
        Field(..., description="The milestone to update."),
        Body(envelop=True),
    ]


class ProjectMilestoneDeleteVariables(BaseModel):
    """Variables for the ``projectMilestoneDelete`` mutation."""

    id: str = Field(..., description="The milestone's UUID.")


class ProjectMilestoneDeleteRequest(BaseModel):
    """Delete a project milestone."""

    variables: Annotated[
        ProjectMilestoneDeleteVariables,
        Field(..., description="The milestone to delete."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# status updates posted on a project
# -----------------------------------------------------


class ProjectUpdatesListVariables(PageVariables):
    """Variables for the ``projectUpdates`` connection."""

    filter: Optional[ProjectUpdateFilter] = Field(
        default=None, description="Narrow the updates returned, usually to one project."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived updates in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class ProjectUpdatesListRequest(BaseModel):
    """Read the status updates posted on projects."""

    variables: Annotated[
        ProjectUpdatesListVariables,
        Field(default_factory=ProjectUpdatesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class ProjectUpdateGetVariables(BaseModel):
    """Variables for the ``projectUpdate`` *query*."""

    id: str = Field(..., description="The status update's UUID.")


class ProjectUpdateGetRequest(BaseModel):
    """Get one project status update."""

    variables: Annotated[
        ProjectUpdateGetVariables,
        Field(..., description="Which status update to fetch."),
        Body(envelop=True),
    ]


class ProjectUpdateCreateInput(BaseModel):
    """The input to ``projectUpdateCreate`` — a status post on a project."""

    project_id: str = Field(..., description="The project to associate the project update with.")
    body: Optional[str] = Field(
        None, description="The content of the project update in markdown format."
    )
    health: Optional[ProjectHealth] = Field(
        None, description="The health of the project at the time of the update."
    )
    is_diff_hidden: Optional[bool] = Field(
        None,
        description="Whether the diff between the current update and the previous one is hidden.",
    )
    id: Optional[str] = Field(
        None,
        description="The identifier. If none is provided, the backend will generate one.",
    )


class ProjectUpdateCreateVariables(BaseModel):
    """Variables for the ``projectUpdateCreate`` mutation."""

    input: ProjectUpdateCreateInput = Field(..., description="The status update to post.")


class ProjectUpdateCreateRequest(BaseModel):
    """Post a status update on a project."""

    variables: Annotated[
        ProjectUpdateCreateVariables,
        Field(..., description="The status update to post."),
        Body(envelop=True),
    ]


class ProjectUpdateUpdateInput(BaseModel):
    """The fields ``projectUpdateUpdate`` changes. All optional.

    Narrower than the create input: Linear accepts ``isDiffHidden`` when the
    update is posted and not afterwards, so it is absent here on purpose.
    """

    body: Optional[str] = Field(
        None, description="The content of the project update in markdown format."
    )
    health: Optional[ProjectHealth] = Field(
        None, description="The health of the project at the time of the update."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> ProjectUpdateUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("projectUpdateUpdate needs at least one field to change.")
        return self


class ProjectUpdateUpdateVariables(BaseModel):
    """Variables for the ``projectUpdateUpdate`` mutation."""

    id: str = Field(..., description="The status update's UUID.")
    input: ProjectUpdateUpdateInput = Field(..., description="The fields to change.")


class ProjectUpdateUpdateRequest(BaseModel):
    """Edit a project status update."""

    variables: Annotated[
        ProjectUpdateUpdateVariables,
        Field(..., description="The status update to edit."),
        Body(envelop=True),
    ]


class ProjectUpdateArchiveVariables(BaseModel):
    """Variables for the ``projectUpdateArchive`` mutation."""

    id: str = Field(..., description="The status update's UUID.")


class ProjectUpdateArchiveRequest(BaseModel):
    """Archive a project status update."""

    variables: Annotated[
        ProjectUpdateArchiveVariables,
        Field(..., description="The status update to archive."),
        Body(envelop=True),
    ]
