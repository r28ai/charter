"""gmail + gsheets — one spreadsheet row per labelled message."""

from __future__ import annotations

from charter_harness.scenarios._fixtures import email, person
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World

SUBJECTS = [
    "Invoice overdue for order 4471",
    "Question about the enterprise plan",
    "Bug: export button does nothing",
    "Partnership proposal",
    "Renewal reminder",
    "Refund request for duplicate charge",
    "Feature request: bulk CSV import",
    "Security questionnaire from procurement",
]
DISTRACTOR_SUBJECTS = ["Weekly newsletter", "Your receipt", "Out of office", "Calendar invitation"]


class InboxToSheet(Scenario):
    id = "inbox_to_sheet"
    packs = ("gmail", "gsheets")
    summary = "List every message under a label as a row (sender, subject) in a spreadsheet."
    # count: labelled messages. distractors: inbox messages carrying the same
    # namespace in their subject but not the label — they must not become rows.
    defaults = {"count": 5, "distractors": 0}
    variants = {
        "two": {"count": 2},
        "three": {"count": 3},
        "seven": {"count": 7},
        "eight": {"count": 8},
        "with_distractors": {"count": 5, "distractors": 2},
        "three_with_distractors": {"count": 3, "distractors": 3},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        label = await world.gmail.label_create(f"{ns}-triage")
        rows = []
        ids = []
        for i in range(self.params["count"]):
            name, _ = person(i)
            addr = email(ns, i)
            subject = f"[{ns}] {SUBJECTS[i % len(SUBJECTS)]}"
            msg = await world.gmail.message_insert(
                sender=f"{name} <{addr}>",
                to="me@harness.invalid",
                subject=subject,
                body=f"Message {i + 1} for triage.",
                label_ids=["INBOX", label["id"]],
            )
            ids.append(msg["id"])
            rows.append({"email": addr, "subject": subject})
        distractor_ids = []
        for i in range(self.params["distractors"]):
            name, _ = person(i + 2)
            msg = await world.gmail.message_insert(
                sender=f"{name} <{email(ns, i + 2)}>",
                to="me@harness.invalid",
                subject=f"[{ns}] {DISTRACTOR_SUBJECTS[i % len(DISTRACTOR_SUBJECTS)]}",
                body="Not for triage.",
                label_ids=["INBOX"],
            )
            distractor_ids.append(msg["id"])
        await world.gmail.await_labelled(label["id"], ids)
        sheet = await world.sheets.spreadsheet_create(f"{ns} inbox triage")
        await world.sheets.values_update(sheet["spreadsheetId"], "Sheet1!A1:B1", [["From", "Subject"]])
        return {
            "label": {"id": label["id"], "name": label["name"]},
            "message_ids": ids,
            "distractor_ids": distractor_ids,
            "rows": rows,
            "spreadsheet_id": sheet["spreadsheetId"],
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"Every Gmail message labelled \"{expected['label']['name']}\" needs a row in the Google "
            f"Sheet with id {expected['spreadsheet_id']} (sheet \"Sheet1\", which already has the header "
            f"row \"From\", \"Subject\"). Add exactly one row per message, below the header: column A the "
            f"sender's email address, column B the subject line exactly as it appears. Do not add rows for "
            f"anything else."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        values = await world.sheets.values_get(expected["spreadsheet_id"], "Sheet1!A1:B200")
        return {"values": values}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        rows = [r for r in observed["values"][1:] if any(str(c).strip() for c in r)]
        wanted = {(r["email"].casefold(), norm(r["subject"])) for r in expected["rows"]}
        got = set()
        for row in rows:
            sender = str(row[0]) if len(row) > 0 else ""
            subject = norm(row[1]) if len(row) > 1 else ""
            match = next((e for e, _ in wanted if e in sender.casefold()), None)
            got.add((match or sender.casefold(), subject))
        return check(
            [
                (wanted <= got, f"missing rows for {sorted(wanted - got)}"),
                (len(rows) == len(expected["rows"]), f"expected {len(expected['rows'])} rows, found {len(rows)}"),
            ]
        )

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "label": {"id": "Label_2", "name": "hx-triage"},
            "message_ids": ["a", "b"],
            "distractor_ids": [],
            "rows": [
                {"email": "ada.hx@harness.invalid", "subject": "[hx] Invoice overdue for order 4471"},
                {"email": "grace.hx@harness.invalid", "subject": "[hx] Question about the enterprise plan"},
            ],
            "spreadsheet_id": "sheet1",
        }
        observed = {
            "values": [
                ["From", "Subject"],
                ["Ada Lovelace <ada.hx@harness.invalid>", "[hx] Invoice overdue for order 4471"],
                ["grace.hx@harness.invalid", "[HX] question about the Enterprise plan"],
            ]
        }
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        values = observed["values"]
        return [
            ("a message's row is missing", {"values": values[:-1]}),
            ("an extra row was added", {"values": values + [["nobody@harness.invalid", "[hx] Not a real message"]]}),
            ("an unlabelled message was rowed", {"values": values + [["edsger.hx@harness.invalid", "[hx] Weekly newsletter"]]}),
            ("a subject was altered", {"values": values[:-1] + [[values[-1][0], "Enterprise plan question"]]}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for mid in expected.get("message_ids", []) + expected.get("distractor_ids", []):
            await world.gmail.message_trash(mid)
        await world.gmail.label_delete(expected["label"]["id"])
        await world.drive.file_delete(expected["spreadsheet_id"])


register(InboxToSheet())
