"""Shopify Admin GraphQL, against the development store.

Three of this pack's corrections are invisible without the real store, and two of
them fail *silently* when they are wrong:

* ``orderCancel`` reports refusal at ``orderCancelUserErrors``. The envelope used
  to read only ``data.*.userErrors``, so a refused cancellation came back as a
  success — and it is asynchronous besides, so even an accepted one has not
  happened yet when the mutation answers.
* ``inventoryAdjustQuantities`` requires both an ``@idempotent`` key and, since
  the version this pack pins, a ``changeFromQuantity`` on every change. Reusing a
  key does *not* replay the first response, whatever the name suggests — the
  request runs again and the compare-and-set refuses it. That is asserted here by
  deliberately reusing one, and it is why the pack's note about what the key
  protects was wrong before this file existed.
* ``tags`` on ``product_update`` replaces rather than appends.

The store token is an online one from ``shopify store auth`` and expires after 24
hours, so this module skips with the command to re-mint it rather than reporting
a wall of credential failures. Scopes are checked the same way: the harness token
carries products, customers, inventory and locations, and the order tests skip
until it also carries orders.
"""

from __future__ import annotations

import uuid

import pytest
from charter.packs import shopify
from charter.types.errors import CharterError

from charter_harness.world import eventually

pytestmark = pytest.mark.live

ORDER_SCOPES = "read_orders, write_orders, write_draft_orders, write_merchant_managed_fulfillment_orders"


@pytest.fixture(autouse=True)
async def shopify_is_reachable(needs, request):
    """One cheap call before each test, so an expired token reads as a skip.

    ``SHOPIFY_ACCESS_TOKEN`` is an *online* token despite its ``shpat_`` prefix,
    and it dies 24 hours after ``shopify store auth`` mints it. Without this every
    test in the file fails with a credential error and the run looks like a pack
    regression.
    """
    if "shopify" not in request.getfixturevalue("available"):
        pytest.skip("not configured: shopify")
    try:
        await shopify.shop_get.ainvoke({})
    except CharterError as exc:
        pytest.skip(
            "the Shopify token is not usable — re-mint it with `shopify store auth "
            f"--store $SHOPIFY_SHOP --scopes ...` and update harness/.env ({exc})"
        )


async def _product(world, trash, run_tag: str, *, title: str) -> dict:
    """A product through the pack, deleted on the way out."""
    made = await shopify.product_create.ainvoke(
        {"variables": {"product": {"title": title, "tags": [f"live-{run_tag}"], "status": "ACTIVE"}}}
    )
    trash.later(lambda: world.shopify.product_delete(made["id"]))
    return made


async def _default_variant(product_id: str) -> dict:
    product = await shopify.product_get.ainvoke({"variables": {"id": product_id}})
    return product["variants"]["nodes"][0]


# -----------------------------------------------------
# The store itself
# -----------------------------------------------------


async def test_the_shop_says_which_store_this_is(needs, settings):
    """``shop_get`` is how an agent confirms which store it is about to write to,
    and which currency the money on every other response is quoted in."""
    needs("shopify")
    shop = await shopify.shop_get.ainvoke({})
    assert shop["myshopifyDomain"] == settings.shopify_shop
    assert shop["currencyCode"]


# -----------------------------------------------------
# Products
# -----------------------------------------------------


async def test_a_product_is_created_read_updated_and_found(needs, world, trash, run_tag):
    """``tags`` on update *replaces*. The second tag list here is a different one,
    and the assertion is that the first is gone — which is the behaviour the
    docstring warns about and the one an agent gets wrong."""
    needs("shopify")
    product = await _product(world, trash, run_tag, title=f"Live widget {run_tag}")
    # Shopify creates products unpublished-but-ACTIVE; the status is worth pinning
    # because an agent listing 'status:active' has to know what it will see.
    assert product["status"] == "ACTIVE"
    assert product["tags"] == [f"live-{run_tag}"]

    found = await shopify.product_get.ainvoke({"variables": {"id": product["id"]}})
    assert found["title"] == f"Live widget {run_tag}"
    assert found["variants"]["nodes"], "a new product still gets its placeholder variant"

    updated = await shopify.product_update.ainvoke(
        {
            "variables": {
                "product": {
                    "id": product["id"],
                    "descriptionHtml": "<p>Edited by the live suite.</p>",
                    "tags": [f"live-{run_tag}", "edited"],
                }
            }
        }
    )
    assert sorted(updated["tags"]) == sorted([f"live-{run_tag}", "edited"])

    replaced = await shopify.product_update.ainvoke(
        {"variables": {"product": {"id": product["id"], "tags": ["edited"]}}}
    )
    assert replaced["tags"] == ["edited"], "tags replace rather than append"

    # The search index lags, so the wait is bounded rather than assumed.
    listed = await eventually(
        lambda: shopify.products_list.ainvoke(
            {"variables": {"first": 50, "query": f"title:Live widget {run_tag}"}}
        ),
        lambda page: product["id"] in [p["id"] for p in page["nodes"]],
        timeout=45.0,
    )
    assert product["id"] in [p["id"] for p in listed["nodes"]]


async def test_a_variant_carries_its_sku_inside_the_inventory_item(
    needs, world, trash, run_tag
):
    """The SKU is on ``inventoryItem``, not on the variant — the single most
    common way to write this mutation wrongly, and Shopify accepts the wrong
    spelling as an unknown field rather than silently ignoring it.

    ``REMOVE_STANDALONE_VARIANT`` is required while the product still carries the
    placeholder variant Shopify creates with it.

    ``optionName`` has to be an option the product *already* has — a fresh
    product has exactly one, "Title" — because this pack cannot create product
    options. Naming a new one is a ``userErrors`` refusal, "Option does not
    exist", which the envelope turns into a raised error rather than a silent
    empty result.
    """
    needs("shopify")
    product = await _product(world, trash, run_tag, title=f"Live variants {run_tag}")

    created = await shopify.product_variants_bulk_create.ainvoke(
        {
            "variables": {
                "productId": product["id"],
                "strategy": "REMOVE_STANDALONE_VARIANT",
                "variants": [
                    {
                        "optionValues": [{"name": "Large", "optionName": "Title"}],
                        "price": "24.99",
                        "inventoryItem": {"sku": f"LIVE-{run_tag}-L", "tracked": True},
                    }
                ],
            }
        }
    )
    variant = created[0] if isinstance(created, list) else created["productVariants"][0]
    assert variant["price"] == "24.99"
    assert variant["inventoryItem"]["sku"] == f"LIVE-{run_tag}-L"
    assert variant["selectedOptions"] == [{"name": "Title", "value": "Large"}]


# -----------------------------------------------------
# Inventory
# -----------------------------------------------------


async def test_stock_moves_by_a_delta_and_a_reused_key_moves_nothing(
    needs, world, trash, run_tag
):
    """``inventory_adjust_quantities`` is relative, not absolute, and what makes
    a retry of it safe is not what the pack used to say.

    ``change_from_quantity`` is a compare-and-set: the caller states what it
    expects to overwrite, and Shopify has required that since the version this
    pack pins — without it the mutation is rejected at the GraphQL layer and never
    runs at all.

    The second half re-sends an identical request under the *same* idempotency
    key. The documented reading of `@idempotent` is that the first response is
    replayed; what the API actually does is execute it again and refuse it,
    because the expected quantity is now stale. Both halves matter and neither is
    observable offline: a mock replays whatever it is told to.
    """
    needs("shopify")
    seeded = await world.shopify.product_create(
        title=f"Live stock {run_tag}", tags=[f"live-{run_tag}"], inventory=10
    )
    trash.later(lambda: world.shopify.product_delete(seeded["id"]))
    variant = seeded["variants"]["nodes"][0]
    inventory_item = variant["inventoryItem"]["id"]

    locations = await shopify.locations_list.ainvoke({"variables": {"first": 5}})
    assert locations["nodes"], "the store has no locations"
    location = locations["nodes"][0]["id"]

    before = await shopify.variant_inventory_level.ainvoke(
        {"variables": {"id": variant["id"], "locationId": location, "names": ["available"]}}
    )
    level = before["inventoryItem"]["inventoryLevel"]
    assert level is not None, "the seed stocked this variant at the store's first location"
    start = next(q["quantity"] for q in level["quantities"] if q["name"] == "available")
    assert start == 10

    moved = await shopify.inventory_adjust_quantities.ainvoke(
        {
            "variables": {
                "idempotencyKey": uuid.uuid4().hex,
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "changes": [
                        {
                            "delta": 5,
                            "inventoryItemId": inventory_item,
                            "locationId": location,
                            "changeFromQuantity": start,
                        }
                    ],
                },
            }
        }
    )
    # Two changes, not one: moving `available` moves `on_hand` with it, which the
    # tool cannot ask for and Shopify does anyway.
    assert {c["name"] for c in moved["changes"]} == {"available", "on_hand"}
    assert all(c["delta"] == 5 for c in moved["changes"])
    # `quantityAfterChange` comes back null on this mutation, always. The new
    # count is only readable from the level, which is what the end of this test
    # does — an agent that reported this field would report nothing.
    assert all(c["quantityAfterChange"] is None for c in moved["changes"])

    # One key and one payload, sent twice. Not a replay: the second is executed
    # and refused, because `change_from_quantity` no longer describes the world.
    key = uuid.uuid4().hex
    again = {
        "variables": {
            "idempotencyKey": key,
            "input": {
                "name": "available",
                "reason": "correction",
                "changes": [
                    {
                        "delta": 3,
                        "inventoryItemId": inventory_item,
                        "locationId": location,
                        "changeFromQuantity": start + 5,
                    }
                ],
            },
        }
    }
    await shopify.inventory_adjust_quantities.ainvoke(again)
    with pytest.raises(CharterError) as refused:
        await shopify.inventory_adjust_quantities.ainvoke(again)
    assert "changeFromQuantity" in str(refused.value)

    after = await shopify.variant_inventory_level.ainvoke(
        {"variables": {"id": variant["id"], "locationId": location, "names": ["available"]}}
    )
    ended = next(
        q["quantity"]
        for q in after["inventoryItem"]["inventoryLevel"]["quantities"]
        if q["name"] == "available"
    )
    assert ended == start + 8, "the refused retry must not have applied its delta"


# -----------------------------------------------------
# Customers
# -----------------------------------------------------


async def test_a_customer_is_created_read_updated_and_found(needs, world, trash, run_tag):
    """``email`` and ``phone`` are deprecated on the Shopify object and live under
    ``defaultEmailAddress``/``defaultPhoneNumber``; the handler collapses them
    back. Reading them at the flat names is the check that it still does."""
    needs("shopify")
    email = f"{run_tag}@harness.invalid"

    made = await shopify.customer_create.ainvoke(
        {
            "variables": {
                "input": {
                    "email": email,
                    "firstName": "Live",
                    "lastName": f"Check {run_tag}",
                    "tags": [f"live-{run_tag}"],
                }
            }
        }
    )
    trash.later(lambda: world.shopify.customer_delete(made["id"]))
    assert made["email"] == email

    found = await shopify.customer_get.ainvoke({"variables": {"id": made["id"]}})
    assert found["email"] == email
    assert found["displayName"] == f"Live Check {run_tag}"
    # Present and null rather than absent: the customer has no phone, and the
    # handler keeps the key so the caller can tell those apart.
    assert found["phone"] is None

    updated = await shopify.customer_update.ainvoke(
        {"variables": {"input": {"id": made["id"], "note": "Edited by the live suite."}}}
    )
    assert updated["id"] == made["id"]

    listed = await eventually(
        lambda: shopify.customers_list.ainvoke(
            {"variables": {"first": 25, "query": f"email:{email}"}}
        ),
        lambda page: made["id"] in [c["id"] for c in page["nodes"]],
        timeout=45.0,
    )
    assert made["id"] in [c["id"] for c in listed["nodes"]]


# -----------------------------------------------------
# Orders: the half the harness token does not yet reach
# -----------------------------------------------------


async def test_an_order_is_built_fulfilled_closed_and_cancelled(
    needs, world, trash, run_tag, scope_skip
):
    """A draft order becomes an order, the order is fulfilled, closed, reopened
    and cancelled. Seven tools, and the only sequence in this pack where each one
    is unreachable without the last.

    ``order_cancel`` is asserted through a *re-read*, not through its own answer:
    it returns a background job, so an empty error list means the cancellation was
    accepted rather than done.
    """
    needs("shopify")
    product = await _product(world, trash, run_tag, title=f"Live order {run_tag}")
    variant = await _default_variant(product["id"])

    try:
        draft = await shopify.draft_order_create.ainvoke(
            {
                "variables": {
                    "input": {
                        "lineItems": [{"variantId": variant["id"], "quantity": 1}],
                        "tags": [f"live-{run_tag}"],
                    }
                }
            }
        )
    except CharterError as exc:
        scope_skip(exc, scope=ORDER_SCOPES)
        raise
    assert draft["status"] == "OPEN"

    completed = await shopify.draft_order_complete.ainvoke({"variables": {"id": draft["id"]}})
    order_id = completed["order"]["id"]

    order = await shopify.order_get.ainvoke({"variables": {"id": order_id}})
    assert order["displayFulfillmentStatus"] == "UNFULFILLED"

    fulfillment_orders = await shopify.order_fulfillment_orders.ainvoke(
        {"variables": {"id": order_id, "first": 10}}
    )
    open_orders = [
        fo for fo in fulfillment_orders["fulfillmentOrders"]["nodes"] if fo["status"] == "OPEN"
    ]
    assert open_orders, "a new unfulfilled order has an open fulfillment order"

    fulfilled = await shopify.fulfillment_create.ainvoke(
        {
            "variables": {
                "fulfillment": {
                    "lineItemsByFulfillmentOrder": [
                        {"fulfillmentOrderId": open_orders[0]["id"]}
                    ],
                    "notifyCustomer": False,
                    "trackingInfo": {"company": "Live suite", "number": run_tag},
                },
                "message": f"live fulfilment {run_tag}",
            }
        }
    )
    assert fulfilled["status"] == "SUCCESS"

    closed = await shopify.order_close.ainvoke({"variables": {"input": {"id": order_id}}})
    assert closed["closed"] is True

    reopened = await shopify.order_open.ainvoke({"variables": {"input": {"id": order_id}}})
    assert reopened["closed"] is False

    await shopify.order_cancel.ainvoke(
        {
            "variables": {
                "orderId": order_id,
                "reason": "OTHER",
                "restock": True,
                "notifyCustomer": False,
                "staffNote": f"live cancel {run_tag}",
            }
        }
    )
    # The mutation answered with a job. Whether the order is cancelled is a
    # question for the order.
    settled = await eventually(
        lambda: shopify.order_get.ainvoke({"variables": {"id": order_id}}),
        lambda o: o["displayFinancialStatus"] in {"VOIDED", "REFUNDED"},
        timeout=60.0,
    )
    assert settled["displayFinancialStatus"] in {"VOIDED", "REFUNDED"}


async def test_the_order_listing_filters_are_accepted(needs, scope_skip):
    """``orders_list`` takes a Shopify search string. Only the last 60 days are
    returned without the read_all_orders scope, which is why nothing here asserts
    a count."""
    needs("shopify")
    try:
        orders = await shopify.orders_list.ainvoke(
            {
                "variables": {
                    "first": 5,
                    "query": "financial_status:paid fulfillment_status:unshipped",
                    "sortKey": "CREATED_AT",
                    "reverse": True,
                }
            }
        )
    except CharterError as exc:
        scope_skip(exc, scope=ORDER_SCOPES)
        raise
    assert "nodes" in orders
