"""Request schemas for Linear's full-text search.

Three searches, one shape: a ``term``, an optional team to scope to, and a flag
for whether comment text counts as a match. They return search *payloads* rather
than plain connections, but the payload still carries ``pageInfo``, so the
pack's declared cursor works unchanged.

``issueSearch`` is the older spelling of ``searchIssues`` and is still live in
the schema; ``searchIssues`` is the one modelled here.

API Reference: https://linear.app/developers/graphql
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.packs.linear.types.common import PageVariables, PaginationOrderBy
from charter.packs.linear.types.filters import IssueFilter
from charter.types import Body

__all__ = [
    "SearchIssuesRequest",
    "SearchProjectsRequest",
    "SearchDocumentsRequest",
]


class _SearchVariables(PageVariables):
    """The arguments every Linear search shares."""

    term: str = Field(..., description="The text to search for.")
    team_id: Optional[str] = Field(
        None, description="Restrict the search to one team's items, by UUID."
    )
    include_comments: Optional[bool] = Field(
        None,
        description="Search comment text as well as titles and descriptions.",
    )
    include_archived: Optional[bool] = Field(
        None, description="Include archived items in the results."
    )
    order_by: Optional[PaginationOrderBy] = Field(
        None, description="Sort by 'createdAt' or 'updatedAt'."
    )


class SearchIssuesVariables(_SearchVariables):
    """Variables for ``searchIssues``."""

    filter: Optional[IssueFilter] = Field(
        None, description="Narrow the search further, on top of the text match."
    )


class SearchIssuesRequest(BaseModel):
    """Search issues by text."""

    variables: Annotated[
        SearchIssuesVariables,
        Field(..., description="What to search for."),
        Body(envelop=True),
    ]


class SearchProjectsVariables(_SearchVariables):
    """Variables for ``searchProjects``."""


class SearchProjectsRequest(BaseModel):
    """Search projects by text."""

    variables: Annotated[
        SearchProjectsVariables,
        Field(..., description="What to search for."),
        Body(envelop=True),
    ]


class SearchDocumentsVariables(_SearchVariables):
    """Variables for ``searchDocuments``."""


class SearchDocumentsRequest(BaseModel):
    """Search documents by text."""

    variables: Annotated[
        SearchDocumentsVariables,
        Field(..., description="What to search for."),
        Body(envelop=True),
    ]
