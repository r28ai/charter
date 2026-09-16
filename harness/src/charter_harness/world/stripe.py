"""
Stripe (test mode), read and written directly.

Fixtures are customers tagged ``metadata[harness]=<ns>`` and PaymentIntents
confirmed with ``pm_card_visa``. Read-back goes by the ids the seed recorded —
never by Stripe's search API, which is eventually consistent and would make a
correct run read as wrong.
"""

from __future__ import annotations

from typing import Any

from charter_harness.world._http import Http, WorldError

__all__ = ["Stripe"]


class Stripe:
    def __init__(self, http: Http) -> None:
        self.http = http

    async def customer_create(self, *, email: str, name: str, ns: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
        data = {"email": email, "name": name, "metadata[harness]": ns}
        for k, v in (extra or {}).items():
            data[f"metadata[{k}]"] = v
        return await self.http.json("POST", "v1/customers", data=data)

    async def customer_get(self, customer_id: str) -> dict[str, Any] | None:
        try:
            data = await self.http.json("GET", f"v1/customers/{customer_id}")
        except WorldError as exc:
            if exc.status == 404:
                return None
            raise
        return None if data.get("deleted") else data

    async def customers_by_email(self, email: str) -> list[dict[str, Any]]:
        data = await self.http.json("GET", "v1/customers", params={"email": email, "limit": 100})
        return [c for c in data.get("data", []) if not c.get("deleted")]

    async def customer_delete(self, customer_id: str) -> None:
        try:
            await self.http.request("DELETE", f"v1/customers/{customer_id}")
        except WorldError as exc:
            if exc.status != 404:
                raise

    async def payment_intent_create_confirmed(
        self, *, customer_id: str, amount: int, currency: str, ns: str, description: str = ""
    ) -> dict[str, Any]:
        """A succeeded PaymentIntent with a real (test) charge behind it.

        ``pm_card_mastercard`` rather than the more usual ``pm_card_visa``: the
        test account this harness was built against declines 4242 with a
        Radar rule, and the Mastercard test card is not affected."""
        return await self.http.json(
            "POST",
            "v1/payment_intents",
            data={
                "amount": str(amount),
                "currency": currency,
                "customer": customer_id,
                "payment_method": "pm_card_mastercard",
                "confirm": "true",
                "payment_method_types[]": "card",
                "description": description,
                "metadata[harness]": ns,
            },
        )

    async def payment_intent_get(self, payment_intent_id: str) -> dict[str, Any]:
        return await self.http.json("GET", f"v1/payment_intents/{payment_intent_id}")

    async def refunds_for_payment_intent(self, payment_intent_id: str) -> list[dict[str, Any]]:
        data = await self.http.json(
            "GET", "v1/refunds", params={"payment_intent": payment_intent_id, "limit": 100}
        )
        return data.get("data", [])

    async def charge_get(self, charge_id: str) -> dict[str, Any]:
        return await self.http.json("GET", f"v1/charges/{charge_id}")
