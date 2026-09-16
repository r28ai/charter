"""stripe + gsheets — report a set of customers into a spreadsheet."""

from __future__ import annotations

from charter_harness.scenarios._fixtures import email, person
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World


class StripeToSheet(Scenario):
    id = "stripe_to_sheet"
    packs = ("stripe", "gsheets")
    summary = "Find the Stripe customers matching an email pattern and list them (email, id) in a sheet."
    # count: customers in the batch. distractors: customers from another
    # "batch" — same people, near-miss addresses — that must not be reported.
    defaults = {"count": 4, "distractors": 1}
    variants = {
        "two": {"count": 2},
        "six": {"count": 6},
        "eight": {"count": 8},
        "no_distractor": {"count": 4, "distractors": 0},
        "three_distractors": {"count": 4, "distractors": 3},
        "six_three_distractors": {"count": 6, "distractors": 3},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        customers = []
        for i in range(self.params["count"]):
            name, _ = person(i)
            c = await world.stripe.customer_create(email=email(ns, i), name=name, ns=ns)
            customers.append({"id": c["id"], "email": c["email"]})
        distractor_ids = []
        for i in range(self.params["distractors"]):
            name, handle = person(i + 4)
            other = await world.stripe.customer_create(
                email=f"{handle}.zz{ns[::-1]}{i}@harness.invalid", name=name, ns=f"not-{ns}"
            )
            distractor_ids.append(other["id"])
        sheet = await world.sheets.spreadsheet_create(f"{ns} customers")
        await world.sheets.values_update(sheet["spreadsheetId"], "Sheet1!A1:B1", [["Email", "Customer ID"]])
        return {
            "spreadsheet_id": sheet["spreadsheetId"],
            "customers": customers,
            "distractor_ids": distractor_ids,
            "marker": f".{ns}@",
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"In Stripe, find every customer whose email address contains \"{expected['marker']}\" — that is, "
            f"the customers created for batch {ns}. In the Google Sheet with id {expected['spreadsheet_id']} "
            f"(sheet \"Sheet1\", header row already present: Email, Customer ID), add one row per such "
            f"customer with their email address and their Stripe customer id. Do not include any other customer."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        return {"values": await world.sheets.values_get(expected["spreadsheet_id"], "Sheet1!A1:B200")}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        rows = [r for r in observed["values"][1:] if any(str(c).strip() for c in r)]
        wanted = {(c["email"].casefold(), c["id"]) for c in expected["customers"]}
        got = {(str(r[0]).strip().casefold() if len(r) > 0 else "", str(r[1]).strip() if len(r) > 1 else "") for r in rows}
        return check(
            [
                (wanted <= got, f"missing or wrong rows for {sorted(wanted - got)}"),
                (not (got - wanted), f"unexpected rows {sorted(got - wanted)}"),
            ]
        )

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "spreadsheet_id": "s",
            "customers": [{"id": "cus_A", "email": "ada.hx@harness.invalid"}, {"id": "cus_B", "email": "grace.hx@harness.invalid"}],
            "distractor_ids": ["cus_Z"],
            "marker": ".hx@",
        }
        observed = {"values": [["Email", "Customer ID"], ["ada.hx@harness.invalid", "cus_A"], ["Grace.hx@harness.invalid", "cus_B"]]}
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        v = observed["values"]
        return [
            ("the distractor customer was included", {"values": v + [["dennis.zzxh0@harness.invalid", "cus_Z"]]}),
            ("a customer is missing", {"values": v[:-1]}),
            ("an id is wrong", {"values": v[:-1] + [[v[-1][0], "cus_WRONG"]]}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for c in expected.get("customers", []):
            await world.stripe.customer_delete(c["id"])
        for cid in expected.get("distractor_ids", []):
            await world.stripe.customer_delete(cid)
        await world.drive.file_delete(expected["spreadsheet_id"])


register(StripeToSheet())
