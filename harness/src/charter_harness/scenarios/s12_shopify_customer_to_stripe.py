"""shopify + stripe — recreate a Shopify customer in Stripe, faithfully."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check, norm
from charter_harness.scenarios.registry import register
from charter_harness.world import World


class ShopifyCustomerToStripe(Scenario):
    id = "shopify_customer_to_stripe"
    packs = ("shopify", "stripe")
    summary = "Create a Stripe customer matching a tagged Shopify customer (email, name, metadata)."
    # first/last/handle: the tagged customer. lookalike: also create an untagged
    # Shopify customer with the same name and a different address.
    defaults = {
        "first_name": "Barbara",
        "last_name": "Liskov",
        "handle": "barbara",
        "lookalike": False,
    }
    variants = {
        "hyphenated": {
            "first_name": "Marie-Claire",
            "last_name": "Dubois",
            "handle": "marie-claire",
        },
        "accented": {"first_name": "José", "last_name": "Álvarez", "handle": "jose"},
        "apostrophe": {"first_name": "Siobhán", "last_name": "O'Neill", "handle": "siobhan"},
        "long_name": {
            "first_name": "Anna Maria",
            "last_name": "von der Leyen-Schmidt",
            "handle": "anna.maria",
        },
        "with_lookalike": {"lookalike": True},
        "accented_with_lookalike": {
            "first_name": "José",
            "last_name": "Álvarez",
            "handle": "jose",
            "lookalike": True,
        },
    }

    async def seed(self, world: World, ns: str) -> Expected:
        first, last = self.params["first_name"], self.params["last_name"]
        email = f"{self.params['handle']}.{ns}@harness.invalid"
        customer = await world.shopify.customer_create(
            email=email, first_name=first, last_name=last, tags=[ns, "harness"]
        )
        numeric_id = customer["id"].rsplit("/", 1)[-1]
        expected: Expected = {
            "tag": ns,
            "shopify_id": customer["id"],
            "shopify_numeric_id": numeric_id,
            "email": email,
            "name": f"{first} {last}",
        }
        if self.params["lookalike"]:
            other_email = f"{self.params['handle']}.zz{ns[::-1]}@harness.invalid"
            other = await world.shopify.customer_create(
                email=other_email, first_name=first, last_name=last, tags=["harness"]
            )
            expected["lookalike"] = {"shopify_id": other["id"], "email": other_email}
        await world.shopify.await_customers_tagged(ns, [customer["id"]])
        return expected

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f'A Shopify customer tagged "{expected["tag"]}" needs a matching Stripe customer. Look the '
            f"customer up in Shopify, then create a Stripe customer with the same email address and the same "
            f"full name, and set the Stripe customer's metadata key \"shopify_id\" to the Shopify customer's "
            f"numeric id. Create exactly one Stripe customer."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        customers = await world.stripe.customers_by_email(expected["email"])
        observed: Observed = {
            "customers": [
                {
                    "id": c["id"],
                    "email": c.get("email"),
                    "name": c.get("name"),
                    "metadata": c.get("metadata") or {},
                }
                for c in customers
            ]
        }
        if expected.get("lookalike"):
            others = await world.stripe.customers_by_email(expected["lookalike"]["email"])
            observed["lookalike_customers"] = [c["id"] for c in others]
        return observed

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        customers = observed["customers"]
        if observed.get("lookalike_customers"):
            return Verdict.fail(
                "a Stripe customer was created for the untagged customer with the same name"
            )
        if len(customers) != 1:
            return Verdict.fail(
                f"expected exactly one Stripe customer with email {expected['email']}, found {len(customers)}"
            )
        c = customers[0]
        shopify_id = str(c["metadata"].get("shopify_id", ""))
        return check(
            [
                (norm(c["email"]) == norm(expected["email"]), "email differs"),
                (
                    norm(c["name"]) == norm(expected["name"]),
                    f"name is {c['name']!r}, expected {expected['name']!r}",
                ),
                (
                    expected["shopify_numeric_id"] in shopify_id,
                    f"metadata.shopify_id is {shopify_id!r}, expected {expected['shopify_numeric_id']}",
                ),
            ]
        )

    def example(self) -> tuple[Expected, Observed]:
        expected: Expected = {
            "tag": "hx",
            "shopify_id": "gid://shopify/Customer/8123",
            "shopify_numeric_id": "8123",
            "email": "barbara.hx@harness.invalid",
            "name": "Barbara Liskov",
        }
        observed: Observed = {
            "customers": [
                {
                    "id": "cus_1",
                    "email": "Barbara.hx@harness.invalid",
                    "name": "Barbara Liskov",
                    "metadata": {"shopify_id": "8123"},
                }
            ]
        }
        if self.params["lookalike"]:
            expected["lookalike"] = {
                "shopify_id": "gid://shopify/Customer/8124",
                "email": "barbara.zzxh@harness.invalid",
            }
            observed["lookalike_customers"] = []
        return expected, observed

    def wrong_observations(
        self, expected: Expected, observed: Observed
    ) -> list[tuple[str, Observed]]:
        c = observed["customers"][0]
        wrongs = [
            ("no customer with that email exists (email mismatch)", {**observed, "customers": []}),
            ("the name is wrong", {**observed, "customers": [dict(c, name="Barbara")]}),
            ("the Shopify id is not recorded", {**observed, "customers": [dict(c, metadata={})]}),
            ("the customer was created twice", {**observed, "customers": [c, dict(c, id="cus_2")]}),
        ]
        if expected.get("lookalike"):
            wrongs.append(
                (
                    "the untagged lookalike was copied instead",
                    {**observed, "customers": [], "lookalike_customers": ["cus_9"]},
                )
            )
        return wrongs

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        emails = [expected["email"]] + (
            [expected["lookalike"]["email"]] if expected.get("lookalike") else []
        )
        for addr in emails:
            for c in await world.stripe.customers_by_email(addr):
                await world.stripe.customer_delete(c["id"])
        await world.shopify.customer_delete(expected["shopify_id"])
        if expected.get("lookalike"):
            await world.shopify.customer_delete(expected["lookalike"]["shopify_id"])


register(ShopifyCustomerToStripe())
