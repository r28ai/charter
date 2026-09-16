"""
Blocks — the thirty-one kinds of content a Notion page is made of.

Everything on a page is a block, and blocks nest: a toggle holds paragraphs, a
column list holds columns, a table holds rows. Notion accepts **two levels of
nesting in one request**, so the nesting is modelled as three concrete tiers
rather than as one recursive model — which is what the API's own request
schemas do, and it means a tree too deep to accept is refused here instead of
by a 400:

* :class:`Block` — a top-level block. All thirty-one kinds.
* :class:`NestedBlock` — a child of one. Twenty-nine: a ``column`` and a
  ``column_list`` only exist at the top.
* :class:`LeafBlock` — a child of a child, and the bottom. Twenty-eight, with no
  ``children`` field at all; ``table`` is gone too, since a table is its rows.

Deeper trees are built by appending to the blocks that come back.

Notion tags each block with a ``type`` and puts the payload in the field of that
name, so ``Block`` carries one optional field per kind with a validator that the
payload matches the ``type``. Five kinds are returned and never accepted:
``child_page``, ``child_database``, ``link_preview``, ``meeting_notes`` and
``unsupported`` — a page, a database and a link preview are created through
their own endpoints, and the last two Notion does not model for writes at all.

Two limits Notion enforces per request rather than per block: at most 100
children in one call, and at most two levels of nesting. Deeper trees are built
by appending to the block that comes back.

API Reference: https://developers.notion.com/reference/block
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.packs.notion.types.common import (
    ExternalFileData,
    FileUploadRef,
    Icon,
    NotionColor,
    NotionHostedFileData,
    Parent,
    PartialUser,
    RichText,
    exactly_one_of,
)
from charter.types import Mode

__all__ = [
    "CodeLanguage",
    "NumberedListFormat",
    "Block",
    "NestedBlock",
    "LeafBlock",
]

# The fields every tier carries that are not one of the content types. The
# validator reads the rest off the model, so a tier that offers fewer kinds of
# block needs no second list saying which.
_NOT_CONTENT = frozenset(
    {
        "object", "type", "id", "parent", "created_time", "created_by",
        "last_edited_time", "last_edited_by", "has_children", "archived",
        "in_trash",
    }
)

RICH_TEXT = "The rich text displayed in the block."
COLOR = "The color of the block."
CHILDREN = "The nested child blocks. At most 100."
CAPTION = "The caption shown beneath it."


CodeLanguage = Literal[
    "abap", "abc", "agda", "arduino", "ascii art", "assembly", "bash", "basic",
    "bnf", "c", "c#", "c++", "clojure", "coffeescript", "coq", "css", "dart",
    "dhall", "diff", "docker", "ebnf", "elixir", "elm", "erlang", "f#", "flow",
    "fortran", "gherkin", "glsl", "go", "graphql", "groovy", "haskell", "hcl",
    "html", "idris", "java", "javascript", "json", "julia", "kotlin", "latex",
    "less", "lisp", "livescript", "llvm ir", "lua", "makefile", "markdown",
    "markup", "matlab", "mathematica", "mermaid", "nix", "notion formula",
    "objective-c", "ocaml", "pascal", "perl", "php", "plain text", "powershell",
    "prolog", "protobuf", "purescript", "python", "r", "racket", "reason",
    "ruby", "rust", "sass", "scala", "scheme", "scss", "shell", "smalltalk",
    "solidity", "sql", "swift", "toml", "typescript", "vb.net", "verilog",
    "vhdl", "visual basic", "webassembly", "xml", "yaml", "java/c/c++/c#",
]
"""The syntax highlighting a code block is rendered with.

Ninety values, several of which are not identifiers — ``plain text``,
``ascii art``, ``llvm ir``, ``notion formula`` and ``visual basic`` carry
spaces, and ``java/c/c++/c#`` is a legacy combined value Notion still accepts.
Taken from the API's own ``languageRequest`` enum rather than from the prose,
which lists a shorter set.

API Reference: https://developers.notion.com/reference/block#code
"""

NumberedListFormat = Literal["numbers", "letters", "roman"]
"""How a numbered list is enumerated. Returned, never set — see :class:`Block`."""


# -----------------------------------------------------
# Payloads shared by more than one block type
# -----------------------------------------------------




class SyncedFromRef(BaseModel):
    """The original block a duplicate synced block mirrors.

    API Reference: https://developers.notion.com/reference/block#synced-block
    """

    type: Optional[Literal["block_id"]] = Field(None, description="Always `block_id`.")
    block_id: str = Field(..., description="The ID of the original synced block.")



# -----------------------------------------------------
# The bottom tier: a child of a child, which holds nothing
# -----------------------------------------------------


# -----------------------------------------------------
# Container payloads
#
# Each is declared once without ``children``, which is also exactly the leaf
# tier's shape. The two deeper tiers add the field, so the descriptions have one
# home and only the child type differs.
# -----------------------------------------------------


class TextBlockContent(BaseModel):
    """Rich text with a colour.

    The shape behind ``bulleted_list_item``, ``numbered_list_item``, ``quote``
    and ``toggle``.

    API Reference: https://developers.notion.com/reference/block
    """

    rich_text: List[RichText] = Field(..., max_length=100, description=RICH_TEXT)
    color: Optional[NotionColor] = Field(None, description=COLOR)


class ToDoContent(TextBlockContent):
    """A checklist item.

    API Reference: https://developers.notion.com/reference/block#to-do
    """

    checked: Optional[bool] = Field(
        None, description="Whether the to-do is checked. Unchecked when absent."
    )


class NumberedListItemContent(TextBlockContent):
    """A numbered list item.

    ``list_start_index`` and ``list_format`` are returned on a read and not
    accepted on a write: Notion numbers a list itself.

    API Reference: https://developers.notion.com/reference/block#numbered-list-item
    """

    list_start_index: Annotated[
        Optional[int],
        Field(None, ge=1, description="The number the list starts counting from."),
        Mode("response_only"),
    ]
    list_format: Annotated[
        Optional[NumberedListFormat],
        Field(
            None,
            description="Whether the list counts in numbers, letters or roman numerals.",
        ),
        Mode("response_only"),
    ]


class ParagraphContent(TextBlockContent):
    """A paragraph of rich text.

    API Reference: https://developers.notion.com/reference/block#paragraph
    """

    icon: Optional[Icon] = Field(
        None,
        description=(
            "An icon shown beside the paragraph. Used when the paragraph is the "
            "direct child of a `tab` block, where it labels the tab."
        ),
    )


class CalloutContent(TextBlockContent):
    """A callout — rich text in a tinted box with an icon.

    API Reference: https://developers.notion.com/reference/block#callout
    """

    icon: Optional[Icon] = Field(None, description="The icon shown in the callout.")


class HeadingContent(TextBlockContent):
    """A heading, optionally collapsible.

    The shape behind ``heading_1`` through ``heading_4``. A heading only holds
    children when ``is_toggleable`` is true.

    API Reference: https://developers.notion.com/reference/block#headings
    """

    is_toggleable: Optional[bool] = Field(
        None,
        description=(
            "Whether the heading collapses to hide the blocks beneath it. A heading "
            "can only have children when this is true."
        ),
    )


class TemplateContent(BaseModel):
    """A template button and the blocks it duplicates.

    Deprecated by Notion in favour of database templates; still returned for
    templates made before that, and still accepted.

    API Reference: https://developers.notion.com/reference/block#template
    """

    rich_text: List[RichText] = Field(
        ..., max_length=100, description="The title of the template button."
    )


class TableContent(BaseModel):
    """A table, whose children are its rows.

    API Reference: https://developers.notion.com/reference/block#table
    """

    table_width: int = Field(
        ...,
        ge=1,
        description="The number of columns. Fixed at creation — an update cannot change it.",
    )
    has_column_header: Optional[bool] = Field(
        None, description="Whether the first row is styled as a header."
    )
    has_row_header: Optional[bool] = Field(
        None, description="Whether the first column is styled as a header."
    )


class ColumnContent(BaseModel):
    """One column of a column list.

    API Reference: https://developers.notion.com/reference/block#column-list-and-column
    """

    width_ratio: Optional[float] = Field(
        None,
        ge=0,
        le=1,
        description=(
            "This column's share of the row's width, between 0 and 1. The ratios "
            "across one column list should sum to 1; absent, the columns are equal."
        ),
    )


class ColumnListContent(BaseModel):
    """A row of side-by-side columns.

    API Reference: https://developers.notion.com/reference/block#column-list-and-column
    """


class SyncedBlockContent(BaseModel):
    """Content that appears in more than one place and stays in step.

    ``synced_from`` decides which half this is: ``null`` makes this the
    *original*, which owns the content; an object pointing at a block makes it a
    *duplicate*, whose content mirrors the original and cannot be edited here.

    API Reference: https://developers.notion.com/reference/block#synced-block
    """

    synced_from: Optional[SyncedFromRef] = Field(
        ...,
        description=(
            "The original this block mirrors, or null if this block is itself the "
            "original. Required either way."
        ),
    )


class TabContent(BaseModel):
    """A set of tabs, whose children are the tabs themselves.

    Each child is a ``paragraph`` block: its rich text is the tab's label and
    its own children are the tab's content.

    API Reference: https://developers.notion.com/reference/block#tab
    """

class MediaContent(BaseModel):
    """A file Notion embeds — an image, a video, an audio clip, a PDF or a file.

    Either link to it with ``external`` or attach an upload with
    ``file_upload``. ``file`` is Notion's own hosted copy and comes back on a
    read.

    API Reference: https://developers.notion.com/reference/block#image
    """

    type: Optional[Literal["external", "file", "file_upload"]] = Field(
        None, description="Where the file comes from."
    )
    external: Optional[ExternalFileData] = Field(
        None, description="A file hosted elsewhere, referenced by URL."
    )
    file_upload: Optional[FileUploadRef] = Field(
        None, description="A completed file upload to attach, referenced by its ID."
    )
    file: Annotated[
        Optional[NotionHostedFileData],
        Field(None, description="Notion's hosted copy, with a URL that expires. Returned, never sent."),
        Mode("response_only"),
    ]
    caption: Optional[List[RichText]] = Field(
        None, max_length=100, description="The caption shown beneath the media."
    )

    @model_validator(mode="after")
    def _one_source(self):
        return exactly_one_of(self, "type", ("external", "file_upload", "file"))


class FileBlockContent(MediaContent):
    """A file attachment, which unlike other media carries a display name.

    API Reference: https://developers.notion.com/reference/block#file
    """

    name: Optional[str] = Field(
        None, max_length=100, description="The name of the file, as shown in Notion."
    )


class CodeContent(BaseModel):
    """A code block.

    API Reference: https://developers.notion.com/reference/block#code
    """

    rich_text: List[RichText] = Field(
        ..., max_length=100, description="The code, as rich text."
    )
    language: CodeLanguage = Field(
        ..., description="The language the code is highlighted as."
    )
    caption: Optional[List[RichText]] = Field(
        None, max_length=100, description="The caption shown beneath the code."
    )


class EquationBlockContent(BaseModel):
    """A standalone LaTeX equation, as its own block.

    Distinct from an inline equation, which is a rich text run.

    API Reference: https://developers.notion.com/reference/block#equation
    """

    expression: str = Field(..., description="A KaTeX compatible string.")


class BookmarkContent(BaseModel):
    """A link rendered as a bookmark card.

    API Reference: https://developers.notion.com/reference/block#bookmark
    """

    url: str = Field(..., description="The link this bookmark points to.")
    caption: Optional[List[RichText]] = Field(
        None, max_length=100, description="The caption shown with the bookmark."
    )


class EmbedContent(BaseModel):
    """Third-party content rendered inline.

    API Reference: https://developers.notion.com/reference/block#embed
    """

    url: Optional[str] = Field(None, description="The link to the embedded content.")
    file_upload: Optional[FileUploadRef] = Field(
        None,
        description=(
            "A completed file upload to embed. An uploaded `.html` file becomes an "
            "HTML embed."
        ),
    )
    caption: Optional[List[RichText]] = Field(
        None, max_length=100, description="The caption shown with the embed."
    )

    @model_validator(mode="after")
    def _one_source(self):
        if (self.url is None) == (self.file_upload is None):
            raise ValueError("an embed takes exactly one of `url` or `file_upload`")
        return self


class TableOfContentsContent(BaseModel):
    """A table of contents, built from the page's headings.

    API Reference: https://developers.notion.com/reference/block#table-of-contents
    """

    color: Optional[NotionColor] = Field(None, description="The color of the block.")


class EmptyContent(BaseModel):
    """A block with no content of its own — a divider or a breadcrumb.

    API Reference: https://developers.notion.com/reference/block#divider
    """


class LinkToPageContent(BaseModel):
    """A link to another page, database or comment in the workspace.

    API Reference: https://developers.notion.com/reference/block#link-to-page
    """

    type: Optional[Literal["page_id", "database_id", "comment_id"]] = Field(
        None, description="What kind of thing is linked to."
    )
    page_id: Optional[str] = Field(None, description="The ID of the linked page.")
    database_id: Optional[str] = Field(None, description="The ID of the linked database.")
    comment_id: Optional[str] = Field(None, description="The ID of the linked comment.")

    @model_validator(mode="after")
    def _one_target(self):
        return exactly_one_of(self, "type", ("page_id", "database_id", "comment_id"))


class TableRowContent(BaseModel):
    """One row of a table.

    API Reference: https://developers.notion.com/reference/block#table-row
    """

    cells: List[List[RichText]] = Field(
        ...,
        description=(
            "The row's cells, left to right, each an array of rich text. The number "
            "of cells must equal the parent table's `table_width`."
        ),
    )


class ChildPageContent(BaseModel):
    """A subpage, as it appears in its parent's content.

    Returned by a read. Create a subpage through the pages endpoint with this
    page as its parent, not by appending a block.

    API Reference: https://developers.notion.com/reference/block#child-page
    """

    title: Optional[str] = Field(None, description="The page's title.")


class ChildDatabaseContent(BaseModel):
    """An inline database, as it appears in its parent's content.

    Returned by a read. Create one through the databases endpoint.

    API Reference: https://developers.notion.com/reference/block#child-database
    """

    title: Optional[str] = Field(None, description="The database's title.")


class LinkPreviewContent(BaseModel):
    """A rich preview of a third-party link.

    Returned, never accepted: Notion builds a link preview itself when someone
    pastes a URL in the app. Append a ``bookmark`` or an ``embed`` instead.

    API Reference: https://developers.notion.com/reference/block#link-preview
    """

    url: Optional[str] = Field(None, description="The previewed link.")


class UnsupportedContent(BaseModel):
    """A block whose type the API does not model.

    API Reference: https://developers.notion.com/reference/block#unsupported
    """


# -----------------------------------------------------
# The block itself
# -----------------------------------------------------



class _BlockCommon(BaseModel):
    """What every block carries, whatever tier it sits at.

    The content fields themselves are declared per tier, since which kinds of
    block are legal depends on how deep it is. The validator reads them off the
    model rather than from a list, so a tier that offers fewer needs no second
    place saying which.

    API Reference: https://developers.notion.com/reference/block
    """

    object: Optional[Literal["block"]] = Field(None, description="Always `block`.")
    type: Optional[str] = Field(
        None,
        description=(
            "Which kind of block this is. Returned on a read; on a write Notion "
            "infers it from whichever content field is set."
        ),
    )

    # ---------- content with no children of its own ----------
    code: Optional[CodeContent] = Field(None, description="A block of code.")
    equation: Optional[EquationBlockContent] = Field(
        None, description="A standalone LaTeX equation."
    )
    image: Optional[MediaContent] = Field(None, description="An image.")
    video: Optional[MediaContent] = Field(None, description="A video.")
    audio: Optional[MediaContent] = Field(None, description="An audio clip.")
    pdf: Optional[MediaContent] = Field(None, description="A PDF.")
    file: Optional[FileBlockContent] = Field(None, description="A file attachment.")
    embed: Optional[EmbedContent] = Field(
        None, description="Third-party content rendered inline."
    )
    bookmark: Optional[BookmarkContent] = Field(
        None, description="A link rendered as a bookmark card."
    )
    divider: Optional[EmptyContent] = Field(
        None, description="A horizontal rule. Send an empty object."
    )
    breadcrumb: Optional[EmptyContent] = Field(
        None, description="The page's ancestry. Send an empty object."
    )
    table_of_contents: Optional[TableOfContentsContent] = Field(
        None, description="A table of contents built from the page's headings."
    )
    table_row: Optional[TableRowContent] = Field(
        None, description="One row of a table."
    )
    link_to_page: Optional[LinkToPageContent] = Field(
        None, description="A link to another page, database or comment."
    )

    # ---------- returned, never accepted ----------
    child_page: Annotated[
        Optional[ChildPageContent],
        Field(None, description="A subpage. Create one through the pages endpoint."),
        Mode("response_only"),
    ]
    child_database: Annotated[
        Optional[ChildDatabaseContent],
        Field(
            None,
            description="An inline database. Create one through the databases endpoint.",
        ),
        Mode("response_only"),
    ]
    link_preview: Annotated[
        Optional[LinkPreviewContent],
        Field(None, description="A rich preview Notion built from a pasted link."),
        Mode("response_only"),
    ]
    unsupported: Annotated[
        Optional[UnsupportedContent],
        Field(None, description="A block whose type the API does not model."),
        Mode("response_only"),
    ]

    # ---------- common, all returned ----------
    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the block."),
        Mode("response_only"),
    ]
    parent: Annotated[
        Optional[Parent],
        Field(None, description="What the block belongs to."),
        Mode("response_only"),
    ]
    created_time: Annotated[
        Optional[str],
        Field(None, description="When the block was created, in ISO 8601 format."),
        Mode("response_only"),
    ]
    created_by: Annotated[
        Optional[PartialUser],
        Field(None, description="The user who created the block."),
        Mode("response_only"),
    ]
    last_edited_time: Annotated[
        Optional[str],
        Field(None, description="When the block was last edited, in ISO 8601 format."),
        Mode("response_only"),
    ]
    last_edited_by: Annotated[
        Optional[PartialUser],
        Field(None, description="The user who last edited the block."),
        Mode("response_only"),
    ]
    has_children: Annotated[
        Optional[bool],
        Field(None, description="Whether the block has child blocks."),
        Mode("response_only"),
    ]
    archived: Annotated[
        Optional[bool],
        Field(None, description="Deprecated. Use `in_trash`."),
        Mode("response_only"),
    ]

    @model_validator(mode="after")
    def _one_kind(self):
        variants = tuple(
            name for name in type(self).model_fields if name not in _NOT_CONTENT
        )
        return exactly_one_of(self, "type", variants)


class LeafBlock(_BlockCommon):
    """A block two levels down, which is as deep as one request goes.

    Twenty-eight kinds, none of them holding children: a ``column``, a
    ``column_list`` and a ``table`` are all defined by what they contain, so
    none of the three can sit here. Append to this block afterwards to go deeper.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    paragraph: Optional[ParagraphContent] = Field(None, description="A paragraph of text.")
    heading_1: Optional[HeadingContent] = Field(None, description="A top-level heading.")
    heading_2: Optional[HeadingContent] = Field(None, description="A second-level heading.")
    heading_3: Optional[HeadingContent] = Field(None, description="A third-level heading.")
    heading_4: Optional[HeadingContent] = Field(None, description="A fourth-level heading.")
    bulleted_list_item: Optional[TextBlockContent] = Field(
        None, description="A bulleted list item."
    )
    numbered_list_item: Optional[NumberedListItemContent] = Field(
        None, description="A numbered list item."
    )
    to_do: Optional[ToDoContent] = Field(None, description="A checklist item.")
    toggle: Optional[TextBlockContent] = Field(
        None, description="A toggle, which collapses the blocks beneath it."
    )
    quote: Optional[TextBlockContent] = Field(None, description="A quotation.")
    callout: Optional[CalloutContent] = Field(
        None, description="A callout — text in a tinted box with an icon."
    )
    template: Optional[TemplateContent] = Field(
        None, description="A template button. Deprecated by Notion."
    )
    synced_block: Optional[SyncedBlockContent] = Field(
        None, description="Content mirrored between two places."
    )
    tab: Optional[TabContent] = Field(None, description="A set of tabs.")


# -----------------------------------------------------
# The middle tier: a child of a top-level block
# -----------------------------------------------------


class NestedParagraphContent(ParagraphContent):
    """A paragraph one level down.

    API Reference: https://developers.notion.com/reference/block#paragraph
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class NestedTextBlockContent(TextBlockContent):
    """A list item, quote or toggle one level down.

    API Reference: https://developers.notion.com/reference/block
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class NestedToDoContent(ToDoContent):
    """A checklist item one level down.

    API Reference: https://developers.notion.com/reference/block#to-do
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class NestedNumberedListItemContent(NumberedListItemContent):
    """A numbered list item one level down.

    API Reference: https://developers.notion.com/reference/block#numbered-list-item
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class NestedCalloutContent(CalloutContent):
    """A callout one level down.

    API Reference: https://developers.notion.com/reference/block#callout
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class NestedHeadingContent(HeadingContent):
    """A heading one level down.

    API Reference: https://developers.notion.com/reference/block#headings
    """

    children: Optional[List[LeafBlock]] = Field(
        None,
        max_length=100,
        description="The blocks the heading collapses, when `is_toggleable` is true.",
    )


class NestedTemplateContent(TemplateContent):
    """A template button one level down.

    API Reference: https://developers.notion.com/reference/block#template
    """

    children: Optional[List[LeafBlock]] = Field(
        None, max_length=100, description="The blocks the button duplicates."
    )


class NestedSyncedBlockContent(SyncedBlockContent):
    """A synced block one level down.

    API Reference: https://developers.notion.com/reference/block#synced-block
    """

    children: Optional[List[LeafBlock]] = Field(
        None,
        max_length=100,
        description="The synced content. Only set on the original, never on a duplicate.",
    )


class NestedTabContent(TabContent):
    """A set of tabs one level down.

    API Reference: https://developers.notion.com/reference/block#tab
    """

    children: List[LeafBlock] = Field(
        ...,
        max_length=100,
        description="The tabs, each a `paragraph` block labelling and holding one tab.",
    )


class NestedTableContent(TableContent):
    """A table one level down.

    API Reference: https://developers.notion.com/reference/block#table
    """

    children: List[LeafBlock] = Field(
        ...,
        max_length=100,
        description=(
            "The table's rows, each a `table_row` block whose `cells` count matches "
            "`table_width`."
        ),
    )


class NestedBlock(_BlockCommon):
    """A block one level down from the top.

    Twenty-nine kinds: everything except a ``column`` and a ``column_list``,
    which Notion only accepts at the top level.

    API Reference: https://developers.notion.com/reference/patch-block-children
    """

    paragraph: Optional[NestedParagraphContent] = Field(
        None, description="A paragraph of text."
    )
    heading_1: Optional[NestedHeadingContent] = Field(
        None, description="A top-level heading."
    )
    heading_2: Optional[NestedHeadingContent] = Field(
        None, description="A second-level heading."
    )
    heading_3: Optional[NestedHeadingContent] = Field(
        None, description="A third-level heading."
    )
    heading_4: Optional[NestedHeadingContent] = Field(
        None, description="A fourth-level heading."
    )
    bulleted_list_item: Optional[NestedTextBlockContent] = Field(
        None, description="A bulleted list item."
    )
    numbered_list_item: Optional[NestedNumberedListItemContent] = Field(
        None, description="A numbered list item."
    )
    to_do: Optional[NestedToDoContent] = Field(None, description="A checklist item.")
    toggle: Optional[NestedTextBlockContent] = Field(
        None, description="A toggle, which collapses the blocks beneath it."
    )
    quote: Optional[NestedTextBlockContent] = Field(None, description="A quotation.")
    callout: Optional[NestedCalloutContent] = Field(
        None, description="A callout — text in a tinted box with an icon."
    )
    template: Optional[NestedTemplateContent] = Field(
        None, description="A template button. Deprecated by Notion."
    )
    synced_block: Optional[NestedSyncedBlockContent] = Field(
        None, description="Content mirrored between two places."
    )
    tab: Optional[NestedTabContent] = Field(None, description="A set of tabs.")
    table: Optional[NestedTableContent] = Field(None, description="A table.")


# -----------------------------------------------------
# The top tier
# -----------------------------------------------------


class BlockParagraphContent(ParagraphContent):
    """A top-level paragraph.

    API Reference: https://developers.notion.com/reference/block#paragraph
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class BlockTextContent(TextBlockContent):
    """A top-level list item, quote or toggle.

    API Reference: https://developers.notion.com/reference/block
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class BlockToDoContent(ToDoContent):
    """A top-level checklist item.

    API Reference: https://developers.notion.com/reference/block#to-do
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class BlockNumberedListItemContent(NumberedListItemContent):
    """A top-level numbered list item.

    API Reference: https://developers.notion.com/reference/block#numbered-list-item
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class BlockCalloutContent(CalloutContent):
    """A top-level callout.

    API Reference: https://developers.notion.com/reference/block#callout
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description=CHILDREN
    )


class BlockHeadingContent(HeadingContent):
    """A top-level heading.

    API Reference: https://developers.notion.com/reference/block#headings
    """

    children: Optional[List[NestedBlock]] = Field(
        None,
        max_length=100,
        description="The blocks the heading collapses, when `is_toggleable` is true.",
    )


class BlockTemplateContent(TemplateContent):
    """A top-level template button.

    API Reference: https://developers.notion.com/reference/block#template
    """

    children: Optional[List[NestedBlock]] = Field(
        None, max_length=100, description="The blocks the button duplicates."
    )


class BlockSyncedBlockContent(SyncedBlockContent):
    """A top-level synced block.

    API Reference: https://developers.notion.com/reference/block#synced-block
    """

    children: Optional[List[NestedBlock]] = Field(
        None,
        max_length=100,
        description="The synced content. Only set on the original, never on a duplicate.",
    )


class BlockTabContent(TabContent):
    """A top-level set of tabs.

    API Reference: https://developers.notion.com/reference/block#tab
    """

    children: List[NestedBlock] = Field(
        ...,
        max_length=100,
        description="The tabs, each a `paragraph` block labelling and holding one tab.",
    )


class BlockTableContent(TableContent):
    """A top-level table.

    API Reference: https://developers.notion.com/reference/block#table
    """

    children: List[NestedBlock] = Field(
        ...,
        max_length=100,
        description=(
            "The table's rows, each a `table_row` block whose `cells` count matches "
            "`table_width`."
        ),
    )


class BlockColumnContent(ColumnContent):
    """One column of a top-level column list.

    API Reference: https://developers.notion.com/reference/block#column-list-and-column
    """

    children: List[NestedBlock] = Field(
        ..., max_length=100, description="The blocks stacked in this column."
    )


class BlockColumnListContent(ColumnListContent):
    """A top-level row of side-by-side columns.

    API Reference: https://developers.notion.com/reference/block#column-list-and-column
    """

    children: List[NestedBlock] = Field(
        ...,
        max_length=100,
        description="The columns, each a `column` block. A column list needs at least two.",
    )


class Block(_BlockCommon):
    """One piece of content on a page.

    All thirty-one kinds Notion accepts. Exactly one of the content fields is
    set, and ``type`` names it.

    API Reference: https://developers.notion.com/reference/block
    """

    paragraph: Optional[BlockParagraphContent] = Field(
        None, description="A paragraph of text."
    )
    heading_1: Optional[BlockHeadingContent] = Field(
        None, description="A top-level heading."
    )
    heading_2: Optional[BlockHeadingContent] = Field(
        None, description="A second-level heading."
    )
    heading_3: Optional[BlockHeadingContent] = Field(
        None, description="A third-level heading."
    )
    heading_4: Optional[BlockHeadingContent] = Field(
        None, description="A fourth-level heading."
    )
    bulleted_list_item: Optional[BlockTextContent] = Field(
        None, description="A bulleted list item."
    )
    numbered_list_item: Optional[BlockNumberedListItemContent] = Field(
        None, description="A numbered list item."
    )
    to_do: Optional[BlockToDoContent] = Field(None, description="A checklist item.")
    toggle: Optional[BlockTextContent] = Field(
        None, description="A toggle, which collapses the blocks beneath it."
    )
    quote: Optional[BlockTextContent] = Field(None, description="A quotation.")
    callout: Optional[BlockCalloutContent] = Field(
        None, description="A callout — text in a tinted box with an icon."
    )
    template: Optional[BlockTemplateContent] = Field(
        None, description="A template button. Deprecated by Notion."
    )
    synced_block: Optional[BlockSyncedBlockContent] = Field(
        None, description="Content mirrored between two places."
    )
    tab: Optional[BlockTabContent] = Field(None, description="A set of tabs.")
    table: Optional[BlockTableContent] = Field(None, description="A table.")
    column_list: Optional[BlockColumnListContent] = Field(
        None, description="A row of side-by-side columns."
    )
    column: Optional[BlockColumnContent] = Field(
        None, description="One column of a column list."
    )
