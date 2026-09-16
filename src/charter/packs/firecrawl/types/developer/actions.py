"""Request schemas for the Firecrawl developer index search endpoint.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/developer-search
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Query, WireName

__all__ = ["DeveloperSearchRequest"]

DeveloperResultType = Literal["doc", "issue", "pull_request", "readme"]


class DeveloperSearchRequest(BaseModel):
    """Search the Firecrawl developer index for docs, issues, pull requests, and readmes.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/developer-search
    """

    query: Annotated[str, Field(..., min_length=1, description="Natural-language question or search phrase."), Query()]
    k: Annotated[
        Optional[int],
        Field(None, ge=1, le=100, description="Number of ranked results to return. The server applies 10 when this is absent."),
        Query(),
    ]
    types: Annotated[
        Optional[List[DeveloperResultType]],
        Field(
            None,
            description="Result kinds to search. Defaults to all four when this is absent.",
        ),
        Query(),
    ]
    repos: Annotated[
        Optional[List[str]],
        Field(
            None,
            description="Repository slugs to scope repository results to, such as 'firecrawl/firecrawl'.",
        ),
        Query(),
    ]
    sources: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=20,
            description="Documentation source ids to scope documentation results to.",
        ),
        Query(),
    ]
    skills: Annotated[
        Optional[Literal["only"]],
        Field(None, description="Set to 'only' to limit the search to indexed agent-skill files."),
        Query(),
    ]
    passages: Annotated[
        Optional[int],
        Field(None, ge=1, le=5, description="Matched passages to return per result. The server applies 1 when this is absent."),
        Query(),
    ]
    language: Annotated[
        Optional[str],
        Field(None, description="Repository primary language filter for repository results."),
        Query(),
    ]
    topic: Annotated[
        Optional[str],
        Field(None, description="Repository topic filter for repository results."),
        Query(),
    ]
    license: Annotated[
        Optional[str],
        Field(None, description="Repository license filter for repository results."),
        Query(),
    ]
    min_stars: Annotated[
        Optional[int],
        Field(None, ge=0, description="Lower bound on repository stars for repository results."),
        Query(),
        WireName("min_stars"),
    ]
    max_stars: Annotated[
        Optional[int],
        Field(None, ge=0, description="Upper bound on repository stars for repository results."),
        Query(),
        WireName("max_stars"),
    ]
    archived: Annotated[
        Optional[bool],
        Field(None, description="Include or exclude archived repositories for repository results."),
        Query(),
    ]
    fork: Annotated[
        Optional[bool],
        Field(None, description="Include or exclude forks for repository results."),
        Query(),
    ]
