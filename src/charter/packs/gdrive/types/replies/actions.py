# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the Replies collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from charter.execution.schema import partial_of
from charter.types import Body, Path

from .._shared import FILE_ID
from ..comments.actions import COMMENT_ID
from ..comments.models import Reply

REPLY_ID = "The ID of the reply."


class RepliesCreateRequest(BaseModel):
    """
    Creates a reply to a comment.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies/create
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
    reply: Annotated[
        Reply,
        Field(..., description="The reply to create."),
        Body(),
    ]

    @model_validator(mode="after")
    def _content_or_action(self) -> RepliesCreateRequest:
        """`content` is required by the create method if no `action` value is specified."""
        if self.reply.content is None and self.reply.action is None:
            raise ValueError(
                "content is required by the create method if no action value is specified."
            )
        return self


PatchReply = partial_of(
    Reply,
    name="PatchReply",
    doc="""Request body for Drive `replies.update`.

    Create requires `content` unless `action` is set; patch leaves out what it
    is not changing, so it needs nothing. Derived rather than written out, so
    the field descriptions have one home.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies/update
    """,
)


class RepliesUpdateRequest(BaseModel):
    """
    Updates a reply with patch semantics.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies/update
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
    reply_id: Annotated[str, Field(..., description=REPLY_ID), Path()]
    reply: Annotated[
        PatchReply,  # type: ignore[valid-type]
        Field(
            ...,
            description=(
                "The reply resource. Only populate fields you want to modify; typically `content`."
            ),
        ),
        Body(),
    ]


class RepliesDeleteRequest(BaseModel):
    """
    Deletes a reply.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/replies/delete
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    comment_id: Annotated[str, Field(..., description=COMMENT_ID), Path()]
    reply_id: Annotated[str, Field(..., description=REPLY_ID), Path()]
