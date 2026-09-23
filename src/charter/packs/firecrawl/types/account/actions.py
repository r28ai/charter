# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Firecrawl team account and billing endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-activity
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Query

__all__ = [
    "ActivityListRequest",
    "CreditUsageGetRequest",
    "HistoricalCreditUsageGetRequest",
    "QueueStatusGetRequest",
    "TokenUsageGetRequest",
    "HistoricalTokenUsageGetRequest",
    "ThreatProtectionGetRequest",
    "ThreatProtectionUpdateRequest",
]

ActivityEndpoint = Literal[
    "scrape",
    "crawl",
    "batch_scrape",
    "search",
    "extract",
    "llmstxt",
    "deep_research",
    "map",
    "agent",
    "browser",
    "interact",
]
ThreatProtectionMode = Literal["off", "normal"]
ThreatProtectionFailurePolicy = Literal["open", "closed"]


class ActivityListRequest(BaseModel):
    """List recent API activity for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-activity
    """

    endpoint: Annotated[
        Optional[ActivityEndpoint],
        Field(None, description="Filter by endpoint."),
        Query(),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description="Maximum number of results per page. The server applies 50 when this is absent.",
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description="Cursor for pagination. Use the cursor value from the previous response.",
        ),
        Query(),
    ]


class CreditUsageGetRequest(BaseModel):
    """Get remaining credits for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-credit-usage
    """


class HistoricalCreditUsageGetRequest(BaseModel):
    """Get historical credit usage for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-credit-usage-historical
    """

    by_api_key: Annotated[
        Optional[bool],
        Field(None, description="Get historical credit usage by API key."),
        Query(),
    ]


class QueueStatusGetRequest(BaseModel):
    """Get metrics about the team's scrape queue.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-queue-status
    """


class TokenUsageGetRequest(BaseModel):
    """Get remaining extract tokens for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-token-usage
    """


class HistoricalTokenUsageGetRequest(BaseModel):
    """Get historical extract token usage for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-token-usage-historical
    """

    by_api_key: Annotated[
        Optional[bool],
        Field(None, description="Get historical token usage by API key."),
        Query(),
    ]


class ThreatProtectionGetRequest(BaseModel):
    """Get the team's threat protection policy.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-threat-protection-get
    """


class ThreatProtectionUpdateRequest(BaseModel):
    """Update the team's threat protection policy.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/team-threat-protection-update
    """

    mode: Annotated[
        ThreatProtectionMode,
        Field(..., description="Threat protection mode."),
        Body(),
    ]
    risk_score_threshold: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=100,
            description="Normalized score (0-100) at or above which a classifier verdict is blocked.",
        ),
        Body(),
    ]
    blacklist: Annotated[
        Optional[List[str]],
        Field(
            None, description="Exact domains or globs always blocked, without a classifier call."
        ),
        Body(),
    ]
    whitelist: Annotated[
        Optional[List[str]],
        Field(
            None, description="Exact domains or globs always allowed. Wins over every other rule."
        ),
        Body(),
    ]
    blocked_tlds: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Top-level domains to block outright, lowercase without a leading dot.",
        ),
        Body(),
    ]
    failure_policy: Annotated[
        Optional[ThreatProtectionFailurePolicy],
        Field(
            None,
            description="Behavior when the classifier is unreachable. The server applies 'closed' when this is absent.",
        ),
        Body(),
    ]
    allow_request_overrides: Annotated[
        Optional[bool],
        Field(None, description="Whether individual requests may pass a threatProtection object."),
        Body(),
    ]
