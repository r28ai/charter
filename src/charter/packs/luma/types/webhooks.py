# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma webhooks operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import Field

from charter.packs.luma.types.common import EventType
from charter.types import Body, Gloss, Query
from charter.types.model import PackModel

__all__ = [
    "WebhooksListRequest",
    "WebhooksGetRequest",
    "WebhooksCreateRequest",
    "WebhooksUpdateRequest",
    "WebhooksDeleteRequest",
]


class WebhooksListRequest(PackModel):
    """List Webhooks

    List all webhook endpoints for the calendar.

    API Reference: https://docs.luma.com/reference/get_v1-webhooks-list
    """

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


class WebhooksGetRequest(PackModel):
    """Get Webhook

    Get details about a specific webhook endpoint.

    API Reference: https://docs.luma.com/reference/get_v2-webhooks-get
    """

    id: Annotated[
        str,
        Field(...),
        Query(),
        Gloss("Webhook ID, as returned by `webhooks_create` or `webhooks_list`."),
    ]


class WebhooksCreateRequest(PackModel):
    """Create Webhook

    Create a new webhook endpoint to receive event notifications.

    API Reference: https://docs.luma.com/reference/post_v2-webhooks-create
    """

    url: Annotated[
        str,
        Field(..., pattern=r"^http.*"),
        Body(),
        Gloss("The URL Luma sends webhook deliveries to."),
    ]
    event_types: Annotated[
        List[EventType],
        Field(..., min_length=1),
        Body(),
        Gloss("The events to deliver. `*` subscribes to every type."),
    ]


class WebhooksUpdateRequest(PackModel):
    """Update Webhook

    Update a webhook endpoint's event types or status (active/paused).

    API Reference: https://docs.luma.com/reference/post_v2-webhooks-update
    """

    id: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("Webhook ID, as returned by `webhooks_create` or `webhooks_list`."),
    ]
    event_types: Annotated[
        Optional[List[EventType]],
        Field(None, min_length=1),
        Body(),
        Gloss("The events to deliver, replacing the current list. `*` subscribes to every type."),
    ]
    status: Annotated[
        Optional[Literal["active", "paused"]],
        Field(None),
        Body(),
        Gloss("`paused` stops deliveries; `active` resumes them."),
    ]


class WebhooksDeleteRequest(PackModel):
    """Delete Webhook

    Delete a webhook endpoint.

    API Reference: https://docs.luma.com/reference/post_v1-webhooks-delete
    """

    id: Annotated[
        str,
        Field(...),
        Body(envelop=True),
        Gloss("Webhook ID, as returned by `webhooks_create` or `webhooks_list`."),
    ]
