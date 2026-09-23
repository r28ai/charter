# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Linear's cycle operations.

A cycle is a team's time-box — Linear's name for a sprint. Cycles are created by
the team's own cadence settings rather than by hand: ``cycleCreate`` exists in
the API but Linear has deprecated it, so it is deliberately not a tool here.
What is left is reading cycles, editing the ones that exist, and the two
schedule operations.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import CycleFilter
from charter.types import Body

__all__ = [
    "CyclesListRequest",
    "CycleGetRequest",
    "CycleUpdateRequest",
    "CycleArchiveRequest",
    "CycleStartUpcomingCycleTodayRequest",
]


class CyclesListVariables(PageVariables):
    """Variables for the ``cycles`` connection."""

    filter: Optional[CycleFilter] = Field(
        default=None,
        description=(
            "Narrow the cycles returned. Filter on `is_active.eq` for a team's current cycle."
        ),
    )
    include_archived: Optional[bool] = Field(
        default=None, description="Include archived cycles in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        default=None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class CyclesListRequest(BaseModel):
    """List cycles."""

    variables: Annotated[
        CyclesListVariables,
        Field(default_factory=CyclesListVariables, description="Paging and filtering."),
        Body(envelop=True),
    ]


class CycleGetVariables(BaseModel):
    """Variables for the ``cycle`` query."""

    id: str = Field(..., description="The cycle's UUID.")


class CycleGetRequest(BaseModel):
    """Get one cycle."""

    variables: Annotated[
        CycleGetVariables,
        Field(..., description="Which cycle to fetch."),
        Body(envelop=True),
    ]


class CycleUpdateInput(BaseModel):
    """The fields ``cycleUpdate`` changes. All optional."""

    name: Optional[str] = Field(None, description="The custom name of the cycle.")
    description: Optional[str] = Field(None, description="The cycle description.")
    starts_at: Optional[str] = Field(
        None, description="The start date of the cycle, as an ISO 8601 timestamp."
    )
    ends_at: Optional[str] = Field(
        None, description="The end date of the cycle, as an ISO 8601 timestamp."
    )
    completed_at: Optional[str] = Field(
        None,
        description="The completion time of the cycle, as an ISO 8601 timestamp.",
    )

    @model_validator(mode="after")
    def _at_least_one_change(self) -> CycleUpdateInput:
        if not self.model_dump(exclude_none=True):
            raise ValueError("cycleUpdate needs at least one field to change.")
        return self


class CycleUpdateVariables(BaseModel):
    """Variables for the ``cycleUpdate`` mutation."""

    id: str = Field(..., description="The cycle's UUID.")
    input: CycleUpdateInput = Field(..., description="The fields to change.")


class CycleUpdateRequest(BaseModel):
    """Update a cycle."""

    variables: Annotated[
        CycleUpdateVariables,
        Field(..., description="The cycle to update."),
        Body(envelop=True),
    ]


class CycleArchiveVariables(BaseModel):
    """Variables for the ``cycleArchive`` mutation."""

    id: str = Field(..., description="The cycle's UUID.")


class CycleArchiveRequest(BaseModel):
    """Archive a cycle."""

    variables: Annotated[
        CycleArchiveVariables,
        Field(..., description="The cycle to archive."),
        Body(envelop=True),
    ]


class CycleStartUpcomingCycleTodayVariables(BaseModel):
    """Variables for the ``cycleStartUpcomingCycleToday`` mutation."""

    id: str = Field(..., description="The UUID of the upcoming cycle to start today.")


class CycleStartUpcomingCycleTodayRequest(BaseModel):
    """Start a team's next cycle today rather than on its scheduled date."""

    variables: Annotated[
        CycleStartUpcomingCycleTodayVariables,
        Field(..., description="The cycle to start."),
        Body(envelop=True),
    ]
