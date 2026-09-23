# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the About collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/about
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from charter.types import Query

ABOUT_FIELDS = (
    "Required. The `fields` parameter must be set. To return the exact fields "
    "you need, see Return specific fields. Example: `user,storageQuota`."
)


class AboutGetRequest(BaseModel):
    """
    Gets information about the user, the user's Drive, and system capabilities.
    Required: The `fields` parameter must be set.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/about/get
    """

    fields: Annotated[str, Field(..., description=ABOUT_FIELDS), Query()]
