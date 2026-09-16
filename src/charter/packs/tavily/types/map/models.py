"""Response models for Tavily POST /map.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/map
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import Usage
from charter.types import Mode


class MapResponse(BaseModel):
    """Root response from Tavily POST /map.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/map
    """

    base_url: Annotated[Optional[str], Field(None, description="Mapped root URL."), Mode("response_only")]
    results: Annotated[
        Optional[List[str]],
        Field(None, description="Discovered URLs."),
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
