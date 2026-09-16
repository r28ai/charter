"""shopify + github — one GitHub issue listing the products that are low on stock."""

from __future__ import annotations

from charter_harness.scenarios.base import Expected, Observed, Scenario, Verdict, check
from charter_harness.scenarios.registry import register
from charter_harness.world import World

PRODUCTS = [("Canvas tote", 2), ("Enamel mug", 12), ("Linen apron", 0), ("Beeswax candle", 30)]
THRESHOLD = 5


class ShopifyLowStockToGitHub(Scenario):
    id = "shopify_low_stock_to_github"
    packs = ("shopify", "github")
    summary = "Open one GitHub issue listing every tagged Shopify product with inventory below a threshold."
    # products: (title, inventory). threshold: strictly-below counts as low.
    defaults = {"products": PRODUCTS, "threshold": THRESHOLD}
    variants = {
        "two": {"products": [("Canvas tote", 2), ("Enamel mug", 12)]},
        "six": {"products": PRODUCTS + [("Wool scarf", 4), ("Ceramic bowl", 7)]},
        "boundary_ten": {"products": [("Canvas tote", 10), ("Enamel mug", 9), ("Linen apron", 11), ("Beeswax candle", 0)], "threshold": 10},
        "all_low": {"products": [("Canvas tote", 1), ("Enamel mug", 3), ("Linen apron", 0)]},
        "one_low": {"products": [("Canvas tote", 25), ("Enamel mug", 12), ("Linen apron", 4), ("Beeswax candle", 30)]},
        "threshold_one": {"products": [("Canvas tote", 0), ("Enamel mug", 1), ("Linen apron", 0), ("Beeswax candle", 2)], "threshold": 1},
    }

    async def seed(self, world: World, ns: str) -> Expected:
        await world.github.ensure_sandbox()
        products = []
        for title, inventory in self.params["products"]:
            p = await world.shopify.product_create(title=f"{title} ({ns})", tags=[ns, "harness"], inventory=inventory)
            products.append({"id": p["id"], "title": f"{title} ({ns})", "inventory": inventory})
        await world.shopify.await_products_tagged(
            ns, [p["id"] for p in products], inventories={p["id"]: p["inventory"] for p in products}
        )
        return {
            "tag": ns,
            "products": products,
            "repo": world.github.full_name,
            "issue_title": f"[{ns}] Low stock",
            "threshold": self.params["threshold"],
        }

    def prompt(self, ns: str, expected: Expected) -> str:
        return (
            f"In Shopify, look at the products tagged \"{expected['tag']}\". Open exactly one issue in the "
            f"GitHub repository {expected['repo']} titled \"{expected['issue_title']}\" whose body lists "
            f"every one of those products with fewer than {expected['threshold']} units in stock, giving each "
            f"product's title and its current inventory. Products at or above {expected['threshold']} units "
            f"must not be mentioned anywhere in the issue, not even to say they were excluded."
        )

    async def observe(self, world: World, ns: str, expected: Expected) -> Observed:
        issues = await world.github.issues_search_in_sandbox(expected["issue_title"], state="open", expect=1)
        return {"issues": [{"number": i["number"], "title": i["title"], "body": i.get("body") or ""} for i in issues]}

    def judge(self, expected: Expected, observed: Observed) -> Verdict:
        issues = observed["issues"]
        if len(issues) != 1:
            return Verdict.fail(f"expected exactly one open issue titled {expected['issue_title']!r}, found {len(issues)}")
        body = issues[0]["body"].casefold()
        conditions = []
        for p in expected["products"]:
            present = p["title"].casefold() in body
            if p["inventory"] < expected["threshold"]:
                conditions.append((present, f"low-stock product {p['title']!r} is not listed"))
            else:
                conditions.append((not present, f"well-stocked product {p['title']!r} is listed"))
        return check(conditions)

    def example(self) -> tuple[Expected, Observed]:
        expected = {
            "tag": "hx",
            "products": [
                {"id": "gid://shopify/Product/1", "title": "Canvas tote (hx)", "inventory": 2},
                {"id": "gid://shopify/Product/2", "title": "Enamel mug (hx)", "inventory": 12},
                {"id": "gid://shopify/Product/3", "title": "Linen apron (hx)", "inventory": 0},
            ],
            "repo": "o/harness-sandbox",
            "issue_title": "[hx] Low stock",
            "threshold": 5,
        }
        observed = {"issues": [{"number": 3, "title": "[hx] Low stock", "body": "- Canvas tote (hx): 2 units\n- Linen apron (hx): 0 units\n"}]}
        return expected, observed

    def wrong_observations(self, expected: Expected, observed: Observed) -> list[tuple[str, Observed]]:
        issue = observed["issues"][0]
        return [
            ("a well-stocked product is listed", {"issues": [dict(issue, body=issue["body"] + "- Enamel mug (hx): 12 units\n")]}),
            ("a low-stock product is missing", {"issues": [dict(issue, body="- Canvas tote (hx): 2 units\n")]}),
            ("two issues were opened", {"issues": [issue, dict(issue, number=4)]}),
            ("no issue was opened", {"issues": []}),
        ]

    async def teardown(self, world: World, ns: str, expected: Expected) -> None:
        for p in expected.get("products", []):
            await world.shopify.product_delete(p["id"])
        for issue in await world.github.issues_search_in_sandbox(expected["issue_title"], state="open"):
            await world.github.issue_close(issue["number"])


register(ShopifyLowStockToGitHub())
