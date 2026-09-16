"""
What the ``forms`` collection sends back.

Charter models requests, and these are here for the same reason the Sheets pack
carries its reply union: the shapes a caller reads off a ``batchUpdate`` are
part of the endpoint's contract, and a pack that documents only half of it
leaves the caller guessing where the new item's ID arrived.

Nothing here is a tool's ``args_schema``, so none of it reaches a model's
context window.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from charter.packs.gforms.types.forms.models import Form, PublishSettings
from charter.packs.gforms.types.forms.requests import WriteControl

__all__ = [
    "CreateItemResponse",
    "Response",
    "BatchUpdateFormResponse",
    "SetPublishSettingsResponse",
]


class CreateItemResponse(BaseModel):
    """The result of creating an item.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#CreateItemResponse
    """

    item_id: Optional[str] = Field(
        default=None,
        description="The ID of the created item.",
    )
    question_id: Optional[List[str]] = Field(
        default=None,
        description=(
            "The ID of the question created as part of this item, for a question group "
            "it lists IDs of all the questions created for this item."
        ),
    )


class Response(BaseModel):
    """A single response from an update.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#Response
    """

    create_item: Optional[CreateItemResponse] = Field(
        default=None,
        description="The result of creating an item.",
    )


class BatchUpdateFormResponse(BaseModel):
    """Response to a BatchUpdateFormRequest.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#body.BatchUpdateFormResponse
    """

    form: Optional[Form] = Field(
        default=None,
        description=(
            "Based on the bool request field `includeFormInResponse`, a form with all "
            "applied mutations/updates is returned or not. This may be later than the "
            "revision ID created by these changes."
        ),
    )
    replies: Optional[List[Response]] = Field(
        default=None,
        description=(
            "The reply of the updates. This maps 1:1 with the update requests, although "
            "replies to some requests may be empty."
        ),
    )
    write_control: Optional[WriteControl] = Field(
        default=None,
        description="The updated write control after applying the request.",
    )


class SetPublishSettingsResponse(BaseModel):
    """The response of a SetPublishSettings request.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/setPublishSettings#body.SetPublishSettingsResponse
    """

    form_id: str = Field(
        ...,
        description=(
            "Required. The ID of the Form. This is same as the `formId` field of the "
            "Form."
        ),
    )
    publish_settings: Optional[PublishSettings] = Field(
        default=None,
        description="The publish settings of the form.",
    )
