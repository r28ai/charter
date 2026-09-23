# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Payment intents: authorising money, capturing it, and giving it back.

The reason these exist as three tools rather than one is `capture_method="manual"`,
which authorises the customer's card without taking the money. The intent then sits
at `requires_capture` until something captures or cancels it, which is the shape of
every order that ships before it bills.

Three details worth having right.

Confirming server-side needs one more parameter than it looks like. Stripe offers
an intent whatever payment methods the account has enabled in its dashboard, and
some of those redirect the customer off-site, so `confirm` on its own is a 400
asking for a `return_url`. `automatic_payment_methods` is the other answer:
`allow_redirects="never"` narrows the intent to methods that finish in one call.
Without one of the two, every confirmed payment fails — and an agent taking a
payment has no client-side step to hand the intent off to.

`capture_method` defaults to `automatic_async`, not `automatic`. Stripe recommends
the async one for latency, and the distinction only matters when reading an intent
back.

`cancellation_reason` has two enums. Four values can be sent; the object reports
those four plus `failed_invoice`, `void_invoice`, `automatic` and `expired`, which
Stripe sets itself. A schema that validated a read value against the sendable set
would reject four legitimate ones, which is why only the request side is typed here.

API Reference: https://docs.stripe.com/api/payment_intents
"""

from __future__ import annotations

from typing import Annotated, Dict, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Gloss, Path

__all__ = [
    "CaptureMethod",
    "CancellationReason",
    "AutomaticPaymentMethods",
    "PaymentIntentsCreateRequest",
    "PaymentIntentsCaptureRequest",
    "PaymentIntentsCancelRequest",
    "ChargesRetrieveRequest",
]

CaptureMethod = Literal["automatic_async", "automatic", "manual"]


class AutomaticPaymentMethods(BaseModel):
    """Which payment methods Stripe offers on this intent.

    API Reference:
    https://docs.stripe.com/api/payment_intents/create#create_payment_intent-automatic_payment_methods
    """

    enabled: Annotated[
        bool,
        Field(
            ...,
            description=(
                "Offer the payment methods enabled in the dashboard. Stripe "
                "requires this whenever the object is sent at all."
            ),
        ),
    ]
    allow_redirects: Annotated[
        Optional[Literal["always", "never"]],
        Field(
            None,
            description=(
                "'never' keeps the intent to methods that finish without sending "
                "the customer off-site, which is what makes a server-side "
                "`confirm` possible without a `return_url`. Absent, Stripe allows "
                "redirects."
            ),
        ),
    ] = None


# What may be sent. The object reports four more that Stripe generates.
CancellationReason = Literal["duplicate", "fraudulent", "requested_by_customer", "abandoned"]


class _IntentId(BaseModel):
    intent: Annotated[
        str,
        Field(..., description="The ID of the PaymentIntent."),
        Path(),
    ]


class PaymentIntentsCreateRequest(BaseModel):
    """Input schema for Stripe `POST /v1/payment_intents`.

    API Reference: https://docs.stripe.com/api/payment_intents/create
    """

    amount: Annotated[
        int,
        Field(
            ...,
            ge=1,
            description=(
                "The amount to collect, in the smallest currency unit. Stripe "
                "enforces a minimum of roughly fifty cents."
            ),
        ),
        Body(),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 collects fifteen cents. "
            "Multiply a decimal amount by 100."
        ),
    ]
    currency: Annotated[
        str,
        Field(..., description="Three-letter lowercase ISO currency code."),
        Body(),
    ]
    customer: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The customer to charge. A payment method attached to a different "
                "customer cannot be used."
            ),
        ),
        Body(),
    ]
    payment_method: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The payment method to charge. If it belongs to a customer, name that customer too."
            ),
        ),
        Body(),
    ]
    capture_method: Annotated[
        Optional[CaptureMethod],
        Field(
            None,
            description=(
                "'manual' authorises the card and holds the funds for a later "
                "capture. Absent, Stripe captures as soon as the customer authorises."
            ),
        ),
        Body(),
    ]
    confirm: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Attempt the payment immediately rather than leaving the intent for "
                "the client to confirm. Needs either `return_url` or "
                "`automatic_payment_methods` with `allow_redirects='never'`, since "
                "the account's enabled payment methods may include ones that send "
                "the customer off-site."
            ),
        ),
        Body(),
    ]
    automatic_payment_methods: Annotated[
        Optional[AutomaticPaymentMethods],
        Field(
            None,
            description=(
                "Which payment methods to offer. Send "
                "`{'enabled': true, 'allow_redirects': 'never'}` to confirm a "
                "payment here without a return URL."
            ),
        ),
        Body(),
    ]
    return_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Where to send the customer back to after a payment method that "
                "redirects. Required by a `confirm` that allows redirects."
            ),
        ),
        Body(),
    ]
    off_session: Annotated[
        Optional[bool],
        Field(
            None,
            description=("The customer is not present. Only meaningful alongside `confirm`."),
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str], Field(None, description="An internal note on the payment."), Body()
    ]
    receipt_email: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Email a receipt here. In live mode this sends regardless of your email settings."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the payment."),
        Body(),
    ]

    @model_validator(mode="after")
    def _off_session_needs_confirm(self) -> PaymentIntentsCreateRequest:
        """Stripe errors on `off_session` unless the intent is being confirmed."""
        if self.off_session is not None and not self.confirm:
            raise ValueError(
                "`off_session` applies only when `confirm` is true. Either confirm "
                "the payment here, or drop `off_session`."
            )
        return self


class PaymentIntentsCaptureRequest(_IntentId):
    """Input schema for Stripe `POST /v1/payment_intents/{intent}/capture`.

    Only an intent at `requires_capture` can be captured, which means it was
    created with `capture_method="manual"`.

    API Reference: https://docs.stripe.com/api/payment_intents/capture
    """

    amount_to_capture: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            description=(
                "Capture less than was authorised. Absent, the whole capturable "
                "amount. It cannot exceed the original."
            ),
        ),
        Body(),
    ]
    final_capture: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "False keeps the remaining authorised funds available for a later "
                "capture. Only send this on an intent that supports multi-capture, "
                "which an online card payment does not: Stripe refuses the whole "
                "capture otherwise, even when the value matches what it would have "
                "done anyway. Absent, the uncaptured remainder is released."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the payment."),
        Body(),
    ]


class PaymentIntentsCancelRequest(_IntentId):
    """Input schema for Stripe `POST /v1/payment_intents/{intent}/cancel`.

    Cancelling releases any authorised funds back to the customer.

    API Reference: https://docs.stripe.com/api/payment_intents/cancel
    """

    cancellation_reason: Annotated[
        Optional[CancellationReason],
        Field(
            None,
            description=(
                "Why the payment is being cancelled. Stripe records its own reasons "
                "for cancellations it makes; these four are the ones you may send."
            ),
        ),
        Body(),
    ]


class ChargesRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/charges/{charge}`.

    API Reference: https://docs.stripe.com/api/charges/retrieve
    """

    charge: Annotated[
        str,
        Field(..., description="The ID of the charge."),
        Path(),
    ]
