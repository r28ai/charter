# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for GitHub's repository endpoints.

API Reference: https://docs.github.com/en/rest/repos/repos
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.github.types.common import GitHubListRequest, RepoRequest, SortDirection
from charter.types import Body, Format, Path, Query

__all__ = [
    "ReposGetRequest",
    "ReposListForAuthenticatedUserRequest",
    "ReposGetContentRequest",
    "ReposListCommitsRequest",
    "ReposCreateOrUpdateFileRequest",
    "BranchesListRequest",
    "GitRefsCreateRequest",
    "GitAuthor",
    "CommitIdentity",
    "OrgRepoType",
    "ReposGetCommitRequest",
    "ReposCompareCommitsRequest",
    "ReposDeleteFileRequest",
    "ReposMergeBranchesRequest",
    "ReposGetBranchRequest",
    "ReposRenameBranchRequest",
    "ReposGetBranchProtectionRequest",
    "ReposListBranchesForHeadCommitRequest",
    "ReposGetReadmeRequest",
    "ReposListTagsRequest",
    "ReposCreateForkRequest",
    "ReposListForOrgRequest",
    "ReposListLanguagesRequest",
    "ReposListContributorsRequest",
]


RepoVisibility = Literal["all", "public", "private"]
RepoType = Literal["all", "owner", "public", "private", "member"]
RepoSort = Literal["created", "updated", "pushed", "full_name"]
OrgRepoType = Literal["all", "public", "private", "forks", "sources", "member"]
"""What kinds of repository an organization listing returns. A different set
from :data:`RepoType`, which is the personal listing's."""


class ReposGetRequest(RepoRequest):
    """Get a repository.

    API Reference: https://docs.github.com/en/rest/repos/repos#get-a-repository
    """


class ReposListForAuthenticatedUserRequest(GitHubListRequest):
    """List repositories the authenticated user has explicit access to.

    API Reference: https://docs.github.com/en/rest/repos/repos#list-repositories-for-the-authenticated-user
    """

    visibility: Annotated[
        Optional[RepoVisibility],
        Field(
            None,
            description=(
                "Limit results to repositories with the specified visibility. GitHub "
                "uses `all` when this is omitted. Cannot be combined with `type`."
            ),
        ),
        Query(),
    ]
    affiliation: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Comma-separated list of values. Must be one or more of: `owner`, "
                "`collaborator`, `organization_member`. GitHub uses "
                "`owner,collaborator,organization_member` when this is omitted. Cannot "
                "be combined with `type`."
            ),
        ),
        Query(),
    ]
    type: Annotated[
        Optional[RepoType],
        Field(
            None,
            description=(
                "Limit results to repositories of the specified type. GitHub uses `all` "
                "when this is omitted. Cannot be combined with `visibility` or "
                "`affiliation` — GitHub answers 422 to a request carrying both."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[RepoSort],
        Field(
            "full_name",
            description="The property to sort the results by. Defaults to `full_name`.",
        ),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(
            None,
            description=(
                "The order to sort by. Default: `asc` when using `full_name`, otherwise `desc`."
            ),
        ),
        Query(),
    ]
    since: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show repositories updated after the given time, in ISO 8601 "
                "format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]
    before: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show repositories updated before the given time, in ISO 8601 "
                "format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]

    @model_validator(mode="after")
    def _type_excludes_visibility_and_affiliation(self) -> ReposListForAuthenticatedUserRequest:
        """GitHub answers 422 when `type` arrives beside either of the other two.

        These three carry documented *server-side* defaults — what GitHub applies
        to a request that omits them — and copying those onto the schema is what
        turned every default call into a 422, because a default that is sent is
        not a default at all. They default to ``None`` here for that reason, and
        this rule catches the combination GitHub rejects before it costs a round
        trip.
        """
        if self.type is not None and (self.visibility is not None or self.affiliation is not None):
            raise ValueError(
                "`type` cannot be combined with `visibility` or `affiliation` — "
                "GitHub answers 422. Use `type` on its own, or use `visibility` "
                "and `affiliation` together."
            )
        return self


class ReposGetContentRequest(RepoRequest):
    """Get the contents of a file or directory in a repository.

    The response for a file carries the content base64-encoded in ``content``;
    the pack's response handler decodes it, so the model reads the file rather
    than a blob.

    API Reference: https://docs.github.com/en/rest/repos/contents#get-repository-content
    """

    path: Annotated[
        str,
        Field(
            ...,
            description=(
                "The path of the file or directory, relative to the repository root. "
                "Use an empty string for the root directory."
            ),
        ),
        # Genuinely multi-segment: "src/charter/tool.py" is one value, not three.
        Path(allow_slash=True),
    ]
    ref: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The name of the commit/branch/tag. Defaults to the repository's default branch."
            ),
        ),
        Query(),
    ]


class ReposListCommitsRequest(RepoRequest, GitHubListRequest):
    """List commits on a repository.

    API Reference: https://docs.github.com/en/rest/commits/commits#list-commits
    """

    sha: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "SHA or branch to start listing commits from. Defaults to the "
                "repository's default branch."
            ),
        ),
        Query(),
    ]
    path: Annotated[
        Optional[str],
        Field(None, description="Only commits containing this file path will be returned."),
        Query(),
    ]
    author: Annotated[
        Optional[str],
        Field(
            None,
            description="GitHub username or email address to filter commits by author.",
        ),
        Query(),
    ]
    since: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only commits after this date will be returned, in ISO 8601 format: "
                "`YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]
    until: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only commits before this date will be returned, in ISO 8601 format: "
                "`YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]


class CommitIdentity(BaseModel):
    """Who a contents-endpoint commit is attributed to.

    GitHub answers 422 if either field is missing — "You must provide values for
    both `name` and `email`, whether you choose to use `author` or `committer`"
    — so both are required inside even where the object itself is optional.
    """

    name: str = Field(..., description="The person's name.")
    email: str = Field(..., description="The person's email address.")


class GitAuthor(CommitIdentity):
    """The same identity, plus the timestamp the *write* endpoint also accepts.

    The two contents endpoints disagree by one field. `PUT /contents/{path}`
    takes `name`, `email` and `date`; `DELETE /contents/{path}` takes the first
    two and has no `date` at all. Reusing one model on both put a field in front
    of the model that the delete endpoint has never accepted — found by reading
    the egress map against GitHub's own description, which is what that map is
    for. Extended rather than copied, so the two descriptions keep one home.
    """

    date: Optional[str] = Field(None, description="ISO 8601 timestamp for the commit.")


class ReposCreateOrUpdateFileRequest(RepoRequest):
    """Write a file, creating it or replacing it in one commit.

    `sha` is what makes this create or update. Creating a file omits it; replacing
    one requires the blob SHA of the file being replaced, which comes back from
    reading the file first. Sending a stale SHA is refused rather than clobbering
    the newer content.

    Write the file's text plainly. The base64 encoding GitHub requires is the
    runtime's job.

    Writing under `.github/workflows` additionally needs the `workflow` scope.
    GitHub also rejects parallel writes to the same repository, so these calls go
    one at a time.

    API Reference: https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents
    """

    path: Annotated[
        str,
        Field(..., description="Path to the file, relative to the repository root."),
        Path(allow_slash=True),
    ]
    message: Annotated[str, Field(..., description="The commit message."), Body()]
    content: Annotated[
        str,
        Field(..., description="The file's contents, as plain text."),
        Format("base64"),
        Body(),
    ]
    sha: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The blob SHA of the file being replaced. Required when updating an "
                "existing file, omitted when creating a new one."
            ),
        ),
        Body(),
    ]
    branch: Annotated[
        Optional[str],
        Field(None, description="The branch to commit to. Absent, the default branch."),
        Body(),
    ]
    committer: Annotated[
        Optional[GitAuthor],
        Field(None, description="Who made the commit. Absent, the authenticated user."),
        Body(),
    ]
    author: Annotated[
        Optional[GitAuthor],
        Field(None, description="Who wrote the change, if not the committer."),
        Body(),
    ]


class BranchesListRequest(RepoRequest, GitHubListRequest):
    """List a repository's branches.

    `protected` has three states, not two: true for protected branches only, false
    for unprotected only, and absent for all of them.

    API Reference: https://docs.github.com/en/rest/branches/branches#list-branches
    """

    protected: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Limit to protected branches when true, unprotected when false. "
                "Absent, every branch is returned."
            ),
        ),
        Query(),
    ]


class GitRefsCreateRequest(RepoRequest):
    """Create a branch or tag by pointing a new ref at an existing commit.

    API Reference: https://docs.github.com/en/rest/git/refs#create-a-reference
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The fully qualified reference, such as 'refs/heads/my-branch'. A "
                "bare branch name is rejected."
            ),
        ),
        Body(),
    ]
    sha: Annotated[
        str,
        Field(..., description="The commit SHA the new reference points at."),
        Body(),
    ]

    @model_validator(mode="after")
    def _ref_is_fully_qualified(self) -> GitRefsCreateRequest:
        """GitHub states the rule and the rejection: it must start with `refs` and
        carry at least two slashes."""
        if not self.ref.startswith("refs/") or self.ref.count("/") < 2:
            raise ValueError(
                f"`ref` must be fully qualified, like 'refs/heads/{self.ref}', not "
                f"'{self.ref}'. GitHub rejects anything that does not start with "
                "'refs' and contain at least two slashes."
            )
        return self


# -----------------------------------------------------
# Reading history: one commit, and the range between two
# -----------------------------------------------------


class ReposGetCommitRequest(RepoRequest, GitHubListRequest):
    """Get one commit, with its diff and per-file statistics.

    The repository-level view of a commit — `git_commits_get` is the Git-level
    one, which has the message and the tree but no diff.

    The pagination here is unusual and worth reading twice: it pages the
    **files**, not a list of commits. GitHub: "If there are more than 300 files
    in the commit diff and the default JSON media type is requested, the
    response will include pagination link headers for the remaining files, up to
    a limit of 3000 files. Each page contains the static commit information, and
    the only changes are to the file listing."

    API Reference: https://docs.github.com/en/rest/commits/commits#get-a-commit
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The commit reference: a commit SHA, a branch name "
                "(`heads/BRANCH_NAME`), or a tag (`tags/TAG_NAME`)."
            ),
        ),
        Path(allow_slash=True),
    ]


class ReposCompareCommitsRequest(RepoRequest, GitHubListRequest):
    """Compare two commits, branches or tags: what is in one and not the other.

    `basehead` is a single string in the form `BASE...HEAD` — three dots, and
    both halves in one path parameter. Across a fork, each half takes a
    `USERNAME:` prefix: `octocat:main...contributor:fix`.

    Two caps, both GitHub's: without paging parameters the commit list stops at
    250, and "The list of changed files is only shown on the first page of
    results, and it includes up to 300 changed files for the entire comparison."

    API Reference: https://docs.github.com/en/rest/commits/commits#compare-two-commits
    """

    basehead: Annotated[
        str,
        Field(
            ...,
            description=(
                "The base and head to compare, as `BASE...HEAD` — for example "
                "`main...my-feature`. Across repositories in the same network, prefix "
                "each side with its owner: `octocat:main...contributor:fix`."
            ),
        ),
        Path(allow_slash=True),
    ]

    @model_validator(mode="after")
    def _basehead_has_both_sides(self) -> ReposCompareCommitsRequest:
        """Two dots is a different Git operator and GitHub does not accept it here."""
        if "..." not in self.basehead:
            raise ValueError(
                f"`basehead` must be 'BASE...HEAD' with three dots, not "
                f"'{self.basehead}'. For example 'main...my-feature'."
            )
        base, _, head = self.basehead.partition("...")
        if not base or not head:
            raise ValueError(
                f"`basehead` needs a ref on both sides of the '...', got '{self.basehead}'."
            )
        return self


class ReposDeleteFileRequest(RepoRequest):
    """Remove a file, in a commit of its own.

    Like its create-or-update sibling this is one file per commit, and it takes
    a required body on a DELETE, which is GitHub's. `sha` is the blob SHA of the
    file being removed — read the file first, or take it from a tree.

    To delete several files in one commit, build a tree instead:
    `git_trees_create` with `delete: true` entries.

    GitHub rejects parallel writes to the same repository, so these calls go one
    at a time.

    API Reference: https://docs.github.com/en/rest/repos/contents#delete-a-file
    """

    path: Annotated[
        str,
        Field(..., description="Path to the file, relative to the repository root."),
        Path(allow_slash=True),
    ]
    message: Annotated[str, Field(..., description="The commit message."), Body()]
    sha: Annotated[
        str,
        Field(..., description="The blob SHA of the file being deleted."),
        Body(),
    ]
    branch: Annotated[
        Optional[str],
        Field(None, description="The branch name. Absent, the repository's default branch."),
        Body(),
    ]
    committer: Annotated[
        Optional[CommitIdentity],
        Field(None, description="Who made the commit. Absent, the authenticated user."),
        Body(),
    ]
    author: Annotated[
        Optional[CommitIdentity],
        Field(None, description="Who wrote the change, if not the committer."),
        Body(),
    ]


class ReposMergeBranchesRequest(RepoRequest):
    """Merge one branch into another directly, without a pull request.

    GitHub answers 201 with the merge commit, **204 when the base already
    contains the head** — nothing to do — and 409 on a conflict. The 204 comes
    back here as an empty object, which is the "already up to date" case.

    API Reference: https://docs.github.com/en/rest/branches/branches#merge-a-branch
    """

    base: Annotated[
        str,
        Field(..., description="The name of the base branch that the head will be merged into."),
        Body(),
    ]
    head: Annotated[
        str,
        Field(..., description="The head to merge. This can be a branch name or a commit SHA1."),
        Body(),
    ]
    commit_message: Annotated[
        Optional[str],
        Field(
            None,
            description="Commit message to use for the merge commit. If omitted, a default message will be used.",
        ),
        Body(),
    ]


class _Branch(RepoRequest):
    branch: Annotated[
        str,
        Field(
            ...,
            description=(
                "The name of the branch. Cannot contain wildcard characters. A plain "
                "name — `main`, not `refs/heads/main`."
            ),
        ),
        Path(allow_slash=True),
    ]


class ReposGetBranchRequest(_Branch):
    """Get one branch: its head commit, and whether it is protected.

    API Reference: https://docs.github.com/en/rest/branches/branches#get-a-branch
    """


class ReposRenameBranchRequest(_Branch):
    """Rename a branch.

    GitHub: "Although the API responds immediately, the branch rename process
    might take some extra time to complete in the background. You won't be able
    to push to the old branch name while the rename process is in progress."

    Renaming the default branch additionally needs admin or owner permission.

    API Reference: https://docs.github.com/en/rest/branches/branches#rename-a-branch
    """

    new_name: Annotated[str, Field(..., description="The new name of the branch."), Body()]


class ReposGetBranchProtectionRequest(_Branch):
    """Read a branch's protection rules: what a push or a merge must satisfy.

    Worth reading before attempting a write. Required status checks, required
    reviews and a linear-history rule are each a reason a later `git_refs_update`
    or `pulls_merge` is refused, and each is visible here first.

    A 404 from this endpoint does not distinguish "no such branch" from "that
    branch is not protected" — GitHub returns the same status for both.

    API Reference: https://docs.github.com/en/rest/branches/branch-protection#get-branch-protection
    """


class ReposListBranchesForHeadCommitRequest(RepoRequest):
    """List the branches whose head is this commit.

    Answers "has this landed, and where" from the commit's side — the reverse of
    looking through branches for a SHA.

    API Reference: https://docs.github.com/en/rest/commits/commits#list-branches-for-head-commit
    """

    commit_sha: Annotated[
        str,
        Field(..., description="The SHA of the commit."),
        Path(),
    ]


class ReposGetReadmeRequest(RepoRequest):
    """Get the repository's README, decoded.

    GitHub picks "the preferred README" itself across the spellings and
    extensions a repository might use, which is why this exists beside
    `repos_get_content`.

    API Reference: https://docs.github.com/en/rest/repos/contents#get-a-repository-readme
    """

    ref: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The name of the commit/branch/tag. Absent, the repository's default branch."
            ),
        ),
        Query(),
    ]


class ReposListTagsRequest(RepoRequest, GitHubListRequest):
    """List a repository's tags, newest first.

    API Reference: https://docs.github.com/en/rest/repos/repos#list-repository-tags
    """


class ReposCreateForkRequest(RepoRequest):
    """Fork a repository.

    GitHub: "Forking a Repository happens asynchronously. You may have to wait a
    short period of time before you can access the git objects." The repository
    record comes back immediately; its contents may not be there yet.

    API Reference: https://docs.github.com/en/rest/repos/forks#create-a-fork
    """

    organization: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Optional parameter to specify the organization name if forking into "
                "an organization. Absent, the fork goes to the authenticated user."
            ),
        ),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(
            None, description="When forking from an existing repository, a new name for the fork."
        ),
        Body(),
    ]
    default_branch_only: Annotated[
        Optional[bool],
        Field(
            None,
            description="When forking from an existing repository, fork with only the default branch.",
        ),
        Body(),
    ]


class ReposListForOrgRequest(GitHubListRequest):
    """List an organization's repositories.

    API Reference: https://docs.github.com/en/rest/repos/repos#list-organization-repositories
    """

    org: Annotated[
        str,
        Field(..., description="The organization name. The name is not case sensitive."),
        Path(),
    ]
    type: Annotated[
        Optional[OrgRepoType],
        Field(
            None,
            description=(
                "Limit results to repositories of the specified type. GitHub uses `all` "
                "when this is absent."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[RepoSort],
        Field(
            None,
            description="The property to sort the results by. GitHub uses `created` when this is absent.",
        ),
        Query(),
    ]
    direction: Annotated[
        Optional[SortDirection],
        Field(
            None,
            description=(
                "The order to sort by. GitHub's default depends on `sort`: `asc` when "
                "sorting by `full_name`, `desc` otherwise."
            ),
        ),
        Query(),
    ]


class ReposListLanguagesRequest(RepoRequest):
    """List the languages in a repository, with bytes of code each.

    The response is an *object* keyed by language name, not a list, so it does
    not page and there is nothing to walk.

    API Reference: https://docs.github.com/en/rest/repos/repos#list-repository-languages
    """


class ReposListContributorsRequest(RepoRequest, GitHubListRequest):
    """List contributors, most commits first.

    GitHub identifies contributors by author email, and "only the first 500
    author email addresses in the repository link to GitHub users. The rest will
    appear as anonymous contributors."

    An empty repository answers 204 rather than an empty list, which arrives
    here as an empty object.

    API Reference: https://docs.github.com/en/rest/repos/repos#list-repository-contributors
    """

    anon: Annotated[
        Optional[str],
        Field(
            None,
            description="Set to `1` or `true` to include anonymous contributors in results.",
        ),
        Query(),
    ]
