# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Response models for Tavily POST /extract.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.tavily.types.common import Usage
from charter.types import Mode


class ExtractResult(BaseModel):
    """A successful URL extraction.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
    """

    url: Annotated[Optional[str], Field(None, description="Source URL."), Mode("response_only")]
    raw_content: Annotated[
        Optional[str],
        Field(None, description="Extracted content or top chunks joined by `[...]`."),
        Mode("response_only"),
    ]
    images: Annotated[
        Optional[List[str]],
        Field(None, description="Image URLs when `include_images` was requested."),
        Mode("response_only"),
    ]
    favicon: Annotated[
        Optional[str],
        Field(None, description="Favicon URL when `include_favicon` was requested."),
        Mode("response_only"),
    ]


class FailedExtractResult(BaseModel):
    """A URL that could not be extracted.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
    """

    url: Annotated[Optional[str], Field(None, description="Failed URL."), Mode("response_only")]
    error: Annotated[
        Optional[str], Field(None, description="Failure reason."), Mode("response_only")
    ]


class ExtractResponse(BaseModel):
    """Root response from Tavily POST /extract.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/extract
    """

    results: Annotated[
        Optional[List[ExtractResult]],
        Field(None, description="Successful extractions."),
        Mode("response_only"),
    ]
    failed_results: Annotated[
        Optional[List[FailedExtractResult]],
        Field(None, description="URLs that could not be processed."),
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
