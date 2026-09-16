"""
Request schema for Granola's folder endpoint.

One endpoint, two parameters. Folders are created and renamed in the Granola
app; the API only lists them, and it lists them for two reasons: to find the
``folder_id`` that narrows a note listing, and to find the ``folder_ids`` that
narrow a webhook endpoint's deliveries.

API Reference: https://docs.granola.ai/api-reference/list-folders
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import CURSOR_DESCRIPTION
from charter.types import Query

__all__ = ["FoldersListRequest"]


class FoldersListRequest(BaseModel):
    """List the folders this API key can reach, sorted alphabetically.

    The listing is flat and each folder names its parent, so a hierarchy is
    reassembled by the caller from ``parent_folder_id`` across a full walk.
    There is no parameter that returns one folder's children alone.

    API Reference: https://docs.granola.ai/api-reference/list-folders
    """

    cursor: Annotated[
        Optional[str],
        Field(None, description=CURSOR_DESCRIPTION),
        Query(),
    ]
    page_size: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=30,
            description=(
                "Maximum number of folders to return per page. The server returns 10 "
                "when this is absent."
            ),
        ),
        Query(),
    ]
