# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

from ..message.models import Message  # Re-use Message definition


class ListDraftsResponse(BaseModel):
    """
    Response model for users.drafts.list.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/list
    """

    drafts: Annotated[
        Optional[List[Draft]],
        Field(
            None,
            description=(
                "List of drafts. Note that the Message property in each Draft resource only contains "
                "an id and a threadId. The messages.get method can fetch additional message details."
            ),
        ),
        Mode("response_only"),
    ]
    next_page_token: Annotated[
        Optional[str],
        Field(None, description="Token to retrieve the next page of results in the list."),
        Mode("response_only"),
    ]
    result_size_estimate: Annotated[
        Optional[int],
        Field(None, description="Estimated total number of results."),
        Mode("response_only"),
    ]


class Draft(BaseModel):
    """Gmail draft resource.

    API: https://developers.google.com/gmail/api/reference/rest/v1/users.drafts#Draft
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The immutable ID of the draft."),
        Mode("response_only"),
    ]
    message: Message = Field(..., description="The message content of the draft.")


ListDraftsResponse.model_rebuild()
