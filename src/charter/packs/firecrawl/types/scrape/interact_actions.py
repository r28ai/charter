# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for interacting with a scrape job's browser session.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape-interact
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path

__all__ = [
    "ScrapeInteractRequest",
    "ScrapeInteractStopRequest",
]


class ScrapeInteractRequest(BaseModel):
    """Execute code in the browser sandbox associated with a scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape-interact
    """

    job_id: Annotated[str, Field(..., description="The scrape job ID"), Path()]
    code: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            max_length=100000,
            description="Code to execute in the scrape-bound browser sandbox",
        ),
        Body(),
    ]
    language: Annotated[
        Optional[Literal["python", "node", "bash"]],
        Field(
            None,
            description="Language of the code to execute. Use `node` for JavaScript or `bash` for agent-browser CLI commands. The server applies 'node' when this is absent.",
        ),
        Body(),
    ]
    timeout: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=300,
            description="Execution timeout in seconds. The server applies 30 when this is absent.",
        ),
        Body(),
    ]
    origin: Annotated[
        Optional[str],
        Field(None, description="Optional origin label used for execution telemetry"),
        Body(),
    ]


class ScrapeInteractStopRequest(BaseModel):
    """Stop the interactive browser session associated with a scrape job.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/scrape-interact-delete
    """

    job_id: Annotated[str, Field(..., description="The scrape job ID"), Path()]
