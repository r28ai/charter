"""
Request schemas for Notion's block endpoints.

API Reference: https://developers.notion.com/reference/block
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.packs.notion.types.blocks.models import Block, BlockColumnListContent
from charter.packs.notion.types.common import PaginatedQuery, Position
from charter.types import Body, Mode, Path

__all__ = [
    "BlocksRetrieveRequest",
    "BlocksUpdateRequest",
    "BlocksDeleteRequest",
    "BlocksChildrenListRequest",
    "BlocksChildrenAppendRequest",
]

BLOCK_ID = "The ID of the block."
BLOCK_OR_PAGE_ID = (
    "The ID of the block, or of a page — a page is the block its top-level "
    "content hangs from."
)


class BlocksRetrieveRequest(BaseModel):
    """Retrieve a block.

    API Reference: https://developers.notion.com/reference/retrieve-a-block
    """

    block_id: Annotated[str, Field(..., description=BLOCK_ID), Path()]


class BlockUpdateBody(Block):
    """The body of an update-block request.

    A block's own content fields, all optional. The type cannot be changed:
    send the field matching the block's existing type. Whatever is sent replaces
    the whole value — sending `rich_text` replaces the entire array rather than
    appending to it — and children are not editable here.

    API Reference: https://developers.notion.com/reference/update-a-block
    """

    in_trash: Optional[bool] = Field(
        None,
        description="Whether the block is in the trash. False restores it.",
    )

    # Neither is accepted here, and both are inherited from `Block`. Hidden
    # rather than removed: pydantic keeps an inherited field whatever you do, so
    # the honest way to say "not on this endpoint" is a mode.
    object: Annotated[
        Optional[Literal["block"]],
        Field(None, description="Not accepted when updating a block."),
        Mode("disabled"),
    ]
    column_list: Annotated[
        Optional[BlockColumnListContent],
        Field(
            None,
            description=(
                "Not accepted when updating a block. Change a column list by "
                "appending to or deleting its columns."
            ),
        ),
        Mode("disabled"),
    ]


class BlocksUpdateRequest(BaseModel):
    """Update a block's content, or trash and restore it.

    API Reference: https://developers.notion.com/reference/update-a-block
    """

    block_id: Annotated[str, Field(..., description=BLOCK_ID), Path()]
    body: Annotated[
        BlockUpdateBody, Field(..., description="The content to replace."), Body()
    ]


class BlocksDeleteRequest(BaseModel):
    """Move a block to the trash.

    A soft delete: the block comes back with `in_trash` true and can be restored
    by updating it.

    API Reference: https://developers.notion.com/reference/delete-a-block
    """

    block_id: Annotated[str, Field(..., description=BLOCK_ID), Path()]


class BlocksChildrenListRequest(PaginatedQuery):
    """List a block's direct children.

    Only one level: a child that has children of its own reports `has_children`,
    and reading those is another call with that child's ID.

    API Reference: https://developers.notion.com/reference/get-block-children
    """

    block_id: Annotated[str, Field(..., description=BLOCK_OR_PAGE_ID), Path()]


class BlockChildrenAppendBody(BaseModel):
    """The body of an append-children request.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    children: List[Block] = Field(
        ...,
        max_length=100,
        description=(
            "The blocks to append. At most 100 per call, nested at most two levels "
            "deep — build deeper trees by appending to the blocks that come back."
        ),
    )
    position: Optional[Position] = Field(
        None,
        description=(
            "Where among the existing children the new blocks land. Appended to the "
            "end when absent."
        ),
    )


class BlocksChildrenAppendRequest(BaseModel):
    """Append blocks to a block or a page.

    Append-only: this cannot move or reorder blocks that are already there.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    block_id: Annotated[str, Field(..., description=BLOCK_OR_PAGE_ID), Path()]
    body: Annotated[
        BlockChildrenAppendBody, Field(..., description="The blocks to append."), Body()
    ]
