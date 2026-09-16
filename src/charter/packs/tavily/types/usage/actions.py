"""Request schemas for Tavily usage and enterprise endpoints.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import LogEndpoint, OrgUsageDepth
from charter.types import Body

__all__ = ["UsageGetRequest", "LogsRequest", "OrgUsageRequest"]


class UsageGetRequest(BaseModel):
    """Get API key and account usage for the current billing cycle.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/usage
    """


class LogsRequest(BaseModel):
    """Retrieve per-request usage logs for API keys under your account.

    Requires an active paid plan or pay-as-you-go enabled. Log entries never
    include request input or output.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/logs
    """

    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=10000,
            description="Maximum logs to return, most recent first. The server applies 10 when this is absent.",
        ),
        Body(),
    ]
    start_date: Annotated[
        Optional[str],
        Field(None, description="Inclusive start date (`YYYY-MM-DD`)."),
        Body(),
    ]
    end_date: Annotated[
        Optional[str],
        Field(None, description="Inclusive end date (`YYYY-MM-DD`)."),
        Body(),
    ]
    endpoints: Annotated[
        Optional[List[LogEndpoint]],
        Field(
            None,
            description="Filter by endpoint. The server returns all endpoints when this is absent.",
        ),
        Body(),
    ]
    project_id: Annotated[
        Optional[str],
        Field(None, description="Filter to a single project."),
        Body(),
    ]
    filter_by_api_key: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "When true, return only logs for the Authorization header key. "
                "When false, return all keys under the account or organization."
            ),
        ),
        Body(),
    ]


class OrgUsageRequest(BaseModel):
    """Retrieve organization-wide usage, PayGo cost, and request counts.

    Authenticate with the organization owner's personal API key, not an
    organization or enterprise key.

    API Reference: https://docs.tavily.com/documentation/enterprise/org-usage
    """

    organization_name: Annotated[
        str,
        Field(..., description="Exact case-sensitive organization name."),
        Body(),
    ]
    start_date: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Inclusive start date (`YYYY-MM-DD`). The server applies the "
                "start of the current billing cycle when this is absent."
            ),
        ),
        Body(),
    ]
    end_date: Annotated[
        Optional[str],
        Field(
            None,
            description="Inclusive end date (`YYYY-MM-DD`). The server applies today when this is absent.",
        ),
        Body(),
    ]
    project_id: Annotated[
        Optional[str],
        Field(None, description="Scope results to a single project."),
        Body(),
    ]
    depth: Annotated[
        Optional[OrgUsageDepth],
        Field(None, description="Scope results to a single request depth."),
        Body(),
    ]
