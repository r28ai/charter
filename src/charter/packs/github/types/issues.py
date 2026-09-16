"""Request schemas for GitHub's issues endpoints.

API Reference: https://docs.github.com/en/rest/issues/issues
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from charter.packs.github.types.common import GitHubListRequest, RepoRequest, SortDirection
from charter.types import Body, Path, Query

__all__ = [
    "IssuesListForRepoRequest",
    "IssuesGetRequest",
    "IssuesCreateRequest",
    "IssuesUpdateRequest",
    "IssuesCreateCommentRequest",
    "IssuesListCommentsRequest",
    "IssueState",
    "IssueSort",
    "StateReason",
    "MilestoneState",
    "MilestoneSort",
    "LockReason",
    "IssueFilter",
    "IssuesListLabelsForRepoRequest",
    "IssuesAddLabelsRequest",
    "IssuesSetLabelsRequest",
    "IssuesRemoveLabelRequest",
    "IssuesCreateLabelRequest",
    "IssuesUpdateLabelRequest",
    "IssuesDeleteLabelRequest",
    "IssuesAddAssigneesRequest",
    "IssuesRemoveAssigneesRequest",
    "IssuesListMilestonesRequest",
    "IssuesCreateMilestoneRequest",
    "IssuesUpdateMilestoneRequest",
    "IssuesGetCommentRequest",
    "IssuesUpdateCommentRequest",
    "IssuesDeleteCommentRequest",
    "IssuesListTimelineRequest",
    "IssuesListEventsRequest",
    "IssuesLockRequest",
    "IssuesUnlockRequest",
    "IssuesListForAuthenticatedUserRequest",
    "IssuesListSubIssuesRequest",
    "IssuesAddSubIssueRequest",
]


IssueState = Literal["open", "closed", "all"]
IssueSort = Literal["created", "updated", "comments"]
StateReason = Literal["completed", "not_planned", "duplicate", "reopened"]


class IssuesListForRepoRequest(RepoRequest, GitHubListRequest):
    """List issues in a repository.

    Note: GitHub's REST API considers every pull request an issue, so this
    endpoint returns pull requests too. Each returned pull request carries a
    ``pull_request`` key; issues do not.

    API Reference: https://docs.github.com/en/rest/issues/issues#list-repository-issues
    """

    milestone: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "If an integer is passed, it should refer to a milestone by its number "
                "field. If the string `*` is passed, issues with any milestone are "
                "accepted. If the string `none` is passed, issues without milestones "
                "are returned."
            ),
        ),
        Query(),
    ]
    state: Annotated[
        Optional[IssueState],
        Field(
            "open",
            description=(
                "Indicates the state of the issues to return. Defaults to `open`."
            ),
        ),
        Query(),
    ]
    assignee: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Can be the name of a user. Pass in `none` for issues with no assigned "
                "user, and `*` for issues assigned to any user."
            ),
        ),
        Query(),
    ]
    creator: Annotated[
        Optional[str],
        Field(None, description="The user that created the issue."),
        Query(),
    ]
    mentioned: Annotated[
        Optional[str],
        Field(None, description="A user that's mentioned in the issue."),
        Query(),
    ]
    labels: Annotated[
        Optional[str],
        Field(
            None,
            description="A list of comma separated label names. Example: `bug,ui,@high`.",
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[IssueSort],
        Field("created", description="What to sort results by. Defaults to `created`."),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field("desc", description="The direction to sort the results by. Defaults to `desc`."),
        Query(),
    ]
    since: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show results that were last updated after the given time. This is "
                "a timestamp in ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]


class IssuesGetRequest(RepoRequest):
    """Get a single issue.

    API Reference: https://docs.github.com/en/rest/issues/issues#get-an-issue
    """

    issue_number: Annotated[
        int,
        Field(..., description="The number that identifies the issue."),
        Path(),
    ]


class IssueCreateBody(BaseModel):
    """The body of a create-issue request.

    API Reference: https://docs.github.com/en/rest/issues/issues#create-an-issue
    """

    title: str = Field(..., description="The title of the issue.")
    body: Optional[str] = Field(None, description="The contents of the issue.")
    milestone: Optional[Union[int, str]] = Field(
        None,
        description="The number of the milestone to associate this issue with.",
    )
    labels: Optional[List[str]] = Field(
        None,
        description="Labels to associate with this issue. Pass label names, not IDs.",
    )
    assignees: Optional[List[str]] = Field(
        None,
        description="Logins for Users to assign to this issue.",
    )


class IssuesCreateRequest(RepoRequest):
    """Create an issue.

    API Reference: https://docs.github.com/en/rest/issues/issues#create-an-issue
    """

    body: Annotated[
        IssueCreateBody,
        Field(..., description="The issue to create."),
        Body(),
    ]


class IssueUpdateBody(BaseModel):
    """The body of an update-issue request.

    Every field is optional; anything omitted is left unchanged. Note that
    ``labels`` and ``assignees`` *replace* the existing sets rather than adding
    to them.

    API Reference: https://docs.github.com/en/rest/issues/issues#update-an-issue
    """

    title: Optional[str] = Field(None, description="The title of the issue.")
    body: Optional[str] = Field(None, description="The contents of the issue.")
    state: Optional[Literal["open", "closed"]] = Field(
        None, description="The open or closed state of the issue."
    )
    state_reason: Optional[StateReason] = Field(
        None,
        description=(
            "The reason for the state change. Ignored unless `state` is changed."
        ),
    )
    milestone: Optional[Union[int, str]] = Field(
        None,
        description=(
            "The number of the milestone to associate this issue with. Set to null to "
            "remove the current milestone."
        ),
    )
    labels: Optional[List[str]] = Field(
        None,
        description=(
            "Labels to associate with this issue. Pass one or more label names to "
            "*replace* the set of labels on this issue."
        ),
    )
    assignees: Optional[List[str]] = Field(
        None,
        description=(
            "Usernames to assign to this issue. Pass one or more user logins to "
            "*replace* the set of assignees on this issue."
        ),
    )


class IssuesUpdateRequest(RepoRequest):
    """Update an issue.

    API Reference: https://docs.github.com/en/rest/issues/issues#update-an-issue
    """

    issue_number: Annotated[
        int,
        Field(..., description="The number that identifies the issue."),
        Path(),
    ]
    body: Annotated[
        IssueUpdateBody,
        Field(..., description="The fields to change."),
        Body(),
    ]


class CommentCreateBody(BaseModel):
    """The body of a create-comment request.

    API Reference: https://docs.github.com/en/rest/issues/comments#create-an-issue-comment
    """

    body: str = Field(..., description="The contents of the comment.")


class IssuesCreateCommentRequest(RepoRequest):
    """Comment on an issue or pull request.

    API Reference: https://docs.github.com/en/rest/issues/comments#create-an-issue-comment
    """

    issue_number: Annotated[
        int,
        Field(
            ...,
            description=(
                "The number that identifies the issue. A pull request number works "
                "here too — GitHub treats pull requests as issues for commenting."
            ),
        ),
        Path(),
    ]
    body: Annotated[
        CommentCreateBody,
        Field(..., description="The comment to post."),
        Body(),
    ]


class IssuesListCommentsRequest(RepoRequest, GitHubListRequest):
    """List comments on an issue or pull request.

    API Reference: https://docs.github.com/en/rest/issues/comments#list-issue-comments
    """

    issue_number: Annotated[
        int,
        Field(..., description="The number that identifies the issue."),
        Path(),
    ]
    since: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show results that were last updated after the given time, in ISO "
                "8601 format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]


# -----------------------------------------------------
# Labels
# -----------------------------------------------------

# GitHub caps a label description at 100 characters and rejects a longer one.
LABEL_DESCRIPTION_MAX = 100

# The colour is a bare hex triple: GitHub's own words are "without the leading
# `#`", and it answers 422 to one that carries it.
_HEX_COLOR = r"^[0-9a-fA-F]{6}$"


class _IssueNumber(RepoRequest):
    issue_number: Annotated[
        int,
        Field(..., description="The number that identifies the issue."),
        Path(),
    ]


class IssuesListLabelsForRepoRequest(RepoRequest, GitHubListRequest):
    """List the labels a repository defines.

    Worth calling before labelling anything: `issues_add_labels` takes names,
    and a name that does not exist yet is a 422.

    API Reference: https://docs.github.com/en/rest/issues/labels#list-labels-for-a-repository
    """


class IssuesAddLabelsRequest(_IssueNumber):
    """Add labels to an issue, keeping the ones already on it.

    The additive half of the pair. `issues_set_labels` replaces instead, and
    `issues_update` replaces too — which is the trap this tool exists to avoid,
    since adding one label through `issues_update` silently removes the rest.

    GitHub accepts a bare array here as well as the object, and recommends the
    object; that is the form this sends.

    API Reference: https://docs.github.com/en/rest/issues/labels#add-labels-to-an-issue
    """

    labels: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            description=(
                "The names of the labels to add to the issue's existing labels. Each "
                "must already exist on the repository."
            ),
        ),
        Body(envelop=True),
    ]


class IssuesSetLabelsRequest(_IssueNumber):
    """Replace an issue's labels with exactly this set.

    GitHub: "Removes any previous labels and sets the new labels for an issue."
    An empty list removes them all, which is the one way to say that.

    API Reference: https://docs.github.com/en/rest/issues/labels#set-labels-for-an-issue
    """

    labels: Annotated[
        List[str],
        Field(
            ...,
            description=(
                "The names of the labels to set for the issue. These replace any "
                "existing labels. Pass an empty array to remove all labels."
            ),
        ),
        Body(envelop=True),
    ]


class IssuesRemoveLabelRequest(_IssueNumber):
    """Take one label off an issue.

    API Reference: https://docs.github.com/en/rest/issues/labels#remove-a-label-from-an-issue
    """

    name: Annotated[
        str,
        Field(..., description="The name of the label to remove from the issue."),
        Path(allow_slash=True),
    ]


class IssuesCreateLabelRequest(RepoRequest):
    """Define a new label on the repository.

    API Reference: https://docs.github.com/en/rest/issues/labels#create-a-label
    """

    name: Annotated[
        str,
        Field(
            ...,
            description=(
                "The name of the label. Emoji can be added to label names, using either "
                "native emoji or colon-style markup, for example `:bug:`."
            ),
        ),
        Body(),
    ]
    color: Annotated[
        Optional[str],
        Field(
            None,
            pattern=_HEX_COLOR,
            description=(
                "The hexadecimal color code for the label, without the leading `#` — "
                "`d73a4a`, not `#d73a4a`."
            ),
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(
            None,
            max_length=LABEL_DESCRIPTION_MAX,
            description="A short description of the label. Must be 100 characters or fewer.",
        ),
        Body(),
    ]


class IssuesUpdateLabelRequest(RepoRequest):
    """Change a label's name, colour, description, or archived state.

    Renaming here renames it on every issue that carries it; there is no
    separate migration.

    API Reference: https://docs.github.com/en/rest/issues/labels#update-a-label
    """

    name: Annotated[
        str,
        Field(..., description="The current name of the label."),
        Path(allow_slash=True),
    ]
    new_name: Annotated[
        Optional[str],
        Field(None, description="The new name of the label."),
        Body(),
    ]
    color: Annotated[
        Optional[str],
        Field(
            None,
            pattern=_HEX_COLOR,
            description="The hexadecimal color code for the label, without the leading `#`.",
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(
            None,
            max_length=LABEL_DESCRIPTION_MAX,
            description="A short description of the label. Must be 100 characters or fewer.",
        ),
        Body(),
    ]
    archived: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to archive or unarchive the label. Archived labels cannot be "
                "added to issues or pull requests."
            ),
        ),
        Body(),
    ]


class IssuesDeleteLabelRequest(RepoRequest):
    """Delete a label, removing it from every issue that carries it.

    API Reference: https://docs.github.com/en/rest/issues/labels#delete-a-label
    """

    name: Annotated[
        str,
        Field(..., description="The name of the label to delete."),
        Path(allow_slash=True),
    ]


# -----------------------------------------------------
# Assignees
# -----------------------------------------------------

# GitHub's own ceiling: "Adds up to 10 assignees to an issue."
MAX_ASSIGNEES = 10


class IssuesAddAssigneesRequest(_IssueNumber):
    """Assign people to an issue, keeping whoever is already assigned.

    Two things GitHub does quietly here, both worth knowing before reading the
    result as success: assignees beyond ten are dropped, and "Only users with
    push access can add assignees to an issue. Assignees are silently ignored
    otherwise." The response carries the resulting assignee list — compare it
    with what you sent rather than assuming.

    API Reference: https://docs.github.com/en/rest/issues/assignees#add-assignees-to-an-issue
    """

    assignees: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            max_length=MAX_ASSIGNEES,
            description=(
                "Usernames of people to assign this issue to, at most ten. A user "
                "without push access to the repository is silently ignored."
            ),
        ),
        Body(envelop=True),
    ]


class IssuesRemoveAssigneesRequest(_IssueNumber):
    """Unassign people from an issue.

    API Reference: https://docs.github.com/en/rest/issues/assignees#remove-assignees-from-an-issue
    """

    assignees: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            description="Usernames of the people to unassign from this issue.",
        ),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# Milestones
# -----------------------------------------------------

MilestoneState = Literal["open", "closed", "all"]
MilestoneSort = Literal["due_on", "completeness"]


class IssuesListMilestonesRequest(RepoRequest, GitHubListRequest):
    """List a repository's milestones.

    API Reference: https://docs.github.com/en/rest/issues/milestones#list-milestones
    """

    state: Annotated[
        Optional[MilestoneState],
        Field(
            None,
            description=(
                "The state of the milestone. GitHub uses `open` when this is absent."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[MilestoneSort],
        Field(
            None,
            description=(
                "What to sort results by. GitHub uses `due_on` when this is absent; "
                "`completeness` sorts by how much of the milestone is closed."
            ),
        ),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(None, description="The direction of the sort. GitHub uses `asc` when this is absent."),
        Query(),
    ]


class IssuesCreateMilestoneRequest(RepoRequest):
    """Create a milestone.

    API Reference: https://docs.github.com/en/rest/issues/milestones#create-a-milestone
    """

    title: Annotated[str, Field(..., description="The title of the milestone."), Body()]
    state: Annotated[
        Optional[Literal["open", "closed"]],
        Field(None, description="The state of the milestone. GitHub uses `open` when this is absent."),
        Body(),
    ]
    description: Annotated[
        Optional[str], Field(None, description="A description of the milestone."), Body()
    ]
    due_on: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "The milestone due date. This is a timestamp in ISO 8601 format: "
                "`YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Body(),
    ]


class IssuesUpdateMilestoneRequest(RepoRequest):
    """Update a milestone. Anything omitted is left alone.

    API Reference: https://docs.github.com/en/rest/issues/milestones#update-a-milestone
    """

    milestone_number: Annotated[
        int,
        Field(..., description="The number that identifies the milestone."),
        Path(),
    ]
    title: Annotated[Optional[str], Field(None, description="The title of the milestone."), Body()]
    state: Annotated[
        Optional[Literal["open", "closed"]],
        Field(None, description="The state of the milestone."),
        Body(),
    ]
    description: Annotated[
        Optional[str], Field(None, description="A description of the milestone."), Body()
    ]
    due_on: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "The milestone due date. This is a timestamp in ISO 8601 format: "
                "`YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Body(),
    ]


# -----------------------------------------------------
# Editing what was said
# -----------------------------------------------------


class _IssueCommentId(RepoRequest):
    comment_id: Annotated[
        int,
        Field(
            ...,
            description=(
                "The unique identifier of the comment — its `id`, not the issue "
                "number it sits on."
            ),
        ),
        Path(),
    ]


class IssuesGetCommentRequest(_IssueCommentId):
    """Get one issue comment by its id.

    API Reference: https://docs.github.com/en/rest/issues/comments#get-an-issue-comment
    """


class IssuesUpdateCommentRequest(_IssueCommentId):
    """Edit an issue comment's text.

    API Reference: https://docs.github.com/en/rest/issues/comments#update-an-issue-comment
    """

    body: Annotated[str, Field(..., description="The contents of the comment."), Body()]


class IssuesDeleteCommentRequest(_IssueCommentId):
    """Delete an issue comment.

    API Reference: https://docs.github.com/en/rest/issues/comments#delete-an-issue-comment
    """


# -----------------------------------------------------
# History, locking, and the authenticated user's backlog
# -----------------------------------------------------


class IssuesListTimelineRequest(_IssueNumber, GitHubListRequest):
    """List everything that has happened to an issue, in order.

    Wider than `issues_list_events`: the timeline includes the comments, the
    cross-references from other issues, the commits that mentioned it and the
    reviews, alongside the label and assignment changes. It is how an agent
    reconstructs what has already been tried.

    An event's `event` field is not a closed set here. GitHub adds kinds
    without a schema change, so it is read as a string.

    API Reference: https://docs.github.com/en/rest/issues/timeline#list-timeline-events-for-an-issue
    """

    exclude: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of timeline event names to exclude from the "
                "response, such as `cross-referenced,mentioned`."
            ),
        ),
        Query(),
    ]


class IssuesListEventsRequest(_IssueNumber, GitHubListRequest):
    """List an issue's state changes: labelled, assigned, closed, renamed.

    The narrow sibling of the timeline, without the comments.

    API Reference: https://docs.github.com/en/rest/issues/events#list-issue-events
    """


LockReason = Literal["off-topic", "too heated", "resolved", "spam"]
"""Why a conversation is being locked.

GitHub is strict about this set — "Lock will fail if you don't use one of these
reasons" — and note that one of them contains a space."""


class IssuesLockRequest(_IssueNumber):
    """Lock an issue or pull request's conversation.

    Needs push access. `lock_reason` is optional, and the four values are the
    only ones accepted when it is given.

    API Reference: https://docs.github.com/en/rest/issues/issues#lock-an-issue
    """

    lock_reason: Annotated[
        Optional[LockReason],
        Field(
            None,
            description=(
                "The reason for locking the issue or pull request conversation. Locking "
                "fails if the reason is not one of these four."
            ),
        ),
        Body(),
    ]


class IssuesUnlockRequest(_IssueNumber):
    """Unlock a conversation.

    API Reference: https://docs.github.com/en/rest/issues/issues#unlock-an-issue
    """


IssueFilter = Literal["assigned", "created", "mentioned", "subscribed", "repos", "all"]
"""Which of the authenticated user's issues to return."""


class IssuesListForAuthenticatedUserRequest(GitHubListRequest):
    """List the authenticated user's issues, across every repository they see.

    The agent's own inbox: what is assigned to it, what it opened, what mentions
    it. Pull requests come back here too, marked `is_pull_request`.

    API Reference: https://docs.github.com/en/rest/issues/issues#list-issues-assigned-to-the-authenticated-user
    """

    filter: Annotated[
        Optional[IssueFilter],
        Field(
            None,
            description=(
                "Which sorts of issues to return. `assigned` means issues assigned to "
                "you. `created` means issues created by you. `mentioned` means issues "
                "mentioning you. `subscribed` means issues you're subscribed to updates "
                "for. `all` or `repos` means all issues you can see, regardless of "
                "participation or creation. GitHub uses `assigned` when this is absent."
            ),
        ),
        Query(),
    ]
    state: Annotated[
        Optional[IssueState],
        Field(
            None,
            description="Indicates the state of the issues to return. GitHub uses `open` when this is absent.",
        ),
        Query(),
    ]
    labels: Annotated[
        Optional[str],
        Field(None, description="A list of comma separated label names. Example: `bug,ui,@high`."),
        Query(),
    ]
    sort: Annotated[
        Optional[IssueSort],
        Field(None, description="What to sort results by. GitHub uses `created` when this is absent."),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(
            None,
            description="The direction to sort the results by. GitHub uses `desc` when this is absent.",
        ),
        Query(),
    ]
    since: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show results that were last updated after the given time, in ISO "
                "8601 format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]
    collab: Annotated[
        Optional[bool],
        Field(None, description="Include issues from repositories you are a collaborator on."),
        Query(),
    ]
    orgs: Annotated[
        Optional[bool],
        Field(None, description="Include issues from your organizations' repositories."),
        Query(),
    ]
    owned: Annotated[
        Optional[bool],
        Field(None, description="Include issues from repositories you own."),
        Query(),
    ]
    pulls: Annotated[
        Optional[bool],
        Field(None, description="Include pull requests alongside issues."),
        Query(),
    ]


class IssuesListSubIssuesRequest(_IssueNumber, GitHubListRequest):
    """List an issue's sub-issues.

    API Reference: https://docs.github.com/en/rest/issues/sub-issues#list-sub-issues
    """


class IssuesAddSubIssueRequest(_IssueNumber):
    """Attach an existing issue to this one as a sub-issue.

    `sub_issue_id` is the issue's **id**, not its number — the two are different
    and both are integers, which is how this goes wrong silently. The id comes
    back on every issue object; the number is what appears in the URL.

    GitHub requires the sub-issue to belong to the same repository owner as the
    parent.

    API Reference: https://docs.github.com/en/rest/issues/sub-issues#add-sub-issue
    """

    sub_issue_id: Annotated[
        int,
        Field(
            ...,
            description=(
                "The id of the sub-issue to add — its `id` field, not the `#number` "
                "shown in GitHub's interface. The sub-issue must belong to the same "
                "repository owner as the parent issue."
            ),
        ),
        Body(),
    ]
    replace_parent: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "When true, moves the sub-issue here from whatever parent it has now. "
                "Absent, an issue that already has a parent is refused."
            ),
        ),
        Body(),
    ]
