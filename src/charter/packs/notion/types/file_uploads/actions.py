"""
Request schemas for Notion's file upload endpoints.

A file becomes Notion-hosted content in three steps: create an upload, put the
bytes in it, then reference the upload's ID from a page, block or property.

The middle step is ``POST /v1/file_uploads/{id}/send``, which takes
``multipart/form-data`` with the raw bytes. Charter's wire contract encodes JSON
and form bodies, not multipart, so that one endpoint is not a tool here — and a
model filling in arguments has no bytes to give it anyway. What *does* work end
to end from this pack is ``mode="external_url"``: Notion fetches the file from a
public URL itself, and there is no send step at all.

API Reference: https://developers.notion.com/reference/file-upload
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.common import PaginatedQuery
from charter.types import Body, Path, Query

__all__ = [
    "FileUploadsCreateRequest",
    "FileUploadsCompleteRequest",
    "FileUploadsRetrieveRequest",
    "FileUploadsListRequest",
]

FILE_UPLOAD_ID = "The ID of the file upload."


class FileUploadCreateBody(BaseModel):
    """The body of a create-file-upload request.

    Which fields are required depends on ``mode``:

    * ``single_part`` (the default) — nothing else is required. The bytes are
      sent afterwards.
    * ``multi_part`` — for files over 20 MiB; needs ``filename`` and
      ``number_of_parts``.
    * ``external_url`` — needs ``filename`` and ``external_url``, and Notion
      fetches the file itself.

    API Reference: https://developers.notion.com/reference/create-a-file-upload
    """

    mode: Optional[Literal["single_part", "multi_part", "external_url"]] = Field(
        default=None,
        description=(
            "How the file arrives. `single_part` when absent: the bytes are sent in "
            "one follow-up request. `multi_part` for files over 20 MiB. "
            "`external_url` imports from a public HTTPS URL with no upload step."
        ),
    )
    filename: Optional[str] = Field(
        default=None,
        description=(
            "The name of the file. Required for `multi_part` and `external_url`. "
            "Include an extension, or give `content_type` so one can be inferred."
        ),
    )
    content_type: Optional[str] = Field(
        default=None,
        description=(
            "The MIME type of the file. It must match the bytes and any extension "
            "on `filename`."
        ),
    )
    number_of_parts: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description=(
            "How many parts a `multi_part` upload is split into. It must match the "
            "number of parts actually sent."
        ),
    )
    external_url: Optional[str] = Field(
        default=None,
        description=(
            "A public HTTPS URL for Notion to import. Required for an `external_url` "
            "upload."
        ),
    )

    @model_validator(mode="after")
    def _mode_is_satisfied(self):
        if self.mode == "external_url":
            missing = [
                n for n in ("filename", "external_url") if getattr(self, n) is None
            ]
            if missing:
                raise ValueError(
                    f"mode='external_url' needs {' and '.join(missing)}"
                )
        if self.mode == "multi_part":
            missing = [
                n for n in ("filename", "number_of_parts") if getattr(self, n) is None
            ]
            if missing:
                raise ValueError(f"mode='multi_part' needs {' and '.join(missing)}")
        if self.external_url is not None and self.mode != "external_url":
            raise ValueError("`external_url` is only read when mode is 'external_url'")
        if self.number_of_parts is not None and self.mode != "multi_part":
            raise ValueError("`number_of_parts` is only read when mode is 'multi_part'")
        return self


class FileUploadsCreateRequest(BaseModel):
    """Start a file upload.

    API Reference: https://developers.notion.com/reference/create-a-file-upload
    """

    body: Annotated[
        FileUploadCreateBody,
        Field(
            default_factory=FileUploadCreateBody,
            description="How the file will arrive. All fields optional for a single-part upload.",
        ),
        Body(),
    ]


class FileUploadsCompleteRequest(BaseModel):
    """Finish a multi-part upload, once every part has been sent.

    Only multi-part uploads need this. A single-part upload is complete when its
    bytes land, and an `external_url` import completes on its own.

    API Reference: https://developers.notion.com/reference/complete-a-file-upload
    """

    file_upload_id: Annotated[str, Field(..., description=FILE_UPLOAD_ID), Path()]


class FileUploadsRetrieveRequest(BaseModel):
    """Retrieve a file upload, including its status.

    Worth polling after an `external_url` import: the upload is only attachable
    once its status is `uploaded`.

    API Reference: https://developers.notion.com/reference/retrieve-a-file-upload
    """

    file_upload_id: Annotated[str, Field(..., description=FILE_UPLOAD_ID), Path()]


class FileUploadsListRequest(PaginatedQuery):
    """List the file uploads this integration has created.

    API Reference: https://developers.notion.com/reference/list-file-uploads
    """

    status: Annotated[
        Optional[Literal["pending", "uploaded", "expired", "failed"]],
        Field(
            None,
            description=(
                "Return only uploads in this state. `pending` is awaiting bytes, "
                "`uploaded` is ready to attach, `expired` was never completed in "
                "time, and `failed` is an import that did not work."
            ),
        ),
        Query(),
    ]
