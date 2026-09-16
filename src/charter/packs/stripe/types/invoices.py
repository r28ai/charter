"""Invoices: the draft, the four one-way actions, and what may still be edited.

An invoice has a life stage, and the stage decides what the API accepts. A draft is
fully editable. Finalising it makes monetary values and ``collection_method``
uneditable, and three of the four actions below cannot be undone at all.

Two rules the reference states, encoded here:

* ``days_until_due`` and ``due_date`` are valid only when
  ``collection_method="send_invoice"``. Stripe defaults that field to
  ``charge_automatically``, so sending either one without also setting
  ``collection_method`` is rejected.
* ``customer`` is required unless ``from_invoice`` is given. ``from_invoice``
  revises an existing invoice and is not modelled here, so ``customer`` is
  required outright: it is required for every call this tool can make.

And one the reference does not state, left alone on purpose: whether
``send_invoice`` *requires* one of ``days_until_due``/``due_date``, and whether
supplying both is rejected. The API enforces something there, the reference does
not say what, and a guess would reject calls Stripe accepts.

API Reference: https://docs.stripe.com/api/invoices
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.stripe.types.common import StripeListRequest
from charter.packs.stripe.types.payments import CreatedFilter
from charter.packs.stripe.types.subscriptions import (
    CollectionMethod,
    SubscriptionDiscount,
)
from charter.types import Body, Gloss, Path, Query

__all__ = [
    "InvoiceStatus",
    "PendingInvoiceItemsBehavior",
    "_InvoiceTaxBehavior",
    "InvoicesListRequest",
    "InvoicesRetrieveRequest",
    "InvoicesCreateRequest",
    "InvoicesUpdateRequest",
    "InvoicesFinalizeRequest",
    "InvoicesSendRequest",
    "InvoicesVoidRequest",
    "InvoicesMarkUncollectibleRequest",
]

# The same five values on the object and as a list filter. Checked separately
# against both pages rather than assumed, because the two sets disagree on other
# Stripe resources.
InvoiceStatus = Literal["draft", "open", "paid", "uncollectible", "void"]

# Two values, not three. `include_and_require` is gone from the current reference.
PendingInvoiceItemsBehavior = Literal["exclude", "include"]

# Shared with invoice items, which bill under the same tax rules.
_InvoiceTaxBehavior = Literal["exclusive", "inclusive", "unspecified"]

_MEMO = "An arbitrary string attached to the invoice. Shown as the memo in the Dashboard."
_SEND_INVOICE_ONLY = "Valid only when `collection_method` is 'send_invoice'."


class _InvoiceId(BaseModel):
    """The path parameter the six single-invoice endpoints share."""

    invoice: Annotated[
        str,
        Field(..., description="The ID of the invoice."),
        Path(),
    ]


class InvoicesListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/invoices`.

    API Reference: https://docs.stripe.com/api/invoices/list
    """

    customer: Annotated[
        Optional[str],
        Field(None, description="Only return invoices for this customer ID."),
        Query(),
    ]
    subscription: Annotated[
        Optional[str],
        Field(None, description="Only return invoices for this subscription ID."),
        Query(),
    ]
    status: Annotated[
        Optional[InvoiceStatus],
        Field(None, description="Only return invoices with this status."),
        Query(),
    ]
    collection_method: Annotated[
        Optional[CollectionMethod],
        Field(None, description="Only return invoices collected this way."),
        Query(),
    ]
    created: Annotated[
        Optional[CreatedFilter],
        Field(None, description="Only return invoices created in this window."),
        Query(),
    ]


class InvoicesRetrieveRequest(_InvoiceId):
    """Input schema for Stripe `GET /v1/invoices/{invoice}`.

    The id is the whole request; Stripe documents no other parameters.

    API Reference: https://docs.stripe.com/api/invoices/retrieve
    """


class _InvoiceWriteCommon(BaseModel):
    """Fields create and update spell identically."""

    description: Annotated[Optional[str], Field(None, description=_MEMO), Body()]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the invoice."),
        Body(),
    ]
    auto_advance: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether Stripe collects the invoice automatically. False leaves the "
                "invoice where it is until you act on it."
            ),
        ),
        Body(),
    ]
    collection_method: Annotated[
        Optional[CollectionMethod],
        Field(
            None,
            description=(
                "How to collect payment. Absent, Stripe charges the customer's default "
                "payment method."
            ),
        ),
        Body(),
    ]
    days_until_due: Annotated[
        Optional[int],
        Field(None, ge=0, description=f"Days until the invoice is due. {_SEND_INVOICE_ONLY}"),
        Body(),
    ]
    due_date: Annotated[
        Optional[int],
        Field(
            None,
            description=f"Unix timestamp when payment is due. {_SEND_INVOICE_ONLY}",
        ),
        Gloss("Seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    default_payment_method: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The payment method to charge. It must belong to the invoice's "
                "customer."
            ),
        ),
        Body(),
    ]
    footer: Annotated[
        Optional[str],
        Field(None, description="Footer text displayed on the invoice."),
        Body(),
    ]
    statement_descriptor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "What the customer sees on their card statement. Must contain at least "
                "one letter."
            ),
        ),
        Body(),
    ]
    on_behalf_of: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The connected account the funds are intended for. Its branding and "
                "support information appear on the invoice."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _due_terms_need_invoicing(self) -> _InvoiceWriteCommon:
        """Both due fields are gated on the same collection method.

        Stripe defaults `collection_method` to 'charge_automatically', so omitting
        it while setting a due term is the same rejected request as setting it to
        'charge_automatically' outright.
        """
        if self.collection_method == "send_invoice":
            return self
        offered = [
            name
            for name, value in (
                ("days_until_due", self.days_until_due),
                ("due_date", self.due_date),
            )
            if value is not None
        ]
        if offered:
            raise ValueError(
                f"{' and '.join('`' + n + '`' for n in offered)} "
                f"{'apply' if len(offered) > 1 else 'applies'} only when "
                "`collection_method` is 'send_invoice'. Either set that, or drop "
                "the due terms."
            )
        return self


class InvoicesCreateRequest(_InvoiceWriteCommon):
    """Input schema for Stripe `POST /v1/invoices`.

    Creates a draft. It bills nothing until it is finalised.

    API Reference: https://docs.stripe.com/api/invoices/create
    """

    customer: Annotated[
        str,
        Field(..., description="The ID of the customer to bill."),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Three-letter lowercase ISO currency code. Absent, the customer's "
                "currency."
            ),
        ),
        Body(),
    ]
    subscription: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Bill this subscription. The invoice then includes only that "
                "subscription's pending items, and its billing cycle is untouched."
            ),
        ),
        Body(),
    ]
    pending_invoice_items_behavior: Annotated[
        Optional[PendingInvoiceItemsBehavior],
        Field(
            None,
            description=(
                "Whether to pull the customer's pending invoice items onto this "
                "invoice. Absent, Stripe excludes them and the draft is empty."
            ),
        ),
        Body(),
    ]
    discounts: Annotated[
        Optional[List[SubscriptionDiscount]],
        Field(
            None,
            description=(
                "Coupons and promotion codes to apply. Absent, the invoice inherits "
                "the customer's discount."
            ),
        ),
        Body(),
    ]


class InvoicesUpdateRequest(_InvoiceWriteCommon, _InvoiceId):
    """Input schema for Stripe `POST /v1/invoices/{invoice}`.

    `customer`, `currency`, `subscription` and `pending_invoice_items_behavior` are
    absent on purpose: Stripe accepts them only at creation.

    `collection_method` and the two due terms are editable only while the invoice is
    a draft. That is a property of the invoice rather than of the request, so it is
    described here and enforced by Stripe.

    API Reference: https://docs.stripe.com/api/invoices/update
    """

    discounts: Annotated[
        Optional[List[SubscriptionDiscount]],
        Field(
            None,
            description=(
                "Coupons and promotion codes. A populated array replaces the "
                "invoice's existing discounts. Absent, they are left alone."
            ),
        ),
        Body(),
    ]


class InvoicesFinalizeRequest(_InvoiceId):
    """Input schema for Stripe `POST /v1/invoices/{invoice}/finalize`.

    Turns a draft into an open invoice. Monetary values and `collection_method`
    stop being editable at this point.

    API Reference: https://docs.stripe.com/api/invoices/finalize
    """

    auto_advance: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether Stripe collects the invoice automatically after finalising. "
                "False leaves it open until you act on it."
            ),
        ),
        Body(),
    ]


class InvoicesSendRequest(_InvoiceId):
    """Input schema for Stripe `POST /v1/invoices/{invoice}/send`.

    Emails the invoice outside the normal schedule. In test mode nothing is sent,
    though the `invoice.sent` event still fires.

    API Reference: https://docs.stripe.com/api/invoices/send
    """


class InvoicesVoidRequest(_InvoiceId):
    """Input schema for Stripe `POST /v1/invoices/{invoice}/void`.

    Voiding is Stripe's deletion for a finalised invoice, and it keeps the paper
    trail. It cannot be undone: correcting a voided invoice means issuing another
    one or a credit note.

    API Reference: https://docs.stripe.com/api/invoices/void
    """


class InvoicesMarkUncollectibleRequest(_InvoiceId):
    """Input schema for Stripe `POST /v1/invoices/{invoice}/mark_uncollectible`.

    Records the invoice as bad debt. It does not refund, credit or cancel anything.

    API Reference: https://docs.stripe.com/api/invoices/mark_uncollectible
    """
