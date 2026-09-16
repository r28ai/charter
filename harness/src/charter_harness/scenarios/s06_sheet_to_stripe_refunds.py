"""gsheets + stripe — refund each customer the amount a spreadsheet says."""

from __future__ import annotations

from charter_harness.scenarios._fixtures import email, person
from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

# (charged cents, refund cents) — two partial refunds and one full, so a blanket
# "refund everything" fails and so does "refund the first amount for everyone".
PAYMENTS = [(4000, 1500), (2500, 2500), (9900, 3000)]
CURRENCY = "usd"


def _dollars(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


class SheetToStripeRefunds(Scenario):
    id = "sheet_to_stripe_refunds"
    packs = ("gsheets", "stripe")
    summary = "For each (email, amount) row, refund that amount on the customer's payment."
    # payments: (charged cents, refund cents) per customer
    defaults = {"payments": PAYMENTS}
    variants = {
        "two": {"payments": [(4000, 1500), (2500, 2500)]},
        "four": {"payments": PAYMENTS + [(1200, 600)]},
        "five": {"payments": [(4000, 1500), (2500, 2500), (9900, 3000), (1200, 600), (7000, 7000)]},
        "all_partial": {"payments": [(5000, 1000), (7500, 2500), (3300, 300)]},
        "all_full": {"payments": [(1999, 1999), (4500, 4500), (825, 825)]},
        "odd_cents": {"payments": [(1234, 567), (9999, 1), (5050, 2525)]},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        customers = []
        rows = [["Email", "Refund (USD)"]]
        for i, (charged, refund) in enumerate(self.params["payments"]):
            name, _ = person(i)
            addr = email(ns, i)
            customer = await world.stripe.customer_create(email=addr, name=name, ns=ns)
            intent = await world.stripe.payment_intent_create_confirmed(
                customer_id=customer["id"], amount=charged, currency=CURRENCY, ns=ns, description=f"{ns} order {i + 1}"
            )
            customers.append(
                {
                    "customer_id": customer["id"],
                    "email": addr,
                    "payment_intent": intent["id"],
                    "charge": intent.get("latest_charge"),
                    "charged": charged,
                    "refund": refund,
                }
            )
            rows.append([addr, _dollars(refund)])
        sheet = await world.sheets.spreadsheet_create(f"{ns} refunds")
        await world.sheets.values_update(sheet["spreadsheetId"], f"Sheet1!A1:B{len(rows)}", rows)
        return {"spreadsheet_id": sheet["spreadsheetId"], "customers": customers}

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"The Google Sheet with id {expected['spreadsheet_id']} (sheet \"Sheet1\") lists refunds to issue: "
            f"a header row, then one row per customer with their email address and the amount to refund in "
            f"US dollars. For each row, find that customer in Stripe, find their most recent successful "
            f"payment, and refund exactly the listed amount on it. Do not refund anything else."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        refunds = {}
        for c in expected["customers"]:
            items = await world.stripe.refunds_for_payment_intent(c["payment_intent"])
            refunds[c["payment_intent"]] = [
                {"amount": r.get("amount"), "status": r.get("status")} for r in items if r.get("status") != "failed"
            ]
        return {"refunds": refunds}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        conditions = []
        for c in expected["customers"]:
            items = observed["refunds"].get(c["payment_intent"], [])
            total = sum(int(r["amount"] or 0) for r in items)
            conditions.append((total == c["refund"], f"{c['email']}: refunded {total} cents, expected {c['refund']}"))
            conditions.append((len(items) <= 1, f"{c['email']}: {len(items)} refunds issued instead of one"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "spreadsheet_id": "s",
            "customers": [
                {"customer_id": "cus_1", "email": "ada.hx@harness.invalid", "payment_intent": "pi_1", "charge": "ch_1", "charged": 4000, "refund": 1500},
                {"customer_id": "cus_2", "email": "grace.hx@harness.invalid", "payment_intent": "pi_2", "charge": "ch_2", "charged": 2500, "refund": 2500},
            ],
        }
        observed = {"refunds": {"pi_1": [{"amount": 1500, "status": "succeeded"}], "pi_2": [{"amount": 2500, "status": "succeeded"}]}}
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        r = observed["refunds"]
        return [
            ("a partial refund was issued for the full charge", {"refunds": {**r, "pi_1": [{"amount": 4000, "status": "succeeded"}]}}),
            ("one customer was not refunded", {"refunds": {**r, "pi_2": []}}),
            ("a refund was issued twice", {"refunds": {**r, "pi_1": [{"amount": 1500, "status": "succeeded"}, {"amount": 1500, "status": "succeeded"}]}}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for c in expected.get("customers", []):
            await world.stripe.customer_delete(c["customer_id"])
        await world.drive.file_delete(expected["spreadsheet_id"])


register(SheetToStripeRefunds())
