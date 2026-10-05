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

from typing import Annotated, List, Optional

from pydantic import Field

from charter.packs.stripe.types.common import ExpandPath
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
# guesses SQL or Lucene and gets a 400 back. A Gloss rather than description
# text, so that each `query` description stays Stripe's own sentence, diffable
# against the OpenAPI document.
# https://docs.stripe.com/search#search-query-language
_SYNTAX = (
    "Syntax: field:value is an exact match, and string values must be quoted "
    "(email:'jane@example.com'). field~'abc' matches a substring of at least 3 "
    "characters on string fields. Numeric fields take >, <, >= and <=. A leading - "
    "negates a clause, and field:null matches an empty field. Metadata is "
    "metadata['key']:'value'. Up to 10 clauses, joined by AND or by OR but never "
    "both, with no parentheses."
)
_SECONDS = "Timestamps are Unix seconds, not milliseconds: created>1700000000."
_CENTS = "Amounts are in the smallest currency unit: $15.00 is 1500."


def _query_description(resource: str, anchor: str) -> str:
    """Stripe's description of ``query``, word for word from the OpenAPI document."""
    return (
        "The search query string. See [search query language]"
        "(https://docs.stripe.com/search#search-query-language) and the list of "
        f"supported [query fields for {resource}]"
        f"(https://docs.stripe.com/search#query-fields-for-{anchor})."
    )


def _query_gloss(resource: str, fields: str, *notes: str) -> Gloss:
    """The fields this resource can be searched on, then how to write a query.

    The field list is the resource's table on the search page, which the
    description links to and a model cannot follow.
    """
    return Gloss(" ".join([f"Query fields for {resource}: {fields}.", _SYNTAX, *notes]))


class StripeSearchRequest(PackModel):
    """The parameters every Stripe search endpoint accepts besides ``query``.

    ``expand`` follows Stripe's rules for a list, which a search result is:
    a property of the results is named through ``data``, and ``total_count`` —
    which a search result carries only when asked — is named on its own.

    API Reference: https://docs.stripe.com/api/customers/search
    Expanding: https://docs.stripe.com/api/expanding_objects
    """

    expand: Annotated[
        Optional[List[ExpandPath]],
        Field(None, description="Specifies which fields in the response should be expanded."),
        Query(),
        Gloss(
            "'total_count' adds the number of results that match the query, accurate "
            "up to 10,000, without fetching them. Prefix a field of the results with "
            "data. to expand it on every result: 'data.customer' replaces each "
            "customer ID with the customer. At most four properties deep, data "
            "included: 'data.payment_intent.customer.default_source'."
        ),
    ]

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
            max_length=5000,
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
            max_length=5000,
            description=_query_description("charges", "charges"),
        ),
        Query(),
        _query_gloss(
            "charges",
            "amount (numeric), billing_details.address.postal_code (token), created "
            "(numeric), currency (token), customer (token), disputed (token, 'true' or "
            "'false'), metadata (token), payment_method_details.{SOURCE}.last4, "
            ".exp_month, .exp_year, .brand, .fingerprint, .reader and .location "
            "(token), refunded (token), status (token). SOURCE is card for online "
            "charges, interac_present for Terminal card-present charges on the "
            "Interac network, card_present for other Terminal card-present charges, "
            "or another payment method Terminal supports. refunded:'true' is fully "
            "refunded, refunded:'false' is not refunded or partially refunded",
            _SECONDS,
            _CENTS,
        ),
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
            max_length=5000,
            description=_query_description("customers", "customers"),
        ),
        Query(),
        _query_gloss(
            "customers",
            "created (numeric), email (string), metadata (token), name (string), phone (string)",
            _SECONDS,
        ),
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
            max_length=5000,
            description=_query_description("invoices", "invoices"),
        ),
        Query(),
        _query_gloss(
            "invoices",
            "created (numeric), currency (token), customer (token), "
            "last_finalization_error_code (token), last_finalization_error_type "
            "(token), metadata (token), number (string), receipt_number (string), "
            "status (string), subscription (string), total (numeric)",
            _SECONDS,
            _CENTS,
        ),
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
            max_length=5000,
            description=_query_description("payment intents", "paymentintents"),
        ),
        Query(),
        _query_gloss(
            "payment intents",
            "amount (numeric), created (numeric), currency (token), customer "
            "(token), metadata (token), status (token)",
            _SECONDS,
            _CENTS,
            "A status match is against a cached status, so a result can show a "
            "newer one: check status on what comes back.",
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
            max_length=5000,
            description=_query_description("prices", "prices"),
        ),
        Query(),
        _query_gloss(
            "prices",
            "active (token), currency (token), lookup_key (string), metadata "
            "(token), product (string), type (token)",
        ),
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
            max_length=5000,
            description=_query_description("products", "products"),
        ),
        Query(),
        _query_gloss(
            "products",
            "active (token), description (string), metadata (token), name "
            "(string), shippable (token), url (string)",
        ),
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
            max_length=5000,
            description=_query_description("subscriptions", "subscriptions"),
        ),
        Query(),
        _query_gloss(
            "subscriptions",
            "canceled_at (numeric), created (numeric), metadata (token), status (token)",
            _SECONDS,
        ),
    ]
