"""
Shopify Admin GraphQL, read and written directly on a development store.

Fixtures are products and customers tagged with the namespace; read-back
searches on the tag. Inventory is set at the store's first location with
``inventorySetQuantities``, which is the one part of the Admin API that takes a
few calls to say "this product has 3 units".
"""

from __future__ import annotations

import uuid
from typing import Any

from charter_harness.world._http import Http, WorldError, eventually

__all__ = ["Shopify"]


class Shopify:
    def __init__(self, http: Http, *, shop: str, api_version: str) -> None:
        self.http = http
        self.shop = shop
        self.api_version = api_version
        self._location_id: str | None = None

    @property
    def graphql_path(self) -> str:
        return f"admin/api/{self.api_version}/graphql.json"

    async def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        data = await self.http.json("POST", self.graphql_path, json={"query": query, "variables": variables or {}})
        if data.get("errors"):
            raise WorldError(f"Shopify GraphQL error: {data['errors']}", status=200, body=str(data)[:2000])
        return data["data"]

    @staticmethod
    def _check(payload: dict[str, Any], op: str) -> dict[str, Any]:
        errors = payload.get("userErrors") or []
        if errors:
            raise WorldError(f"Shopify {op} userErrors: {errors}", status=200)
        return payload

    async def location_id(self) -> str:
        if self._location_id is None:
            data = await self.gql("{ locations(first: 1) { nodes { id name } } }")
            nodes = data["locations"]["nodes"]
            if not nodes:
                raise WorldError("The Shopify store has no locations")
            self._location_id = str(nodes[0]["id"])
        return str(self._location_id)

    # ---- products

    async def product_create(self, *, title: str, tags: list[str], inventory: int, price: str = "10.00") -> dict[str, Any]:
        data = await self.gql(
            """
            mutation($input: ProductCreateInput!) {
              productCreate(product: $input) {
                product { id title tags status variants(first: 1) { nodes { id inventoryItem { id } } } }
                userErrors { field message }
              }
            }
            """,
            {"input": {"title": title, "tags": tags, "status": "ACTIVE"}},
        )
        product = self._check(data["productCreate"], "productCreate")["product"]
        variant = product["variants"]["nodes"][0]
        inventory_item_id = variant["inventoryItem"]["id"]
        location = await self.location_id()
        # Track and stock the default variant.
        await self.gql(
            """
            mutation($id: ID!, $input: InventoryItemInput!) {
              inventoryItemUpdate(id: $id, input: $input) { inventoryItem { id tracked } userErrors { field message } }
            }
            """,
            {"id": inventory_item_id, "input": {"tracked": True}},
        )
        # Since 2026-07 the inventory mutations refuse to run without an
        # ``@idempotent`` key on the field, and ``inventorySetQuantities`` is
        # compare-and-set only (``ignoreCompareQuantity`` is gone): every quantity
        # must say what it expects to overwrite. Each seed is a distinct write, so
        # a fresh key per call is the honest value.
        activated = await self.gql(
            """
            mutation($id: ID!, $location: ID!, $key: String!) {
              inventoryActivate(inventoryItemId: $id, locationId: $location) @idempotent(key: $key) {
                inventoryLevel { id quantities(names: ["available"]) { name quantity } }
                userErrors { field message }
              }
            }
            """,
            {"id": inventory_item_id, "location": location, "key": uuid.uuid4().hex},
        )
        level = self._check(activated["inventoryActivate"], "inventoryActivate")["inventoryLevel"]
        current = next((q["quantity"] for q in level["quantities"] if q["name"] == "available"), 0)
        set_data = await self.gql(
            """
            mutation($input: InventorySetQuantitiesInput!, $key: String!) {
              inventorySetQuantities(input: $input) @idempotent(key: $key) { userErrors { field message } }
            }
            """,
            {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "quantities": [
                        {
                            "inventoryItemId": inventory_item_id,
                            "locationId": location,
                            "quantity": inventory,
                            "changeFromQuantity": current,
                        }
                    ],
                },
                "key": uuid.uuid4().hex,
            },
        )
        self._check(set_data["inventorySetQuantities"], "inventorySetQuantities")
        await self.gql(
            """
            mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) { userErrors { field message } }
            }
            """,
            {"productId": product["id"], "variants": [{"id": variant["id"], "price": price}]},
        )
        return product

    async def products_tagged(self, tag: str) -> list[dict[str, Any]]:
        data = await self.gql(
            """
            query($q: String!) {
              products(first: 50, query: $q) {
                nodes { id title tags totalInventory variants(first: 1) { nodes { id price inventoryQuantity } } }
              }
            }
            """,
            {"q": f"tag:{tag}"},
        )
        return data["products"]["nodes"]

    async def await_products_tagged(
        self, tag: str, ids: list[str], *, inventories: dict[str, int] | None = None, timeout: float = 90.0
    ) -> list[dict[str, Any]]:
        """Wait until every seeded product is findable by tag — and, when
        ``inventories`` (id -> units) is given, until each product's
        ``totalInventory`` reports the units the seed set.

        Both lag: the ``query:`` search is an index, and ``totalInventory`` is an
        aggregate that can read 0 for several seconds after
        ``inventorySetQuantities`` succeeded. An agent shown 0 for a product
        stocked at 30 would list it as low, and be right to.
        """
        wanted = set(ids)
        expected = inventories or {}

        def settled(products: list[dict[str, Any]]) -> bool:
            seen = {p["id"]: p for p in products}
            return wanted <= set(seen) and all(seen[i].get("totalInventory") == units for i, units in expected.items())

        got = await eventually(lambda: self.products_tagged(tag), settled, timeout=timeout, interval=3.0)
        missing = wanted - {p["id"] for p in got}
        if missing:
            raise WorldError(f"{len(missing)} Shopify product(s) tagged {tag!r} not searchable after {timeout:.0f}s")
        stale = {p["title"]: (p.get("totalInventory"), expected[p["id"]]) for p in got if p["id"] in expected and p.get("totalInventory") != expected[p["id"]]}
        if stale:
            raise WorldError(f"Shopify inventory not settled after {timeout:.0f}s (seen, set): {stale}")
        return got

    async def product_delete(self, product_id: str) -> None:
        try:
            await self.gql(
                "mutation($input: ProductDeleteInput!) { productDelete(input: $input) { deletedProductId userErrors { message } } }",
                {"input": {"id": product_id}},
            )
        except WorldError:
            pass

    # ---- customers

    async def customer_create(self, *, email: str, first_name: str, last_name: str, tags: list[str]) -> dict[str, Any]:
        data = await self.gql(
            """
            mutation($input: CustomerInput!) {
              customerCreate(input: $input) {
                customer { id email firstName lastName tags }
                userErrors { field message }
              }
            }
            """,
            {"input": {"email": email, "firstName": first_name, "lastName": last_name, "tags": tags}},
        )
        return self._check(data["customerCreate"], "customerCreate")["customer"]

    async def customers_tagged(self, tag: str) -> list[dict[str, Any]]:
        data = await self.gql(
            "query($q: String!) { customers(first: 50, query: $q) { nodes { id email firstName lastName tags } } }",
            {"q": f"tag:{tag}"},
        )
        return data["customers"]["nodes"]

    async def await_customers_tagged(self, tag: str, ids: list[str], *, timeout: float = 90.0) -> list[dict[str, Any]]:
        wanted = set(ids)
        got = await eventually(lambda: self.customers_tagged(tag), lambda cs: wanted <= {c["id"] for c in cs}, timeout=timeout, interval=3.0)
        missing = wanted - {c["id"] for c in got}
        if missing:
            raise WorldError(f"{len(missing)} Shopify customer(s) tagged {tag!r} not searchable after {timeout:.0f}s")
        return got

    async def customer_delete(self, customer_id: str) -> None:
        try:
            await self.gql(
                "mutation($input: CustomerDeleteInput!) { customerDelete(input: $input) { deletedCustomerId userErrors { message } } }",
                {"input": {"id": customer_id}},
            )
        except WorldError:
            pass
