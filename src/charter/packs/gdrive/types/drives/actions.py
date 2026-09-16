"""
Request schemas for the Drives collection (shared drives).

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/drives
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Path, Query

from .._shared import PageToken

DRIVE_ID = "The ID of the shared drive."
PAGE_SIZE = (
    "The maximum number of shared drives to return. The service may return fewer "
    "than this value. If unspecified, at most 10 shared drives will be returned. "
    "The maximum value is 100; values above 100 will be coerced to 100."
)
Q = "Query string for searching shared drives."
USE_DOMAIN_ADMIN_ACCESS_LIST = (
    "Issue the request as a domain administrator; if set to true, then all "
    "shared drives of the domain in which the requester is an administrator are "
    "returned."
)
USE_DOMAIN_ADMIN_ACCESS_GET = (
    "Issue the request as a domain administrator; if set to true, then the "
    "requester will be granted access if they are an administrator of the domain "
    "to which the shared drive belongs."
)


class DrivesListRequest(BaseModel):
    """
    Lists the user's shared drives. This method accepts the `q` parameter, which
    is a search query combining one or more search terms.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/drives/list
    """

    q: Annotated[Optional[str], Field(None, description=Q), Query()] = None
    page_size: Annotated[
        Optional[int], Field(None, ge=1, le=100, description=PAGE_SIZE), Query()
    ] = None
    page_token: PageToken = None
    use_domain_admin_access: Annotated[
        Optional[bool], Field(None, description=USE_DOMAIN_ADMIN_ACCESS_LIST), Query()
    ] = None


class DrivesGetRequest(BaseModel):
    """
    Gets a shared drive's metadata by ID.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/drives/get
    """

    drive_id: Annotated[str, Field(..., description=DRIVE_ID), Path()]
    use_domain_admin_access: Annotated[
        Optional[bool], Field(None, description=USE_DOMAIN_ADMIN_ACCESS_GET), Query()
    ] = None
