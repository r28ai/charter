"""Disputes, and the two ways this API loses money quietly.

**Writing evidence submits it.** Stripe states twice that updating any field in the
evidence hash submits *all* fields in the hash for review, and ``submit`` defaults to
true. So a call that sets one field is not a patch: it posts the whole hash to the
bank, and that cannot be taken back. ``submit=False`` stages evidence instead, which
is the only shape that lets anyone read it before it goes. The field is declared with
no default here so that choice is always the caller's, and never a silent true.

**Closing accepts the loss.** ``disputes_close`` takes no arguments at all, moves the
dispute from ``needs_response`` to ``lost``, and the reference calls it irreversible
in italics. A tool with nothing to validate is one where the call is the mistake, so
the only protection available is the description and the ``action_label``.

Two things are deliberately absent. The nine file-upload evidence fields
(``receipt``, ``customer_signature``, ``refund_policy`` and the rest) each need a
``file_...`` id from a prior multipart upload, which nothing here can produce. And
``enhanced_evidence`` is excluded because setting
``visa_compliance.fee_acknowledged`` to true spends 500 USD, refunded only if the
dispute is won. Neither belongs behind a boolean a model can flip.

API Reference: https://docs.stripe.com/api/disputes
"""

from __future__ import annotations

from typing import Annotated, Dict, Optional

from pydantic import BaseModel, Field

from charter.packs.stripe.types.common import StripeListRequest
from charter.packs.stripe.types.payments import CreatedFilter
from charter.types import Body, Path, Query

__all__ = [
    "DisputeEvidence",
    "DisputesListRequest",
    "DisputesRetrieveRequest",
    "DisputesUpdateRequest",
    "DisputesCloseRequest",
]

_TEXT_LIMIT = 20_000


class DisputeEvidence(BaseModel):
    """The evidence fields an agent can actually write.

    Every field here is free text. The file-upload fields Stripe also accepts are
    absent: they take an id minted by uploading an actual document, so there is
    nothing a tool could put in them.

    Stripe caps the combined length of all evidence at 150,000 characters, which is
    a property of the whole hash rather than of any field, so it is not expressible
    as a per-field limit.
    """

    product_description: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description="A description of the product or service that was sold.",
    )
    customer_name: Optional[str] = Field(None, description="The name of the customer.")
    customer_email_address: Optional[str] = Field(
        None, description="The email address of the customer."
    )
    customer_purchase_ip: Optional[str] = Field(
        None, description="The IP address the customer used when making the purchase."
    )
    billing_address: Optional[str] = Field(
        None, description="The billing address the customer provided."
    )
    duplicate_charge_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the earlier charge that appears to be a duplicate of the "
            "disputed one."
        ),
    )
    duplicate_charge_explanation: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description=(
            "How the disputed charge differs from the earlier one that looks like a "
            "duplicate."
        ),
    )
    refund_policy_disclosure: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description=(
            "How and when the customer was shown the refund policy before buying. "
            "Text, not an uploaded document."
        ),
    )
    refund_refusal_explanation: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description="Why the customer is not entitled to a refund.",
    )
    cancellation_policy_disclosure: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description=(
            "How and when the customer was shown the cancellation policy before "
            "buying. Text, not an uploaded document."
        ),
    )
    cancellation_rebuttal: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description="Why the customer's subscription was not cancelled.",
    )
    service_date: Optional[str] = Field(
        None,
        description=(
            "When the customer received or began receiving the service, written for a "
            "human to read rather than as a timestamp."
        ),
    )
    shipping_date: Optional[str] = Field(
        None,
        description=(
            "When the product began its route to the shipping address, written for a "
            "human to read rather than as a timestamp."
        ),
    )
    shipping_carrier: Optional[str] = Field(
        None,
        description=(
            "The delivery service that shipped the product. Separate several with "
            "commas."
        ),
    )
    shipping_tracking_number: Optional[str] = Field(
        None,
        description="The tracking number from the delivery service. Several, comma separated.",
    )
    shipping_address: Optional[str] = Field(
        None, description="The address the product was shipped to, as complete as possible."
    )
    access_activity_log: Optional[str] = Field(
        None,
        max_length=_TEXT_LIMIT,
        description=(
            "Server or activity logs showing the customer accessed the digital "
            "product, with IP addresses and timestamps."
        ),
    )
    uncategorized_text: Optional[str] = Field(
        None, max_length=_TEXT_LIMIT, description="Any additional evidence or statements."
    )


class _DisputeId(BaseModel):
    dispute: Annotated[
        str,
        Field(..., description="The ID of the dispute."),
        Path(),
    ]


class DisputesListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/disputes`.

    Stripe documents no `status` filter here, so narrowing to the disputes that still
    need a response means reading `status` off the results.

    API Reference: https://docs.stripe.com/api/disputes/list
    """

    charge: Annotated[
        Optional[str],
        Field(None, description="Only return disputes for this charge ID."),
        Query(),
    ]
    payment_intent: Annotated[
        Optional[str],
        Field(None, description="Only return disputes for this PaymentIntent ID."),
        Query(),
    ]
    created: Annotated[
        Optional[CreatedFilter],
        Field(None, description="Only return disputes created in this window."),
        Query(),
    ]


class DisputesRetrieveRequest(_DisputeId):
    """Input schema for Stripe `GET /v1/disputes/{dispute}`.

    Worth reading off the result: `evidence_details.due_by` and
    `evidence_details.past_due`. Evidence submitted after the deadline is wasted.

    API Reference: https://docs.stripe.com/api/disputes/retrieve
    """


class DisputesUpdateRequest(_DisputeId):
    """Input schema for Stripe `POST /v1/disputes/{dispute}`.

    Sending any evidence field submits every evidence field for review unless
    `submit` is false. Set `submit` to false to stage evidence for a human to read,
    then call again with true.

    API Reference: https://docs.stripe.com/api/disputes/update
    """

    evidence: Annotated[
        Optional[DisputeEvidence],
        Field(None, description="Evidence supporting the charge."),
        Body(),
    ]
    submit: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to send the evidence to the bank now. False stages it on the "
                "dispute instead, where it can be read and changed. Stripe submits if "
                "this is not set, and submitting cannot be undone."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the dispute."),
        Body(),
    ]


class DisputesCloseRequest(_DisputeId):
    """Input schema for Stripe `POST /v1/disputes/{dispute}/close`.

    Closing concedes the dispute. The status becomes `lost`, the funds stay with the
    customer, and it cannot be reopened.

    API Reference: https://docs.stripe.com/api/disputes/close
    """
