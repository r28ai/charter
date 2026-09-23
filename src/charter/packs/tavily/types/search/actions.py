# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schema for Tavily POST /search.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.tavily.types.common import (
    Country,
    IncludeAnswer,
    IncludeDomainsMode,
    IncludeRawContent,
    SearchDepth,
    TimeRange,
    Topic,
)
from charter.types import Body

__all__ = ["SearchRequest"]


class SearchRequest(BaseModel):
    """Execute a real-time web search optimized for AI agents.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/search
    """

    query: Annotated[
        str,
        Field(..., description="Search query to execute."),
        Body(),
    ]
    search_depth: Annotated[
        Optional[SearchDepth],
        Field(
            None,
            description=(
                "Latency/relevance tradeoff. The server applies `basic` when this "
                "is absent. `advanced` costs 2 credits; `basic`, `fast` and "
                "`ultra-fast` cost 1 credit."
            ),
        ),
        Body(),
    ]
    chunks_per_source: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=3,
            description=(
                "Maximum relevant chunks per source in each result's `content`. "
                "The server applies 3 when this is absent. Available only when "
                "`search_depth` is `advanced`, `basic` or `fast`. Each chunk is "
                "at most 500 characters and joined with `[...]`."
            ),
        ),
        Body(),
    ]
    max_results: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            le=20,
            description="Maximum search results to return. The server applies 10 when this is absent.",
        ),
        Body(),
    ]
    topic: Annotated[
        Optional[Topic],
        Field(
            None,
            description=(
                "Search category. The server applies `general` when this is absent. "
                "`news` automatically enables `include_published_date`."
            ),
        ),
        Body(),
    ]
    time_range: Annotated[
        Optional[TimeRange],
        Field(
            None,
            description="Filter by publish or last-updated date window.",
        ),
        Body(),
    ]
    start_date: Annotated[
        Optional[str],
        Field(
            None,
            description="Return results after this date (`YYYY-MM-DD`).",
        ),
        Body(),
    ]
    end_date: Annotated[
        Optional[str],
        Field(
            None,
            description="Return results before this date (`YYYY-MM-DD`).",
        ),
        Body(),
    ]
    include_published_date: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Include `published_date` on each result. Beta feature. "
                "Automatically enabled when `topic` is `news`."
            ),
        ),
        Body(),
    ]
    filter_by_published_date: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Remove results outside the date window or with no detectable "
                "date. Also enables `include_published_date`."
            ),
        ),
        Body(),
    ]
    include_answer: Annotated[
        Optional[IncludeAnswer],
        Field(
            None,
            description=(
                "Include an LLM-generated answer. `true` or `basic` returns a "
                "quick answer; `advanced` returns a detailed answer. The server "
                "applies `false` when this is absent."
            ),
        ),
        Body(),
    ]
    include_raw_content: Annotated[
        Optional[IncludeRawContent],
        Field(
            None,
            description=(
                "Include cleaned page content per result. `true` or `markdown` "
                "returns markdown; `text` returns plain text and may increase "
                "latency. The server applies `false` when this is absent."
            ),
        ),
        Body(),
    ]
    include_images: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include query-related images and per-result `images`.",
        ),
        Body(),
    ]
    include_image_descriptions: Annotated[
        Optional[bool],
        Field(
            None,
            description="Add descriptive text per image when `include_images` is true.",
        ),
        Body(),
    ]
    include_favicon: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include a favicon URL per result.",
        ),
        Body(),
    ]
    include_domains: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=300,
            description="Domains to include (max 300).",
        ),
        Body(),
    ]
    exclude_domains: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=150,
            description="Domains to exclude (max 150).",
        ),
        Body(),
    ]
    include_domains_mode: Annotated[
        Optional[IncludeDomainsMode],
        Field(
            None,
            description=("How `include_domains` is applied. Requires `include_domains` to be set."),
        ),
        Body(),
    ]
    country: Annotated[
        Optional[Country],
        Field(
            None,
            description=(
                "Boost results from a country using Tavily's lowercase English "
                "country name (for example `united states`). Available only "
                "when `topic` is `general`."
            ),
        ),
        Body(),
    ]
    language: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Boost or filter results by language — an ISO 639-1 code "
                "(for example `en`, `fr`, `zh-cn`) or English language name "
                "(for example `english`, `french`)."
            ),
        ),
        Body(),
    ]
    filter_by_language: Annotated[
        Optional[bool],
        Field(
            None,
            description=("Strictly filter out non-matching languages. Requires `language`."),
        ),
        Body(),
    ]
    auto_parameters: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Let Tavily configure parameters from the query. Explicit values "
                "override auto-selected ones. `include_answer`, "
                "`include_raw_content` and `max_results` must always be set "
                "manually when using this."
            ),
        ),
        Body(),
    ]
    exact_match: Annotated[
        Optional[bool],
        Field(
            None,
            description="Return only results containing the exact quoted phrase(s) in the query.",
        ),
        Body(),
    ]
    include_usage: Annotated[
        Optional[bool],
        Field(
            None,
            description="Include credit usage in the response.",
        ),
        Body(),
    ]
    safe_search: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Filter adult or unsafe content. Not supported when "
                "`search_depth` is `fast` or `ultra-fast`."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _cross_field_rules(self) -> SearchRequest:
        if self.include_domains_mode is not None and not self.include_domains:
            raise ValueError("include_domains_mode requires include_domains.")
        if self.filter_by_language and not self.language:
            raise ValueError("filter_by_language requires language.")
        if self.country is not None and self.topic not in (None, "general"):
            raise ValueError("country is available only when topic is general.")
        if self.chunks_per_source is not None and self.search_depth in ("ultra-fast",):
            raise ValueError("chunks_per_source is unavailable when search_depth is ultra-fast.")
        if self.safe_search and self.search_depth in ("fast", "ultra-fast"):
            raise ValueError(
                "safe_search is not supported when search_depth is fast or ultra-fast."
            )
        return self
