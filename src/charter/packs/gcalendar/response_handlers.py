"""
Google Calendar response trimming — context economy only.

A Calendar event is about 745 bytes on the wire and roughly a quarter of that
is actionable. The rest is provenance an agent cannot use: ``htmlLink``,
``iCalUID``, ``etag``, ``kind``, ``created``/``updated``, ``sequence``, and a
``reminders`` block that is almost always ``{"useDefault": true}``. A list of
sixty events therefore arrives as tens of kilobytes to say sixty times what
fits in a line each.

These handlers keep what a model can act on — the identifier it needs to
update or delete, the title it matches on, the times it reasons about — and
drop the rest. Fields that are only *sometimes* meaningful (a description, a
location, attendees, recurrence) are kept when present and omitted when not,
so the common event stays small without the rare one losing information.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "extract_calendar",
    "extract_calendar_metadata",
    "extract_event",
    "extract_events",
    "extract_calendars",
]

# Kept verbatim when present. Absent from most events, actionable in all of them.
_OPTIONAL = ("location", "recurringEventId", "recurrence")

# `description` is the reason a page of events is large. On a real calendar it
# is rarely prose: it is the conferencing block a client pasted in — "Join with
# Google Meet", a dial-in number, a PIN, a "Learn more" link — a kilobyte or two
# of HTML per event, repeated on every recurring instance. A page of twenty
# averages 23KB because of it, and one measured call reached 176KB.
#
# Dropping it is wrong; it is also where a human writes the agenda. So it is
# capped on the list endpoints and kept whole by `extract_event`, which is what
# `events_get` uses — the id needed to make that call is in the same item. A
# truncated description says so rather than ending mid-sentence, because the
# failure this guards against is a model reading a cut-off string as the whole
# note.
#
# 300 characters because of where the split falls, not as a round number: every
# client that injects a conferencing block appends it, so the part a person
# typed is at the front and the part a machine generated is behind the cap.
_DESCRIPTION_LIMIT = 300
_TRUNCATION_NOTE = "… [truncated — call events_get with this event's id for the full text]"


def _cursor(response: Dict[str, Any]) -> Optional[str]:
    """The page token, read from the pack declaration rather than re-derived."""
    from charter.packs.gcalendar import GOOGLE_PAGINATION

    return GOOGLE_PAGINATION.next_cursor(response)


def _trim_time(value: Any) -> Optional[Dict[str, Any]]:
    """One end of an event: ``date`` for all-day, ``dateTime`` otherwise.

    ``timeZone`` is kept because a ``dateTime`` without an offset is ambiguous
    without it, and Calendar returns exactly that shape when the caller supplied
    a naive local time.
    """
    if not isinstance(value, dict):
        return None
    kept = {k: value[k] for k in ("date", "dateTime", "timeZone") if value.get(k)}
    return kept or None


def _conference(event: Dict[str, Any]) -> Optional[str]:
    """The join link, as a link rather than as prose inside the description.

    Calendar carries it in two places: `hangoutLink` for Meet, and the
    `conferenceData.entryPoints` array for everything else. Reading it out is
    what makes capping the description safe — otherwise the one actionable
    thing in that HTML block is what the cap removes.
    """
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    data = event.get("conferenceData")
    if not isinstance(data, dict):
        return None
    for entry in data.get("entryPoints") or []:
        if isinstance(entry, dict) and entry.get("entryPointType") == "video":
            if entry.get("uri"):
                return entry["uri"]
    return None


def _trim_event(event: Dict[str, Any], *, full_description: bool = True) -> Dict[str, Any]:
    """One event, reduced to what an agent can act on."""
    out: Dict[str, Any] = {
        "id": event.get("id"),
        "summary": event.get("summary", ""),
    }
    for key in ("start", "end"):
        trimmed = _trim_time(event.get(key))
        if trimmed:
            out[key] = trimmed

    # "confirmed" is the default and would cost a line on every event; its
    # absence means confirmed, and "cancelled" is the case worth reporting.
    status = event.get("status")
    if status and status != "confirmed":
        out["status"] = status

    for key in _OPTIONAL:
        if event.get(key):
            out[key] = event[key]

    description = event.get("description")
    if description:
        if full_description or len(description) <= _DESCRIPTION_LIMIT:
            out["description"] = description
        else:
            out["description"] = description[:_DESCRIPTION_LIMIT] + _TRUNCATION_NOTE
            out["description_truncated"] = True

    join_url = _conference(event)
    if join_url:
        out["conferenceUrl"] = join_url

    # The organiser matters only when it is somebody else.
    organizer = event.get("organizer") or {}
    if organizer.get("email") and not organizer.get("self"):
        out["organizer"] = organizer["email"]

    attendees = event.get("attendees")
    if attendees:
        out["attendees"] = [
            {"email": a.get("email"), "responseStatus": a.get("responseStatus")}
            for a in attendees
            if isinstance(a, dict)
        ]
    return out


async def extract_event(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a single event resource — ``events.get``, ``events.insert`` and the
    other writes that echo the event back.

    The description is kept whole here. One event is not a page of them, and
    this is the call an agent makes when the capped version on the list was not
    enough.
    """
    return _trim_event(response, full_description=True)


async def extract_events(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``events.list``.

    Keeps the events and the page token; drops the calendar's own metadata.
    ``timeZone`` survives because it is the calendar default against which a
    naive ``dateTime`` in an item is read. Descriptions are capped here and not
    in :func:`extract_event` — see ``_DESCRIPTION_LIMIT``.
    """
    out: Dict[str, Any] = {
        "items": [
            _trim_event(e, full_description=False)
            for e in response.get("items") or []
            if isinstance(e, dict)
        ]
    }
    if response.get("timeZone"):
        out["timeZone"] = response["timeZone"]
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


def _trim_calendar_entry(calendar: Dict[str, Any]) -> Dict[str, Any]:
    """One calendarList entry, reduced to what picks a calendar to act on."""
    entry: Dict[str, Any] = {
        "id": calendar.get("id"),
        "summary": calendar.get("summary", ""),
    }
    for key in ("primary", "selected"):
        if calendar.get(key):
            entry[key] = True
    for key in ("accessRole", "timeZone"):
        if calendar.get(key):
            entry[key] = calendar[key]
    return entry


async def extract_calendar(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``calendarList.get`` — one entry, the same shape the list returns."""
    return _trim_calendar_entry(response)


async def extract_calendar_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``calendars.get`` — the calendar itself rather than the user's view of it.

    ``timeZone`` is the reason this endpoint is worth having: it is the zone a
    naive ``dateTime`` on an event is read against, and reading it beats guessing.
    """
    out: Dict[str, Any] = {"id": response.get("id"), "summary": response.get("summary", "")}
    for key in ("description", "location", "timeZone"):
        if response.get(key):
            out[key] = response[key]
    return out


async def extract_calendars(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``calendarList.list`` to what picks a calendar to act on."""
    calendars: List[Dict[str, Any]] = [
        _trim_calendar_entry(c) for c in response.get("items") or [] if isinstance(c, dict)
    ]
    out: Dict[str, Any] = {"items": calendars}
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out
