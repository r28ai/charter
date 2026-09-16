"""gcalendar + gdocs — an agenda document from tagged events, in chronological order."""

from __future__ import annotations

from datetime import timedelta

from charter_harness.scenarios._fixtures import at, iso, next_monday, utc_iso
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World

# Deliberately not in chronological order in the seed, so "copy the list order"
# fails and only "sort by start" passes.
EVENTS = [("Budget sync", 14, 0), ("Standup", 9, 30), ("Customer call", 11, 0)]


class CalendarToDoc(Scenario):
    id = "calendar_to_doc"
    packs = ("gcalendar", "gdocs")
    summary = "Write a Google Doc agenda listing tagged events in chronological order."
    # events: (title, hour, minute), in seed order — never chronological.
    defaults = {"events": EVENTS}
    variants = {
        "two": {"events": [("Customer call", 11, 0), ("Standup", 9, 30)]},
        "four": {"events": [("Retro", 16, 30), ("Budget sync", 14, 0), ("Standup", 9, 30), ("Customer call", 11, 0)]},
        "five": {"events": [("Retro", 16, 30), ("Budget sync", 14, 0), ("Standup", 9, 30), ("Lunch with Sam", 12, 30), ("Customer call", 11, 0)]},
        "close_times": {"events": [("Third", 9, 30), ("First", 9, 0), ("Fourth", 9, 45), ("Second", 9, 15)]},
        "reverse_order": {"events": [("Wrap-up", 17, 0), ("Planning", 15, 0), ("Review", 13, 0), ("Kickoff", 10, 0)]},
        "same_hour": {"events": [("Late morning sync", 10, 50), ("Coffee chat", 10, 5), ("Design check", 10, 20)]},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        tz = world.settings.timezone
        day = next_monday(tz)
        created = []
        for title, hour, minute in self.params["events"]:
            start = at(day, hour, minute)
            event = await world.calendar.event_insert(
                summary=f"{ns} {title}", start=iso(start), end=iso(start + timedelta(minutes=30)), timezone=tz
            )
            created.append({"id": event["id"], "title": f"{ns} {title}", "start": iso(start)})
        window = {"min": utc_iso(day - timedelta(days=1)), "max": utc_iso(day + timedelta(days=2))}
        await world.calendar.await_events(q=ns, ids=[e["id"] for e in created], time_min=window["min"], time_max=window["max"])
        chronological = [e["title"] for e in sorted(created, key=lambda e: e["start"])]
        return {
            "events": created,
            "chronological_titles": chronological,
            "doc_title": f"{ns} agenda",
            "day": day.strftime("%Y-%m-%d"),
            "timezone": tz,
            "window": window,
            "owned": {"gcalendar.event": [e["id"] for e in created]},
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"On {expected['day']} my primary Google Calendar has several events whose title starts with "
            f"\"{ns}\". Create a Google Doc titled exactly \"{expected['doc_title']}\" containing an agenda "
            f"for that day: one line per such event, in chronological order, each line giving the start time "
            f"({expected['timezone']}) followed by the event title exactly as it appears in the calendar."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        files = await world.drive.files_list_eventually(name_contains=expected["doc_title"])
        docs = [f for f in files if f.get("mimeType") == "application/vnd.google-apps.document"]
        texts = []
        for f in docs:
            doc = await world.docs.document_get(f["id"])
            if doc:
                texts.append({"id": f["id"], "title": doc.get("title", ""), "text": world.docs.text_of(doc)})
        return {"docs": texts}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        docs = [d for d in observed["docs"] if norm(d["title"]) == norm(expected["doc_title"])]
        if len(docs) != 1:
            return Verdict.fail(f"expected exactly one document titled {expected['doc_title']!r}, found {len(docs)}")
        text = norm(docs[0]["text"])
        positions = [text.find(norm(t)) for t in expected["chronological_titles"]]
        return check(
            [
                (all(p >= 0 for p in positions), "an event title is missing from the agenda"),
                (positions == sorted(positions) and len(set(positions)) == len(positions), "events are not in chronological order"),
            ]
        )

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "events": [],
            "chronological_titles": ["hx Standup", "hx Customer call", "hx Budget sync"],
            "doc_title": "hx agenda",
            "day": "2026-09-14",
            "timezone": "Europe/Paris",
            "window": {"min": "", "max": ""},
        }
        observed = {
            "docs": [
                {
                    "id": "d1",
                    "title": "hx agenda",
                    "text": "Agenda for 2026-09-14\n09:30 hx Standup\n11:00 hx Customer call\n14:00 hx Budget sync\n",
                }
            ]
        }
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        doc = observed["docs"][0]
        return [
            ("two events are in the wrong order", {"docs": [dict(doc, text="09:30 hx Standup\n14:00 hx Budget sync\n11:00 hx Customer call\n")]}),
            ("an event is missing", {"docs": [dict(doc, text="09:30 hx Standup\n14:00 hx Budget sync\n")]}),
            ("the document has a different title", {"docs": [dict(doc, title="agenda")]}),
            ("no document was created", {"docs": []}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for e in expected.get("events", []):
            await world.calendar.event_delete(e["id"])
        for f in await world.drive.files_list(name_contains=expected["doc_title"]):
            await world.drive.file_delete(f["id"])


register(CalendarToDoc())
