# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Semantic types for AI agents.

These types represent the semantic *meaning* of data, as opposed to wire formats.
LLMs interact with these semantic types, which are then transformed to wire formats
for API calls by the transforms in :mod:`charter.transforms`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EmailContent",
    "CalendarEvent",
    "DocumentContent",
    "FileContent",
]


# -----------------------------------------------------
# Email Types
# -----------------------------------------------------


class EmailContent(BaseModel):
    """Semantic representation of an email message.

    This is what the LLM sees and provides, which gets transformed to various wire
    formats (RFC822, JSON, ...) depending on the API.
    """

    model_config = ConfigDict(populate_by_name=True)  # Allow both 'from_' and 'from'

    to: Union[str, List[str]] = Field(..., description="Recipient email address(es)")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(
        ...,
        description="Email body content (plain text or HTML depending on mimeType)",
    )
    mimeType: Optional[str] = Field(
        None,
        description=(
            "MIME type of the body: 'text/plain' (default) or 'text/html'. "
            "When bodyHtml is also provided, both are sent as multipart/alternative."
        ),
    )
    bodyHtml: Optional[str] = Field(
        None,
        description=(
            "HTML version of the body. When provided alongside body, the message "
            "is sent as multipart/alternative with both plain text and HTML parts."
        ),
    )
    cc: Optional[Union[str, List[str]]] = Field(None, description="Carbon copy recipient(s)")
    bcc: Optional[Union[str, List[str]]] = Field(None, description="Blind carbon copy recipient(s)")
    from_: Optional[str] = Field(
        None,
        alias="from",
        description="Sender email address (optional, defaults to authenticated user)",
    )
    reply_to: Optional[str] = Field(None, description="Reply-to email address")
    in_reply_to: Optional[str] = Field(
        None,
        description=(
            "Message-ID of the message being replied to (for threading). "
            "Required when replying to a message to maintain thread continuity."
        ),
    )
    references: Optional[str] = Field(
        None,
        description=(
            "Space-separated list of Message-IDs that trace the conversation thread. "
            "Should include all previous Message-IDs in the thread, most recent first."
        ),
    )


# -----------------------------------------------------
# Calendar Types
# -----------------------------------------------------


class CalendarEvent(BaseModel):
    """Semantic representation of a calendar event."""

    summary: str = Field(..., description="Event title/summary")
    start: datetime = Field(..., description="Event start time")
    end: datetime = Field(..., description="Event end time")
    description: Optional[str] = Field(None, description="Detailed event description")
    location: Optional[str] = Field(None, description="Event location")
    attendees: Optional[List[str]] = Field(None, description="List of attendee email addresses")


# -----------------------------------------------------
# Document Types
# -----------------------------------------------------


class DocumentContent(BaseModel):
    """Semantic representation of a document."""

    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Document content (supports markdown)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional document metadata")


# -----------------------------------------------------
# File Types
# -----------------------------------------------------


class FileContent(BaseModel):
    """Semantic representation of file content."""

    filename: str = Field(..., description="Name of the file")
    content: str = Field(..., description="File content as text")
    mime_type: Optional[str] = Field(None, description="MIME type of the file")
