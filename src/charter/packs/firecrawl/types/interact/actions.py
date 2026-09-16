"""Request schemas for Firecrawl browser sandbox interact endpoints.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/interact
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

__all__ = [
    "InteractCreateRequest",
    "InteractExecuteRequest",
    "InteractListRequest",
    "InteractDeleteRequest",
]


class InteractProfile(BaseModel):
    """Persistent storage profile for interact sessions."""

    name: str = Field(..., min_length=1, max_length=128, description="A name for the profile. Sessions with the same name share storage.")
    save_changes: Optional[bool] = Field(
        None,
        description="When true, browser state is saved back to the profile on close. The server applies true when this is absent.",
    )


class InteractCreateRequest(BaseModel):
    """Create a browser sandbox interact session.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/interact-create
    """

    ttl: Annotated[
        Optional[int],
        Field(None, ge=30, le=3600, description="Total time-to-live in seconds for the interact session. The server applies 300 when this is absent."),
        Body(),
    ]
    activity_ttl: Annotated[
        Optional[int],
        Field(None, ge=10, le=3600, description="Time in seconds before the session is destroyed due to inactivity"),
        Body(),
    ]
    stream_web_view: Annotated[
        Optional[bool],
        Field(None, description="Whether to stream a live view of the browser. The server applies true when this is absent."),
        Body(),
    ]
    profile: Annotated[
        Optional[InteractProfile],
        Field(None, description="Enable persistent storage across interact sessions."),
        Body(),
    ]


class InteractExecuteRequest(BaseModel):
    """Execute code in an interact session.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/interact-execute
    """

    session_id: Annotated[str, Field(..., description="The interact session ID"), Path()]
    code: Annotated[
        str,
        Field(..., min_length=1, max_length=100000, description="Code to execute in the browser sandbox"),
        Body(),
    ]
    language: Annotated[
        Optional[Literal["python", "node", "bash"]],
        Field(
            None,
            description="Language of the code to execute. The server applies 'node' when this is absent.",
        ),
        Body(),
    ]
    timeout: Annotated[
        Optional[int],
        Field(None, ge=1, le=300, description="Execution timeout in seconds"),
        Body(),
    ]


class InteractListRequest(BaseModel):
    """List interact sessions.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/interact-list
    """

    status: Annotated[
        Optional[Literal["active", "destroyed"]],
        Field(None, description="Filter sessions by status"),
        Query(),
    ]


class InteractDeleteRequest(BaseModel):
    """Delete an interact session.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/interact-delete
    """

    session_id: Annotated[str, Field(..., description="The interact session ID"), Path()]
