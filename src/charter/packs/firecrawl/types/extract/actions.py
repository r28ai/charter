"""Request schemas for Firecrawl extract endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/extract
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import ScrapeOptionsNested, ThreatProtectionOverride
from charter.types import Body, Path, WireName

__all__ = [
    "ExtractRequest",
    "ExtractStatusRequest",
]


class ExtractRequest(BaseModel):
    """Extract structured data from pages using LLMs.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/extract
    """

    urls: Annotated[
        List[str],
        Field(..., description="The URLs to extract data from. URLs should be in glob format."),
        Body(),
    ]
    prompt: Annotated[
        Optional[str],
        Field(None, description="Prompt to guide the extraction process."),
        Body(),
    ]
    schema_: Annotated[
        Optional[dict],
        Field(
            None,
            alias="schema",
            description="Schema to define the structure of the extracted data. Must conform to JSON Schema.",
        ),
        Body(),
        WireName("schema"),
    ]
    enable_web_search: Annotated[
        Optional[bool],
        Field(None, description="When true, the extraction will use web search to find additional data."),
        Body(),
    ]
    ignore_sitemap: Annotated[
        Optional[bool],
        Field(None, description="When true, sitemap.xml files will be ignored during website scanning."),
        Body(),
    ]
    include_subdomains: Annotated[
        Optional[bool],
        Field(None, description="When true, subdomains of the provided URLs will also be scanned. The server applies true when this is absent."),
        Body(),
    ]
    show_sources: Annotated[
        Optional[bool],
        Field(None, description="When true, the sources used to extract the data will be included in the response as `sources`."),
        Body(),
    ]
    scrape_options: Annotated[
        Optional[ScrapeOptionsNested],
        Field(None, description="Options applied when scraping pages for extraction."),
        Body(),
    ]
    ignore_invalid_urls: Annotated[
        Optional[bool],
        Field(
            None,
            description="If invalid URLs are specified, they are ignored and returned in invalidURLs instead of failing the request. The server applies true when this is absent.",
        ),
        Body(),
        WireName("ignoreInvalidURLs"),
    ]
    threat_protection: Annotated[
        Optional[ThreatProtectionOverride],
        Field(None, description="Per-request threat protection override. Enterprise feature."),
        Body(),
    ]


class ExtractStatusRequest(BaseModel):
    """Get the status of an extract job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/extract-get
    """

    id: Annotated[str, Field(..., description="The ID of the extract job"), Path()]
