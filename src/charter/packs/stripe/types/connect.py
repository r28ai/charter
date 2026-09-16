"""Connect and money movement, read-only.

Acting as a connected account is a header, not a field. Stripe's own schema never
declares `stripe_account` as a parameter anywhere, and `Stripe-Account` is transport,
so in this pack it goes through the per-call header channel where the host sets it
and the model cannot::

    await stripe.payouts_list.ainvoke(
        {"status": "pending"}, headers={"Stripe-Account": "acct_1032D82eZvKYlo2C"}
    )

The one exception is `accounts_retrieve`, where the connected account is named in the
URL. Stripe documents the header approach as implicit in any request carrying the
account id in the path, so there it is an ordinary field.

Nothing here writes. Creating or updating a connected account is an onboarding flow
with identity verification attached, and a tool that lets an agent start one is a
liability rather than a feature. Reading is the part a support agent needs.

Two names that look alike and are not: `destination` on transfers is a connected
account id and filters the platform's own transfers, while `destination` on payouts
is an external account — a bank account or card.

API Reference: https://docs.stripe.com/connect/authentication
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.stripe.types.common import StripeListRequest
from charter.packs.stripe.types.payments import CreatedFilter
from charter.types import Path, Query

__all__ = [
    "PayoutStatusFilter",
    "BalanceTransactionType",
    "AccountsListRequest",
    "AccountsRetrieveRequest",
    "TransfersListRequest",
    "TransfersRetrieveRequest",
    "PayoutsListRequest",
    "PayoutsRetrieveRequest",
    "ApplicationFeesListRequest",
    "BalanceTransactionsListRequest",
]

# Four, not five. The Payout object also reports `in_transit`, but the list filter
# documents only these, and Stripe's schema puts no enum on the query parameter at
# all — so whether `in_transit` filters is undocumented either way. Offering it here
# would be betting the model's call on undocumented behaviour.
PayoutStatusFilter = Literal["pending", "paid", "failed", "canceled"]

# A real enum in Stripe's schema, unlike most of this pack's filters, and checked
# against the prose list value by value.
BalanceTransactionType = Literal[
    "adjustment",
    "advance",
    "advance_funding",
    "anticipation_repayment",
    "application_fee",
    "application_fee_refund",
    "charge",
    "climate_order_purchase",
    "climate_order_refund",
    "connect_collection_transfer",
    "contribution",
    "fee_credit_funding",
    "inbound_transfer",
    "inbound_transfer_reversal",
    "issuing_authorization_hold",
    "issuing_authorization_release",
    "issuing_dispute",
    "issuing_transaction",
    "obligation_outbound",
    "obligation_reversal_inbound",
    "payment",
    "payment_failure_refund",
    "payment_network_reserve_hold",
    "payment_network_reserve_release",
    "payment_refund",
    "payment_reversal",
    "payment_unreconciled",
    "payout",
    "payout_cancel",
    "payout_failure",
    "payout_minimum_balance_hold",
    "payout_minimum_balance_release",
    "refund",
    "refund_failure",
    "reserve_hold",
    "reserve_release",
    "reserve_transaction",
    "reserved_funds",
    "stripe_balance_payment_debit",
    "stripe_balance_payment_debit_reversal",
    "stripe_fee",
    "stripe_fx_fee",
    "tax_fee",
    "tax_fund",
    "topup",
    "topup_reversal",
    "transfer",
    "transfer_cancel",
    "transfer_failure",
    "transfer_refund",
]

_CREATED = "Only return records created in this window."


class AccountsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/accounts`.

    Stripe offers no filters here beyond the creation window: no status, no country,
    no email. Narrowing past that means reading the results.

    API Reference: https://docs.stripe.com/api/accounts/list
    """

    created: Annotated[Optional[CreatedFilter], Field(None, description=_CREATED), Query()]


class AccountsRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/accounts/{account}`.

    API Reference: https://docs.stripe.com/api/accounts/retrieve
    """

    account: Annotated[
        str,
        Field(..., description="The ID of the connected account, beginning 'acct_'."),
        Path(),
    ]


class TransfersListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/transfers`.

    API Reference: https://docs.stripe.com/api/transfers/list
    """

    destination: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only return transfers sent to this connected account ID, beginning "
                "'acct_'."
            ),
        ),
        Query(),
    ]
    transfer_group: Annotated[
        Optional[str],
        Field(None, description="Only return transfers in this transfer group."),
        Query(),
    ]
    created: Annotated[Optional[CreatedFilter], Field(None, description=_CREATED), Query()]


class TransfersRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/transfers/{transfer}`.

    API Reference: https://docs.stripe.com/api/transfers/retrieve
    """

    transfer: Annotated[
        str,
        Field(..., description="The ID of the transfer."),
        Path(),
    ]


class PayoutsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/payouts`.

    API Reference: https://docs.stripe.com/api/payouts/list
    """

    status: Annotated[
        Optional[PayoutStatusFilter],
        Field(
            None,
            description=(
                "Only return payouts with this status. A payout Stripe has sent to the "
                "bank but not settled reports 'in_transit' on the object, which this "
                "filter does not document."
            ),
        ),
        Query(),
    ]
    destination: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only return payouts sent to this external account: a bank account or "
                "card, not a connected account."
            ),
        ),
        Query(),
    ]
    created: Annotated[Optional[CreatedFilter], Field(None, description=_CREATED), Query()]
    arrival_date: Annotated[
        Optional[CreatedFilter],
        Field(
            None,
            description="Only return payouts expected to arrive in this window.",
        ),
        Query(),
    ]


class PayoutsRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/payouts/{payout}`.

    API Reference: https://docs.stripe.com/api/payouts/retrieve
    """

    payout: Annotated[
        str,
        Field(..., description="The ID of the payout."),
        Path(),
    ]


class ApplicationFeesListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/application_fees`.

    API Reference: https://docs.stripe.com/api/application_fees/list
    """

    charge: Annotated[
        Optional[str],
        Field(None, description="Only return application fees for this charge ID."),
        Query(),
    ]
    created: Annotated[Optional[CreatedFilter], Field(None, description=_CREATED), Query()]


class BalanceTransactionsListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/balance_transactions`.

    For accounting, the object's `reporting_category` groups transactions more
    usefully than `type` does. It is not a filter, so it has to be read off results.

    API Reference: https://docs.stripe.com/api/balance_transactions/list
    """

    type: Annotated[
        Optional[BalanceTransactionType],
        Field(None, description="Only return transactions of this type."),
        Query(),
    ]
    payout: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only return transactions paid out in this payout. Automatic payouts "
                "only."
            ),
        ),
        Query(),
    ]
    source: Annotated[
        Optional[str],
        Field(None, description="Only return transactions for this object ID."),
        Query(),
    ]
    currency: Annotated[
        Optional[str],
        Field(None, description="Three-letter lowercase ISO currency code."),
        Query(),
    ]
    created: Annotated[Optional[CreatedFilter], Field(None, description=_CREATED), Query()]
