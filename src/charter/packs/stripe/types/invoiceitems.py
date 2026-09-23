# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Invoice items: what an invoice is actually made of.

An invoice created through this pack starts empty. These are what put a line on it,
and without them the eight invoice tools can only bill what a subscription already
produced.

Two things the reference is explicit about and one it is not.

`price` is no longer a parameter. It moved under `pricing`, so a line naming an
existing price sends `pricing[price]`. `price_data` did not move, which makes the
pair look inconsistent and is why both are spelled out here.

An item created without `invoice` floats: it attaches to the customer's next
subscription invoice, but a standalone invoice does **not** pick it up unless that
invoice was created with `pending_invoice_items_behavior="include"`. Creating an
invoice and then creating items for it, in that order, is the reliable sequence.

What the reference never states is whether `amount`, `pricing` and `price_data` are
a required one-of. There is no `oneOf` in the schema and no prose saying so, so
nothing here enforces it.

API Reference: https://docs.stripe.com/api/invoiceitems
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.stripe.types.common import StripeListRequest
from charter.packs.stripe.types.invoices import _InvoiceTaxBehavior
from charter.packs.stripe.types.payments import CreatedFilter
from charter.packs.stripe.types.subscriptions import SubscriptionDiscount
from charter.types import Body, Gloss, Path, Query

__all__ = [
    "InvoiceItemPeriod",
    "InvoiceItemPricing",
    "InvoiceItemPriceData",
    "InvoiceItemsCreateRequest",
    "InvoiceItemsListRequest",
    "InvoiceItemsUpdateRequest",
    "InvoiceItemsDeleteRequest",
]


class InvoiceItemPeriod(BaseModel):
    """The service period a line covers. Both ends are inclusive and required."""

    start: Annotated[
        int,
        Field(..., description="Unix timestamp the period starts, inclusive."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ]
    end: Annotated[
        int,
        Field(..., description="Unix timestamp the period ends, inclusive."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ]

    @model_validator(mode="after")
    def _end_after_start(self) -> InvoiceItemPeriod:
        if self.end < self.start:
            raise ValueError("`period.end` cannot be before `period.start`.")
        return self


class InvoiceItemPricing(BaseModel):
    """Where an existing price is named.

    Stripe moved `price` under here; a top-level `price` is not a parameter.
    """

    price: Optional[str] = Field(None, description="The ID of an existing price to bill.")


class InvoiceItemPriceData(BaseModel):
    """A price created inline for this line only.

    Unlike a subscription's inline price this takes a product ID; there is no
    inline product here.
    """

    currency: str = Field(..., description="Three-letter lowercase ISO currency code.")
    product: str = Field(..., description="The ID of the product being billed.")
    unit_amount: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The amount in the smallest currency unit. Mutually exclusive with "
                "unit_amount_decimal."
            ),
        ),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 prices this at fifteen "
            "cents. Multiply a decimal amount by 100."
        ),
    ] = None
    unit_amount_decimal: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Same as `unit_amount`, but accepts a decimal value in the smallest "
                "currency unit with at most 12 decimal places. Only one of "
                "`unit_amount` and `unit_amount_decimal` can be set."
            ),
        ),
        Gloss(
            'Cents, not dollars: $15.00 is "1500". The decimal places are '
            'fractions of a cent, so "1500.5" is fifteen dollars and half a cent.'
        ),
    ] = None
    tax_behavior: Optional[_InvoiceTaxBehavior] = Field(
        None, description="Whether the amount includes tax."
    )

    @model_validator(mode="after")
    def _one_amount(self) -> InvoiceItemPriceData:
        if self.unit_amount is not None and self.unit_amount_decimal is not None:
            raise ValueError(
                "Set `unit_amount` or `unit_amount_decimal`, not both — Stripe "
                "accepts only one of them."
            )
        return self


class _InvoiceItemFields(BaseModel):
    """What create and update both accept."""

    amount: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The amount in the smallest currency unit. Negative reduces what the "
                "invoice is due."
            ),
        ),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 puts fifteen cents on the "
            "invoice. Multiply a decimal amount by 100."
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="What this line says on the invoice."),
        Body(),
    ]
    quantity: Annotated[
        Optional[int],
        Field(None, ge=0, description="How many units this line bills."),
        Body(),
    ]
    pricing: Annotated[
        Optional[InvoiceItemPricing],
        Field(None, description="An existing price to bill, named as `pricing.price`."),
        Body(),
    ]
    price_data: Annotated[
        Optional[InvoiceItemPriceData],
        Field(None, description="A price created inline for this line."),
        Body(),
    ]
    period: Annotated[
        Optional[InvoiceItemPeriod],
        Field(None, description="The service period this line covers."),
        Body(),
    ]
    discountable: Annotated[
        Optional[bool],
        Field(None, description="Whether invoice-level discounts apply to this line."),
        Body(),
    ]
    discounts: Annotated[
        Optional[List[SubscriptionDiscount]],
        Field(None, description="Coupons or promotion codes applying to this line alone."),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the line."),
        Body(),
    ]
    tax_behavior: Annotated[
        Optional[_InvoiceTaxBehavior],
        Field(
            None,
            description=(
                "Whether the amount includes tax. Once set to inclusive or exclusive "
                "it cannot be changed."
            ),
        ),
        Body(),
    ]
    tax_code: Annotated[
        Optional[str], Field(None, description="The tax code for what is being billed."), Body()
    ]


class InvoiceItemsCreateRequest(_InvoiceItemFields):
    """Input schema for Stripe `POST /v1/invoiceitems`.

    API Reference: https://docs.stripe.com/api/invoiceitems/create
    """

    customer: Annotated[
        str,
        Field(..., description="The ID of the customer to bill."),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(None, description="Three-letter lowercase ISO currency code."),
        Body(),
    ]
    invoice: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The draft invoice to add this line to, at most 250 lines. Absent, "
                "the line waits for the customer's next subscription invoice and a "
                "standalone invoice will not collect it on its own."
            ),
        ),
        Body(),
    ]
    subscription: Annotated[
        Optional[str],
        Field(
            None,
            description="Bill this line on that subscription's invoices only.",
        ),
        Body(),
    ]


class InvoiceItemsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/invoiceitems`.

    API Reference: https://docs.stripe.com/api/invoiceitems/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="Only return lines for this customer."),
        Query(),
    ]
    invoice: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only return lines on this invoice. Naming one makes the customer "
                "filter unnecessary."
            ),
        ),
        Query(),
    ]
    pending: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True for lines not yet on any invoice, false for lines already "
                "attached. Absent, both."
            ),
        ),
        Query(),
    ]
    created: Annotated[
        Optional[CreatedFilter],
        Field(None, description="Only return lines created in this window."),
        Query(),
    ]


class InvoiceItemsUpdateRequest(_InvoiceItemFields):
    """Input schema for Stripe `POST /v1/invoiceitems/{invoiceitem}`.

    `customer`, `currency`, `invoice` and `subscription` are create-only: a line
    cannot be moved to another customer or another invoice.

    Editable only while the invoice is still open. The item's own `frozen_fields`
    lists what has stopped being editable, which beats guessing from invoice state.

    API Reference: https://docs.stripe.com/api/invoiceitems/update
    """

    invoiceitem: Annotated[
        str,
        Field(..., description="The ID of the invoice line to update."),
        Path(),
    ]


class InvoiceItemsDeleteRequest(BaseModel):
    """Input schema for Stripe `DELETE /v1/invoiceitems/{invoiceitem}`.

    Only while the line is unattached or its invoice is still a draft.

    API Reference: https://docs.stripe.com/api/invoiceitems/delete
    """

    invoiceitem: Annotated[
        str,
        Field(..., description="The ID of the invoice line to delete."),
        Path(),
    ]
