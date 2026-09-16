"""Request schemas for the workspace lookups: teams, members, states, organization.

These are the tools that turn a name into a UUID. Linear's write operations take
identifiers and nothing else — ``issue_create`` wants a ``team_id``, not
``"ENG"`` — so almost every sequence an agent runs starts here.

**Team administration is deliberately absent.** Linear's ``teamCreate`` and
``teamUpdate`` carry 40 and 55 fields respectively, nearly all of them workspace
settings: cycle cadence, triage routing, estimation scales, SLA policy,
auto-archive thresholds, Slack and GitHub wiring. Those configure a workspace
rather than do work in one, and an agent that reaches for them is doing
something a human should confirm in Linear's own settings UI. Teams are readable
here, and their membership is writable; the settings are not.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import TeamFilter, UserFilter, WorkflowStateFilter
from charter.types import Body

__all__ = [
    "ViewerRequest",
    "OrganizationRequest",
    "TeamsListRequest",
    "TeamGetRequest",
    "UsersListRequest",
    "UserGetRequest",
    "WorkflowStatesListRequest",
    "WorkflowStateGetRequest",
    "WorkflowStateCreateRequest",
    "WorkflowStateUpdateRequest",
    "WorkflowStateArchiveRequest",
    "TeamMembershipsListRequest",
    "TeamMembershipGetRequest",
    "TeamMembershipCreateRequest",
    "TeamMembershipUpdateRequest",
    "TeamMembershipDeleteRequest",
]

WORKFLOW_STATE_TYPES = (
    "triage",
    "backlog",
    "unstarted",
    "started",
    "completed",
    "canceled",
)
_STATE_TYPE_DESCRIPTION = (
    "The category the state belongs to: 'triage', 'backlog', 'unstarted', "
    "'started', 'completed' or 'canceled'. Linear types this as a string rather "
    "than a closed enum, so treat the list as the documented set rather than an "
    "exhaustive one."
)


class NoVariables(BaseModel):
    """A query that takes no arguments."""


class ViewerRequest(BaseModel):
    """Get the authenticated user.

    API Reference: https://linear.app/developers/graphql
    """

    variables: Annotated[
        Optional[NoVariables],
        Field(None, description="This query takes no variables."),
        Body(envelop=True),
    ]


class OrganizationRequest(BaseModel):
    """Get the workspace itself.

    API Reference: https://linear.app/developers/graphql
    """

    variables: Annotated[
        Optional[NoVariables],
        Field(None, description="This query takes no variables."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# teams
# -----------------------------------------------------


class TeamsListVariables(PageVariables):
    """Variables for the ``teams`` connection."""

    filter: Optional[TeamFilter] = Field(
        default=None, description="Narrow the teams returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived teams in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class TeamsListRequest(BaseModel):
    """List the workspace's teams. Use this to resolve a team key to its UUID."""

    variables: Annotated[
        TeamsListVariables,
        Field(default_factory=TeamsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class TeamGetVariables(BaseModel):
    """Variables for the ``team`` query."""

    id: str = Field(..., description="The team's UUID, or its key such as 'ENG'.")


class TeamGetRequest(BaseModel):
    """Get one team."""

    variables: Annotated[
        TeamGetVariables,
        Field(..., description="Which team to fetch."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# users
# -----------------------------------------------------


class UsersListVariables(PageVariables):
    """Variables for the ``users`` connection."""

    filter: Optional[UserFilter] = Field(
        default=None, description="Narrow the users returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived users in the results."
    )
    include_disabled: Optional[bool] = Field(
        default=None, description="Include suspended users in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class UsersListRequest(BaseModel):
    """List workspace members. Use this to resolve a name to an assignee UUID."""

    variables: Annotated[
        UsersListVariables,
        Field(default_factory=UsersListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class UserGetVariables(BaseModel):
    """Variables for the ``user`` query."""

    id: str = Field(
        ...,
        description="The user's UUID, or 'me' for the authenticated user.",
    )


class UserGetRequest(BaseModel):
    """Get one workspace member."""

    variables: Annotated[
        UserGetVariables,
        Field(..., description="Which user to fetch."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# workflow states
# -----------------------------------------------------


class WorkflowStatesListVariables(PageVariables):
    """Variables for the ``workflowStates`` connection."""

    filter: Optional[WorkflowStateFilter] = Field(
        default=None, description="Narrow the states returned, usually to one team."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived states in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class WorkflowStatesListRequest(BaseModel):
    """List workflow states — the statuses an issue can be moved between."""

    variables: Annotated[
        WorkflowStatesListVariables,
        Field(default_factory=WorkflowStatesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class WorkflowStateGetVariables(BaseModel):
    """Variables for the ``workflowState`` query."""

    id: str = Field(..., description="The state's UUID.")


class WorkflowStateGetRequest(BaseModel):
    """Get one workflow state."""

    variables: Annotated[
        WorkflowStateGetVariables,
        Field(..., description="Which state to fetch."),
        Body(envelop=True),
    ]


class WorkflowStateCreateInput(BaseModel):
    """The input to ``workflowStateCreate``."""

    name: str = Field(..., description="The name of the state.")
    team_id: str = Field(
        ..., description="The team associated with the state."
    )
    type: str = Field(..., description=_STATE_TYPE_DESCRIPTION)
    color: str = Field(
        ..., description="The color of the state, as a hex string such as '#4ea7fc'."
    )
    description: Optional[str] = Field(
        None, description="The description of the state."
    )
    position: Optional[float] = Field(
        None, description="The position of the state in the team's workflow."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class WorkflowStateCreateVariables(BaseModel):
    """Variables for the ``workflowStateCreate`` mutation."""

    input: WorkflowStateCreateInput = Field(..., description="The state to create.")


class WorkflowStateCreateRequest(BaseModel):
    """Create a workflow state."""

    variables: Annotated[
        WorkflowStateCreateVariables,
        Field(..., description="The state to create."),
        Body(envelop=True),
    ]


class WorkflowStateUpdateInput(BaseModel):
    """The fields ``workflowStateUpdate`` changes. All optional.

    The state's ``type`` and its team are fixed at creation; Linear's update
    input does not accept either.
    """

    name: Optional[str] = Field(None, description="The name of the state.")
    color: Optional[str] = Field(
        None, description="The color of the state, as a hex string such as '#4ea7fc'."
    )
    description: Optional[str] = Field(
        None, description="The description of the state."
    )
    position: Optional[float] = Field(
        None, description="The position of the state in the team's workflow."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> WorkflowStateUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("workflowStateUpdate needs at least one field to change.")
        return self


class WorkflowStateUpdateVariables(BaseModel):
    """Variables for the ``workflowStateUpdate`` mutation."""

    id: str = Field(..., description="The state's UUID.")
    input: WorkflowStateUpdateInput = Field(..., description="The fields to change.")


class WorkflowStateUpdateRequest(BaseModel):
    """Update a workflow state."""

    variables: Annotated[
        WorkflowStateUpdateVariables,
        Field(..., description="The state to update."),
        Body(envelop=True),
    ]


class WorkflowStateArchiveVariables(BaseModel):
    """Variables for the ``workflowStateArchive`` mutation."""

    id: str = Field(..., description="The state's UUID.")


class WorkflowStateArchiveRequest(BaseModel):
    """Archive a workflow state."""

    variables: Annotated[
        WorkflowStateArchiveVariables,
        Field(..., description="The state to archive."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# team membership
# -----------------------------------------------------


class TeamMembershipsListVariables(PageVariables):
    """Variables for the ``teamMemberships`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived memberships in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class TeamMembershipsListRequest(BaseModel):
    """List who belongs to which team."""

    variables: Annotated[
        TeamMembershipsListVariables,
        Field(default_factory=TeamMembershipsListVariables, description="Paging."),
        Body(envelop=True),
    ]


class TeamMembershipGetVariables(BaseModel):
    """Variables for the ``teamMembership`` query."""

    id: str = Field(..., description="The membership's UUID.")


class TeamMembershipGetRequest(BaseModel):
    """Get one team membership."""

    variables: Annotated[
        TeamMembershipGetVariables,
        Field(..., description="Which membership to fetch."),
        Body(envelop=True),
    ]


class TeamMembershipCreateInput(BaseModel):
    """The input to ``teamMembershipCreate``."""

    team_id: str = Field(..., description="The identifier of the team associated with the membership.")
    user_id: str = Field(..., description="The identifier of the user associated with the membership.")
    owner: Optional[bool] = Field(
        None, description="Whether the user is the owner of the team."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the item in the users list."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class TeamMembershipCreateVariables(BaseModel):
    """Variables for the ``teamMembershipCreate`` mutation."""

    input: TeamMembershipCreateInput = Field(..., description="The membership to create.")


class TeamMembershipCreateRequest(BaseModel):
    """Add a member to a team."""

    variables: Annotated[
        TeamMembershipCreateVariables,
        Field(..., description="The membership to create."),
        Body(envelop=True),
    ]


class TeamMembershipUpdateInput(BaseModel):
    """The fields ``teamMembershipUpdate`` changes. All optional."""

    owner: Optional[bool] = Field(
        None, description="Whether the user is the owner of the team."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the item in the users list."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> TeamMembershipUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("teamMembershipUpdate needs at least one field to change.")
        return self


class TeamMembershipUpdateVariables(BaseModel):
    """Variables for the ``teamMembershipUpdate`` mutation."""

    id: str = Field(..., description="The membership's UUID.")
    input: TeamMembershipUpdateInput = Field(..., description="The fields to change.")


class TeamMembershipUpdateRequest(BaseModel):
    """Change a team membership, such as making someone the team's owner."""

    variables: Annotated[
        TeamMembershipUpdateVariables,
        Field(..., description="The membership to update."),
        Body(envelop=True),
    ]


class TeamMembershipDeleteVariables(BaseModel):
    """Variables for the ``teamMembershipDelete`` mutation."""

    id: str = Field(..., description="The membership's UUID.")


class TeamMembershipDeleteRequest(BaseModel):
    """Remove a member from a team."""

    variables: Annotated[
        TeamMembershipDeleteVariables,
        Field(..., description="The membership to remove."),
        Body(envelop=True),
    ]
