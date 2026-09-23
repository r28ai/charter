# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for Granola's note endpoints.

Notes are read-only through the API. There is no endpoint that creates, edits or
deletes one — a note is written by the Granola app during a meeting, and this
API is how a program reads it back.

API Reference: https://docs.granola.ai/api-reference/list-notes
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import (
    CURSOR_DESCRIPTION,
    FOLDER_ID_PATTERN,
    NOTE_ID_PATTERN,
)
from charter.types import Path, Query

__all__ = [
    "NotesListRequest",
    "NotesGetRequest",
    "NotesTranscriptGetRequest",
]

_NOTE_ID_DESCRIPTION = (
    "The ID of the note, as returned by the list endpoint — a `not_` prefix "
    "followed by fourteen alphanumeric characters. The UUID in a Granola web "
    "app URL is a different identifier and is not accepted here."
)


class NotesListRequest(BaseModel):
    """List the meeting notes this API key can reach.

    Only notes that already have a generated AI summary and transcript are
    returned. One that is still processing, or that was never summarized, is
    absent from this list rather than present and empty.

    Which notes are reachable is a property of the key, not of this call: a key
    carries `personal` and/or `public` access scopes, chosen when it was
    created, and there is no parameter here that widens them.

    API Reference: https://docs.granola.ai/api-reference/list-notes
    """

    created_before: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Return notes created before this date. A date (`2026-01-27`) or a "
                "date-time (`2026-01-27T15:30:00Z`)."
            ),
        ),
        Query(),
    ]
    created_after: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Return notes created after this date. A date (`2026-01-27`) or a "
                "date-time (`2026-01-27T15:30:00Z`)."
            ),
        ),
        Query(),
    ]
    updated_after: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Return notes updated after this date. A date (`2026-01-27`) or a "
                "date-time (`2026-01-27T15:30:00Z`)."
            ),
        ),
        Query(),
    ]
    folder_id: Annotated[
        Optional[str],
        Field(
            None,
            pattern=FOLDER_ID_PATTERN,
            description=(
                "Return notes in this folder and any of its child folders. Use the "
                "list folders endpoint to discover folder IDs."
            ),
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(None, description=CURSOR_DESCRIPTION),
        Query(),
    ]
    page_size: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=30,
            description=(
                "Maximum number of notes to return per page. The server returns 10 "
                "when this is absent."
            ),
        ),
        Query(),
    ]


class NotesGetRequest(BaseModel):
    """Retrieve one note, with its summary, attendees and calendar event.

    ``include="transcript"`` adds the transcript inline. A transcript too large
    to inline is not truncated: the call answers `413 TRANSCRIPT_TOO_LARGE` and
    the transcript has to be read a page at a time from the transcript endpoint.
    A note that has no generated summary answers 404 rather than returning an
    empty one.

    API Reference: https://docs.granola.ai/api-reference/get-note
    """

    note_id: Annotated[
        str,
        Field(..., pattern=NOTE_ID_PATTERN, description=_NOTE_ID_DESCRIPTION),
        Path(),
    ]
    include: Annotated[
        Optional[Literal["transcript"]],
        Field(
            None,
            description=(
                "Include the note transcript in the response. If it is too large to "
                "return inline, Get Note returns `TRANSCRIPT_TOO_LARGE`; retrieve "
                "it in pages from `/v1/notes/{note_id}/transcript`."
            ),
        ),
        Query(),
    ]


class NotesTranscriptGetRequest(BaseModel):
    """Read a meeting transcript a page at a time.

    The way to read a transcript that ``notes_get`` refused to inline, and the
    right way to read any long one: a full transcript is the largest payload
    this API returns, and it arrives here in bounded pages instead of all at
    once.

    API Reference: https://docs.granola.ai/api-reference/get-transcript
    """

    note_id: Annotated[
        str,
        Field(..., pattern=NOTE_ID_PATTERN, description=_NOTE_ID_DESCRIPTION),
        Path(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(None, description="The opaque cursor returned by the previous page"),
        Query(),
    ]
    page_size: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description=(
                "The maximum number of transcript items to return. The server "
                "returns 50 when this is absent."
            ),
        ),
        Query(),
    ]
