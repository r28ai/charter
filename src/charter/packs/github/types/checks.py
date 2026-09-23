# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for the Checks API and commit statuses.

These are the two ways GitHub records "did this commit pass", and they are not
the same system. A **check run** is what a GitHub App reports — Actions, and
every third-party CI that integrates as an App — and it carries structured
*annotations*: a file, a line, a level and a message, extracted by whoever ran
the check. A **commit status** is the older, flatter thing: a context, a state
and a URL, with no file and no line.

An agent fixing a red build wants the annotations. They are the only place in
this API where a failure is already localised to a file and a line, which is
the difference between handing a model a diagnosis and handing it a log to
read.

`ref` on the three reference-scoped endpoints takes GitHub's own spelling for
a commit-ish: a commit SHA, a branch as ``heads/BRANCH_NAME``, or a tag as
``tags/TAG_NAME``.

API Reference: https://docs.github.com/en/rest/checks
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from charter.packs.github.types.common import GitHubListRequest, RepoRequest
from charter.types import Path, Query

__all__ = [
    "CheckRunStatusFilter",
    "CheckRunFilter",
    "ChecksListForRefRequest",
    "ChecksGetRunRequest",
    "ChecksListAnnotationsRequest",
    "ChecksListSuitesForRefRequest",
    "ReposGetCombinedStatusRequest",
]


CheckRunStatusFilter = Literal["queued", "in_progress", "completed"]
"""The three values the check-run *filter* accepts.

Narrower than the filter on ``actions_list_workflow_runs``, which folds
statuses and conclusions into one parameter. Here a conclusion is not a status
and GitHub refuses one: filtering for `failure` is `status='completed'` plus
reading `conclusion` off what comes back."""

CheckRunFilter = Literal["latest", "all"]
"""Whether to report only the most recent check runs or every attempt."""


class _Ref(RepoRequest):
    """A repository-scoped request that names a commit-ish."""

    ref: Annotated[
        str,
        Field(
            ...,
            description=(
                "The commit reference. Can be a commit SHA, branch name "
                "(`heads/BRANCH_NAME`), or tag name (`tags/TAG_NAME`)."
            ),
        ),
        # `heads/main` is one reference, not two path segments.
        Path(allow_slash=True),
    ]


class ChecksListForRefRequest(_Ref, GitHubListRequest):
    """List the check runs for a commit, branch or tag.

    GitHub caps this: "If there are more than 1000 check suites on a single git
    reference, this endpoint will limit check runs to the 1000 most recent
    check suites."

    API Reference: https://docs.github.com/en/rest/checks/runs#list-check-runs-for-a-git-reference
    """

    check_name: Annotated[
        Optional[str],
        Field(None, description="Returns check runs with the specified `name`."),
        Query(),
    ]
    status: Annotated[
        Optional[CheckRunStatusFilter],
        Field(
            None,
            description=(
                "Returns check runs with the specified `status`. This filter takes a "
                "status only — a failed run is `status: completed` with a `conclusion` "
                "of `failure` on the way back."
            ),
        ),
        Query(),
    ]
    filter: Annotated[
        Optional[CheckRunFilter],
        Field(
            None,
            description=(
                "Filters check runs by their `completed_at` timestamp. `latest` returns "
                "the most recent check runs. GitHub uses `latest` when this is absent."
            ),
        ),
        Query(),
    ]
    app_id: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "Only check runs reported by this GitHub App. GitHub Actions is itself "
                "an App, so this is how a repository with several CI providers is "
                "narrowed to one."
            ),
        ),
        Query(),
    ]


class _CheckRunId(RepoRequest):
    check_run_id: Annotated[
        int,
        Field(..., description="The unique identifier of the check run."),
        Path(),
    ]


class ChecksGetRunRequest(_CheckRunId):
    """Get one check run, with its summary text and counts.

    API Reference: https://docs.github.com/en/rest/checks/runs#get-a-check-run
    """


class ChecksListAnnotationsRequest(_CheckRunId, GitHubListRequest):
    """List a check run's annotations: the failures, already located.

    Each annotation carries `path`, `start_line`, `end_line`, `annotation_level`
    and `message` — a compiler error or a lint failure with the file and the
    line GitHub extracted for it. This is the cheap answer to "why is CI red":
    no log to download and nothing to parse.

    GitHub limits the Checks API to 50 annotations per request, so a check run
    with more of them is read by paging.

    API Reference: https://docs.github.com/en/rest/checks/runs#list-check-run-annotations
    """


class ChecksListSuitesForRefRequest(_Ref, GitHubListRequest):
    """List the check suites for a commit, branch or tag.

    A suite is one App's whole set of check runs for a commit. Its `conclusion`
    is a wider enum than a check run's: it adds `startup_failure` and `stale`,
    which is why neither is read here against a closed set.

    API Reference: https://docs.github.com/en/rest/checks/suites#list-check-suites-for-a-git-reference
    """

    app_id: Annotated[
        Optional[int],
        Field(None, description="Filters check suites by GitHub App `id`."),
        Query(),
    ]
    check_name: Annotated[
        Optional[str],
        Field(None, description="Returns check runs with the specified `name`."),
        Query(),
    ]


class ReposGetCombinedStatusRequest(_Ref, GitHubListRequest):
    """Get the single roll-up state of a commit: the answer to "is this green".

    The older system, and still the one that answers in one field. GitHub
    combines every context into one `state`: "failure if any of the contexts
    report as error or failure; pending if there are no statuses or a context is
    pending; success if the latest status for all contexts is success."

    Note that this does **not** include check runs — an Actions-only repository
    reports `pending` here with no statuses at all, and its real answer is in
    `checks_list_for_ref`. Read both, or read the one the repository uses.

    API Reference: https://docs.github.com/en/rest/commits/statuses#get-the-combined-status-for-a-specific-reference
    """
