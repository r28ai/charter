# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's webhook operations.

A webhook is how Linear pushes changes out rather than being polled for them.
It is scoped to one team, or to every public team at once, and it names the
resource types it wants.

``enabled`` is documented with a default of ``true``. It is **not** copied onto
the field: a default belongs to the request that omits the parameter, and
sending it explicitly makes a different request from the one the documentation
describes. Absent, Linear enables the webhook.

API Reference: https://linear.app/developers/webhooks
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.types import Body
from charter.types.model import PackModel

__all__ = [
    "WebhooksListRequest",
    "WebhookGetRequest",
    "WebhookCreateRequest",
    "WebhookUpdateRequest",
    "WebhookDeleteRequest",
]


class WebhooksListVariables(PageVariables):
    """Variables for the ``webhooks`` connection."""

    include_archived: Optional[bool] = Field(
        default=None, description="Include archived webhooks in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class WebhooksListRequest(PackModel):
    """List the workspace's webhooks."""

    variables: Annotated[
        WebhooksListVariables,
        Field(default_factory=WebhooksListVariables, description="Paging."),
        Body(envelop=True),
    ]


class WebhookGetVariables(PackModel):
    """Variables for the ``webhook`` query."""

    id: str = Field(..., description="The webhook's UUID.")


class WebhookGetRequest(PackModel):
    """Get one webhook."""

    variables: Annotated[
        WebhookGetVariables,
        Field(..., description="Which webhook to fetch."),
        Body(envelop=True),
    ]


class WebhookCreateInput(PackModel):
    """The input to ``webhookCreate``.

    Give a ``team_id`` to scope the webhook to one team, or set
    ``all_public_teams`` to cover every public team. Setting both is refused.
    """

    url: str = Field(..., description="The URL that will be called on data change.")
    resource_types: List[str] = Field(
        ...,
        min_length=1,
        description=(
            "List of resources the webhook should subscribe to, such as 'Issue', "
            "'Comment', 'Project' or 'Cycle'."
        ),
    )
    team_id: Optional[str] = Field(
        None, description="The identifier or key of the team associated with the webhook."
    )
    all_public_teams: Optional[bool] = Field(
        None, description="Whether to subscribe to all public teams."
    )
    label: Optional[str] = Field(None, description="A label for the webhook.")
    secret: Optional[str] = Field(
        None, description="A secret token used to sign the webhook payload."
    )
    enabled: Optional[bool] = Field(
        None,
        description=("Whether this webhook is enabled. Absent, Linear enables it."),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )

    @model_validator(mode="after")
    def _one_scope(self) -> WebhookCreateInput:
        if self.team_id is not None and self.all_public_teams:
            raise ValueError(
                "Scope the webhook to one team with `team_id`, or to every public "
                "team with `all_public_teams` — not both."
            )
        return self


class WebhookCreateVariables(PackModel):
    """Variables for the ``webhookCreate`` mutation."""

    input: WebhookCreateInput = Field(..., description="The webhook to create.")


class WebhookCreateRequest(PackModel):
    """Create a webhook."""

    variables: Annotated[
        WebhookCreateVariables,
        Field(..., description="The webhook to create."),
        Body(envelop=True),
    ]


class WebhookUpdateInput(PackModel):
    """The fields ``webhookUpdate`` changes. All optional."""

    url: Optional[str] = Field(None, description="The URL that will be called on data change.")
    resource_types: Optional[List[str]] = Field(
        None, description="List of resources the webhook should subscribe to."
    )
    label: Optional[str] = Field(None, description="A label for the webhook.")
    secret: Optional[str] = Field(
        None, description="A secret token used to sign the webhook payload."
    )
    enabled: Optional[bool] = Field(None, description="Whether this webhook is enabled.")

    @model_validator(mode="after")
    def _at_least_one_change(self) -> WebhookUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("webhookUpdate needs at least one field to change.")
        return self


class WebhookUpdateVariables(PackModel):
    """Variables for the ``webhookUpdate`` mutation."""

    id: str = Field(..., description="The webhook's UUID.")
    input: WebhookUpdateInput = Field(..., description="The fields to change.")


class WebhookUpdateRequest(PackModel):
    """Update a webhook."""

    variables: Annotated[
        WebhookUpdateVariables,
        Field(..., description="The webhook to update."),
        Body(envelop=True),
    ]


class WebhookDeleteVariables(PackModel):
    """Variables for the ``webhookDelete`` mutation."""

    id: str = Field(..., description="The webhook's UUID.")


class WebhookDeleteRequest(PackModel):
    """Delete a webhook."""

    variables: Annotated[
        WebhookDeleteVariables,
        Field(..., description="The webhook to delete."),
        Body(envelop=True),
    ]
