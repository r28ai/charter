# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Stripe's search endpoints.

Seven resources answer ``GET /v1/<resource>/search``, and all seven take the
same three parameters: a ``query`` in Stripe's search query language, a
``limit``, and a ``page`` cursor. What differs is which fields the query may
name, so each resource gets its own ``query`` field carrying its own list.

Search is not a list with a filter. It pages with an opaque ``page`` token that
Stripe hands back as ``next_page``, where every list endpoint derives its cursor
from the last object's id, so these schemas do not inherit
:class:`~charter.packs.stripe.types.common.StripeListRequest`: a
``starting_after`` here is a parameter Stripe does not accept.

API Reference: https://docs.stripe.com/search
OpenAPI: https://github.com/stripe/openapi (``/v1/*/search``)
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field

from charter.types import Gloss, Query
from charter.types.model import PackModel

__all__ = [
    "StripeSearchRequest",
    "ChargesSearchRequest",
    "CustomersSearchRequest",
    "InvoicesSearchRequest",
    "PaymentIntentsSearchRequest",
    "PricesSearchRequest",
    "ProductsSearchRequest",
    "SubscriptionsSearchRequest",
]

# How to write a query, condensed from the search query language section. It is
# the same for every resource, and a model that has not met Stripe's syntax
# guesses SQL or Lucene and gets a 400 back.
# https://docs.stripe.com/search#search-query-language
_SYNTAX = (
    "Syntax: field:value is an exact match, and string values must be quoted "
    "(email:'jane@example.com'). field~'abc' matches a substring of at least 3 "
    "characters on string fields. Numeric fields take >, <, >= and <=. A leading - "
    "negates a clause. Metadata is metadata['key']:'value'. Up to 10 clauses, "
    "joined by AND or by OR but never both, with no parentheses."
)
_SECONDS = "Timestamps are Unix seconds, not milliseconds: created>1700000000."
_CENTS = "Amounts are in the smallest currency unit: $15.00 is 1500."


def _query_description(resource: str, anchor: str, fields: str) -> str:
    return (
        "The search query string. See search query language "
        "(https://docs.stripe.com/search#search-query-language) and the list of "
        f"supported query fields for {resource} "
        f"(https://docs.stripe.com/search#query-fields-for-{anchor}). "
        f"Query fields for {resource}: {fields}."
    )


class StripeSearchRequest(PackModel):
    """The parameters every Stripe search endpoint accepts besides ``query``.

    API Reference: https://docs.stripe.com/api/customers/search
    """

    limit: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=100,
            description=(
                "A limit on the number of objects to be returned. Limit can range "
                "between 1 and 100, and the default is 10."
            ),
        ),
        Query(),
    ]
    page: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A cursor for pagination across multiple pages of results. Don't "
                "include this parameter on the first call. Use the next_page value "
                "returned in a previous response to request subsequent results."
            ),
        ),
        Query(),
    ]


class ChargesSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/charges/search`.

    API Reference: https://docs.stripe.com/api/charges/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "charges",
                "charges",
                "amount (numeric), billing_details.address.postal_code (token), "
                "created (numeric), currency (token), customer (token), disputed "
                "(token, 'true' or 'false'), metadata (token), "
                "payment_method_details.{SOURCE}.last4, .exp_month, .exp_year, "
                ".brand, .fingerprint, .reader and .location (token; SOURCE is card "
                "for online payments, interac_present for Terminal card payments on "
                "the Interac network and card_present for other Terminal card "
                "payments), refunded (token: 'true' is fully refunded, 'false' is "
                "unrefunded or partially refunded, null is not refundable), status "
                "(token)",
            ),
        ),
        Query(),
        Gloss(f"{_SYNTAX} {_SECONDS} {_CENTS}"),
    ]


class CustomersSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/customers/search`.

    API Reference: https://docs.stripe.com/api/customers/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "customers",
                "customers",
                "created (numeric), email (string), metadata (token), name (string), "
                "phone (string)",
            ),
        ),
        Query(),
        Gloss(f"{_SYNTAX} {_SECONDS}"),
    ]


class InvoicesSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/invoices/search`.

    API Reference: https://docs.stripe.com/api/invoices/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "invoices",
                "invoices",
                "created (numeric), currency (token), customer (token), "
                "last_finalization_error_code (token), last_finalization_error_type "
                "(token), metadata (token), number (string), receipt_number "
                "(string), status (string), subscription (string), total (numeric)",
            ),
        ),
        Query(),
        Gloss(f"{_SYNTAX} {_SECONDS} {_CENTS}"),
    ]


class PaymentIntentsSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/payment_intents/search`.

    API Reference: https://docs.stripe.com/api/payment_intents/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "payment intents",
                "paymentintents",
                "amount (numeric), created (numeric), currency (token), customer "
                "(token), metadata (token), status (token)",
            ),
        ),
        Query(),
        Gloss(
            f"{_SYNTAX} {_SECONDS} {_CENTS} A status match is against a cached "
            "status, so a result can show a newer one: check status on what comes back."
        ),
    ]


class PricesSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/prices/search`.

    API Reference: https://docs.stripe.com/api/prices/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "prices",
                "prices",
                "active (token), currency (token), lookup_key (string), metadata "
                "(token), product (string), type (token)",
            ),
        ),
        Query(),
        Gloss(_SYNTAX),
    ]


class ProductsSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/products/search`.

    API Reference: https://docs.stripe.com/api/products/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "products",
                "products",
                "active (token), description (string), metadata (token), name "
                "(string), shippable (token), url (string)",
            ),
        ),
        Query(),
        Gloss(_SYNTAX),
    ]


class SubscriptionsSearchRequest(StripeSearchRequest):
    """Input schema for Stripe `GET /v1/subscriptions/search`.

    API Reference: https://docs.stripe.com/api/subscriptions/search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=_query_description(
                "subscriptions",
                "subscriptions",
                "canceled_at (numeric), created (numeric), metadata (token), status (token)",
            ),
        ),
        Query(),
        Gloss(f"{_SYNTAX} {_SECONDS}"),
    ]
