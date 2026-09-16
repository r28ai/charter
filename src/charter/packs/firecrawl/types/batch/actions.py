"""Request schemas for Firecrawl batch scrape endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import ScrapeOptionsMixin, Webhook
from charter.types import Body, Path, WireName

__all__ = [
    "BatchScrapeRequest",
    "BatchScrapeStatusRequest",
    "BatchScrapeCancelRequest",
    "BatchScrapeErrorsRequest",
]


class BatchScrapeRequest(ScrapeOptionsMixin):
    """Scrape multiple URLs in a single batch job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape
    """

    urls: Annotated[
        List[str],
        Field(..., description="The URLs to scrape"),
        Body(),
    ]
    webhook: Annotated[
        Optional[Webhook],
        Field(None, description="Webhook specification for batch scrape lifecycle events."),
        Body(),
    ]
    max_concurrency: Annotated[
        Optional[int],
        Field(None, description="Maximum number of concurrent scrapes for this batch."),
        Body(),
    ]
    ignore_invalid_urls: Annotated[
        Optional[bool],
        Field(
            None,
            description="If invalid URLs are specified, they are ignored and returned in invalidURLs instead of failing the request.",
        ),
        Body(),
        WireName("ignoreInvalidURLs"),
    ]
    zero_data_retention: Annotated[
        Optional[bool],
        Field(
            None,
            description="If true, this will enable zero data retention for this batch scrape. To enable this feature, please contact help@firecrawl.dev",
        ),
        Body(),
    ]


class BatchScrapeStatusRequest(BaseModel):
    """Get the status of a batch scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape-get
    """

    id: Annotated[str, Field(..., description="The ID of the batch scrape job"), Path()]


class BatchScrapeCancelRequest(BaseModel):
    """Cancel a batch scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape-delete
    """

    id: Annotated[str, Field(..., description="The ID of the batch scrape job"), Path()]


class BatchScrapeErrorsRequest(BaseModel):
    """Get errors from a batch scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/batch-scrape-get-errors
    """

    id: Annotated[str, Field(..., description="The ID of the batch scrape job"), Path()]
