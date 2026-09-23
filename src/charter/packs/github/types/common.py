# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Shared request pieces for the GitHub pack.

GitHub gives every list endpoint the same two pagination parameters, and every
repository-scoped endpoint the same two path parameters, so both are declared
once here rather than repeated on a dozen schemas.

API Reference: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Path, Query

__all__ = ["GitHubListRequest", "RepoRequest", "SortDirection"]


SortDirection = Literal["asc", "desc"]
"""The order a sorted list comes back in. GitHub spells it ``direction`` on the
REST list endpoints and ``order`` on the search endpoints."""


class GitHubListRequest(BaseModel):
    """The pagination parameters every GitHub list endpoint accepts.

    GitHub pages by number, not by cursor: you ask for page 1, 2, 3 and stop
    when a page comes back with fewer items than ``per_page``. The ``next`` link
    it also sends lives in the ``Link`` response header, which is why the page
    number is the marker Charter declares — see :data:`~charter.packs.github.GITHUB_PAGINATION`.

    API Reference: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
    """

    per_page: Annotated[
        Optional[int],
        Field(
            30,
            ge=1,
            le=100,
            description="The number of results per page (max 100). Defaults to 30.",
        ),
        Query(),
    ]
    page: Annotated[
        Optional[int],
        Field(
            1,
            ge=1,
            description="The page number of the results to fetch. Defaults to 1.",
        ),
        Query(),
    ]


class RepoRequest(BaseModel):
    """The two path parameters every repository-scoped endpoint takes.

    API Reference: https://docs.github.com/en/rest/repos/repos
    """

    owner: Annotated[
        str,
        Field(
            ...,
            description=("The account owner of the repository. The name is not case sensitive."),
        ),
        Path(),
    ]
    repo: Annotated[
        str,
        Field(
            ...,
            description=(
                "The name of the repository without the `.git` extension. The name is "
                "not case sensitive."
            ),
        ),
        Path(),
    ]
