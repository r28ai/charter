# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schema for Tavily POST /map.

API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/map
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body

__all__ = ["MapRequest"]


class MapRequest(BaseModel):
    """Traverse a site like a graph to generate a comprehensive site map.

    API Reference: https://docs.tavily.com/documentation/api-reference/endpoint/map
    """

    url: Annotated[
        str,
        Field(..., description="Root URL to begin mapping."),
        Body(),
    ]
    instructions: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Natural language instructions for mapping. Doubles cost to 2 "
                "credits per 10 pages when set."
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
            description="Maximum mapping depth. The server applies 1 when this is absent.",
        ),
        Body(),
    ]
    max_breadth: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=500,
            description="Maximum links per level. The server applies 20 when this is absent.",
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
        Field(None, description="Regex path patterns to include."),
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
