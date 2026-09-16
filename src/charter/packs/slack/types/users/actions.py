"""Request schemas for Slack's `users.*` methods.

API reference: https://docs.slack.dev/reference/methods/users.list
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Query


class UsersListRequest(BaseModel):
    """Input schema for Slack `users.list`.

    Lists all users in a Slack team, including deactivated accounts.

    API Reference: https://docs.slack.dev/reference/methods/users.list
    """

    limit: Annotated[
        Optional[int],
        Field(
            100,
            ge=1,
            le=200,
            description=(
                "The maximum number of items to return. Fewer than the requested "
                "number of items may be returned, even if the end of the users list "
                "has not been reached. Providing no limit value will result in Slack "
                "attempting to deliver you the entire result set."
            ),
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Paginate through collections of data by setting this to the "
                "next_cursor attribute returned by a previous request's "
                "response_metadata."
            ),
        ),
        Query(),
    ]
    include_locale: Annotated[
        Optional[bool],
        Field(
            None,
            description="Set this to true to receive the locale for users. Defaults to false.",
        ),
        Query(),
    ]
    team_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Encoded team id to list users in. Required if the token belongs to "
                "an org-wide app."
            ),
        ),
        Query(),
    ]


class UsersInfoRequest(BaseModel):
    """Input schema for Slack `users.info`.

    Gets information about a user.

    API Reference: https://docs.slack.dev/reference/methods/users.info
    """

    user: Annotated[
        str,
        Field(..., description="User to get info on, e.g. 'W1234567890'."),
        Query(),
    ]
    include_locale: Annotated[
        Optional[bool],
        Field(
            None,
            description="Set this to true to receive the locale for this user. Defaults to false.",
        ),
        Query(),
    ]
