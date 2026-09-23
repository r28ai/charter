# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schema for Tavily POST /crawl.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/crawl
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.tavily.types.common import ContentFormat, ExtractDepth
from charter.types import Body

__all__ = ["CrawlRequest"]


class CrawlRequest(BaseModel):
    """Graph-based website traversal with built-in extraction.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/crawl
    """

    url: Annotated[
        str,
        Field(..., description="Root URL to begin the crawl."),
        Body(),
    ]
    instructions: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Natural language instructions for the crawler. Doubles cost to "
                "2 credits per 10 pages when set."
            ),
        ),
        Body(),
    ]
    chunks_per_source: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=5,
            description=(
                "Maximum chunks in each page's `raw_content`. The server applies 3 "
                "when this is absent. Available only when `instructions` is provided."
            ),
        ),
        Body(),
    ]
    max_depth: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=5,
            description="Maximum crawl depth from the base URL. The server applies 1 when this is absent.",
        ),
        Body(),
    ]
    max_breadth: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=500,
            description="Maximum links per tree level. The server applies 20 when this is absent.",
        ),
        Body(),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description="Total links processed before stopping. The server applies 50 when this is absent.",
        ),
        Body(),
    ]
    select_paths: Annotated[
        Optional[List[str]],
        Field(None, description="Regex path patterns to include (for example `/docs/.*`)."),
        Body(),
    ]
    select_domains: Annotated[
        Optional[List[str]],
        Field(None, description="Regex domain or subdomain patterns to include."),
        Body(),
    ]
    exclude_paths: Annotated[
        Optional[List[str]],
        Field(None, description="Regex path patterns to exclude."),
        Body(),
    ]
    exclude_domains: Annotated[
        Optional[List[str]],
        Field(None, description="Regex domain or subdomain patterns to exclude."),
        Body(),
    ]
    allow_external: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include external domain links in results. The server applies true when this is absent.",
        ),
        Body(),
    ]
    include_images: Annotated[
        Optional[bool],
        Field(None, description="Include images in crawl results."),
        Body(),
    ]
    extract_depth: Annotated[
        Optional[ExtractDepth],
        Field(
            None,
            description="Page extraction depth. The server applies `basic` when this is absent.",
        ),
        Body(),
    ]
    format: Annotated[
        Optional[ContentFormat],
        Field(
            None,
            description="Extracted content format. The server applies `markdown` when this is absent.",
        ),
        Body(),
    ]
    include_favicon: Annotated[
        Optional[bool],
        Field(None, description="Include favicon URL per result."),
        Body(),
    ]
    timeout: Annotated[
        Optional[float],
        Field(
            None,
            ge=10.0,
            le=150.0,
            description="Maximum wait in seconds. The server applies 150 when this is absent.",
        ),
        Body(),
    ]
    include_usage: Annotated[
        Optional[bool],
        Field(None, description="Include credit usage in the response."),
        Body(),
    ]

    @model_validator(mode="after")
    def _cross_field_rules(self) -> CrawlRequest:
        if self.chunks_per_source is not None and not self.instructions:
            raise ValueError("chunks_per_source requires instructions.")
        return self
