# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Input schemas for the ``forms`` collection.

``forms.create`` makes an empty form from a title. ``forms.get`` reads one.
``forms.batchUpdate`` applies a list of ``Request`` oneofs atomically.
``forms.setPublishSettings`` publishes or unpublishes it.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.packs.gforms.types.forms.models import Info, PublishSettings
from charter.packs.gforms.types.forms.requests import Request, WriteControl
from charter.types import Body, FieldMask, Format, Path, Query

__all__ = [
    "FormsCreateBody",
    "FormsCreateRequest",
    "FormsGetRequest",
    "BatchUpdateFormBody",
    "FormsBatchUpdateRequest",
    "SetPublishSettingsBody",
    "FormsSetPublishSettingsRequest",
]


class FormsCreateBody(BaseModel):
    """The body of a create-form request.

    Google's reference says this body is a ``Form`` and then says, in the same
    page, that only ``info.title`` and ``info.documentTitle`` are copied to the
    new form and that "all other fields including the form description, items
    and settings are disallowed". Modelling the whole ``Form`` would advertise
    capabilities the endpoint does not have; what is modelled is what is
    honoured. To add items, create the form and then call
    ``forms_batch_update`` with the returned ``formId``.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/create
    """

    info: Info = Field(
        ...,
        description=(
            "Required. The title and description of the form. Only the title and the "
            "document title are copied to the new form."
        ),
    )


class FormsCreateRequest(BaseModel):
    """Create a new form using the title given in the provided form message in
    the request.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/create
    """

    unpublished: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Optional. Whether the form is unpublished. If set to `true`, the form "
                "doesn't accept responses. If set to `false` or unset, the form is "
                "published and accepts responses."
            ),
        ),
        Query(),
    ]
    body: Annotated[
        FormsCreateBody,
        Field(..., description="The form to create."),
        Body(),
    ]


class FormsGetRequest(BaseModel):
    """Get a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/get
    """

    form_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Required. The form ID. This is the long string in the form's edit URL, "
                "between `/d/` and `/edit`."
            ),
        ),
        Path(),
    ]


class BatchUpdateFormBody(BaseModel):
    """The body of a batch-update request.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#body.request_body
    """

    include_form_in_response: Optional[bool] = Field(
        default=None,
        description="Whether to return an updated version of the model in the response.",
    )
    requests: List[Request] = Field(
        ...,
        description=(
            "Required. The update requests of this batch. Each entry sets exactly one "
            "kind of request, and they apply in order against a form that shifts as "
            "they do: a create_item at index 2 moves every later item down, so order "
            "several insertions back-to-front, or state each location against the form "
            "as it will be by then."
        ),
    )
    write_control: Optional[WriteControl] = Field(
        default=None,
        description="Provides control over how write requests are executed.",
    )


class FormsBatchUpdateRequest(BaseModel):
    """Change the form with a batch of updates.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate
    """

    form_id: Annotated[
        str,
        Field(..., description="Required. The form ID."),
        Path(),
    ]
    body: Annotated[
        BatchUpdateFormBody,
        Field(..., description="The updates to apply."),
        Body(),
    ]


class SetPublishSettingsBody(BaseModel):
    """The body of a set-publish-settings request.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/setPublishSettings#body.request_body
    """

    publish_settings: PublishSettings = Field(
        ...,
        description="Required. The desired publish settings to apply to the form.",
    )
    update_mask: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description=(
                "Optional. The `publishSettings` fields to update. This field mask "
                "accepts the following values: `publishState`, which updates or replaces "
                'all `publishState` settings, and `"*"`, which updates or replaces all '
                "`publishSettings` fields."
            ),
        ),
    ] = None


class FormsSetPublishSettingsRequest(BaseModel):
    """Updates the publish settings of a form.

    Legacy forms aren't supported because they don't have the
    ``publishSettings`` field.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/setPublishSettings
    """

    form_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Required. The ID of the form. You can get the id from the `formId` "
                "field of the Form."
            ),
        ),
        Path(),
    ]
    body: Annotated[
        SetPublishSettingsBody,
        Field(..., description="The publish settings to apply."),
        Body(),
    ]
