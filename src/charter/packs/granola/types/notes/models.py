"""
Response models for Granola's note endpoints.

Every field is ``Mode("response_only")``: a note is written by the Granola app,
and nothing here is ever sent back to the API.

API Reference: https://docs.granola.ai/api-reference/get-note
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import (
    CursorPage,
    Folder,
    TranscriptItem,
    User,
)
from charter.types import Mode

__all__ = [
    "CalendarInvitee",
    "CalendarEvent",
    "NoteSummary",
    "Note",
    "ListNotesOutput",
    "GetTranscriptOutput",
]


class CalendarInvitee(BaseModel):
    """Someone invited to the meeting, by email alone.

    Distinct from an attendee: an invitee is who the calendar event was sent to,
    an attendee is who Granola saw in the meeting.

    API Reference: https://docs.granola.ai/api-reference/get-note
    """

    email: Annotated[
        Optional[str],
        Field(None, description="The email of the calendar invitee"),
        Mode("response_only"),
    ]


class CalendarEvent(BaseModel):
    """The calendar event a note was taken against, when there was one.

    Null on a note taken outside a scheduled meeting. Every field inside is
    nullable in its own right, so a note can carry an event whose title or
    organiser Granola never saw.

    API Reference: https://docs.granola.ai/api-reference/get-note
    """

    event_title: Annotated[
        Optional[str],
        Field(None, description="The title of the calendar event"),
        Mode("response_only"),
    ]
    invitees: Annotated[
        Optional[List[CalendarInvitee]],
        Field(None, description="The people the calendar event was sent to"),
        Mode("response_only"),
    ]
    organiser: Annotated[
        Optional[str],
        Field(None, description="The email of the organiser"),
        Mode("response_only"),
    ]
    calendar_event_id: Annotated[
        Optional[str],
        Field(None, description="The id of the calendar event"),
        Mode("response_only"),
    ]
    scheduled_start_time: Annotated[
        Optional[str],
        Field(None, description="The start time of the calendar event"),
        Mode("response_only"),
    ]
    scheduled_end_time: Annotated[
        Optional[str],
        Field(None, description="The end time of the calendar event"),
        Mode("response_only"),
    ]


class NoteSummary(BaseModel):
    """A note as it appears in a listing: what it is, who owns it, when.

    Deliberately smaller than :class:`Note` — no summary, no transcript, no
    folder membership. A listing of thirty of these is a few kilobytes, and the
    note itself is fetched by ID once the caller knows which one it wants.

    API Reference: https://docs.granola.ai/api-reference/list-notes
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the note"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the note"),
        Mode("response_only"),
    ]
    title: Annotated[
        Optional[str],
        Field(None, description="The title of the note"),
        Mode("response_only"),
    ]
    owner: Annotated[
        Optional[User],
        Field(None, description="The user who owns the note"),
        Mode("response_only"),
    ]
    created_at: Annotated[
        Optional[str],
        Field(None, description="The creation time of the note"),
        Mode("response_only"),
    ]
    updated_at: Annotated[
        Optional[str],
        Field(None, description="The last update time of the note"),
        Mode("response_only"),
    ]


class Note(BaseModel):
    """One note in full.

    The summary arrives twice, as ``summary_text`` and ``summary_markdown``, and
    so do the owner's private notes. The pack's response handler keeps the
    markdown and drops the plain-text twin when both are present, which is where
    most of a long note's payload goes.

    API Reference: https://docs.granola.ai/api-reference/get-note
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the note"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the note"),
        Mode("response_only"),
    ]
    title: Annotated[
        Optional[str],
        Field(None, description="The title of the note"),
        Mode("response_only"),
    ]
    owner: Annotated[
        Optional[User],
        Field(None, description="The user who owns the note"),
        Mode("response_only"),
    ]
    created_at: Annotated[
        Optional[str],
        Field(None, description="The creation time of the note"),
        Mode("response_only"),
    ]
    updated_at: Annotated[
        Optional[str],
        Field(None, description="The last update time of the note"),
        Mode("response_only"),
    ]
    web_url: Annotated[
        Optional[str],
        Field(None, description="The URL to view the note in the Granola web app"),
        Mode("response_only"),
    ]
    calendar_event: Annotated[
        Optional[CalendarEvent],
        Field(None, description="The calendar event this note was taken against"),
        Mode("response_only"),
    ]
    attendees: Annotated[
        Optional[List[User]],
        Field(None, description="The attendees of the meeting"),
        Mode("response_only"),
    ]
    folder_membership: Annotated[
        Optional[List[Folder]],
        Field(
            None,
            description=(
                "The folder membership of the note, including the ancestors of each "
                "folder that directly contains it"
            ),
        ),
        Mode("response_only"),
    ]
    summary_text: Annotated[
        Optional[str],
        Field(None, description="The summary text of the note"),
        Mode("response_only"),
    ]
    summary_markdown: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The summary of the note in markdown format. Can be null if the "
                "note has no summary."
            ),
        ),
        Mode("response_only"),
    ]
    private_notes_text: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The private notes the note's owner wrote themselves, as plain text. "
                "Only returned when the API key belongs to the user who created the "
                "note; `null` otherwise (including for shared notes and "
                "workspace-scoped keys)."
            ),
        ),
        Mode("response_only"),
    ]
    private_notes_markdown: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The private notes the note's owner wrote themselves, in markdown "
                "format. Only returned when the API key belongs to the user who "
                "created the note; `null` otherwise (including for shared notes and "
                "workspace-scoped keys)."
            ),
        ),
        Mode("response_only"),
    ]
    transcript: Annotated[
        Optional[List[TranscriptItem]],
        Field(
            None,
            description=(
                "The inline transcript of the note, present only when `include` "
                "asked for it. If it is too large to return inline, Get Note "
                "returns `TRANSCRIPT_TOO_LARGE`; retrieve it in pages from "
                "`/v1/notes/{note_id}/transcript`."
            ),
        ),
        Mode("response_only"),
    ]


class ListNotesOutput(CursorPage):
    """A page of notes.

    API Reference: https://docs.granola.ai/api-reference/list-notes
    """

    notes: Annotated[
        Optional[List[NoteSummary]],
        Field(None, description="The notes on this page"),
        Mode("response_only"),
    ]


class GetTranscriptOutput(CursorPage):
    """A page of transcript items.

    API Reference: https://docs.granola.ai/api-reference/get-transcript
    """

    transcript: Annotated[
        Optional[List[TranscriptItem]],
        Field(None, description="Transcript items for this page"),
        Mode("response_only"),
    ]
