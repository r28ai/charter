# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Input schemas for the ``forms.responses`` collection.

Both endpoints are reads. ``forms.responses.get`` fetches one response by ID;
``forms.responses.list`` walks them, filtered by submission time.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Gloss, Path, Query

__all__ = [
    "FormsResponsesGetRequest",
    "FormsResponsesListRequest",
]


class FormsResponsesGetRequest(BaseModel):
    """Get one response from the form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses/get
    """

    form_id: Annotated[
        str,
        Field(..., description="Required. The form ID."),
        Path(),
    ]
    response_id: Annotated[
        str,
        Field(..., description="Required. The response ID within the form."),
        Path(),
    ]


class FormsResponsesListRequest(BaseModel):
    """List a form's responses.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms.responses/list
    """

    form_id: Annotated[
        str,
        Field(..., description="Required. ID of the Form whose responses to list."),
        Path(),
    ]
    filter: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Which form responses to return. Currently, the only supported filters "
                "are: `timestamp > N` which means to get all form responses submitted "
                "after (but not at) timestamp N, and `timestamp >= N` which means to get "
                "all form responses submitted at and after timestamp N. For both "
                'supported filters, timestamp must be formatted in RFC3339 UTC "Zulu" '
                'format. Examples: "2014-10-02T15:01:23Z" and '
                '"2014-10-02T15:01:23.045123456Z".'
            ),
        ),
        Query(),
        Gloss(
            "The whole filter is one string, operator included: "
            "'timestamp >= 2014-10-02T15:01:23Z'. There is no other filterable "
            "field — a question, an email or a score cannot be filtered here."
        ),
    ]
    page_size: Annotated[
        Optional[int],
        Field(
            None,
            description=(
                "The maximum number of responses to return. The service may return fewer "
                "than this value. If unspecified or zero, at most 5000 responses are "
                "returned."
            ),
        ),
        Query(),
    ]
    page_token: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A page token returned by a previous list response. If this field is "
                "set, the form and the values of the filter must be the same as for the "
                "original request."
            ),
        ),
        Query(),
    ]
