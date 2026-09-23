# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Slack's `search.*` methods.

API reference: https://docs.slack.dev/reference/methods/search.messages
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Query

SearchSort = Literal["score", "timestamp"]
SearchSortDir = Literal["asc", "desc"]


class SearchMessagesRequest(BaseModel):
    """Input schema for Slack `search.messages`.

    Searches for messages matching a query. Requires a **user** token with the
    `search:read` scope — bot tokens cannot call this method.

    API Reference: https://docs.slack.dev/reference/methods/search.messages
    """

    query: Annotated[
        str,
        Field(
            ...,
            description=(
                "Search query. Supports Slack's search modifiers, e.g. "
                "'in:#engineering from:@ada after:2026-01-01'."
            ),
        ),
        Query(),
    ]
    count: Annotated[
        Optional[int],
        Field(
            20,
            ge=1,
            le=100,
            description="Number of items to return per page. Maximum of 100.",
        ),
        Query(),
    ]
    page: Annotated[
        Optional[int],
        Field(1, ge=1, le=100, description="Page number of results to return."),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Use this when getting results with cursormark pagination. Set to '*' "
                "for the first call and use the value of next_cursor thereafter."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[SearchSort],
        Field(None, description="Return matches sorted by either 'score' or 'timestamp'."),
        Query(),
    ]
    sort_dir: Annotated[
        Optional[SearchSortDir],
        Field(
            None, description="Change sort direction to ascending ('asc') or descending ('desc')."
        ),
        Query(),
    ]
    highlight: Annotated[
        Optional[bool],
        Field(None, description="Pass a value to enable query highlight markers."),
        Query(),
    ]
    team_id: Annotated[
        Optional[str],
        Field(
            None,
            description="Encoded team id to search in. Required if the token belongs to an org-wide app.",
        ),
        Query(),
    ]
