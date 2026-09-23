# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The ``batchUpdate`` request union — every change Google Forms can apply.

``forms.batchUpdate`` takes a list of ``Request`` objects, each of which is a
*oneof*: exactly one of six kinds of update must be set, and setting two is an
error the API reports as a 400 with no useful detail. That constraint is a
``model_validator`` on ``Request``, and on ``Location``, whose ``where`` union
is required.

Six members is the whole union, which is what makes this pack cheap where the
Docs and Sheets ones are expensive: the breadth of the Forms API is in the
``Item`` a ``createItem`` carries, not in the number of edits.

API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from charter.execution.schema import partial_of
from charter.packs.gforms.types.forms.models import FormSettings, Info, Item
from charter.types import ConflictsWith, FieldMask, Format

__all__ = [
    "Location",
    "UpdateFormInfo",
    "UpdateFormInfoRequest",
    "UpdateSettingsRequest",
    "CreateItemRequest",
    "MoveItemRequest",
    "DeleteItemRequest",
    "UpdateItemRequest",
    "WriteControl",
    "Request",
]

_REQUEST_KINDS = (
    "update_form_info",
    "update_settings",
    "create_item",
    "move_item",
    "delete_item",
    "update_item",
)


class Location(BaseModel):
    """A specific location in a form.

    ``index`` is the sole member of the required ``where`` union, so it is
    declared optional and required by the validator rather than by the
    annotation — the shape stays right if Google adds a second way to name a
    place in a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#Location
    """

    index: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "The index of an item in the form. This must be in the range `[0..N)`, "
            "where N is the number of items in the form."
        ),
    )

    @model_validator(mode="after")
    def _exactly_one_where(self) -> Location:
        if self.index is None:
            raise ValueError("Location requires its `where` union: set `index`.")
        return self


# `Info.title` is Required on the resource and is not required to update the
# description beside it: the update mask decides what changes, so mandating a
# title here would mean reading the form just to echo its own title back.
# Derived rather than hand-written, so the descriptions and the modes keep one
# home — see `partial_of` in the SDK docs.
UpdateFormInfo = partial_of(Info, name="UpdateFormInfo")


class UpdateFormInfoRequest(BaseModel):
    """Update Form's Info.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#UpdateFormInfoRequest
    """

    info: Optional[UpdateFormInfo] = Field(  # type: ignore[valid-type]
        default=None,
        description="The info to update.",
    )
    update_mask: Annotated[
        FieldMask,
        Format("field_mask"),
        Field(
            ...,
            description=(
                "Required. Only values named in this mask are changed. At least one "
                "field must be specified. The root `info` is implied and should not be "
                'specified. A single `"*"` can be used as short-hand for updating '
                "every field."
            ),
        ),
    ]


class UpdateSettingsRequest(BaseModel):
    """Update Form's ``FormSettings``.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#UpdateSettingsRequest
    """

    settings: FormSettings = Field(
        ...,
        description="Required. The settings to update with.",
    )
    update_mask: Annotated[
        FieldMask,
        Format("field_mask"),
        Field(
            ...,
            description=(
                "Required. Only values named in this mask are changed. At least one "
                "field must be specified. The root `settings` is implied and should not "
                'be specified. A single `"*"` can be used as short-hand for updating '
                "every field."
            ),
        ),
    ]


class CreateItemRequest(BaseModel):
    """Create an item in a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#CreateItemRequest
    """

    item: Item = Field(
        ...,
        description="Required. The item to create.",
    )
    location: Location = Field(
        ...,
        description="Required. Where to place the new item.",
    )


class MoveItemRequest(BaseModel):
    """Move an item in a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#MoveItemRequest
    """

    original_location: Location = Field(
        ...,
        description="Required. The location of the item to move.",
    )
    new_location: Location = Field(
        ...,
        description="Required. The new location for the item.",
    )


class DeleteItemRequest(BaseModel):
    """Delete an item in a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#DeleteItemRequest
    """

    location: Location = Field(
        ...,
        description="Required. The location of the item to delete.",
    )


class UpdateItemRequest(BaseModel):
    """Update an item in a form.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#UpdateItemRequest
    """

    item: Item = Field(
        ...,
        description=(
            "Required. New values for the item. Note that item and question IDs are "
            "used if they are provided (and are in the field mask). If an ID is blank "
            "(and in the field mask) a new ID is generated. This means you can modify "
            "an item by getting the form via `forms.get`, modifying your local copy of "
            "that item to be how you want it, and using `UpdateItemRequest` to write it "
            "back, with the IDs being the same (or not in the field mask)."
        ),
    )
    location: Location = Field(
        ...,
        description="Required. The location identifying the item to update.",
    )
    update_mask: Annotated[
        FieldMask,
        Format("field_mask"),
        Field(
            ...,
            description=(
                "Required. Only values named in this mask are changed. This is a "
                "comma-separated list of fully qualified names of fields. Example: "
                '`"user.displayName,photo"`.'
            ),
        ),
    ]


class WriteControl(BaseModel):
    """Provides control over how write requests are executed.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#WriteControl
    """

    required_revision_id: Optional[str] = Field(
        default=None,
        description=(
            "The revision ID of the form that the write request is applied to. If this "
            "is not the latest revision of the form, the request is not processed and "
            "returns a 400 bad request error."
        ),
    )
    target_revision_id: Annotated[
        Optional[str],
        Field(
            default=None,
            description=(
                "The target revision ID of the form that the write request is applied "
                "to. If changes have occurred after this revision, the changes in this "
                "update request are transformed against those changes. This results in "
                "a new revision of the form that incorporates both the changes in the "
                "request and the intervening changes, with the server resolving "
                "conflicting changes. The target revision ID may only be used to write "
                "to recent versions of a form. If the target revision is too far behind "
                "the latest revision, the request is not processed and returns a 400 "
                "(Bad Request Error). The request may be retried after reading the "
                "latest version of the form. In most cases a target revision ID remains "
                "valid for several minutes after it is read, but for frequently-edited "
                "forms this window may be shorter."
            ),
        ),
        ConflictsWith(
            "required_revision_id",
            reason=(
                "`control` is a oneof: requiredRevisionId refuses the write if the "
                "form moved on, targetRevisionId rebases it. Send one."
            ),
        ),
    ] = None


class Request(BaseModel):
    """The kinds of update requests that can be made.

    API Reference: https://developers.google.com/workspace/forms/api/reference/rest/v1/forms/batchUpdate#Request
    """

    update_form_info: Optional[UpdateFormInfoRequest] = Field(
        default=None,
        description="Update Form's Info.",
    )
    update_settings: Optional[UpdateSettingsRequest] = Field(
        default=None,
        description="Updates the Form's settings.",
    )
    create_item: Optional[CreateItemRequest] = Field(
        default=None,
        description="Create a new item.",
    )
    move_item: Optional[MoveItemRequest] = Field(
        default=None,
        description="Move an item to a specified location.",
    )
    delete_item: Optional[DeleteItemRequest] = Field(
        default=None,
        description="Delete an item.",
    )
    update_item: Optional[UpdateItemRequest] = Field(
        default=None,
        description="Update an item.",
    )

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> Request:
        provided = [name for name in _REQUEST_KINDS if getattr(self, name) is not None]
        if len(provided) != 1:
            raise ValueError(f"Exactly one request kind must be set, found: {provided}")
        return self

    model_config = ConfigDict(extra="forbid")
