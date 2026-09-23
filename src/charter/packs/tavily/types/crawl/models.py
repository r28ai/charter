# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Response models for Tavily POST /crawl.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/crawl
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import Usage
from charter.types import Mode


class CrawlResult(BaseModel):
    """An extracted page from a crawl.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/crawl
    """

    url: Annotated[Optional[str], Field(None, description="Crawled URL."), Mode("response_only")]
    raw_content: Annotated[
        Optional[str],
        Field(None, description="Extracted page content."),
        Mode("response_only"),
    ]
    favicon: Annotated[
        Optional[str],
        Field(None, description="Favicon URL when `include_favicon` was requested."),
        Mode("response_only"),
    ]
    images: Annotated[
        Optional[List[str]],
        Field(None, description="Image URLs when `include_images` was requested."),
        Mode("response_only"),
    ]


class CrawlResponse(BaseModel):
    """Root response from Tavily POST /crawl.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/crawl
    """

    base_url: Annotated[
        Optional[str], Field(None, description="Crawled root URL."), Mode("response_only")
    ]
    results: Annotated[
        Optional[List[CrawlResult]],
        Field(None, description="Extracted pages."),
        Mode("response_only"),
    ]
    response_time: Annotated[
        Optional[float],
        Field(None, description="Request duration in seconds."),
        Mode("response_only"),
    ]
    usage: Annotated[
        Optional[Usage],
        Field(None, description="Credit usage when `include_usage` was requested."),
        Mode("response_only"),
    ]
    request_id: Annotated[
        Optional[str],
        Field(None, description="Support identifier."),
        Mode("response_only"),
    ]
