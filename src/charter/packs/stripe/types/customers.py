# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Stripe's customer endpoints.

API Reference: https://docs.stripe.com/api/customers
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.stripe.types.common import Address, StripeListRequest
from charter.types import Body, Gloss, Path, Query

__all__ = [
    "TaxExempt",
    "CustomerFields",
    "CustomersListRequest",
    "CustomersRetrieveRequest",
    "CustomersCreateRequest",
    "CustomersUpdateRequest",
]

TaxExempt = Literal["none", "exempt", "reverse"]


class CustomersListRequest(StripeListRequest):
    """Input schema for Stripe `GET /v1/customers`.

    Returns a list of your customers, sorted with the most recently created first.

    API Reference: https://docs.stripe.com/api/customers/list
    """

    email: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A case-sensitive filter on the list based on the customer's email "
                "field. The value must be a string."
            ),
        ),
        Query(),
    ]


class CustomersRetrieveRequest(BaseModel):
    """Input schema for Stripe `GET /v1/customers/{customer}`.

    API Reference: https://docs.stripe.com/api/customers/retrieve
    """

    customer: Annotated[
        str,
        Field(..., description="The identifier of the customer, e.g. 'cus_NffrFeUfNV2Hib'."),
        Path(),
    ]


class CustomerFields(BaseModel):
    """The customer attributes both create and update accept.

    Split out because the two endpoints are *nearly* the same and the difference
    matters: ``payment_method`` is a create-only parameter, and Stripe answers
    `400 Received unknown parameter` when an update carries it. Deriving update
    from create put it on the update schema, where the model could fill it in.

    API Reference: https://docs.stripe.com/api/customers/create
    """

    email: Annotated[
        Optional[str],
        Field(
            None,
            max_length=512,
            description=(
                "Customer's email address. Displayed alongside the customer in the "
                "dashboard and useful for searching and tracking."
            ),
        ),
        Body(),
    ]
    name: Annotated[
        Optional[str],
        Field(None, max_length=256, description="The customer's full name or business name."),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "An arbitrary string attached to the customer. Displayed alongside the "
                "customer in the dashboard."
            ),
        ),
        Body(),
    ]
    phone: Annotated[
        Optional[str],
        Field(None, max_length=20, description="The customer's phone number."),
        Body(),
    ]
    address: Annotated[
        Optional[Address],
        Field(None, description="The customer's address. Required if calculating taxes."),
        Body(),
    ]
    metadata: Annotated[
        Optional[Dict[str, str]],
        Field(
            None,
            description=(
                "Set of key-value pairs attached to the object, for storing additional "
                "information in a structured format."
            ),
        ),
        Body(),
    ]
    preferred_locales: Annotated[
        Optional[List[str]],
        Field(None, description="Customer's preferred languages, ordered by preference."),
        Body(),
    ]
    tax_exempt: Annotated[
        Optional[TaxExempt],
        Field(
            None,
            description="The customer's tax exemption. One of 'none', 'exempt', or 'reverse'.",
        ),
        Body(),
    ]
    balance: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "An integer amount in the smallest currency unit representing the "
                "customer's starting balance. A negative amount is a credit."
            ),
        ),
        Body(),
        Gloss(
            "Cents, not dollars: $15.00 is 1500, and 15 is a fifteen-cent "
            "balance. Multiply a decimal amount by 100."
        ),
    ]


class CustomersCreateRequest(CustomerFields):
    """Input schema for Stripe `POST /v1/customers`.

    API Reference: https://docs.stripe.com/api/customers/create
    """

    payment_method: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The ID of the PaymentMethod to attach to the customer. Accepted only "
                "when creating; use the Stripe dashboard or the PaymentMethods API to "
                "change one later."
            ),
        ),
        Body(),
    ]


class CustomersUpdateRequest(CustomerFields):
    """Input schema for Stripe `POST /v1/customers/{customer}`.

    Takes the shared customer attributes, plus the customer to update. Any
    parameter not provided is left unchanged. Note that this is *not* create's
    schema plus a path parameter: ``payment_method`` is create-only.

    API Reference: https://docs.stripe.com/api/customers/update
    """

    customer: Annotated[
        str,
        Field(..., description="The identifier of the customer to update."),
        Path(),
    ]
