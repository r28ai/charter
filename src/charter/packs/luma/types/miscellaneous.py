# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma miscellaneous operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field

from charter.types import Body, Gloss, Query
from charter.types.model import PackModel

__all__ = [
    "UsersGetSelfRequest",
    "EntitiesLookupRequest",
    "PlacesSearchRequest",
    "ImagesSearchRequest",
    "ImagesCreateUploadUrlRequest",
]


class UsersGetSelfRequest(PackModel):
    """Get Self

    API Reference: https://docs.luma.com/reference/get_v1-users-get-self
    """


class EntitiesLookupRequest(PackModel):
    """Lookup Entity

    Look up an event or calendar by its slug, Luma URL, or permanent public path such as
    `event/evt-...`, `e/evt-...`, or `calendar/cal-...`. URL query parameters and fragments
    are ignored.

    API Reference: https://docs.luma.com/reference/get_v1-entities-lookup
    """

    slug: Annotated[
        str,
        Field(...),
        Query(),
        Gloss(
            "A slug, a Luma URL, or a permanent public path such as `event/evt-...` or "
            "`calendar/cal-...`."
        ),
    ]


class PlacesSearchRequest(PackModel):
    """Search Places

    Search Google Maps for a place and get up to 5 candidates. Pass the chosen `place_id` as
    `geo_address_json: { type: "google", place_id }` when creating or updating an event.

    API Reference: https://docs.luma.com/reference/get_v1-places-search
    """

    query: Annotated[
        str,
        Field(
            ..., min_length=1, description='Address or place name, e.g. "120 W 41st St, New York".'
        ),
        Query(),
    ]


class ImagesSearchRequest(PackModel):
    """Search Cover Images

    Search Luma’s gallery of stock event cover images by keyword. Pass the chosen
    `image_url` as `cover_url` when creating or updating an event — gallery images don’t
    need to be uploaded first.

    API Reference: https://docs.luma.com/reference/get_v1-images-search
    """

    query: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description=(
                'Keywords to match against image descriptions and tags, e.g. "dinner party".'
            ),
        ),
        Query(),
    ]
    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]


class ImagesCreateUploadUrlRequest(PackModel):
    """Create Upload URL

    API Reference: https://docs.luma.com/reference/post_v1-images-create-upload-url
    """

    content_type: Annotated[
        Optional[Literal["image/jpeg", "image/png"]],
        Field(None),
        Body(envelop=True),
        Gloss("The type of the image you will upload."),
    ]
