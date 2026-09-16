from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import AuditMetadata, ThreatProtectionOverride
from charter.types import Body, Gloss


class MapLocation(BaseModel):
    """Location settings applied to the map request.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/map
    """

    country: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{2}$",
        description="ISO 3166-1 alpha-2 country code (e.g., 'US', 'AU', 'DE', 'JP'). The server applies 'US' when this is absent.",
    )
    languages: Optional[List[str]] = Field(
        None,
        description="Preferred languages and locales for the request in order of priority.",
    )


class MapRequest(BaseModel):
    """Request schema for the Firecrawl POST /map endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/map
    """

    url: Annotated[
        str,
        Field(..., description="The base URL to start crawling from."),
        Body(),
    ]
    search: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specify a search query to order the results by relevance. "
                "Example: 'blog' will return URLs that contain the word 'blog' "
                "in the URL ordered by relevance."
            ),
        ),
        Body(),
    ]
    sitemap: Annotated[
        Optional[Literal["skip", "include", "only"]],
        Field(
            None,
            description=(
                "Sitemap mode when mapping. If you set it to `skip`, the sitemap "
                "won't be used to find URLs. If you set it to `only`, only URLs "
                "that are in the sitemap will be returned. The server applies `include` "
                "when this is absent."
            ),
        ),
        Body(),
    ]
    include_subdomains: Annotated[
        Optional[bool],
        Field(None, description="Include subdomains of the website. The server applies true when this is absent."),
        Body(),
    ]
    ignore_query_parameters: Annotated[
        Optional[bool],
        Field(None, description="Do not return URLs with query parameters. The server applies true when this is absent."),
        Body(),
    ]
    ignore_cache: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Bypass the sitemap cache to retrieve fresh URLs. Sitemap data is "
                "cached for up to 7 days; use this parameter when your sitemap has "
                "been recently updated."
            ),
        ),
        Body(),
    ]
    limit: Annotated[
        Optional[int],
        Field(None, le=100000, description="Maximum number of links to return. The server applies 5000 when this is absent."),
        Body(),
    ]
    timeout: Annotated[
        Optional[int],
        Field(None, description="Timeout in milliseconds. There is no timeout by default."),
        Gloss("Milliseconds, not seconds: 30000 is thirty seconds, and 30 fails instantly."),
        Body(),
    ]
    location: Annotated[
        Optional[MapLocation],
        Field(None, description="Location settings for the request."),
        Body(),
    ]
    audit_metadata: Annotated[
        Optional[AuditMetadata],
        Field(None, description="User attribution included with SIEM logging events when SIEM is enabled."),
        Body(),
    ]
    threat_protection: Annotated[
        Optional[ThreatProtectionOverride],
        Field(None, description="Per-request threat protection override. Enterprise feature."),
        Body(),
    ]
