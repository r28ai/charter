"""Request schema for Tavily POST /extract.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
"""

from __future__ import annotations

from typing import Annotated, List, Optional, Union

from pydantic import BaseModel, Field, model_validator

from charter.packs.tavily.types.common import ContentFormat, ExtractDepth
from charter.types import Body

__all__ = ["ExtractRequest"]


class ExtractRequest(BaseModel):
    """Extract clean content from one or more URLs.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
    """

    urls: Annotated[
        Union[str, List[str]],
        Field(..., description="Single URL or list of URLs to extract (max 20)."),
        Body(),
    ]
    query: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "User intent for reranking chunks. When provided, chunks are "
                "reranked and joined in `raw_content`."
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
                "Maximum chunks per source in `raw_content`. The server applies 3 "
                "when this is absent. Available only when `query` is provided."
            ),
        ),
        Body(),
    ]
    extract_depth: Annotated[
        Optional[ExtractDepth],
        Field(
            None,
            description=(
                "Extraction depth. The server applies `basic` when this is absent. "
                "`basic` costs 1 credit per 5 successful extractions; `advanced` "
                "costs 2 per 5."
            ),
        ),
        Body(),
    ]
    include_images: Annotated[
        Optional[bool],
        Field(None, description="Include image URL list per result."),
        Body(),
    ]
    include_favicon: Annotated[
        Optional[bool],
        Field(None, description="Include favicon URL per result."),
        Body(),
    ]
    format: Annotated[
        Optional[ContentFormat],
        Field(
            None,
            description="Output format for extracted content. The server applies `markdown` when this is absent.",
        ),
        Body(),
    ]
    timeout: Annotated[
        Optional[float],
        Field(
            None,
            ge=1.0,
            le=60.0,
            description=(
                "Maximum wait in seconds. The server applies 10 for `basic` and 30 "
                "for `advanced` when this is absent."
            ),
        ),
        Body(),
    ]
    include_usage: Annotated[
        Optional[bool],
        Field(None, description="Include credit usage in the response."),
        Body(),
    ]

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ExtractRequest:
        if self.chunks_per_source is not None and not self.query:
            raise ValueError("chunks_per_source requires query.")
        if isinstance(self.urls, list) and len(self.urls) > 20:
            raise ValueError("urls accepts at most 20 entries.")
        return self
