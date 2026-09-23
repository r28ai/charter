# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated

from pydantic import BaseModel, Field

from charter import partial_of
from charter.types import Body, Path

from .._common import USER_ID_DESCRIPTION
from .models import Label


class LabelsListRequest(BaseModel):
    """Input schema for Gmail `users.labels.list` endpoint.

    Lists all labels in the user's mailbox.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/list
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]


class LabelsGetRequest(BaseModel):
    """Input schema for Gmail `users.labels.get` endpoint.

    Gets the specified label.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/get
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(..., description="The ID of the label to retrieve."),
        Path(),
    ]


class LabelsCreateRequest(BaseModel):
    """Input schema for Gmail `users.labels.create` endpoint.

    Creates a new label.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/create
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]

    body: Annotated[
        Label,
        Field(..., description="The label to create."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


PatchLabelRequest = partial_of(
    Label,
    name="PatchLabelRequest",
    doc="""Request body for Gmail `users.labels.patch`.

    Both patch and update document their body as a Label, and the difference
    between them is what an absent field means: update replaces the label, so it
    needs the name; patch leaves out what it is not changing, so it needs
    nothing. Using Label itself here would make `name` required on the one
    endpoint whose point is not having to send it.

    Derived rather than written out, so the field descriptions have one home.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/patch
    """,
)


class LabelsUpdateRequest(BaseModel):
    """Input schema for Gmail `users.labels.update` endpoint.

    Updates the specified label. The label is replaced by what is sent, so send
    the label you want to end up with rather than the part that changed. Use
    `labels_patch` to change one field on its own.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/update
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(..., description="The ID of the label to update."),
        Path(),
    ]

    body: Annotated[
        Label,
        Field(..., description="The label's replacement content."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class LabelsPatchRequest(BaseModel):
    """Input schema for Gmail `users.labels.patch` endpoint.

    Patch the specified label. Fields left out keep the value they have.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/patch
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(..., description="The ID of the label to update."),
        Path(),
    ]

    body: Annotated[
        # A model built at runtime, so a static checker cannot follow it into a
        # type expression. Pydantic resolves it at class-construction time.
        # charter.execution.schema records why this is accepted and the
        # `relaxed()` shape that would avoid it.
        PatchLabelRequest,  # type: ignore[valid-type]
        Field(..., description="The fields to change on the label."),
        Body(),
    ]

    model_config = {
        "validate_assignment": True,
        "extra": "forbid",
    }


class LabelsDeleteRequest(BaseModel):
    """Input schema for Gmail `users.labels.delete` endpoint.

    Immediately and permanently deletes the specified label and removes it from
    any messages and threads that it's applied to.

    API Reference: https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/delete
    """

    userId: Annotated[
        str,
        Field(
            "me",
            description=USER_ID_DESCRIPTION,
        ),
        Path(),
    ]
    id: Annotated[
        str,
        Field(..., description="The ID of the label to delete."),
        Path(),
    ]
