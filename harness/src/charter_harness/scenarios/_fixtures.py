"""
Fixture vocabulary shared by the scenarios: names, addresses, dates.

Everything here is a pure function of the namespace and an index, so two
epochs of one scenario never share an email address or a title, and a judge
can be handed the same values offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

__all__ = ["PEOPLE", "email", "person", "next_monday", "at", "iso", "utc_iso"]

PEOPLE: list[tuple[str, str]] = [
    ("Ada Lovelace", "ada"),
    ("Grace Hopper", "grace"),
    ("Edsger Dijkstra", "edsger"),
    ("Barbara Liskov", "barbara"),
    ("Dennis Ritchie", "dennis"),
    ("Frances Allen", "frances"),
    ("Alan Turing", "alan"),
    ("Margaret Hamilton", "margaret"),
    ("Donald Knuth", "donald"),
    ("Radia Perlman", "radia"),
]


def person(i: int) -> tuple[str, str]:
    return PEOPLE[i % len(PEOPLE)]


def email(ns: str, i: int) -> str:
    """Unique per index even past the end of ``PEOPLE`` (``ada1.<ns>@...``)."""
    suffix = i // len(PEOPLE) or ""
    return f"{person(i)[1]}{suffix}.{ns}@harness.invalid"


def next_monday(tz: str, *, weeks_ahead: int = 1) -> datetime:
    """Midnight of a Monday at least a week out — clear of anything real on the calendar."""
    now = datetime.now(ZoneInfo(tz))
    days = (7 - now.weekday()) % 7 or 7
    day = (now + timedelta(days=days + 7 * (weeks_ahead - 1))).date()
    return datetime(day.year, day.month, day.day, tzinfo=ZoneInfo(tz))


def at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def iso(dt: datetime) -> str:
    """RFC 3339 with the zone's offset, seconds included — what Calendar echoes back."""
    return dt.isoformat(timespec="seconds")


def utc_iso(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
