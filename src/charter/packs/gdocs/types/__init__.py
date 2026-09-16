"""Request schemas for the Google Docs pack.

Three endpoints, one of which — ``batchUpdate`` — carries the whole editing
surface of Google Docs as a union of thirty-three request types. That union
lives in :mod:`~charter.packs.gdocs.types.requests`.

API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.gdocs.types.requests import Request
from charter.types import Body, Path, Query

__all__ = [
    "Request",
    "WriteControl",
    "SuggestionsViewMode",
    "DocumentsGetRequest",
    "DocumentsCreateRequest",
    "DocumentsBatchUpdateRequest",
    "BatchUpdateBody",
    "DocumentsCreateBody",
]


SuggestionsViewMode = Literal[
    "DEFAULT_FOR_CURRENT_ACCESS",
    "SUGGESTIONS_INLINE",
    "PREVIEW_SUGGESTIONS_ACCEPTED",
    "PREVIEW_WITHOUT_SUGGESTIONS",
]
"""How suggested edits are rendered in a fetched document.

API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get
"""


class WriteControl(BaseModel):
    """Optimistic concurrency for a batch update.

    Set ``required_revision_id`` to make the write conditional: if the document
    has moved on, the API answers 400 rather than applying edits to something
    that is no longer what you read. Without it, updates apply to whatever the
    latest revision happens to be — which is the right default for a single
    writer and the wrong one for an agent racing a human.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate#WriteControl
    """

    required_revision_id: Optional[str] = Field(
        default=None,
        description=(
            "The revision ID the write is applied to. If this is not the latest "
            "revision of the document, the request is not processed and returns a "
            "400. Obtain it from `revisionId` on a document you fetched."
        ),
    )
    target_revision_id: Optional[str] = Field(
        default=None,
        description=(
            "The target revision ID. The request is applied to the latest revision, "
            "with any changes made since the target revision transformed onto it "
            "rather than rejected. Mutually exclusive with requiredRevisionId."
        ),
    )


class DocumentsGetRequest(BaseModel):
    """Fetch a document's content.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/get
    """

    document_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "The ID of the document to retrieve. This is the long string in the "
                "document's URL, between `/d/` and `/edit`."
            ),
        ),
        Path(),
    ]
    suggestions_view_mode: Annotated[
        Optional[SuggestionsViewMode],
        Field(
            None,
            description=(
                "How to render suggested edits. Defaults to "
                "DEFAULT_FOR_CURRENT_ACCESS, which shows suggestions inline if the "
                "caller may see them."
            ),
        ),
        Query(),
    ]
    include_tabs_content: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "When true, content is returned in the `tabs` field, covering every "
                "tab in the document. When false or omitted, only the first tab's "
                "content is returned, in the legacy top-level `body` field."
            ),
        ),
        Query(),
    ]


class DocumentsCreateBody(BaseModel):
    """The body of a create-document request.

    Only ``title`` is honoured. Google's own reference is explicit about this:
    the request takes a full Document, and every field except the title is
    ignored. Modelling the rest would advertise capabilities the endpoint does
    not have — to add content, create the document and then call
    ``documents_batch_update``.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/create
    """

    title: Optional[str] = Field(
        default=None,
        description=(
            "The title of the new document. This is the only field documents.create "
            "honours; the document is created empty."
        ),
    )


class DocumentsCreateRequest(BaseModel):
    """Create a blank document.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/create
    """

    body: Annotated[
        DocumentsCreateBody,
        Field(
            default_factory=DocumentsCreateBody,
            description="The document to create. Only the title is honoured.",
        ),
        Body(),
    ]


class BatchUpdateBody(BaseModel):
    """The body of a batch-update request.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate
    """

    requests: List[Request] = Field(
        ...,
        description=(
            "The edits to apply, in order. Each entry sets exactly one kind of "
            "request. Note that edits are applied sequentially and indices shift as "
            "they are: when inserting several pieces of text by index, order the "
            "requests back-to-front so that earlier insertions do not move the "
            "positions later ones refer to."
        ),
    )
    write_control: Optional[WriteControl] = Field(
        default=None,
        description=(
            "Optional concurrency control. Set requiredRevisionId to refuse the "
            "write if the document has changed since it was read."
        ),
    )


class DocumentsBatchUpdateRequest(BaseModel):
    """Apply a list of edits to a document.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/batchUpdate
    """

    document_id: Annotated[
        str,
        Field(..., description="The ID of the document to update."),
        Path(),
    ]
    body: Annotated[
        BatchUpdateBody,
        Field(..., description="The edits to apply."),
        Body(),
    ]
