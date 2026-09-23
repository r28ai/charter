# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The objects Granola's three resources share, and the constants that describe them.

A note, a folder and a webhook endpoint are separate resources with separate
endpoints, but they quote each other: a note lists the folders it belongs to and
the people who attended it, a webhook endpoint names the folders it filters on
and the person who created it. Those shared shapes live here so that each one is
described once.

Everything in this module is ``Mode("response_only")``. Granola's write surface
is four webhook fields; every object below is something the API returns and
never accepts, so none of it belongs in a model's input schema.

API Reference: https://docs.granola.ai/introduction
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

__all__ = [
    "NOTE_ID_PATTERN",
    "FOLDER_ID_PATTERN",
    "WEBHOOK_ENDPOINT_ID_PATTERN",
    "CURSOR_DESCRIPTION",
    "User",
    "Folder",
    "Speaker",
    "TranscriptItem",
    "CursorPage",
]

# Granola prefixes every ID with its object type and follows it with fourteen
# alphanumeric characters. The patterns are on the fields so that a model
# handing back a bare UUID — which the quick start warns about explicitly,
# because the web app's URLs carry one — fails locally instead of as a 404.
# https://docs.granola.ai/introduction
NOTE_ID_PATTERN = r"^not_[a-zA-Z0-9]{14}$"
FOLDER_ID_PATTERN = r"^fol_[a-zA-Z0-9]{14}$"
WEBHOOK_ENDPOINT_ID_PATTERN = r"^whe_[a-zA-Z0-9]{14}$"

# One cursor convention across every list endpoint, so its description has one
# home. The parameter is named `cursor` going out and the field is named
# `cursor` coming back, which is rarer than it sounds and worth not restating
# three times.
CURSOR_DESCRIPTION = "The cursor to continue from"


class User(BaseModel):
    """A person Granola knows about: a note's owner, an attendee, a creator.

    API Reference: https://docs.granola.ai/api-reference/get-note
    """

    name: Annotated[
        Optional[str],
        Field(None, description="The name of the user"),
        Mode("response_only"),
    ]
    email: Annotated[
        Optional[str],
        Field(None, description="The email of the user"),
        Mode("response_only"),
    ]


class Folder(BaseModel):
    """A folder, as it appears in a listing and in a note's membership.

    ``parent_folder_id`` is the whole of the hierarchy: a folder names its
    parent and nothing names its children, so a tree is assembled by the caller
    from a full listing.

    API Reference: https://docs.granola.ai/api-reference/list-folders
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the folder"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the folder"),
        Mode("response_only"),
    ]
    name: Annotated[
        Optional[str],
        Field(None, description="The name of the folder"),
        Mode("response_only"),
    ]
    parent_folder_id: Annotated[
        Optional[str],
        Field(
            None,
            description="The ID of the parent folder, or null if the folder is top-level.",
        ),
        Mode("response_only"),
    ]


class Speaker(BaseModel):
    """Who said one line of a transcript, to whatever resolution Granola has.

    Four fields, and which of them arrive depends on the platform the meeting
    was captured on. ``source`` is always there. ``attribution`` says whether it
    was the note-taker, and is omitted when that is unknown.
    ``diarization_label`` carries the anonymous ``Speaker A`` bucket, on iOS and
    only when diarization ran. ``name`` arrives only when a speaker was
    actually identified.

    ``source`` is a ``str`` rather than a closed set: Granola documents
    ``microphone`` and ``speaker`` and then says in the same sentence that
    clients should not assume the set will never expand.

    API Reference: https://docs.granola.ai/api-reference/get-transcript
    """

    source: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The source of the speaker. For iOS transcripts, Granola currently "
                "returns `microphone` for all transcript items because iOS currently "
                "captures a single audio stream. Clients should not assume this will "
                "never expand in the future."
            ),
        ),
        Mode("response_only"),
    ]
    attribution: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Who said this relative to the note: `me` is the note-taker (the "
                "note's owner), `them` is other meeting participants. Omitted when "
                "the attribution is unknown, such as iOS transcript items that only "
                "carry an anonymous `diarization_label`."
            ),
        ),
        Mode("response_only"),
    ]
    diarization_label: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The diarized anonymous speaker label assigned in the transcript, "
                "such as `Speaker A`. This is currently only present on iOS "
                "transcripts when diarization is available."
            ),
        ),
        Mode("response_only"),
    ]
    name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The resolved name of the identified speaker, such as `Alice Smith`. "
                "This is only present when a speaker could be identified for the "
                "transcript item."
            ),
        ),
        Mode("response_only"),
    ]


class TranscriptItem(BaseModel):
    """One line of a meeting transcript.

    The same shape whether it arrives inline from ``notes_get`` or a page at a
    time from ``notes_transcript_get``.

    API Reference: https://docs.granola.ai/api-reference/get-transcript
    """

    speaker: Annotated[
        Optional[Speaker],
        Field(None, description="Who said this line, to whatever resolution is known"),
        Mode("response_only"),
    ]
    text: Annotated[
        Optional[str],
        Field(None, description="The text of the transcript"),
        Mode("response_only"),
    ]
    start_time: Annotated[
        Optional[str],
        Field(None, description="The start time of the transcript"),
        Mode("response_only"),
    ]
    end_time: Annotated[
        Optional[str],
        Field(None, description="The end time of the transcript"),
        Mode("response_only"),
    ]


class CursorPage(BaseModel):
    """The two fields every paginated Granola response ends with.

    ``hasMore`` is the only camelCase key in the API. It is authoritative:
    ``cursor`` is null on the last page, but the pack reads ``hasMore`` so that
    a walk stops on the API's own answer rather than on the absence of a token.

    API Reference: https://docs.granola.ai/introduction
    """

    has_more: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether there is another page to fetch. Spelled `hasMore` on the "
                "wire — the one camelCase key in an otherwise snake_case API."
            ),
        ),
        Mode("response_only"),
    ]
    cursor: Annotated[
        Optional[str],
        Field(None, description=CURSOR_DESCRIPTION),
        Mode("response_only"),
    ]
