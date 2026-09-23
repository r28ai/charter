# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.packs.firecrawl.types.common import ScrapeOptionsMixin
from charter.types import Body, Path

__all__ = ["ScrapeRequest", "ScrapeStatusRequest"]


class ScrapeRequest(ScrapeOptionsMixin):
    """Scrape a single URL and return its content in one or more formats.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape
    """

    url: Annotated[
        str,
        Field(..., description="The URL to scrape"),
        Body(),
    ]
    zero_data_retention: Annotated[
        Optional[bool],
        Field(
            None,
            description="If true, this will enable zero data retention for this scrape. To enable this feature, please contact help@firecrawl.dev",
        ),
        Body(),
    ]


class ScrapeStatusRequest(BaseModel):
    """Get the status of a scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape-get
    """

    job_id: Annotated[str, Field(..., description="The ID of the job"), Path()]
