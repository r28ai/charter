# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Firecrawl monitor endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from charter.packs.firecrawl.types.common import CrawlTargetOptions, ScrapeOptionsNested
from charter.types import Body, Path, Query

__all__ = [
    "MonitorCreateRequest",
    "MonitorListRequest",
    "MonitorGetRequest",
    "MonitorUpdateRequest",
    "MonitorDeleteRequest",
    "MonitorRunRequest",
    "MonitorChecksListRequest",
    "MonitorCheckGetRequest",
]

MonitorWebhookEvent = Literal["monitor.page", "monitor.check.completed"]
MonitorCheckStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "partial",
    "skipped_overlap",
    "skipped_no_credits",
]
MonitorPageStatus = Literal["same", "new", "changed", "removed", "error"]
MonitorStatus = Literal["active", "paused", "deleted"]
MonitorSearchWindow = Literal["5m", "15m", "1h", "6h", "24h", "7d"]


class MonitorSchedule(BaseModel):
    """Schedule for monitor checks. Provide either cron or text."""

    cron: Optional[str] = Field(
        None, description="Five-field cron expression. Minimum interval is 5 minutes."
    )
    text: Optional[str] = Field(
        None,
        description="Natural language schedule such as 'every 30 minutes' or 'daily at 9am'.",
    )
    timezone: Optional[str] = Field(
        None,
        description="IANA timezone for the schedule. The server applies 'UTC' when this is absent.",
    )

    @model_validator(mode="after")
    def _cron_or_text(self) -> MonitorSchedule:
        if self.cron and self.text:
            raise ValueError("Provide either cron or text, not both.")
        if not self.cron and not self.text:
            raise ValueError("Provide either cron or text.")
        return self


class MonitorWebhook(BaseModel):
    """Webhook destination for monitor page and check completion events."""

    url: str = Field(..., description="The URL to send monitor webhooks to.")
    headers: Optional[dict[str, str]] = Field(
        None, description="Headers to send to the webhook URL."
    )
    metadata: Optional[dict] = Field(
        None, description="Custom metadata included in webhook payloads."
    )
    events: Optional[List[MonitorWebhookEvent]] = Field(
        None,
        description="Monitor webhook events to receive. The server sends all monitor events when this is absent.",
    )


class MonitorEmailNotification(BaseModel):
    """Email notification settings for a monitor."""

    enabled: Optional[bool] = Field(None, description="Whether email notifications are enabled.")
    recipients: Optional[List[str]] = Field(
        None, max_length=25, description="Email recipients for monitor alerts."
    )
    include_diffs: Optional[bool] = Field(
        None, description="Include changed page details in email summaries."
    )


class MonitorNotification(BaseModel):
    """Notification destinations for a monitor."""

    email: Optional[MonitorEmailNotification] = Field(
        None, description="Email notification settings."
    )


class MonitorScrapeTarget(BaseModel):
    """Monitor target that scrapes one or more URLs on each check."""

    id: Optional[str] = Field(
        None, description="Optional stable ID for this target. Generated if omitted."
    )
    type_: Annotated[Literal["scrape"], Field(..., alias="type", description="Scrape target type.")]
    urls: List[str] = Field(..., min_length=1, description="URLs to scrape on each check.")
    scrape_options: Optional[ScrapeOptionsNested] = Field(
        None, description="Scrape options applied to each URL."
    )


class MonitorCrawlTarget(BaseModel):
    """Monitor target that crawls a site on each check."""

    id: Optional[str] = Field(
        None, description="Optional stable ID for this target. Generated if omitted."
    )
    type_: Annotated[Literal["crawl"], Field(..., alias="type", description="Crawl target type.")]
    url: str = Field(..., description="Root URL to crawl on each check.")
    crawl_options: Optional[CrawlTargetOptions] = Field(
        None, description="Crawl options such as limit and includePaths."
    )
    scrape_options: Optional[ScrapeOptionsNested] = Field(
        None, description="Scrape options applied to each crawled page."
    )


class MonitorSearchTarget(BaseModel):
    """Monitor target that runs web search queries on each check."""

    id: Optional[str] = Field(
        None, description="Optional stable ID for this target. Generated if omitted."
    )
    type_: Annotated[Literal["search"], Field(..., alias="type", description="Search target type.")]
    queries: List[str] = Field(
        ...,
        min_length=1,
        max_length=12,
        description="Search queries to run on each check (1-12).",
    )
    search_window: Optional[MonitorSearchWindow] = Field(
        None,
        description="Recency filter for search results. The server applies '24h' when this is absent.",
    )
    max_results: Optional[int] = Field(
        None,
        ge=1,
        le=50,
        description="Total results to evaluate per check. The server applies 10 when this is absent.",
    )
    include_domains: Optional[List[str]] = Field(
        None, max_length=50, description="Restrict results to these domains."
    )
    exclude_domains: Optional[List[str]] = Field(
        None, max_length=50, description="Drop results from these domains."
    )


MonitorTarget = Union[MonitorScrapeTarget, MonitorCrawlTarget, MonitorSearchTarget]


class MonitorCreateRequest(BaseModel):
    """Create a monitor that runs scrape, crawl, or search targets on a schedule.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-create
    """

    name: Annotated[str, Field(..., max_length=256, description="Monitor name."), Body()]
    schedule: Annotated[
        MonitorSchedule, Field(..., description="Schedule for monitor checks."), Body()
    ]
    targets: Annotated[
        List[MonitorTarget],
        Field(..., min_length=1, max_length=50, description="Targets to run on each check."),
        Body(),
    ]
    webhook: Annotated[
        Optional[MonitorWebhook],
        Field(None, description="Webhook destination for monitor events."),
        Body(),
    ]
    notification: Annotated[
        Optional[MonitorNotification], Field(None, description="Notification destinations."), Body()
    ]
    retention_days: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=365,
            description="How long to retain monitor history. The server applies 30 when this is absent.",
        ),
        Body(),
    ]
    goal: Annotated[
        Optional[str],
        Field(
            None,
            max_length=2000,
            description="Plain-language goal used to judge whether changed pages are meaningful.",
        ),
        Body(),
    ]
    judge_enabled: Annotated[
        Optional[bool],
        Field(None, description="Whether to judge changed pages against goal."),
        Body(),
    ]


class MonitorListRequest(BaseModel):
    """List monitors for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-list
    """

    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description="Maximum monitors to return. The server applies 25 when this is absent.",
        ),
        Query(),
    ]
    offset: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            description="Number of monitors to skip. The server applies 0 when this is absent.",
        ),
        Query(),
    ]


class MonitorGetRequest(BaseModel):
    """Get a monitor by ID.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-get
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]


class MonitorUpdateRequest(BaseModel):
    """Update a monitor. Include at least one field.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-update
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]
    name: Annotated[Optional[str], Field(None, max_length=256, description="Monitor name."), Body()]
    schedule: Annotated[
        Optional[MonitorSchedule], Field(None, description="Schedule for monitor checks."), Body()
    ]
    webhook: Annotated[
        Optional[MonitorWebhook],
        Field(None, description="Webhook destination for monitor events."),
        Body(),
    ]
    notification: Annotated[
        Optional[MonitorNotification], Field(None, description="Notification destinations."), Body()
    ]
    targets: Annotated[
        Optional[List[MonitorTarget]],
        Field(None, min_length=1, max_length=50, description="Targets to run on each check."),
        Body(),
    ]
    retention_days: Annotated[
        Optional[int],
        Field(None, ge=1, le=365, description="How long to retain monitor history."),
        Body(),
    ]
    goal: Annotated[
        Optional[str],
        Field(
            None,
            max_length=2000,
            description="Plain-language goal used to judge whether changed pages are meaningful.",
        ),
        Body(),
    ]
    judge_enabled: Annotated[
        Optional[bool],
        Field(None, description="Whether to judge changed pages against goal."),
        Body(),
    ]
    status: Annotated[
        Optional[Literal["active", "paused"]], Field(None, description="Monitor status."), Body()
    ]

    @model_validator(mode="after")
    def _at_least_one_field(self) -> MonitorUpdateRequest:
        if all(
            value is None
            for value in (
                self.name,
                self.schedule,
                self.webhook,
                self.notification,
                self.targets,
                self.retention_days,
                self.goal,
                self.judge_enabled,
                self.status,
            )
        ):
            raise ValueError("Include at least one field to update.")
        return self


class MonitorDeleteRequest(BaseModel):
    """Delete a monitor.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-delete
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]


class MonitorRunRequest(BaseModel):
    """Queue an immediate monitor check.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-run
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]


class MonitorChecksListRequest(BaseModel):
    """List checks for a monitor.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-checks-list
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]
    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description="Maximum checks to return. The server applies 25 when this is absent.",
        ),
        Query(),
    ]
    offset: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            description="Number of checks to skip. The server applies 0 when this is absent.",
        ),
        Query(),
    ]
    status: Annotated[
        Optional[MonitorCheckStatus],
        Field(None, description="Filter checks by status."),
        Query(),
    ]


class MonitorCheckGetRequest(BaseModel):
    """Get a monitor check with optional page results.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/monitor-check-get
    """

    monitor_id: Annotated[str, Field(..., description="The monitor ID"), Path()]
    check_id: Annotated[str, Field(..., description="The monitor check ID"), Path()]
    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description="Maximum page results to return. The server applies 25 when this is absent.",
        ),
        Query(),
    ]
    skip: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            description="Number of page results to skip. The server applies 0 when this is absent.",
        ),
        Query(),
    ]
    status: Annotated[
        Optional[MonitorPageStatus],
        Field(None, description="Filter page results by status."),
        Query(),
    ]
