"""Response models for Tavily usage endpoints.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import LogEndpoint
from charter.types import Mode


class KeyUsage(BaseModel):
    """Usage for the authenticated API key.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
    """

    usage: Annotated[
        Optional[int],
        Field(None, description="Total credits used this billing cycle."),
        Mode("response_only"),
    ]
    limit: Annotated[
        Optional[int],
        Field(None, description="Key usage limit; null when unlimited."),
        Mode("response_only"),
    ]
    search_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    extract_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    crawl_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    map_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    research_usage: Annotated[Optional[int], Field(None), Mode("response_only")]


class AccountUsage(BaseModel):
    """Account-level plan and usage.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
    """

    current_plan: Annotated[Optional[str], Field(None), Mode("response_only")]
    plan_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    plan_limit: Annotated[Optional[int], Field(None), Mode("response_only")]
    paygo_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    paygo_limit: Annotated[Optional[int], Field(None), Mode("response_only")]
    search_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    extract_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    crawl_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    map_usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    research_usage: Annotated[Optional[int], Field(None), Mode("response_only")]


class UsageResponse(BaseModel):
    """Root response from Tavily GET /usage.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
    """

    key: Annotated[Optional[KeyUsage], Field(None), Mode("response_only")]
    account: Annotated[Optional[AccountUsage], Field(None), Mode("response_only")]


class LogEntry(BaseModel):
    """One usage log entry.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/logs
    """

    timestamp: Annotated[Optional[str], Field(None), Mode("response_only")]
    endpoint: Annotated[Optional[LogEndpoint], Field(None), Mode("response_only")]
    depth: Annotated[Optional[str], Field(None), Mode("response_only")]
    response_time: Annotated[Optional[float], Field(None), Mode("response_only")]
    credits: Annotated[Optional[float], Field(None), Mode("response_only")]
    api_key: Annotated[Optional[str], Field(None), Mode("response_only")]
    request_id: Annotated[Optional[str], Field(None), Mode("response_only")]


class LogsResponse(BaseModel):
    """Root response from Tavily POST /logs.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/logs
    """

    logs: Annotated[Optional[List[LogEntry]], Field(None), Mode("response_only")]
    count: Annotated[Optional[int], Field(None), Mode("response_only")]
    response_time: Annotated[Optional[float], Field(None), Mode("response_only")]
    request_id: Annotated[Optional[str], Field(None), Mode("response_only")]


class UsageMetrics(BaseModel):
    """Per-endpoint usage breakdown.

    API Reference: https://docs.tavily.com/documentation/enterprise/org-usage
    """

    usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    paygo_cost_usd: Annotated[Optional[float], Field(None), Mode("response_only")]
    request_count: Annotated[Optional[int], Field(None), Mode("response_only")]


class OrgUsageFilters(BaseModel):
    """Applied filters echoed in an org usage response."""

    start_date: Annotated[Optional[str], Field(None), Mode("response_only")]
    end_date: Annotated[Optional[str], Field(None), Mode("response_only")]
    project_id: Annotated[Optional[str], Field(None), Mode("response_only")]
    depth: Annotated[Optional[str], Field(None), Mode("response_only")]


class OrganizationInfo(BaseModel):
    """Organization metadata in an org usage response."""

    name: Annotated[Optional[str], Field(None), Mode("response_only")]
    filters: Annotated[Optional[OrgUsageFilters], Field(None), Mode("response_only")]


class OrgUsageByType(BaseModel):
    """Per-endpoint totals for an organization or key."""

    search: Annotated[Optional[UsageMetrics], Field(None), Mode("response_only")]
    crawl: Annotated[Optional[UsageMetrics], Field(None), Mode("response_only")]
    extract: Annotated[Optional[UsageMetrics], Field(None), Mode("response_only")]
    map: Annotated[Optional[UsageMetrics], Field(None), Mode("response_only")]
    research: Annotated[Optional[UsageMetrics], Field(None), Mode("response_only")]


class OrgUsageTotals(BaseModel):
    """Aggregated usage across all organization keys."""

    usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    paygo_cost_usd: Annotated[Optional[float], Field(None), Mode("response_only")]
    request_count: Annotated[Optional[int], Field(None), Mode("response_only")]
    by_type: Annotated[Optional[OrgUsageByType], Field(None), Mode("response_only")]


class OrgKeyUsage(BaseModel):
    """Per-key usage breakdown."""

    key: Annotated[Optional[str], Field(None), Mode("response_only")]
    name: Annotated[Optional[str], Field(None), Mode("response_only")]
    usage: Annotated[Optional[int], Field(None), Mode("response_only")]
    paygo_cost_usd: Annotated[Optional[float], Field(None), Mode("response_only")]
    request_count: Annotated[Optional[int], Field(None), Mode("response_only")]
    by_type: Annotated[Optional[OrgUsageByType], Field(None), Mode("response_only")]


class OrgUsageResponse(BaseModel):
    """Root response from Tavily POST /org-usage.

    API Reference: https://docs.tavily.com/documentation/enterprise/org-usage
    """

    organization: Annotated[Optional[OrganizationInfo], Field(None), Mode("response_only")]
    totals: Annotated[Optional[OrgUsageTotals], Field(None), Mode("response_only")]
    keys: Annotated[Optional[List[OrgKeyUsage]], Field(None), Mode("response_only")]
