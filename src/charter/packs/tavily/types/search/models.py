"""Response models for Tavily POST /search.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import SearchImage, Usage
from charter.types import Mode


class SearchResult(BaseModel):
    """A single search result sorted by relevancy.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
    """

    title: Annotated[Optional[str], Field(None, description="Result title."), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="Result URL."), Mode("response_only")]
    content: Annotated[
        Optional[str],
        Field(None, description="Short description or chunked snippets."),
        Mode("response_only"),
    ]
    score: Annotated[
        Optional[float],
        Field(None, description="Relevance score."),
        Mode("response_only"),
    ]
    raw_content: Annotated[
        Optional[str],
        Field(None, description="Full page content when `include_raw_content` was requested."),
        Mode("response_only"),
    ]
    published_date: Annotated[
        Optional[str],
        Field(None, description="Publish date when `include_published_date` was requested."),
        Mode("response_only"),
    ]
    favicon: Annotated[
        Optional[str],
        Field(None, description="Favicon URL when `include_favicon` was requested."),
        Mode("response_only"),
    ]
    images: Annotated[
        Optional[List[SearchImage]],
        Field(None, description="Per-result images when `include_images` was requested."),
        Mode("response_only"),
    ]
    id: Annotated[
        Optional[str],
        Field(None, description="Unique result identifier."),
        Mode("response_only"),
    ]


class SearchResponse(BaseModel):
    """Root response from Tavily POST /search.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
    """

    query: Annotated[Optional[str], Field(None, description="Echo of the executed query."), Mode("response_only")]
    answer: Annotated[
        Optional[str],
        Field(None, description="LLM-generated answer when `include_answer` was requested."),
        Mode("response_only"),
    ]
    images: Annotated[
        Optional[List[SearchImage]],
        Field(None, description="Query-related images when `include_images` was requested."),
        Mode("response_only"),
    ]
    results: Annotated[
        Optional[List[SearchResult]],
        Field(None, description="Search results sorted by relevancy."),
        Mode("response_only"),
    ]
    auto_parameters: Annotated[
        Optional[Dict[str, Any]],
        Field(None, description="Auto-selected parameters when `auto_parameters` was true."),
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
        Field(None, description="Support and debug identifier."),
        Mode("response_only"),
    ]
