"""Request schemas for Linear's issue operations.

An issue is the unit of work in Linear, and almost everything else in this pack
hangs off one. The operations here cover reading, writing, filing, labelling,
subscribing, linking and archiving.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import (
    PRIORITY_DESCRIPTION,
    PageVariables,
    PaginationOrderBy,
    Priority,
    SlaDayCountType,
)
from charter.packs.linear.types.filters import IssueFilter
from charter.types import Body

__all__ = [
    "IssuesListRequest",
    "IssueGetRequest",
    "IssueCreateRequest",
    "IssueUpdateRequest",
    "IssueDeleteRequest",
    "IssueArchiveRequest",
    "IssueUnarchiveRequest",
    "IssueAddLabelRequest",
    "IssueRemoveLabelRequest",
    "IssueSubscribeRequest",
    "IssueUnsubscribeRequest",
    "IssueBatchUpdateRequest",
    "IssueRelationsListRequest",
    "IssueRelationGetRequest",
    "IssueRelationCreateRequest",
    "IssueRelationUpdateRequest",
    "IssueRelationDeleteRequest",
    "IssueRelationType",
]


IssueRelationType = Literal["blocks", "duplicate", "related", "similar"]
"""How two issues are linked. ``blocks`` is directional — the issue named in
``issue_id`` blocks the one in ``related_issue_id``."""


# -----------------------------------------------------
# reading
# -----------------------------------------------------


class IssuesListVariables(PageVariables):
    """Variables for the ``issues`` connection."""

    filter: Optional[IssueFilter] = Field(
        default=None, description="Narrow the issues returned. Conditions combine with AND."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None,
        description=(
            "Sort by 'createdAt' or 'updatedAt'. Linear sorts by 'updatedAt' by "
            "default."
        ),
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived issues in the results."
    )


class IssuesListRequest(BaseModel):
    """List issues, optionally filtered.

    API Reference: https://linear.app/developers/filtering
    """

    variables: Annotated[
        IssuesListVariables,
        Field(default_factory=IssuesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class IssueGetVariables(BaseModel):
    """Variables for the ``issue`` query."""

    id: str = Field(
        ...,
        description=(
            "The issue's UUID, or its human identifier such as 'ENG-123'. Both are "
            "accepted here."
        ),
    )


class IssueGetRequest(BaseModel):
    """Get one issue, with its comments."""

    variables: Annotated[
        IssueGetVariables,
        Field(..., description="Which issue to fetch."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# writing
# -----------------------------------------------------


class IssueCreateInput(BaseModel):
    """The input to ``issueCreate``.

    API Reference: https://linear.app/developers/graphql
    """

    team_id: str = Field(
        ...,
        description=(
            "UUID of the team the issue belongs to. Required. Use `teams_list` to "
            "resolve a team key such as 'ENG' to its UUID."
        ),
    )
    title: str = Field(..., description="The issue title.")
    description: Optional[str] = Field(
        None, description="The issue description in markdown format."
    )
    assignee_id: Optional[str] = Field(
        None,
        description=(
            "The identifier of the user to assign the issue to. Use `users_list` "
            "to resolve a name."
        ),
    )
    priority: Optional[Priority] = Field(None, description=PRIORITY_DESCRIPTION)
    state_id: Optional[str] = Field(
        None,
        description=(
            "The team state of the issue. Use `workflow_states_list` to resolve a "
            "state name such as 'In Progress'. Omit to use the team's default."
        ),
    )
    label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the issue labels associated with this ticket."
    )
    project_id: Optional[str] = Field(
        None, description="The project associated with the issue."
    )
    project_milestone_id: Optional[str] = Field(
        None, description="The project milestone associated with the issue."
    )
    cycle_id: Optional[str] = Field(
        None, description="The cycle associated with the issue."
    )
    parent_id: Optional[str] = Field(
        None,
        description=(
            "The identifier of the parent issue, to create this as a sub-issue. "
            "Can be a UUID or issue identifier (e.g., 'LIN-123')."
        ),
    )
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this ticket."
    )
    estimate: Optional[int] = Field(
        None, description="The estimated complexity of the issue."
    )
    due_date: Optional[str] = Field(
        None, description="The date at which the issue is due, as `YYYY-MM-DD`."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the issue related to other issues."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description="The position of the issue related to other issues, when ordered by priority.",
    )
    sub_issue_sort_order: Optional[float] = Field(
        None, description="The position of the issue in parent's sub-issue list."
    )
    preserve_sort_order_on_create: Optional[bool] = Field(
        None, description="Whether the passed sort order should be preserved."
    )
    delegate_id: Optional[str] = Field(
        None, description="The identifier of the agent user to delegate the issue to."
    )
    sla_type: Optional[SlaDayCountType] = Field(
        None,
        description=(
            "The SLA day count type for the issue. Whether SLA should be business "
            "days only or calendar days (default)."
        ),
    )
    template_id: Optional[str] = Field(
        None,
        description=(
            "The identifier of a template the issue should be created from. If "
            "other values are provided in the input, they will override template "
            "values."
        ),
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the issue."
    )
    use_default_template: Optional[bool] = Field(
        None,
        description=(
            "Whether to use the default template for the team. When set to true, "
            "the default template of this team based on user's membership will "
            "be applied."
        ),
    )
    source_comment_id: Optional[str] = Field(
        None, description="The comment the issue is created from."
    )
    reference_comment_id: Optional[str] = Field(
        None, description="The comment the issue is referencing."
    )
    release_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the releases to associate with this issue."
    )
    created_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the issue was created (e.g. if importing from "
            "another system). Must be a time in the past. If none is provided, "
            "the backend will generate the time as now."
        ),
    )
    completed_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the issue was completed (e.g. if importing from "
            "another system). Must be a time in the past and after createdAt. "
            "Cannot be provided with an incompatible workflow state."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class IssueCreateVariables(BaseModel):
    """Variables for the ``issueCreate`` mutation."""

    input: IssueCreateInput = Field(..., description="The issue to create.")


class IssueCreateRequest(BaseModel):
    """Create an issue."""

    variables: Annotated[
        IssueCreateVariables,
        Field(..., description="The issue to create."),
        Body(envelop=True),
    ]


class IssueUpdateInput(BaseModel):
    """The input to ``issueUpdate``. Every field is optional.

    Labels can be changed two ways, and they mean different things:
    ``label_ids`` *replaces* the issue's labels, while ``added_label_ids`` and
    ``removed_label_ids`` adjust the set that is already there. Prefer the
    additive pair unless you genuinely mean to overwrite.

    API Reference: https://linear.app/developers/graphql
    """

    title: Optional[str] = Field(None, description="The issue title.")
    description: Optional[str] = Field(
        None,
        description="The issue description in markdown format. Replaces the existing one.",
    )
    assignee_id: Optional[str] = Field(
        None, description="The identifier of the user to assign the issue to."
    )
    priority: Optional[Priority] = Field(None, description=PRIORITY_DESCRIPTION)
    state_id: Optional[str] = Field(
        None,
        description=(
            "The team state of the issue. This is how an issue is closed: move it "
            "to a state whose type is 'completed' or 'canceled'."
        ),
    )
    label_ids: Optional[List[str]] = Field(
        None,
        description=(
            "The complete set of label identifiers for the issue. This *replaces* "
            "the issue's labels; use `added_label_ids` to add to them instead."
        ),
    )
    added_label_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the issue labels to be added to this issue."
    )
    removed_label_ids: Optional[List[str]] = Field(
        None,
        description="The identifiers of the issue labels to be removed from this issue.",
    )
    team_id: Optional[str] = Field(
        None, description="The identifier of the team to move the issue to."
    )
    project_id: Optional[str] = Field(
        None, description="The project associated with the issue."
    )
    project_milestone_id: Optional[str] = Field(
        None, description="The project milestone associated with the issue."
    )
    cycle_id: Optional[str] = Field(
        None, description="The cycle associated with the issue."
    )
    parent_id: Optional[str] = Field(
        None, description="The identifier of the parent issue."
    )
    subscriber_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the users subscribing to this ticket."
    )
    estimate: Optional[int] = Field(
        None, description="The estimated complexity of the issue."
    )
    due_date: Optional[str] = Field(
        None, description="The date at which the issue is due, as `YYYY-MM-DD`."
    )
    snoozed_until_at: Optional[str] = Field(
        None, description="The time until which the issue is snoozed, as an ISO 8601 timestamp."
    )
    snoozed_by_id: Optional[str] = Field(
        None, description="The identifier of the user who snoozed the issue."
    )
    delegate_id: Optional[str] = Field(
        None, description="The identifier of the agent user to delegate the issue to."
    )
    trashed: Optional[bool] = Field(
        None, description="Whether the issue has been moved to the trash."
    )
    sort_order: Optional[float] = Field(
        None, description="The position of the issue related to other issues."
    )
    priority_sort_order: Optional[float] = Field(
        None,
        description="The position of the issue related to other issues, when ordered by priority.",
    )
    sub_issue_sort_order: Optional[float] = Field(
        None, description="The position of the issue in parent's sub-issue list."
    )
    sla_type: Optional[SlaDayCountType] = Field(
        None,
        description=(
            "The SLA day count type for the issue. Whether SLA should be business "
            "days only or calendar days (default)."
        ),
    )
    last_applied_template_id: Optional[str] = Field(
        None, description="The ID of the last template applied to the issue."
    )
    release_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the releases associated with this issue."
    )
    added_release_ids: Optional[List[str]] = Field(
        None, description="The identifiers of the releases to be added to this issue."
    )
    removed_release_ids: Optional[List[str]] = Field(
        None,
        description="The identifiers of the releases to be removed from this issue.",
    )
    auto_closed_by_parent_closing: Optional[bool] = Field(
        None,
        description=(
            "Whether the issue was automatically closed because its parent issue "
            "was closed."
        ),
    )
    inherits_shared_access: Optional[bool] = Field(
        None,
        description=(
            "Whether this issue should inherit shared access from its parent issue."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> IssueUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError(
                "issueUpdate needs at least one field to change; an empty input "
                "would send a mutation that does nothing."
            )
        return self


class IssueUpdateVariables(BaseModel):
    """Variables for the ``issueUpdate`` mutation."""

    id: str = Field(..., description="UUID or identifier of the issue to update.")
    input: IssueUpdateInput = Field(..., description="The fields to change.")


class IssueUpdateRequest(BaseModel):
    """Update an issue."""

    variables: Annotated[
        IssueUpdateVariables,
        Field(..., description="Which issue to update, and how."),
        Body(envelop=True),
    ]


class IssueBatchUpdateVariables(BaseModel):
    """Variables for the ``issueBatchUpdate`` mutation."""

    ids: List[str] = Field(
        ...,
        min_length=1,
        description="The UUIDs of the issues to update. These must be UUIDs, not identifiers such as 'ENG-123'.",
    )
    input: IssueUpdateInput = Field(
        ..., description="The fields to change, applied to every issue in `ids`."
    )


class IssueBatchUpdateRequest(BaseModel):
    """Apply the same change to many issues at once."""

    variables: Annotated[
        IssueBatchUpdateVariables,
        Field(..., description="Which issues to update, and how."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# removing
# -----------------------------------------------------


class IssueDeleteVariables(BaseModel):
    """Variables for the ``issueDelete`` mutation.

    Linear's delete is a *trash*, not an erasure: the issue leaves the active
    lists and can be restored. ``permanently_delete`` is the irreversible one,
    which is why it is absent by default rather than carrying the API's own
    documented value.
    """

    id: str = Field(..., description="The issue's UUID.")
    permanently_delete: Optional[bool] = Field(
        None,
        description=(
            "Permanently delete the issue instead of moving it to the trash. This "
            "cannot be undone. Absent, the issue is trashed and can be restored."
        ),
    )


class IssueDeleteRequest(BaseModel):
    """Move an issue to the trash, or permanently delete it."""

    variables: Annotated[
        IssueDeleteVariables,
        Field(..., description="The issue to delete."),
        Body(envelop=True),
    ]


class IssueArchiveVariables(BaseModel):
    """Variables for the ``issueArchive`` mutation."""

    id: str = Field(..., description="The issue's UUID.")
    trash: Optional[bool] = Field(
        None,
        description=(
            "Send the issue to the trash as well as archiving it. Absent, it is "
            "archived and stays findable."
        ),
    )


class IssueArchiveRequest(BaseModel):
    """Archive an issue."""

    variables: Annotated[
        IssueArchiveVariables,
        Field(..., description="The issue to archive."),
        Body(envelop=True),
    ]


class IssueUnarchiveVariables(BaseModel):
    """Variables for the ``issueUnarchive`` mutation."""

    id: str = Field(..., description="The issue's UUID.")


class IssueUnarchiveRequest(BaseModel):
    """Restore an archived issue."""

    variables: Annotated[
        IssueUnarchiveVariables,
        Field(..., description="The issue to restore."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# labels and subscribers on one issue
# -----------------------------------------------------


class IssueLabelLinkVariables(BaseModel):
    """Variables for ``issueAddLabel`` and ``issueRemoveLabel``."""

    id: str = Field(..., description="The issue's UUID.")
    label_id: str = Field(..., description="The label's UUID.")


class IssueAddLabelRequest(BaseModel):
    """Add one label to an issue."""

    variables: Annotated[
        IssueLabelLinkVariables,
        Field(..., description="The issue and the label."),
        Body(envelop=True),
    ]


class IssueRemoveLabelRequest(BaseModel):
    """Remove one label from an issue."""

    variables: Annotated[
        IssueLabelLinkVariables,
        Field(..., description="The issue and the label."),
        Body(envelop=True),
    ]


class IssueSubscriptionVariables(BaseModel):
    """Variables for ``issueSubscribe`` and ``issueUnsubscribe``.

    The user is named by UUID or by email; giving neither acts on the
    authenticated user.
    """

    id: str = Field(..., description="The issue's UUID.")
    user_id: Optional[str] = Field(
        None,
        description=(
            "The UUID of the user to subscribe. Omit both this and `user_email` "
            "to act on the authenticated user."
        ),
    )
    user_email: Optional[str] = Field(
        None, description="The email address of the user to subscribe."
    )

    @model_validator(mode="after")
    def _one_way_of_naming_the_user(self) -> IssueSubscriptionVariables:
        if self.user_id is not None and self.user_email is not None:
            raise ValueError(
                "Name the user by `user_id` or by `user_email`, not both."
            )
        return self


class IssueSubscribeRequest(BaseModel):
    """Subscribe a user to an issue's updates."""

    variables: Annotated[
        IssueSubscriptionVariables,
        Field(..., description="The issue, and who to subscribe."),
        Body(envelop=True),
    ]


class IssueUnsubscribeRequest(BaseModel):
    """Unsubscribe a user from an issue's updates."""

    variables: Annotated[
        IssueSubscriptionVariables,
        Field(..., description="The issue, and who to unsubscribe."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# relations between issues
# -----------------------------------------------------


class IssueRelationsListVariables(PageVariables):
    """Variables for the ``issueRelations`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include relations on archived issues."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class IssueRelationsListRequest(BaseModel):
    """List the links between issues."""

    variables: Annotated[
        IssueRelationsListVariables,
        Field(default_factory=IssueRelationsListVariables, description="Paging."),
        Body(envelop=True),
    ]


class IssueRelationGetVariables(BaseModel):
    """Variables for the ``issueRelation`` query."""

    id: str = Field(..., description="The relation's UUID.")


class IssueRelationGetRequest(BaseModel):
    """Get one issue relation."""

    variables: Annotated[
        IssueRelationGetVariables,
        Field(..., description="Which relation to fetch."),
        Body(envelop=True),
    ]


class IssueRelationCreateInput(BaseModel):
    """The input to ``issueRelationCreate``.

    ``blocks`` and ``duplicate`` are directional: the issue in ``issue_id`` is
    the one doing the blocking, or the one that is the duplicate.
    """

    issue_id: str = Field(..., description="The identifier of the issue that is related.")
    related_issue_id: str = Field(
        ..., description="The identifier of the related issue."
    )
    type: IssueRelationType = Field(
        ..., description="The type of relation between the two issues."
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend "
            "will generate one."
        ),
    )


class IssueRelationCreateVariables(BaseModel):
    """Variables for the ``issueRelationCreate`` mutation."""

    input: IssueRelationCreateInput = Field(..., description="The relation to create.")


class IssueRelationCreateRequest(BaseModel):
    """Link two issues."""

    variables: Annotated[
        IssueRelationCreateVariables,
        Field(..., description="The relation to create."),
        Body(envelop=True),
    ]


class IssueRelationUpdateInput(BaseModel):
    """The fields ``issueRelationUpdate`` changes. All optional."""

    issue_id: Optional[str] = Field(
        None, description="The identifier of the issue that is related."
    )
    related_issue_id: Optional[str] = Field(
        None, description="The identifier of the related issue."
    )
    type: Optional[IssueRelationType] = Field(
        None, description="The type of relation between the two issues."
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> IssueRelationUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError(
                "issueRelationUpdate needs at least one field to change."
            )
        return self


class IssueRelationUpdateVariables(BaseModel):
    """Variables for the ``issueRelationUpdate`` mutation."""

    id: str = Field(..., description="The relation's UUID.")
    input: IssueRelationUpdateInput = Field(..., description="The fields to change.")


class IssueRelationUpdateRequest(BaseModel):
    """Change how two issues are linked."""

    variables: Annotated[
        IssueRelationUpdateVariables,
        Field(..., description="The relation to update."),
        Body(envelop=True),
    ]


class IssueRelationDeleteVariables(BaseModel):
    """Variables for the ``issueRelationDelete`` mutation."""

    id: str = Field(..., description="The relation's UUID.")


class IssueRelationDeleteRequest(BaseModel):
    """Unlink two issues."""

    variables: Annotated[
        IssueRelationDeleteVariables,
        Field(..., description="The relation to remove."),
        Body(envelop=True),
    ]
