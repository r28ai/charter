"""Request schemas for Firecrawl research paper index endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/research-search-papers
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Path, Query, WireName

__all__ = [
    "ResearchPapersSearchRequest",
    "ResearchPaperGetRequest",
    "ResearchSimilarPapersRequest",
]

ResearchSimilarMode = Literal["similar", "citers", "references"]


class ResearchPapersSearchRequest(BaseModel):
    """Search the research paper index.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/research-search-papers
    """

    query: Annotated[str, Field(..., min_length=1, description="Natural-language paper search query."), Query()]
    k: Annotated[
        Optional[int],
        Field(None, ge=1, le=500, description="Maximum number of ranked papers to return. The server applies 40 when this is absent."),
        Query(),
    ]
    authors: Annotated[
        Optional[str],
        Field(None, description="Author substring filter. Repeat or pass a comma-separated value."),
        Query(),
    ]
    categories: Annotated[
        Optional[str],
        Field(None, description="Paper category filter. Repeat or pass a comma-separated value."),
        Query(),
    ]
    from_: Annotated[
        Optional[str],
        Field(None, description="Inclusive lower bound on created/updated date."),
        Query(),
        WireName("from"),
    ]
    to: Annotated[
        Optional[str],
        Field(None, description="Inclusive upper bound on created/updated date."),
        Query(),
    ]


class ResearchPaperGetRequest(BaseModel):
    """Inspect or read a paper from the research index.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/research-get-paper
    """

    id: Annotated[str, Field(..., description="Paper reference: a canonical paperId or source-specific primaryId."), Path()]
    query: Annotated[
        Optional[str],
        Field(None, min_length=1, description="When present, returns top matching full-text passages for this question."),
        Query(),
    ]
    k: Annotated[
        Optional[int],
        Field(None, ge=1, le=50, description="Passage count for read mode. Only valid when query is present. The server applies 4 when this is absent."),
        Query(),
    ]


class ResearchSimilarPapersRequest(BaseModel):
    """Find related papers from the research index.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/research-related-papers
    """

    id: Annotated[str, Field(..., description="Primary seed paper reference."), Path()]
    intent: Annotated[
        str,
        Field(..., min_length=1, description="Natural-language ranking/filtering intent used for semantic ranking."),
        Query(),
    ]
    mode: Annotated[
        Optional[ResearchSimilarMode],
        Field(None, description="Structural expansion mode. The server applies 'similar' when this is absent."),
        Query(),
    ]
    k: Annotated[
        Optional[int],
        Field(None, ge=1, le=500, description="Maximum number of related papers to return. The server applies 40 when this is absent."),
        Query(),
    ]
    rerank: Annotated[
        Optional[bool],
        Field(None, description="Apply an additional rerank over fused candidates."),
        Query(),
    ]
    anchor: Annotated[
        Optional[str],
        Field(None, description="Additional seed paper reference. Repeat this parameter for multiple anchors."),
        Query(),
    ]
