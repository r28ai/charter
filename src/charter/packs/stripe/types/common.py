# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Shared request pieces for the Stripe pack.

Stripe gives every list endpoint the same three pagination parameters and the
same ``metadata`` map, so they are declared once here rather than repeated on
every schema.

API Reference: https://docs.stripe.com/api/pagination
"""

from __future__ import annotations

from typing import Annotated, Dict, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Query

__all__ = ["StripeListRequest", "Address"]


class StripeListRequest(BaseModel):
    """The parameters every Stripe list endpoint accepts.

    API Reference: https://docs.stripe.com/api/pagination
    """

    limit: Annotated[
        Optional[int],
        Field(
            10,
            ge=1,
            le=100,
            description=(
                "A limit on the number of objects to be returned, between 1 and 100. "
                "Defaults to 10."
            ),
        ),
        Query(),
    ]
    starting_after: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A cursor for use in pagination: an object ID that defines your place "
                "in the list. To get the next page, pass the id of the last object in "
                "the current page."
            ),
        ),
        Query(),
    ]
    ending_before: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A cursor for use in pagination: an object ID that defines your place "
                "in the list. Returns the page before the named object. Mutually "
                "exclusive with starting_after."
            ),
        ),
        Query(),
    ]

    @model_validator(mode="after")
    def _one_direction_at_a_time(self) -> StripeListRequest:
        """Stripe pages forwards or backwards, not both at once.

        The declared :data:`~charter.packs.stripe.STRIPE_PAGINATION` walks
        forwards with ``starting_after``; ``ending_before`` is here for a caller
        who wants the other direction. Sending both is a contradiction Stripe
        should not have to answer.
        """
        if self.starting_after is not None and self.ending_before is not None:
            raise ValueError(
                "`starting_after` and `ending_before` are the two directions of the "
                "same cursor and are mutually exclusive. Pass one."
            )
        return self


class Address(BaseModel):
    """A postal address.

    API Reference: https://docs.stripe.com/api/customers/create
    """

    line1: Optional[str] = Field(None, description="Address line 1 (street address, PO Box).")
    line2: Optional[str] = Field(
        None, description="Address line 2 (apartment, suite, unit, or building)."
    )
    city: Optional[str] = Field(None, description="City, district, suburb, town, or village.")
    state: Optional[str] = Field(None, description="State, county, province, or region.")
    postal_code: Optional[str] = Field(None, description="ZIP or postal code.")
    country: Optional[str] = Field(
        None, description="Two-letter country code (ISO 3166-1 alpha-2)."
    )


MetadataMap = Dict[str, str]
"""Stripe metadata is a flat map of string keys to string values.

On the wire it becomes ``metadata[order_id]=6735`` — the bracket notation the
form encoder produces.
"""
