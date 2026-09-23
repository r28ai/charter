# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Response models for Granola's webhook endpoints, and the two closed sets they
share with the request schemas.

A webhook endpoint is the only thing this API lets a program create, change or
delete. Everything else in the pack reads.

API Reference: https://docs.granola.ai/api-reference/create-webhook-endpoint
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import User
from charter.types import Mode

__all__ = [
    "WebhookScope",
    "WebhookEventName",
    "WebhookEndpoint",
    "CreateWebhookEndpointOutput",
    "ListWebhookEndpointsOutput",
    "DeleteWebhookEndpointOutput",
]

# Closed sets, both of them: Granola enumerates the three scopes and the three
# events and says nothing about either growing. `source` on a Speaker is the one
# place in this API that warns it might, and that one is a `str` instead.
WebhookScope = Literal["personal", "public", "workspace"]
WebhookEventName = Literal["note.access_granted", "note.edited", "note.generated"]


class WebhookEndpoint(BaseModel):
    """A registered delivery target: where events go, and which events reach it.

    The signing secret is not here. It is returned once, by the create call, and
    is never in a list or update response — see
    :class:`CreateWebhookEndpointOutput`.

    API Reference: https://docs.granola.ai/api-reference/list-webhook-endpoints
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the webhook endpoint"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the webhook endpoint"),
        Mode("response_only"),
    ]
    url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The HTTPS URL deliveries are sent to. When `url_redacted` is true, "
                "reduced to the URL's origin."
            ),
        ),
        Mode("response_only"),
    ]
    url_redacted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True when this response reduces `url` to its origin because the "
                "caller is not the endpoint's creator (the path can carry "
                "credentials). Orphaned endpoints whose creator account was deleted "
                "are returned unredacted so they can be cleaned up."
            ),
        ),
        Mode("response_only"),
    ]
    events: Annotated[
        Optional[List[WebhookEventName]],
        Field(None, description="The event names this endpoint is subscribed to"),
        Mode("response_only"),
    ]
    folder_ids: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Folder IDs this endpoint's delivery is restricted to, or an empty "
                "array when unrestricted. Events fire only for notes in these "
                "folders or their subfolders."
            ),
        ),
        Mode("response_only"),
    ]
    scopes: Annotated[
        Optional[List[WebhookScope]],
        Field(
            None,
            description=(
                "Which notes this endpoint receives events for. `personal` covers "
                "notes the creating user owns, notes shared directly with them, and "
                "notes in private folders shared with them. `public` covers notes "
                "visible to everyone in the workspace. `workspace` is reported for "
                "endpoints created with a workspace API key: public workspace notes "
                "plus notes in spaces with Granola API access enabled."
            ),
        ),
        Mode("response_only"),
    ]
    created_by: Annotated[
        Optional[User],
        Field(
            None,
            description=(
                "The user who created this endpoint. Null for a workspace-managed "
                'endpoint (`scopes` is `["workspace"]`), or when the creator\'s '
                "account was deleted."
            ),
        ),
        Mode("response_only"),
    ]
    enabled: Annotated[
        Optional[bool],
        Field(None, description="Whether deliveries are active"),
        Mode("response_only"),
    ]
    created_at: Annotated[
        Optional[str],
        Field(None, description="The creation time of the webhook endpoint"),
        Mode("response_only"),
    ]


class CreateWebhookEndpointOutput(WebhookEndpoint):
    """The created endpoint, plus the one field that is never returned again.

    ``signing_secret`` appears in this response and in no other. Granola cannot
    reissue it, so a caller that discards it has to delete the endpoint and
    create another one.

    API Reference: https://docs.granola.ai/api-reference/create-webhook-endpoint
    """

    signing_secret: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Secret for verifying delivery signatures (Standard Webhooks "
                "HMAC-SHA256). Shown only once, in this response — store it "
                "securely."
            ),
        ),
        Mode("response_only"),
    ]


class ListWebhookEndpointsOutput(BaseModel):
    """Every endpoint this key can manage.

    Not paginated, and deliberately so: Granola returns the whole list in one
    response, with no cursor and no `hasMore`. A personal key sees the endpoints
    its owner created; a workspace admin on Enterprise sees the whole workspace.

    API Reference: https://docs.granola.ai/api-reference/list-webhook-endpoints
    """

    webhook_endpoints: Annotated[
        Optional[List[WebhookEndpoint]],
        Field(None, description="The webhook endpoints this API key can manage"),
        Mode("response_only"),
    ]


class DeleteWebhookEndpointOutput(BaseModel):
    """The receipt for a deleted endpoint.

    API Reference: https://docs.granola.ai/api-reference/delete-webhook-endpoint
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the deleted webhook endpoint"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the webhook endpoint"),
        Mode("response_only"),
    ]
    deleted: Annotated[
        Optional[bool],
        Field(None, description="Always true — the endpoint no longer exists"),
        Mode("response_only"),
    ]
