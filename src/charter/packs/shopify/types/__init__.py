# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for the Shopify pack.

Every schema here has a single ``variables`` field marked ``Body(envelop=True)``,
for the reason set out in :mod:`charter.packs.linear.types`: a GraphQL request is a
document plus its variables, and only the variables are the model's business.

Two Shopify-specific notes:

**IDs are GIDs.** Shopify identifies everything by a global ID of the form
``gid://shopify/Product/1234567890``, not a bare number. Every ``id`` field here
says so, because a model that passes ``1234567890`` gets an error that does not
explain itself.

**Filtering is a query string, not a filter object.** Where Linear takes a typed
``IssueFilter``, Shopify takes a search string in its own syntax —
``"status:active vendor:Acme"``. It cannot be typed, so it is documented
instead, with the supported qualifiers listed per resource.

API Reference: https://shopify.dev/docs/api/admin-graphql
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Gloss

__all__ = [
    "ShopGetRequest",
    "ProductsListRequest",
    "ProductGetRequest",
    "ProductCreateRequest",
    "ProductUpdateRequest",
    "OrdersListRequest",
    "OrderGetRequest",
    "CustomersListRequest",
    "CustomerGetRequest",
    "CustomerCreateRequest",
    "CustomerUpdateRequest",
    "OrderFulfillmentOrdersRequest",
    "FulfillmentCreateRequest",
    "InventoryAdjustRequest",
    "VariantInventoryLevelRequest",
    "LocationsRequest",
    "OrderCloseRequest",
    "OrderOpenRequest",
    "OrderCancelRequest",
    "DraftOrderCreateRequest",
    "DraftOrderCompleteRequest",
    "ProductVariantsBulkCreateRequest",
    "FulfillmentInput",
    "InventoryAdjustInput",
    "InventoryChange",
    "InventoryStateName",
    "InventoryAdjustReason",
    "OrderCancelReason",
    "ProductVariantBulkInput",
]


ProductStatus = Literal["ACTIVE", "ARCHIVED", "DRAFT"]

# The full enums, not a convenient subset: a closed Literal that omits a value
# the API accepts rejects a valid call, and the model has no way to know the
# difference between "Shopify will not sort by this" and "this pack left it out".
# `RELEVANCE` is only meaningful alongside a `query`.
ProductSortKeys = Literal[
    "CREATED_AT",
    "ID",
    "INVENTORY_TOTAL",
    "PRODUCT_TYPE",
    "PUBLISHED_AT",
    "RELEVANCE",
    "TITLE",
    "UPDATED_AT",
    "VENDOR",
]
OrderSortKeys = Literal[
    "CREATED_AT",
    "CURRENT_TOTAL_PRICE",
    "CUSTOMER_NAME",
    "DESTINATION",
    "FINANCIAL_STATUS",
    "FULFILLMENT_STATUS",
    "ID",
    "ORDER_NUMBER",
    "PO_NUMBER",
    "PROCESSED_AT",
    "RELEVANCE",
    "TOTAL_ITEMS_QUANTITY",
    "TOTAL_PRICE",
    "UPDATED_AT",
]
CustomerSortKeys = Literal["CREATED_AT", "ID", "LOCATION", "NAME", "RELEVANCE", "UPDATED_AT"]

_GID = "A Shopify global ID, of the form `gid://shopify/{kind}/1234567890`."


class ConnectionVariables(BaseModel):
    """The arguments every Shopify connection accepts.

    API Reference: https://shopify.dev/docs/api/usage/pagination-graphql
    """

    first: Optional[int] = Field(
        default=50,
        ge=1,
        le=250,
        description=(
            "How many results to return, at most 250. Larger pages cost more "
            "against the store's query-cost budget."
        ),
    )
    after: Optional[str] = Field(
        default=None,
        description="The `endCursor` from the previous page's `pageInfo`.",
    )
    reverse: Optional[bool] = Field(
        default=None, description="Reverse the sort order. Defaults to false."
    )


# -----------------------------------------------------
# shop
# -----------------------------------------------------


class ShopGetVariables(BaseModel):
    """``shop`` takes no arguments."""


class ShopGetRequest(BaseModel):
    """Get the store's own details."""

    variables: Annotated[
        Optional[ShopGetVariables],
        Field(None, description="This query takes no variables."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# products
# -----------------------------------------------------


class ProductsListVariables(ConnectionVariables):
    """Variables for the ``products`` connection."""

    query: Optional[str] = Field(
        default=None,
        description=(
            "A Shopify search string. Supported qualifiers include `title:`, "
            "`vendor:`, `product_type:`, `tag:`, `status:` (active/archived/draft), "
            "`created_at:`, `updated_at:` and `inventory_total:`. Terms combine "
            "with AND; use OR explicitly. Example: `status:active vendor:Acme`. "
            "A record created moments ago may not appear here yet; search is eventually consistent, so confirm a write with the id it returned. "
            "Use only the qualifiers listed: Shopify ignores one it does not recognise instead of rejecting it, so a typo like `vendorr:` returns the whole unfiltered set rather than an error. "
        ),
    )
    sort_key: Optional[ProductSortKeys] = Field(
        default=None, description="Which field to sort by. Shopify sorts by ID by default."
    )


class ProductsListRequest(BaseModel):
    """List products."""

    variables: Annotated[
        ProductsListVariables,
        Field(default_factory=ProductsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class ProductGetVariables(BaseModel):
    """Variables for the ``product`` query."""

    id: str = Field(..., description=_GID.format(kind="Product"))


class ProductGetRequest(BaseModel):
    """Get one product, with its variants."""

    variables: Annotated[
        ProductGetVariables,
        Field(..., description="Which product to fetch."),
        Body(envelop=True),
    ]


class ProductCreateInput(BaseModel):
    """The input to ``productCreate``.

    Note that Shopify creates products unpublished: a new product is not visible
    on the storefront until it is published to a sales channel, which is a
    separate mutation this pack does not model.

    API Reference: https://shopify.dev/docs/api/admin-graphql/latest/mutations/productCreate
    """

    title: str = Field(..., description="The product's title. Required.")
    description_html: Optional[str] = Field(None, description="The product description, as HTML.")
    vendor: Optional[str] = Field(None, description="The product's vendor name.")
    product_type: Optional[str] = Field(
        None, description="A custom product type, used for filtering and reporting."
    )
    tags: Optional[List[str]] = Field(None, description="Tags to attach to the product.")
    status: Optional[ProductStatus] = Field(
        None,
        description=(
            "The product's status. Defaults to ACTIVE. DRAFT keeps it out of the storefront."
        ),
    )
    handle: Optional[str] = Field(
        None,
        description=("The URL slug for the product. Derived from the title when omitted."),
    )


class ProductCreateVariables(BaseModel):
    """Variables for the ``productCreate`` mutation.

    The argument is named ``product``, not ``input`` — Shopify renamed it, and
    the ``input`` form is deprecated.
    """

    product: ProductCreateInput = Field(..., description="The product to create.")


class ProductCreateRequest(BaseModel):
    """Create a product."""

    variables: Annotated[
        ProductCreateVariables,
        Field(..., description="The product to create."),
        Body(envelop=True),
    ]


class ProductUpdateInput(BaseModel):
    """The input to ``productUpdate``. Only ``id`` is required.

    API Reference: https://shopify.dev/docs/api/admin-graphql/latest/mutations/productUpdate
    """

    id: str = Field(..., description=_GID.format(kind="Product"))
    title: Optional[str] = Field(None, description="A new title.")
    description_html: Optional[str] = Field(None, description="A new description, as HTML.")
    vendor: Optional[str] = Field(None, description="A new vendor name.")
    product_type: Optional[str] = Field(None, description="A new product type.")
    tags: Optional[List[str]] = Field(
        None,
        description="Tags. This *replaces* the product's tags rather than adding to them.",
    )
    status: Optional[ProductStatus] = Field(None, description="A new status.")
    handle: Optional[str] = Field(None, description="A new URL slug.")

    @model_validator(mode="after")
    def _at_least_one_change(self) -> ProductUpdateInput:
        changes = self.model_dump(exclude_none=True)
        changes.pop("id", None)
        if not changes:
            raise ValueError(
                "productUpdate needs at least one field to change besides `id`; an "
                "id on its own would send a mutation that does nothing."
            )
        return self


class ProductUpdateVariables(BaseModel):
    """Variables for the ``productUpdate`` mutation."""

    product: ProductUpdateInput = Field(..., description="The product changes.")


class ProductUpdateRequest(BaseModel):
    """Update a product."""

    variables: Annotated[
        ProductUpdateVariables,
        Field(..., description="The product changes."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# orders
# -----------------------------------------------------


class OrdersListVariables(ConnectionVariables):
    """Variables for the ``orders`` connection.

    Shopify serves only the last 60 days of orders unless the app holds the
    approval-gated ``read_all_orders`` scope. Older orders are not an error,
    they are simply absent.

    API Reference: https://shopify.dev/docs/api/admin-graphql/latest/queries/orders
    """

    query: Optional[str] = Field(
        default=None,
        description=(
            "A Shopify search string. Supported qualifiers include "
            "`financial_status:` (paid/pending/refunded/voided), "
            "`fulfillment_status:` (shipped/unshipped/partial), `created_at:`, "
            "`updated_at:`, `email:`, `name:` and `tag:`. Example: "
            "`financial_status:paid fulfillment_status:unshipped`. "
            "Use only the qualifiers listed: Shopify ignores one it does not recognise instead of rejecting it, so a typo like `vendorr:` returns the whole unfiltered set rather than an error. "
            "Note that a `created_at:` window reaching further back than 60 days "
            "returns nothing unless the app holds the `read_all_orders` scope."
        ),
    )
    sort_key: Optional[OrderSortKeys] = Field(
        default=None,
        description="Which field to sort by. Shopify sorts by PROCESSED_AT by default.",
    )


class OrdersListRequest(BaseModel):
    """List orders."""

    variables: Annotated[
        OrdersListVariables,
        Field(default_factory=OrdersListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class OrderGetVariables(BaseModel):
    """Variables for the ``order`` query."""

    id: str = Field(..., description=_GID.format(kind="Order"))


class OrderGetRequest(BaseModel):
    """Get one order, with its line items and shipping address."""

    variables: Annotated[
        OrderGetVariables,
        Field(..., description="Which order to fetch."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# customers
# -----------------------------------------------------


class CustomersListVariables(ConnectionVariables):
    """Variables for the ``customers`` connection."""

    query: Optional[str] = Field(
        default=None,
        description=(
            "A Shopify search string. Supported qualifiers include `email:`, "
            "`first_name:`, `last_name:`, `phone:`, `tag:`, `orders_count:` and "
            "`total_spent:`. Example: `orders_count:>5`. "
            "A record created moments ago may not appear here yet; search is eventually consistent, so confirm a write with the id it returned. "
            "Use only the qualifiers listed: Shopify ignores one it does not recognise instead of rejecting it, so a typo like `vendorr:` returns the whole unfiltered set rather than an error. "
        ),
    )
    sort_key: Optional[CustomerSortKeys] = Field(
        default=None, description="Which field to sort by."
    )


class CustomersListRequest(BaseModel):
    """List customers."""

    variables: Annotated[
        CustomersListVariables,
        Field(default_factory=CustomersListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class CustomerGetVariables(BaseModel):
    """Variables for the ``customer`` query."""

    id: str = Field(..., description=_GID.format(kind="Customer"))


class CustomerGetRequest(BaseModel):
    """Get one customer, with lifetime spend and default address."""

    variables: Annotated[
        CustomerGetVariables,
        Field(..., description="Which customer to fetch."),
        Body(envelop=True),
    ]


class CustomerInput(BaseModel):
    """The input to ``customerCreate``.

    API Reference: https://shopify.dev/docs/api/admin-graphql/latest/mutations/customerCreate
    """

    email: Optional[str] = Field(
        None,
        description=(
            "The customer's email address. Either this or `phone` is needed for "
            "Shopify to accept the customer."
        ),
    )
    phone: Optional[str] = Field(None, description="The customer's phone number, in E.164 format.")
    first_name: Optional[str] = Field(None, description="The customer's first name.")
    last_name: Optional[str] = Field(None, description="The customer's last name.")
    note: Optional[str] = Field(None, description="A note about the customer.")
    tags: Optional[List[str]] = Field(None, description="Tags to attach to the customer.")

    @model_validator(mode="after")
    def _needs_a_contact(self) -> CustomerInput:
        if self.email is None and self.phone is None:
            raise ValueError(
                "A customer needs at least an email address or a phone number; "
                "Shopify rejects one with neither."
            )
        return self


class CustomerCreateVariables(BaseModel):
    """Variables for the ``customerCreate`` mutation."""

    input: CustomerInput = Field(..., description="The customer to create.")


class CustomerCreateRequest(BaseModel):
    """Create a customer."""

    variables: Annotated[
        CustomerCreateVariables,
        Field(..., description="The customer to create."),
        Body(envelop=True),
    ]


# -----------------------------------------------------
# Round two: fulfilment, inventory, order state, drafts
# -----------------------------------------------------


class CustomerUpdateInput(BaseModel):
    """The input to ``customerUpdate``.

    Not :class:`CustomerInput`, for two reasons that both made the update tool
    unusable. It has no ``id``, so the mutation could not say *which* customer to
    change and the schema rejected one as an extra field; and its validator
    insists on an email address or a phone number, which is right for a customer
    being created and wrong for one being edited — changing a note would have had
    to restate the contact details.

    API Reference: https://shopify.dev/docs/api/admin-graphql/latest/mutations/customerUpdate
    """

    id: str = Field(..., description="The customer's global ID, `gid://shopify/Customer/...`.")
    email: Optional[str] = Field(None, description="The customer's email address.")
    phone: Optional[str] = Field(None, description="The customer's phone number, in E.164 format.")
    first_name: Optional[str] = Field(None, description="The customer's first name.")
    last_name: Optional[str] = Field(None, description="The customer's last name.")
    note: Optional[str] = Field(None, description="A note about the customer.")
    tags: Optional[List[str]] = Field(
        None,
        description=(
            "Tags for the customer. This replaces the existing tags rather than adding to them."
        ),
    )


class CustomerUpdateVariables(BaseModel):
    """Variables for the ``customerUpdate`` mutation."""

    input: CustomerUpdateInput = Field(
        ..., description="The customer's `id` plus the fields to change."
    )


class CustomerUpdateRequest(BaseModel):
    """Update a customer."""

    variables: Annotated[
        CustomerUpdateVariables,
        Field(..., description="The customer to update."),
        Body(envelop=True),
    ]


class OrderFulfillmentOrdersVariables(BaseModel):
    """Variables for reading an order's fulfillment orders."""

    id: str = Field(..., description="The order's global ID, `gid://shopify/Order/...`.")
    first: int = Field(10, ge=1, le=50, description="How many fulfillment orders to read.")


class OrderFulfillmentOrdersRequest(BaseModel):
    """Resolve an order into the fulfillment orders a fulfillment can name."""

    variables: Annotated[
        OrderFulfillmentOrdersVariables,
        Field(..., description="The order to resolve."),
        Body(envelop=True),
    ]


class FulfillmentOrderLineItem(BaseModel):
    """One line of a fulfillment order, when fulfilling it only in part."""

    id: str = Field(
        ..., description="The line's global ID, `gid://shopify/FulfillmentOrderLineItem/...`."
    )
    quantity: int = Field(..., ge=1, description="How many units to fulfil.")


class FulfillmentOrderLineItems(BaseModel):
    """One fulfillment order, whole or in part.

    Omit `fulfillment_order_line_items` and Shopify fulfils the whole fulfillment
    order, which is what most callers mean.
    """

    fulfillment_order_id: str = Field(
        ..., description="The fulfillment order's global ID, from the resolve step."
    )
    fulfillment_order_line_items: Optional[List[FulfillmentOrderLineItem]] = Field(
        None,
        description="Specific lines to fulfil. Absent, the whole fulfillment order.",
    )


class FulfillmentTracking(BaseModel):
    """Where the customer can follow the parcel."""

    company: Optional[str] = Field(None, description="The carrier's name.")
    number: Optional[str] = Field(None, description="The tracking number.")
    url: Optional[str] = Field(None, description="A tracking URL.")


class FulfillmentInput(BaseModel):
    """What to fulfil, and whether to tell the customer.

    Every fulfillment order named here must belong to the same order and be
    assigned to the same location. An order split across locations needs one call
    per location.
    """

    line_items_by_fulfillment_order: List[FulfillmentOrderLineItems] = Field(
        ..., min_length=1, description="The fulfillment orders being fulfilled."
    )
    notify_customer: Optional[bool] = Field(
        None, description="Email the customer. Absent, Shopify does not."
    )
    tracking_info: Optional[FulfillmentTracking] = Field(
        None, description="Carrier and tracking number."
    )


class FulfillmentCreateVariables(BaseModel):
    """Variables for the ``fulfillmentCreate`` mutation."""

    fulfillment: FulfillmentInput = Field(..., description="What to fulfil.")
    message: Optional[str] = Field(None, description="A message recorded against the fulfillment.")


class FulfillmentCreateRequest(BaseModel):
    """Fulfil one or more fulfillment orders."""

    variables: Annotated[
        FulfillmentCreateVariables,
        Field(..., description="The fulfilment to create."),
        Body(envelop=True),
    ]


InventoryStateName = Literal["available", "damaged", "quality_control", "reserved", "safety_stock"]

InventoryAdjustReason = Literal[
    "correction",
    "cycle_count_available",
    "damaged",
    "movement_created",
    "movement_updated",
    "movement_received",
    "movement_canceled",
    "other",
    "promotion",
    "quality_control",
    "received",
    "reservation_created",
    "reservation_deleted",
    "reservation_updated",
    "restock",
    "safety_stock",
    "shrinkage",
]


class InventoryChange(BaseModel):
    """One stock movement, relative to what is there now.

    ``change_from_quantity`` makes this a compare-and-set rather than a blind
    increment: Shopify applies the delta only if the count is still what the
    caller last saw. It has been required since the 2026-07 version — a change
    without it is rejected at the GraphQL layer, not at the business layer, so
    the mutation never ran at all — and it is what makes concurrent adjustments
    safe rather than last-writer-wins.

    API Reference:
    https://shopify.dev/docs/api/admin-graphql/latest/mutations/inventoryAdjustQuantities
    """

    delta: int = Field(..., description="How much to add or remove. Negative reduces the count.")
    inventory_item_id: str = Field(
        ..., description="The item's global ID, `gid://shopify/InventoryItem/...`."
    )
    location_id: str = Field(
        ..., description="The location's global ID, `gid://shopify/Location/...`."
    )
    change_from_quantity: int = Field(
        ...,
        description=(
            "The quantity you expect to be there now, from "
            "`variant_inventory_level`. Shopify refuses the change if the count "
            "has moved since, so read it immediately before adjusting."
        ),
    )
    ledger_document_uri: Optional[str] = Field(
        None,
        description=(
            "A URI recording why the stock moved. Shopify requires one for every "
            "state except `available`, and it must not be a gid."
        ),
    )


class InventoryAdjustInput(BaseModel):
    """A relative stock adjustment.

    This moves stock by a delta. Setting an absolute count is a different Shopify
    mutation, which this pack does not carry.

    `on_hand` cannot be adjusted here, and `committed` is never writable: Shopify
    derives it from orders.
    """

    name: InventoryStateName = Field(..., description="Which stock state to move.")
    reason: InventoryAdjustReason = Field(
        ..., description="Why the stock moved. `correction` is the general case."
    )
    changes: List[InventoryChange] = Field(..., min_length=1, description="The movements to apply.")
    reference_document_uri: Optional[str] = Field(
        None, description="A URI for the document this adjustment came from."
    )


class InventoryAdjustVariables(BaseModel):
    """Variables for ``inventoryAdjustQuantities``, including its idempotency key."""

    input: InventoryAdjustInput = Field(..., description="The adjustment to apply.")
    idempotency_key: str = Field(
        default_factory=lambda: str(uuid4()),
        description=(
            "Deduplicates this adjustment for 24 hours. A fresh one is generated "
            "per call; pass your own to make a retry safe to repeat."
        ),
    )


class InventoryAdjustRequest(BaseModel):
    """Move stock by a delta."""

    variables: Annotated[
        InventoryAdjustVariables,
        Field(..., description="The adjustment to apply."),
        Body(envelop=True),
    ]


class VariantInventoryLevelVariables(BaseModel):
    """Variables for reading one variant's stock at one location."""

    id: str = Field(..., description="The variant's global ID, `gid://shopify/ProductVariant/...`.")
    location_id: str = Field(
        ..., description="The location's global ID, `gid://shopify/Location/...`."
    )
    names: List[str] = Field(
        default_factory=lambda: ["available", "on_hand"],
        min_length=1,
        description=(
            "Which stock states to read: available, committed, incoming, on_hand, "
            "reserved, damaged, safety_stock, quality_control."
        ),
    )


class VariantInventoryLevelRequest(BaseModel):
    """Read a variant's stock at one location."""

    variables: Annotated[
        VariantInventoryLevelVariables,
        Field(..., description="The variant and location to read."),
        Body(envelop=True),
    ]


class LocationsVariables(ConnectionVariables):
    """Variables for the ``locations`` connection."""

    query: Optional[str] = Field(default=None, description="A Shopify search string.")
    include_inactive: Optional[bool] = Field(
        default=None,
        description="Include deactivated locations. Absent, only active ones.",
    )


class LocationsRequest(BaseModel):
    """List the store's locations."""

    variables: Annotated[
        LocationsVariables,
        Field(default_factory=LocationsVariables, description="Paging and filters."),
        Body(envelop=True),
    ]


class OrderIdInput(BaseModel):
    """The single-field input `orderClose` and `orderOpen` share."""

    id: str = Field(..., description="The order's global ID, `gid://shopify/Order/...`.")


class OrderStateVariables(BaseModel):
    """Variables for ``orderClose`` and ``orderOpen``."""

    input: OrderIdInput = Field(..., description="The order to change.")


class OrderCloseRequest(BaseModel):
    """Close an order, marking it done."""

    variables: Annotated[
        OrderStateVariables,
        Field(..., description="The order to close."),
        Body(envelop=True),
    ]


class OrderOpenRequest(BaseModel):
    """Reopen a closed order."""

    variables: Annotated[
        OrderStateVariables,
        Field(..., description="The order to reopen."),
        Body(envelop=True),
    ]


OrderCancelReason = Literal["CUSTOMER", "DECLINED", "FRAUD", "INVENTORY", "OTHER", "STAFF"]


class OrderCancelVariables(BaseModel):
    """Variables for ``orderCancel``.

    `restock` is not optional in Shopify's schema, so cancelling always states
    what happens to the stock rather than leaving it to a default.
    """

    order_id: str = Field(..., description="The order's global ID.")
    reason: OrderCancelReason = Field(..., description="Why the order is being cancelled.")
    restock: bool = Field(..., description="Whether to return the items to inventory.")
    notify_customer: Optional[bool] = Field(
        None, description="Email the customer. Absent, Shopify does not."
    )
    staff_note: Optional[str] = Field(
        None, max_length=255, description="An internal note on the cancellation."
    )


class OrderCancelRequest(BaseModel):
    """Cancel an order."""

    variables: Annotated[
        OrderCancelVariables,
        Field(..., description="The order to cancel."),
        Body(envelop=True),
    ]


class DraftOrderCreateVariables(BaseModel):
    """Variables for ``draftOrderCreate``."""

    input: Dict[str, Any] = Field(
        ...,
        description=(
            "The draft order. Useful keys: `lineItems` (each with `variantId` and "
            "`quantity`, or `title` and `originalUnitPrice` for a custom line), "
            "`customerId`, `email`, `note`, `tags`, `shippingAddress`."
        ),
    )


class DraftOrderCreateRequest(BaseModel):
    """Create a draft order."""

    variables: Annotated[
        DraftOrderCreateVariables,
        Field(..., description="The draft order to create."),
        Body(envelop=True),
    ]


class DraftOrderCompleteVariables(BaseModel):
    """Variables for ``draftOrderComplete``."""

    id: str = Field(..., description="The draft order's global ID.")
    payment_gateway_id: Optional[str] = Field(
        None, description="The gateway to charge through, when taking payment now."
    )
    source_name: Optional[str] = Field(None, description="Where the resulting order came from.")


class DraftOrderCompleteRequest(BaseModel):
    """Turn a draft order into a real one."""

    variables: Annotated[
        DraftOrderCompleteVariables,
        Field(..., description="The draft order to complete."),
        Body(envelop=True),
    ]


class VariantOptionValue(BaseModel):
    """One option value that distinguishes a variant, such as Size / Large."""

    name: str = Field(..., description="The value, such as 'Large'.")
    option_name: str = Field(..., description="The option it belongs to, such as 'Size'.")


class VariantInventoryItem(BaseModel):
    """The variant fields Shopify moved onto the inventory item.

    `sku` lives here rather than on the variant, which is the most common thing to
    get wrong when porting from older Shopify code.
    """

    sku: Optional[str] = Field(None, description="The variant's SKU.")
    tracked: Optional[bool] = Field(
        None, description="Whether Shopify tracks stock for this variant."
    )


class ProductVariantBulkInput(BaseModel):
    """One variant to add to a product."""

    option_values: List[VariantOptionValue] = Field(
        ..., min_length=1, description="What distinguishes this variant."
    )
    price: Annotated[
        Optional[str],
        Field(None, description="The price, as a decimal string."),
        Gloss(
            'Dollars as written, not a count of cents: "15.00" is fifteen dollars '
            'and "1500" is fifteen hundred.'
        ),
    ] = None
    compare_at_price: Annotated[
        Optional[str],
        Field(None, description="The struck-through price, as a decimal string."),
        Gloss(
            'Dollars as written, not a count of cents: "15.00" is fifteen dollars '
            'and "1500" is fifteen hundred.'
        ),
    ] = None
    barcode: Optional[str] = Field(None, description="The variant's barcode.")
    taxable: Optional[bool] = Field(None, description="Whether tax applies.")
    inventory_item: Optional[VariantInventoryItem] = Field(
        None, description="SKU and stock tracking."
    )


ProductVariantsBulkCreateStrategy = Literal["DEFAULT", "REMOVE_STANDALONE_VARIANT"]


class ProductVariantsBulkCreateVariables(BaseModel):
    """Variables for ``productVariantsBulkCreate``."""

    product_id: str = Field(
        ..., description="The product's global ID, `gid://shopify/Product/...`."
    )
    variants: List[ProductVariantBulkInput] = Field(
        ..., min_length=1, description="The variants to add."
    )
    strategy: Optional[ProductVariantsBulkCreateStrategy] = Field(
        None,
        description=(
            "Use 'REMOVE_STANDALONE_VARIANT' when adding the first real variant to a "
            "product that still carries its default placeholder."
        ),
    )


class ProductVariantsBulkCreateRequest(BaseModel):
    """Add variants to a product."""

    variables: Annotated[
        ProductVariantsBulkCreateVariables,
        Field(..., description="The variants to add."),
        Body(envelop=True),
    ]
