"""Request schemas for Stripe's product catalog and subscriptions.

API Reference: https://docs.stripe.com/api/products
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from charter.packs.stripe.types.common import StripeListRequest
from charter.types import Query

__all__ = [
    "SubscriptionStatus",
    "ProductsListRequest",
    "PricesListRequest",
    "SubscriptionsListRequest",
]

SubscriptionStatus = Literal[
    "active",
    "past_due",
    "unpaid",
    "canceled",
    "incomplete",
    "incomplete_expired",
    "trialing",
    "paused",
    "all",
    "ended",
]


class ProductsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/products`.

    API Reference: https://docs.stripe.com/api/products/list
    """

    active: Annotated[
        Optional[bool],
        Field(None, description="Only return products that are active or inactive."),
        Query(),
    ]


class PricesListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/prices`.

    API Reference: https://docs.stripe.com/api/prices/list
    """

    active: Annotated[
        Optional[bool],
        Field(None, description="Only return prices that are active or inactive."),
        Query(),
    ]
    product: Annotated[
        Optional[str],
        Field(None, description="Only return prices for the given product."),
        Query(),
    ]
    currency: Annotated[
        Optional[str],
        Field(None, description="Only return prices in this three-letter ISO currency code."),
        Query(),
    ]


class SubscriptionsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/subscriptions`.

    API Reference: https://docs.stripe.com/api/subscriptions/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="The ID of the customer whose subscriptions will be retrieved."),
        Query(),
    ]
    price: Annotated[
        Optional[str],
        Field(
            None,
            description="Filter for subscriptions that contain this recurring price ID.",
        ),
        Query(),
    ]
    status: Annotated[
        Optional[SubscriptionStatus],
        Field(
            None,
            description=(
                "The status of the subscriptions to retrieve. Pass 'all' to return "
                "subscriptions of all statuses."
            ),
        ),
        Query(),
    ]
