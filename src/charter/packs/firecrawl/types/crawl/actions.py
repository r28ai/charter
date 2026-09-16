"""Request schemas for Firecrawl crawl endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import ScrapeOptionsNested, Webhook
from charter.types import Body, Path, WireName

__all__ = [
    "CrawlRequest",
    "CrawlStatusRequest",
    "CrawlCancelRequest",
    "CrawlErrorsRequest",
    "CrawlParamsPreviewRequest",
    "CrawlActiveRequest",
]


class CrawlRequest(BaseModel):
    """Recursively crawl a website and scrape each page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl
    """

    url: Annotated[str, Field(..., description="The base URL to start crawling from"), Body()]
    prompt: Annotated[
        Optional[str],
        Field(None, description="Natural language prompt to generate crawler options from."),
        Body(),
    ]
    exclude_paths: Annotated[
        Optional[List[str]],
        Field(None, max_length=1000, description="URL pathname regex patterns that exclude matching URLs from the crawl."),
        Body(),
    ]
    include_paths: Annotated[
        Optional[List[str]],
        Field(None, max_length=1000, description="URL pathname regex patterns that include matching URLs in the crawl."),
        Body(),
    ]
    max_discovery_depth: Annotated[
        Optional[int],
        Field(None, description="Maximum depth to crawl based on discovery order."),
        Body(),
    ]
    sitemap: Annotated[
        Optional[Literal["skip", "include", "only"]],
        Field(None, description="Sitemap mode when crawling. The server applies 'include' when this is absent."),
        Body(),
    ]
    ignore_query_parameters: Annotated[
        Optional[bool],
        Field(None, description="Do not re-scrape the same path with different query parameters."),
        Body(),
    ]
    regex_on_full_url: Annotated[
        Optional[bool],
        Field(None, description="Match includePaths and excludePaths against the full URL instead of just the pathname."),
        Body(),
        WireName("regexOnFullURL"),
    ]
    limit: Annotated[
        Optional[int],
        Field(None, description="Maximum number of pages to crawl. The server applies 10000 when this is absent."),
        Body(),
    ]
    crawl_entire_domain: Annotated[
        Optional[bool],
        Field(None, description="Allow the crawler to follow internal links to sibling or parent URLs, not just child paths."),
        Body(),
    ]
    allow_external_links: Annotated[
        Optional[bool],
        Field(None, description="Allow the crawler to follow links to external websites (one hop only)."),
        Body(),
    ]
    allow_subdomains: Annotated[
        Optional[bool],
        Field(None, description="Allow the crawler to follow links to subdomains of the main domain."),
        Body(),
    ]
    ignore_robots_txt: Annotated[
        Optional[bool],
        Field(None, description="Ignore the website's robots.txt rules. Enterprise only."),
        Body(),
    ]
    robots_user_agent: Annotated[
        Optional[str],
        Field(None, description="Custom User-Agent string for robots.txt evaluation. Enterprise only."),
        Body(),
    ]
    delay: Annotated[
        Optional[float],
        Field(None, description="Delay in seconds between scrapes. Setting this forces concurrency to 1."),
        Body(),
    ]
    max_concurrency: Annotated[
        Optional[int],
        Field(None, description="Maximum number of concurrent scrapes for this crawl."),
        Body(),
    ]
    webhook: Annotated[
        Optional[Webhook],
        Field(None, description="Webhook specification for crawl lifecycle events."),
        Body(),
    ]
    scrape_options: Annotated[
        Optional[ScrapeOptionsNested],
        Field(None, description="Options applied when scraping each crawled page."),
        Body(),
    ]
    zero_data_retention: Annotated[
        Optional[bool],
        Field(None, description="If true, this will enable zero data retention for this crawl."),
        Body(),
    ]


class CrawlStatusRequest(BaseModel):
    """Get the status of a crawl job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl-get
    """

    id: Annotated[str, Field(..., description="The ID of the crawl job"), Path()]


class CrawlCancelRequest(BaseModel):
    """Cancel a crawl job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl-delete
    """

    id: Annotated[str, Field(..., description="The ID of the crawl job"), Path()]


class CrawlErrorsRequest(BaseModel):
    """Get errors from a crawl job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl-get-errors
    """

    id: Annotated[str, Field(..., description="The ID of the crawl job"), Path()]


class CrawlParamsPreviewRequest(BaseModel):
    """Preview crawl parameters generated from a natural language prompt.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl-params-preview
    """

    url: Annotated[str, Field(..., description="The URL to crawl"), Body()]
    prompt: Annotated[
        str,
        Field(..., max_length=10000, description="Natural language prompt describing what you want to crawl"),
        Body(),
    ]


class CrawlActiveRequest(BaseModel):
    """Get all active crawls for the authenticated team.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/crawl-active
    """
