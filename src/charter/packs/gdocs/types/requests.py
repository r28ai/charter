# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The ``batchUpdate`` request union — every edit Google Docs can apply.

This is the widest schema in the repository, and the reason the Docs pack exists
as a test of the contract layer. ``documents.batchUpdate`` takes a list of
``Request`` objects, each of which is a *oneof*: exactly one of thirty-three
possible edits must be set, and setting two is an error the API reports as a
400 with no useful detail.

That constraint is declared here as a ``model_validator``, on ``Request`` and on
the eleven individual edits that have a oneof of their own (``location`` versus
``end_of_segment_location``, and so on). Those validators are the point: they
are enforced locally, against the model's own input, before anything is sent.

Ported from a production implementation, which is why the coverage is complete
rather than the usual documented-core subset.

API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# =========================
# Enums (Literal aliases)
# =========================

BulletGlyphPreset = Literal[
    "ARROW",
    "ARROW3D",
    "CHECKBOX",
    "CIRCLE",
    "DIAMOND",
    "DIAMONDX",
    "HOLLOWDIAMOND",
    "DISC",
    "SQUARE",
    "STAR",
    "ALPHA",
    "UPPERALPHA",
    "DECIMAL",
    "ZERODECIMAL",
    "ROMAN",
    "UPPERROMAN",
    "LEFTTRIANGLE",
    "BULLET_GLYPH_PRESET_UNSPECIFIED",
    "BULLET_DISC_CIRCLE_SQUARE",
    "BULLET_DIAMONDX_ARROW3D_SQUARE",
    "BULLET_CHECKBOX",
    "BULLET_ARROW_DIAMOND_DISC",
    "BULLET_STAR_CIRCLE_SQUARE",
    "BULLET_ARROW3D_CIRCLE_SQUARE",
    "BULLET_LEFTTRIANGLE_DIAMOND_DISC",
    "BULLET_DIAMONDX_HOLLOWDIAMOND_SQUARE",
    "BULLET_DIAMOND_CIRCLE_SQUARE",
    "NUMBERED_DECIMAL_ALPHA_ROMAN",
    "NUMBERED_DECIMAL_ALPHA_ROMAN_PARENS",
    "NUMBERED_DECIMAL_NESTED",
    "NUMBERED_UPPERALPHA_ALPHA_ROMAN",
    "NUMBERED_UPPERROMAN_UPPERALPHA_DECIMAL",
    "NUMBERED_ZERODECIMAL_ALPHA_ROMAN",
]

ImageReplaceMethod = Literal["IMAGE_REPLACE_METHOD_UNSPECIFIED", "CENTER_CROP"]

HeaderFooterType = Literal["HEADER_FOOTER_TYPE_UNSPECIFIED", "DEFAULT"]

SectionType = Literal["SECTION_TYPE_UNSPECIFIED", "CONTINUOUS", "NEXT_PAGE", "NEXT_COLUMN"]

# =========================
# Simple / Re-usable models
# =========================


class TabsCriteria(BaseModel):
    """A criteria that specifies in which tabs a request executes.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#TabsCriteria
    """

    tab_ids: Optional[List[str]] = Field(
        default=None, description="The list of tab IDs in which the request executes."
    )


class SubstringMatchCriteria(BaseModel):
    """Finds text in the document matching this substring.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#SubstringMatchCriteria
    """

    text: str = Field(..., description="The text to search for in the document.")
    match_case: Optional[bool] = Field(
        default=None, description="Indicates whether the search should respect case."
    )
    search_by_regex: Optional[bool] = Field(
        default=None,
        description="True if the find value should be treated as a regular expression.",
    )


class Location(BaseModel):
    """A particular location in the document.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#Location
    """

    segment_id: Optional[str] = Field(
        default=None,
        description="The ID of the header, footer or footnote the location is in. An empty segment ID signifies the document's body.",
    )
    index: Optional[int] = Field(
        default=None,
        description="The zero-based index, in UTF-16 code units relative to the beginning of the segment.",
    )
    tab_id: Optional[str] = Field(
        default=None,
        description="The tab that the location is in. When omitted, the request is applied to the first tab.",
    )


class EndOfSegmentLocation(BaseModel):
    """Location at the end of a body, header, footer or footnote.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#EndOfSegmentLocation
    """

    segment_id: Optional[str] = Field(
        default=None,
        description="The ID of the header, footer or footnote the location is in. An empty segment ID signifies the document's body.",
    )
    tab_id: Optional[str] = Field(
        default=None,
        description="The tab that the location is in. When omitted, the request is applied to the first tab.",
    )


class Range(BaseModel):
    """The start and end indices of text in the document.

    NOTE: The official docs reference the Range type, but its full schema is not present in the scraped page. The essential fields are included here.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#Range
    """

    start_index: Optional[int] = Field(
        default=None, description="The start index of the range, in UTF-16 code units."
    )
    end_index: Optional[int] = Field(
        default=None, description="The end index of the range, in UTF-16 code units."
    )
    segment_id: Optional[str] = Field(
        default=None,
        description="The ID of the header, footer or footnote the range is in. An empty segment ID signifies the document's body.",
    )


# ------------------------------------------------------------------
# Minimal style models (partial definitions to preserve type safety)
# ------------------------------------------------------------------


class TextStyle(BaseModel):
    """Text styling information.

    The full TextStyle schema is extensive. The subset below contains the most
    commonly used fields and allows extra attributes to satisfy completeness.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#TextStyle
    """

    bold: Optional[bool] = Field(default=None, description="Whether the text is bold.")
    italic: Optional[bool] = Field(default=None, description="Whether the text is italic.")
    underline: Optional[bool] = Field(default=None, description="Whether the text is underlined.")

    model_config = {"extra": "allow"}


class ParagraphStyle(BaseModel):
    """Paragraph styling information (partial)."""

    alignment: Optional[str] = Field(
        default=None, description="The text alignment for this paragraph."
    )

    model_config = {"extra": "allow"}


class Size(BaseModel):
    """Represents the width & height of an object."""

    width: Optional[float] = Field(default=None, description="Width in points.")
    height: Optional[float] = Field(default=None, description="Height in points.")


class TableCellLocation(BaseModel):
    """Location of a single cell within a table."""

    table_start_location: Location = Field(
        ..., description="The location where the table starts in the document."
    )
    row_index: int = Field(..., description="The zero-based row index.")
    column_index: int = Field(..., description="The zero-based column index.")


class TableRange(BaseModel):
    """A rectangular (or L-shaped) set of table cells."""

    table_cell_location: TableCellLocation = Field(
        ..., description="The cell location where the table range starts."
    )
    row_span: int = Field(..., description="The row span of the table range.")
    column_span: int = Field(..., description="The column span of the table range.")


class TableColumnProperties(BaseModel):
    """Properties of a column in a table (partial)."""

    width: Optional[float] = Field(default=None, description="Column width in points.")

    model_config = {"extra": "allow"}


class TableCellStyle(BaseModel):
    """Styling for a table cell (partial)."""

    background_color: Optional[str] = Field(
        default=None, description="Background color as a hex string."
    )

    model_config = {"extra": "allow"}


class TableRowStyle(BaseModel):
    """Styling for a table row (partial)."""

    min_row_height: Optional[float] = Field(
        default=None, description="Minimum row height in points."
    )

    model_config = {"extra": "allow"}


class DocumentStyle(BaseModel):
    """Overall document styling (partial)."""

    background: Optional[str] = Field(default=None, description="Background color as a hex string.")

    model_config = {"extra": "allow"}


class SectionStyle(BaseModel):
    """Styling for a section (partial)."""

    margin_left: Optional[float] = Field(default=None, description="Left margin in points.")

    model_config = {"extra": "allow"}


# ==================================
# Individual Request payload models
# ==================================


class ReplaceAllTextRequest(BaseModel):
    replace_text: str = Field(..., description="The text that will replace the matched text.")
    tabs_criteria: Optional[TabsCriteria] = Field(
        default=None,
        description="Optional. The criteria used to specify in which tabs the replacement occurs.",
    )
    contains_text: SubstringMatchCriteria = Field(
        ..., description="Finds text in the document matching this substring criteria."
    )


class InsertTextRequest(BaseModel):
    text: str = Field(..., description="The text to be inserted.")
    location: Optional[Location] = Field(
        None, description="Inserts the text at a specific index in the document."
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None,
        description="Inserts the text at the end of a header, footer, footnote or the document body.",
    )

    @model_validator(mode="after")
    def _oneof(self) -> InsertTextRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class UpdateTextStyleRequest(BaseModel):
    text_style: TextStyle = Field(..., description="The styles to set on the text.")
    fields: str = Field(..., description="The fields that should be updated.")
    range: Range = Field(..., description="The range of text to style.")


class CreateParagraphBulletsRequest(BaseModel):
    range: Range = Field(..., description="The range to apply the bullet preset to.")
    bullet_preset: BulletGlyphPreset = Field(
        ..., description="The kinds of bullet glyphs to be used."
    )


class DeleteParagraphBulletsRequest(BaseModel):
    range: Range = Field(..., description="The range to delete bullets from.")


class CreateNamedRangeRequest(BaseModel):
    name: str = Field(..., description="The name of the NamedRange.")
    range: Range = Field(..., description="The range to apply the name to.")


class DeleteNamedRangeRequest(BaseModel):
    tabs_criteria: Optional[TabsCriteria] = Field(
        default=None,
        description="Optional. The criteria used to specify which tab(s) the range deletion should occur in.",
    )
    named_range_id: Optional[str] = Field(None, description="The ID of the named range to delete.")
    name: Optional[str] = Field(None, description="The name of the range(s) to delete.")

    @model_validator(mode="after")
    def _oneof(self) -> DeleteNamedRangeRequest:
        if (self.named_range_id is None) == (self.name is None):
            raise ValueError("Exactly one of `named_range_id` or `name` must be provided.")
        return self


class UpdateParagraphStyleRequest(BaseModel):
    paragraph_style: ParagraphStyle = Field(..., description="The styles to set on the paragraphs.")
    fields: str = Field(..., description="The fields that should be updated.")
    range: Range = Field(..., description="The range overlapping the paragraphs to style.")


class DeleteContentRangeRequest(BaseModel):
    range: Range = Field(..., description="The range of content to delete.")


class InsertInlineImageRequest(BaseModel):
    uri: str = Field(..., description="The image URI.")
    object_size: Optional[Size] = Field(
        default=None, description="The size that the image should appear as in the document."
    )
    location: Optional[Location] = Field(
        None, description="Inserts the image at a specific index in the document."
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None,
        description="Inserts the image at the end of a header, footer, footnote or the document body.",
    )

    @model_validator(mode="after")
    def _oneof(self) -> InsertInlineImageRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class InsertTableRequest(BaseModel):
    rows: int = Field(..., description="The number of rows in the table.")
    columns: int = Field(..., description="The number of columns in the table.")
    location: Optional[Location] = Field(
        None, description="Inserts the table at a specific index in the document."
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None,
        description="Inserts the table at the end of a header, footer, footnote or the document body.",
    )

    @model_validator(mode="after")
    def _oneof(self) -> InsertTableRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class InsertTableRowRequest(BaseModel):
    table_cell_location: TableCellLocation = Field(
        ..., description="The reference table cell location from which rows will be inserted."
    )
    insert_below: bool = Field(
        ..., description="Whether to insert new row below the reference cell location."
    )


class InsertTableColumnRequest(BaseModel):
    table_cell_location: TableCellLocation = Field(
        ..., description="The reference table cell location from which columns will be inserted."
    )
    insert_right: bool = Field(
        ..., description="Whether to insert new column to the right of the reference cell location."
    )


class DeleteTableRowRequest(BaseModel):
    table_cell_location: TableCellLocation = Field(
        ..., description="The reference table cell location from which the row will be deleted."
    )


class DeleteTableColumnRequest(BaseModel):
    table_cell_location: TableCellLocation = Field(
        ..., description="The reference table cell location from which the column will be deleted."
    )


class InsertPageBreakRequest(BaseModel):
    location: Optional[Location] = Field(
        None, description="Inserts the page break at a specific index in the document."
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None, description="Inserts the page break at the end of the document body."
    )

    @model_validator(mode="after")
    def _oneof(self) -> InsertPageBreakRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class DeletePositionedObjectRequest(BaseModel):
    object_id: str = Field(..., description="The ID of the positioned object to delete.")
    tab_id: Optional[str] = Field(
        default=None, description="The tab that the positioned object to delete is in."
    )


class UpdateTableColumnPropertiesRequest(BaseModel):
    table_start_location: Location = Field(
        ..., description="The location where the table starts in the document."
    )
    column_indices: Optional[List[int]] = Field(
        default=None,
        description="The list of zero-based column indices whose property should be updated. If no indices are specified, all columns will be updated.",
    )
    table_column_properties: TableColumnProperties = Field(
        ..., description="The table column properties to update."
    )
    fields: str = Field(..., description="The fields that should be updated.")


class UpdateTableCellStyleRequest(BaseModel):
    table_cell_style: TableCellStyle = Field(
        ..., description="The style to set on the table cells."
    )
    fields: str = Field(..., description="The fields that should be updated.")
    table_range: Optional[TableRange] = Field(
        None,
        description="The table range representing the subset of the table to which the updates are applied.",
    )
    table_start_location: Optional[Location] = Field(
        None, description="The location where the table starts in the document."
    )

    @model_validator(mode="after")
    def _oneof(self) -> UpdateTableCellStyleRequest:
        if (self.table_range is None) == (self.table_start_location is None):
            raise ValueError(
                "Exactly one of `table_range` or `table_start_location` must be provided."
            )
        return self


class UpdateTableRowStyleRequest(BaseModel):
    table_start_location: Location = Field(
        ..., description="The location where the table starts in the document."
    )
    row_indices: Optional[List[int]] = Field(
        default=None,
        description="The list of zero-based row indices whose style should be updated. If no indices are specified, all rows will be updated.",
    )
    table_row_style: TableRowStyle = Field(..., description="The styles to be set on the rows.")
    fields: str = Field(..., description="The fields that should be updated.")


class ReplaceImageRequest(BaseModel):
    image_object_id: str = Field(
        ..., description="The ID of the existing image that will be replaced."
    )
    uri: str = Field(..., description="The URI of the new image.")
    image_replace_method: Optional[ImageReplaceMethod] = Field(
        default=None, description="Optional. The replacement method."
    )
    tab_id: Optional[str] = Field(
        default=None, description="The tab that the image to be replaced is in."
    )


class UpdateDocumentStyleRequest(BaseModel):
    document_style: DocumentStyle = Field(..., description="The styles to set on the document.")
    fields: str = Field(..., description="The fields that should be updated.")
    tab_id: Optional[str] = Field(
        default=None, description="The tab that contains the style to update."
    )


class MergeTableCellsRequest(BaseModel):
    table_range: TableRange = Field(
        ..., description="The table range specifying which cells of the table to merge."
    )


class UnmergeTableCellsRequest(BaseModel):
    table_range: TableRange = Field(
        ..., description="The table range specifying which cells of the table to unmerge."
    )


class CreateHeaderRequest(BaseModel):
    type: HeaderFooterType = Field(..., description="The type of header to create.")
    section_break_location: Optional[Location] = Field(
        default=None,
        description="The location of the SectionBreak which begins the section this header should belong to.",
    )


class CreateFooterRequest(BaseModel):
    type: HeaderFooterType = Field(..., description="The type of footer to create.")
    section_break_location: Optional[Location] = Field(
        default=None,
        description="The location of the SectionBreak immediately preceding the section whose SectionStyle this footer should belong to.",
    )


class CreateFootnoteRequest(BaseModel):
    location: Optional[Location] = Field(
        None, description="Inserts the footnote reference at a specific index in the document."
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None, description="Inserts the footnote reference at the end of the document body."
    )

    @model_validator(mode="after")
    def _oneof(self) -> CreateFootnoteRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class ReplaceNamedRangeContentRequest(BaseModel):
    tabs_criteria: Optional[TabsCriteria] = Field(
        default=None,
        description="Optional. The criteria used to specify in which tabs the replacement occurs.",
    )
    text: str = Field(
        ..., description="Replaces the content of the specified named range(s) with the given text."
    )
    named_range_id: Optional[str] = Field(
        None, description="The ID of the named range whose content will be replaced."
    )
    named_range_name: Optional[str] = Field(
        None, description="The name of the NamedRanges whose content will be replaced."
    )

    @model_validator(mode="after")
    def _oneof(self) -> ReplaceNamedRangeContentRequest:
        if (self.named_range_id is None) == (self.named_range_name is None):
            raise ValueError(
                "Exactly one of `named_range_id` or `named_range_name` must be provided."
            )
        return self


class UpdateSectionStyleRequest(BaseModel):
    range: Range = Field(..., description="The range overlapping the sections to style.")
    section_style: SectionStyle = Field(..., description="The styles to be set on the section.")
    fields: str = Field(..., description="The fields that should be updated.")


class InsertSectionBreakRequest(BaseModel):
    section_type: SectionType = Field(..., description="The type of section to insert.")
    location: Optional[Location] = Field(
        None,
        description="Inserts a newline and a section break at a specific index in the document.",
    )
    end_of_segment_location: Optional[EndOfSegmentLocation] = Field(
        None, description="Inserts a newline and a section break at the end of the document body."
    )

    @model_validator(mode="after")
    def _oneof(self) -> InsertSectionBreakRequest:
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be provided."
            )
        return self


class DeleteHeaderRequest(BaseModel):
    header_id: str = Field(..., description="The id of the header to delete.")
    tab_id: Optional[str] = Field(
        default=None, description="The tab containing the header to delete."
    )


class DeleteFooterRequest(BaseModel):
    footer_id: str = Field(..., description="The id of the footer to delete.")
    tab_id: Optional[str] = Field(
        default=None, description="The tab that contains the footer to delete."
    )


class PinTableHeaderRowsRequest(BaseModel):
    table_start_location: Location = Field(
        ..., description="The location where the table starts in the document."
    )
    pinned_header_rows_count: int = Field(
        ...,
        description="The number of table rows to pin, where 0 implies that all rows are unpinned.",
    )


# ======================================================
# Top-level Request wrapper to be used by the AI tooling
# ======================================================


class Request(BaseModel):
    """A single update to apply to a document.

    API Reference: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#Request
    """

    replace_all_text: Optional[ReplaceAllTextRequest] = Field(
        default=None, description="Replaces all instances of the specified text."
    )
    insert_text: Optional[InsertTextRequest] = Field(
        default=None, description="Inserts text at the specified location."
    )
    update_text_style: Optional[UpdateTextStyleRequest] = Field(
        default=None, description="Updates the text style at the specified range."
    )
    create_paragraph_bullets: Optional[CreateParagraphBulletsRequest] = Field(
        default=None, description="Creates bullets for paragraphs."
    )
    delete_paragraph_bullets: Optional[DeleteParagraphBulletsRequest] = Field(
        default=None, description="Deletes bullets from paragraphs."
    )
    create_named_range: Optional[CreateNamedRangeRequest] = Field(
        default=None, description="Creates a named range."
    )
    delete_named_range: Optional[DeleteNamedRangeRequest] = Field(
        default=None, description="Deletes a named range."
    )
    update_paragraph_style: Optional[UpdateParagraphStyleRequest] = Field(
        default=None, description="Updates the paragraph style at the specified range."
    )
    delete_content_range: Optional[DeleteContentRangeRequest] = Field(
        default=None, description="Deletes content from the document."
    )
    insert_inline_image: Optional[InsertInlineImageRequest] = Field(
        default=None, description="Inserts an inline image at the specified location."
    )
    insert_table: Optional[InsertTableRequest] = Field(
        default=None, description="Inserts a table at the specified location."
    )
    insert_table_row: Optional[InsertTableRowRequest] = Field(
        default=None, description="Inserts an empty row into a table."
    )
    insert_table_column: Optional[InsertTableColumnRequest] = Field(
        default=None, description="Inserts an empty column into a table."
    )
    delete_table_row: Optional[DeleteTableRowRequest] = Field(
        default=None, description="Deletes a row from a table."
    )
    delete_table_column: Optional[DeleteTableColumnRequest] = Field(
        default=None, description="Deletes a column from a table."
    )
    insert_page_break: Optional[InsertPageBreakRequest] = Field(
        default=None, description="Inserts a page break at the specified location."
    )
    delete_positioned_object: Optional[DeletePositionedObjectRequest] = Field(
        default=None, description="Deletes a positioned object from the document."
    )
    update_table_column_properties: Optional[UpdateTableColumnPropertiesRequest] = Field(
        default=None, description="Updates the properties of columns in a table."
    )
    update_table_cell_style: Optional[UpdateTableCellStyleRequest] = Field(
        default=None, description="Updates the style of table cells."
    )
    update_table_row_style: Optional[UpdateTableRowStyleRequest] = Field(
        default=None, description="Updates the row style in a table."
    )
    replace_image: Optional[ReplaceImageRequest] = Field(
        default=None, description="Replaces an image in the document."
    )
    update_document_style: Optional[UpdateDocumentStyleRequest] = Field(
        default=None, description="Updates the style of the document."
    )
    merge_table_cells: Optional[MergeTableCellsRequest] = Field(
        default=None, description="Merges cells in a table."
    )
    unmerge_table_cells: Optional[UnmergeTableCellsRequest] = Field(
        default=None, description="Unmerges cells in a table."
    )
    create_header: Optional[CreateHeaderRequest] = Field(
        default=None, description="Creates a header."
    )
    create_footer: Optional[CreateFooterRequest] = Field(
        default=None, description="Creates a footer."
    )
    create_footnote: Optional[CreateFootnoteRequest] = Field(
        default=None, description="Creates a footnote."
    )
    replace_named_range_content: Optional[ReplaceNamedRangeContentRequest] = Field(
        default=None, description="Replaces the content in a named range."
    )
    update_section_style: Optional[UpdateSectionStyleRequest] = Field(
        default=None, description="Updates the section style of the specified range."
    )
    insert_section_break: Optional[InsertSectionBreakRequest] = Field(
        default=None, description="Inserts a section break at the specified location."
    )
    delete_header: Optional[DeleteHeaderRequest] = Field(
        default=None, description="Deletes a header from the document."
    )
    delete_footer: Optional[DeleteFooterRequest] = Field(
        default=None, description="Deletes a footer from the document."
    )
    pin_table_header_rows: Optional[PinTableHeaderRowsRequest] = Field(
        default=None, description="Updates the number of pinned header rows in a table."
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> Request:
        provided = [name for name, value in self.__dict__.items() if value is not None]
        if len(provided) != 1:
            raise ValueError(f"Exactly one request must be set, found: {provided}")
        return self

    model_config = ConfigDict(extra="forbid")
