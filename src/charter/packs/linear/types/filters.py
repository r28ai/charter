"""The filter inputs Linear's connections accept.

Linear builds a filter out of one comparator object per field —
``{"title": {"containsIgnoreCase": "flake"}}`` — and every connection in the
API takes a filter shaped this way. They live in one module because they are
mutually recursive: an issue filter reaches a team filter, a team filter reaches
an issue filter, and ``and``/``or`` reach back into themselves.

**Boolean composition is modelled.** ``and`` and ``or`` each take a list of
filters of the same type, nested arbitrarily deep, which is how Linear expresses
"urgent *or* assigned to me". An earlier version of this pack left them out and
said so as a known limit; they are here now, and
``test_a_boolean_composition_survives_to_the_wire`` holds them in place.

Pydantic needs the self-reference declared as a string annotation and the model
rebuilt afterwards, which is what the ``model_rebuild()`` calls at the bottom
are for.

API Reference: https://linear.app/developers/filtering
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from charter.packs.linear.types.common import (
    BooleanComparator,
    ContentComparator,
    CyclePeriodComparator,
    DateComparator,
    EstimateComparator,
    IdComparator,
    NullableDateComparator,
    NullableNumberComparator,
    NullableStringComparator,
    NullableTimelessDateComparator,
    NumberComparator,
    RelationExistsComparator,
    ReleasePipelineTypeComparator,
    ReleaseStageTypeComparator,
    SlaStatusComparator,
    SourceMetadataComparator,
    StringComparator,
    TeamVisibilityComparator,
)

__all__ = [
    "IssueFilter",
    "WorkflowStateFilter",
    "UserFilter",
    "TeamFilter",
    "ProjectFilter",
    "CommentFilter",
    "IssueLabelFilter",
    "CycleFilter",
    "InitiativeFilter",
    "DocumentFilter",
    "AttachmentFilter",
    "CustomerFilter",
    "CustomerNeedFilter",
    "ProjectMilestoneFilter",
    "TemplateFilter",
    "ProjectUpdateFilter",
    "ProjectStatusFilter",
    "CustomerStatusFilter",
    "CustomerTierFilter",
    "ReactionFilter",
    "ActivityFilter",
    "FeedItemFilter",
    "ReleaseFilter",
    "IssueCollectionFilter",
    "UserCollectionFilter",
    "TeamCollectionFilter",
    "ProjectCollectionFilter",
    "ProjectMilestoneCollectionFilter",
    "CommentCollectionFilter",
    "AttachmentCollectionFilter",
    "CustomerNeedCollectionFilter",
    "InitiativeCollectionFilter",
    "ProjectUpdateCollectionFilter",
    "ProjectUpdatesCollectionFilter",
    "IssueLabelCollectionFilter",
    "ReactionCollectionFilter",
    "ReleaseCollectionFilter",
    "NullableUserFilter",
    "NullableTeamFilter",
    "NullableIssueFilter",
    "NullableProjectFilter",
    "NullableCycleFilter",
]

_AND = "Every filter in this list must match."
_OR = "At least one filter in this list must match."
_NULL_REL = "Filter based on the existence of the relation."
_LENGTH = "Comparator for the collection length."


class UserFilter(BaseModel):
    """A filter over users, or over a user-valued field such as ``assignee``.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by user UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by name.")
    display_name: Optional[StringComparator] = Field(
        None, description="Filter by display name."
    )
    email: Optional[StringComparator] = Field(None, description="Filter by email address.")
    active: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the user's account is active."
    )
    admin: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the user is an admin of the workspace."
    )
    is_me: Optional[BooleanComparator] = Field(
        None,
        description=(
            "Filter by whether the user is the authenticated user. This is how to "
            "say 'assigned to me' without resolving your own UUID first."
        ),
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the user was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the user was last updated."
    )
    app: Optional[BooleanComparator] = Field(
        None, description="Comparator for the user's app status."
    )
    owner: Optional[BooleanComparator] = Field(
        None, description="Comparator for the user's owner status."
    )
    invited: Optional[BooleanComparator] = Field(
        None, description="Comparator for the user's invited status."
    )
    is_invited: Optional[BooleanComparator] = Field(
        None, description="Comparator for the user's invited status."
    )
    assigned_issues: Optional[IssueCollectionFilter] = Field(
        None, description="Filters that the users assigned issues must satisfy."
    )
    and_: Optional[List[UserFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[UserFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class TeamFilter(BaseModel):
    """A filter over teams, or over an issue's ``team``.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by team UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by team name.")
    key: Optional[StringComparator] = Field(
        None, description="Filter by team key, e.g. 'ENG'."
    )
    description: Optional[NullableStringComparator] = Field(
        None, description="Filter by the team's description."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the team was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the team was last updated."
    )
    visibility: Optional[TeamVisibilityComparator] = Field(
        None, description="Comparator for the team visibility."
    )
    retired_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the time at which the team was retired."
    )
    parent: Optional[TeamFilter] = Field(
        None, description="Filters that the team's parent must satisfy."
    )
    ancestors: Optional[TeamCollectionFilter] = Field(
        None, description="Filters that the team's ancestors must satisfy."
    )
    members: Optional[UserCollectionFilter] = Field(
        None, description="Filters that the team's members must satisfy."
    )
    owners: Optional[UserCollectionFilter] = Field(
        None, description="Filters that the team's owners must satisfy."
    )
    issues: Optional[IssueCollectionFilter] = Field(
        None, description="Filters that the team's issues must satisfy."
    )
    release_pipelines: Optional[ReleasePipelineCollectionFilter] = Field(
        None, description="Filters that the team's release pipelines must satisfy."
    )
    and_: Optional[List[TeamFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[TeamFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class WorkflowStateFilter(BaseModel):
    """A filter over workflow states, or over an issue's ``state``.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by state UUID.")
    name: Optional[StringComparator] = Field(
        None, description="Filter by state name, e.g. 'In Progress'."
    )
    description: Optional[NullableStringComparator] = Field(
        None, description="Filter by the state's description."
    )
    type: Optional[StringComparator] = Field(
        None,
        description=(
            "Filter by state category: 'triage', 'backlog', 'unstarted', "
            "'started', 'completed', 'canceled' or 'duplicate'."
        ),
    )
    position: Optional[NumberComparator] = Field(
        None, description="Filter by the state's position in the team's workflow."
    )
    team: Optional[TeamFilter] = Field(
        None, description="Filter by the team the state belongs to."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the state was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the state was last updated."
    )
    issues: Optional[IssueCollectionFilter] = Field(
        None, description="Filters that the workflow states issues must satisfy."
    )
    and_: Optional[List[WorkflowStateFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[WorkflowStateFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class IssueLabelFilter(BaseModel):
    """A filter over labels.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by label UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by label name.")
    is_group: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the label is a group of other labels."
    )
    creator: Optional[NullableUserFilter] = Field(
        None, description="Filters that the issue labels creator must satisfy."
    )
    team: Optional[NullableTeamFilter] = Field(
        None,
        description=(
            "Filter by the team the label belongs to. Workspace-wide labels have "
            "no team."
        ),
    )
    parent: Optional[IssueLabelFilter] = Field(
        None, description="Filters that the issue label's parent label must satisfy."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the label was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the label was last updated."
    )
    and_: Optional[List[IssueLabelFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[IssueLabelFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class CycleFilter(BaseModel):
    """A filter over cycles, or over an issue's ``cycle``.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by cycle UUID.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the cycle name."
    )
    number: Optional[NumberComparator] = Field(
        None, description="Filter by the cycle's number."
    )
    starts_at: Optional[DateComparator] = Field(
        None, description="Filter by when the cycle starts."
    )
    ends_at: Optional[DateComparator] = Field(
        None, description="Filter by when the cycle ends."
    )
    completed_at: Optional[DateComparator] = Field(
        None, description="Comparator for the cycle completed at date."
    )
    is_active: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the cycle is the team's current one."
    )
    is_next: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the cycle is the team's next one."
    )
    is_previous: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the cycle is the team's previous one."
    )
    is_future: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the cycle is in the future."
    )
    is_past: Optional[BooleanComparator] = Field(
        None, description="Filter by whether the cycle is in the past."
    )
    team: Optional[TeamFilter] = Field(
        None, description="Filter by the team the cycle belongs to."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    inherited_from_id: Optional[IdComparator] = Field(
        None, description="Comparator for the inherited cycle ID."
    )
    is_in_cooldown: Optional[BooleanComparator] = Field(
        None,
        description="Comparator for filtering for whether the cycle is currently in cooldown.",
    )
    issues: Optional[IssueCollectionFilter] = Field(
        None, description="Filters that the cycles issues must satisfy."
    )
    and_: Optional[List[CycleFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[CycleFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class ProjectMilestoneFilter(BaseModel):
    """A filter over project milestones.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by milestone UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by name.")
    target_date: Optional[NullableDateComparator] = Field(
        None, description="Filter by the milestone's target date."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the milestone was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the milestone was last updated."
    )
    project: Optional[ProjectFilter] = Field(
        None, description="Filters that the project milestone's project must satisfy."
    )
    and_: Optional[List[ProjectMilestoneFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[ProjectMilestoneFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class ProjectFilter(BaseModel):
    """A filter over projects, or over an issue's ``project``.

    Linear's schema still has a ``roadmaps`` collection here; it is not
    modelled. Roadmaps are a deprecated domain, replaced by initiatives.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by project UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by project name.")
    slug_id: Optional[StringComparator] = Field(
        None, description="Filter by the project's slug."
    )
    priority: Optional[NullableNumberComparator] = Field(
        None, description="Filter by the project's priority."
    )
    health: Optional[StringComparator] = Field(
        None,
        description=(
            "Filter by the project's health: 'onTrack', 'atRisk' or 'offTrack'."
        ),
    )
    state: Optional[StringComparator] = Field(
        None,
        description=(
            "Filter by the project's state, such as 'planned', 'started', "
            "'completed' or 'canceled'."
        ),
    )
    start_date: Optional[NullableDateComparator] = Field(
        None, description="Filter by the project's start date."
    )
    target_date: Optional[NullableDateComparator] = Field(
        None, description="Filter by the project's target date."
    )
    completed_at: Optional[NullableDateComparator] = Field(
        None, description="Filter by when the project was completed."
    )
    canceled_at: Optional[NullableDateComparator] = Field(
        None, description="Filter by when the project was canceled."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the project was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the project was last updated."
    )
    lead: Optional[UserFilter] = Field(
        None, description="Filter by the project's lead."
    )
    creator: Optional[UserFilter] = Field(
        None, description="Filter by who created the project."
    )
    members: Optional[UserCollectionFilter] = Field(
        None, description="Filters that the project's members must satisfy."
    )
    started_at: Optional[NullableDateComparator] = Field(
        None,
        description=(
            "Comparator for the project started date (when it was moved to an "
            "\"In Progress\" status)."
        ),
    )
    activity_type: Optional[StringComparator] = Field(
        None,
        description="Comparator for the project activity type: buzzin, active, some, none.",
    )
    health_with_age: Optional[StringComparator] = Field(
        None,
        description=(
            "Comparator for the project health (with age): onTrack, atRisk, "
            "offTrack, outdated, noUpdate."
        ),
    )
    customer_count: Optional[NumberComparator] = Field(
        None, description="Count of customers."
    )
    customer_important_count: Optional[NumberComparator] = Field(
        None, description="Count of important customers."
    )
    has_blocked_by_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering projects which are blocked."
    )
    has_blocking_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering projects which are blocking."
    )
    has_related_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering projects with relations."
    )
    has_violated_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering projects with violated dependencies."
    )
    status: Optional[ProjectStatusFilter] = Field(
        None, description="Filters that the project status must satisfy."
    )
    lead_team: Optional[TeamFilter] = Field(
        None, description="Filters that the project's lead team must satisfy."
    )
    accessible_teams: Optional[TeamCollectionFilter] = Field(
        None, description="Filters that the project's team must satisfy."
    )
    last_applied_template: Optional[TemplateFilter] = Field(
        None, description="Filters that the last applied template must satisfy."
    )
    next_project_milestone: Optional[ProjectMilestoneFilter] = Field(
        None, description="Filters that the project's next milestone must satisfy."
    )
    project_milestones: Optional[ProjectMilestoneCollectionFilter] = Field(
        None, description="Filters that the project's milestones must satisfy."
    )
    completed_project_milestones: Optional[ProjectMilestoneCollectionFilter] = Field(
        None, description="Filters that the project's completed milestones must satisfy."
    )
    project_updates: Optional[ProjectUpdatesCollectionFilter] = Field(
        None, description="Filters that the project's updates must satisfy."
    )
    labels: Optional[ProjectLabelCollectionFilter] = Field(
        None, description="Filters that project labels must satisfy."
    )
    initiatives: Optional[InitiativeCollectionFilter] = Field(
        None, description="Filters that the projects initiatives must satisfy."
    )
    issues: Optional[IssueCollectionFilter] = Field(
        None, description="Filters that the projects issues must satisfy."
    )
    needs: Optional[CustomerNeedCollectionFilter] = Field(
        None, description="Filters that the project's customer needs must satisfy."
    )
    and_: Optional[List[ProjectFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[ProjectFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class IssueFilter(BaseModel):
    """A filter over issues. Conditions on the same object combine with AND.

    Every sendable field Linear's ``IssueFilter`` accepts is here, including
    SLA status, relation-existence flags, collection filters on comments and
    attachments, and boolean composition through ``and_``/``or_``.

    Fields Linear marks ``[Internal]`` — agent-session buckets, suggestion
    collections, derived timings, Prosemirror content — are absent. They
    cannot be used from a personal API key in the way this pack is built.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    number: Optional[NumberComparator] = Field(
        None, description="Comparator for the issues number."
    )
    title: Optional[StringComparator] = Field(
        None, description="Comparator for the issues title."
    )
    description: Optional[NullableStringComparator] = Field(
        None, description="Filter by issue description."
    )
    priority: Optional[NullableNumberComparator] = Field(
        None,
        description=(
            "Comparator for the issues priority. 0 = No priority, 1 = Urgent, "
            "2 = High, 3 = Medium, 4 = Low."
        ),
    )
    estimate: Optional[EstimateComparator] = Field(
        None, description="Filter by the issue's estimate."
    )
    due_date: Optional[NullableTimelessDateComparator] = Field(
        None, description="Filter by the issue's due date."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the issue was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the issue was last updated."
    )
    started_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues started at date."
    )
    completed_at: Optional[NullableDateComparator] = Field(
        None, description="Filter by when the issue was completed."
    )
    canceled_at: Optional[NullableDateComparator] = Field(
        None, description="Filter by when the issue was canceled."
    )
    triaged_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues triaged at date."
    )
    archived_at: Optional[NullableDateComparator] = Field(
        None, description="Filter by when the issue was archived."
    )
    snoozed_until_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues snoozed until date."
    )
    added_to_cycle_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues added to cycle at date."
    )
    added_to_cycle_period: Optional[CyclePeriodComparator] = Field(
        None, description="Comparator for the period when issue was added to a cycle."
    )
    auto_archived_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues auto archived at date."
    )
    auto_closed_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issues auto closed at date."
    )
    sla_breaches_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the issue's SLA breach date."
    )
    sla_status: Optional[SlaStatusComparator] = Field(
        None, description="Comparator for the issues sla status."
    )
    customer_count: Optional[NumberComparator] = Field(
        None, description="Count of customers."
    )
    customer_important_count: Optional[NumberComparator] = Field(
        None, description="Count of important customers."
    )
    state: Optional[WorkflowStateFilter] = Field(
        None, description="Filters that the issues state must satisfy."
    )
    assignee: Optional[NullableUserFilter] = Field(
        None, description="Filter by the issue's assignee."
    )
    creator: Optional[NullableUserFilter] = Field(
        None, description="Filter by who created the issue."
    )
    delegate: Optional[NullableUserFilter] = Field(
        None, description="Filter by the agent the issue is delegated to."
    )
    snoozed_by: Optional[NullableUserFilter] = Field(
        None, description="Filters that the issues snoozer must satisfy."
    )
    subscribers: Optional[UserCollectionFilter] = Field(
        None, description="Filters that issue subscribers must satisfy."
    )
    shared_with: Optional[UserCollectionFilter] = Field(
        None,
        description="Filters that users the issue has been shared with must satisfy.",
    )
    team: Optional[TeamFilter] = Field(
        None, description="Filters that the issues team must satisfy."
    )
    labels: Optional[IssueLabelCollectionFilter] = Field(
        None, description="Filters that issue labels must satisfy."
    )
    project: Optional[NullableProjectFilter] = Field(
        None, description="Filters that the issues project must satisfy."
    )
    project_milestone: Optional[NullableProjectMilestoneFilter] = Field(
        None, description="Filters that the issues project milestone must satisfy."
    )
    cycle: Optional[NullableCycleFilter] = Field(
        None, description="Filters that the issues cycle must satisfy."
    )
    parent: Optional[NullableIssueFilter] = Field(
        None, description="Filters that the issue parent must satisfy."
    )
    children: Optional[IssueCollectionFilter] = Field(
        None, description="Filter by the issue's sub-issues."
    )
    comments: Optional[CommentCollectionFilter] = Field(
        None, description="Filters that the issues comments must satisfy."
    )
    attachments: Optional[AttachmentCollectionFilter] = Field(
        None, description="Filters that the issues attachments must satisfy."
    )
    reactions: Optional[ReactionCollectionFilter] = Field(
        None, description="Filters that the issues reactions must satisfy."
    )
    activity: Optional[ActivityCollectionFilter] = Field(
        None, description="Filters that the issue's activities must satisfy."
    )
    needs: Optional[CustomerNeedCollectionFilter] = Field(
        None, description="Filters that the issue's customer needs must satisfy."
    )
    releases: Optional[ReleaseCollectionFilter] = Field(
        None, description="Filters that the issue's releases must satisfy."
    )
    last_applied_template: Optional[NullableTemplateFilter] = Field(
        None, description="Filters that the last applied template must satisfy."
    )
    recurring_issue_template: Optional[NullableTemplateFilter] = Field(
        None, description="[ALPHA] Filters that the recurring issue template must satisfy."
    )
    source_metadata: Optional[SourceMetadataComparator] = Field(
        None, description="Filters that the source must satisfy."
    )
    has_blocked_by_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering issues which are blocked."
    )
    has_blocking_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering issues which are blocking."
    )
    has_duplicate_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering issues which are duplicates."
    )
    has_related_relations: Optional[RelationExistsComparator] = Field(
        None, description="Comparator for filtering issues with relations."
    )
    has_shared_users: Optional[RelationExistsComparator] = Field(
        None,
        description=(
            "Comparator for filtering issues which have been shared with users "
            "outside of the team."
        ),
    )
    and_: Optional[List[IssueFilter]] = Field(None, description=_AND)
    or_: Optional[List[IssueFilter]] = Field(None, description=_OR)


class CommentFilter(BaseModel):
    """A filter over comments. Conditions combine with AND.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by comment UUID.")
    body: Optional[StringComparator] = Field(
        None, description="Match on the comment's text."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the comment was posted."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the comment was last edited."
    )
    user: Optional[UserFilter] = Field(
        None, description="Filter by who wrote the comment."
    )
    issue: Optional[NullableIssueFilter] = Field(
        None,
        description=(
            "Filter by the issue the comment is on. To read one issue's thread, "
            "use `issue.id.eq` with the issue's UUID."
        ),
    )
    project: Optional[NullableProjectFilter] = Field(
        None, description="Filter by the project the comment is on."
    )
    parent: Optional[NullableCommentFilter] = Field(
        None, description="Filters that the comment parent must satisfy."
    )
    project_update: Optional[NullableProjectUpdateFilter] = Field(
        None, description="Filters that the comment's project update must satisfy."
    )
    initiative_update: Optional[NullableInitiativeUpdateFilter] = Field(
        None, description="Filters that the comment's initiative update must satisfy."
    )
    document_content: Optional[NullableDocumentContentFilter] = Field(
        None, description="Filters that the comment's document content must satisfy."
    )
    reactions: Optional[ReactionCollectionFilter] = Field(
        None, description="Filters that the comment's reactions must satisfy."
    )
    needs: Optional[CustomerNeedCollectionFilter] = Field(
        None, description="Filters that the comment's customer needs must satisfy."
    )
    and_: Optional[List[CommentFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[CommentFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class InitiativeFilter(BaseModel):
    """A filter over initiatives.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by initiative UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by name.")
    status: Optional[StringComparator] = Field(
        None,
        description=(
            "Filter by status: 'Planned', 'Proposed', 'Active', 'Completed' or "
            "'Canceled'."
        ),
    )
    creator: Optional[UserFilter] = Field(
        None, description="Filter by who created the initiative."
    )
    owner: Optional[UserFilter] = Field(
        None, description="Filter by the initiative's owner."
    )
    target_date: Optional[NullableDateComparator] = Field(
        None, description="Filter by the initiative's target date."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the initiative was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the initiative was last updated."
    )
    slug_id: Optional[StringComparator] = Field(
        None, description="Comparator for the initiative's slug."
    )
    custom_identifier: Optional[NullableStringComparator] = Field(
        None, description="Comparator for the initiative's custom identifier."
    )
    priority: Optional[NullableNumberComparator] = Field(
        None, description="Comparator for the initiative's priority."
    )
    health: Optional[StringComparator] = Field(
        None, description="Comparator for the initiative's health."
    )
    health_with_age: Optional[StringComparator] = Field(
        None, description="Comparator for the initiative's health, with age."
    )
    activity_type: Optional[StringComparator] = Field(
        None, description="Comparator for the initiative's activity type."
    )
    started_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the initiative's started date."
    )
    completed_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the initiative's completed date."
    )
    canceled_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the initiative's canceled date."
    )
    lead_team: Optional[TeamFilter] = Field(
        None, description="Filters that the initiative's lead team must satisfy."
    )
    ancestors: Optional[InitiativeCollectionFilter] = Field(
        None, description="Filters that the initiative's ancestors must satisfy."
    )
    teams: Optional[TeamCollectionFilter] = Field(
        None, description="Filters that the initiative's teams must satisfy."
    )
    labels: Optional[InitiativeLabelCollectionFilter] = Field(
        None, description="Filters that the initiative labels must satisfy."
    )
    initiative_updates: Optional[InitiativeUpdatesCollectionFilter] = Field(
        None, description="Filters that the initiative updates must satisfy."
    )
    and_: Optional[List[InitiativeFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[InitiativeFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class DocumentFilter(BaseModel):
    """A filter over documents.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by document UUID.")
    title: Optional[StringComparator] = Field(None, description="Filter by title.")
    slug_id: Optional[StringComparator] = Field(
        None, description="Filter by the document's slug."
    )
    creator: Optional[UserFilter] = Field(
        None, description="Filter by who created the document."
    )
    project: Optional[ProjectFilter] = Field(
        None, description="Filter by the project the document belongs to."
    )
    initiative: Optional[InitiativeFilter] = Field(
        None, description="Filter by the initiative the document belongs to."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the document was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the document was last updated."
    )
    cycle: Optional[CycleFilter] = Field(
        None, description="Filters that the document's cycle must satisfy."
    )
    issue: Optional[IssueFilter] = Field(
        None, description="Filters that the document's issue must satisfy."
    )
    team: Optional[TeamFilter] = Field(
        None, description="Filters that the document's team must satisfy."
    )
    owner: Optional[UserFilter] = Field(
        None, description="Filters that the document's owner must satisfy."
    )
    searchable_content: Optional[ContentComparator] = Field(
        None, description="Comparator for the document's searchable content."
    )
    release: Optional[ReleaseFilter] = Field(
        None, description="Filters that the document's release must satisfy."
    )
    and_: Optional[List[DocumentFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[DocumentFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class AttachmentFilter(BaseModel):
    """A filter over attachments.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Filter by attachment UUID.")
    title: Optional[StringComparator] = Field(None, description="Filter by title.")
    subtitle: Optional[NullableStringComparator] = Field(
        None, description="Filter by subtitle."
    )
    url: Optional[StringComparator] = Field(
        None, description="Filter by the attachment's URL."
    )
    source_type: Optional[StringComparator] = Field(
        None,
        description=(
            "Filter by which integration created the attachment, e.g. 'github' "
            "or 'slack'."
        ),
    )
    creator: Optional[UserFilter] = Field(
        None, description="Filter by who created the attachment."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the attachment was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the attachment was last updated."
    )
    and_: Optional[List[AttachmentFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[AttachmentFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class CustomerFilter(BaseModel):
    """A filter over customers.

    API Reference: https://linear.app/developers/managing-customers
    """

    id: Optional[IdComparator] = Field(None, description="Filter by customer UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by name.")
    domains: Optional[StringComparator] = Field(
        None, description="Filter by one of the customer's domains."
    )
    external_ids: Optional[StringComparator] = Field(
        None, description="Filter by an external id the customer was synced with."
    )
    revenue: Optional[NullableNumberComparator] = Field(
        None, description="Filter by the customer's recorded revenue."
    )
    size: Optional[NullableNumberComparator] = Field(
        None, description="Filter by the customer's recorded size."
    )
    owner: Optional[UserFilter] = Field(
        None, description="Filter by the customer's owner."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the customer was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the customer was last updated."
    )
    slack_channel_id: Optional[NullableStringComparator] = Field(
        None, description="Comparator for the customer's linked Slack channel."
    )
    status: Optional[CustomerStatusFilter] = Field(
        None, description="Filters that the customer's status must satisfy."
    )
    tier: Optional[CustomerTierFilter] = Field(
        None, description="Filters that the customer's tier must satisfy."
    )
    needs: Optional[CustomerNeedCollectionFilter] = Field(
        None, description="Filters that the customer's requests must satisfy."
    )
    and_: Optional[List[CustomerFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[CustomerFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class CustomerNeedFilter(BaseModel):
    """A filter over customer requests.

    API Reference: https://linear.app/developers/managing-customers
    """

    id: Optional[IdComparator] = Field(None, description="Filter by request UUID.")
    priority: Optional[NumberComparator] = Field(
        None, description="Filter by the request's priority."
    )
    customer: Optional[CustomerFilter] = Field(
        None, description="Filter by the customer who made the request."
    )
    issue: Optional[IssueFilter] = Field(
        None, description="Filter by the issue the request is attached to."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the request was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the request was last updated."
    )
    project: Optional[ProjectFilter] = Field(
        None, description="Filters that the request's project must satisfy."
    )
    comment: Optional[CommentFilter] = Field(
        None, description="Filters that the request's comment must satisfy."
    )
    and_: Optional[List[CustomerNeedFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[CustomerNeedFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class TemplateFilter(BaseModel):
    """A filter over templates.

    API Reference: https://linear.app/developers/graphql
    """

    id: Optional[IdComparator] = Field(None, description="Filter by template UUID.")
    name: Optional[StringComparator] = Field(None, description="Filter by name.")
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the template was created."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the template was last updated."
    )
    type: Optional[StringComparator] = Field(
        None, description="Comparator for the template's type."
    )
    team: Optional[NullableTeamFilter] = Field(
        None, description="Filters that the template's team must satisfy."
    )
    inherited_from_id: Optional[IdComparator] = Field(
        None, description="Comparator for the inherited template's ID."
    )
    and_: Optional[List[TemplateFilter]] = Field(
        None, description="Every filter in this list must match."
    )
    or_: Optional[List[TemplateFilter]] = Field(
        None, description="At least one filter in this list must match."
    )


class ProjectUpdateFilter(BaseModel):
    """A filter over project status updates.

    API Reference: https://linear.app/developers/graphql
    """

    id: Optional[IdComparator] = Field(None, description="Filter by update UUID.")
    user: Optional[UserFilter] = Field(
        None, description="Filter by who posted the update."
    )
    project: Optional[ProjectFilter] = Field(
        None, description="Filter by the project the update belongs to."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Filter by when the update was posted."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Filter by when the update was last edited."
    )
    reactions: Optional[ReactionCollectionFilter] = Field(
        None, description="Filters that the update's reactions must satisfy."
    )
    and_: Optional[List[ProjectUpdateFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectUpdateFilter]] = Field(None, description=_OR)


class ProjectStatusFilter(BaseModel):
    """A filter over project statuses.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the project status name."
    )
    description: Optional[StringComparator] = Field(
        None, description="Comparator for the project status description."
    )
    type: Optional[StringComparator] = Field(
        None, description="Comparator for the project status type."
    )
    position: Optional[NumberComparator] = Field(
        None, description="Comparator for the project status position."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    team: Optional[NullableTeamFilter] = Field(
        None,
        description=(
            "Filters that the project status's team must satisfy. Use `{ null: true }` "
            "to filter workspace-level statuses."
        ),
    )
    projects: Optional[ProjectCollectionFilter] = Field(
        None, description="Filters that the project status projects must satisfy."
    )
    and_: Optional[List[ProjectStatusFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectStatusFilter]] = Field(None, description=_OR)


class CustomerStatusFilter(BaseModel):
    """A filter over customer statuses.

    API Reference: https://linear.app/developers/managing-customers
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the customer status name."
    )
    description: Optional[StringComparator] = Field(
        None, description="Comparator for the customer status description."
    )
    color: Optional[StringComparator] = Field(
        None, description="Comparator for the customer status color."
    )
    type: Optional[StringComparator] = Field(
        None, description="Comparator for the customer status type."
    )
    position: Optional[NumberComparator] = Field(
        None, description="Comparator for the customer status position."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[CustomerStatusFilter]] = Field(None, description=_AND)
    or_: Optional[List[CustomerStatusFilter]] = Field(None, description=_OR)


class CustomerTierFilter(BaseModel):
    """A filter over customer tiers.

    API Reference: https://linear.app/developers/managing-customers
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    display_name: Optional[StringComparator] = Field(
        None, description="Comparator for the customer tier display name."
    )
    description: Optional[StringComparator] = Field(
        None, description="Comparator for the customer tier description."
    )
    color: Optional[StringComparator] = Field(
        None, description="Comparator for the customer tier color."
    )
    position: Optional[NumberComparator] = Field(
        None, description="Comparator for the customer tier position."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[CustomerTierFilter]] = Field(None, description=_AND)
    or_: Optional[List[CustomerTierFilter]] = Field(None, description=_OR)


class ReactionFilter(BaseModel):
    """A filter over reactions.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    emoji: Optional[StringComparator] = Field(
        None, description="Comparator for the reactions emoji."
    )
    custom_emoji_id: Optional[IdComparator] = Field(
        None, description="Comparator for the reactions custom emoji."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[ReactionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReactionFilter]] = Field(None, description=_OR)


class ActivityFilter(BaseModel):
    """A filter over an issue's activity entries.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    user: Optional[UserFilter] = Field(
        None, description="Filters that the activity's user must satisfy."
    )
    and_: Optional[List[ActivityFilter]] = Field(None, description=_AND)
    or_: Optional[List[ActivityFilter]] = Field(None, description=_OR)


class InitiativeLabelFilter(BaseModel):
    """A filter over initiative labels.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(None, description="Comparator for the name.")
    is_group: Optional[BooleanComparator] = Field(
        None, description="Comparator for whether the label is a group label."
    )
    creator: Optional[NullableUserFilter] = Field(
        None, description="Filters that the initiative labels creator must satisfy."
    )
    parent: Optional[InitiativeLabelFilter] = Field(
        None, description="Filters that the initiative label's parent label must satisfy."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[InitiativeLabelFilter]] = Field(None, description=_AND)
    or_: Optional[List[InitiativeLabelFilter]] = Field(None, description=_OR)


class InitiativeUpdatesFilter(BaseModel):
    """A filter over initiative status updates as a collection.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[InitiativeUpdatesFilter]] = Field(None, description=_AND)
    or_: Optional[List[InitiativeUpdatesFilter]] = Field(None, description=_OR)


class ProjectLabelFilter(BaseModel):
    """A filter over project labels.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(None, description="Comparator for the name.")
    is_group: Optional[BooleanComparator] = Field(
        None, description="Comparator for whether the label is a group label."
    )
    creator: Optional[NullableUserFilter] = Field(
        None, description="Filters that the project labels creator must satisfy."
    )
    parent: Optional[ProjectLabelFilter] = Field(
        None, description="Filters that the project label's parent label must satisfy."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[ProjectLabelFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectLabelFilter]] = Field(None, description=_OR)


class ProjectUpdatesFilter(BaseModel):
    """A filter over a project's status-update collection.

    Distinct from :class:`ProjectUpdateFilter`, which filters one update.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    health: Optional[StringComparator] = Field(
        None, description="Comparator for the project update health."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[ProjectUpdatesFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectUpdatesFilter]] = Field(None, description=_OR)


class ReleaseStageFilter(BaseModel):
    """A filter over release stages.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the stage name."
    )
    type: Optional[ReleaseStageTypeComparator] = Field(
        None, description="Comparator for the stage type."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    and_: Optional[List[ReleaseStageFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReleaseStageFilter]] = Field(None, description=_OR)


class ReleasePipelineFilter(BaseModel):
    """A filter over release pipelines.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the pipeline name."
    )
    type: Optional[ReleasePipelineTypeComparator] = Field(
        None, description="Comparator for the pipeline type."
    )
    is_production: Optional[BooleanComparator] = Field(
        None, description="Comparator for the pipeline production flag."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    teams: Optional[TeamCollectionFilter] = Field(
        None, description="Filters that the release pipeline's teams must satisfy."
    )
    and_: Optional[List[ReleasePipelineFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReleasePipelineFilter]] = Field(None, description=_OR)


class ReleaseFilter(BaseModel):
    """A filter over releases.

    Modelled so issue and document filters can constrain by release. This pack
    does not ship release-pipeline tools; the filter is still sendable on the
    operations that take it.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    name: Optional[StringComparator] = Field(
        None, description="Comparator for the release name."
    )
    version: Optional[StringComparator] = Field(
        None, description="Comparator for the release version."
    )
    completed_at: Optional[NullableDateComparator] = Field(
        None, description="Comparator for the release completion date."
    )
    has_release_notes: Optional[BooleanComparator] = Field(
        None,
        description=(
            "Comparator for whether the release is covered by any (non-archived) "
            "release note."
        ),
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    pipeline: Optional[ReleasePipelineFilter] = Field(
        None, description="Filters that the release's pipeline must satisfy."
    )
    stage: Optional[ReleaseStageFilter] = Field(
        None, description="Filters that the release's stage must satisfy."
    )
    and_: Optional[List[ReleaseFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReleaseFilter]] = Field(None, description=_OR)


class DocumentContentFilter(BaseModel):
    """A filter over document content a comment can hang off.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    content: Optional[NullableStringComparator] = Field(
        None, description="Comparator for the document content."
    )
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    document: Optional[DocumentFilter] = Field(
        None, description="Filters that the document content document must satisfy."
    )
    initiative: Optional[InitiativeFilter] = Field(
        None, description="Filters that the document content initiative must satisfy."
    )
    issue: Optional[IssueFilter] = Field(
        None, description="Filters that the document content issue must satisfy."
    )
    project: Optional[ProjectFilter] = Field(
        None, description="Filters that the document content project must satisfy."
    )
    project_milestone: Optional[ProjectMilestoneFilter] = Field(
        None,
        description="Filters that the document content project milestone must satisfy.",
    )
    and_: Optional[List[DocumentContentFilter]] = Field(None, description=_AND)
    or_: Optional[List[DocumentContentFilter]] = Field(None, description=_OR)


class FeedItemFilter(BaseModel):
    """A filter over feed items, used by saved views.

    API Reference: https://linear.app/developers/filtering
    """

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    author: Optional[UserFilter] = Field(
        None, description="Filters that the feed item author must satisfy."
    )
    project_update: Optional[ProjectUpdateFilter] = Field(
        None, description="Filters that the feed item's project update must satisfy."
    )
    related_initiatives: Optional[InitiativeCollectionFilter] = Field(
        None, description="Filters that the related feed item initiatives must satisfy."
    )
    related_teams: Optional[TeamCollectionFilter] = Field(
        None, description="Filters that the related feed item team must satisfy."
    )
    update_health: Optional[StringComparator] = Field(
        None,
        description=(
            "Comparator for the project or initiative update health: onTrack, "
            "atRisk, offTrack."
        ),
    )
    update_type: Optional[StringComparator] = Field(
        None, description="Comparator for the update type: initiative, project, team."
    )
    and_: Optional[List[FeedItemFilter]] = Field(None, description=_AND)
    or_: Optional[List[FeedItemFilter]] = Field(None, description=_OR)


# Collection filters are the corresponding Filter plus some/every/length.
# and_/or_ take the collection type, so collection operators survive nesting.
# Linear's wording is kept: "Filters that needs to be matched by some X."


class UserCollectionFilter(UserFilter):
    """UserFilter plus collection operators."""

    some: Optional[UserFilter] = Field(
        None, description="Filters that needs to be matched by some users."
    )
    every: Optional[UserFilter] = Field(
        None, description="Filters that needs to be matched by all users."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[UserCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[UserCollectionFilter]] = Field(None, description=_OR)


class TeamCollectionFilter(TeamFilter):
    """TeamFilter plus collection operators."""

    some: Optional[TeamFilter] = Field(
        None, description="Filters that needs to be matched by some teams."
    )
    every: Optional[TeamFilter] = Field(
        None, description="Filters that needs to be matched by all teams."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[TeamCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[TeamCollectionFilter]] = Field(None, description=_OR)


class IssueCollectionFilter(IssueFilter):
    """IssueFilter plus collection operators."""

    some: Optional[IssueFilter] = Field(
        None, description="Filters that needs to be matched by some issues."
    )
    every: Optional[IssueFilter] = Field(
        None, description="Filters that needs to be matched by all issues."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[IssueCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[IssueCollectionFilter]] = Field(None, description=_OR)


class ProjectCollectionFilter(ProjectFilter):
    """ProjectFilter plus collection operators."""

    some: Optional[ProjectFilter] = Field(
        None, description="Filters that needs to be matched by some projects."
    )
    every: Optional[ProjectFilter] = Field(
        None, description="Filters that needs to be matched by all projects."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ProjectCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectCollectionFilter]] = Field(None, description=_OR)


class ProjectMilestoneCollectionFilter(ProjectMilestoneFilter):
    """ProjectMilestoneFilter plus collection operators."""

    some: Optional[ProjectMilestoneFilter] = Field(
        None, description="Filters that needs to be matched by some milestones."
    )
    every: Optional[ProjectMilestoneFilter] = Field(
        None, description="Filters that needs to be matched by all milestones."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ProjectMilestoneCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectMilestoneCollectionFilter]] = Field(None, description=_OR)


class CommentCollectionFilter(CommentFilter):
    """CommentFilter plus collection operators."""

    some: Optional[CommentFilter] = Field(
        None, description="Filters that needs to be matched by some comments."
    )
    every: Optional[CommentFilter] = Field(
        None, description="Filters that needs to be matched by all comments."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[CommentCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[CommentCollectionFilter]] = Field(None, description=_OR)


class AttachmentCollectionFilter(AttachmentFilter):
    """AttachmentFilter plus collection operators."""

    some: Optional[AttachmentFilter] = Field(
        None, description="Filters that needs to be matched by some attachments."
    )
    every: Optional[AttachmentFilter] = Field(
        None, description="Filters that needs to be matched by all attachments."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[AttachmentCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[AttachmentCollectionFilter]] = Field(None, description=_OR)


class CustomerNeedCollectionFilter(CustomerNeedFilter):
    """CustomerNeedFilter plus collection operators."""

    some: Optional[CustomerNeedFilter] = Field(
        None, description="Filters that needs to be matched by some customer needs."
    )
    every: Optional[CustomerNeedFilter] = Field(
        None, description="Filters that needs to be matched by all customer needs."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[CustomerNeedCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[CustomerNeedCollectionFilter]] = Field(None, description=_OR)


class InitiativeCollectionFilter(InitiativeFilter):
    """InitiativeFilter plus collection operators."""

    some: Optional[InitiativeFilter] = Field(
        None, description="Filters that needs to be matched by some initiatives."
    )
    every: Optional[InitiativeFilter] = Field(
        None, description="Filters that needs to be matched by all initiatives."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[InitiativeCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[InitiativeCollectionFilter]] = Field(None, description=_OR)


class ProjectUpdateCollectionFilter(ProjectUpdateFilter):
    """ProjectUpdateFilter plus collection operators."""

    some: Optional[ProjectUpdateFilter] = Field(
        None, description="Filters that needs to be matched by some updates."
    )
    every: Optional[ProjectUpdateFilter] = Field(
        None, description="Filters that needs to be matched by all updates."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ProjectUpdateCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectUpdateCollectionFilter]] = Field(None, description=_OR)


class ProjectUpdatesCollectionFilter(ProjectUpdatesFilter):
    """ProjectUpdatesFilter plus collection operators."""

    some: Optional[ProjectUpdatesFilter] = Field(
        None, description="Filters that needs to be matched by some updates."
    )
    every: Optional[ProjectUpdatesFilter] = Field(
        None, description="Filters that needs to be matched by all updates."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ProjectUpdatesCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectUpdatesCollectionFilter]] = Field(None, description=_OR)


class IssueLabelCollectionFilter(IssueLabelFilter):
    """IssueLabelFilter plus collection operators."""

    some: Optional[IssueLabelFilter] = Field(
        None, description="Filters that needs to be matched by some issue labels."
    )
    every: Optional[IssueLabelFilter] = Field(
        None, description="Filters that needs to be matched by all issue labels."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[IssueLabelCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[IssueLabelCollectionFilter]] = Field(None, description=_OR)


class ReactionCollectionFilter(ReactionFilter):
    """ReactionFilter plus collection operators."""

    some: Optional[ReactionFilter] = Field(
        None, description="Filters that needs to be matched by some reactions."
    )
    every: Optional[ReactionFilter] = Field(
        None, description="Filters that needs to be matched by all reactions."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ReactionCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReactionCollectionFilter]] = Field(None, description=_OR)


class ReleaseCollectionFilter(ReleaseFilter):
    """ReleaseFilter plus collection operators."""

    some: Optional[ReleaseFilter] = Field(
        None, description="Filters that needs to be matched by some releases."
    )
    every: Optional[ReleaseFilter] = Field(
        None, description="Filters that needs to be matched by all releases."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ReleaseCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReleaseCollectionFilter]] = Field(None, description=_OR)


class ReleasePipelineCollectionFilter(ReleasePipelineFilter):
    """ReleasePipelineFilter plus collection operators."""

    some: Optional[ReleasePipelineFilter] = Field(
        None, description="Filters that needs to be matched by some release pipelines."
    )
    every: Optional[ReleasePipelineFilter] = Field(
        None, description="Filters that needs to be matched by all release pipelines."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ReleasePipelineCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ReleasePipelineCollectionFilter]] = Field(None, description=_OR)


class InitiativeLabelCollectionFilter(InitiativeLabelFilter):
    """InitiativeLabelFilter plus collection operators."""

    some: Optional[InitiativeLabelCollectionFilter] = Field(
        None, description="Filters that needs to be matched by some initiative labels."
    )
    every: Optional[InitiativeLabelFilter] = Field(
        None, description="Filters that needs to be matched by all initiative labels."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[InitiativeLabelCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[InitiativeLabelCollectionFilter]] = Field(None, description=_OR)


class InitiativeUpdatesCollectionFilter(InitiativeUpdatesFilter):
    """InitiativeUpdatesFilter plus collection operators."""

    some: Optional[InitiativeUpdatesFilter] = Field(
        None, description="Filters that needs to be matched by some initiative updates."
    )
    every: Optional[InitiativeUpdatesFilter] = Field(
        None, description="Filters that needs to be matched by all initiative updates."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[InitiativeUpdatesCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[InitiativeUpdatesCollectionFilter]] = Field(None, description=_OR)


class ProjectLabelCollectionFilter(ProjectLabelFilter):
    """ProjectLabelFilter plus collection operators."""

    some: Optional[ProjectLabelCollectionFilter] = Field(
        None, description="Filters that needs to be matched by some project labels."
    )
    every: Optional[ProjectLabelFilter] = Field(
        None, description="Filters that needs to be matched by all project labels."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[ProjectLabelCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ProjectLabelCollectionFilter]] = Field(None, description=_OR)


class ActivityCollectionFilter(ActivityFilter):
    """ActivityFilter plus collection operators."""

    some: Optional[ActivityFilter] = Field(
        None, description="Filters that needs to be matched by some activities."
    )
    every: Optional[ActivityFilter] = Field(
        None, description="Filters that needs to be matched by all activities."
    )
    length: Optional[NumberComparator] = Field(None, description=_LENGTH)
    and_: Optional[List[ActivityCollectionFilter]] = Field(None, description=_AND)
    or_: Optional[List[ActivityCollectionFilter]] = Field(None, description=_OR)


# Nullable wrappers add `null` so a relation can be matched as unset.


class NullableUserFilter(UserFilter):
    """UserFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableUserFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableUserFilter]] = Field(None, description=_OR)


class NullableTeamFilter(TeamFilter):
    """TeamFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableTeamFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableTeamFilter]] = Field(None, description=_OR)


class NullableIssueFilter(IssueFilter):
    """IssueFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableIssueFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableIssueFilter]] = Field(None, description=_OR)


class NullableProjectFilter(ProjectFilter):
    """ProjectFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableProjectFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableProjectFilter]] = Field(None, description=_OR)


class NullableCycleFilter(CycleFilter):
    """CycleFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableCycleFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableCycleFilter]] = Field(None, description=_OR)


class NullableProjectMilestoneFilter(ProjectMilestoneFilter):
    """ProjectMilestoneFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableProjectMilestoneFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableProjectMilestoneFilter]] = Field(None, description=_OR)


class NullableTemplateFilter(TemplateFilter):
    """TemplateFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableTemplateFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableTemplateFilter]] = Field(None, description=_OR)


class NullableCommentFilter(CommentFilter):
    """CommentFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableCommentFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableCommentFilter]] = Field(None, description=_OR)


class NullableProjectUpdateFilter(ProjectUpdateFilter):
    """ProjectUpdateFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableProjectUpdateFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableProjectUpdateFilter]] = Field(None, description=_OR)


class NullableInitiativeUpdateFilter(BaseModel):
    """A filter over initiative status updates that may be unset."""

    id: Optional[IdComparator] = Field(None, description="Comparator for the identifier.")
    created_at: Optional[DateComparator] = Field(
        None, description="Comparator for the created at date."
    )
    updated_at: Optional[DateComparator] = Field(
        None, description="Comparator for the updated at date."
    )
    initiative: Optional[InitiativeFilter] = Field(
        None, description="Filters that the initiative update initiative must satisfy."
    )
    user: Optional[UserFilter] = Field(
        None, description="Filters that the initiative update creator must satisfy."
    )
    reactions: Optional[ReactionCollectionFilter] = Field(
        None, description="Filters that the initiative updates reactions must satisfy."
    )
    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableInitiativeUpdateFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableInitiativeUpdateFilter]] = Field(None, description=_OR)


class NullableDocumentContentFilter(DocumentContentFilter):
    """DocumentContentFilter that can also match an unset relation."""

    null: Optional[bool] = Field(None, description=_NULL_REL)
    and_: Optional[List[NullableDocumentContentFilter]] = Field(None, description=_AND)
    or_: Optional[List[NullableDocumentContentFilter]] = Field(None, description=_OR)


# The filters above reference themselves and each other, so the forward
# references are resolved once, here, after every class exists.
for _model in (
    UserFilter,
    TeamFilter,
    WorkflowStateFilter,
    IssueLabelFilter,
    CycleFilter,
    ProjectMilestoneFilter,
    ProjectFilter,
    IssueFilter,
    CommentFilter,
    InitiativeFilter,
    DocumentFilter,
    AttachmentFilter,
    CustomerFilter,
    CustomerNeedFilter,
    TemplateFilter,
    ProjectUpdateFilter,
    ProjectStatusFilter,
    CustomerStatusFilter,
    CustomerTierFilter,
    ReactionFilter,
    ActivityFilter,
    InitiativeLabelFilter,
    InitiativeUpdatesFilter,
    ProjectLabelFilter,
    ProjectUpdatesFilter,
    ReleaseStageFilter,
    ReleasePipelineFilter,
    ReleaseFilter,
    DocumentContentFilter,
    FeedItemFilter,
    UserCollectionFilter,
    TeamCollectionFilter,
    IssueCollectionFilter,
    ProjectCollectionFilter,
    ProjectMilestoneCollectionFilter,
    CommentCollectionFilter,
    AttachmentCollectionFilter,
    CustomerNeedCollectionFilter,
    InitiativeCollectionFilter,
    ProjectUpdateCollectionFilter,
    ProjectUpdatesCollectionFilter,
    IssueLabelCollectionFilter,
    ReactionCollectionFilter,
    ReleaseCollectionFilter,
    ReleasePipelineCollectionFilter,
    InitiativeLabelCollectionFilter,
    InitiativeUpdatesCollectionFilter,
    ProjectLabelCollectionFilter,
    ActivityCollectionFilter,
    NullableUserFilter,
    NullableTeamFilter,
    NullableIssueFilter,
    NullableProjectFilter,
    NullableCycleFilter,
    NullableProjectMilestoneFilter,
    NullableTemplateFilter,
    NullableCommentFilter,
    NullableProjectUpdateFilter,
    NullableInitiativeUpdateFilter,
    NullableDocumentContentFilter,
):
    _model.model_rebuild()
