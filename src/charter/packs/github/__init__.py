"""
GitHub — 139 tools over the GitHub REST API.

    from charter import StaticTokenProvider
    from charter.packs import github

    github.configure(StaticTokenProvider(token))   # ghp_... or a GitHub App token
    await github.issues_create.ainvoke(
        owner="octocat", repo="hello-world",
        body={"title": "Flaky test on main", "labels": ["bug"]},
    )

``configure()`` is optional if ``$GITHUB_TOKEN`` is set.

Three things about GitHub that this pack absorbs:

**It requires constant headers alongside the bearer token.** Every request wants
``Accept: application/vnd.github+json`` and ``X-GitHub-Api-Version``, and GitHub
rejects a request with no ``User-Agent`` outright. None of those are the model's
business, so they are declared once as :data:`GITHUB_HEADERS` on the factory and
sent verbatim on every call — the OAuth-plus-constant-header shape, which is
what ``static_headers`` exists for. Pinning the API version is the point: an
unpinned integration is one that breaks on GitHub's schedule rather than yours.

**It pages by number, not by cursor.** There is no token to carry: you ask for
page 1, 2, 3 and stop when a page comes back shorter than ``per_page``.
:data:`GITHUB_PAGINATION` declares that style, so the same
``next_page_args`` loop that walks Slack's cursors walks GitHub's pages.

**Its objects are enormous.** One issue is 4-6KB of nested user objects,
reaction counts and twenty ``*_url`` fields; a page of thirty is a quarter of a
million characters, almost none of it actionable. Nearly every tool has a
response handler, and they project rather than filter — dropping an item would
corrupt the page-length signal that pagination depends on.

Two of them were measured rather than guessed at. On a hundred comments from a
long cpython thread the nested ``user`` object came to 119KB against 87KB for
every word of every comment: trimming it takes the page from ~71,000 tokens to
~29,000 without removing anything anyone reads. ``pulls_list_files`` is the
opposite case — 89% of it is ``patch``, which is the diff and has to stay, so
projecting the three redundant blob URLs away saves only 6%. A large pull
request is genuinely a large response; ``per_page`` is the control, and the
tool's description says so.

``issues_create_comment`` is trimmed with the same projection as the list it
posts into. It used to have no handler, on the grounds that the caller already
knows what it said — true of the body, and not of the rest: GitHub answers a
comment write with the full comment resource, which is the twenty-field ``user``
object, ``reactions``, ``node_id`` and three self-referential URLs around the
text you just sent. What the caller does *not* already have is the new
comment's ``id`` and ``html_url``, which is what an edit, a deletion or a link
back needs, and the projection keeps both.

Four places where GitHub leaves the shape the rest of the pack assumes, each
declared rather than worked around:

* **Logs and artifacts are a 302, not a payload.** GitHub answers
  ``actions_download_job_logs`` with a redirect to a signed URL that "expires
  after 1 minute". Those three tools set ``follow_redirects``; the bearer token
  does not travel with them, because httpx drops ``Authorization`` when a
  redirect leaves the origin. What comes back is not the file: a job log is
  routinely megabytes, so the handler keeps the last 200 lines and the lines
  that look like the failure, and says how many there were in total. Inlining
  the file would undo every projection above in one call.
* **A run's logs are a ZIP and a job's are text.** GitHub's own words are "a
  plain text file" for one and "an archive of log files" for the other. The
  archive is opened with stdlib ``zipfile`` and reduced to one tail per job.
* **``pulls_get_diff`` is the same endpoint as ``pulls_get``.** One URL, three
  representations, selected by ``Accept``. A media type is a constant of the
  request rather than an argument of it — a schema field for it would be the
  model choosing a header value — so the diff is a second factory with the
  header pinned, and the model chooses between two named tools.
* **``releases_upload_asset`` posts bytes to another host.** GitHub serves
  uploads from ``uploads.github.com`` with the file as the body. Both facts are
  on a third factory: :data:`UPLOAD_BASE_URL` and ``body_format="raw"``.

Known limits, named rather than hidden:

* **The ``Link`` header is not read.** GitHub also advertises the next page in a
  ``Link`` header (RFC 8288). Charter's response is the parsed body, so the page
  number is the marker this pack declares. In practice the two agree; where they
  differ is a repository mutating under you mid-walk, and neither marker is
  reliable then. The one place this costs something is
  ``dependabot_list_alerts``, which GitHub pages *only* by a ``Link`` cursor and
  which therefore declares no pagination at all — raise ``per_page`` rather than
  expecting a walk.
* **Issues include pull requests.** That is GitHub's model, not a bug here:
  ``issues_list_for_repo`` returns both. The response handler sets
  ``is_pull_request`` on the ones that are, since GitHub's own signal for it
  (the presence of a ``pull_request`` key) does not survive trimming.
* **``releases_upload_asset`` carries text, not binary.** The body is a schema
  field and a schema field is a string; there is no way to put arbitrary bytes
  through one. A checksums file or a generated changelog uploads; a tarball does
  not.
* **Projects v2 and resolving a review thread are GraphQL-only.** There is no
  REST equivalent of either — ``POST /graphql`` is the whole surface — so
  neither is modelled here. That is a boundary, not an oversight: reaching them
  would mean giving GitHub the Linear and Shopify treatment, a GraphQL factory
  with a document per operation, which is a different pack rather than more of
  this one.
* **Secrets are read by name only.** ``actions_list_repo_secrets`` is the one
  secrets endpoint carried, because it is the one that cannot return a value.
  The write endpoints beside it take a libsodium-sealed box, which is a
  dependency this library does not have and a capability an agent does not need.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.github.response_handlers import (
    passthrough_diff,
    read_artifact_archive,
    tail_job_log,
    tail_run_log_archive,
    trim_annotations,
    trim_artifacts,
    trim_blob,
    trim_branch_protection,
    trim_branches,
    trim_check_runs,
    trim_check_suites,
    trim_code_scanning_alerts,
    trim_code_search,
    trim_combined_status,
    trim_comments,
    trim_commits,
    trim_comparison,
    trim_content,
    trim_contributors,
    trim_dependabot_alerts,
    trim_generated_notes,
    trim_git_commits,
    trim_git_refs,
    trim_issue_events,
    trim_issues,
    trim_jobs,
    trim_labels,
    trim_languages,
    trim_merged_check,
    trim_milestones,
    trim_notifications,
    trim_pending_deployments,
    trim_pull_files,
    trim_pulls,
    trim_rate_limit,
    trim_release_assets,
    trim_releases,
    trim_repos,
    trim_requested_reviewers,
    trim_review_comments,
    trim_reviews,
    trim_run_usage,
    trim_secret_names,
    trim_secret_scanning_alerts,
    trim_tags,
    trim_tree,
    trim_user,
    trim_users,
    trim_workflow_runs,
    trim_workflows,
    trim_written_content,
)
from charter.packs.github.types import (
    ActionsCancelWorkflowRunRequest,
    ActionsCreateWorkflowDispatchRequest,
    ActionsDownloadArtifactRequest,
    ActionsDownloadJobLogsRequest,
    ActionsDownloadRunLogsRequest,
    ActionsGetArtifactRequest,
    ActionsGetJobRequest,
    ActionsGetRunUsageRequest,
    ActionsGetWorkflowRequest,
    ActionsGetWorkflowRunRequest,
    ActionsListJobsForRunRequest,
    ActionsListPendingDeploymentsRequest,
    ActionsListRepoSecretsRequest,
    ActionsListRunArtifactsRequest,
    ActionsListRunsForWorkflowRequest,
    ActionsListWorkflowRunsRequest,
    ActionsListWorkflowsRequest,
    ActionsRerunFailedJobsRequest,
    ActionsRerunWorkflowRequest,
    ActionsReviewPendingDeploymentsRequest,
    BranchesListRequest,
    ChecksGetRunRequest,
    ChecksListAnnotationsRequest,
    ChecksListForRefRequest,
    ChecksListSuitesForRefRequest,
    CodeScanningGetAlertRequest,
    CodeScanningListAlertsRequest,
    DependabotGetAlertRequest,
    DependabotListAlertsRequest,
    DependabotUpdateAlertRequest,
    GitBlobsCreateRequest,
    GitBlobsGetRequest,
    GitCommitsCreateRequest,
    GitCommitsGetRequest,
    GitRefsCreateRequest,
    GitRefsDeleteRequest,
    GitRefsGetRequest,
    GitRefsListMatchingRequest,
    GitRefsUpdateRequest,
    GitTagsCreateRequest,
    GitTreesCreateRequest,
    GitTreesGetRequest,
    IssuesAddAssigneesRequest,
    IssuesAddLabelsRequest,
    IssuesAddSubIssueRequest,
    IssuesCreateCommentRequest,
    IssuesCreateLabelRequest,
    IssuesCreateMilestoneRequest,
    IssuesCreateRequest,
    IssuesDeleteCommentRequest,
    IssuesDeleteLabelRequest,
    IssuesGetCommentRequest,
    IssuesGetRequest,
    IssuesListCommentsRequest,
    IssuesListEventsRequest,
    IssuesListForAuthenticatedUserRequest,
    IssuesListForRepoRequest,
    IssuesListLabelsForRepoRequest,
    IssuesListMilestonesRequest,
    IssuesListSubIssuesRequest,
    IssuesListTimelineRequest,
    IssuesLockRequest,
    IssuesRemoveAssigneesRequest,
    IssuesRemoveLabelRequest,
    IssuesSetLabelsRequest,
    IssuesUnlockRequest,
    IssuesUpdateCommentRequest,
    IssuesUpdateLabelRequest,
    IssuesUpdateMilestoneRequest,
    IssuesUpdateRequest,
    NotificationsGetThreadRequest,
    NotificationsListRequest,
    NotificationsMarkReadRequest,
    NotificationsMarkThreadReadRequest,
    PullsCheckMergedRequest,
    PullsCreateRequest,
    PullsCreateReviewCommentRequest,
    PullsCreateReviewRequest,
    PullsDeletePendingReviewRequest,
    PullsDeleteReviewCommentRequest,
    PullsDismissReviewRequest,
    PullsGetDiffRequest,
    PullsGetRequest,
    PullsGetReviewRequest,
    PullsListCommentsForReviewRequest,
    PullsListCommitsRequest,
    PullsListFilesRequest,
    PullsListRequest,
    PullsListRequestedReviewersRequest,
    PullsListReviewCommentsForRepoRequest,
    PullsListReviewCommentsRequest,
    PullsListReviewsRequest,
    PullsMergeRequest,
    PullsRemoveRequestedReviewersRequest,
    PullsReplyToReviewCommentRequest,
    PullsRequestReviewersRequest,
    PullsSubmitReviewRequest,
    PullsUpdateBranchRequest,
    PullsUpdateRequest,
    PullsUpdateReviewCommentRequest,
    PullsUpdateReviewRequest,
    RateLimitGetRequest,
    ReleasesCreateRequest,
    ReleasesDeleteRequest,
    ReleasesGenerateNotesRequest,
    ReleasesGetByTagRequest,
    ReleasesGetLatestRequest,
    ReleasesGetRequest,
    ReleasesListAssetsRequest,
    ReleasesListRequest,
    ReleasesUpdateRequest,
    ReleasesUploadAssetRequest,
    ReposCompareCommitsRequest,
    ReposCreateForkRequest,
    ReposCreateOrUpdateFileRequest,
    ReposDeleteFileRequest,
    ReposGetBranchProtectionRequest,
    ReposGetBranchRequest,
    ReposGetCombinedStatusRequest,
    ReposGetCommitRequest,
    ReposGetContentRequest,
    ReposGetReadmeRequest,
    ReposGetRequest,
    ReposListBranchesForHeadCommitRequest,
    ReposListCommitsRequest,
    ReposListContributorsRequest,
    ReposListForAuthenticatedUserRequest,
    ReposListForOrgRequest,
    ReposListLanguagesRequest,
    ReposListTagsRequest,
    ReposMergeBranchesRequest,
    ReposRenameBranchRequest,
    SearchCodeRequest,
    SearchCommitsRequest,
    SearchIssuesRequest,
    SearchRepositoriesRequest,
    SearchUsersRequest,
    SecretScanningListAlertsRequest,
    UsersGetAuthenticatedRequest,
    compile_tree_deletions,
    unwrap_asset_body,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://api.github.com/"
QUOTA_DOC_URL = "https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api"

# The API version this pack was written against. GitHub dates its REST versions
# and keeps old ones working; pinning is what makes the pack's behaviour a
# property of this file rather than of the day it runs.
API_VERSION = "2022-11-28"

# Sent verbatim on every request, alongside the bearer token the credential
# provider supplies. `User-Agent` is not optional — GitHub answers 403 without
# one. https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": API_VERSION,
    "User-Agent": "charter",
}

# The scopes these tools need on a classic PAT. A fine-grained token instead
# needs read/write on Issues, Pull requests, Contents and Metadata.
SCOPES = ["repo", "read:user"]

# GitHub pages by number: there is no cursor, and a short page is the end
# signal. https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
GITHUB_PAGINATION = Pagination(page_param="page", per_page_param="per_page")

# The search endpoints wrap their results in `items` instead of returning a bare
# array, so the same page-number walk needs to look somewhere else for the list.
# GitHub serves at most the first 1,000 matches of a search, however many
# `total_count` reports. The request schemas already refuse a page past that;
# declaring it here is what makes a *walk* stop cleanly at the wall instead of
# stepping into it. https://docs.github.com/en/rest/search
SEARCH_RESULT_CAP = 1000

SEARCH_PAGINATION = Pagination(
    page_param="page",
    per_page_param="per_page",
    items_field="items",
    max_items=SEARCH_RESULT_CAP,
)

_credentials = DeferredCredentialProvider("github", env_var="GITHUB_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_github = oauth_tool_factory(
    pack="github",
    base_url=BASE_URL,
    provider="github",
    credential_provider=_credentials,
    scopes=SCOPES,
    # GitHub is snake_case on the wire, in both directions.
    body_case="snake",
    query_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=GITHUB_HEADERS,
)

# GitHub serves a pull request in three representations from one endpoint and
# chooses between them by `Accept`. A media type is a constant of the request,
# not an argument of it — a field for it would be the model picking a header
# value — so the diff representation is a second factory with the header pinned,
# and the model chooses between two named tools instead.
# https://docs.github.com/en/rest/using-the-rest-api/getting-started-with-the-rest-api#media-types
DIFF_HEADERS = {**GITHUB_HEADERS, "Accept": "application/vnd.github.diff"}

# Release assets do not go to api.github.com. GitHub serves the upload from
# `uploads.github.com` and wants the file's bytes as the body rather than a JSON
# document, so both facts are declared on their own factory rather than worked
# around per call. `Content-Type` describes the payload and defaults to opaque
# bytes; a host that knows the real media type passes it per call with
# `ainvoke(..., headers={"Content-Type": ...})`.
# https://docs.github.com/en/rest/releases/assets#upload-a-release-asset
UPLOAD_BASE_URL = "https://uploads.github.com/"

UPLOAD_HEADERS = {**GITHUB_HEADERS, "Content-Type": "application/octet-stream"}

_github_uploads = oauth_tool_factory(
    pack="github",
    base_url=UPLOAD_BASE_URL,
    provider="github",
    credential_provider=_credentials,
    scopes=SCOPES,
    body_case="snake",
    query_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=UPLOAD_HEADERS,
    # The body is a file, not a document.
    body_format="raw",
)

_github_diff = oauth_tool_factory(
    pack="github",
    base_url=BASE_URL,
    provider="github",
    credential_provider=_credentials,
    scopes=SCOPES,
    body_case="snake",
    query_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=DIFF_HEADERS,
)

# ---------- issues ----------

issues_list_for_repo = _github(
    name="issues_list_for_repo",
    args_schema=IssuesListForRepoRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/issues",
    description=(
        "List issues in a repository. Note that GitHub counts pull requests as "
        "issues, so results include both; the ones that are pull requests are "
        "marked `is_pull_request`. Filter with `state`, `labels`, `assignee` or "
        "`creator`."
    ),
    action_label="Lists GitHub issues.",
    response_handler=trim_issues,
    pagination_override=GITHUB_PAGINATION,
)

issues_get = _github(
    name="issues_get",
    args_schema=IssuesGetRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/issues/{issue_number}",
    description="Get a single issue by its number, including the full body text.",
    action_label="Reads a GitHub issue.",
    response_handler=trim_issues,
)

issues_create = _github(
    name="issues_create",
    args_schema=IssuesCreateRequest,
    method="POST",
    url_template="repos/{owner}/{repo}/issues",
    description=(
        "Open an issue. Only `title` is required. Labels must already exist on "
        "the repository, and assignees must have push access."
    ),
    action_label="Opens a GitHub issue.",
    response_handler=trim_issues,
)

issues_update = _github(
    name="issues_update",
    args_schema=IssuesUpdateRequest,
    method="PATCH",
    url_template="repos/{owner}/{repo}/issues/{issue_number}",
    description=(
        "Update an issue. Fields not provided are left unchanged. Set `state` to "
        "'closed' to close it, with `state_reason` saying why. Note that `labels` "
        "and `assignees` replace the existing sets rather than adding to them."
    ),
    action_label="Updates a GitHub issue.",
    response_handler=trim_issues,
)

issues_create_comment = _github(
    name="issues_create_comment",
    args_schema=IssuesCreateCommentRequest,
    method="POST",
    url_template="repos/{owner}/{repo}/issues/{issue_number}/comments",
    description=(
        "Post a comment on an issue or pull request. Pull requests take their "
        "own number here — GitHub treats them as issues for commenting."
    ),
    action_label="Comments on GitHub.",
    response_handler=trim_comments,
)

issues_list_comments = _github(
    name="issues_list_comments",
    args_schema=IssuesListCommentsRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/issues/{issue_number}/comments",
    description="List the comments on an issue or pull request, oldest first.",
    action_label="Reads a GitHub discussion.",
    response_handler=trim_comments,
    pagination_override=GITHUB_PAGINATION,
)

# ---------- pull requests ----------

pulls_list = _github(
    name="pulls_list",
    args_schema=PullsListRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/pulls",
    description=(
        "List pull requests. Filter by `state`, by `base` branch, or by `head` in "
        "the form 'user:branch'."
    ),
    action_label="Lists GitHub pull requests.",
    response_handler=trim_pulls,
    pagination_override=GITHUB_PAGINATION,
)

pulls_get = _github(
    name="pulls_get",
    args_schema=PullsGetRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}",
    description=(
        "Get a single pull request, including its mergeability and the counts of "
        "changed files, additions and deletions. These details are only present "
        "on this endpoint, not on `pulls_list`."
    ),
    action_label="Reads a GitHub pull request.",
    response_handler=trim_pulls,
)

pulls_create = _github(
    name="pulls_create",
    args_schema=PullsCreateRequest,
    method="POST",
    url_template="repos/{owner}/{repo}/pulls",
    description=(
        "Open a pull request from `head` into `base`. Provide `title` for a new "
        "pull request, or `issue` to convert an existing issue into one — exactly "
        "one of the two. Both branches must already exist."
    ),
    action_label="Opens a GitHub pull request.",
    response_handler=trim_pulls,
)

pulls_list_files = _github(
    name="pulls_list_files",
    args_schema=PullsListFilesRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}/files",
    description=(
        "List the files a pull request changes, with per-file additions, "
        "deletions and patch text. A large pull request returns a lot of diff: "
        "keep `per_page` small and page through it."
    ),
    action_label="Reads a GitHub diff.",
    response_handler=trim_pull_files,
    pagination_override=GITHUB_PAGINATION,
)

# ---------- repositories ----------

repos_get = _github(
    name="repos_get",
    args_schema=ReposGetRequest,
    method="GET",
    url_template="repos/{owner}/{repo}",
    description="Get a repository's metadata, including its default branch and topics.",
    action_label="Looks up a GitHub repository.",
    response_handler=trim_repos,
)

repos_list_for_authenticated_user = _github(
    name="repos_list_for_authenticated_user",
    args_schema=ReposListForAuthenticatedUserRequest,
    method="GET",
    url_template="user/repos",
    description=(
        "List repositories the authenticated user can access. Note that passing "
        "`type` together with `visibility` or `affiliation` is a 422 from GitHub."
    ),
    action_label="Lists your GitHub repositories.",
    response_handler=trim_repos,
    pagination_override=GITHUB_PAGINATION,
)

repos_get_content = _github(
    name="repos_get_content",
    args_schema=ReposGetContentRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/contents/{path}",
    description=(
        "Read a file, or list a directory. Pass an empty `path` for the "
        "repository root. File contents come back decoded as text."
    ),
    action_label="Reads a GitHub file.",
    response_handler=trim_content,
)

repos_list_commits = _github(
    name="repos_list_commits",
    args_schema=ReposListCommitsRequest,
    method="GET",
    url_template="repos/{owner}/{repo}/commits",
    description=(
        "List commits, newest first. Narrow with `sha` for a branch, `path` for "
        "one file's history, or `since`/`until` for a window."
    ),
    action_label="Reads GitHub history.",
    response_handler=trim_commits,
    pagination_override=GITHUB_PAGINATION,
)

# ---------- search ----------

# Search has its own rate limit — 30 requests per minute against 5,000 per hour
# for the rest of the REST API — and its own response envelope.
search_issues = _github(
    name="search_issues",
    args_schema=SearchIssuesRequest,
    method="GET",
    url_template="search/issues",
    description=(
        "Search issues and pull requests across GitHub with qualifiers, e.g. "
        "'repo:owner/name is:issue is:open label:bug'. Use this when the "
        "repository is unknown or the filter is richer than issues_list_for_repo "
        "supports. Rate limited to 30 requests per minute."
    ),
    action_label="Searches GitHub issues.",
    response_handler=trim_issues,
    pagination_override=SEARCH_PAGINATION,
)

search_repositories = _github(
    name="search_repositories",
    args_schema=SearchRepositoriesRequest,
    method="GET",
    url_template="search/repositories",
    description=(
        "Search repositories with qualifiers, e.g. 'topic:cli language:go "
        "stars:>500'. Rate limited to 30 requests per minute."
    ),
    action_label="Searches GitHub repositories.",
    response_handler=trim_repos,
    pagination_override=SEARCH_PAGINATION,
)

# ---------- account ----------

users_get_authenticated = _github(
    name="users_get_authenticated",
    args_schema=UsersGetAuthenticatedRequest,
    method="GET",
    url_template="user",
    description=(
        "Get the authenticated user. Use this to resolve 'me' to a login before "
        "filtering issues or pull requests by author or assignee."
    ),
    action_label="Checks the GitHub account.",
    response_handler=trim_user,
)

# ---------- pull request lifecycle ----------

pulls_update = _github(
    name="pulls_update", args_schema=PullsUpdateRequest, method="PATCH",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}",
    description=(
        "Update a pull request's title, body, state or base branch. Closing one is "
        "`state: closed`; there is no REST way to change its draft status."
    ),
    action_label="Updates a GitHub pull request.", response_handler=trim_pulls,
)

pulls_merge = _github(
    name="pulls_merge", args_schema=PullsMergeRequest, method="PUT",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}/merge",
    description=(
        "Merge a pull request. A pull request that cannot be merged fails with 405 "
        "rather than reporting it in the body. Pass `sha` to refuse the merge if the "
        "branch has moved since you looked."
    ),
    action_label="Merges a GitHub pull request.",
)

pulls_create_review = _github(
    name="pulls_create_review", args_schema=PullsCreateReviewRequest, method="POST",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews",
    description=(
        "Approve a pull request, request changes on it, or leave a comment. A body "
        "is required for everything except an approval."
    ),
    action_label="Reviews a GitHub pull request.", response_handler=trim_reviews,
)

pulls_list_reviews = _github(
    name="pulls_list_reviews", args_schema=PullsListReviewsRequest, method="GET",
    url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews",
    description="List the reviews left on a pull request, oldest first.",
    action_label="Lists reviews on a GitHub pull request.",
    response_handler=trim_reviews, pagination_override=GITHUB_PAGINATION,
)

pulls_request_reviewers = _github(
    name="pulls_request_reviewers", args_schema=PullsRequestReviewersRequest,
    method="POST", url_template="repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
    description=(
        "Ask users or teams to review a pull request. Users are named by login, "
        "teams by slug."
    ),
    action_label="Requests reviewers on a GitHub pull request.", response_handler=trim_pulls,
)

# ---------- writing code ----------

repos_create_or_update_file = _github(
    name="repos_create_or_update_file", args_schema=ReposCreateOrUpdateFileRequest,
    method="PUT", url_template="repos/{owner}/{repo}/contents/{path}",
    description=(
        "Create a file or replace an existing one, in a single commit. Write the "
        "content as plain text. To replace a file, read it first and pass its `sha`; "
        "without one GitHub treats this as a create and refuses if the path exists."
    ),
    action_label="Commits a file to a GitHub repository.",
    response_handler=trim_written_content,
)

branches_list = _github(
    name="branches_list", args_schema=BranchesListRequest, method="GET",
    url_template="repos/{owner}/{repo}/branches",
    description="List a repository's branches and the commit each one points at.",
    action_label="Lists GitHub branches.",
    response_handler=trim_branches, pagination_override=GITHUB_PAGINATION,
)

git_refs_create = _github(
    name="git_refs_create", args_schema=GitRefsCreateRequest, method="POST",
    url_template="repos/{owner}/{repo}/git/refs",
    description=(
        "Create a branch or tag pointing at an existing commit. The reference must "
        "be fully qualified, like 'refs/heads/my-branch'."
    ),
    action_label="Creates a GitHub branch.",
)

# ---------- actions ----------

actions_list_workflow_runs = _github(
    name="actions_list_workflow_runs", args_schema=ActionsListWorkflowRunsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs",
    description=(
        "List CI runs, most recent first. The single `status` filter matches either "
        "a run's status or its conclusion, so 'in_progress' and 'failure' are both "
        "valid there."
    ),
    action_label="Lists GitHub Actions runs.",
    response_handler=trim_workflow_runs, pagination_override=GITHUB_PAGINATION,
)

actions_rerun_workflow = _github(
    name="actions_rerun_workflow", args_schema=ActionsRerunWorkflowRequest,
    method="POST", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/rerun",
    description="Run a workflow again from the start, including jobs that passed.",
    action_label="Reruns a GitHub Actions workflow.",
)

actions_cancel_workflow_run = _github(
    name="actions_cancel_workflow_run", args_schema=ActionsCancelWorkflowRunRequest,
    method="POST", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/cancel",
    description=(
        "Ask GitHub to cancel a running workflow. It answers once the request is "
        "accepted, not once the run has stopped, so confirm by listing runs again."
    ),
    action_label="Cancels a GitHub Actions run.",
)

search_code = _github(
    name="search_code", args_schema=SearchCodeRequest, method="GET",
    url_template="search/code",
    description=(
        "Search code across GitHub. Only default branches are indexed and only files "
        "under 384 KB. The query needs a real search term, not just qualifiers. This "
        "endpoint allows ten requests per minute and returns at most 1,000 results."
    ),
    action_label="Searches code on GitHub.",
    response_handler=trim_code_search, pagination_override=GITHUB_PAGINATION,
)


# ---------- CI: reading a run ----------

actions_get_workflow_run = _github(
    name="actions_get_workflow_run", args_schema=ActionsGetWorkflowRunRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}",
    description=(
        "Get one workflow run: its status, conclusion, branch, commit and attempt "
        "number. Start here when a run id is known; `actions_list_jobs_for_run` is "
        "the next step when the conclusion is a failure."
    ),
    action_label="Reads a GitHub Actions run.",
    response_handler=trim_workflow_runs,
)

actions_list_jobs_for_run = _github(
    name="actions_list_jobs_for_run", args_schema=ActionsListJobsForRunRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/jobs",
    description=(
        "List a run's jobs, each with its conclusion and its failing steps named. "
        "This is what turns 'the run failed' into 'the `pytest` step of the `test` "
        "job failed', usually without reading a log at all."
    ),
    action_label="Lists GitHub Actions jobs.",
    response_handler=trim_jobs, pagination_override=GITHUB_PAGINATION,
)

actions_get_job = _github(
    name="actions_get_job", args_schema=ActionsGetJobRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/jobs/{job_id}",
    description=(
        "Get one job of a workflow run, with the steps that did not pass named "
        "individually and the runner it ran on."
    ),
    action_label="Reads a GitHub Actions job.",
    response_handler=trim_jobs,
)

actions_download_job_logs = _github(
    name="actions_download_job_logs", args_schema=ActionsDownloadJobLogsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/jobs/{job_id}/logs",
    description=(
        "Read a failing job's log. Returns the last 200 lines plus every line that "
        "looks like an error, with the line numbers and the log's real length — not "
        "the whole file, which is routinely megabytes. Use this after "
        "`actions_list_jobs_for_run` has named the job; try "
        "`checks_list_annotations` first, which is cheaper when the check reported "
        "the failure with a file and a line."
    ),
    action_label="Reads a GitHub Actions job log.",
    response_handler=tail_job_log,
    # GitHub answers 302 to a signed URL that lives one minute. Not following it
    # returns an empty body and no second chance.
    follow_redirects_override=True,
)

actions_download_run_logs = _github(
    name="actions_download_run_logs", args_schema=ActionsDownloadRunLogsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/logs",
    description=(
        "Read a whole run's logs in one call. GitHub sends a ZIP of one text file "
        "per job; this returns each job's tail and error lines. Heavier than "
        "`actions_download_job_logs` — use it when the failing job is not known yet."
    ),
    action_label="Reads GitHub Actions run logs.",
    response_handler=tail_run_log_archive,
    follow_redirects_override=True,
)

actions_rerun_failed_jobs = _github(
    name="actions_rerun_failed_jobs", args_schema=ActionsRerunFailedJobsRequest,
    method="POST", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs",
    description=(
        "Re-run only the failed jobs of a run, and the jobs that depend on them. "
        "The right tool for a flaky test; `actions_rerun_workflow` re-runs "
        "everything, including what already passed."
    ),
    action_label="Retries failed GitHub Actions jobs.",
)

# ---------- CI: workflows ----------

actions_list_workflows = _github(
    name="actions_list_workflows", args_schema=ActionsListWorkflowsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/workflows",
    description=(
        "List the repository's workflows, with the file each one is defined in and "
        "whether it is active or disabled."
    ),
    action_label="Lists GitHub Actions workflows.",
    response_handler=trim_workflows, pagination_override=GITHUB_PAGINATION,
)

actions_get_workflow = _github(
    name="actions_get_workflow", args_schema=ActionsGetWorkflowRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/workflows/{workflow_id}",
    description=(
        "Get one workflow. `workflow_id` accepts the file name — 'ci.yml' — as "
        "well as the numeric id, and the file name is usually the one you have."
    ),
    action_label="Reads a GitHub Actions workflow.",
    response_handler=trim_workflows,
)

actions_create_workflow_dispatch = _github(
    name="actions_create_workflow_dispatch", args_schema=ActionsCreateWorkflowDispatchRequest,
    method="POST", url_template="repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
    description=(
        "Trigger a workflow by hand on a branch or tag. The workflow file must "
        "declare the `workflow_dispatch` trigger itself. GitHub answers with no "
        "body unless `return_run_details` is set, so set it to learn which run "
        "started."
    ),
    action_label="Triggers a GitHub Actions workflow.",
)

actions_list_runs_for_workflow = _github(
    name="actions_list_runs_for_workflow", args_schema=ActionsListRunsForWorkflowRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs",
    description=(
        "List the runs of one workflow, most recent first — 'is this pipeline "
        "green', rather than 'is anything red'. The same single `status` filter as "
        "`actions_list_workflow_runs`, which matches a status or a conclusion."
    ),
    action_label="Lists runs of a GitHub Actions workflow.",
    response_handler=trim_workflow_runs, pagination_override=GITHUB_PAGINATION,
)

# ---------- CI: artifacts and cost ----------

actions_list_run_artifacts = _github(
    name="actions_list_run_artifacts", args_schema=ActionsListRunArtifactsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
    description=(
        "List what a run uploaded, with each artifact's size and whether it has "
        "expired. Read `expired` before downloading: an expired artifact still has "
        "a record here and answers 410 at the download."
    ),
    action_label="Lists GitHub Actions artifacts.",
    response_handler=trim_artifacts, pagination_override=GITHUB_PAGINATION,
)

actions_get_artifact = _github(
    name="actions_get_artifact", args_schema=ActionsGetArtifactRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/artifacts/{artifact_id}",
    description="Get one artifact's name, size, expiry and digest.",
    action_label="Reads a GitHub Actions artifact.",
    response_handler=trim_artifacts,
)

actions_download_artifact = _github(
    name="actions_download_artifact", args_schema=ActionsDownloadArtifactRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip",
    description=(
        "Download an artifact and report what is in it: every entry's name and "
        "size, plus the contents of the small text files — a JUnit report or a "
        "coverage summary comes back readable. Large or binary entries are listed "
        "and not inlined. An expired artifact answers 410."
    ),
    action_label="Downloads a GitHub Actions artifact.",
    response_handler=read_artifact_archive,
    follow_redirects_override=True,
)

actions_get_run_usage = _github(
    name="actions_get_run_usage", args_schema=ActionsGetRunUsageRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/timing",
    description=(
        "Get a run's total run time and its billable milliseconds per runner "
        "operating system. Billable minutes apply only to private repositories on "
        "GitHub-hosted runners. GitHub has this endpoint closing down."
    ),
    action_label="Reads GitHub Actions run timing.",
    response_handler=trim_run_usage,
)

# ---------- CI: deployments waiting on a human ----------

actions_list_pending_deployments = _github(
    name="actions_list_pending_deployments", args_schema=ActionsListPendingDeploymentsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments",
    description=(
        "List the environments a run is waiting on for approval, and who can "
        "approve them. This is where a run sits when it is neither failing nor "
        "progressing."
    ),
    action_label="Lists pending GitHub deployments.",
    response_handler=trim_pending_deployments,
)

actions_review_pending_deployments = _github(
    name="actions_review_pending_deployments", args_schema=ActionsReviewPendingDeploymentsRequest,
    method="POST", url_template="repos/{owner}/{repo}/actions/runs/{run_id}/pending_deployments",
    description=(
        "Approve or reject a run's pending deployments. Takes the environment ids "
        "from `actions_list_pending_deployments`. A comment is required by GitHub, "
        "not optional."
    ),
    action_label="Approves or rejects a GitHub deployment.",
)

actions_list_repo_secrets = _github(
    name="actions_list_repo_secrets", args_schema=ActionsListRepoSecretsRequest,
    method="GET", url_template="repos/{owner}/{repo}/actions/secrets",
    description=(
        "List the names of the repository's Actions secrets, with when each was "
        "created and last changed. Values are never returned by this endpoint — "
        "GitHub does not include them, encrypted or otherwise. Use it to check "
        "whether a workflow's secret exists before blaming the workflow."
    ),
    action_label="Lists GitHub Actions secret names.",
    response_handler=trim_secret_names, pagination_override=GITHUB_PAGINATION,
)

# ---------- CI: checks and commit status ----------

checks_list_for_ref = _github(
    name="checks_list_for_ref", args_schema=ChecksListForRefRequest,
    method="GET", url_template="repos/{owner}/{repo}/commits/{ref}/check-runs",
    description=(
        "List the check runs reported against a commit, branch or tag — every CI "
        "provider that reports as a GitHub App, Actions included. `ref` takes a "
        "SHA, 'heads/BRANCH' or 'tags/TAG'. The `status` filter takes a status "
        "only: a failure is `status: completed` plus a `conclusion` of 'failure'."
    ),
    action_label="Lists GitHub check runs.",
    response_handler=trim_check_runs, pagination_override=GITHUB_PAGINATION,
)

checks_get_run = _github(
    name="checks_get_run", args_schema=ChecksGetRunRequest,
    method="GET", url_template="repos/{owner}/{repo}/check-runs/{check_run_id}",
    description=(
        "Get one check run, with its summary text and how many annotations it "
        "produced. A non-zero annotation count means `checks_list_annotations` "
        "will name the files and lines that failed."
    ),
    action_label="Reads a GitHub check run.",
    response_handler=trim_check_runs,
)

checks_list_annotations = _github(
    name="checks_list_annotations", args_schema=ChecksListAnnotationsRequest,
    method="GET", url_template="repos/{owner}/{repo}/check-runs/{check_run_id}/annotations",
    description=(
        "List a check run's annotations: each failure with the file, the line "
        "range, a level and a message, already extracted by whoever ran the check. "
        "The cheapest way to find out why a build is red — try this before "
        "downloading any log. GitHub returns at most 50 per page."
    ),
    action_label="Reads GitHub check annotations.",
    response_handler=trim_annotations, pagination_override=GITHUB_PAGINATION,
)

checks_list_suites_for_ref = _github(
    name="checks_list_suites_for_ref", args_schema=ChecksListSuitesForRefRequest,
    method="GET", url_template="repos/{owner}/{repo}/commits/{ref}/check-suites",
    description=(
        "List the check suites for a commit, branch or tag — one suite per app "
        "that reported. Coarser than `checks_list_for_ref`, and the way past its "
        "1,000-suite ceiling on a very busy reference."
    ),
    action_label="Lists GitHub check suites.",
    response_handler=trim_check_suites, pagination_override=GITHUB_PAGINATION,
)

repos_get_combined_status = _github(
    name="repos_get_combined_status", args_schema=ReposGetCombinedStatusRequest,
    method="GET", url_template="repos/{owner}/{repo}/commits/{ref}/status",
    description=(
        "Get the single rolled-up state of a commit — 'success', 'failure', "
        "'pending' or 'error' — plus one line per reporting context. This covers "
        "commit statuses only, not check runs: a repository that uses only Actions "
        "reports 'pending' here with no statuses, and its real answer is in "
        "`checks_list_for_ref`."
    ),
    action_label="Checks a GitHub commit's status.",
    response_handler=trim_combined_status, pagination_override=GITHUB_PAGINATION,
)


# ---------- code review: comments on a line ----------

pulls_create_review_comment = _github(
    name="pulls_create_review_comment", args_schema=PullsCreateReviewCommentRequest,
    method="POST", url_template="repos/{owner}/{repo}/pulls/{pull_number}/comments",
    description=(
        "Leave a comment on a specific line of a pull request's diff — the thing "
        "reviewing is made of. Needs the file `path`, the `line` in the diff, and "
        "`commit_id` set to the pull request's current head SHA. Use `side: LEFT` "
        "for a deleted line and `RIGHT` for an added or context line; add "
        "`start_line` to span a range. `pulls_create_review` leaves a verdict on "
        "the whole change instead."
    ),
    action_label="Comments on a line of a GitHub diff.",
    response_handler=trim_review_comments,
)

pulls_list_review_comments = _github(
    name="pulls_list_review_comments", args_schema=PullsListReviewCommentsRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/comments",
    description=(
        "List the line comments on a pull request, each with the file and line it "
        "sits on. A comment whose line has since changed comes back marked "
        "`outdated`."
    ),
    action_label="Reads GitHub review comments.",
    response_handler=trim_review_comments, pagination_override=GITHUB_PAGINATION,
)

pulls_reply_to_review_comment = _github(
    name="pulls_reply_to_review_comment", args_schema=PullsReplyToReviewCommentRequest,
    method="POST", url_template="repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_id}/replies",
    description=(
        "Reply to an existing review comment, continuing its thread. `comment_id` "
        "must be a top-level comment: GitHub does not support replies to replies."
    ),
    action_label="Replies to a GitHub review comment.",
    response_handler=trim_review_comments,
)

pulls_update_review_comment = _github(
    name="pulls_update_review_comment", args_schema=PullsUpdateReviewCommentRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/pulls/comments/{comment_id}",
    description="Edit the text of a review comment. Its placement does not change.",
    action_label="Edits a GitHub review comment.",
    response_handler=trim_review_comments,
)

pulls_delete_review_comment = _github(
    name="pulls_delete_review_comment", args_schema=PullsDeleteReviewCommentRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/pulls/comments/{comment_id}",
    description="Delete a review comment. There is no undo.",
    action_label="Deletes a GitHub review comment.",
)

pulls_list_review_comments_for_repo = _github(
    name="pulls_list_review_comments_for_repo", args_schema=PullsListReviewCommentsForRepoRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/comments",
    description=(
        "List the line comments across every pull request in a repository. Use "
        "`since` to read what has been said lately without knowing which pull "
        "requests to look at."
    ),
    action_label="Reads GitHub review comments across a repository.",
    response_handler=trim_review_comments, pagination_override=GITHUB_PAGINATION,
)

# ---------- code review: the review lifecycle ----------

pulls_get_review = _github(
    name="pulls_get_review", args_schema=PullsGetReviewRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}",
    description="Get one review of a pull request, with its state and summary text.",
    action_label="Reads a GitHub review.",
    response_handler=trim_reviews,
)

pulls_submit_review = _github(
    name="pulls_submit_review", args_schema=PullsSubmitReviewRequest,
    method="POST", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/events",
    description=(
        "Submit a pending review as an approval, a request for changes, or a "
        "comment. A review stays invisible until this lands. Only needed for a "
        "review left pending — `pulls_create_review` submits in one step."
    ),
    action_label="Submits a GitHub review.",
    response_handler=trim_reviews,
)

pulls_update_review = _github(
    name="pulls_update_review", args_schema=PullsUpdateReviewRequest,
    method="PUT", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}",
    description=(
        "Edit a review's summary text. This changes the words, not the verdict: an "
        "approval stays an approval. To withdraw one, use `pulls_dismiss_review`."
    ),
    action_label="Edits a GitHub review.",
    response_handler=trim_reviews,
)

pulls_dismiss_review = _github(
    name="pulls_dismiss_review", args_schema=PullsDismissReviewRequest,
    method="PUT", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/dismissals",
    description=(
        "Dismiss a review so it stops blocking the pull request, with a message "
        "saying why. On a protected branch this needs administrator rights."
    ),
    action_label="Dismisses a GitHub review.",
    response_handler=trim_reviews,
)

pulls_delete_pending_review = _github(
    name="pulls_delete_pending_review", args_schema=PullsDeletePendingReviewRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}",
    description=(
        "Discard a review that was never submitted. Only a pending review can be "
        "deleted; a submitted one is dismissed instead."
    ),
    action_label="Discards a pending GitHub review.",
    response_handler=trim_reviews,
)

pulls_list_comments_for_review = _github(
    name="pulls_list_comments_for_review", args_schema=PullsListCommentsForReviewRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/reviews/{review_id}/comments",
    description="List the line comments that belong to one review, rather than to the pull request as a whole.",
    action_label="Reads the comments of a GitHub review.",
    response_handler=trim_review_comments, pagination_override=GITHUB_PAGINATION,
)

# ---------- code review: the rest of a pull request's state ----------

pulls_get_diff = _github_diff(
    name="pulls_get_diff", args_schema=PullsGetDiffRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}",
    description=(
        "Get a pull request's whole change as a unified diff, in one call. The "
        "same endpoint as `pulls_get` asked for a different representation. Use it "
        "to read a change end to end; use `pulls_list_files` when the change is "
        "large enough to need paging, since this has no way to ask for less."
    ),
    action_label="Reads a GitHub pull request diff.",
    response_handler=passthrough_diff,
)

pulls_list_commits = _github(
    name="pulls_list_commits", args_schema=PullsListCommitsRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/commits",
    description=(
        "List the commits on a pull request. GitHub caps this at 250 however you "
        "page it; a longer branch needs `repos_list_commits`."
    ),
    action_label="Lists commits on a GitHub pull request.",
    response_handler=trim_commits, pagination_override=GITHUB_PAGINATION,
)

pulls_update_branch = _github(
    name="pulls_update_branch", args_schema=PullsUpdateBranchRequest,
    method="PUT", url_template="repos/{owner}/{repo}/pulls/{pull_number}/update-branch",
    description=(
        "Bring a pull request's branch up to date by merging the base branch into "
        "it — the fix for a 'this branch is out of date' block. The 202 means the "
        "job was accepted, not that the branch has moved; read the pull request "
        "again to confirm. Pass `expected_head_sha` to refuse if it has moved "
        "since you looked."
    ),
    action_label="Updates a GitHub pull request branch.",
)

pulls_check_merged = _github(
    name="pulls_check_merged", args_schema=PullsCheckMergedRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/merge",
    description=(
        "Ask whether a pull request has been merged. This endpoint has no body: "
        "GitHub answers 204 for merged and 404 for not, so this returns "
        "`{merged: true}` or raises. `pulls_get` reports the same thing in a "
        "readable field and is usually the better call."
    ),
    action_label="Checks whether a GitHub pull request is merged.",
    response_handler=trim_merged_check,
)

pulls_list_requested_reviewers = _github(
    name="pulls_list_requested_reviewers", args_schema=PullsListRequestedReviewersRequest,
    method="GET", url_template="repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
    description=(
        "List who has been asked to review and has not answered yet. A reviewer "
        "drops off this list once they submit, so an empty list means nobody is "
        "outstanding — not that nobody was asked."
    ),
    action_label="Lists requested GitHub reviewers.",
    response_handler=trim_requested_reviewers,
)

pulls_remove_requested_reviewers = _github(
    name="pulls_remove_requested_reviewers", args_schema=PullsRemoveRequestedReviewersRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers",
    description=(
        "Withdraw a review request from users or teams. `reviewers` is required by "
        "GitHub even when only teams are being removed — pass an empty list for "
        "that case."
    ),
    action_label="Withdraws a GitHub review request.",
    response_handler=trim_pulls,
)


# ---------- authoring a change: the Git object store ----------
#
# `repos_create_or_update_file` is one file per commit. These four are how a
# change across several files becomes one commit — build a tree on the current
# one, commit it, move the branch — and nothing is visible until the last step.

git_refs_get = _github(
    name="git_refs_get", args_schema=GitRefsGetRequest,
    method="GET", url_template="repos/{owner}/{repo}/git/ref/{ref}",
    description=(
        "Get a reference and the commit SHA it points at — how you read a branch's "
        "current head before building on it. `ref` is `heads/main` or "
        "`tags/v1.0`, without the `refs/` prefix."
    ),
    action_label="Reads a GitHub branch reference.",
    response_handler=trim_git_refs,
)

git_refs_update = _github(
    name="git_refs_update", args_schema=GitRefsUpdateRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/git/refs/{ref}",
    description=(
        "Point a branch or tag at a different commit — the step that makes a "
        "commit built with `git_trees_create` and `git_commits_create` visible. "
        "Refuses a non-fast-forward unless `force` is set, which is what stops "
        "this overwriting work you have not seen."
    ),
    action_label="Moves a GitHub branch.",
    response_handler=trim_git_refs,
)

git_refs_delete = _github(
    name="git_refs_delete", args_schema=GitRefsDeleteRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/git/refs/{ref}",
    description=(
        "Delete a branch or tag, by reference. `heads/my-branch`, without the "
        "`refs/` prefix. GitHub refuses to delete the default branch."
    ),
    action_label="Deletes a GitHub branch.",
)

git_refs_list_matching = _github(
    name="git_refs_list_matching", args_schema=GitRefsListMatchingRequest,
    method="GET", url_template="repos/{owner}/{repo}/git/matching-refs/{ref}",
    description=(
        "List every reference under a prefix — `heads/` for all branches, "
        "`tags/v2` for the v2 tags. A prefix match, so `heads/feat` also returns "
        "`heads/feature-x`."
    ),
    action_label="Lists GitHub references.",
    response_handler=trim_git_refs,
)

git_blobs_create = _github(
    name="git_blobs_create", args_schema=GitBlobsCreateRequest,
    method="POST", url_template="repos/{owner}/{repo}/git/blobs",
    description=(
        "Write a file's content into the object store and get its SHA back, "
        "without committing anything. Needed for binary content, which a tree "
        "entry cannot carry inline; for text, putting `content` straight on the "
        "tree entry is one call fewer. Up to 100 MB."
    ),
    action_label="Uploads a file to GitHub's object store.",
)

git_blobs_get = _github(
    name="git_blobs_get", args_schema=GitBlobsGetRequest,
    method="GET", url_template="repos/{owner}/{repo}/git/blobs/{file_sha}",
    description=(
        "Read a blob by SHA, decoded to text. Says so plainly instead when the "
        "blob is binary or over GitHub's 1MB ceiling for this endpoint."
    ),
    action_label="Reads a GitHub blob.",
    response_handler=trim_blob,
)

git_trees_create = _github(
    name="git_trees_create", args_schema=GitTreesCreateRequest,
    method="POST", url_template="repos/{owner}/{repo}/git/trees",
    description=(
        "Build one commit's worth of changes across any number of files. Pass "
        "`base_tree` as the current commit's tree SHA and list only what changed; "
        "each entry takes either `content` (new text) or `sha` (an existing "
        "blob), and `delete: true` removes a path. Omitting `base_tree` builds a "
        "tree containing *only* these entries, which commits as a deletion of "
        "everything else."
    ),
    action_label="Builds a GitHub tree.",
    # `delete: true` has to reach the wire as a present-and-null `sha`, which a
    # Pydantic dump cannot produce. See compile_tree_deletions.
    build_request=compile_tree_deletions,
    response_handler=trim_tree,
)

git_trees_get = _github(
    name="git_trees_get", args_schema=GitTreesGetRequest,
    method="GET", url_template="repos/{owner}/{repo}/git/trees/{tree_sha}",
    description=(
        "Read a tree: every path in it with its mode and object SHA. Accepts a "
        "branch name as well as a SHA. Set `recursive` to '1' to walk subtrees — "
        "check `truncated` on the way back, because GitHub caps a recursive read "
        "at 100,000 entries and 7 MB."
    ),
    action_label="Reads a GitHub tree.",
    response_handler=trim_tree,
)

git_commits_create = _github(
    name="git_commits_create", args_schema=GitCommitsCreateRequest,
    method="POST", url_template="repos/{owner}/{repo}/git/commits",
    description=(
        "Create a commit pointing at a tree. `parents` is required and is "
        "normally the branch's current head — an omitted `parents` is a root "
        "commit with no history, which the branch update afterwards then "
        "refuses. Nothing is visible until `git_refs_update` moves a branch onto "
        "the SHA this returns."
    ),
    action_label="Creates a GitHub commit.",
    response_handler=trim_git_commits,
)

git_commits_get = _github(
    name="git_commits_get", args_schema=GitCommitsGetRequest,
    method="GET", url_template="repos/{owner}/{repo}/git/commits/{commit_sha}",
    description=(
        "Read a commit object: its message, its tree SHA and its parents. "
        "`repos_get_commit` is the richer view, with the diff and the file list."
    ),
    action_label="Reads a GitHub commit object.",
    response_handler=trim_git_commits,
)

git_tags_create = _github(
    name="git_tags_create", args_schema=GitTagsCreateRequest,
    method="POST", url_template="repos/{owner}/{repo}/git/tags",
    description=(
        "Create an annotated tag object. This does not create the tag: follow it "
        "with `git_refs_create` pointing `refs/tags/NAME` at the SHA returned "
        "here. A lightweight tag needs only that second call."
    ),
    action_label="Creates a GitHub tag object.",
)

# ---------- authoring a change: history and branches ----------

repos_get_commit = _github(
    name="repos_get_commit", args_schema=ReposGetCommitRequest,
    method="GET", url_template="repos/{owner}/{repo}/commits/{ref}",
    description=(
        "Get one commit with its diff and per-file line counts. Note that "
        "`page`/`per_page` here page the *files* of the one commit, not a list of "
        "commits — GitHub stops at 300 files per page and 3,000 in total."
    ),
    action_label="Reads a GitHub commit.",
    response_handler=trim_commits, pagination_override=GITHUB_PAGINATION,
)

repos_compare_commits = _github(
    name="repos_compare_commits", args_schema=ReposCompareCommitsRequest,
    method="GET", url_template="repos/{owner}/{repo}/compare/{basehead}",
    description=(
        "Compare two refs and get what is in one and not the other: the status, "
        "how far ahead or behind, the commits and the changed files. `basehead` "
        "is one string, 'main...my-feature', with three dots. Across forks, "
        "prefix each side with its owner."
    ),
    action_label="Compares GitHub commits.",
    response_handler=trim_comparison, pagination_override=GITHUB_PAGINATION,
)

repos_delete_file = _github(
    name="repos_delete_file", args_schema=ReposDeleteFileRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/contents/{path}",
    description=(
        "Delete a file in a commit of its own. Needs the file's blob `sha`, so "
        "read it first. To remove several files in one commit, use "
        "`git_trees_create` with `delete: true` entries instead."
    ),
    action_label="Deletes a file from a GitHub repository.",
    response_handler=trim_written_content,
)

repos_merge_branches = _github(
    name="repos_merge_branches", args_schema=ReposMergeBranchesRequest,
    method="POST", url_template="repos/{owner}/{repo}/merges",
    description=(
        "Merge one branch into another directly, without opening a pull request. "
        "Answers with the merge commit, an empty object when the base already "
        "contains the head, and 409 on a conflict."
    ),
    action_label="Merges a GitHub branch.",
    response_handler=trim_commits,
)

repos_get_branch = _github(
    name="repos_get_branch", args_schema=ReposGetBranchRequest,
    method="GET", url_template="repos/{owner}/{repo}/branches/{branch}",
    description="Get one branch: its head commit and whether it is protected.",
    action_label="Reads a GitHub branch.",
    response_handler=trim_branches,
)

repos_rename_branch = _github(
    name="repos_rename_branch", args_schema=ReposRenameBranchRequest,
    method="POST", url_template="repos/{owner}/{repo}/branches/{branch}/rename",
    description=(
        "Rename a branch. GitHub answers immediately but finishes in the "
        "background, and pushes to the old name fail while it is running. "
        "Renaming the default branch needs admin permission."
    ),
    action_label="Renames a GitHub branch.",
    response_handler=trim_branches,
)

repos_get_branch_protection = _github(
    name="repos_get_branch_protection", args_schema=ReposGetBranchProtectionRequest,
    method="GET", url_template="repos/{owner}/{repo}/branches/{branch}/protection",
    description=(
        "Read a branch's protection rules — required checks, required reviews, "
        "linear history — before attempting a write that they would refuse. A 404 "
        "means either no such branch or no protection on it; GitHub does not "
        "distinguish them."
    ),
    action_label="Reads GitHub branch protection.",
    response_handler=trim_branch_protection,
)

repos_list_branches_for_head_commit = _github(
    name="repos_list_branches_for_head_commit", args_schema=ReposListBranchesForHeadCommitRequest,
    method="GET", url_template="repos/{owner}/{repo}/commits/{commit_sha}/branches-where-head",
    description=(
        "List the branches whose head is this exact commit — 'has this landed, "
        "and where', asked from the commit's side."
    ),
    action_label="Finds GitHub branches at a commit.",
    response_handler=trim_branches,
)

repos_get_readme = _github(
    name="repos_get_readme", args_schema=ReposGetReadmeRequest,
    method="GET", url_template="repos/{owner}/{repo}/readme",
    description=(
        "Get the repository's README, decoded to text. GitHub picks the preferred "
        "file itself across the spellings a repository might use, which saves "
        "guessing at `repos_get_content`."
    ),
    action_label="Reads a GitHub README.",
    response_handler=trim_content,
)

repos_list_tags = _github(
    name="repos_list_tags", args_schema=ReposListTagsRequest,
    method="GET", url_template="repos/{owner}/{repo}/tags",
    description="List a repository's tags with the commit each points at, newest first.",
    action_label="Lists GitHub tags.",
    response_handler=trim_tags, pagination_override=GITHUB_PAGINATION,
)

repos_create_fork = _github(
    name="repos_create_fork", args_schema=ReposCreateForkRequest,
    method="POST", url_template="repos/{owner}/{repo}/forks",
    description=(
        "Fork a repository, optionally into an organization or under a new name. "
        "GitHub forks asynchronously: the repository record comes back at once, "
        "but its git objects may not be readable for a short while."
    ),
    action_label="Forks a GitHub repository.",
    response_handler=trim_repos,
)


# ---------- issue metadata: labels ----------

issues_list_labels_for_repo = _github(
    name="issues_list_labels_for_repo", args_schema=IssuesListLabelsForRepoRequest,
    method="GET", url_template="repos/{owner}/{repo}/labels",
    description=(
        "List the labels a repository defines, with their colours and "
        "descriptions. Worth reading before labelling: a name that does not exist "
        "yet is a 422."
    ),
    action_label="Lists GitHub labels.",
    response_handler=trim_labels, pagination_override=GITHUB_PAGINATION,
)

issues_add_labels = _github(
    name="issues_add_labels", args_schema=IssuesAddLabelsRequest,
    method="POST", url_template="repos/{owner}/{repo}/issues/{issue_number}/labels",
    description=(
        "Add labels to an issue, keeping the ones already on it. Use this rather "
        "than `issues_update` to label something: `issues_update` *replaces* the "
        "whole set, so adding one label there removes the rest."
    ),
    action_label="Labels a GitHub issue.",
    response_handler=trim_labels,
)

issues_set_labels = _github(
    name="issues_set_labels", args_schema=IssuesSetLabelsRequest,
    method="PUT", url_template="repos/{owner}/{repo}/issues/{issue_number}/labels",
    description=(
        "Replace an issue's labels with exactly this set, dropping any others. An "
        "empty list removes every label."
    ),
    action_label="Sets the labels on a GitHub issue.",
    response_handler=trim_labels,
)

issues_remove_label = _github(
    name="issues_remove_label", args_schema=IssuesRemoveLabelRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/issues/{issue_number}/labels/{name}",
    description="Take one label off an issue, leaving the others in place.",
    action_label="Removes a label from a GitHub issue.",
    response_handler=trim_labels,
)

issues_create_label = _github(
    name="issues_create_label", args_schema=IssuesCreateLabelRequest,
    method="POST", url_template="repos/{owner}/{repo}/labels",
    description=(
        "Define a new label on the repository. `color` is a six-digit hex code "
        "without the leading '#'."
    ),
    action_label="Creates a GitHub label.",
    response_handler=trim_labels,
)

issues_update_label = _github(
    name="issues_update_label", args_schema=IssuesUpdateLabelRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/labels/{name}",
    description=(
        "Rename a label or change its colour, description, or archived state. A "
        "rename applies everywhere the label is used."
    ),
    action_label="Updates a GitHub label.",
    response_handler=trim_labels,
)

issues_delete_label = _github(
    name="issues_delete_label", args_schema=IssuesDeleteLabelRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/labels/{name}",
    description="Delete a label, removing it from every issue that carries it.",
    action_label="Deletes a GitHub label.",
)

# ---------- issue metadata: assignees and milestones ----------

issues_add_assignees = _github(
    name="issues_add_assignees", args_schema=IssuesAddAssigneesRequest,
    method="POST", url_template="repos/{owner}/{repo}/issues/{issue_number}/assignees",
    description=(
        "Assign people to an issue, keeping whoever is already assigned. At most "
        "ten. A user without push access is silently ignored rather than "
        "refused — check the assignees on the way back against what you sent."
    ),
    action_label="Assigns a GitHub issue.",
    response_handler=trim_issues,
)

issues_remove_assignees = _github(
    name="issues_remove_assignees", args_schema=IssuesRemoveAssigneesRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/issues/{issue_number}/assignees",
    description="Unassign people from an issue.",
    action_label="Unassigns a GitHub issue.",
    response_handler=trim_issues,
)

issues_list_milestones = _github(
    name="issues_list_milestones", args_schema=IssuesListMilestonesRequest,
    method="GET", url_template="repos/{owner}/{repo}/milestones",
    description=(
        "List a repository's milestones, with how many issues in each are open "
        "and closed. Sort by `completeness` to see what is nearly done."
    ),
    action_label="Lists GitHub milestones.",
    response_handler=trim_milestones, pagination_override=GITHUB_PAGINATION,
)

issues_create_milestone = _github(
    name="issues_create_milestone", args_schema=IssuesCreateMilestoneRequest,
    method="POST", url_template="repos/{owner}/{repo}/milestones",
    description="Create a milestone. Only `title` is required.",
    action_label="Creates a GitHub milestone.",
    response_handler=trim_milestones,
)

issues_update_milestone = _github(
    name="issues_update_milestone", args_schema=IssuesUpdateMilestoneRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/milestones/{milestone_number}",
    description="Update a milestone. Anything omitted is left unchanged.",
    action_label="Updates a GitHub milestone.",
    response_handler=trim_milestones,
)

# ---------- issue metadata: editing what was said ----------

issues_get_comment = _github(
    name="issues_get_comment", args_schema=IssuesGetCommentRequest,
    method="GET", url_template="repos/{owner}/{repo}/issues/comments/{comment_id}",
    description=(
        "Get one issue comment by its id — the `id` from `issues_list_comments`, "
        "not the issue number."
    ),
    action_label="Reads a GitHub comment.",
    response_handler=trim_comments,
)

issues_update_comment = _github(
    name="issues_update_comment", args_schema=IssuesUpdateCommentRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/issues/comments/{comment_id}",
    description=(
        "Edit an issue comment's text. This is how an agent corrects or extends "
        "something it already posted, rather than posting again."
    ),
    action_label="Edits a GitHub comment.",
    response_handler=trim_comments,
)

issues_delete_comment = _github(
    name="issues_delete_comment", args_schema=IssuesDeleteCommentRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/issues/comments/{comment_id}",
    description="Delete an issue comment. There is no undo.",
    action_label="Deletes a GitHub comment.",
)

# ---------- issue metadata: history and locking ----------

issues_list_timeline = _github(
    name="issues_list_timeline", args_schema=IssuesListTimelineRequest,
    method="GET", url_template="repos/{owner}/{repo}/issues/{issue_number}/timeline",
    description=(
        "List everything that has happened to an issue in order — comments, "
        "labels, assignments, cross-references, the commits that mentioned it. "
        "The way to find out what has already been tried before trying it again. "
        "Use `exclude` to leave out noisy event kinds."
    ),
    action_label="Reads a GitHub issue's history.",
    response_handler=trim_issue_events, pagination_override=GITHUB_PAGINATION,
)

issues_list_events = _github(
    name="issues_list_events", args_schema=IssuesListEventsRequest,
    method="GET", url_template="repos/{owner}/{repo}/issues/{issue_number}/events",
    description=(
        "List an issue's state changes — labelled, assigned, closed, renamed — "
        "without the comments. The narrow form of `issues_list_timeline`."
    ),
    action_label="Lists GitHub issue events.",
    response_handler=trim_issue_events, pagination_override=GITHUB_PAGINATION,
)

issues_lock = _github(
    name="issues_lock", args_schema=IssuesLockRequest,
    method="PUT", url_template="repos/{owner}/{repo}/issues/{issue_number}/lock",
    description=(
        "Lock an issue or pull request's conversation. Needs push access. If "
        "`lock_reason` is given it must be one of 'off-topic', 'too heated', "
        "'resolved' or 'spam' — anything else is refused."
    ),
    action_label="Locks a GitHub conversation.",
)

issues_unlock = _github(
    name="issues_unlock", args_schema=IssuesUnlockRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/issues/{issue_number}/lock",
    description="Unlock a conversation that was locked.",
    action_label="Unlocks a GitHub conversation.",
)

issues_list_for_authenticated_user = _github(
    name="issues_list_for_authenticated_user", args_schema=IssuesListForAuthenticatedUserRequest,
    method="GET", url_template="issues",
    description=(
        "List the authenticated user's issues across every repository they can "
        "see — the agent's own queue. `filter` chooses between what is assigned "
        "to you, what you opened, what mentions you and everything visible. Pull "
        "requests appear here too, marked `is_pull_request`."
    ),
    action_label="Lists your GitHub issues.",
    response_handler=trim_issues, pagination_override=GITHUB_PAGINATION,
)

issues_list_sub_issues = _github(
    name="issues_list_sub_issues", args_schema=IssuesListSubIssuesRequest,
    method="GET", url_template="repos/{owner}/{repo}/issues/{issue_number}/sub_issues",
    description="List the sub-issues of an issue — how a tracking issue's pieces are found.",
    action_label="Lists GitHub sub-issues.",
    response_handler=trim_issues, pagination_override=GITHUB_PAGINATION,
)

issues_add_sub_issue = _github(
    name="issues_add_sub_issue", args_schema=IssuesAddSubIssueRequest,
    method="POST", url_template="repos/{owner}/{repo}/issues/{issue_number}/sub_issues",
    description=(
        "Attach an existing issue to this one as a sub-issue. `sub_issue_id` is "
        "the issue's `id` field, not the number shown in its URL — the two are "
        "different integers. Set `replace_parent` to move an issue that already "
        "has a parent."
    ),
    action_label="Adds a GitHub sub-issue.",
    response_handler=trim_issues,
)


# ---------- releases ----------

releases_list = _github(
    name="releases_list", args_schema=ReleasesListRequest,
    method="GET", url_template="repos/{owner}/{repo}/releases",
    description=(
        "List a repository's releases, newest first. Tags that were never made "
        "into releases do not appear here — `repos_list_tags` has those. Drafts "
        "are visible only with push access."
    ),
    action_label="Lists GitHub releases.",
    response_handler=trim_releases, pagination_override=GITHUB_PAGINATION,
)

releases_get = _github(
    name="releases_get", args_schema=ReleasesGetRequest,
    method="GET", url_template="repos/{owner}/{repo}/releases/{release_id}",
    description="Get one release by its numeric id, with its notes and its assets.",
    action_label="Reads a GitHub release.",
    response_handler=trim_releases,
)

releases_get_latest = _github(
    name="releases_get_latest", args_schema=ReleasesGetLatestRequest,
    method="GET", url_template="repos/{owner}/{repo}/releases/latest",
    description=(
        "Get the latest published release — GitHub's definition, meaning the most "
        "recent release that is neither a draft nor a prerelease. Not simply the "
        "newest one."
    ),
    action_label="Reads the latest GitHub release.",
    response_handler=trim_releases,
)

releases_get_by_tag = _github(
    name="releases_get_by_tag", args_schema=ReleasesGetByTagRequest,
    method="GET", url_template="repos/{owner}/{repo}/releases/tags/{tag}",
    description=(
        "Get a release by its tag name, such as 'v1.4.0'. Usually more useful "
        "than `releases_get`, since a version string is something you already "
        "have and a release id is not."
    ),
    action_label="Reads a GitHub release by tag.",
    response_handler=trim_releases,
)

releases_create = _github(
    name="releases_create", args_schema=ReleasesCreateRequest,
    method="POST", url_template="repos/{owner}/{repo}/releases",
    description=(
        "Publish a release, creating its tag if it does not exist. Set "
        "`generate_release_notes` to have GitHub write the changelog from the "
        "merged pull requests since the last release. `make_latest` is a string "
        "— 'true', 'false' or 'legacy' — not a boolean."
    ),
    action_label="Publishes a GitHub release.",
    response_handler=trim_releases,
)

releases_update = _github(
    name="releases_update", args_schema=ReleasesUpdateRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/releases/{release_id}",
    description=(
        "Update a release; anything omitted is left unchanged. Publishing a draft "
        "is this call with `draft: false`."
    ),
    action_label="Updates a GitHub release.",
    response_handler=trim_releases,
)

releases_delete = _github(
    name="releases_delete", args_schema=ReleasesDeleteRequest,
    method="DELETE", url_template="repos/{owner}/{repo}/releases/{release_id}",
    description=(
        "Delete a release. The Git tag survives — use `git_refs_delete` on "
        "`tags/NAME` to remove that too."
    ),
    action_label="Deletes a GitHub release.",
)

releases_generate_notes = _github(
    name="releases_generate_notes", args_schema=ReleasesGenerateNotesRequest,
    method="POST", url_template="repos/{owner}/{repo}/releases/generate-notes",
    description=(
        "Generate release-note text from the pull requests merged since a "
        "previous tag. This creates nothing — GitHub returns a name and a "
        "markdown body and saves neither — so it is safe to call for a draft "
        "changelog. Pass the result to `releases_create` to publish it."
    ),
    action_label="Drafts GitHub release notes.",
    response_handler=trim_generated_notes,
)

releases_list_assets = _github(
    name="releases_list_assets", args_schema=ReleasesListAssetsRequest,
    method="GET", url_template="repos/{owner}/{repo}/releases/{release_id}/assets",
    description="List the files attached to a release, with sizes and download counts.",
    action_label="Lists GitHub release assets.",
    response_handler=trim_release_assets, pagination_override=GITHUB_PAGINATION,
)

releases_upload_asset = _github_uploads(
    name="releases_upload_asset", args_schema=ReleasesUploadAssetRequest,
    method="POST", url_template="repos/{owner}/{repo}/releases/{release_id}/assets",
    description=(
        "Attach a file to a release. Text content only: the body is sent as raw "
        "bytes, and the tool has no way to carry binary. GitHub rewrites names "
        "with special characters, and refuses a name the release already has "
        "rather than replacing it. This call goes to uploads.github.com."
    ),
    action_label="Uploads a GitHub release asset.",
    # A lone scalar Body() keeps its name everywhere else, which is right
    # everywhere else. GitHub wants the file, not an object around it.
    build_request=unwrap_asset_body,
    response_handler=trim_release_assets,
)

# ---------- notifications ----------

notifications_list = _github(
    name="notifications_list", args_schema=NotificationsListRequest,
    method="GET", url_template="notifications",
    description=(
        "List your unread notifications — mentions, review requests, assignments "
        "— most recently updated first. This is how an agent finds out it is "
        "needed without polling repositories. `reason` says why each one is here; "
        "`url` is the thing it concerns. Note `per_page` maxes at 50 here, not "
        "100."
    ),
    action_label="Checks your GitHub notifications.",
    response_handler=trim_notifications, pagination_override=GITHUB_PAGINATION,
)

notifications_mark_read = _github(
    name="notifications_mark_read", args_schema=NotificationsMarkReadRequest,
    method="PUT", url_template="notifications",
    description=(
        "Mark notifications as read — all of them, or everything up to "
        "`last_read_at`. GitHub answers 205 when it finished and 202 when there "
        "were too many and it will finish in the background, so list again with "
        "`all: false` to know whether the queue is actually empty."
    ),
    action_label="Clears your GitHub notifications.",
)

notifications_get_thread = _github(
    name="notifications_get_thread", args_schema=NotificationsGetThreadRequest,
    method="GET", url_template="notifications/threads/{thread_id}",
    description=(
        "Get one notification thread: what it concerns, and the `reason` you were "
        "notified."
    ),
    action_label="Reads a GitHub notification.",
    response_handler=trim_notifications,
)

notifications_mark_thread_read = _github(
    name="notifications_mark_thread_read", args_schema=NotificationsMarkThreadReadRequest,
    method="PATCH", url_template="notifications/threads/{thread_id}",
    description=(
        "Mark one notification thread as read — how an agent takes a handled "
        "item off its own queue."
    ),
    action_label="Marks a GitHub notification read.",
)

# ---------- security alerts ----------

dependabot_list_alerts = _github(
    name="dependabot_list_alerts", args_schema=DependabotListAlertsRequest,
    method="GET", url_template="repos/{owner}/{repo}/dependabot/alerts",
    description=(
        "List a repository's Dependabot alerts: which dependency, how severe, and "
        "the first version that fixes it. Several filters take a comma-separated "
        "list, so `state='open,dismissed'` is valid. Needs the `security_events` "
        "scope. This endpoint has no page parameter — raise `per_page` rather "
        "than paging."
    ),
    action_label="Lists GitHub Dependabot alerts.",
    response_handler=trim_dependabot_alerts,
)

dependabot_get_alert = _github(
    name="dependabot_get_alert", args_schema=DependabotGetAlertRequest,
    method="GET", url_template="repos/{owner}/{repo}/dependabot/alerts/{alert_number}",
    description="Get one Dependabot alert, with its advisory summary and the patched version.",
    action_label="Reads a GitHub Dependabot alert.",
    response_handler=trim_dependabot_alerts,
)

dependabot_update_alert = _github(
    name="dependabot_update_alert", args_schema=DependabotUpdateAlertRequest,
    method="PATCH", url_template="repos/{owner}/{repo}/dependabot/alerts/{alert_number}",
    description=(
        "Dismiss a Dependabot alert or reopen one. Dismissing requires a "
        "`dismissed_reason` — one of fix_started, inaccurate, no_bandwidth, "
        "not_used or tolerable_risk."
    ),
    action_label="Updates a GitHub Dependabot alert.",
    response_handler=trim_dependabot_alerts,
)

code_scanning_list_alerts = _github(
    name="code_scanning_list_alerts", args_schema=CodeScanningListAlertsRequest,
    method="GET", url_template="repos/{owner}/{repo}/code-scanning/alerts",
    description=(
        "List code scanning alerts, each with the rule that fired and the file "
        "and line it fired on. Filter to one pull request with `pr`, or to a "
        "branch with `ref`. Needs GitHub Advanced Security on a private "
        "repository, which answers 403 without it."
    ),
    action_label="Lists GitHub code scanning alerts.",
    response_handler=trim_code_scanning_alerts, pagination_override=GITHUB_PAGINATION,
)

code_scanning_get_alert = _github(
    name="code_scanning_get_alert", args_schema=CodeScanningGetAlertRequest,
    method="GET", url_template="repos/{owner}/{repo}/code-scanning/alerts/{alert_number}",
    description=(
        "Get one code scanning alert, with the rule's description and the most "
        "recent place it was seen."
    ),
    action_label="Reads a GitHub code scanning alert.",
    response_handler=trim_code_scanning_alerts,
)

secret_scanning_list_alerts = _github(
    name="secret_scanning_list_alerts", args_schema=SecretScanningListAlertsRequest,
    method="GET", url_template="repos/{owner}/{repo}/secret-scanning/alerts",
    description=(
        "List secret scanning alerts: which pattern matched, which provider, and "
        "whether the credential is still valid. The detected secret itself is "
        "never returned by this tool — it is dropped from the response whatever "
        "the request asked for, because triage does not need it. Requires "
        "administrator access."
    ),
    action_label="Lists GitHub secret scanning alerts.",
    response_handler=trim_secret_scanning_alerts, pagination_override=GITHUB_PAGINATION,
)

# ---------- discovery and quota ----------

search_commits = _github(
    name="search_commits", args_schema=SearchCommitsRequest,
    method="GET", url_template="search/commits",
    description=(
        "Search commits by message, author or date across GitHub — "
        "'repo:owner/name fix flaky test'. The way to find where a change was "
        "introduced. Rate limited to 30 requests per minute."
    ),
    action_label="Searches GitHub commits.",
    response_handler=trim_commits, pagination_override=SEARCH_PAGINATION,
)

search_users = _github(
    name="search_users", args_schema=SearchUsersRequest,
    method="GET", url_template="search/users",
    description=(
        "Search users and organizations — 'type:org language:rust'. Sees only "
        "publicly visible accounts, whatever the token. Rate limited to 30 "
        "requests per minute."
    ),
    action_label="Searches GitHub users.",
    response_handler=trim_users, pagination_override=SEARCH_PAGINATION,
)

repos_list_for_org = _github(
    name="repos_list_for_org", args_schema=ReposListForOrgRequest,
    method="GET", url_template="orgs/{org}/repos",
    description=(
        "List an organization's repositories. Unlike the personal listing, `type` "
        "and `sort` combine freely here."
    ),
    action_label="Lists an organization's GitHub repositories.",
    response_handler=trim_repos, pagination_override=GITHUB_PAGINATION,
)

repos_list_languages = _github(
    name="repos_list_languages", args_schema=ReposListLanguagesRequest,
    method="GET", url_template="repos/{owner}/{repo}/languages",
    description=(
        "List a repository's languages with bytes of code each — the quickest way "
        "to find out what a repository is written in before reading any of it. "
        "Answers with an object keyed by language, so there is nothing to page."
    ),
    action_label="Reads a GitHub repository's languages.",
    response_handler=trim_languages,
)

repos_list_contributors = _github(
    name="repos_list_contributors", args_schema=ReposListContributorsRequest,
    method="GET", url_template="repos/{owner}/{repo}/contributors",
    description=(
        "List contributors, most commits first — who to ask about a repository. "
        "GitHub links only the first 500 author email addresses to accounts; the "
        "rest come back anonymous. An empty repository returns an empty object."
    ),
    action_label="Lists GitHub contributors.",
    response_handler=trim_contributors, pagination_override=GITHUB_PAGINATION,
)

rate_limit_get = _github(
    name="rate_limit_get", args_schema=RateLimitGetRequest,
    method="GET", url_template="rate_limit",
    description=(
        "Check how much API budget is left, per resource. `core` covers most of "
        "this pack, `search` is the 30-per-minute budget the search tools spend, "
        "and `code_search` is narrower still. This request does not itself count "
        "against any of them, so it is safe to call before a long walk."
    ),
    action_label="Checks your GitHub rate limit.",
    response_handler=trim_rate_limit,
)


TOOLS: list[Tool] = [
    issues_list_for_repo,
    issues_get,
    issues_create,
    issues_update,
    issues_create_comment,
    issues_list_comments,
    pulls_list,
    pulls_get,
    pulls_create,
    pulls_list_files,
    repos_get,
    repos_list_for_authenticated_user,
    repos_get_content,
    repos_list_commits,
    search_issues,
    search_repositories,
    users_get_authenticated,
    pulls_update,
    pulls_merge,
    pulls_create_review,
    pulls_list_reviews,
    pulls_request_reviewers,
    repos_create_or_update_file,
    branches_list,
    git_refs_create,
    actions_list_workflow_runs,
    actions_rerun_workflow,
    actions_cancel_workflow_run,
    search_code,
    actions_get_workflow_run,
    actions_list_jobs_for_run,
    actions_get_job,
    actions_download_job_logs,
    actions_download_run_logs,
    actions_rerun_failed_jobs,
    actions_list_workflows,
    actions_get_workflow,
    actions_create_workflow_dispatch,
    actions_list_runs_for_workflow,
    actions_list_run_artifacts,
    actions_get_artifact,
    actions_download_artifact,
    actions_get_run_usage,
    actions_list_pending_deployments,
    actions_review_pending_deployments,
    actions_list_repo_secrets,
    checks_list_for_ref,
    checks_get_run,
    checks_list_annotations,
    checks_list_suites_for_ref,
    repos_get_combined_status,
    pulls_create_review_comment,
    pulls_list_review_comments,
    pulls_reply_to_review_comment,
    pulls_update_review_comment,
    pulls_delete_review_comment,
    pulls_list_review_comments_for_repo,
    pulls_get_review,
    pulls_submit_review,
    pulls_update_review,
    pulls_dismiss_review,
    pulls_delete_pending_review,
    pulls_list_comments_for_review,
    pulls_get_diff,
    pulls_list_commits,
    pulls_update_branch,
    pulls_check_merged,
    pulls_list_requested_reviewers,
    pulls_remove_requested_reviewers,
    git_refs_get,
    git_refs_update,
    git_refs_delete,
    git_refs_list_matching,
    git_blobs_create,
    git_blobs_get,
    git_trees_create,
    git_trees_get,
    git_commits_create,
    git_commits_get,
    git_tags_create,
    repos_get_commit,
    repos_compare_commits,
    repos_delete_file,
    repos_merge_branches,
    repos_get_branch,
    repos_rename_branch,
    repos_get_branch_protection,
    repos_list_branches_for_head_commit,
    repos_get_readme,
    repos_list_tags,
    repos_create_fork,
    issues_list_labels_for_repo,
    issues_add_labels,
    issues_set_labels,
    issues_remove_label,
    issues_create_label,
    issues_update_label,
    issues_delete_label,
    issues_add_assignees,
    issues_remove_assignees,
    issues_list_milestones,
    issues_create_milestone,
    issues_update_milestone,
    issues_get_comment,
    issues_update_comment,
    issues_delete_comment,
    issues_list_timeline,
    issues_list_events,
    issues_lock,
    issues_unlock,
    issues_list_for_authenticated_user,
    issues_list_sub_issues,
    issues_add_sub_issue,
    releases_list,
    releases_get,
    releases_get_latest,
    releases_get_by_tag,
    releases_create,
    releases_update,
    releases_delete,
    releases_generate_notes,
    releases_list_assets,
    releases_upload_asset,
    notifications_list,
    notifications_mark_read,
    notifications_get_thread,
    notifications_mark_thread_read,
    dependabot_list_alerts,
    dependabot_get_alert,
    dependabot_update_alert,
    code_scanning_list_alerts,
    code_scanning_get_alert,
    secret_scanning_list_alerts,
    search_commits,
    search_users,
    repos_list_for_org,
    repos_list_languages,
    repos_list_contributors,
    rate_limit_get,
]

__all__ = [
    "configure",
    "BASE_URL",
    "UPLOAD_BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "API_VERSION",
    "GITHUB_HEADERS",
    "GITHUB_PAGINATION",
    "SEARCH_PAGINATION",
    "SEARCH_RESULT_CAP",
    "issues_list_for_repo",
    "issues_get",
    "issues_create",
    "issues_update",
    "issues_create_comment",
    "issues_list_comments",
    "pulls_list",
    "pulls_get",
    "pulls_create",
    "pulls_list_files",
    "repos_get",
    "repos_list_for_authenticated_user",
    "repos_get_content",
    "repos_list_commits",
    "search_issues",
    "search_repositories",
    "users_get_authenticated",
    "pulls_update",
    "pulls_merge",
    "pulls_create_review",
    "pulls_list_reviews",
    "pulls_request_reviewers",
    "repos_create_or_update_file",
    "branches_list",
    "git_refs_create",
    "actions_list_workflow_runs",
    "actions_rerun_workflow",
    "actions_cancel_workflow_run",
    "search_code",
    "actions_get_workflow_run",
    "actions_list_jobs_for_run",
    "actions_get_job",
    "actions_download_job_logs",
    "actions_download_run_logs",
    "actions_rerun_failed_jobs",
    "actions_list_workflows",
    "actions_get_workflow",
    "actions_create_workflow_dispatch",
    "actions_list_runs_for_workflow",
    "actions_list_run_artifacts",
    "actions_get_artifact",
    "actions_download_artifact",
    "actions_get_run_usage",
    "actions_list_pending_deployments",
    "actions_review_pending_deployments",
    "actions_list_repo_secrets",
    "checks_list_for_ref",
    "checks_get_run",
    "checks_list_annotations",
    "checks_list_suites_for_ref",
    "repos_get_combined_status",
    "pulls_create_review_comment",
    "pulls_list_review_comments",
    "pulls_reply_to_review_comment",
    "pulls_update_review_comment",
    "pulls_delete_review_comment",
    "pulls_list_review_comments_for_repo",
    "pulls_get_review",
    "pulls_submit_review",
    "pulls_update_review",
    "pulls_dismiss_review",
    "pulls_delete_pending_review",
    "pulls_list_comments_for_review",
    "pulls_get_diff",
    "pulls_list_commits",
    "pulls_update_branch",
    "pulls_check_merged",
    "pulls_list_requested_reviewers",
    "pulls_remove_requested_reviewers",
    "git_refs_get",
    "git_refs_update",
    "git_refs_delete",
    "git_refs_list_matching",
    "git_blobs_create",
    "git_blobs_get",
    "git_trees_create",
    "git_trees_get",
    "git_commits_create",
    "git_commits_get",
    "git_tags_create",
    "repos_get_commit",
    "repos_compare_commits",
    "repos_delete_file",
    "repos_merge_branches",
    "repos_get_branch",
    "repos_rename_branch",
    "repos_get_branch_protection",
    "repos_list_branches_for_head_commit",
    "repos_get_readme",
    "repos_list_tags",
    "repos_create_fork",
    "issues_list_labels_for_repo",
    "issues_add_labels",
    "issues_set_labels",
    "issues_remove_label",
    "issues_create_label",
    "issues_update_label",
    "issues_delete_label",
    "issues_add_assignees",
    "issues_remove_assignees",
    "issues_list_milestones",
    "issues_create_milestone",
    "issues_update_milestone",
    "issues_get_comment",
    "issues_update_comment",
    "issues_delete_comment",
    "issues_list_timeline",
    "issues_list_events",
    "issues_lock",
    "issues_unlock",
    "issues_list_for_authenticated_user",
    "issues_list_sub_issues",
    "issues_add_sub_issue",
    "releases_list",
    "releases_get",
    "releases_get_latest",
    "releases_get_by_tag",
    "releases_create",
    "releases_update",
    "releases_delete",
    "releases_generate_notes",
    "releases_list_assets",
    "releases_upload_asset",
    "notifications_list",
    "notifications_mark_read",
    "notifications_get_thread",
    "notifications_mark_thread_read",
    "dependabot_list_alerts",
    "dependabot_get_alert",
    "dependabot_update_alert",
    "code_scanning_list_alerts",
    "code_scanning_get_alert",
    "secret_scanning_list_alerts",
    "search_commits",
    "search_users",
    "repos_list_for_org",
    "repos_list_languages",
    "repos_list_contributors",
    "rate_limit_get",
]
