# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's customer operations.

Linear's customer model has two halves: a **customer** is the company, and a
**customer need** — what the product calls a customer request — is one piece of
feedback from that company, optionally attached to an issue. Counting requests
per issue is how Linear ranks demand.

``customerNeedCreate`` is the one mutation in this pack whose payload carries no
entity: it answers ``{success}`` alone. The envelope still reads it, so a
declined request still raises.

API Reference: https://linear.app/developers/managing-customers
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import CustomerFilter, CustomerNeedFilter
from charter.types import Body

__all__ = [
    "CustomersListRequest",
    "CustomerGetRequest",
    "CustomerCreateRequest",
    "CustomerUpdateRequest",
    "CustomerDeleteRequest",
    "CustomerNeedsListRequest",
    "CustomerNeedCreateRequest",
    "CustomerNeedUpdateRequest",
    "CustomerNeedDeleteRequest",
    "CustomerStatusesListRequest",
    "CustomerTiersListRequest",
]


class CustomersListVariables(PageVariables):
    """Variables for the ``customers`` connection."""

    filter: Optional[CustomerFilter] = Field(
        default=None, description="Narrow the customers returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived customers in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class CustomersListRequest(BaseModel):
    """List customers."""

    variables: Annotated[
        CustomersListVariables,
        Field(default_factory=CustomersListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class CustomerGetVariables(BaseModel):
    """Variables for the ``customer`` query."""

    id: str = Field(..., description="The customer's UUID.")


class CustomerGetRequest(BaseModel):
    """Get one customer."""

    variables: Annotated[
        CustomerGetVariables,
        Field(..., description="Which customer to fetch."),
        Body(envelop=True),
    ]


class CustomerCreateInput(BaseModel):
    """The input to ``customerCreate``."""

    name: str = Field(..., description="The name of the customer.")
    domains: Optional[List[str]] = Field(
        None,
        description=("The domains associated with the customer. Absent, Linear records none."),
    )
    external_ids: Optional[List[str]] = Field(
        None,
        description=("The ids of the customer in external systems. Absent, Linear records none."),
    )
    owner_id: Optional[str] = Field(
        None, description="The identifier of the user who owns the customer."
    )
    status_id: Optional[str] = Field(None, description="The identifier of the customer's status.")
    tier_id: Optional[str] = Field(None, description="The identifier of the customer's tier.")
    revenue: Optional[int] = Field(
        None, description="The annual revenue associated with the customer."
    )
    size: Optional[int] = Field(None, description="The number of employees of the customer.")
    logo_url: Optional[str] = Field(None, description="The URL of the customer's logo.")
    slack_channel_id: Optional[str] = Field(
        None, description="The ID of the Slack channel to link to this customer."
    )
    main_source_id: Optional[str] = Field(
        None,
        description=(
            "The primary external source ID for customers with multiple sources. "
            "Must be one of the values provided in externalIds."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )


class CustomerCreateVariables(BaseModel):
    """Variables for the ``customerCreate`` mutation."""

    input: CustomerCreateInput = Field(..., description="The customer to create.")


class CustomerCreateRequest(BaseModel):
    """Create a customer."""

    variables: Annotated[
        CustomerCreateVariables,
        Field(..., description="The customer to create."),
        Body(envelop=True),
    ]


class CustomerUpdateInput(BaseModel):
    """The fields ``customerUpdate`` changes. All optional."""

    name: Optional[str] = Field(None, description="The name of the customer.")
    domains: Optional[List[str]] = Field(
        None, description="The domains associated with the customer."
    )
    external_ids: Optional[List[str]] = Field(
        None, description="The ids of the customer in external systems."
    )
    owner_id: Optional[str] = Field(
        None, description="The identifier of the user who owns the customer."
    )
    status_id: Optional[str] = Field(None, description="The identifier of the customer's status.")
    tier_id: Optional[str] = Field(None, description="The identifier of the customer's tier.")
    revenue: Optional[int] = Field(
        None, description="The annual revenue associated with the customer."
    )
    size: Optional[int] = Field(None, description="The number of employees of the customer.")
    logo_url: Optional[str] = Field(None, description="The URL of the customer's logo.")
    slack_channel_id: Optional[str] = Field(
        None,
        description=(
            "The ID of the Slack channel to link to this customer. This schema "
            "cannot send null to unlink — absent means unchanged."
        ),
    )
    main_source_id: Optional[str] = Field(
        None,
        description=(
            "The primary external source ID for customers with multiple sources. "
            "Must be one of the values in externalIds."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> CustomerUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("customerUpdate needs at least one field to change.")
        return self


class CustomerUpdateVariables(BaseModel):
    """Variables for the ``customerUpdate`` mutation."""

    id: str = Field(..., description="The customer's UUID.")
    input: CustomerUpdateInput = Field(..., description="The fields to change.")


class CustomerUpdateRequest(BaseModel):
    """Update a customer."""

    variables: Annotated[
        CustomerUpdateVariables,
        Field(..., description="The customer to update."),
        Body(envelop=True),
    ]


class CustomerDeleteVariables(BaseModel):
    """Variables for the ``customerDelete`` mutation."""

    id: str = Field(..., description="The customer's UUID.")


class CustomerDeleteRequest(BaseModel):
    """Delete a customer."""

    variables: Annotated[
        CustomerDeleteVariables,
        Field(..., description="The customer to delete."),
        Body(envelop=True),
    ]


class CustomerNeedsListVariables(PageVariables):
    """Variables for the ``customerNeeds`` connection."""

    filter: Optional[CustomerNeedFilter] = Field(
        default=None, description="Narrow the requests returned."
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived requests in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class CustomerNeedsListRequest(BaseModel):
    """List customer requests."""

    variables: Annotated[
        CustomerNeedsListVariables,
        Field(default_factory=CustomerNeedsListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class CustomerNeedCreateInput(BaseModel):
    """The input to ``customerNeedCreate``.

    The customer is named by UUID or by the id it carries in an external system;
    the request itself attaches to an issue, a project, or neither.
    """

    customer_id: Optional[str] = Field(
        None, description="The ID of the customer this need belongs to."
    )
    customer_external_id: Optional[str] = Field(
        None, description="The external ID of the customer this need belongs to."
    )
    body: Optional[str] = Field(None, description="The content of the need in markdown format.")
    issue_id: Optional[str] = Field(
        None, description="The ID of the issue this need is attached to."
    )
    project_id: Optional[str] = Field(
        None, description="The ID of the project this need is attached to."
    )
    attachment_id: Optional[str] = Field(
        None, description="The ID of the attachment this need is associated with."
    )
    attachment_url: Optional[str] = Field(
        None, description="The URL of the attachment this need is associated with."
    )
    comment_id: Optional[str] = Field(
        None, description="The ID of the comment this need is associated with."
    )
    priority: Optional[float] = Field(None, description="The priority of the need.")
    created_at: Optional[str] = Field(
        None,
        description=(
            "The time at which the customer need was created (e.g. if importing "
            "from another system). Must be a time in the past. If none is "
            "provided, the backend will generate the time as now."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "The identifier in UUID v4 format. If none is provided, the backend will generate one."
        ),
    )

    @model_validator(mode="after")
    def _one_way_of_naming_the_customer(self) -> CustomerNeedCreateInput:
        if self.customer_id is not None and self.customer_external_id is not None:
            raise ValueError(
                "Name the customer by `customer_id` or by `customer_external_id`, not both."
            )
        return self


class CustomerNeedCreateVariables(BaseModel):
    """Variables for the ``customerNeedCreate`` mutation."""

    input: CustomerNeedCreateInput = Field(..., description="The request to record.")


class CustomerNeedCreateRequest(BaseModel):
    """Record a customer request."""

    variables: Annotated[
        CustomerNeedCreateVariables,
        Field(..., description="The request to record."),
        Body(envelop=True),
    ]


class CustomerNeedUpdateInput(BaseModel):
    """The fields ``customerNeedUpdate`` changes. All optional."""

    body: Optional[str] = Field(None, description="The content of the need in markdown format.")
    issue_id: Optional[str] = Field(
        None, description="The ID of the issue this need is attached to."
    )
    project_id: Optional[str] = Field(
        None, description="The ID of the project this need is attached to."
    )
    priority: Optional[float] = Field(None, description="The priority of the need.")
    customer_id: Optional[str] = Field(
        None,
        description=(
            "The UUID of the customer to reassign this need to. Cannot be used "
            "together with customerExternalId."
        ),
    )
    customer_external_id: Optional[str] = Field(
        None,
        description=(
            "The external system ID of the customer to reassign this need to. "
            "Cannot be used together with customerId."
        ),
    )
    attachment_url: Optional[str] = Field(
        None,
        description=(
            "A URL to create a new attachment from and set as the source for this "
            "customer need. Replaces any existing manually-added attachment."
        ),
    )
    apply_priority_to_related_needs: Optional[bool] = Field(
        None,
        description=(
            "When true and priority is also set, applies the same priority update "
            "to all other needs from the same customer on the same issue or project."
        ),
    )
    id: Optional[str] = Field(
        None,
        description=(
            "An optional identifier in UUID v4 format. If provided, will be set "
            "as the customer need's ID."
        ),
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> CustomerNeedUpdateInput:
        named = self.model_dump(exclude_none=True)
        if not named:
            raise ValueError("customerNeedUpdate needs at least one field to change.")
        if "customer_id" in named and "customer_external_id" in named:
            raise ValueError(
                "Name the customer by `customer_id` or by `customer_external_id`, not both."
            )
        return self


class CustomerNeedUpdateVariables(BaseModel):
    """Variables for the ``customerNeedUpdate`` mutation."""

    id: str = Field(..., description="The request's UUID.")
    input: CustomerNeedUpdateInput = Field(..., description="The fields to change.")


class CustomerNeedUpdateRequest(BaseModel):
    """Update a customer request."""

    variables: Annotated[
        CustomerNeedUpdateVariables,
        Field(..., description="The request to update."),
        Body(envelop=True),
    ]


class CustomerNeedDeleteVariables(BaseModel):
    """Variables for the ``customerNeedDelete`` mutation."""

    id: str = Field(..., description="The request's UUID.")


class CustomerNeedDeleteRequest(BaseModel):
    """Delete a customer request."""

    variables: Annotated[
        CustomerNeedDeleteVariables,
        Field(..., description="The request to delete."),
        Body(envelop=True),
    ]


class CustomerStatusesListRequest(BaseModel):
    """List the statuses a customer can be in."""

    variables: Annotated[
        PageVariables,
        Field(default_factory=PageVariables, description="Paging."),
        Body(envelop=True),
    ]


class CustomerTiersListRequest(BaseModel):
    """List the tiers a customer can be assigned to."""

    variables: Annotated[
        PageVariables,
        Field(default_factory=PageVariables, description="Paging."),
        Body(envelop=True),
    ]
