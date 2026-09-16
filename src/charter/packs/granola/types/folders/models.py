"""
Response model for Granola's folder endpoint.

The ``Folder`` object itself lives in ``types/common.py``: a note's
``folder_membership`` returns the same shape, so it is described once.

API Reference: https://docs.granola.ai/api-reference/list-folders
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field

from charter.packs.granola.types.common import CursorPage, Folder
from charter.types import Mode

__all__ = ["ListFoldersOutput"]


class ListFoldersOutput(CursorPage):
    """A page of folders.

    API Reference: https://docs.granola.ai/api-reference/list-folders
    """

    folders: Annotated[
        Optional[List[Folder]],
        Field(None, description="The folders on this page"),
        Mode("response_only"),
    ]
