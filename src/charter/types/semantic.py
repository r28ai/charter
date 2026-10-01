# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Semantic types for AI agents.

These types represent the semantic *meaning* of data, as opposed to wire formats.
LLMs interact with these semantic types, which are then transformed to wire formats
for API calls by the transforms in :mod:`charter.transforms`.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "EmailContent",
    "CalendarEvent",
    "DocumentContent",
    "FileContent",
]

# RFC 5322 folding: a line break followed by whitespace continues the header.
_FOLDING = re.compile(r"\r?\n[ \t]+")


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

    @field_validator(
        "to",
        "cc",
        "bcc",
        "subject",
        "from_",
        "reply_to",
        "in_reply_to",
        "references",
        mode="before",
    )
    @classmethod
    def _single_line(cls, value: Any) -> Any:
        # A line break followed by a space or tab is a folded header, one
        # logical line, so it is unfolded. Any other line break is how a second
        # header (a Bcc) gets smuggled in. The encoder would refuse that too,
        # but as a parse error a model can't act on; this names the field.
        def unfold(item: Any) -> Any:
            if not isinstance(item, str):
                return item
            item = _FOLDING.sub(" ", item)
            if "\r" in item or "\n" in item:
                raise ValueError("must be a single line; header fields cannot contain line breaks")
            return item

        return [unfold(item) for item in value] if isinstance(value, list) else unfold(value)


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
