"""Request schemas for GitHub's pull request endpoints.

API Reference: https://docs.github.com/en/rest/pulls/pulls
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.github.types.common import GitHubListRequest, RepoRequest, SortDirection
from charter.types import Body, Path, Query

__all__ = [
    "PullsListRequest",
    "PullsGetRequest",
    "PullsCreateRequest",
    "PullsListFilesRequest",
    "PullsUpdateRequest",
    "PullsMergeRequest",
    "PullsCreateReviewRequest",
    "PullsListReviewsRequest",
    "PullsRequestReviewersRequest",
    "ReviewComment",
    "MergeMethod",
    "ReviewEvent",
    "ReviewSide",
    "PullsGetDiffRequest",
    "ReviewCommentSort",
    "RepoReviewCommentSort",
    "SubjectType",
    "PullsCreateReviewCommentRequest",
    "PullsListReviewCommentsRequest",
    "PullsListReviewCommentsForRepoRequest",
    "PullsReplyToReviewCommentRequest",
    "PullsUpdateReviewCommentRequest",
    "PullsDeleteReviewCommentRequest",
    "PullsGetReviewRequest",
    "PullsSubmitReviewRequest",
    "PullsUpdateReviewRequest",
    "PullsDismissReviewRequest",
    "PullsDeletePendingReviewRequest",
    "PullsListCommentsForReviewRequest",
    "PullsListCommitsRequest",
    "PullsUpdateBranchRequest",
    "PullsCheckMergedRequest",
    "PullsListRequestedReviewersRequest",
    "PullsRemoveRequestedReviewersRequest",
]


PullState = Literal["open", "closed", "all"]
PullSort = Literal["created", "updated", "popularity", "long-running"]


class PullsListRequest(RepoRequest, GitHubListRequest):
    """List pull requests in a repository.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests
    """

    state: Annotated[
        Optional[PullState],
        Field(
            "open",
            description=(
                "Either `open`, `closed`, or `all` to filter by state. Defaults to `open`."
            ),
        ),
        Query(),
    ]
    head: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Filter pulls by head user or head organization and branch name in the "
                "format of `user:ref-name` or `organization:ref-name`."
            ),
        ),
        Query(),
    ]
    base: Annotated[
        Optional[str],
        Field(None, description="Filter pulls by base branch name. Example: `gh-pages`."),
        Query(),
    ]
    sort: Annotated[
        Optional[PullSort],
        Field("created", description="What to sort results by. Defaults to `created`."),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(
            None,
            description=(
                "The direction of the sort. Default: `desc` when sort is `created` or "
                "not specified, otherwise `asc`."
            ),
        ),
        Query(),
    ]


class PullsGetRequest(RepoRequest):
    """Get a single pull request, including its diff statistics and mergeability.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    """

    pull_number: Annotated[
        int,
        Field(..., description="The number that identifies the pull request."),
        Path(),
    ]


class PullsGetDiffRequest(RepoRequest):
    """Get a pull request as a unified diff, or as an mbox patch.

    The same endpoint as :class:`PullsGetRequest` and the same arguments. What
    differs is the representation GitHub is asked for, and it is asked for in
    the ``Accept`` header — ``application/vnd.github.diff`` rather than
    ``application/vnd.github+json``.

    That is why this is a second tool rather than a field on the first. A media
    type is a constant of the request, not an argument of it: put it in the
    schema and the model is choosing a header value, and the pack's own rule is
    that constants are infrastructure. Declared on a second factory it stays a
    constant, and the model chooses between two named tools instead — which is
    the choice it is actually making.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request
    """

    pull_number: Annotated[
        int,
        Field(..., description="The number that identifies the pull request."),
        Path(),
    ]


class PullCreateBody(BaseModel):
    """The body of a create-pull-request request.

    Exactly one of ``title`` or ``issue`` is required: ``title`` opens a new pull
    request, ``issue`` converts an existing issue into one.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request
    """

    title: Optional[str] = Field(
        None,
        description="The title of the new pull request. Required unless `issue` is given.",
    )
    head: str = Field(
        ...,
        description=(
            "The name of the branch where your changes are implemented. For "
            "cross-repository pull requests, prefix with a username, e.g. "
            "`username:branch`."
        ),
    )
    head_repo: Optional[str] = Field(
        None,
        description=(
            "The name of the repository where the changes in the pull request were "
            "made. Used for cross-repository pull requests from forks."
        ),
    )
    base: str = Field(
        ...,
        description=(
            "The name of the branch you want the changes pulled into. This should be "
            "an existing branch on the current repository."
        ),
    )
    body: Optional[str] = Field(None, description="The contents of the pull request.")
    maintainer_can_modify: Optional[bool] = Field(
        None,
        description="Indicates whether maintainers can modify the pull request.",
    )
    draft: Optional[bool] = Field(
        None,
        description="Indicates whether the pull request is a draft.",
    )
    issue: Optional[int] = Field(
        None,
        description=(
            "An issue number to convert into a pull request. Required unless `title` "
            "is given. The issue's title, body and comments carry over."
        ),
    )

    @model_validator(mode="after")
    def _title_or_issue(self) -> PullCreateBody:
        if (self.title is None) == (self.issue is None):
            raise ValueError(
                "Exactly one of `title` (open a new pull request) or `issue` (convert "
                "an existing issue) must be provided."
            )
        return self


class PullsCreateRequest(RepoRequest):
    """Open a pull request.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#create-a-pull-request
    """

    body: Annotated[
        PullCreateBody,
        Field(..., description="The pull request to open."),
        Body(),
    ]


class PullsListFilesRequest(RepoRequest, GitHubListRequest):
    """List the files changed by a pull request.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
    """

    pull_number: Annotated[
        int,
        Field(..., description="The number that identifies the pull request."),
        Path(),
    ]


MergeMethod = Literal["merge", "squash", "rebase"]
ReviewEvent = Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"]
ReviewSide = Literal["LEFT", "RIGHT"]
PullUpdateState = Literal["open", "closed"]


class _PullNumber(RepoRequest):
    """The pull request a request acts on."""

    pull_number: Annotated[
        int,
        Field(..., description="The number that identifies the pull request."),
        Path(),
    ]


class PullsUpdateRequest(_PullNumber):
    """Update a pull request's title, body, state or base branch.

    GitHub exposes no `draft` field here, so marking a pull request ready for
    review is not reachable over REST.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request
    """

    title: Annotated[Optional[str], Field(None, description="The new title."), Body()]
    body: Annotated[Optional[str], Field(None, description="The new description."), Body()]
    state: Annotated[
        Optional[PullUpdateState],
        Field(None, description="Whether the pull request is open or closed."),
        Body(),
    ]
    base: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The branch to merge into. It must already exist on this repository; "
                "a pull request cannot be repointed at another repository."
            ),
        ),
        Body(),
    ]
    maintainer_can_modify: Annotated[
        Optional[bool],
        Field(None, description="Whether maintainers can commit to the head branch."),
        Body(),
    ]


class PullsMergeRequest(_PullNumber):
    """Merge a pull request.

    Failure arrives as a status code rather than in the body: 405 when the pull
    request cannot be merged, and 409 when `sha` no longer matches the head.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
    """

    merge_method: Annotated[
        Optional[MergeMethod],
        Field(
            None,
            description=(
                "How to merge. Absent, GitHub creates a merge commit. 'squash' "
                "collapses the branch into one commit, 'rebase' replays it."
            ),
        ),
        Body(),
    ]
    commit_title: Annotated[
        Optional[str], Field(None, description="Title for the merge commit."), Body()
    ]
    commit_message: Annotated[
        Optional[str], Field(None, description="Extra detail for the merge commit."), Body()
    ]
    sha: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The head SHA this merge expects. If the branch has moved since, the "
                "merge is refused rather than merging work you have not seen."
            ),
        ),
        Body(),
    ]


class ReviewComment(BaseModel):
    """One inline comment left as part of a review.

    `position` is not offered: GitHub deprecated it in 2022 in favour of `line`.
    """

    path: str = Field(..., description="The file the comment is on, relative to the repo root.")
    body: str = Field(..., description="The comment text.")
    line: Optional[int] = Field(
        None,
        description=(
            "The line in the diff the comment applies to. For a multi-line comment, "
            "the last line of the range."
        ),
    )
    side: Optional[ReviewSide] = Field(
        None, description="Which side of the diff: 'LEFT' is the old file, 'RIGHT' the new."
    )
    start_line: Optional[int] = Field(
        None, description="The first line of a multi-line comment."
    )
    start_side: Optional[ReviewSide] = Field(
        None, description="Which side the multi-line range starts on."
    )


class PullsCreateReviewRequest(_PullNumber):
    """Review a pull request: approve it, request changes, or comment.

    `event` is required here although GitHub marks it optional. Omitting it creates
    a review in the PENDING state, which has to be submitted by a separate endpoint
    this pack does not carry: an agent that left one would have no way to finish.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#create-a-review-for-a-pull-request
    """

    event: Annotated[
        ReviewEvent,
        Field(..., description="Whether to approve, request changes, or just comment."),
        Body(),
    ]
    body: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The review text. Required when requesting changes or commenting, "
                "optional when approving."
            ),
        ),
        Body(),
    ]
    commit_id: Annotated[
        Optional[str],
        Field(None, description="The commit to review. Absent, the most recent one."),
        Body(),
    ]
    comments: Annotated[
        Optional[List[ReviewComment]],
        Field(None, description="Inline comments to leave on specific lines."),
        Body(),
    ]

    @model_validator(mode="after")
    def _body_when_not_approving(self) -> PullsCreateReviewRequest:
        """GitHub requires a body for everything except an approval."""
        if self.event in ("REQUEST_CHANGES", "COMMENT") and not self.body:
            raise ValueError(
                f"`body` is required when `event` is '{self.event}'. Only an APPROVE "
                "may be left without one."
            )
        return self


class PullsListReviewsRequest(_PullNumber, GitHubListRequest):
    """List the reviews on a pull request, oldest first.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request
    """


class PullsRequestReviewersRequest(_PullNumber):
    """Ask people or teams to review a pull request.

    GitHub marks both lists optional, which would let a request ask nobody for
    anything. At least one is required here.

    API Reference: https://docs.github.com/en/rest/pulls/review-requests
    """

    reviewers: Annotated[
        Optional[List[str]],
        Field(None, description="Usernames to request a review from."),
        Body(),
    ]
    team_reviewers: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Team slugs to request a review from. A slug, not a team name.",
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _someone_must_be_asked(self) -> PullsRequestReviewersRequest:
        if not self.reviewers and not self.team_reviewers:
            raise ValueError(
                "Name at least one of `reviewers` or `team_reviewers`. A review "
                "request that asks nobody does nothing."
            )
        return self


# -----------------------------------------------------
# Review comments — a comment on a line of a diff
# -----------------------------------------------------

ReviewCommentSort = Literal["created", "updated"]
"""How the per-pull-request comment list is sorted."""

RepoReviewCommentSort = Literal["created", "updated", "created_at"]
"""How the repository-wide comment list is sorted.

Wider than the per-pull-request enum by one value. `created_at` is GitHub's
older spelling of `created` and it still accepts it here and not there, which
is why these are two aliases and not one."""

SubjectType = Literal["line", "file"]
"""Whether a review comment is attached to a line of the diff or to the whole
file. `file` is what makes `line` unnecessary."""


class PullsCreateReviewCommentRequest(_PullNumber):
    """Comment on one line of a pull request's diff.

    The primitive that reviewing is made of, and the one this pack was missing:
    ``pulls_create_review`` leaves a verdict on the whole change, and this
    leaves a remark on the line that earned it.

    Three rules from GitHub, each of which is a 422 when broken:

    * ``commit_id`` is required, and should be the pull request's latest head.
      GitHub: "Not using the latest commit SHA may render your comment outdated
      if a subsequent commit modifies the line you specify."
    * ``line`` is "Required unless using ``subject_type:file``" — a
      file-level comment has no line, and a line-level one cannot do without.
    * A multi-line comment needs ``start_line`` and ``start_side`` as well,
      "unless using ``in_reply_to``".

    ``in_reply_to`` overrides everything: GitHub says that when it is set, "all
    parameters other than ``body`` in the request body are ignored". The
    validator below refuses that combination rather than sending fields the
    server will drop, because a comment that lands somewhere other than where
    the model aimed it is worse than a rejected call.

    ``position`` is not offered. GitHub marks it "closing down" in favour of
    ``line``, and it counts lines from a hunk header rather than naming one,
    which is not a number a model can work out from a diff it has read.

    API Reference: https://docs.github.com/en/rest/pulls/comments#create-a-review-comment-for-a-pull-request
    """

    body: Annotated[str, Field(..., description="The text of the review comment."), Body()]
    commit_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "The SHA of the commit needing a comment. Use the pull request's "
                "current head SHA — an older one may leave the comment attached to a "
                "line a later commit has already changed."
            ),
        ),
        Body(),
    ]
    path: Annotated[
        str,
        Field(..., description="The relative path to the file that necessitates a comment."),
        Body(),
    ]
    line: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "Required unless using `subject_type: file`. The line of the blob in "
                "the pull request diff that the comment applies to. For a multi-line "
                "comment, the last line of the range that your comment applies to."
            ),
        ),
        Body(),
    ]
    side: Annotated[
        Optional[ReviewSide],
        Field(
            None,
            description=(
                "In a split diff view, the side of the diff that the pull request's "
                "changes appear on. Use `LEFT` for deletions that appear in red. Use "
                "`RIGHT` for additions that appear in green or unchanged lines that "
                "appear in white and are shown for context."
            ),
        ),
        Body(),
    ]
    start_line: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "Required when using multi-line comments unless using `in_reply_to`. "
                "The first line in the pull request diff that your multi-line comment "
                "applies to."
            ),
        ),
        Body(),
    ]
    start_side: Annotated[
        Optional[ReviewSide],
        Field(
            None,
            description=(
                "Required when using multi-line comments unless using `in_reply_to`. "
                "The starting side of the diff that the comment applies to."
            ),
        ),
        Body(),
    ]
    subject_type: Annotated[
        Optional[SubjectType],
        Field(
            None,
            description=(
                "The level at which the comment is targeted. `file` comments on the "
                "whole file and needs no `line`; absent, GitHub targets a line."
            ),
        ),
        Body(),
    ]
    in_reply_to: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The ID of an existing top-level review comment to reply to, from "
                "`pulls_list_review_comments`. When set, no other field here may be "
                "given: GitHub ignores them all except `body`."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _placement_is_complete_and_unambiguous(self) -> PullsCreateReviewCommentRequest:
        """The three placement rules, checked before the round trip.

        `in_reply_to` is checked first and strictly. GitHub *ignores* the other
        fields rather than rejecting them, which means a model that sets a
        `path` and a `line` beside a reply id gets a 201 and a comment in a
        place it did not choose. A validation error here is the only signal
        that distinguishes the two outcomes.
        """
        if self.in_reply_to is not None:
            extra = [
                name
                for name in ("line", "side", "start_line", "start_side", "subject_type")
                if getattr(self, name) is not None
            ]
            if extra:
                raise ValueError(
                    f"`in_reply_to` cannot be combined with {', '.join(extra)}. GitHub "
                    "ignores every field except `body` on a reply, so the comment "
                    "would be posted somewhere other than where these fields place it. "
                    "Reply with `body` alone, or post a new comment without "
                    "`in_reply_to`."
                )
            return self

        if self.subject_type != "file" and self.line is None:
            raise ValueError(
                "`line` is required unless `subject_type` is 'file'. Give the line of "
                "the diff the comment applies to, or set `subject_type` to 'file' to "
                "comment on the whole file."
            )
        if self.start_line is not None:
            if self.start_side is None:
                raise ValueError(
                    "A multi-line comment needs `start_side` beside `start_line`."
                )
            if self.line is not None and self.start_line > self.line:
                raise ValueError(
                    f"`start_line` ({self.start_line}) must not be after `line` "
                    f"({self.line}) — `line` is the last line of the range."
                )
        return self


class PullsListReviewCommentsRequest(_PullNumber, GitHubListRequest):
    """List the line comments on a pull request, oldest first.

    API Reference: https://docs.github.com/en/rest/pulls/comments#list-review-comments-on-a-pull-request
    """

    sort: Annotated[
        Optional[ReviewCommentSort],
        Field(None, description="The property to sort the results by. GitHub uses `created` when this is absent."),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(None, description="The direction to sort results. Ignored without `sort` parameter."),
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


class PullsListReviewCommentsForRepoRequest(RepoRequest, GitHubListRequest):
    """List the line comments on every pull request in a repository.

    API Reference: https://docs.github.com/en/rest/pulls/comments#list-review-comments-in-a-repository
    """

    sort: Annotated[
        Optional[RepoReviewCommentSort],
        Field(None, description="The property to sort the results by."),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(None, description="The direction to sort results. Ignored without `sort` parameter."),
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


class _CommentId(RepoRequest):
    comment_id: Annotated[
        int,
        Field(..., description="The unique identifier of the review comment."),
        Path(),
    ]


class PullsReplyToReviewCommentRequest(_PullNumber):
    """Reply to a review comment, continuing its thread.

    GitHub: the id must be "the ID of a *top-level review comment*, not a reply
    to that comment. Replies to replies are not supported."

    API Reference: https://docs.github.com/en/rest/pulls/comments#create-a-reply-for-a-review-comment
    """

    comment_id: Annotated[
        int,
        Field(
            ...,
            description=(
                "The unique identifier of the top-level review comment being replied "
                "to. A reply's own id is not accepted here."
            ),
        ),
        Path(),
    ]
    body: Annotated[str, Field(..., description="The text of the review comment."), Body()]


class PullsUpdateReviewCommentRequest(_CommentId):
    """Edit a review comment's text.

    API Reference: https://docs.github.com/en/rest/pulls/comments#update-a-review-comment-for-a-pull-request
    """

    body: Annotated[str, Field(..., description="The text of the review comment."), Body()]


class PullsDeleteReviewCommentRequest(_CommentId):
    """Delete a review comment.

    API Reference: https://docs.github.com/en/rest/pulls/comments#delete-a-review-comment-for-a-pull-request
    """


# -----------------------------------------------------
# The review lifecycle
# -----------------------------------------------------


class _ReviewId(_PullNumber):
    review_id: Annotated[
        int,
        Field(..., description="The unique identifier of the review."),
        Path(),
    ]


class PullsGetReviewRequest(_ReviewId):
    """Get one review of a pull request.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#get-a-review-for-a-pull-request
    """


class PullsSubmitReviewRequest(_ReviewId):
    """Submit a pending review, turning it into an approval, a request for
    changes, or a comment.

    The other half of a two-step review: a review created without an `event` is
    left PENDING and is not visible to anyone until it is submitted here.
    ``pulls_create_review`` in this pack requires an `event` precisely so that
    the one-step path never strands a review — this endpoint is what finishes
    one that a `pulls_create_review_comment` sequence built up.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#submit-a-review-for-a-pull-request
    """

    event: Annotated[
        ReviewEvent,
        Field(
            ...,
            description=(
                "The review action to perform. GitHub: leaving this blank returns 422 "
                "and leaves the review PENDING."
            ),
        ),
        Body(),
    ]
    body: Annotated[
        Optional[str],
        Field(None, description="The body text of the pull request review."),
        Body(),
    ]


class PullsUpdateReviewRequest(_ReviewId):
    """Edit a review's summary text.

    Changes the words, not the verdict: there is no `event` here, so an
    approval stays an approval. Dismissing is ``pulls_dismiss_review``.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#update-a-review-for-a-pull-request
    """

    body: Annotated[
        str, Field(..., description="The body text of the pull request review."), Body()
    ]


class PullsDismissReviewRequest(_ReviewId):
    """Dismiss a review, so it no longer blocks the pull request.

    On a protected branch this needs administrator rights, or membership of the
    list of people who may dismiss reviews.

    `event` takes the single value 'DISMISS' and GitHub marks it optional, so it
    is not offered: a field with one legal value and no alternative is a
    constant, and the model has nothing to decide.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#dismiss-a-review-for-a-pull-request
    """

    message: Annotated[
        str,
        Field(..., description="The message for the pull request review dismissal."),
        Body(),
    ]


class PullsDeletePendingReviewRequest(_ReviewId):
    """Delete a review that was never submitted.

    Only a PENDING review can be deleted; GitHub does not delete a submitted
    one. Dismissing is what a submitted review gets instead.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#delete-a-pending-review-for-a-pull-request
    """


class PullsListCommentsForReviewRequest(_ReviewId, GitHubListRequest):
    """List the line comments that belong to one review.

    API Reference: https://docs.github.com/en/rest/pulls/reviews#list-comments-for-a-pull-request-review
    """


# -----------------------------------------------------
# The rest of a pull request's state
# -----------------------------------------------------


class PullsListCommitsRequest(_PullNumber, GitHubListRequest):
    """List the commits on a pull request.

    GitHub caps this at 250 commits however you page it: "Lists a maximum of 250
    commits for a pull request. To receive a complete commit list for pull
    requests with more than 250 commits, use the List commits endpoint" —
    ``repos_list_commits`` here.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#list-commits-on-a-pull-request
    """


class PullsUpdateBranchRequest(_PullNumber):
    """Merge the base branch into the pull request's branch, bringing it up to date.

    The 202 says the job was accepted, not that the branch has moved. Confirm by
    reading the pull request again rather than assuming.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch
    """

    expected_head_sha: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The expected SHA of the pull request's HEAD ref — its most recent "
                "commit. If it does not match, GitHub answers 422 rather than updating "
                "a branch that has moved since you looked."
            ),
        ),
        Body(),
    ]


class PullsCheckMergedRequest(_PullNumber):
    """Ask whether a pull request has been merged.

    This endpoint has no response body at all. GitHub: "The HTTP status of the
    response indicates whether or not the pull request has been merged" — 204
    for merged, 404 for not. Charter raises on the 404, so *not raising* is the
    "yes", and a merged pull request comes back as an empty object.

    ``pulls_get`` reports the same thing in a field you can read, and is the
    better tool unless the status line is what you want.

    API Reference: https://docs.github.com/en/rest/pulls/pulls#check-if-a-pull-request-has-been-merged
    """


class PullsListRequestedReviewersRequest(_PullNumber):
    """List who has been asked to review and has not yet answered.

    GitHub: "Once a requested reviewer submits a review, they are no longer
    considered a requested reviewer" — so this shrinks as a review lands, and an
    empty list does not mean nobody was asked.

    API Reference: https://docs.github.com/en/rest/pulls/review-requests#get-all-requested-reviewers-for-a-pull-request
    """


class PullsRemoveRequestedReviewersRequest(_PullNumber):
    """Withdraw a review request from users or teams.

    A DELETE that carries a required body, which is unusual and is GitHub's:
    `reviewers` is mandatory even when only teams are being removed, so an empty
    list is how you say "no users".

    API Reference: https://docs.github.com/en/rest/pulls/review-requests#remove-requested-reviewers-from-a-pull-request
    """

    reviewers: Annotated[
        List[str],
        Field(
            ...,
            description=(
                "An array of user `login`s that will be removed. Required by GitHub "
                "even when removing teams only — pass an empty list for that case."
            ),
        ),
        Body(),
    ]
    team_reviewers: Annotated[
        Optional[List[str]],
        Field(None, description="An array of team `slug`s that will be removed."),
        Body(),
    ]
