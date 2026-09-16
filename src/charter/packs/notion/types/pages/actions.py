"""
Request schemas for Notion's page endpoints.

API Reference: https://developers.notion.com/reference/page
"""

from __future__ import annotations

from typing import Annotated, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.blocks.models import Block
from charter.packs.notion.types.common import (
    Cover,
    Icon,
    Parent,
    Position,
    Template,
    exactly_one_of,
)
from charter.packs.notion.types.pages.models import PagePropertyValue
from charter.types import Body, ConflictsWith, Mode, Path, Query

__all__ = [
    "PagesCreateRequest",
    "PagesRetrieveRequest",
    "PagesUpdateRequest",
    "PagesMoveRequest",
    "PagesRetrievePropertyItemRequest",
    "PagesRetrieveMarkdownRequest",
    "PagesUpdateMarkdownRequest",
]

PAGE_ID = "The ID of the page."

PROPERTIES = (
    "The values of the page's properties, keyed by property name or ID. A page "
    "whose parent is a data source must use that data source's schema; a page "
    "whose parent is another page has only `title`."
)


class PageCreateBody(BaseModel):
    """The body of a create-page request.

    Content can arrive three ways and only one at a time: as `children` blocks,
    as a `markdown` string Notion parses, or from a `template`.

    API Reference: https://developers.notion.com/reference/post-page
    """

    parent: Parent = Field(
        ...,
        description=(
            "Where the page is created: `page_id` for a subpage, or "
            "`data_source_id` to add a row to a database."
        ),
    )
    properties: Optional[Dict[str, PagePropertyValue]] = Field(
        None, description=PROPERTIES
    )
    icon: Optional[Icon] = Field(None, description="The page's icon.")
    cover: Optional[Cover] = Field(None, description="The page's cover image.")
    children: Annotated[
        Optional[List[Block]],
        Field(
            None,
            max_length=100,
            description=(
                "The content of the new page, as blocks. At most 100, and at most "
                "two levels of nesting — append the rest afterwards."
            ),
        ),
        ConflictsWith(
            "markdown",
            reason="Content comes from blocks or from Markdown, not both.",
        ),
    ]
    content: Annotated[
        Optional[List[Block]],
        Field(
            None,
            max_length=100,
            description="An alias for `children`. Send one or the other, not both.",
        ),
        ConflictsWith(
            "children",
            "markdown",
            reason="`content` and `children` are the same field under two names.",
        ),
    ]
    markdown: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The content of the new page as Notion-flavored Markdown, which "
                "Notion parses into blocks. Newlines must be `\\n`."
            ),
        ),
    ]
    template: Annotated[
        Optional[Template],
        Field(
            None,
            description=(
                "A template to build the page from. Applying one is incompatible "
                "with supplying content directly."
            ),
        ),
        ConflictsWith(
            "children",
            "content",
            "markdown",
            reason="A template supplies the content itself.",
        ),
    ]
    position: Optional[Position] = Field(
        None, description="Where the content is placed within the page."
    )
    allow_async: Optional[bool] = Field(
        None,
        description=(
            "Whether a large `markdown` body may be parsed in the background. When "
            "true the call answers 202 with an async task to poll rather than the "
            "finished page."
        ),
    )


class PagesCreateRequest(BaseModel):
    """Create a page.

    API Reference: https://developers.notion.com/reference/post-page
    """

    body: Annotated[PageCreateBody, Field(..., description="The page to create."), Body()]
    filter_properties: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=100,
            description=(
                "Property IDs to return on the page that comes back, instead of all "
                "of them. A page that does not have a listed property omits it."
            ),
        ),
        Query(),
    ]



class PagesRetrieveRequest(BaseModel):
    """Retrieve a page.

    API Reference: https://developers.notion.com/reference/retrieve-a-page
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    filter_properties: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=100,
            description=(
                "Property IDs to return, instead of all of them. A page that does "
                "not have a listed property simply omits it."
            ),
        ),
        Query(),
    ]


class PageUpdateBody(BaseModel):
    """The body of an update-page request.

    Every field is optional: anything omitted is left unchanged. A page's parent
    cannot be changed here — see :class:`PagesMoveRequest`.

    API Reference: https://developers.notion.com/reference/patch-page
    """

    properties: Optional[Dict[str, PagePropertyValue]] = Field(
        None,
        description=(
            f"{PROPERTIES} Set a value to null to clear it. Leave the computed "
            "types out of the map entirely rather than sending them as null."
        ),
    )
    icon: Optional[Icon] = Field(None, description="The page's icon. Null removes it.")
    cover: Optional[Cover] = Field(
        None, description="The page's cover image. Null removes it."
    )
    in_trash: Optional[bool] = Field(
        None, description="Whether the page is in the trash. False restores it."
    )
    is_archived: Optional[bool] = Field(
        None,
        description=(
            "Whether the page is archived. `in_trash` is the field to reach for; "
            "this is the older spelling and the API still accepts it."
        ),
    )
    is_locked: Optional[bool] = Field(
        None,
        description=(
            "Whether the page is locked against editing in the Notion app. It does "
            "not block writes through the API."
        ),
    )
    template: Optional[Template] = Field(
        None, description="A template to apply to the page."
    )
    erase_content: Optional[bool] = Field(
        None, description="Whether to delete every block on the page."
    )


class PagesUpdateRequest(BaseModel):
    """Update a page's properties, icon, cover or trash state.

    API Reference: https://developers.notion.com/reference/patch-page
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    body: Annotated[
        PageUpdateBody, Field(..., description="The fields to change."), Body()
    ]
    filter_properties: Annotated[
        Optional[List[str]],
        Field(
            None,
            max_length=100,
            description=(
                "Property IDs to return on the page that comes back, instead of all "
                "of them. A page that does not have a listed property omits it."
            ),
        ),
        Query(),
    ]



class PageMoveBody(BaseModel):
    """The body of a move-page request.

    API Reference: https://developers.notion.com/reference/move-page
    """

    parent: Parent = Field(..., description="Where to move the page to.")


class PagesMoveRequest(BaseModel):
    """Move a page under a different parent.

    The update endpoint cannot change a parent; this is the one that can.

    API Reference: https://developers.notion.com/reference/move-page
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    body: Annotated[PageMoveBody, Field(..., description="The new parent."), Body()]


class PagesRetrievePropertyItemRequest(BaseModel):
    """Retrieve one property value of a page, in full.

    A page object truncates the list-valued properties — title, rich text,
    relation and people — at 25 entries. This endpoint pages through all of them.

    API Reference: https://developers.notion.com/reference/retrieve-a-page-property
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    property_id: Annotated[
        str,
        Field(..., description="The ID or name of the property to retrieve."),
        Path(),
    ]
    start_cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "A `next_cursor` from a previous response, for the properties that "
                "paginate."
            ),
        ),
        Query(),
    ]
    page_size: Annotated[
        Optional[int],
        Field(None, ge=1, le=100, description="How many entries to return. Maximum 100."),
        Query(),
    ]


class PagesRetrieveMarkdownRequest(BaseModel):
    """Retrieve a page's content as Markdown.

    Notion renders the block tree itself, which is the cheap way to read a page:
    one call and no recursion through `blocks_children_list`.

    API Reference: https://developers.notion.com/reference/retrieve-page-markdown
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    include_transcript: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to include the transcript of a meeting notes block in the "
                "rendered Markdown."
            ),
        ),
        Query(),
    ]


class ContentUpdate(BaseModel):
    """One search-and-replace over a page's Markdown.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    old_str: str = Field(
        ...,
        description=(
            "The existing content to find. It must match a unique stretch of the "
            "page, or the operation cannot tell which one you meant."
        ),
    )
    new_str: str = Field(..., description="What to put in its place.")


class UpdateContentOp(BaseModel):
    """Edit parts of a page, leaving the rest alone.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    content_updates: List[ContentUpdate] = Field(
        ..., description="The search-and-replace operations to apply, in order."
    )
    allow_deleting_content: Optional[bool] = Field(
        None,
        description=(
            "Whether an edit may delete child pages or databases. Refused when "
            "absent, so a replacement that would remove one fails rather than "
            "doing it quietly."
        ),
    )


class ReplaceContentOp(BaseModel):
    """Replace a page's entire content.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    new_str: str = Field(
        ..., description="The Markdown that becomes the whole of the page's content."
    )
    allow_deleting_content: Optional[bool] = Field(
        None,
        description=(
            "Whether the replacement may delete child pages or databases. Refused "
            "when absent."
        ),
    )


class InsertPosition(BaseModel):
    """Which end of the page content is inserted at.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    type: Literal["start", "end"] = Field(
        ..., description="Whether to prepend or append the content."
    )


class InsertContentOp(BaseModel):
    """Add content without touching what is there.

    Deprecated by Notion in favour of `update_content`.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    content: str = Field(..., description="The Markdown to insert.")
    after: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                'Existing content to insert after, written as "start text...end '
                'text". Omit to append at the end of the page.'
            ),
        ),
        ConflictsWith("position", reason="Both say where the content goes."),
    ]
    position: Optional[InsertPosition] = Field(
        None, description="Insert at the start or the end of the page."
    )


class ReplaceContentRangeOp(BaseModel):
    """Replace one stretch of a page.

    Deprecated by Notion in favour of `update_content`.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    content: str = Field(..., description="The Markdown that replaces the range.")
    content_range: str = Field(
        ...,
        description='The existing content to replace, written as "start text...end text".',
    )
    allow_deleting_content: Optional[bool] = Field(
        None,
        description="Whether the replacement may delete child pages or databases.",
    )


class PageMarkdownUpdateBody(BaseModel):
    """The body of an update-page-markdown request.

    This is not a single field of Markdown: it is one of four operations, named
    by ``type``. Two of them Notion has deprecated in favour of
    ``update_content``, and they are marked ``Mode("disabled")`` so a model is
    offered the two that are current — they stay declared here because the API
    still accepts them and the schema is what documents that.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    type: Optional[
        Literal["update_content", "replace_content", "insert_content", "replace_content_range"]
    ] = Field(None, description="Which operation to perform.")
    update_content: Optional[UpdateContentOp] = Field(
        None, description="Edit parts of the page by search and replace."
    )
    replace_content: Optional[ReplaceContentOp] = Field(
        None, description="Replace the whole of the page's content."
    )
    insert_content: Annotated[
        Optional[InsertContentOp],
        Field(None, description="Deprecated. Add content at a position."),
        Mode("disabled"),
    ]
    replace_content_range: Annotated[
        Optional[ReplaceContentRangeOp],
        Field(None, description="Deprecated. Replace one stretch of the page."),
        Mode("disabled"),
    ]
    allow_async: Optional[bool] = Field(
        None,
        description=(
            "Whether a large edit may run in the background, answering 202 with an "
            "async task to poll rather than the finished page."
        ),
    )

    @model_validator(mode="after")
    def _one_operation(self):
        return exactly_one_of(
            self,
            "type",
            ("update_content", "replace_content", "insert_content", "replace_content_range"),
        )



class PagesUpdateMarkdownRequest(BaseModel):
    """Replace a page's content with Markdown.

    API Reference: https://developers.notion.com/reference/update-page-markdown
    """

    page_id: Annotated[str, Field(..., description=PAGE_ID), Path()]
    body: Annotated[
        PageMarkdownUpdateBody, Field(..., description="The new content."), Body()
    ]
