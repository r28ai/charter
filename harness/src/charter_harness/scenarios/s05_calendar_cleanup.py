"""gcalendar — delete the cancelled events and only those."""

from __future__ import annotations

from datetime import timedelta

from charter_harness.scenarios._fixtures import at, iso, next_monday, utc_iso
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

EVENTS = [
    ("[CANCELLED] Vendor demo", 9, True),
    ("Sprint planning", 10, False),
    ("[CANCELLED] 1:1 with Sam", 13, True),
    ("Release go/no-go", 16, False),
]


class CalendarCleanup(Scenario):
    id = "calendar_cleanup"
    packs = ("gcalendar",)
    summary = "Delete the events marked [CANCELLED] on a given day; keep the rest."
    # events: (title, hour, cancelled)
    defaults = {"events": EVENTS}
    variants = {
        "one_of_three": {
            "events": [
                ("Sprint planning", 10, False),
                ("[CANCELLED] 1:1 with Sam", 13, True),
                ("Release go/no-go", 16, False),
            ]
        },
        "three_of_five": {
            "events": [
                ("[CANCELLED] Vendor demo", 9, True),
                ("Sprint planning", 10, False),
                ("[CANCELLED] 1:1 with Sam", 13, True),
                ("[CANCELLED] Budget review", 15, True),
                ("Release go/no-go", 16, False),
            ]
        },
        "cancelled_last": {
            "events": [
                ("Standup", 9, False),
                ("Design review", 11, False),
                ("[CANCELLED] Offsite prep", 14, True),
                ("[CANCELLED] Happy hour", 17, True),
            ]
        },
        "all_but_one": {
            "events": [
                ("[CANCELLED] A", 9, True),
                ("[CANCELLED] B", 10, True),
                ("Keep me", 11, False),
                ("[CANCELLED] C", 12, True),
            ]
        },
        "decoy_title": {
            "events": [
                ("[CANCELLED] Vendor demo", 9, True),
                ("Review cancelled orders", 10, False),
                ("Sprint planning", 11, False),
                ("[CANCELLED] 1:1 with Sam", 13, True),
            ]
        },
        "six": {
            "events": [
                ("Standup", 9, False),
                ("[CANCELLED] Vendor demo", 10, True),
                ("Sprint planning", 11, False),
                ("Lunch", 12, False),
                ("[CANCELLED] 1:1 with Sam", 13, True),
                ("Release go/no-go", 16, False),
            ]
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        tz = world.settings.timezone
        day = next_monday(tz)
        created = []
        for title, hour, cancelled in self.params["events"]:
            start = at(day, hour)
            event = await world.calendar.event_insert(
                summary=f"{title} ({ns})",
                start=iso(start),
                end=iso(start + timedelta(minutes=30)),
                timezone=tz,
            )
            created.append({"id": event["id"], "title": f"{title} ({ns})", "cancelled": cancelled})
        window = {"min": utc_iso(day - timedelta(days=1)), "max": utc_iso(day + timedelta(days=2))}
        await world.calendar.await_events(
            q=ns, ids=[e["id"] for e in created], time_min=window["min"], time_max=window["max"]
        )
        return {
            "events": created,
            "day": day.strftime("%Y-%m-%d"),
            "window": window,
            "owned": {"gcalendar.event": [e["id"] for e in created]},
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"On {expected['day']}, my primary Google Calendar has several events whose title ends with "
            f'"({ns})". Some of them have been cancelled: their title starts with "[CANCELLED]". Delete every '
            f"cancelled event on that day and leave the others exactly as they are."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        state = {}
        for e in expected["events"]:
            event = await world.calendar.event_get(e["id"])
            state[e["id"]] = (
                "deleted" if event is None or event.get("status") == "cancelled" else "present"
            )
        return {"state": state}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        conditions = []
        for e in expected["events"]:
            got = observed["state"].get(e["id"], "missing")
            if e["cancelled"]:
                conditions.append(
                    (got == "deleted", f"cancelled event {e['title']!r} is still on the calendar")
                )
            else:
                conditions.append((got == "present", f"live event {e['title']!r} was deleted"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "events": [
                {"id": "a", "title": "[CANCELLED] Vendor demo (hx)", "cancelled": True},
                {"id": "b", "title": "Sprint planning (hx)", "cancelled": False},
                {"id": "c", "title": "[CANCELLED] 1:1 with Sam (hx)", "cancelled": True},
                {"id": "d", "title": "Release go/no-go (hx)", "cancelled": False},
            ],
            "day": "2026-09-14",
            "window": {"min": "", "max": ""},
        }
        observed = {"state": {"a": "deleted", "b": "present", "c": "deleted", "d": "present"}}
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        s = observed["state"]
        return [
            ("a live event was deleted", {"state": {**s, "b": "deleted"}}),
            ("a cancelled event was left in place", {"state": {**s, "c": "present"}}),
            ("everything was deleted", {"state": {k: "deleted" for k in s}}),
            ("nothing was deleted", {"state": {k: "present" for k in s}}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for e in expected.get("events", []):
            await world.calendar.event_delete(e["id"])


register(CalendarCleanup())
