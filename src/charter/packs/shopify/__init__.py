# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Shopify — ten tools over the Admin GraphQL API.

    from charter.packs import shopify

    shopify.configure(shop="my-store", access_token="shpat_...")
    await shopify.orders_list.ainvoke(
        variables={"query": "financial_status:paid fulfillment_status:unshipped"}
    )

``configure()`` is optional if ``$SHOPIFY_SHOP`` and ``$SHOPIFY_ACCESS_TOKEN``
are both set.

Shopify is the second GraphQL pack, and it breaks one assumption Linear did not.

**The host is a property of the installation, not of the API.** Every other pack
here has a fixed base URL. A Shopify store lives at
``https://{shop}.myshopify.com/``, so the host is only known once someone
installs the app. It cannot be a schema field — that would let the model choose
which server to talk to, which is the one thing a boundary must not permit — so
it is resolved at request time from what ``configure()`` was given. Zendesk,
Atlassian and self-hosted GitLab have the same shape.

**The API version is in the path, and pinning it is not optional.** Shopify
ships a new version quarterly and supports each for twelve months; an unpinned
integration is one that changes under you. :data:`API_VERSION` is the version
these documents were written against.

**Failure hides in ``userErrors``.** As with Linear, GraphQL's ``errors`` array
only carries problems with the *document*. A mutation Shopify ran and then
refused — a duplicate handle, a customer with no contact details — returns HTTP
200, no ``errors``, and a populated ``userErrors``. Both are caught by the
envelope on the factory — ``errors_field=("errors", "data.*.userErrors")``,
where ``*`` stands for whichever operation the tool called — rather than by
logic inside each mutation's response handler, where the first tool added
without one would report a refused write as a success.

**Rate limiting is a cost budget, not a request count.** Shopify prices each
query by the fields it selects, so the selection sets in
:mod:`~charter.packs.shopify.queries` are deliberately narrow, and ``first`` is
worth keeping small. ``quota_cost`` is left unset rather than fabricated: the
cost of a call depends on the page size it is invoked with, so no constant is
truthful.

Known limits, named rather than hidden:

* **Filtering is an untyped search string.** Shopify's ``query`` argument takes
  its own syntax rather than a filter object, so it cannot be typed the way
  Linear's ``IssueFilter`` can. The supported qualifiers are documented on each
  field instead.
* **Orders older than 60 days need a scope you must apply for.** Shopify serves
  only the last 60 days of orders to an app holding ``read_orders``; everything
  before that requires ``read_all_orders``, which is granted by review rather
  than by asking. The truncation is silent — no error, no marker in the page,
  just a shorter history than the store has — so ``orders_list`` says so in its
  description, where the model reading it will see it.
* **Search is eventually consistent; fetching by id is not.** A record created
  a moment ago is returned by ``customer_get``/``product_get`` immediately, but
  does not appear under ``query:`` for a few seconds — measured at 2-5s on a
  development store. An agent that creates a customer, searches for it to
  confirm, finds nothing and creates it again ends up with duplicates in a real
  store. Confirm a write with the id the mutation returned, not with a search.
* **Coverage is the read-and-triage core.** Products, orders, customers and the
  shop itself. Fulfillment, inventory adjustment, discounts and the Storefront
  API are not modelled.
* **Bulk operations are not modelled.** Shopify's answer to large exports is an
  asynchronous bulk query that you poll and then download; that is orchestration,
  and orchestration stays in your agent.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.shopify import queries
from charter.packs.shopify.response_handlers import unwrap, unwrap_mutation
from charter.packs.shopify.types import (
    CustomerCreateRequest,
    CustomerGetRequest,
    CustomersListRequest,
    CustomerUpdateRequest,
    DraftOrderCompleteRequest,
    DraftOrderCreateRequest,
    FulfillmentCreateRequest,
    InventoryAdjustRequest,
    LocationsRequest,
    OrderCancelRequest,
    OrderCloseRequest,
    OrderFulfillmentOrdersRequest,
    OrderGetRequest,
    OrderOpenRequest,
    OrdersListRequest,
    ProductCreateRequest,
    ProductGetRequest,
    ProductsListRequest,
    ProductUpdateRequest,
    ProductVariantsBulkCreateRequest,
    ShopGetRequest,
    VariantInventoryLevelRequest,
)
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.errors import CredentialError
from charter.types.pagination import Pagination


# Shopify fails in two places, and one declaration covers both.
#
# `errors` is GraphQL's own array. `data.*.userErrors` is the other one: a
# mutation Shopify ran and then refused — a duplicate handle, a customer with no
# contact details — returns HTTP 200, no `errors`, and a populated `userErrors`.
# The `*` stands for whichever operation the tool called, so every mutation is
# covered without a per-tool step anyone can forget. A query has no `userErrors`,
# and a successful mutation has an empty one, so neither matches.
def _throttled_retry_after(payload: Any) -> Optional[int]:
    """Seconds until the query that was just refused would fit in the budget.

    Shopify does not rate limit by request count; it prices each query by the
    fields it selects and draws from a bucket that refills at a fixed rate. A
    throttled call answers **HTTP 200** with `THROTTLED` in `errors`, and no
    `Retry-After` anywhere — but the same response carries the bucket state and
    the cost that did not fit, which is the whole of the arithmetic:

        (requested cost - currently available) / restore rate

    Without this an agent that hits the limit has no idea how long to wait, on
    the one API here whose limit is a budget rather than a count.
    https://shopify.dev/docs/api/usage/rate-limits
    """
    if not isinstance(payload, dict):
        return None
    cost = (payload.get("extensions") or {}).get("cost") or {}
    throttle = cost.get("throttleStatus") or {}
    requested = cost.get("requestedQueryCost")
    available = throttle.get("currentlyAvailable")
    restore = throttle.get("restoreRate")
    if not (
        isinstance(requested, (int, float))
        and isinstance(available, (int, float))
        and isinstance(restore, (int, float))
    ):
        return None
    if restore <= 0:
        return None
    deficit = float(requested) - float(available)
    if deficit <= 0:
        return None
    return max(1, math.ceil(deficit / float(restore)))


SHOPIFY_ENVELOPE = Envelope(
    # `orderCancel` is the one mutation in this pack that does not report through
    # `userErrors`. Its own `userErrors` field still exists and is deprecated, and
    # the live one is `orderCancelUserErrors`, so both paths are declared — a
    # mutation whose refusal is not read is a write reported as a success.
    errors_field=("errors", "data.*.userErrors", "data.*.orderCancelUserErrors"),
    retry_after=_throttled_retry_after,
)

# The Admin API version these documents were written against. Shopify releases
# quarterly and supports each version for twelve months.
API_VERSION = "2026-07"

GRAPHQL_PATH = f"admin/api/{API_VERSION}/graphql.json"
QUOTA_DOC_URL = "https://shopify.dev/docs/api/usage/rate-limits"

# Relay-style, like Linear: the cursor comes back nested under the connection and
# goes back out inside `variables`.
# https://shopify.dev/docs/api/usage/pagination-graphql
SHOPIFY_PAGINATION = Pagination(
    cursor_field="pageInfo.endCursor",
    cursor_param="variables.after",
    more_field="pageInfo.hasNextPage",
)


class _DeferredShopUrl:
    """The store's base URL, resolved at request time.

    Shopify's host is a property of the installation, so it is not known when
    the tools are built. This holds the place until ``configure()`` supplies it,
    and fails locally — before anything reaches the network — if it never does.
    """

    # The host, and the variable it reads, as documentation: the wire block on
    # the pack page renders these rather than restating the format by hand.
    template = "https://{shop}.myshopify.com/"
    env_var = "SHOPIFY_SHOP"

    def __init__(self) -> None:
        self._shop: Optional[str] = os.environ.get(self.env_var) or None

    def configure(self, shop: str) -> None:
        if not shop:
            raise CredentialError("charter.packs.shopify was given an empty shop name")
        # Accept "my-store", "my-store.myshopify.com", or the full URL, since all
        # three appear in Shopify's own documentation and admin UI.
        shop = shop.strip().removeprefix("https://").removeprefix("http://")
        self._shop = shop.rstrip("/").removesuffix(".myshopify.com")

    @property
    def is_configured(self) -> bool:
        return self._shop is not None

    def __call__(self) -> str:
        if self._shop is None:
            raise CredentialError(
                "charter.packs.shopify has no store. Call "
                "charter.packs.shopify.configure(shop=..., access_token=...) or set "
                "$SHOPIFY_SHOP.",
                provider="shopify",
            )
        return f"https://{self._shop}.myshopify.com/"

    def __repr__(self) -> str:
        return f"_DeferredShopUrl({self._shop or 'unconfigured'!r})"


_base_url = _DeferredShopUrl()

# Shopify does not use Authorization; the token has its own header.
# https://shopify.dev/docs/api/admin-graphql#authentication
_headers: DeferredApiKeyHeaders = api_key_headers(
    "shopify",
    {"X-Shopify-Access-Token": "CHARTER_UNCONFIGURED"},
    "X-Shopify-Access-Token",
    "SHOPIFY_ACCESS_TOKEN",
)


def configure(shop: str, access_token: str) -> None:
    """Point this pack's tools at one store.

    ``shop`` is the store's subdomain — ``"my-store"`` for
    ``my-store.myshopify.com``. The full domain or URL is accepted too.
    ``access_token`` is an Admin API access token (``shpat_...``).
    """
    _base_url.configure(shop)
    _headers.configure(access_token)


def base_url() -> str:
    """The configured store's base URL. Raises if the pack is unconfigured."""
    return _base_url()


_shopify = api_key_tool_factory(
    pack="shopify",
    base_url=_base_url,
    api_key_headers=_headers,
    # GraphQL variables are camelCase: `sort_key` arrives as `sortKey`.
    body_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    envelope=SHOPIFY_ENVELOPE,
)


def _query(name, schema, document, operation, description, action_label, *, paginates=False):
    """Declare one GraphQL query as a tool."""
    return _shopify(
        name=name,
        args_schema=schema,
        method="POST",
        url_template=GRAPHQL_PATH,
        description=description,
        action_label=action_label,
        static_body={"query": document},
        response_handler=unwrap(operation),
        pagination_override=SHOPIFY_PAGINATION if paginates else None,
    )


def _mutation(name, schema, document, operation, description, action_label):
    """Declare one GraphQL mutation, with the userErrors check its payload needs."""
    return _shopify(
        name=name,
        args_schema=schema,
        method="POST",
        url_template=GRAPHQL_PATH,
        description=description,
        action_label=action_label,
        static_body={"query": document},
        response_handler=unwrap_mutation(operation),
    )


# ---------- shop ----------

shop_get = _query(
    "shop_get",
    ShopGetRequest,
    queries.SHOP,
    "shop",
    (
        "Get the store's own details — its name, domain, currency and timezone. "
        "Useful to confirm which store the credentials point at, and to learn the "
        "currency that order totals are quoted in."
    ),
    "Checks the Shopify store.",
)

# ---------- products ----------

products_list = _query(
    "products_list",
    ProductsListRequest,
    queries.PRODUCTS,
    "products",
    (
        "List products. Narrow with a Shopify search string in `query`, e.g. "
        "'status:active vendor:Acme' or 'inventory_total:<5'."
    ),
    "Lists Shopify products.",
    paginates=True,
)

product_get = _query(
    "product_get",
    ProductGetRequest,
    queries.PRODUCT,
    "product",
    (
        "Get one product with its description and its first 50 variants, "
        "including each variant's SKU, price and inventory. Takes a global ID "
        "(`gid://shopify/Product/...`), not a bare number."
    ),
    "Reads a Shopify product.",
)

product_create = _mutation(
    "product_create",
    ProductCreateRequest,
    queries.PRODUCT_CREATE,
    "productCreate",
    (
        "Create a product. Only `title` is required. Note that Shopify creates "
        "products unpublished — a new product is not on the storefront until it "
        "is published to a sales channel, which is a separate operation."
    ),
    "Creates a Shopify product.",
)

product_update = _mutation(
    "product_update",
    ProductUpdateRequest,
    queries.PRODUCT_UPDATE,
    "productUpdate",
    (
        "Update a product. `id` is required; only the other fields provided are "
        "changed. Note that `tags` replaces the product's tags rather than adding "
        "to them."
    ),
    "Updates a Shopify product.",
)

# ---------- orders ----------

orders_list = _query(
    "orders_list",
    OrdersListRequest,
    queries.ORDERS,
    "orders",
    (
        "List orders. Narrow with a Shopify search string in `query`, e.g. "
        "'financial_status:paid fulfillment_status:unshipped' to find orders "
        "waiting to ship. Only the last 60 days of orders are visible unless this "
        "app holds Shopify's `read_all_orders` scope, and older orders are absent "
        "rather than reported — do not read an empty result as an empty history."
    ),
    "Lists Shopify orders.",
    paginates=True,
)

order_get = _query(
    "order_get",
    OrderGetRequest,
    queries.ORDER,
    "order",
    (
        "Get one order with its line items, shipping address and totals. Takes a "
        "global ID (`gid://shopify/Order/...`), which `orders_list` returns."
    ),
    "Reads a Shopify order.",
)

# ---------- customers ----------

customers_list = _query(
    "customers_list",
    CustomersListRequest,
    queries.CUSTOMERS,
    "customers",
    (
        "List customers. Narrow with a Shopify search string in `query`, e.g. "
        "'email:ada@example.com' or 'orders_count:>5'."
    ),
    "Lists Shopify customers.",
    paginates=True,
)

customer_get = _query(
    "customer_get",
    CustomerGetRequest,
    queries.CUSTOMER,
    "customer",
    (
        "Get one customer, with lifetime spend and default address. Takes a "
        "global ID (`gid://shopify/Customer/...`)."
    ),
    "Reads a Shopify customer.",
)

customer_create = _mutation(
    "customer_create",
    CustomerCreateRequest,
    queries.CUSTOMER_CREATE,
    "customerCreate",
    (
        "Create a customer. Shopify needs at least an email address or a phone "
        "number; a customer with neither is rejected."
    ),
    "Creates a Shopify customer.",
)


# ---------- fulfilment ----------

customer_update = _mutation(
    "customer_update",
    CustomerUpdateRequest,
    queries.CUSTOMER_UPDATE,
    "customerUpdate",
    "Update a customer. Give the customer's `id` inside `input` along with the fields to change.",
    "Updates a Shopify customer.",
)

order_fulfillment_orders = _query(
    "order_fulfillment_orders",
    OrderFulfillmentOrdersRequest,
    queries.ORDER_FULFILLMENT_ORDERS,
    "order",
    (
        "List an order's fulfillment orders, which is the first half of fulfilling "
        "it. Shopify creates these itself, and `fulfillment_create` names them. The "
        "location is at `assignedLocation.location.id`."
    ),
    "Reads a Shopify order's fulfillment orders.",
)

fulfillment_create = _mutation(
    "fulfillment_create",
    FulfillmentCreateRequest,
    queries.FULFILLMENT_CREATE,
    "fulfillmentCreate",
    (
        "Fulfil one or more fulfillment orders, marking the goods as shipped. Get "
        "the ids from `order_fulfillment_orders` first. Omit the line items to "
        "fulfil a fulfillment order whole. Every one named must belong to the same "
        "order and the same location, so an order shipping from two places needs "
        "two calls."
    ),
    "Fulfils a Shopify order and can email the customer.",
)

# ---------- inventory ----------

inventory_adjust_quantities = _mutation(
    "inventory_adjust_quantities",
    InventoryAdjustRequest,
    queries.INVENTORY_ADJUST_QUANTITIES,
    "inventoryAdjustQuantities",
    (
        "Move stock by a relative amount: `delta` of 5 adds five, -5 removes five. "
        "This is not a way to set an absolute count. Every change must also carry "
        "`change_from_quantity`, the count you expect to be overwriting — read it "
        "with `variant_inventory_level` immediately before — so two adjustments "
        "racing each other cannot both win. `committed` is never writable, and "
        "`on_hand` cannot be named here although adjusting `available` moves it by "
        "the same delta. The result reports the deltas applied and leaves "
        "`quantity_after_change` null, so read the level back for the new count. "
        "Since 2026-04 adjusting an item that is not stocked at the location "
        "succeeds and creates an inactive level, so a success does not prove the "
        "stock is sellable."
    ),
    "Changes Shopify stock levels.",
)

variant_inventory_level = _query(
    "variant_inventory_level",
    VariantInventoryLevelRequest,
    queries.VARIANT_INVENTORY_LEVEL,
    "productVariant",
    (
        "Read a variant's stock at one location. Returns null where the variant is "
        "not stocked there, which is not an error."
    ),
    "Reads Shopify stock for a variant.",
)

locations_list = _query(
    "locations_list",
    LocationsRequest,
    queries.LOCATIONS,
    "locations",
    "List the store's locations. Inactive ones are excluded unless asked for.",
    "Lists Shopify locations.",
    paginates=True,
)

# ---------- order state ----------

order_close = _mutation(
    "order_close",
    OrderCloseRequest,
    queries.ORDER_CLOSE,
    "orderClose",
    "Close an order, marking it finished. Closing does not cancel or refund anything.",
    "Closes a Shopify order.",
)

order_open = _mutation(
    "order_open",
    OrderOpenRequest,
    queries.ORDER_OPEN,
    "orderOpen",
    "Reopen a closed order.",
    "Reopens a Shopify order.",
)

order_cancel = _mutation(
    "order_cancel",
    OrderCancelRequest,
    queries.ORDER_CANCEL,
    "orderCancel",
    (
        "Cancel an order. `restock` has to be stated: true returns the items to "
        "inventory, false leaves stock as it is. Shopify does this in the "
        "background and answers with a job, so no errors means accepted rather "
        "than finished. Cancelling cannot be undone."
    ),
    "Cancels a Shopify order. This cannot be undone.",
)

# ---------- draft orders ----------

draft_order_create = _mutation(
    "draft_order_create",
    DraftOrderCreateRequest,
    queries.DRAFT_ORDER_CREATE,
    "draftOrderCreate",
    (
        "Create a draft order, the way to build an order by hand before it is "
        "placed. A draft holds no inventory until it is completed."
    ),
    "Creates a Shopify draft order.",
)

draft_order_complete = _mutation(
    "draft_order_complete",
    DraftOrderCompleteRequest,
    queries.DRAFT_ORDER_COMPLETE,
    "draftOrderComplete",
    ("Turn a draft order into a real one. This reserves inventory, so check stock first."),
    "Completes a Shopify draft order into a real order.",
)

# ---------- variants ----------

product_variants_bulk_create = _mutation(
    "product_variants_bulk_create",
    ProductVariantsBulkCreateRequest,
    queries.PRODUCT_VARIANTS_BULK_CREATE,
    "productVariantsBulkCreate",
    (
        "Add variants to a product. The SKU goes inside `inventory_item`, not on "
        "the variant. When the product still carries its default placeholder "
        "variant, pass the strategy that removes it."
    ),
    "Adds variants to a Shopify product.",
)


TOOLS: list[Tool] = [
    shop_get,
    products_list,
    product_get,
    product_create,
    product_update,
    orders_list,
    order_get,
    customers_list,
    customer_get,
    customer_create,
    customer_update,
    order_fulfillment_orders,
    fulfillment_create,
    inventory_adjust_quantities,
    variant_inventory_level,
    locations_list,
    order_close,
    order_open,
    order_cancel,
    draft_order_create,
    draft_order_complete,
    product_variants_bulk_create,
]

__all__ = [
    "TOOLS",
    "configure",
    "base_url",
    "API_VERSION",
    "GRAPHQL_PATH",
    "QUOTA_DOC_URL",
    "SHOPIFY_PAGINATION",
    "SHOPIFY_ENVELOPE",
    "queries",
    "shop_get",
    "products_list",
    "product_get",
    "product_create",
    "product_update",
    "orders_list",
    "order_get",
    "customers_list",
    "customer_get",
    "customer_create",
]
