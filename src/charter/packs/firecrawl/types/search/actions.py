from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import ScrapeOptionsNested, ThreatProtectionOverride
from charter.types import Body, ConflictsWith, Gloss, Path, WireName

__all__ = [
    "SearchSource",
    "SearchCategory",
    "SearchRequest",
    "ValuableSource",
    "MissingContent",
    "SearchFeedbackRequest",
]


class SearchSource(BaseModel):
    """A source to search. Determines which result arrays appear in the response.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """

    type_: Annotated[
        Literal["web", "images", "news"],
        Field(..., alias="type", description="The source type to search."),
    ]
    tbs: Optional[str] = Field(
        None,
        description=(
            "Time-based search parameter for web sources. Supports predefined time ranges "
            "(qdr:h, qdr:d, qdr:w, qdr:m, qdr:y), custom date ranges "
            "(cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY), and sort by date (sbd:1)."
        ),
    )
    location: Optional[str] = Field(
        None,
        description="Location parameter for web sources (e.g. San Francisco,California,United States).",
    )


class SearchCategory(BaseModel):
    """A category to filter search results by.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """

    type_: Annotated[
        Literal["developer", "research", "pdf"],
        Field(..., alias="type", description="The category type to filter results by."),
    ]


class SearchRequest(BaseModel):
    """Search the web using Firecrawl's /search endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """

    query: Annotated[
        str,
        Field(..., max_length=500, description="The search query"),
        Body(),
    ]
    limit: Annotated[
        Optional[int],
        Field(None, ge=1, le=100, description="Maximum number of results to return per source type. The server applies 10 when this is absent."),
        Body(),
    ]
    sources: Annotated[
        Optional[List[Union[Literal["web", "images", "news"], SearchSource]]],
        Field(
            None,
            description=(
                "Sources to search. Strings or objects. The documented default is ['web']; "
                "objects add source-specific options such as tbs and location."
            ),
        ),
        Body(),
    ]
    categories: Annotated[
        Optional[List[Union[Literal["developer", "research", "pdf"], SearchCategory]]],
        Field(
            None,
            description=(
                "Categories to filter results by. Strings or objects. "
                "The server applies no category filter when this is absent."
            ),
        ),
        Body(),
    ]
    include_domains: Annotated[
        Optional[List[str]],
        Field(None, description="Restricts search results to these hostnames. Cannot be used with excludeDomains."),
        Body(),
        ConflictsWith("exclude_domains", reason="Drop excludeDomains to restrict to includeDomains."),
    ]
    exclude_domains: Annotated[
        Optional[List[str]],
        Field(None, description="Excludes search results from these hostnames. Cannot be used with includeDomains."),
        Body(),
        ConflictsWith("include_domains", reason="Drop includeDomains to exclude domains."),
    ]
    tbs: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Time-based search parameter. Supports predefined time ranges "
                "(qdr:h, qdr:d, qdr:w, qdr:m, qdr:y), custom date ranges "
                "(cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY), and sort by date (sbd:1)."
            ),
        ),
        Body(),
    ]
    location: Annotated[
        Optional[str],
        Field(None, description="Location parameter for search results (e.g. San Francisco,California,United States)."),
        Body(),
    ]
    country: Annotated[
        Optional[str],
        Field(None, description="ISO country code for geo-targeting. The server applies US when this is absent."),
        Body(),
    ]
    safe: Annotated[
        Optional[bool],
        Field(None, description="When true, filters explicit content from search results (SafeSearch)."),
        Body(),
    ]
    timeout: Annotated[
        Optional[int],
        Field(None, description="Timeout in milliseconds. The server applies 60000 when this is absent."),
        Gloss("Milliseconds, not seconds: 30000 is thirty seconds, and 30 fails instantly."),
        Body(),
    ]
    ignore_invalid_urls: Annotated[
        Optional[bool],
        Field(None, description="Excludes URLs that are invalid for other Firecrawl endpoints."),
        Body(),
        WireName("ignoreInvalidURLs"),
    ]
    highlights: Annotated[
        Optional[bool],
        Field(None, description="Generate query-relevant highlights. The server applies true when this is absent."),
        Body(),
    ]
    enterprise: Annotated[
        Optional[List[Literal["anon", "zdr"]]],
        Field(None, description="Enterprise Zero Data Retention options. ['zdr'] is end-to-end ZDR; ['anon'] is anonymized ZDR."),
        Body(),
    ]
    scrape_options: Annotated[
        Optional[ScrapeOptionsNested],
        Field(None, description="Options for scraping search results"),
        Body(),
    ]
    threat_protection: Annotated[
        Optional[ThreatProtectionOverride],
        Field(None, description="Per-request threat protection override. Enterprise feature."),
        Body(),
    ]


class ValuableSource(BaseModel):
    """A search result source marked as valuable in feedback."""

    url: str = Field(..., description="URL of the valuable source.")
    reason: Optional[str] = Field(None, max_length=1000, description="Why this source was valuable.")


class MissingContent(BaseModel):
    """Content the search results failed to cover."""

    topic: str = Field(..., min_length=1, max_length=200, description="Topic that was missing from the results.")
    description: Optional[str] = Field(None, max_length=2000, description="Additional detail about what was missing.")


class SearchFeedbackRequest(BaseModel):
    """Submit feedback for a search job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search-feedback
    """

    job_id: Annotated[str, Field(..., description="Search job id returned by /search."), Path()]
    rating: Annotated[
        Literal["good", "partial", "bad"],
        Field(..., description="Overall rating for the search results."),
        Body(),
    ]
    valuable_sources: Annotated[
        Optional[List[ValuableSource]],
        Field(None, max_length=50, description="Sources that were especially useful."),
        Body(),
    ]
    missing_content: Annotated[
        Optional[List[MissingContent]],
        Field(None, max_length=20, description="Topics or content missing from the results."),
        Body(),
    ]
    query_suggestions: Annotated[
        Optional[str],
        Field(None, max_length=2000, description="Suggested alternative queries."),
        Body(),
    ]
    origin: Annotated[
        Optional[str],
        Field(None, description="Origin label for the feedback. The server applies 'api' when this is absent."),
        Body(),
    ]
    integration: Annotated[
        Optional[str],
        Field(None, description="Optional integration identifier."),
        Body(),
    ]
