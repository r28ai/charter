# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Subscription lifecycle: create, update, cancel.

The three operations do not share a schema, and the reason is worth stating because
it looks like duplication. Stripe documents the same parameter names with different
validity on each endpoint:

* ``proration_behavior="always_invoice"`` is valid on update and documented as
  **unsupported for subscription creation**. Creation accepts it and does nothing
  with it — a 200 and no proration — so the reason to withhold it here is that a
  silent no-op is worse for a model than a refusal, not that Stripe refuses it.
* ``payment_behavior="pending_if_incomplete"`` is valid on update and documented as
  **exclusive to updates, cannot be used for creation**.
* ``customer``, ``currency`` and ``trial_period_days`` do not exist on update. A
  customer cannot be changed after creation, and trial length moves to ``trial_end``.
* ``items`` is required on create. On update it is optional, and *there* one of
  ``price`` or ``price_data`` is required per item.

A shared enum would let the model send a value the endpoint rejects, and the model
has no way to tell a bad argument from the API refusing the call, so it cannot
recover. Two Literals is the cheaper mistake.

API Reference:
https://docs.stripe.com/api/subscriptions/create
https://docs.stripe.com/api/subscriptions/update
https://docs.stripe.com/api/subscriptions/cancel
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Gloss, Path

__all__ = [
    "CollectionMethod",
    "CancelAtSentinel",
    "CancellationFeedback",
    "CancelAtUnset",
    "ProrationBehaviorOnCreate",
    "ProrationBehaviorOnUpdate",
    "PaymentBehaviorOnCreate",
    "PaymentBehaviorOnUpdate",
    "RecurringInterval",
    "PriceTaxBehavior",
    "SubscriptionDiscount",
    "PriceRecurring",
    "SubscriptionPriceData",
    "SubscriptionItemCreate",
    "SubscriptionItemUpdate",
    "CancellationDetails",
    "SubscriptionsCreateRequest",
    "SubscriptionsUpdateRequest",
    "SubscriptionsCancelRequest",
]

CollectionMethod = Literal["charge_automatically", "send_invoice"]

# `cancel_at` is a union: a timestamp, or one of these sentinels. Typing it as an
# integer alone would drop the sentinels; typing it as a string alone would drop the
# timestamp.
CancelAtSentinel = Literal["max_billed_until", "max_period_end", "min_period_end"]

# Stripe clears a scheduled cancellation with an empty string, and only on update —
# creation has nothing to clear and does not accept it. Verified against the live
# API at the pinned version: setting `cancel_at` then sending `cancel_at=""` answers
# 200 with `cancel_at: null`. Stripe's prose documents the three sentinels and not
# this, so it is asserted by a test rather than trusted to the reference.
CancelAtUnset = Literal[""]

RecurringInterval = Literal["day", "week", "month", "year"]

PriceTaxBehavior = Literal["exclusive", "inclusive", "unspecified"]

CancellationFeedback = Literal[
    "customer_service",
    "low_quality",
    "missing_features",
    "other",
    "switched_service",
    "too_complex",
    "too_expensive",
    "unused",
]

# `always_invoice` is documented as unsupported on creation, where it is accepted
# and silently ignored rather than refused.
ProrationBehaviorOnCreate = Literal["create_prorations", "none"]
ProrationBehaviorOnUpdate = Literal["always_invoice", "create_prorations", "none"]

# `pending_if_incomplete` is documented as update-only.
PaymentBehaviorOnCreate = Literal["allow_incomplete", "default_incomplete", "error_if_incomplete"]
PaymentBehaviorOnUpdate = Literal[
    "allow_incomplete", "default_incomplete", "error_if_incomplete", "pending_if_incomplete"
]

_MAX_ITEMS = 20


class SubscriptionDiscount(BaseModel):
    """One discount, on the subscription or on a single item.

    Stripe has no top-level `coupon` or `promotion_code` parameter on either endpoint.
    Both exist only inside a discounts array.
    """

    coupon: Optional[str] = Field(None, description="The ID of a coupon to apply.")
    discount: Optional[str] = Field(None, description="The ID of an existing discount to reuse.")
    promotion_code: Optional[str] = Field(None, description="The ID of a promotion code to apply.")


class PriceRecurring(BaseModel):
    """How often an inline price bills."""

    interval: RecurringInterval = Field(
        ..., description="The billing frequency: day, week, month or year."
    )
    interval_count: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "The number of intervals between billings. Absent, Stripe bills once per interval."
        ),
    )


class SubscriptionPriceData(BaseModel):
    """An inline price, created with the subscription rather than looked up."""

    currency: str = Field(..., description="Three-letter lowercase ISO currency code.")
    product: str = Field(..., description="The ID of the product this price is for.")
    recurring: PriceRecurring = Field(..., description="The billing interval.")
    unit_amount: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "A positive integer in the smallest currency unit. Mutually exclusive "
                "with unit_amount_decimal."
            ),
        ),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 charges fifteen cents each "
            "period. Multiply a decimal amount by 100."
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
    tax_behavior: Optional[PriceTaxBehavior] = Field(
        None,
        description=(
            "Whether the price is considered inclusive or exclusive of taxes. Stripe "
            "recommends setting this if you calculate taxes."
        ),
    )

    @model_validator(mode="after")
    def _one_amount(self) -> SubscriptionPriceData:
        if self.unit_amount is not None and self.unit_amount_decimal is not None:
            raise ValueError(
                "Set `unit_amount` or `unit_amount_decimal`, not both — they are two "
                "spellings of the same amount."
            )
        return self


class _SubscriptionItemCommon(BaseModel):
    """The item fields both create and update accept."""

    price: Optional[str] = Field(None, description="The ID of the price object.")
    price_data: Optional[SubscriptionPriceData] = Field(
        None, description="An inline price, instead of naming an existing one."
    )
    quantity: Optional[int] = Field(
        None, ge=0, description="How many of this price the subscription covers."
    )
    metadata: Optional[Dict[str, str]] = Field(
        None, description="Set of key-value pairs attached to this item."
    )
    tax_rates: Optional[List[str]] = Field(
        None,
        description=("Tax rate IDs overriding the subscription's default_tax_rates for this item."),
    )
    discounts: Optional[List[SubscriptionDiscount]] = Field(
        None, description="Discounts applying to this item alone."
    )


class SubscriptionItemCreate(_SubscriptionItemCommon):
    """One item on a new subscription.

    Nothing here is required. The reference carries the "one of `price` or
    `price_data` is required" rule on update only, and inventing it here would
    reject calls Stripe accepts.
    """


class SubscriptionItemUpdate(_SubscriptionItemCommon):
    """One item on an existing subscription.

    Omitting `id` adds a new item rather than editing one, which is the difference
    between changing a plan and buying a second one.
    """

    id: Optional[str] = Field(
        None,
        description=(
            "The ID of the subscription item to modify. Omit it and Stripe adds a "
            "new item instead of updating an existing one."
        ),
    )
    deleted: Optional[bool] = Field(
        None, description="Set true to remove this item from the subscription."
    )
    clear_usage: Optional[bool] = Field(
        None,
        description=(
            "Whether to reset the billing period's usage. Required when deleting an "
            "item that records usage. No effect when the plan has a billing meter."
        ),
    )

    @model_validator(mode="after")
    def _price_on_update(self) -> SubscriptionItemUpdate:
        """Stripe documents one of `price` or `price_data` as required here.

        Only when the item is not being deleted: a delete names the item by id and
        has no price to give.
        """
        if self.deleted:
            return self
        if self.price is None and self.price_data is None:
            raise ValueError(
                "A subscription item needs one of `price` or `price_data` on update. "
                "To remove an item instead, send its `id` with `deleted: true`."
            )
        return self


class CancellationDetails(BaseModel):
    """Why the subscription was cancelled.

    Recorded on the subscription; it does not change what Stripe bills.
    """

    comment: Optional[str] = Field(
        None, description="A free-text comment, if the customer gave one."
    )
    feedback: Optional[CancellationFeedback] = Field(
        None, description="The customer-submitted reason, from Stripe's fixed set."
    )
    feedback_option: Optional[str] = Field(
        None, description="A customised feedback option, for more detail than the enum."
    )


class _SubscriptionWriteCommon(BaseModel):
    """Parameters create and update spell identically."""

    description: Annotated[
        Optional[str],
        Field(
            None,
            max_length=500,
            description="An arbitrary string attached to the subscription.",
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Set of key-value pairs attached to the subscription."),
        Body(),
    ]
    trial_end: Annotated[
        Optional[Union[Literal["now"], int]],
        Field(
            None,
            description=(
                "When the trial ends: the string 'now' to end it immediately, or a "
                "Unix timestamp at most two years out. Overrides any trial the plan "
                "defines."
            ),
        ),
        Gloss("A timestamp is seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    cancel_at: Annotated[
        Optional[Union[int, CancelAtSentinel]],
        Field(
            None,
            description=(
                "When to cancel: a Unix timestamp, or one of 'max_billed_until', "
                "'max_period_end', 'min_period_end'. A timestamp before the current "
                "period ends prorates if prorations are enabled."
            ),
        ),
        Gloss("A timestamp is seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    collection_method: Annotated[
        Optional[CollectionMethod],
        Field(
            None,
            description=("How to collect payment. Absent, Stripe charges automatically."),
        ),
        Body(),
    ]
    days_until_due: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            description=(
                "Days until an invoice is due. Valid only when collection_method is 'send_invoice'."
            ),
        ),
        Body(),
    ]
    default_payment_method: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The payment method to charge. It must already belong to this "
                "subscription's customer."
            ),
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _due_days_need_invoicing(self) -> _SubscriptionWriteCommon:
        """`days_until_due` is meaningless when Stripe charges the card itself.

        Stripe answers 400 for the combination. Checking it here costs nothing and
        the model gets a sentence it can act on instead of a rejected call.
        """
        if self.days_until_due is not None and self.collection_method != "send_invoice":
            raise ValueError(
                "`days_until_due` applies only when `collection_method` is "
                "'send_invoice'. Either set that, or drop `days_until_due`."
            )
        return self


class SubscriptionsCreateRequest(_SubscriptionWriteCommon):
    """Input schema for Stripe `POST /v1/subscriptions`.

    API Reference: https://docs.stripe.com/api/subscriptions/create
    """

    customer: Annotated[
        Optional[str],
        Field(
            None,
            description="The ID of the customer to subscribe.",
        ),
        Body(),
    ]
    items: Annotated[
        List[SubscriptionItemCreate],
        Field(
            ...,
            max_length=_MAX_ITEMS,
            description=f"The prices the customer is subscribing to, up to {_MAX_ITEMS}.",
        ),
        Body(),
    ]
    currency: Annotated[
        Optional[str],
        Field(None, description="Three-letter lowercase ISO currency code."),
        Body(),
    ]
    trial_period_days: Annotated[
        Optional[int],
        Field(
            None,
            ge=0,
            description=("Length of the trial in days. Overrides any trial the plan defines."),
        ),
        Body(),
    ]
    cancel_at_period_end: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to cancel at the end of the current period. Absent, Stripe "
                "does not schedule a cancellation."
            ),
        ),
        Body(),
    ]
    proration_behavior: Annotated[
        Optional[ProrationBehaviorOnCreate],
        Field(
            None,
            description=(
                "How to handle prorations. Absent, Stripe creates them. "
                "'always_invoice' is not accepted on creation."
            ),
        ),
        Body(),
    ]
    payment_behavior: Annotated[
        Optional[PaymentBehaviorOnCreate],
        Field(
            None,
            description=(
                "What to do if the first payment fails. Absent, Stripe allows the "
                "subscription to be created incomplete. 'pending_if_incomplete' is "
                "not accepted on creation."
            ),
        ),
        Body(),
    ]
    discounts: Annotated[
        Optional[List[SubscriptionDiscount]],
        Field(
            None,
            description=(
                "Coupons and promotion codes to apply. Absent, the subscription "
                "inherits the customer's discount."
            ),
        ),
        Body(),
    ]


class SubscriptionsUpdateRequest(_SubscriptionWriteCommon):
    """Input schema for Stripe `POST /v1/subscriptions/{subscription}`.

    `customer`, `currency` and `trial_period_days` are absent on purpose: Stripe does
    not accept them here.

    API Reference: https://docs.stripe.com/api/subscriptions/update
    """

    subscription: Annotated[
        str,
        Field(..., description="The ID of the subscription to update."),
        Path(),
    ]
    items: Annotated[
        Optional[List[SubscriptionItemUpdate]],
        Field(
            None,
            max_length=_MAX_ITEMS,
            description=(
                f"The items to change, up to {_MAX_ITEMS}. Absent, the items are left alone."
            ),
        ),
        Body(),
    ]
    cancel_at: Annotated[
        Optional[Union[int, CancelAtSentinel, CancelAtUnset]],
        Field(
            None,
            description=(
                "When to cancel: a Unix timestamp, or one of 'max_billed_until', "
                "'max_period_end', 'min_period_end'. A timestamp before the current "
                "period ends prorates if prorations are enabled. Pass an empty "
                "string to clear a cancellation that was scheduled earlier; "
                "`cancel_at_period_end` does not clear a timestamp."
            ),
        ),
        Gloss("A timestamp is seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    cancel_at_period_end: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether the subscription cancels at the end of the current period. "
                "Send it only to change the setting."
            ),
        ),
        Body(),
    ]
    proration_behavior: Annotated[
        Optional[ProrationBehaviorOnUpdate],
        Field(
            None,
            description=(
                "How to handle prorations when the billing cycle or an item quantity "
                "changes. Absent, Stripe creates them."
            ),
        ),
        Body(),
    ]
    payment_behavior: Annotated[
        Optional[PaymentBehaviorOnUpdate],
        Field(
            None,
            description=(
                "What to do if payment for the update fails. Absent, Stripe allows "
                "the subscription to go past_due."
            ),
        ),
        Body(),
    ]
    proration_date: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "A Unix timestamp to calculate prorations against, as though the "
                "update happened then. Absent, Stripe uses now."
            ),
        ),
        Gloss("A timestamp is seconds, not milliseconds: 1700000000, not 1700000000000."),
        Body(),
    ]
    cancellation_details: Annotated[
        Optional[CancellationDetails],
        Field(None, description="Why the subscription is being cancelled."),
        Body(),
    ]
    discounts: Annotated[
        Optional[List[SubscriptionDiscount]],
        Field(
            None,
            description=(
                "Coupons and promotion codes. A populated array replaces the "
                "subscription's existing discounts. Absent, they are left alone."
            ),
        ),
        Body(),
    ]


class SubscriptionsCancelRequest(BaseModel):
    """Input schema for Stripe `DELETE /v1/subscriptions/{subscription}`.

    Cancels immediately. Once cancelled the subscription is largely immutable: only
    `metadata` and `cancellation_details` can still be changed. To stop a
    subscription at the end of the period instead, update it with
    `cancel_at_period_end`.

    API Reference: https://docs.stripe.com/api/subscriptions/cancel
    """

    subscription: Annotated[
        str,
        Field(..., description="The ID of the subscription to cancel."),
        Path(),
    ]
    invoice_now: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to invoice now for un-invoiced metered usage and pending "
                "proration items. Absent, Stripe does not."
            ),
        ),
        Body(),
    ]
    prorate: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to credit the unused time remaining in the period. Absent, "
                "Stripe does not."
            ),
        ),
        Body(),
    ]
    cancellation_details: Annotated[
        Optional[CancellationDetails],
        Field(None, description="Why the subscription was cancelled."),
        Body(),
    ]
