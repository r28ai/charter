# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""GitHub Actions: seeing what CI did, and running it again.

Two things about this API are easy to get wrong and both come from the same place.

There is **one** filter, `status`, and it matches either a run's status or its
conclusion. GitHub says so outright: "Returns workflow runs with the check run
`status` or `conclusion` that you specify." There is no `conclusion` query
parameter, so a tool offering one would send a parameter GitHub ignores, and the
model would read an unfiltered page as a filtered one.

And `conclusion` on the way back is not an enum. GitHub's own schema types it as a
plain nullable string, the seven-value set people quote lives on the sibling
check-run schema, and values outside it (`stale`, `startup_failure`) turn up in
practice. Reading it against a closed set would fail on a real run.

API Reference: https://docs.github.com/en/rest/actions/workflow-runs
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import Field

from charter.packs.github.types.common import (
    GitHubListRequest,
    RepoRequest,
    SortDirection,
)
from charter.types import Body, Path, Query

__all__ = [
    "WorkflowRunStatusFilter",
    "JobFilter",
    "DeploymentReviewState",
    "ActionsListWorkflowRunsRequest",
    "ActionsRerunWorkflowRequest",
    "ActionsCancelWorkflowRunRequest",
    "ActionsGetWorkflowRunRequest",
    "ActionsListJobsForRunRequest",
    "ActionsGetJobRequest",
    "ActionsDownloadJobLogsRequest",
    "ActionsDownloadRunLogsRequest",
    "ActionsRerunFailedJobsRequest",
    "ActionsListWorkflowsRequest",
    "ActionsGetWorkflowRequest",
    "ActionsCreateWorkflowDispatchRequest",
    "ActionsListRunsForWorkflowRequest",
    "ActionsListRunArtifactsRequest",
    "ActionsGetArtifactRequest",
    "ActionsDownloadArtifactRequest",
    "ActionsGetRunUsageRequest",
    "ActionsListPendingDeploymentsRequest",
    "ActionsReviewPendingDeploymentsRequest",
    "ActionsListRepoSecretsRequest",
]

# The filter's own enum, which spans both statuses and conclusions. All fourteen.
WorkflowRunStatusFilter = Literal[
    "completed",
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "success",
    "timed_out",
    "in_progress",
    "queued",
    "requested",
    "waiting",
    "pending",
]


class _RunId(RepoRequest):
    run_id: Annotated[
        int,
        Field(..., description="The ID of the workflow run."),
        Path(),
    ]


class ActionsListWorkflowRunsRequest(RepoRequest, GitHubListRequest):
    """List workflow runs for a repository, most recent first.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-repository
    """

    status: Annotated[
        Optional[WorkflowRunStatusFilter],
        Field(
            None,
            description=(
                "Match a run's status or its conclusion. 'in_progress' and 'queued' "
                "are statuses; 'success', 'failure' and 'cancelled' are conclusions."
            ),
        ),
        Query(),
    ]
    branch: Annotated[
        Optional[str],
        Field(None, description="Only runs for pushes to this branch."),
        Query(),
    ]
    event: Annotated[
        Optional[str],
        Field(
            None,
            description="Only runs triggered by this event, such as 'push' or 'pull_request'.",
        ),
        Query(),
    ]
    actor: Annotated[
        Optional[str],
        Field(None, description="Only runs for pushes by this username."),
        Query(),
    ]
    head_sha: Annotated[
        Optional[str],
        Field(None, description="Only runs for this commit SHA."),
        Query(),
    ]
    created: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only runs created in this window, in GitHub's search syntax: "
                "'>=2026-01-01' or '2026-01-01..2026-02-01'."
            ),
        ),
        Query(),
    ]
    exclude_pull_requests: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Leave the pull requests off each run. They are the bulkiest part of "
                "the response and rarely the reason for listing runs."
            ),
        ),
        Query(),
    ]


class ActionsRerunWorkflowRequest(_RunId):
    """Run a workflow again from the start.

    This reruns every job, including the ones that passed. Use
    ``actions_rerun_failed_jobs`` to retry only what failed.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#re-run-a-workflow
    """

    enable_debug_logging: Annotated[
        Optional[bool],
        Field(None, description="Turn on runner and step debug logging for the rerun."),
        Body(),
    ]


class ActionsCancelWorkflowRunRequest(_RunId):
    """Ask GitHub to cancel a workflow run.

    The 202 means the cancellation was accepted, not that the run has stopped. A
    run that is already finished answers 409 instead.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#cancel-a-workflow-run
    """


# -----------------------------------------------------
# Reading a run: jobs, logs, artifacts
# -----------------------------------------------------

JobFilter = Literal["latest", "all"]
"""Which execution of a run to report jobs from. A rerun does not replace the
previous attempt's jobs, it adds a newer set beside them."""


class ActionsGetWorkflowRunRequest(_RunId):
    """Get one workflow run.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#get-a-workflow-run
    """

    exclude_pull_requests: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "If `true` pull requests are omitted from the response (empty array). "
                "They are the bulkiest part of a run and rarely the reason for reading "
                "one. GitHub includes them when this is absent."
            ),
        ),
        Query(),
    ]


class ActionsListJobsForRunRequest(_RunId, GitHubListRequest):
    """List the jobs of a workflow run.

    This is the step between "CI is red" and "which job failed": the run's own
    ``conclusion`` says only that something did.

    API Reference: https://docs.github.com/en/rest/actions/workflow-jobs#list-jobs-for-a-workflow-run
    """

    filter: Annotated[
        Optional[JobFilter],
        Field(
            None,
            description=(
                "Filters jobs by their `completed_at` timestamp. `latest` returns jobs "
                "from the most recent execution of the workflow run. `all` returns all "
                "jobs for a workflow run, including from old executions of the workflow "
                "run. GitHub uses `latest` when this is absent."
            ),
        ),
        Query(),
    ]


class _JobId(RepoRequest):
    job_id: Annotated[
        int,
        Field(
            ...,
            description=(
                "The unique identifier of the job. This is the job's `id` from "
                "`actions_list_jobs_for_run`, not its name and not the run's id."
            ),
        ),
        Path(),
    ]


class ActionsGetJobRequest(_JobId):
    """Get one job of a workflow run, with its per-step outcomes.

    The `steps` array is where a failure localises to a command: each step
    carries its own `conclusion`, so the failing one is named without reading
    any logs.

    API Reference: https://docs.github.com/en/rest/actions/workflow-jobs#get-a-job-for-a-workflow-run
    """


class ActionsDownloadJobLogsRequest(_JobId):
    """Download one job's logs, as plain text.

    GitHub answers 302 with a `Location` pointing at a signed URL that "expires
    after 1 minute", and serves the log itself from there as a plain text file.
    This tool follows that redirect — see ``follow_redirects`` on the tool — and
    the bearer token does not travel with it, because httpx drops
    ``Authorization`` when a redirect leaves the origin.

    A job log is routinely megabytes, so what comes back here is not the file:
    the response handler keeps the tail and the lines that look like the
    failure. The full text is never in the model's context.

    API Reference: https://docs.github.com/en/rest/actions/workflow-jobs#download-job-logs-for-a-workflow-run
    """


class ActionsDownloadRunLogsRequest(_RunId):
    """Download a whole run's logs, as a ZIP of per-job text files.

    The sibling of ``actions_download_job_logs`` and a different payload: GitHub
    calls this one "an archive of log files", and it is a ZIP, not text. The
    response handler opens it and keeps each job's tail, so one call covers a
    run whose failure could be in any of its jobs.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#download-workflow-run-logs
    """


class ActionsRerunFailedJobsRequest(_RunId):
    """Re-run only the failed jobs of a workflow run, and their dependents.

    The narrow sibling of ``actions_rerun_workflow``, which re-runs everything
    including the jobs that passed.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#re-run-failed-jobs-from-a-workflow-run
    """

    enable_debug_logging: Annotated[
        Optional[bool],
        Field(None, description="Whether to enable debug logging for the re-run."),
        Body(),
    ]


# -----------------------------------------------------
# Workflows
# -----------------------------------------------------


class ActionsListWorkflowsRequest(RepoRequest, GitHubListRequest):
    """List the workflows defined in a repository.

    API Reference: https://docs.github.com/en/rest/actions/workflows#list-repository-workflows
    """


class _WorkflowId(RepoRequest):
    workflow_id: Annotated[
        Union[int, str],
        Field(
            ...,
            description=(
                "The ID of the workflow. You can also pass the workflow file name as a "
                "string, such as `ci.yml`, which is usually the one you have."
            ),
        ),
        Path(),
    ]


class ActionsGetWorkflowRequest(_WorkflowId):
    """Get one workflow, including whether it is active or disabled.

    API Reference: https://docs.github.com/en/rest/actions/workflows#get-a-workflow
    """


class ActionsCreateWorkflowDispatchRequest(_WorkflowId):
    """Trigger a workflow run by hand.

    The workflow must declare the `workflow_dispatch` trigger in its own file;
    GitHub will not run one that does not, and there is nothing in this request
    that can make it.

    API Reference: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
    """

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The git reference for the workflow. The reference can be a branch or tag name."
            ),
        ),
        Body(),
    ]
    inputs: Annotated[
        Optional[Dict[str, Union[str, int, float, bool]]],
        Field(
            None,
            max_length=25,
            description=(
                "Input keys and values configured in the workflow file. The maximum "
                "number of properties is 25. Any default properties configured in the "
                "workflow file will be used when `inputs` are omitted."
            ),
        ),
        Body(),
    ]
    return_run_details: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether the response should include the workflow run ID and URLs. "
                "Absent, GitHub answers 204 with no body at all, and the run you just "
                "started has to be found by listing runs."
            ),
        ),
        Body(),
    ]


class ActionsListRunsForWorkflowRequest(_WorkflowId, GitHubListRequest):
    """List the runs of one workflow, most recent first.

    The same filters as ``actions_list_workflow_runs``, narrowed to a single
    workflow file — which is how you ask "is *this* pipeline green" rather than
    "is anything red".

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow
    """

    actor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Returns someone's workflow runs. Use the login for the user who "
                "created the `push` associated with the check suite or workflow run."
            ),
        ),
        Query(),
    ]
    branch: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Returns workflow runs associated with a branch. Use the name of the "
                "branch of the `push`."
            ),
        ),
        Query(),
    ]
    event: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Returns workflow run triggered by the event you specify. For example, "
                "`push`, `pull_request` or `issue`."
            ),
        ),
        Query(),
    ]
    status: Annotated[
        Optional[WorkflowRunStatusFilter],
        Field(
            None,
            description=(
                "Returns workflow runs with the check run `status` or `conclusion` that "
                "you specify. For example, a conclusion can be `success` or a status "
                "can be `in_progress`. Only GitHub Actions can set a status of "
                "`waiting`, `pending`, or `requested`."
            ),
        ),
        Query(),
    ]
    created: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Returns workflow runs created within the given date-time range, in "
                "GitHub's search syntax: '>=2026-01-01' or '2026-01-01..2026-02-01'."
            ),
        ),
        Query(),
    ]
    exclude_pull_requests: Annotated[
        Optional[bool],
        Field(
            None,
            description="If `true` pull requests are omitted from the response (empty array).",
        ),
        Query(),
    ]
    check_suite_id: Annotated[
        Optional[int],
        Field(
            None, description="Returns workflow runs with the `check_suite_id` that you specify."
        ),
        Query(),
    ]
    head_sha: Annotated[
        Optional[str],
        Field(
            None,
            description="Only returns workflow runs that are associated with the specified `head_sha`.",
        ),
        Query(),
    ]


# -----------------------------------------------------
# Artifacts
# -----------------------------------------------------


class ActionsListRunArtifactsRequest(_RunId, GitHubListRequest):
    """List what a workflow run uploaded.

    API Reference: https://docs.github.com/en/rest/actions/artifacts#list-workflow-run-artifacts
    """

    name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The name field of an artifact. When specified, only artifacts with "
                "this name will be returned."
            ),
        ),
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


class _ArtifactId(RepoRequest):
    artifact_id: Annotated[
        int,
        Field(..., description="The unique identifier of the artifact."),
        Path(),
    ]


class ActionsGetArtifactRequest(_ArtifactId):
    """Get one artifact's metadata, including whether it has expired.

    `expired` is worth reading before a download: an artifact past its retention
    window still has a record here, and answers 410 at the download endpoint.

    API Reference: https://docs.github.com/en/rest/actions/artifacts#get-an-artifact
    """


class ActionsDownloadArtifactRequest(_ArtifactId):
    """Download an artifact and report what is inside it.

    `archive_format` is part of this endpoint's URL and GitHub documents exactly
    one legal value — "The `:archive_format` must be `zip`" — so it is a
    constant in the URL template rather than a field the model has to fill in
    with the only answer.

    An artifact is an arbitrary archive and can be very large. This does not
    hand the archive to the model: the response handler reads the ZIP's own
    index and returns the entry names and sizes, plus the contents of the small
    text entries, which is what an agent reading a test report or a coverage
    summary actually needs.

    API Reference: https://docs.github.com/en/rest/actions/artifacts#download-an-artifact
    """


class ActionsGetRunUsageRequest(_RunId):
    """Get a run's billable minutes and total run time.

    GitHub has this one marked "in the process of closing down", and it is
    carried here with that said rather than left out silently. Billable minutes
    only apply to private repositories on GitHub-hosted runners; a public
    repository reports run time and no billing.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#get-workflow-run-usage
    """


# -----------------------------------------------------
# Deployments waiting on a human
# -----------------------------------------------------

DeploymentReviewState = Literal["approved", "rejected"]


class ActionsListPendingDeploymentsRequest(_RunId):
    """List the environments of a run that are waiting for a reviewer.

    This is where a run sits when it is neither failing nor progressing.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#get-pending-deployments-for-a-workflow-run
    """


class ActionsReviewPendingDeploymentsRequest(_RunId):
    """Approve or reject a run's pending deployments.

    All three fields are required by GitHub, `comment` included — a review with
    no reason given is not a request this API accepts.

    API Reference: https://docs.github.com/en/rest/actions/workflow-runs#review-pending-deployments-for-a-workflow-run
    """

    environment_ids: Annotated[
        List[int],
        Field(
            ...,
            description=(
                "The list of environment ids to approve or reject. These are the "
                "`environment.id` values from `actions_list_pending_deployments`."
            ),
        ),
        Body(),
    ]
    state: Annotated[
        DeploymentReviewState,
        Field(
            ...,
            description="Whether to approve or reject deployment to the specified environments.",
        ),
        Body(),
    ]
    comment: Annotated[
        str,
        Field(..., description="A comment to accompany the deployment review."),
        Body(),
    ]


class ActionsListRepoSecretsRequest(RepoRequest, GitHubListRequest):
    """List the names of a repository's Actions secrets.

    GitHub's own description: "Lists all secrets available in a repository
    without revealing their encrypted values." A secret object carries `name`,
    `created_at` and `updated_at` and nothing else — there is no field here that
    could return a value, which is why this endpoint is safe to hand an agent
    and the sibling write endpoints are not carried.

    API Reference: https://docs.github.com/en/rest/actions/secrets#list-repository-secrets
    """
