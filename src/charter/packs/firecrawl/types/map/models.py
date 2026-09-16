"""Response models for the Firecrawl /map endpoint.

All fields use Mode("response_only") — they are populated by the API response
and never sent in requests. The LLM reads these rich typed models; the framework
handles wire-format conversion transparently.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/map
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Mode


class MapLink(BaseModel):
    """A single URL entry returned by the map endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/map
    """

    url: Annotated[
        str,
        Field(..., description="The URL of the mapped page."),
        Mode("response_only"),
    ]
    title: Annotated[
        Optional[str],
        Field(None, description="The title of the page, if available."),
        Mode("response_only"),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="A description of the page, if available."),
        Mode("response_only"),
    ]


class MapResponse(BaseModel):
    """Root response from the Firecrawl POST /map endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/map
    """

    success: Annotated[
        Optional[bool],
        Field(None, description="Whether the map request was successful."),
        Mode("response_only"),
    ]
    links: Annotated[
        Optional[List[MapLink]],
        Field(None, description="List of URLs discovered during the map operation."),
        Mode("response_only"),
    ]
