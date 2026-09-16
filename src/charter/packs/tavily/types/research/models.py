"""Response models for Tavily research endpoints.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research-get
"""

from __future__ import annotations

from typing import Annotated, Any, List, Optional, Union

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import ResearchStatus, Usage
from charter.types import Mode


class ResearchSource(BaseModel):
    """A source cited in a completed research report.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research-get
    """

    title: Annotated[Optional[str], Field(None, description="Source title."), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="Source URL."), Mode("response_only")]
    favicon: Annotated[
        Optional[str],
        Field(None, description="Source favicon URL."),
        Mode("response_only"),
    ]


class ResearchCreateResponse(BaseModel):
    """Response from Tavily POST /research (non-streaming).

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research
    """

    request_id: Annotated[
        Optional[str],
        Field(None, description="Task identifier for polling."),
        Mode("response_only"),
    ]
    created_at: Annotated[
        Optional[str],
        Field(None, description="Task creation timestamp."),
        Mode("response_only"),
    ]
    status: Annotated[
        Optional[ResearchStatus],
        Field(None, description="Task status."),
        Mode("response_only"),
    ]
    input: Annotated[
        Optional[str],
        Field(None, description="Echo of the research input."),
        Mode("response_only"),
    ]
    model: Annotated[
        Optional[str],
        Field(None, description="Resolved model tier."),
        Mode("response_only"),
    ]
    response_time: Annotated[
        Optional[int],
        Field(None, description="Request duration in seconds."),
        Mode("response_only"),
    ]


class ResearchGetResponse(BaseModel):
    """Response from Tavily GET /research/{request_id}.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/research-get
    """

    request_id: Annotated[
        Optional[str],
        Field(None, description="Task identifier."),
        Mode("response_only"),
    ]
    created_at: Annotated[
        Optional[str],
        Field(None, description="Task creation timestamp."),
        Mode("response_only"),
    ]
    status: Annotated[
        Optional[ResearchStatus],
        Field(None, description="Task status."),
        Mode("response_only"),
    ]
    content: Annotated[
        Optional[Union[str, dict[str, Any]]],
        Field(
            None,
            description="Report text, or structured object when `output_schema` was used.",
        ),
        Mode("response_only"),
    ]
    sources: Annotated[
        Optional[List[ResearchSource]],
        Field(None, description="Sources used in the report."),
        Mode("response_only"),
    ]
    response_time: Annotated[
        Optional[int],
        Field(None, description="Request duration in seconds."),
        Mode("response_only"),
    ]
    usage: Annotated[
        Optional[Usage],
        Field(None, description="Credit usage when `include_usage` was requested."),
        Mode("response_only"),
    ]
