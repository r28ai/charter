"""
Request schemas for Granola's webhook endpoints.

The API's whole write surface: register a delivery URL, change one, pause one,
delete one. Nothing here writes a note.

API Reference: https://docs.granola.ai/webhooks
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, field_validator

from charter.packs.granola.types.common import (
    FOLDER_ID_PATTERN,
    WEBHOOK_ENDPOINT_ID_PATTERN,
)
from charter.packs.granola.types.webhooks.models import WebhookEventName, WebhookScope
from charter.types import Body, Path

__all__ = [
    "WebhookEndpointsCreateRequest",
    "WebhookEndpointsListRequest",
    "WebhookEndpointsUpdateRequest",
    "WebhookEndpointsDeleteRequest",
]

_URL_DESCRIPTION = "The publicly reachable HTTPS URL to deliver events to"

_SCOPES_DESCRIPTION = (
    "Which notes to receive events for. `personal` covers notes you own, notes "
    "shared directly with you, and notes in private folders shared with you. "
    "`public` covers notes visible to everyone in the workspace. Pass both for "
    "both sets of notes. Workspace admins can disable scopes for non-admin "
    "members in the workspace's API settings. With a Workspace API key, pass "
    'exactly `["workspace"]` — the key\'s own scope: public workspace notes plus '
    "notes in spaces with Granola API access enabled."
)

_ENDPOINT_ID_DESCRIPTION = "The ID of the webhook endpoint"

# The pattern belongs to each element, not to the list, so it is declared on the
# item type. Written as a validator instead it would be absent from the JSON
# schema the model reads, and the model is who fills these in.
FolderId = Annotated[str, Field(pattern=FOLDER_ID_PATTERN)]


def _workspace_scope_stands_alone(scopes: Optional[List[str]]) -> Optional[List[str]]:
    """``workspace`` is a whole key's scope, not one a caller mixes into a set.

    Granola says it twice — "pass exactly `["workspace"]`" on create, "a
    workspace-managed endpoint's scope is fixed" on update — and answers 403
    either way. Judged here because the rule is about one field's contents, not
    about two fields meeting, which is what ``ConflictsWith`` covers.
    """
    if scopes and "workspace" in scopes and len(set(scopes)) > 1:
        raise ValueError(
            'scopes: "workspace" is the scope of a workspace API key and cannot be '
            'combined with "personal" or "public". Send exactly ["workspace"] with a '
            "workspace key, or the personal/public scopes with a personal one."
        )
    return scopes


class WebhookEndpointsCreateRequest(BaseModel):
    """Register an HTTPS URL to receive note events.

    The response to this call carries the signing secret, and no later response
    ever does. Store it when the call returns or create the endpoint again.

    The URL must be HTTPS and reachable from the internet; Granola rejects
    addresses on private networks.

    API Reference: https://docs.granola.ai/api-reference/create-webhook-endpoint
    """

    url: Annotated[
        str,
        Field(..., description=_URL_DESCRIPTION),
        Body(),
    ]
    scopes: Annotated[
        List[WebhookScope],
        Field(..., min_length=1, description=_SCOPES_DESCRIPTION),
        Body(),
    ]
    events: Annotated[
        Optional[List[WebhookEventName]],
        Field(
            None,
            min_length=1,
            description=(
                "Event names to subscribe to. Omit to subscribe to all events — "
                "`note.access_granted`, `note.edited` and `note.generated`."
            ),
        ),
        Body(),
    ]
    folder_ids: Annotated[
        Optional[List[FolderId]],
        Field(
            None,
            min_length=1,
            max_length=100,
            description=(
                "Restrict delivery to notes in these folders or any of their "
                "subfolders. Accepts folder IDs returned by `GET /v1/folders`. Omit "
                "to receive events for every note matching `scopes`. The same filter "
                "applies to all subscribed `events`."
            ),
        ),
        Body(),
    ]

    @field_validator("scopes")
    @classmethod
    def _workspace_stands_alone(cls, value: List[str]) -> List[str]:
        return _workspace_scope_stands_alone(value) or value


class WebhookEndpointsListRequest(BaseModel):
    """List the webhook endpoints this API key can manage.

    Takes nothing and pages through nothing: Granola returns the whole list in
    one response. A personal key sees the endpoints its owner created; a
    workspace admin on Enterprise sees every endpoint in the workspace.

    API Reference: https://docs.granola.ai/api-reference/list-webhook-endpoints
    """


class WebhookEndpointsUpdateRequest(BaseModel):
    """Change a webhook endpoint, or pause it.

    Every field is optional and an omitted one is left alone. The list fields
    replace rather than merge: sending one event name leaves the endpoint
    subscribed to that event only.

    Two rules Granola enforces with a 403 rather than a 400: a caller who is not
    the endpoint's creator may change `enabled` and nothing else, and a
    workspace-managed endpoint's scope is fixed.

    API Reference: https://docs.granola.ai/api-reference/update-webhook-endpoint
    """

    webhook_endpoint_id: Annotated[
        str,
        Field(
            ...,
            pattern=WEBHOOK_ENDPOINT_ID_PATTERN,
            description=_ENDPOINT_ID_DESCRIPTION,
        ),
        Path(),
    ]
    url: Annotated[
        Optional[str],
        Field(None, description=f"{_URL_DESCRIPTION}. Omit to leave unchanged."),
        Body(),
    ]
    scopes: Annotated[
        Optional[List[WebhookScope]],
        Field(
            None,
            min_length=1,
            description=(
                "Which notes to receive events for; replaces the current scopes. "
                "`personal` covers notes you own, notes shared directly with you, "
                "and notes in private folders shared with you. `public` covers notes "
                "visible to everyone in the workspace. Pass both for both sets of "
                "notes. Workspace admins can disable scopes for non-admin members in "
                "the workspace's API settings. A workspace-managed endpoint's scope "
                'is fixed: only `["workspace"]` is accepted. Omit to leave unchanged.'
            ),
        ),
        Body(),
    ]
    events: Annotated[
        Optional[List[WebhookEventName]],
        Field(
            None,
            min_length=1,
            description=(
                "Event names to subscribe to; replaces the current subscriptions. "
                "Omit to leave unchanged."
            ),
        ),
        Body(),
    ]
    folder_ids: Annotated[
        Optional[List[FolderId]],
        Field(
            None,
            max_length=100,
            description=(
                "Restrict delivery to notes in these folders or any of their "
                "subfolders; replaces the current folder filter. Accepts folder IDs "
                "returned by `GET /v1/folders`. Pass an empty array to remove the "
                "filter. Omit to leave unchanged."
            ),
        ),
        Body(),
    ]
    enabled: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Pause (`false`) or resume (`true`) event deliveries. A paused "
                "endpoint keeps its configuration and signing secret; events that "
                "occur while paused are not delivered later. Omit to leave "
                "unchanged."
            ),
        ),
        Body(),
    ]

    @field_validator("scopes")
    @classmethod
    def _workspace_stands_alone(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return _workspace_scope_stands_alone(value)


class WebhookEndpointsDeleteRequest(BaseModel):
    """Delete a webhook endpoint and stop its deliveries immediately.

    There is no disable-and-keep here — that is ``enabled: false`` on the update
    endpoint, which preserves the signing secret. A delete does not.

    API Reference: https://docs.granola.ai/api-reference/delete-webhook-endpoint
    """

    webhook_endpoint_id: Annotated[
        str,
        Field(
            ...,
            pattern=WEBHOOK_ENDPOINT_ID_PATTERN,
            description=_ENDPOINT_ID_DESCRIPTION,
        ),
        Path(),
    ]
