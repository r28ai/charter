"""
Request schemas for the Revisions collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/revisions
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Path, Query

from .._shared import FILE_ID, AcknowledgeAbuse, PageToken

REVISION_ID = "The ID of the revision."
PAGE_SIZE = (
    "The maximum number of revisions to return. The service may return fewer "
    "than this value. If unspecified, at most 200 revisions will be returned. "
    "The maximum value is 1000; values above 1000 will be coerced to 1000."
)


class RevisionsListRequest(BaseModel):
    """
    Lists a file's revisions.

    Important: The list of revisions returned by this method might be incomplete
    for files with a large revision history, including frequently edited Google
    Docs, Sheets, and Slides. Older revisions might be omitted from the
    response, meaning the first revision returned may not be the oldest existing
    revision. The revision history visible in the Workspace editor user
    interface might be more complete than the list returned by the API.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/revisions/list
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    page_size: Annotated[
        Optional[int], Field(None, ge=1, le=1000, description=PAGE_SIZE), Query()
    ] = None
    page_token: PageToken = None


class RevisionsGetRequest(BaseModel):
    """
    Gets a revision's metadata or content by ID.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/revisions/get
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    revision_id: Annotated[str, Field(..., description=REVISION_ID), Path()]
    acknowledge_abuse: AcknowledgeAbuse = None
