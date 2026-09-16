"""Request schemas for notifications, security alerts and the rate limit.

What these have in common is that they are how an agent finds out something has
changed without being told. ``notifications_list`` is the wake-up signal — "you
were mentioned", "a review was requested" — and the alert endpoints are the same
thing for supply-chain and code-scanning findings. ``rate_limit_get`` is the one
self-regarding tool in the pack: an agent walking thirty pages should be able to
see the budget it is spending.

Two pagination notes that matter, because both differ from the rest of GitHub:

* ``notifications_list`` caps ``per_page`` at **50**, not the usual 100.
* The three alert endpoints page by an opaque cursor carried in the ``Link``
  header, which is not in the response body and therefore not something Charter
  can follow. ``code_scanning_list_alerts`` and ``secret_scanning_list_alerts``
  also accept ``page``, so those walk normally. ``dependabot_list_alerts`` does
  **not** — it has no ``page`` parameter at all — so it declares no pagination
  and its first page is what a single call returns. Raise ``per_page`` rather
  than expecting a walk.

API Reference: https://docs.github.com/en/rest/activity/notifications
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.github.types.common import (
    GitHubListRequest,
    RepoRequest,
    SortDirection,
)
from charter.types import Body, Path, Query

__all__ = [
    "NOTIFICATIONS_PER_PAGE_MAX",
    "DependabotScope",
    "DependabotSort",
    "DependabotState",
    "DismissedReason",
    "CodeScanningState",
    "CodeScanningSeverity",
    "CodeScanningSort",
    "SecretScanningState",
    "SecretScanningSort",
    "NotificationsListRequest",
    "NotificationsMarkReadRequest",
    "NotificationsGetThreadRequest",
    "NotificationsMarkThreadReadRequest",
    "DependabotListAlertsRequest",
    "DependabotGetAlertRequest",
    "DependabotUpdateAlertRequest",
    "CodeScanningListAlertsRequest",
    "CodeScanningGetAlertRequest",
    "SecretScanningListAlertsRequest",
    "RateLimitGetRequest",
]


# GitHub's ceiling on this one endpoint, against 100 everywhere else.
NOTIFICATIONS_PER_PAGE_MAX = 50


class NotificationsListRequest(BaseModel):
    """List the authenticated user's notifications, most recently updated first.

    The trigger for an agent that waits rather than polls a repository: a
    mention, a review request, a failing workflow it was subscribed to. Unread
    only by default, which is what makes it a queue.

    Its own pagination parameters, because ``per_page`` is capped at 50 here
    rather than 100.

    API Reference: https://docs.github.com/en/rest/activity/notifications#list-notifications-for-the-authenticated-user
    """

    all: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "If `true`, show notifications marked as read. Absent, only unread "
                "ones come back."
            ),
        ),
        Query(),
    ]
    participating: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "If `true`, only shows notifications in which the user is directly "
                "participating or mentioned — the ones that are about you rather than "
                "about a repository you watch."
            ),
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
    before: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Only show notifications updated before the given time, in ISO 8601 "
                "format: `YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Query(),
    ]
    per_page: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=NOTIFICATIONS_PER_PAGE_MAX,
            description=(
                "The number of results per page. This endpoint's maximum is 50, not "
                "the 100 the rest of the REST API allows. Defaults to 50."
            ),
        ),
        Query(),
    ]
    page: Annotated[
        Optional[int],
        Field(None, ge=1, description="The page number of the results to fetch. Defaults to 1."),
        Query(),
    ]


class NotificationsMarkReadRequest(BaseModel):
    """Mark notifications as read — all of them, or everything up to a time.

    GitHub answers 205 when it finished the job and **202 when it did not**:
    "If the number of notifications is too large to complete in one request, you
    will receive a `202 Accepted` status and GitHub will run an asynchronous
    process to mark notifications as 'read'." Both are successes here, and only
    one of them means the inbox is empty — list again with `all: false` to know
    which happened.

    API Reference: https://docs.github.com/en/rest/activity/notifications#mark-notifications-as-read
    """

    last_read_at: Annotated[
        Optional[datetime],
        Field(
            None,
            description=(
                "Describes the last point that notifications were checked. Anything "
                "updated since this time will not be marked as read. If you omit this "
                "parameter, all notifications are marked as read. ISO 8601: "
                "`YYYY-MM-DDTHH:MM:SSZ`."
            ),
        ),
        Body(),
    ]
    read: Annotated[
        Optional[bool],
        Field(None, description="Whether the notification has been read."),
        Body(),
    ]


class _ThreadId(BaseModel):
    thread_id: Annotated[
        int,
        Field(..., description="The unique identifier of the notification thread."),
        Path(),
    ]


class NotificationsGetThreadRequest(_ThreadId):
    """Get one notification thread: what it is about, and why you have it.

    `reason` is the useful field — `mention`, `review_requested`, `ci_activity`,
    `assign` — and `subject.url` is the API URL of the thing it concerns, which
    is how an agent gets from a notification to the issue or pull request.

    API Reference: https://docs.github.com/en/rest/activity/notifications#get-a-thread
    """


class NotificationsMarkThreadReadRequest(_ThreadId):
    """Mark one thread as read — the equivalent of clicking it.

    Takes no body and returns none. This is how an agent that has handled a
    notification takes it off its own queue.

    API Reference: https://docs.github.com/en/rest/activity/notifications#mark-a-thread-as-read
    """


# -----------------------------------------------------
# Dependabot
# -----------------------------------------------------

DependabotState = Literal["auto_dismissed", "dismissed", "fixed", "open"]
DependabotScope = Literal["development", "runtime"]
DependabotSort = Literal["created", "updated", "epss_percentage"]
DismissedReason = Literal[
    "fix_started", "inaccurate", "no_bandwidth", "not_used", "tolerable_risk"
]

# GitHub caps the comment left when dismissing an alert.
DISMISSED_COMMENT_MAX = 280


class DependabotListAlertsRequest(RepoRequest):
    """List a repository's Dependabot alerts.

    Several of these filters take a **comma-separated list** rather than a
    single value, which is why they are typed as strings with the accepted
    values named in the description: `state='open,dismissed'` is a legal value
    and a closed enum could not express it.

    This endpoint has no `page` parameter. GitHub pages it by an opaque cursor
    in the `Link` header, which is not in the response body, so there is no walk
    to declare — one call returns one page, and `per_page` is the control.

    Needs the `security_events` scope, or `public_repo` for public repositories
    only.

    API Reference: https://docs.github.com/en/rest/dependabot/alerts#list-dependabot-alerts-for-a-repository
    """

    state: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of states. If specified, only alerts with these "
                "states will be returned. Can be: `auto_dismissed`, `dismissed`, "
                "`fixed`, `open`."
            ),
        ),
        Query(),
    ]
    severity: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of severities. Can be: `low`, `medium`, `high`, "
                "`critical`."
            ),
        ),
        Query(),
    ]
    ecosystem: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of ecosystems. Can be: `composer`, `go`, "
                "`maven`, `npm`, `nuget`, `pip`, `pub`, `rubygems`, `rust`."
            ),
        ),
        Query(),
    ]
    package: Annotated[
        Optional[str],
        Field(
            None,
            description="A comma-separated list of package names to restrict the results to.",
        ),
        Query(),
    ]
    manifest: Annotated[
        Optional[str],
        Field(None, description="A comma-separated list of full manifest paths."),
        Query(),
    ]
    classification: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of vulnerability classifications. Can be: "
                "`malware`, `general`."
            ),
        ),
        Query(),
    ]
    epss_percentage: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Filter by EPSS percentage — the estimated probability of exploitation. "
                "An exact number, a comparator such as `>0.5`, or a range `0.1..0.4`, "
                "with values from 0.0 to 1.0."
            ),
        ),
        Query(),
    ]
    has: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only alerts with the given property. Currently only `patch` is "
                "supported, which restricts results to alerts that have a fix "
                "available."
            ),
        ),
        Query(),
    ]
    assignee: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Filter alerts by assignees, as a comma-separated list of user handles. "
                "Use `*` for alerts with at least one assignee or `none` for alerts "
                "with no assignees."
            ),
        ),
        Query(),
    ]
    scope: Annotated[
        Optional[DependabotScope],
        Field(
            None,
            description=(
                "The scope of the vulnerable dependency. `runtime` is what ships; "
                "`development` is what only the build sees."
            ),
        ),
        Query(),
    ]
    relationship: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of relationships of the vulnerable dependency "
                "to your project. Can be: `unknown`, `direct`, `transitive`, "
                "`inconclusive`."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[DependabotSort],
        Field(
            None,
            description=(
                "The property by which to sort the results. `created` means when the "
                "alert was created. `updated` means when the alert's state last "
                "changed. `epss_percentage` sorts by estimated exploitation "
                "probability. GitHub uses `created` when this is absent."
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
    per_page: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description="The number of results to return (max 100). Defaults to 30.",
        ),
        Query(),
    ]


class _AlertNumber(RepoRequest):
    alert_number: Annotated[
        int,
        Field(
            ...,
            description=(
                "The number that identifies the alert in its repository — the `number` "
                "field on a listed alert, and the last segment of its URL."
            ),
        ),
        Path(),
    ]


class DependabotGetAlertRequest(_AlertNumber):
    """Get one Dependabot alert, with its advisory and the fixed version.

    API Reference: https://docs.github.com/en/rest/dependabot/alerts#get-a-dependabot-alert
    """


class DependabotUpdateAlertRequest(_AlertNumber):
    """Dismiss a Dependabot alert, or reopen one.

    ``dismissed_reason`` is GitHub's, verbatim: "Required when `state` is
    `dismissed`." The validator enforces it rather than spending a round trip on
    a 422.

    API Reference: https://docs.github.com/en/rest/dependabot/alerts#update-a-dependabot-alert
    """

    state: Annotated[
        Optional[Literal['dismissed', 'open']],
        Field(
            None,
            description=(
                "The state of the Dependabot alert. A `dismissed_reason` must be "
                "provided when setting the state to `dismissed`."
            ),
        ),
        Body(),
    ]
    dismissed_reason: Annotated[
        Optional[DismissedReason],
        Field(
            None,
            description="Required when `state` is `dismissed`. A reason for dismissing the alert.",
        ),
        Body(),
    ]
    dismissed_comment: Annotated[
        Optional[str],
        Field(
            None,
            max_length=DISMISSED_COMMENT_MAX,
            description="An optional comment associated with dismissing the alert.",
        ),
        Body(),
    ]
    assignees: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Usernames to assign to this Dependabot alert. Pass one or more user "
                "logins to *replace* the set of assignees on this alert. Send an empty "
                "array to clear all assignees."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _dismissal_states_its_reason(self) -> DependabotUpdateAlertRequest:
        if self.state == "dismissed" and self.dismissed_reason is None:
            raise ValueError(
                "`dismissed_reason` is required when `state` is 'dismissed'. Choose "
                "one of: fix_started, inaccurate, no_bandwidth, not_used, "
                "tolerable_risk."
            )
        if self.dismissed_reason is not None and self.state != "dismissed":
            raise ValueError(
                "`dismissed_reason` only applies when `state` is 'dismissed'."
            )
        return self


# -----------------------------------------------------
# Code scanning and secret scanning
# -----------------------------------------------------

CodeScanningState = Literal["open", "closed", "dismissed", "fixed"]
CodeScanningSeverity = Literal[
    "critical", "high", "medium", "low", "warning", "note", "error"
]
CodeScanningSort = Literal["created", "updated"]


class CodeScanningListAlertsRequest(RepoRequest, GitHubListRequest):
    """List a repository's code scanning alerts.

    Needs GitHub Advanced Security on a private repository; without it the
    endpoint answers 403 rather than an empty list.

    API Reference: https://docs.github.com/en/rest/code-scanning/code-scanning#list-code-scanning-alerts-for-a-repository
    """

    tool_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The name of a code scanning tool. Only results by this tool will be "
                "listed. You can specify the tool by using either `tool_name` or "
                "`tool_guid`, but not both."
            ),
        ),
        Query(),
    ]
    tool_guid: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The GUID of a code scanning tool. Note that some code scanning tools "
                "may not include a GUID in their analysis data. Cannot be combined with "
                "`tool_name`."
            ),
        ),
        Query(),
    ]
    ref: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The Git reference for the results you want to list. A branch can be "
                "`refs/heads/BRANCH` or simply `BRANCH`. To reference a pull request "
                "use `refs/pull/NUMBER/merge`."
            ),
        ),
        Query(),
    ]
    pr: Annotated[
        Optional[int],
        Field(None, description="The number of the pull request for the results you want to list."),
        Query(),
    ]
    state: Annotated[
        Optional[CodeScanningState],
        Field(None, description="If specified, only code scanning alerts with this state will be returned."),
        Query(),
    ]
    severity: Annotated[
        Optional[CodeScanningSeverity],
        Field(
            None,
            description="If specified, only code scanning alerts with this severity will be returned.",
        ),
        Query(),
    ]
    assignees: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Filter alerts by assignees, as a comma-separated list of user handles. "
                "Use `*` for at least one assignee or `none` for unassigned."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[CodeScanningSort],
        Field(
            None,
            description="The property by which to sort the results. GitHub uses `created` when this is absent.",
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

    @model_validator(mode="after")
    def _one_tool_selector(self) -> CodeScanningListAlertsRequest:
        """GitHub: "either `tool_name` or `tool_guid`, but not both"."""
        if self.tool_name is not None and self.tool_guid is not None:
            raise ValueError(
                "Specify the tool with either `tool_name` or `tool_guid`, not both."
            )
        return self


class CodeScanningGetAlertRequest(_AlertNumber):
    """Get one code scanning alert, with the rule that fired and where.

    `most_recent_instance` carries the file, the line range and the message —
    the same shape as a check annotation, for the alerts that outlive a run.

    API Reference: https://docs.github.com/en/rest/code-scanning/code-scanning#get-a-code-scanning-alert
    """


SecretScanningState = Literal["open", "resolved"]
SecretScanningSort = Literal["created", "updated"]


class SecretScanningListAlertsRequest(RepoRequest, GitHubListRequest):
    """List a repository's secret scanning alerts, newest first.

    The authenticated user must be an administrator of the repository or its
    organization; a repository without secret scanning answers 404 rather than
    an empty list.

    **The alert objects contain the detected secret.** ``hide_secret`` leaves it
    out, and is worth setting whenever the answer is going to a model: the value
    of a leaked credential is not something an agent needs in order to file,
    triage or close the alert.

    API Reference: https://docs.github.com/en/rest/secret-scanning/secret-scanning#list-secret-scanning-alerts-for-a-repository
    """

    state: Annotated[
        Optional[SecretScanningState],
        Field(
            None,
            description="Set to `open` or `resolved` to only list alerts in a specific state.",
        ),
        Query(),
    ]
    secret_type: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of secret types to return. All default secret "
                "patterns are returned when absent. Cannot be combined with "
                "`exclude_secret_types`."
            ),
        ),
        Query(),
    ]
    exclude_secret_types: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of secret types to exclude from the results. "
                "Cannot be combined with `secret_type`."
            ),
        ),
        Query(),
    ]
    resolution: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of resolutions. Valid resolutions are "
                "`false_positive`, `wont_fix`, `revoked`, `pattern_edited`, "
                "`pattern_deleted` or `used_in_tests`."
            ),
        ),
        Query(),
    ]
    assignee: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Filters alerts by assignee. Use `*` for all assigned alerts, `none` "
                "for unassigned, or a GitHub username."
            ),
        ),
        Query(),
    ]
    validity: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A comma-separated list of validities — whether GitHub could confirm "
                "the secret still works. Can be: `active`, `inactive`, `unknown`."
            ),
        ),
        Query(),
    ]
    hide_secret: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Leave the detected secret value out of the response. Set this when the "
                "result is going into a model's context: triage needs the type, the "
                "location and the state, not the credential."
            ),
        ),
        Query(),
    ]
    is_publicly_leaked: Annotated[
        Optional[bool],
        Field(None, description="Only alerts for secrets that were leaked publicly."),
        Query(),
    ]
    is_multi_repo: Annotated[
        Optional[bool],
        Field(None, description="Only alerts for secrets detected in more than one repository."),
        Query(),
    ]
    sort: Annotated[
        Optional[SecretScanningSort],
        Field(
            None,
            description=(
                "The property to sort the results by. `created` means when the alert "
                "was created; `updated` means when it was updated or resolved. GitHub "
                "uses `created` when this is absent."
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

    @model_validator(mode="after")
    def _secret_type_filters_are_exclusive(self) -> SecretScanningListAlertsRequest:
        if self.secret_type is not None and self.exclude_secret_types is not None:
            raise ValueError(
                "`secret_type` and `exclude_secret_types` cannot be combined — name "
                "the types to include, or the types to leave out, not both."
            )
        return self


class RateLimitGetRequest(BaseModel):
    """Read the rate limit budget, without spending any of it.

    GitHub does not count this request against the limit it reports, which makes
    it safe to call before a long walk. The resources are separate budgets:
    `core` for most of the REST API, `search` at 30 requests a minute, and
    `code_search` narrower still.

    API Reference: https://docs.github.com/en/rest/rate-limit/rate-limit
    """
