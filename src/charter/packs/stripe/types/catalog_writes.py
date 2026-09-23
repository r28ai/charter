# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Reading a checkout back, and managing the catalog it sells from.

Three things here are asymmetric in ways that look like mistakes and are not.

**A price is almost immutable.** Update accepts eight fields and none of them is an
amount: no `unit_amount`, no `currency`, no `recurring`, not even `product`.
Changing what something costs means creating a new price and deactivating the old
one, which is deliberate on Stripe's part, since a price is referenced by every
subscription already using it.

**A completed checkout is not a paid one.** `status="complete"` means the session
finished; `payment_status` says whether money moved, and only `status` is a list
filter. Deciding to fulfil an order needs both.

**Products and prices disagree about their own path parameter.** Stripe spells one
`/v1/products/{id}` and the other `/v1/prices/{price}`. Both are copied from the
schema rather than guessed into consistency.

API Reference: https://docs.stripe.com/api/checkout/sessions
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.stripe.types.common import StripeListRequest
from charter.packs.stripe.types.invoices import _InvoiceTaxBehavior
from charter.packs.stripe.types.payments import CreatedFilter
from charter.packs.stripe.types.subscriptions import RecurringInterval
from charter.types import Body, Gloss, Path, Query

__all__ = [
    "CheckoutSessionStatus",
    "RecurringPrice",
    "CheckoutSessionsRetrieveRequest",
    "CheckoutSessionsListRequest",
    "CheckoutSessionsLineItemsRequest",
    "ProductsCreateRequest",
    "ProductsUpdateRequest",
    "PricesCreateRequest",
    "PricesUpdateRequest",
]

CheckoutSessionStatus = Literal["open", "complete", "expired"]

PriceUsageType = Literal["licensed", "metered"]


class _SessionId(BaseModel):
    session: Annotated[
        str,
        Field(..., description="The ID of the checkout session."),
        Path(),
    ]


class CheckoutSessionsRetrieveRequest(_SessionId):
    """Input schema for Stripe `GET /v1/checkout/sessions/{session}`.

    Read `payment_status` alongside `status` before fulfilling: a complete session
    has finished, which is not the same as having been paid.

    API Reference: https://docs.stripe.com/api/checkout/sessions/retrieve
    """


class CheckoutSessionsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/checkout/sessions`.

    `payment_status` is not a filter, so finding the sessions that actually paid
    means reading it off the results.

    API Reference: https://docs.stripe.com/api/checkout/sessions/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="Only return sessions for this customer."),
        Query(),
    ]
    subscription: Annotated[
        Optional[str],
        Field(None, description="Return the session that created this subscription."),
        Query(),
    ]
    payment_intent: Annotated[
        Optional[str],
        Field(None, description="Return the session for this PaymentIntent."),
        Query(),
    ]
    payment_link: Annotated[
        Optional[str],
        Field(None, description="Only return sessions created by this payment link."),
        Query(),
    ]
    status: Annotated[
        Optional[CheckoutSessionStatus],
        Field(
            None,
            description=(
                "Only return sessions in this state. 'complete' means finished, not "
                "necessarily paid."
            ),
        ),
        Query(),
    ]
    created: Annotated[
        Optional[CreatedFilter],
        Field(None, description="Only return sessions created in this window."),
        Query(),
    ]


class CheckoutSessionsLineItemsRequest(_SessionId, StripeListRequest):
    """Input schema for Stripe `GET /v1/checkout/sessions/{session}/line_items`.

    API Reference: https://docs.stripe.com/api/checkout/sessions/line_items
    """


class RecurringPrice(BaseModel):
    """What makes a price a subscription price rather than a one-off."""

    interval: RecurringInterval = Field(
        ..., description="How often it bills: day, week, month or year."
    )
    interval_count: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "Intervals between billings. At most three years, thirty-six months or "
            "a hundred and fifty-six weeks."
        ),
    )
    usage_type: Optional[PriceUsageType] = Field(
        None,
        description=(
            "'licensed' bills a fixed quantity, 'metered' bills what was reported. "
            "Absent, licensed."
        ),
    )


class _ProductFields(BaseModel):
    description: Annotated[
        Optional[str],
        Field(None, description="Customer-facing description of the product."),
        Body(),
    ]
    active: Annotated[
        Optional[bool],
        Field(None, description="Whether the product can be bought. Absent, it can."),
        Body(),
    ]
    images: Annotated[
        Optional[List[str]],
        Field(None, max_length=8, description="Up to eight image URLs."),
        Body(),
    ]
    url: Annotated[
        Optional[str],
        Field(None, description="A public webpage for the product."),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the product."),
        Body(),
    ]


class ProductsCreateRequest(_ProductFields):
    """Input schema for Stripe `POST /v1/products`.

    API Reference: https://docs.stripe.com/api/products/create
    """

    name: Annotated[
        str,
        Field(..., description="The product's name, shown to customers."),
        Body(),
    ]


class ProductsUpdateRequest(_ProductFields):
    """Input schema for Stripe `POST /v1/products/{id}`.

    A price cannot be created here. `default_price` names one that already exists.

    API Reference: https://docs.stripe.com/api/products/update
    """

    id: Annotated[
        str,
        Field(..., description="The ID of the product to update."),
        Path(),
    ]
    name: Annotated[Optional[str], Field(None, description="The product's name."), Body()]
    default_price: Annotated[
        Optional[str],
        Field(
            None,
            description="The ID of an existing price to make this product's default.",
        ),
        Body(),
    ]


class PricesCreateRequest(BaseModel):
    """Input schema for Stripe `POST /v1/prices`.

    Omit `recurring` for a one-off price. Setting it makes the price subscribable.

    API Reference: https://docs.stripe.com/api/prices/create
    """

    currency: Annotated[
        str,
        Field(..., description="Three-letter lowercase ISO currency code."),
        Body(),
    ]
    product: Annotated[
        str,
        Field(..., description="The ID of the product this price is for."),
        Body(),
    ]
    unit_amount: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The amount in the smallest currency unit. Mutually exclusive with "
                "unit_amount_decimal."
            ),
        ),
        Body(),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 prices this at fifteen "
            "cents. Multiply a decimal amount by 100."
        ),
    ]
    unit_amount_decimal: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Same as `unit_amount`, but accepts a decimal value in the smallest "
                "currency unit with at most 12 decimal places."
            ),
        ),
        Gloss(
            'Cents, not dollars: $15.00 is "1500". The decimal places are '
            'fractions of a cent, so "1500.5" is fifteen dollars and half a cent.'
        ),
        Body(),
    ]
    recurring: Annotated[
        Optional[RecurringPrice],
        Field(None, description="Billing interval. Absent, this is a one-off price."),
        Body(),
    ]
    nickname: Annotated[
        Optional[str],
        Field(None, description="An internal label. Customers never see it."),
        Body(),
    ]
    active: Annotated[
        Optional[bool],
        Field(None, description="Whether the price can be used. Absent, it can."),
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
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the price."),
        Body(),
    ]

    @model_validator(mode="after")
    def _one_amount(self) -> PricesCreateRequest:
        """Stripe states the exclusion on the field itself."""
        if self.unit_amount is not None and self.unit_amount_decimal is not None:
            raise ValueError(
                "Set `unit_amount` or `unit_amount_decimal`, not both — Stripe "
                "accepts only one of them."
            )
        return self


class PricesUpdateRequest(BaseModel):
    """Input schema for Stripe `POST /v1/prices/{price}`.

    Everything about what a price costs is fixed once it exists: no amount, no
    currency, no interval, not even the product. To change a price, create a new
    one and set `active` false on this.

    API Reference: https://docs.stripe.com/api/prices/update
    """

    price: Annotated[
        str,
        Field(..., description="The ID of the price to update."),
        Path(),
    ]
    active: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether the price can be used. Setting this false is how a price is retired."
            ),
        ),
        Body(),
    ]
    nickname: Annotated[Optional[str], Field(None, description="An internal label."), Body()]
    lookup_key: Annotated[
        Optional[str],
        Field(None, max_length=200, description="A key to look this price up by."),
        Body(),
    ]
    tax_behavior: Annotated[
        Optional[_InvoiceTaxBehavior],
        Field(
            None,
            description=(
                "Whether the amount includes tax. Settable only while it is still 'unspecified'."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the price."),
        Body(),
    ]
