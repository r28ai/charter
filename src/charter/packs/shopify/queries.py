"""
The GraphQL documents this pack sends.

As in the Linear pack, each document is a constant that belongs to its tool and
reaches the wire through ``static_body``, never through the schema. See
:mod:`charter.packs.linear.queries` for why that boundary matters.

Two things are specific to Shopify:

**Selection sets are billed.** Shopify rate-limits by calculated query cost
rather than request count — each field has a point value, a connection
multiplies by its page size, and the response reports what the query cost
against the remaining budget. Asking for fields nobody reads is not free, so
these selections are deliberately narrow.

**Money is a nested object.** Shopify returns prices as ``MoneyBag`` —
``{"shopMoney": {"amount": "10.00", "currencyCode": "USD"}}`` — because a store
can present a different currency than it settles in. The handlers flatten the
shop-currency side, which is the one an operator means.

API Reference: https://shopify.dev/docs/api/admin-graphql
"""

from __future__ import annotations

__all__ = [
    "SHOP",
    "PRODUCTS",
    "PRODUCT",
    "PRODUCT_CREATE",
    "PRODUCT_UPDATE",
    "ORDERS",
    "ORDER",
    "CUSTOMERS",
    "CUSTOMER",
    "CUSTOMER_CREATE",
]


_PRODUCT_FIELDS = """
    id
    title
    handle
    status
    vendor
    productType
    tags
    totalInventory
    createdAt
    updatedAt
"""

_ORDER_FIELDS = """
    id
    name
    email
    createdAt
    displayFinancialStatus
    displayFulfillmentStatus
    totalPriceSet { shopMoney { amount currencyCode } }
    subtotalPriceSet { shopMoney { amount currencyCode } }
    customer { id displayName defaultEmailAddress { emailAddress } }
"""

_CUSTOMER_FIELDS = """
    id
    displayName
    firstName
    lastName
    defaultEmailAddress { emailAddress }
    defaultPhoneNumber { phoneNumber }
    numberOfOrders
    state
    createdAt
    tags
"""


SHOP = """
query Shop {
  shop {
    id
    name
    myshopifyDomain
    primaryDomain { url }
    email
    currencyCode
    ianaTimezone
    plan { publicDisplayName }
  }
}
"""

PRODUCTS = f"""
query Products($first: Int, $after: String, $query: String, $sortKey: ProductSortKeys, $reverse: Boolean) {{
  products(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {{
    nodes {{{_PRODUCT_FIELDS}}}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

PRODUCT = f"""
query Product($id: ID!) {{
  product(id: $id) {{
    {_PRODUCT_FIELDS}
    descriptionHtml
    variants(first: 50) {{
      nodes {{ id title sku price inventoryQuantity }}
    }}
  }}
}}
"""

PRODUCT_CREATE = f"""
mutation ProductCreate($product: ProductCreateInput!) {{
  productCreate(product: $product) {{
    product {{{_PRODUCT_FIELDS}}}
    userErrors {{ field message }}
  }}
}}
"""

PRODUCT_UPDATE = f"""
mutation ProductUpdate($product: ProductUpdateInput!) {{
  productUpdate(product: $product) {{
    product {{{_PRODUCT_FIELDS}}}
    userErrors {{ field message }}
  }}
}}
"""

ORDERS = f"""
query Orders($first: Int, $after: String, $query: String, $sortKey: OrderSortKeys, $reverse: Boolean) {{
  orders(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {{
    nodes {{{_ORDER_FIELDS}}}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

ORDER = f"""
query Order($id: ID!) {{
  order(id: $id) {{
    {_ORDER_FIELDS}
    note
    shippingAddress {{ address1 city province country zip }}
    lineItems(first: 50) {{
      nodes {{
        id
        title
        quantity
        sku
        originalTotalSet {{ shopMoney {{ amount currencyCode }} }}
      }}
    }}
  }}
}}
"""

CUSTOMERS = f"""
query Customers($first: Int, $after: String, $query: String, $sortKey: CustomerSortKeys, $reverse: Boolean) {{
  customers(first: $first, after: $after, query: $query, sortKey: $sortKey, reverse: $reverse) {{
    nodes {{{_CUSTOMER_FIELDS}}}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

CUSTOMER = f"""
query Customer($id: ID!) {{
  customer(id: $id) {{
    {_CUSTOMER_FIELDS}
    amountSpent {{ amount currencyCode }}
    defaultAddress {{ address1 city province country zip }}
  }}
}}
"""

CUSTOMER_CREATE = f"""
mutation CustomerCreate($input: CustomerInput!) {{
  customerCreate(input: $input) {{
    customer {{{_CUSTOMER_FIELDS}}}
    userErrors {{ field message }}
  }}
}}
"""


# ---------- customers ----------

CUSTOMER_UPDATE = f"""
mutation CustomerUpdate($input: CustomerInput!) {{
  customerUpdate(input: $input) {{
    customer {{{_CUSTOMER_FIELDS}}}
    userErrors {{ field message }}
  }}
}}
"""

# ---------- fulfilment ----------

# Fulfillment orders are created by Shopify when the order is placed and cannot be
# made by a caller, so fulfilling anything starts here: an order id resolves to the
# fulfillment orders that a fulfillment can name. The location lives two levels
# down, because `assignedLocation` is an address snapshot rather than a Location.
ORDER_FULFILLMENT_ORDERS = """
query OrderFulfillmentOrders($id: ID!, $first: Int!) {
  order(id: $id) {
    id
    name
    fulfillmentOrders(first: $first) {
      nodes {
        id
        status
        requestStatus
        assignedLocation { name location { id } }
        lineItems(first: 50) { nodes { id remainingQuantity } }
      }
    }
  }
}
"""

FULFILLMENT_CREATE = """
mutation FulfillmentCreate($fulfillment: FulfillmentInput!, $message: String) {
  fulfillmentCreate(fulfillment: $fulfillment, message: $message) {
    fulfillment {
      id
      status
      createdAt
      totalQuantity
      trackingInfo { number url company }
    }
    userErrors { field message }
  }
}
"""

# ---------- inventory ----------

# `@idempotent` has been required since the 2026-04 version, and its key is a
# variable rather than a literal because a key is a fact about one call.
#
# What it does *not* do, measured against the API rather than assumed from the
# name: re-sending a key does not replay the first response. An identical second
# request is executed again, and refused — by `changeFromQuantity`, which no
# longer matches what is persisted. So the thing that makes a retry safe here is
# the compare-and-set, not the key. `tests/live/test_live_shopify.py` pins both
# halves; nothing offline can, since a mock replays whatever it is told to.
INVENTORY_ADJUST_QUANTITIES = """
mutation InventoryAdjustQuantities(
  $input: InventoryAdjustQuantitiesInput!
  $idempotencyKey: String!
) {
  inventoryAdjustQuantities(input: $input) @idempotent(key: $idempotencyKey) {
    inventoryAdjustmentGroup {
      id
      reason
      changes { name delta quantityAfterChange }
    }
    userErrors { field message }
  }
}
"""

VARIANT_INVENTORY_LEVEL = """
query VariantInventoryLevel($id: ID!, $locationId: ID!, $names: [String!]!) {
  productVariant(id: $id) {
    id
    title
    inventoryItem {
      id
      inventoryLevel(locationId: $locationId) {
        id
        location { id name }
        quantities(names: $names) { name quantity }
      }
    }
  }
}
"""

LOCATIONS = """
query Locations($first: Int!, $after: String, $query: String, $includeInactive: Boolean, $reverse: Boolean) {
  locations(first: $first, after: $after, query: $query, includeInactive: $includeInactive, reverse: $reverse) {
    nodes { id name isActive address { formatted } }
    pageInfo { hasNextPage endCursor }
  }
}
"""

# ---------- order state ----------

ORDER_CLOSE = """
mutation OrderClose($input: OrderCloseInput!) {
  orderClose(input: $input) {
    order { id name closed closedAt displayFulfillmentStatus }
    userErrors { field message }
  }
}
"""

ORDER_OPEN = """
mutation OrderOpen($input: OrderOpenInput!) {
  orderOpen(input: $input) {
    order { id name closed displayFulfillmentStatus }
    userErrors { field message }
  }
}
"""

# The one mutation in this pack whose errors are not at `userErrors`, and the one
# that answers with a job rather than the thing it changed.
ORDER_CANCEL = """
mutation OrderCancel(
  $orderId: ID!
  $reason: OrderCancelReason!
  $restock: Boolean!
  $notifyCustomer: Boolean
  $staffNote: String
) {
  orderCancel(
    orderId: $orderId
    reason: $reason
    restock: $restock
    notifyCustomer: $notifyCustomer
    staffNote: $staffNote
  ) {
    job { id done }
    orderCancelUserErrors { field message code }
  }
}
"""

# ---------- draft orders ----------

DRAFT_ORDER_CREATE = """
mutation DraftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder {
      id
      name
      status
      invoiceUrl
      totalPriceSet { shopMoney { amount currencyCode } }
    }
    userErrors { field message }
  }
}
"""

DRAFT_ORDER_COMPLETE = """
mutation DraftOrderComplete($id: ID!, $paymentGatewayId: ID, $sourceName: String) {
  draftOrderComplete(id: $id, paymentGatewayId: $paymentGatewayId, sourceName: $sourceName) {
    draftOrder { id name status order { id name } }
    userErrors { field message }
  }
}
"""

# ---------- variants ----------

PRODUCT_VARIANTS_BULK_CREATE = """
mutation ProductVariantsBulkCreate(
  $productId: ID!
  $variants: [ProductVariantsBulkInput!]!
  $strategy: ProductVariantsBulkCreateStrategy
) {
  productVariantsBulkCreate(
    productId: $productId
    variants: $variants
    strategy: $strategy
  ) {
    productVariants {
      id
      title
      price
      inventoryItem { id sku }
      selectedOptions { name value }
    }
    userErrors { field message }
  }
}
"""
