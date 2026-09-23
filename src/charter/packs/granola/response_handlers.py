# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Granola response trimming — context economy only.

Two payloads in this API carry meaningful overhead, and they are the two an
agent reaches for most.

**A transcript repeats its envelope once per line.** Each item is a ``speaker``
object of up to four keys, a ``text``, and two ISO timestamps. In Granola's own
example the speaker object is ``{"source": "microphone", "attribution": "me"}``
— 48 bytes to say *the note-taker*, beside about 60 bytes of what was actually
said. An hour of conversation is several hundred of those, so the object is
collapsed to the one word it spells: the identified name where there is one,
otherwise the attribution, otherwise the diarization bucket, otherwise the
source. Nothing an agent reads is lost, because those four keys are a priority
order, not four independent facts.

**A note returns its summary twice.** ``summary_text`` and ``summary_markdown``
are the same prose in two encodings, and so are ``private_notes_text`` and
``private_notes_markdown``. On a long note that is kilobytes of exact
duplication. The markdown is kept where it exists — it is the superset, and it
degrades to readable text — and the plain-text twin is dropped. Where the
markdown is null, the text is what survives, so no note ever comes back with no
summary at all.

Both handlers keep ``hasMore`` and ``cursor`` untouched. A trimmed page that
lost its paging signal would be a walk that cannot terminate.

API Reference: https://docs.granola.ai/api-reference/get-note
"""

from __future__ import annotations

from typing import Any, Dict

__all__ = ["trim_note", "trim_transcript"]

# Priority order, most specific first. `name` arrives only when a speaker was
# identified; `attribution` says me-or-them; `diarization_label` is the
# anonymous iOS bucket; `source` is the microphone-or-room fallback that is
# always present.
_SPEAKER_KEYS = ("name", "attribution", "diarization_label", "source")

# The pairs Granola returns in two encodings. Markdown wins where it is there.
_DUPLICATED = (
    ("summary_markdown", "summary_text"),
    ("private_notes_markdown", "private_notes_text"),
)


def _speaker(speaker: Any) -> Any:
    """The one word a speaker object spells, or the object back if it is not one."""
    if not isinstance(speaker, dict):
        return speaker
    for key in _SPEAKER_KEYS:
        value = speaker.get(key)
        if value:
            return value
    # A speaker object with nothing in it. Returning None rather than {} says
    # "not known" instead of "here is a speaker", which is the truth.
    return None


def _item(item: Any) -> Any:
    """One transcript line, with its speaker collapsed and its text untouched."""
    if not isinstance(item, dict) or "speaker" not in item:
        return item
    return {**item, "speaker": _speaker(item["speaker"])}


def _items(transcript: Any) -> Any:
    if not isinstance(transcript, list):
        return transcript
    return [_item(item) for item in transcript]


def _deduplicate(note: Dict[str, Any]) -> Dict[str, Any]:
    """Drop the plain-text twin of any field that also came back as markdown."""
    trimmed = dict(note)
    for markdown, text in _DUPLICATED:
        if trimmed.get(markdown) and trimmed.get(text):
            trimmed.pop(text)
    return trimmed


async def trim_note(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``GET /v1/notes/{note_id}``.

    The summary survives in one encoding rather than two, and an inline
    transcript's speakers are collapsed. Everything else — the title, the owner,
    the attendees, the calendar event, the folder membership — is passed through
    exactly as the API sent it.
    """
    if not isinstance(response, dict):
        return response
    note = _deduplicate(response)
    if note.get("transcript") is not None:
        note["transcript"] = _items(note["transcript"])
    return note


async def trim_transcript(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``GET /v1/notes/{note_id}/transcript``.

    ``hasMore`` and ``cursor`` are carried through untouched: they are what the
    declared pagination reads, and an empty page still has to be able to say
    whether another one follows.
    """
    if not isinstance(response, dict):
        return response
    transcript = response.get("transcript")
    if transcript is None:
        return response
    return {**response, "transcript": _items(transcript)}
