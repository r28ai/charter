"""
Resources shared across Drive collections.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/User
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Mode


class User(BaseModel):
    """
    Information about a Drive user.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/User
    """

    display_name: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. A plain text displayable name for this user.",
        ),
        Mode("response_only"),
    ] = None
    kind: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Identifies what kind of resource this is. Value: the "
                "fixed string `drive#user`."
            ),
        ),
        Mode("response_only"),
    ] = None
    me: Annotated[
        Optional[bool],
        Field(None, description="Output only. Whether this user is the requesting user."),
        Mode("response_only"),
    ] = None
    permission_id: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. The user's ID as visible in Permission resources.",
        ),
        Mode("response_only"),
    ] = None
    email_address: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The email address of the user. This may not be present "
                "in certain contexts if the user has not made their email address "
                "visible to the requester."
            ),
        ),
        Mode("response_only"),
    ] = None
    photo_link: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. A link to the user's profile photo, if available.",
        ),
        Mode("response_only"),
    ] = None
