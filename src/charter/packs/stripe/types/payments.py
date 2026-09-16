"""Request schemas for Stripe's payment endpoints.

API Reference: https://docs.stripe.com/api/payment_intents
"""

from __future__ import annotations

from typing import Annotated, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.stripe.types.common import StripeListRequest
from charter.types import Body, Gloss, Path, Query

__all__ = [
    "RefundReason",
    "RefundStatus",
    "CreatedFilter",
    "PaymentIntentsListRequest",
    "PaymentIntentsRetrieveRequest",
    "ChargesListRequest",
    "RefundsCreateRequest",
    "RefundsListRequest",
    "RefundsRetrieveRequest",
    "BalanceRetrieveRequest",
]

RefundReason = Literal["duplicate", "fraudulent", "requested_by_customer"]

# The Refund object's own status. Stripe documents no `status` filter on the list
# endpoint, so this is here to be read off a result, never sent as a parameter.
RefundStatus = Literal["pending", "requires_action", "succeeded", "failed", "canceled"]


class CreatedFilter(BaseModel):
    """A Stripe date-range filter.

    Serialises as `created[gte]=1700000000&created[lt]=1800000000`. Stripe also
    accepts a bare timestamp for an exact match, which this does not express: an
    exact second is not a filter anyone means, and the range is.
    """

    gt: Annotated[
        Optional[int],
        Field(None, description="Created strictly after this Unix timestamp."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ] = None
    gte: Annotated[
        Optional[int],
        Field(None, description="Created at or after this Unix timestamp."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ] = None
    lt: Annotated[
        Optional[int],
        Field(None, description="Created strictly before this Unix timestamp."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ] = None
    lte: Annotated[
        Optional[int],
        Field(None, description="Created at or before this Unix timestamp."),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
    ] = None


class PaymentIntentsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/payment_intents`.

    API Reference: https://docs.stripe.com/api/payment_intents/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="Only return PaymentIntents for the customer with this ID."),
        Query(),
    ]


class PaymentIntentsRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/payment_intents/{payment_intent}`.

    API Reference: https://docs.stripe.com/api/payment_intents/retrieve
    """

    payment_intent: Annotated[
        str,
        Field(..., description="The identifier of the PaymentIntent, e.g. 'pi_3MtwBw...'."),
        Path(),
    ]


class ChargesListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/charges`.

    API Reference: https://docs.stripe.com/api/charges/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="Only return charges for the customer with this ID."),
        Query(),
    ]
    payment_intent: Annotated[
        Optional[str],
        Field(None, description="Only return charges for this PaymentIntent."),
        Query(),
    ]


class RefundsCreateRequest(BaseModel):
    """Input schema for Stripe `POST /v1/refunds`.

    Refunds a charge that has previously been created. Provide either `charge` or
    `payment_intent`, not both.

    API Reference: https://docs.stripe.com/api/refunds/create
    """

    charge: Annotated[
        Optional[str],
        Field(None, description="The identifier of the charge to refund."),
        Body(),
    ]
    payment_intent: Annotated[
        Optional[str],
        Field(None, description="The identifier of the PaymentIntent to refund."),
        Body(),
    ]
    amount: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "A positive integer in the smallest currency unit representing how much "
                "to refund. Defaults to the entire charge."
            ),
        ),
        Body(),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 refunds fifteen cents. "
            "Multiply a decimal amount by 100."
        ),
    ]
    reason: Annotated[
        Optional[RefundReason],
        Field(
            None,
            description=(
                "The reason for the refund. If set to 'fraudulent', the associated "
                "payment is marked as fraudulent."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the refund."),
        Body(),
    ]

    @model_validator(mode="after")
    def _exactly_one_target(self) -> RefundsCreateRequest:
        """A refund names one thing to refund.

        Neither is a 400 asking which charge; both is a 400 saying they conflict.
        Refunds are the one write in this pack that moves money, so the argument
        that decides *what* gets refunded is worth checking before the call
        rather than after it.
        """
        if (self.charge is None) == (self.payment_intent is None):
            raise ValueError(
                "Exactly one of `charge` or `payment_intent` identifies what to "
                "refund. Pass the PaymentIntent if you have it; pass `charge` only "
                "for a charge created outside the PaymentIntents API."
            )
        return self


class BalanceRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/balance`.

    Retrieves the current account balance, based on the authentication used.

    API Reference: https://docs.stripe.com/api/balance/balance_retrieve
    """


class RefundsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/refunds`.

    Stripe documents no `status` filter here, so a caller wanting only succeeded
    refunds filters the returned objects. The six parameters below are the whole
    documented set.

    API Reference: https://docs.stripe.com/api/refunds/list
    """

    charge: Annotated[
        Optional[str],
        Field(None, description="Only return refunds for this charge ID."),
        Query(),
    ]
    payment_intent: Annotated[
        Optional[str],
        Field(None, description="Only return refunds for this PaymentIntent ID."),
        Query(),
    ]
    created: Annotated[
        Optional[CreatedFilter],
        Field(None, description="Only return refunds created in this window."),
        Query(),
    ]


class RefundsRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/refunds/{refund}`.

    The id is the whole request; Stripe documents no query parameters.

    API Reference: https://docs.stripe.com/api/refunds/retrieve
    """

    refund: Annotated[
        str,
        Field(..., description="The ID of the refund to retrieve."),
        Path(),
    ]
