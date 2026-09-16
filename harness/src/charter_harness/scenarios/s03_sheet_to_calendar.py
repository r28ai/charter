"""gsheets + gcalendar — a spreadsheet of sessions becomes calendar events."""

from __future__ import annotations

from datetime import datetime, timedelta

from charter_harness.scenarios._fixtures import at, iso, next_monday, utc_iso
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World

# (title, hour, minute, duration in minutes)
SESSIONS = [("Kickoff", 9, 0, 45), ("Design review", 11, 30, 60), ("Retro", 15, 0, 30)]


def _same_instant(a: str, b: str) -> bool:
    try:
        return datetime.fromisoformat(a.replace("Z", "+00:00")) == datetime.fromisoformat(b.replace("Z", "+00:00"))
    except ValueError:
        return False


class SheetToCalendar(Scenario):
    id = "sheet_to_calendar"
    packs = ("gsheets", "gcalendar")
    summary = "Create one calendar event per spreadsheet row, at the stated local time and duration."
    defaults = {"sessions": SESSIONS}
    variants = {
        "two": {"sessions": [("Kickoff", 9, 0, 45), ("Retro", 15, 0, 30)]},
        "four": {"sessions": SESSIONS + [("Lunch and learn", 12, 15, 45)]},
        "five_odd_minutes": {
            "sessions": [("Standup", 8, 45, 15), ("Pairing", 9, 15, 90), ("Triage", 11, 45, 20), ("Demo", 14, 15, 40), ("Wrap-up", 17, 45, 15)]
        },
        "afternoon": {"sessions": [("Vendor call", 13, 0, 30), ("Roadmap", 14, 30, 60), ("Hiring sync", 16, 0, 45)]},
        "long_blocks": {"sessions": [("Workshop", 9, 0, 180), ("Deep work", 13, 0, 120), ("Office hours", 16, 0, 60)]},
        "early_late": {"sessions": [("Breakfast briefing", 7, 30, 30), ("Midday check-in", 12, 0, 15), ("Evening review", 18, 45, 45)]},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        tz = world.settings.timezone
        day = next_monday(tz)
        rows = []
        for title, hour, minute, minutes in self.params["sessions"]:
            start = at(day, hour, minute)
            rows.append(
                {
                    "title": f"{ns} {title}",
                    "start_local": start.strftime("%Y-%m-%d %H:%M"),
                    "minutes": minutes,
                    "start": iso(start),
                    "end": iso(start + timedelta(minutes=minutes)),
                }
            )
        sheet = await world.sheets.spreadsheet_create(f"{ns} schedule")
        await world.sheets.values_update(
            sheet["spreadsheetId"],
            f"Sheet1!A1:C{len(rows) + 1}",
            [["Title", "Start", "Minutes"]] + [[r["title"], r["start_local"], r["minutes"]] for r in rows],
        )
        return {
            "spreadsheet_id": sheet["spreadsheetId"],
            "timezone": tz,
            "rows": rows,
            "window": {"min": utc_iso(day - timedelta(days=1)), "max": utc_iso(day + timedelta(days=2))},
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"The Google Sheet with id {expected['spreadsheet_id']} (sheet \"Sheet1\") has a header row and then "
            f"one session per row: Title, Start (local date and time in the {expected['timezone']} time zone, "
            f"format YYYY-MM-DD HH:MM) and Minutes (duration). Create one event on my primary Google Calendar "
            f"for each session, with exactly that title, starting at that local time in {expected['timezone']} "
            f"and lasting the stated number of minutes."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        # The model created these; the free-text search may still be catching up.
        events = await world.calendar.events_list_eventually(
            q=ns, time_min=expected["window"]["min"], time_max=expected["window"]["max"], at_least=len(expected["rows"])
        )
        return {
            "events": [
                {
                    "id": e.get("id"),
                    "summary": e.get("summary", ""),
                    "start": (e.get("start") or {}).get("dateTime", ""),
                    "end": (e.get("end") or {}).get("dateTime", ""),
                }
                for e in events
                if e.get("status") != "cancelled"
            ]
        }

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        conditions = []
        for row in expected["rows"]:
            matches = [e for e in observed["events"] if norm(e["summary"]) == norm(row["title"])]
            conditions.append((len(matches) == 1, f"expected exactly one event titled {row['title']!r}, found {len(matches)}"))
            if len(matches) == 1:
                e = matches[0]
                conditions.append((_same_instant(e["start"], row["start"]), f"{row['title']!r} starts at {e['start']}, expected {row['start']}"))
                conditions.append((_same_instant(e["end"], row["end"]), f"{row['title']!r} ends at {e['end']}, expected {row['end']}"))
        conditions.append(
            (len(observed["events"]) == len(expected["rows"]), f"expected {len(expected['rows'])} events, found {len(observed['events'])}")
        )
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "spreadsheet_id": "s",
            "timezone": "Europe/Paris",
            "rows": [
                {"title": "hx Kickoff", "start_local": "2026-09-14 09:00", "minutes": 45, "start": "2026-09-14T09:00:00+02:00", "end": "2026-09-14T09:45:00+02:00"},
                {"title": "hx Retro", "start_local": "2026-09-14 15:00", "minutes": 30, "start": "2026-09-14T15:00:00+02:00", "end": "2026-09-14T15:30:00+02:00"},
            ],
            "window": {"min": "2026-09-13T00:00:00Z", "max": "2026-09-16T00:00:00Z"},
        }
        observed = {
            "events": [
                # the API may echo the instant in another offset; the judge compares instants
                {"id": "e1", "summary": "hx Kickoff", "start": "2026-09-14T07:00:00Z", "end": "2026-09-14T07:45:00Z"},
                {"id": "e2", "summary": "hx Retro", "start": "2026-09-14T15:00:00+02:00", "end": "2026-09-14T15:30:00+02:00"},
            ]
        }
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        events = observed["events"]
        off_by_hour = dict(events[0], start="2026-09-14T08:00:00Z", end="2026-09-14T08:45:00Z")
        wrong_duration = dict(events[1], end="2026-09-14T16:00:00+02:00")
        return [
            ("an event starts one hour off (time zone mistake)", {"events": [off_by_hour] + events[1:]}),
            ("an event has the wrong duration", {"events": events[:-1] + [wrong_duration]}),
            ("an event is missing", {"events": events[:-1]}),
            ("an event was created twice", {"events": events + [dict(events[0], id="dup")]}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        events = await world.calendar.events_list(
            q=ns, time_min=expected["window"]["min"], time_max=expected["window"]["max"]
        )
        for e in events:
            await world.calendar.event_delete(e["id"])
        await world.drive.file_delete(expected["spreadsheet_id"])


register(SheetToCalendar())
