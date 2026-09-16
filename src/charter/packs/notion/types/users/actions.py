"""
Request schemas for Notion's user endpoints.

Users are read-only through the API: there is no endpoint that creates or
changes one.

API Reference: https://developers.notion.com/reference/user
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from charter.packs.notion.types.common import PaginatedQuery
from charter.types import Path

__all__ = ["UsersListRequest", "UsersRetrieveRequest", "UsersRetrieveMeRequest"]


class UsersListRequest(PaginatedQuery):
    """List the users in the workspace.

    Guests are not included, and the API offers no way to filter by name or
    email. A personal access token cannot call this.

    API Reference: https://developers.notion.com/reference/get-users
    """


class UsersRetrieveRequest(BaseModel):
    """Retrieve a user by ID.

    API Reference: https://developers.notion.com/reference/get-user
    """

    user_id: Annotated[
        str, Field(..., description="The ID of the user to retrieve."), Path()
    ]


class UsersRetrieveMeRequest(BaseModel):
    """Retrieve the bot the token authenticates as.

    Answers with the bot user for an integration token, including its owner and
    workspace, and with the person who created it for a personal access token.
    The cheapest way to check that a credential works.

    API Reference: https://developers.notion.com/reference/get-self
    """
