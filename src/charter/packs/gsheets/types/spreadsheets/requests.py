# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The ``batchUpdate`` request union — every edit Google Sheets can apply.

``spreadsheets.batchUpdate`` takes a list of ``Request`` objects, each of which
is a *oneof*: exactly one kind of update must be set, and setting two is an
error the API reports as a 400 with no useful detail. That constraint is a
``model_validator`` on ``Request`` and on the nested edits that have a oneof of
their own.

The five comment edits (``insert_comment`` and neighbours) are Developer
Preview. They are modelled because the reference documents them; the API may
refuse them outside the preview program.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from charter.packs.gsheets.types.spreadsheets.models import (
    BandedRange,
    BasicFilter,
    Border,
    CellData,
    ChartSpec,
    ConditionalFormatRule,
    DataFilter,
    DataSource,
    DataSourceColumnReference,
    DataSourceObjectReferences,
    DataValidationRule,
    DelimiterType,
    DeveloperMetadata,
    Dimension,
    DimensionGroup,
    DimensionProperties,
    DimensionRange,
    EmbeddedChart,
    EmbeddedObjectBorder,
    EmbeddedObjectPosition,
    FilterView,
    GridCoordinate,
    GridRange,
    MergeType,
    NamedRange,
    PasteOrientation,
    PasteType,
    Post,
    ProtectedRange,
    RowData,
    SheetProperties,
    Slicer,
    SlicerSpec,
    SortSpec,
    SpreadsheetProperties,
    Table,
)
from charter.types import FieldMask, Format


class AddBandingRequest(BaseModel):
    """
    Adds a new banded range to the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddBandingRequest
    """

    banded_range: Optional[BandedRange] = Field(
        default=None,
        description="The banded range to add. The bandedRangeId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of a range that already exists.)",
    )


class AddChartRequest(BaseModel):
    """
    Adds a chart to a sheet in the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddChartRequest
    """

    chart: Optional[EmbeddedChart] = Field(
        default=None,
        description="The chart that should be added to the spreadsheet, including the position where it should be placed. The chartId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of an embedded object that already exists.)",
    )


class AddConditionalFormatRuleRequest(BaseModel):
    """
    Adds a new conditional format rule at the given index. All subsequent rules' indexes are incremented.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddConditionalFormatRuleRequest
    """

    index: Optional[int] = Field(
        default=None,
        description="The zero-based index where the rule should be inserted.",
    )

    rule: Optional[ConditionalFormatRule] = Field(
        default=None,
        description="The rule to add.",
    )


class AddDataSourceRequest(BaseModel):
    """
    Adds a data source. After the data source is added successfully, an associated DATA_SOURCE sheet is created and an execution is triggered to refresh the sheet to read data from the data source. The request requires an additional `bigquery.readonly` OAuth scope if you are adding a BigQuery data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddDataSourceRequest
    """

    data_source: Optional[DataSource] = Field(
        default=None,
        description="The data source to add.",
    )


class AddDimensionGroupRequest(BaseModel):
    """
    Creates a group over the specified range. If the requested range is a superset of the range of an existing group G, then the depth of G is incremented and this new group G' has the depth of that group. For example, a group [C:D, depth 1] + [B:E] results in groups [B:E, depth 1] and [C:D, depth 2]. If the requested range is a subset of the range of an existing group G, then the depth of the new group G' becomes one greater than the depth of G. For example, a group [B:E, depth 1] + [C:D] results in groups [B:E, depth 1] and [C:D, depth 2]. If the requested range starts before and ends within, or starts within and ends after, the range of an existing group G, then the range of the existing group G becomes the union of the ranges, and the new group G' has depth one greater than the depth of G and range as the intersection of the ranges. For example, a group [B:D, depth 1] + [C:E] results in groups [B:E, depth 1] and [C:D, depth 2].

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddDimensionGroupRequest
    """

    range: Optional[DimensionRange] = Field(
        default=None,
        description="The range over which to create a group.",
    )


class AddFilterViewRequest(BaseModel):
    """
    Adds a filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddFilterViewRequest
    """

    filter: Optional[FilterView] = Field(
        default=None,
        description="The filter to add. The filterViewId field is optional. If one is not set, an ID will be randomly generated. (It is an error to specify the ID of a filter that already exists.)",
    )


class AddNamedRangeRequest(BaseModel):
    """
    Adds a named range to the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddNamedRangeRequest
    """

    named_range: Optional[NamedRange] = Field(
        default=None,
        description="The named range to add. The namedRangeId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of a range that already exists.)",
    )


class AddProtectedRangeRequest(BaseModel):
    """
    Adds a new protected range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddProtectedRangeRequest
    """

    protected_range: Optional[ProtectedRange] = Field(
        default=None,
        description="The protected range to be added. The protectedRangeId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of a range that already exists.)",
    )


class AddSheetRequest(BaseModel):
    """
    Adds a new sheet. When a sheet is added at a given index, all subsequent sheets' indexes are incremented. To add an object sheet, use AddChartRequest instead and specify EmbeddedObjectPosition.sheetId or EmbeddedObjectPosition.newSheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddSheetRequest
    """

    properties: Optional[SheetProperties] = Field(
        default=None,
        description="The properties the new sheet should have. All properties are optional. The sheetId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of a sheet that already exists.)",
    )


class AddSlicerRequest(BaseModel):
    """
    Adds a slicer to a sheet in the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddSlicerRequest
    """

    slicer: Optional[Slicer] = Field(
        default=None,
        description="The slicer that should be added to the spreadsheet, including the position where it should be placed. The slicerId field is optional; if one is not set, an id will be randomly generated. (It is an error to specify the ID of a slicer that already exists.)",
    )


class AddTableRequest(BaseModel):
    """
    Adds a new table to the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddTableRequest
    """

    table: Optional[Table] = Field(
        default=None,
        description="Required. The table to add.",
    )


class AppendCellsRequest(BaseModel):
    """
    Adds new cells after the last row with data in a sheet, inserting new rows into the sheet if necessary.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AppendCellsRequest
    """

    table_id: Optional[str] = Field(
        default=None,
        description="The ID of the table to append data to. The data will be only appended to the table body. This field also takes precedence over the `sheet_id` field.",
    )

    rows: Optional[List[RowData]] = Field(
        default=None,
        description="The data to append.",
    )

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet ID to append the data to.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description="The fields of CellData that should be updated. At least one field must be specified. The root is the CellData; 'row.values.' should not be specified. A single `\"*\"` can be used as short-hand for listing every field.",
        ),
    ] = None


class AppendDimensionRequest(BaseModel):
    """
    Appends rows or columns to the end of a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AppendDimensionRequest
    """

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet to append rows or columns to.",
    )

    dimension: Optional[Dimension] = Field(
        default=None,
        description="Whether rows or columns should be appended.",
    )

    length: Optional[int] = Field(
        default=None,
        description="The number of rows or columns to append.",
    )


class AutoFillRequest(BaseModel):
    """
    Fills in more data based on existing data.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AutoFillRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to autofill. This will examine the range and detect the location that has data and automatically fill that data in to the rest of the range.",
    )

    source_and_destination: Optional[SourceAndDestination] = Field(
        default=None,
        description="The source and destination areas to autofill. This explicitly lists the source of the autofill and where to extend that data.",
    )

    use_alternate_series: Optional[bool] = Field(
        default=None,
        description='True if we should generate data with the "alternate" series. This differs based on the type and amount of source data.',
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> AutoFillRequest:
        provided = [n for n in ("range", "source_and_destination") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'range', 'source_and_destination' must be set, found: {provided}"
            )
        return self


class AutoResizeDimensionsRequest(BaseModel):
    """
    Automatically resizes one or more dimensions based on the contents of the cells in that dimension.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AutoResizeDimensionsRequest
    """

    dimensions: Optional[DimensionRange] = Field(
        default=None,
        description="The dimensions to automatically resize.",
    )

    data_source_sheet_dimensions: Optional[DataSourceSheetDimensionRange] = Field(
        default=None,
        description="The dimensions on a data source sheet to automatically resize.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> AutoResizeDimensionsRequest:
        provided = [
            n
            for n in ("dimensions", "data_source_sheet_dimensions")
            if getattr(self, n) is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'dimensions', 'data_source_sheet_dimensions' must be set, found: {provided}"
            )
        return self


class CancelDataSourceRefreshRequest(BaseModel):
    """
    Cancels one or multiple refreshes of data source objects in the spreadsheet by the specified references. The request requires an additional `bigquery.readonly` OAuth scope if you are cancelling a refresh on a BigQuery data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#CancelDataSourceRefreshRequest
    """

    is_all: Optional[bool] = Field(
        default=None,
        description="Cancels all existing data source object refreshes for all data sources in the spreadsheet.",
    )

    references: Optional[DataSourceObjectReferences] = Field(
        default=None,
        description="References to data source objects whose refreshes are to be cancelled.",
    )

    data_source_id: Optional[str] = Field(
        default=None,
        description="Reference to a DataSource. If specified, cancels all associated data source object refreshes for this data source.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> CancelDataSourceRefreshRequest:
        provided = [
            n for n in ("references", "data_source_id", "is_all") if getattr(self, n) is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'references', 'data_source_id', 'is_all' must be set, found: {provided}"
            )
        return self


class ClearBasicFilterRequest(BaseModel):
    """
    Clears the basic filter, if any exists on the sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#ClearBasicFilterRequest
    """

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet ID on which the basic filter should be cleared.",
    )


class CopyPasteRequest(BaseModel):
    """
    Copies data from the source to the destination.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#CopyPasteRequest
    """

    destination: Optional[GridRange] = Field(
        default=None,
        description="The location to paste to. If the range covers a span that's a multiple of the source's height or width, then the data will be repeated to fill in the destination range. If the range is smaller than the source range, the entire source data will still be copied (beyond the end of the destination range).",
    )

    paste_orientation: Optional[PasteOrientation] = Field(
        default=None,
        description="How that data should be oriented when pasting.",
    )

    paste_type: Optional[PasteType] = Field(
        default=None,
        description="What kind of data to paste.",
    )

    source: Optional[GridRange] = Field(
        default=None,
        description="The source range to copy.",
    )


class CreateDeveloperMetadataRequest(BaseModel):
    """
    A request to create developer metadata.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#CreateDeveloperMetadataRequest
    """

    developer_metadata: Optional[DeveloperMetadata] = Field(
        default=None,
        description="The developer metadata to create.",
    )


class CutPasteRequest(BaseModel):
    """
    Moves data from the source to the destination.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#CutPasteRequest
    """

    destination: Optional[GridCoordinate] = Field(
        default=None,
        description="The top-left coordinate where the data should be pasted.",
    )

    paste_type: Optional[PasteType] = Field(
        default=None,
        description="What kind of data to paste. All the source data will be cut, regardless of what is pasted.",
    )

    source: Optional[GridRange] = Field(
        default=None,
        description="The source data to cut.",
    )


class DataSourceSheetDimensionRange(BaseModel):
    """
    A range along a single dimension on a DATA_SOURCE sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DataSourceSheetDimensionRange
    """

    column_references: Optional[List[DataSourceColumnReference]] = Field(
        default=None,
        description="The columns on the data source sheet.",
    )

    sheet_id: Optional[int] = Field(
        default=None,
        description="The ID of the data source sheet the range is on.",
    )


class DeleteBandingRequest(BaseModel):
    """
    Removes the banded range with the given ID from the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteBandingRequest
    """

    banded_range_id: Optional[int] = Field(
        default=None,
        description="The ID of the banded range to delete.",
    )


class DeleteConditionalFormatRuleRequest(BaseModel):
    """
    Deletes a conditional format rule at the given index. All subsequent rules' indexes are decremented.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteConditionalFormatRuleRequest
    """

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet the rule is being deleted from.",
    )

    index: Optional[int] = Field(
        default=None,
        description="The zero-based index of the rule to be deleted.",
    )


class DeleteDataSourceRequest(BaseModel):
    """
    Deletes a data source. The request also deletes the associated data source sheet, and unlinks all associated data source objects.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteDataSourceRequest
    """

    data_source_id: Optional[str] = Field(
        default=None,
        description="The ID of the data source to delete.",
    )


class DeleteDeveloperMetadataRequest(BaseModel):
    """
    A request to delete developer metadata.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteDeveloperMetadataRequest
    """

    data_filter: Optional[DataFilter] = Field(
        default=None,
        description="The data filter describing the criteria used to select which developer metadata entry to delete.",
    )


class DeleteDimensionGroupRequest(BaseModel):
    """
    Deletes a group over the specified range by decrementing the depth of the dimensions in the range. For example, assume the sheet has a depth-1 group over B:E and a depth-2 group over C:D. Deleting a group over D:E leaves the sheet with a depth-1 group over B:D and a depth-2 group over C:C.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteDimensionGroupRequest
    """

    range: Optional[DimensionRange] = Field(
        default=None,
        description="The range of the group to be deleted.",
    )


class DeleteDimensionRequest(BaseModel):
    """
     Deletes the dimensions from the sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteDimensionRequest
    """

    range: Optional[DimensionRange] = Field(
        default=None,
        description="The dimensions to delete from the sheet.",
    )


class DeleteDuplicatesRequest(BaseModel):
    """
    Removes rows within this range that contain values in the specified columns that are duplicates of values in any previous row. Rows with identical values but different letter cases, formatting, or formulas are considered to be duplicates. This request also removes duplicate rows hidden from view (for example, due to a filter). When removing duplicates, the first instance of each duplicate row scanning from the top downwards is kept in the resulting range. Content outside of the specified range isn't removed, and rows considered duplicates do not have to be adjacent to each other in the range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteDuplicatesRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to remove duplicates rows from.",
    )

    comparison_columns: Optional[List[DimensionRange]] = Field(
        default=None,
        description="The columns in the range to analyze for duplicate values. If no columns are selected then all columns are analyzed for duplicates.",
    )


class DeleteEmbeddedObjectRequest(BaseModel):
    """
    Deletes the embedded object with the given ID.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteEmbeddedObjectRequest
    """

    object_id: Optional[int] = Field(
        default=None,
        description="The ID of the embedded object to delete.",
    )


class DeleteFilterViewRequest(BaseModel):
    """
    Deletes a particular filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteFilterViewRequest
    """

    filter_id: Optional[int] = Field(
        default=None,
        description="The ID of the filter to delete.",
    )


class DeleteNamedRangeRequest(BaseModel):
    """
    Removes the named range with the given ID from the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteNamedRangeRequest
    """

    named_range_id: Optional[str] = Field(
        default=None,
        description="The ID of the named range to delete.",
    )


class DeleteProtectedRangeRequest(BaseModel):
    """
    Deletes the protected range with the given ID.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteProtectedRangeRequest
    """

    protected_range_id: Optional[int] = Field(
        default=None,
        description="The ID of the protected range to delete.",
    )


class DeleteRangeRequest(BaseModel):
    """
    Deletes a range of cells, shifting other cells into the deleted area.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteRangeRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range of cells to delete.",
    )

    shift_dimension: Optional[Dimension] = Field(
        default=None,
        description="The dimension from which deleted cells will be replaced with. If ROWS, existing cells will be shifted upward to replace the deleted cells. If COLUMNS, existing cells will be shifted left to replace the deleted cells.",
    )


class DeleteSheetRequest(BaseModel):
    """
    Deletes the requested sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteSheetRequest
    """

    sheet_id: Optional[int] = Field(
        default=None,
        description="The ID of the sheet to delete. If the sheet is of DATA_SOURCE type, the associated DataSource is also deleted.",
    )


class DeleteTableRequest(BaseModel):
    """
    Removes the table with the given ID from the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteTableRequest
    """

    table_id: Optional[str] = Field(
        default=None,
        description="The ID of the table to delete.",
    )


class DuplicateFilterViewRequest(BaseModel):
    """
    Duplicates a particular filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DuplicateFilterViewRequest
    """

    filter_id: Optional[int] = Field(
        default=None,
        description="The ID of the filter being duplicated.",
    )


class DuplicateSheetRequest(BaseModel):
    """
    Duplicates the contents of a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DuplicateSheetRequest
    """

    source_sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet to duplicate. If the source sheet is of DATA_SOURCE type, its backing DataSource is also duplicated and associated with the new copy of the sheet. No data execution is triggered, the grid data of this sheet is also copied over but only available after the batch request completes.",
    )

    insert_sheet_index: Optional[int] = Field(
        default=None,
        description="The zero-based index where the new sheet should be inserted. The index of all sheets after this are incremented.",
    )

    new_sheet_id: Optional[int] = Field(
        default=None,
        ge=0,
        description="If set, the ID of the new sheet. If not set, an ID is chosen. If set, the ID must not conflict with any existing sheet ID. If set, it must be non-negative.",
    )

    new_sheet_name: Optional[str] = Field(
        default=None,
        description="The name of the new sheet. If empty, a new name is chosen for you.",
    )


class FindReplaceRequest(BaseModel):
    """
    Finds and replaces data in cells over a range, sheet, or all sheets.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#FindReplaceRequest
    """

    match_case: Optional[bool] = Field(
        default=None,
        description="True if the search is case sensitive.",
    )

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to find/replace over.",
    )

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet to find/replace over.",
    )

    find: Optional[str] = Field(
        default=None,
        description="The value to search.",
    )

    search_by_regex: Optional[bool] = Field(
        default=None,
        description='True if the find value is a regex. The regular expression and replacement should follow Java regex rules at https://docs.oracle.com/javase/8/docs/api/java/util/regex/Pattern.html. The replacement string is allowed to refer to capturing groups. For example, if one cell has the contents `"Google Sheets"` and another has `"Google Docs"`, then searching for `"o.* (.*)"` with a replacement of `"$1 Rocks"` would change the contents of the cells to `"GSheets Rocks"` and `"GDocs Rocks"` respectively.',
    )

    include_formulas: Optional[bool] = Field(
        default=None,
        description="True if the search should include cells with formulas. False to skip cells with formulas.",
    )

    replacement: Optional[str] = Field(
        default=None,
        description="The value to use as the replacement.",
    )

    all_sheets: Optional[bool] = Field(
        default=None,
        description="True to find/replace over all sheets.",
    )

    match_entire_cell: Optional[bool] = Field(
        default=None,
        description="True if the find value should match the entire cell.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> FindReplaceRequest:
        provided = [n for n in ("range", "sheet_id", "all_sheets") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'range', 'sheet_id', 'all_sheets' must be set, found: {provided}"
            )
        return self


class InsertDimensionRequest(BaseModel):
    """
    Inserts rows or columns in a sheet at a particular index.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#InsertDimensionRequest
    """

    inherit_from_before: Optional[bool] = Field(
        default=None,
        description="Whether dimension properties should be extended from the dimensions before or after the newly inserted dimensions. True to inherit from the dimensions before (in which case the start index must be greater than 0), and false to inherit from the dimensions after. For example, if row index 0 has red background and row index 1 has a green background, then inserting 2 rows at index 1 can inherit either the green or red background. If `inheritFromBefore` is true, the two new rows will be red (because the row before the insertion point was red), whereas if `inheritFromBefore` is false, the two new rows will be green (because the row after the insertion point was green).",
    )

    range: Optional[DimensionRange] = Field(
        default=None,
        description="The dimensions to insert. Both the start and end indexes must be bounded.",
    )


class InsertRangeRequest(BaseModel):
    """
    Inserts cells into a range, shifting the existing cells over or down.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#InsertRangeRequest
    """

    shift_dimension: Optional[Dimension] = Field(
        default=None,
        description="The dimension which will be shifted when inserting cells. If ROWS, existing cells will be shifted down. If COLUMNS, existing cells will be shifted right.",
    )

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to insert new cells into. The range is constrained to the current sheet boundaries.",
    )


class MergeCellsRequest(BaseModel):
    """
    Merges all cells in the range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#MergeCellsRequest
    """

    merge_type: Optional[MergeType] = Field(
        default=None,
        description="How the cells should be merged.",
    )

    range: Optional[GridRange] = Field(
        default=None,
        description="The range of cells to merge.",
    )


class MoveDimensionRequest(BaseModel):
    """
    Moves one or more rows or columns.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#MoveDimensionRequest
    """

    source: Optional[DimensionRange] = Field(
        default=None,
        description="The source dimensions to move.",
    )

    destination_index: Optional[int] = Field(
        default=None,
        description='The zero-based start index of where to move the source data to, based on the coordinates *before* the source data is removed from the grid. Existing data will be shifted down or right (depending on the dimension) to make room for the moved dimensions. The source dimensions are removed from the grid, so the the data may end up in a different index than specified. For example, given `A1..A5` of `0, 1, 2, 3, 4` and wanting to move `"1"` and `"2"` to between `"3"` and `"4"`, the source would be `ROWS [1..3)`,and the destination index would be `"4"` (the zero-based index of row 5). The end result would be `A1..A5` of `0, 3, 1, 2, 4`.',
    )


class PasteDataRequest(BaseModel):
    """
    Inserts data into the spreadsheet starting at the specified coordinate.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#PasteDataRequest
    """

    data: Optional[str] = Field(
        default=None,
        description="The data to insert.",
    )

    type: Optional[PasteType] = Field(
        default=None,
        description="How the data should be pasted.",
    )

    coordinate: Optional[GridCoordinate] = Field(
        default=None,
        description="The coordinate at which the data should start being inserted.",
    )

    delimiter: Optional[str] = Field(
        default=None,
        description="The delimiter in the data.",
    )

    html: Optional[bool] = Field(
        default=None,
        description="True if the data is HTML.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> PasteDataRequest:
        provided = [n for n in ("delimiter", "html") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(f"Exactly one of 'delimiter', 'html' must be set, found: {provided}")
        return self


class RandomizeRangeRequest(BaseModel):
    """
    Randomizes the order of the rows in a range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#RandomizeRangeRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to randomize.",
    )


class RefreshDataSourceRequest(BaseModel):
    """
    Refreshes one or multiple data source objects in the spreadsheet by the specified references. The request requires an additional `bigquery.readonly` OAuth scope if you are refreshing a BigQuery data source. If there are multiple refresh requests referencing the same data source objects in one batch, only the last refresh request is processed, and all those requests will have the same response accordingly.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#RefreshDataSourceRequest
    """

    references: Optional[DataSourceObjectReferences] = Field(
        default=None,
        description="References to data source objects to refresh.",
    )

    data_source_id: Optional[str] = Field(
        default=None,
        description="Reference to a DataSource. If specified, refreshes all associated data source objects for the data source.",
    )

    is_all: Optional[bool] = Field(
        default=None,
        description="Refreshes all existing data source objects in the spreadsheet.",
    )

    force: Optional[bool] = Field(
        default=None,
        description="Refreshes the data source objects regardless of the current state. If not set and a referenced data source object was in error state, the refresh will fail immediately.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> RefreshDataSourceRequest:
        provided = [
            n for n in ("references", "data_source_id", "is_all") if getattr(self, n) is not None
        ]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'references', 'data_source_id', 'is_all' must be set, found: {provided}"
            )
        return self


class RepeatCellRequest(BaseModel):
    """
    Updates all cells in the range to the values in the given Cell object. Only the fields listed in the fields field are updated; others are unchanged. If writing a cell with a formula, the formula's ranges will automatically increment for each field in the range. For example, if writing a cell with formula `=A1` into range B2:C4, B2 would be `=A1`, B3 would be `=A2`, B4 would be `=A3`, C2 would be `=B1`, C3 would be `=B2`, C4 would be `=B3`. To keep the formula's ranges static, use the `$` indicator. For example, use the formula `=$A$1` to prevent both the row and the column from incrementing.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#RepeatCellRequest
    """

    cell: Optional[CellData] = Field(
        default=None,
        description="The data to write.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `cell` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to repeat the cell in.",
    )


class SetBasicFilterRequest(BaseModel):
    """
    Sets the basic filter associated with a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#SetBasicFilterRequest
    """

    filter: Optional[BasicFilter] = Field(
        default=None,
        description="The filter to set.",
    )


class SetDataValidationRequest(BaseModel):
    """
    Sets a data validation rule to every cell in the range. To clear validation in a range, call this with no rule specified.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#SetDataValidationRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range the data validation rule should apply to.",
    )

    rule: Optional[DataValidationRule] = Field(
        default=None,
        description="The data validation rule to set on each cell in the range, or empty to clear the data validation in the range.",
    )

    filtered_rows_included: Optional[bool] = Field(
        default=None,
        description="Optional. If true, the data validation rule will be applied to the filtered rows as well.",
    )


class SortRangeRequest(BaseModel):
    """
    Sorts data in rows based on a sort order per column.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#SortRangeRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to sort.",
    )

    sort_specs: Optional[List[SortSpec]] = Field(
        default=None,
        description="The sort order per column. Later specifications are used when values are equal in the earlier specifications.",
    )


class SourceAndDestination(BaseModel):
    """
    A combination of a source range and how to extend that source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#SourceAndDestination
    """

    source: Optional[GridRange] = Field(
        default=None,
        description="The location of the data to use as the source of the autofill.",
    )

    dimension: Optional[Dimension] = Field(
        default=None,
        description="The dimension that data should be filled into.",
    )

    fill_length: Optional[int] = Field(
        default=None,
        description="The number of rows or columns that data should be filled into. Positive numbers expand beyond the last row or last column of the source. Negative numbers expand before the first row or first column of the source.",
    )


class TextToColumnsRequest(BaseModel):
    """
    Splits a column of text into multiple columns, based on a delimiter in each cell.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#TextToColumnsRequest
    """

    delimiter_type: Optional[DelimiterType] = Field(
        default=None,
        description="The delimiter type to use.",
    )

    source: Optional[GridRange] = Field(
        default=None,
        description="The source data range. This must span exactly one column.",
    )

    delimiter: Optional[str] = Field(
        default=None,
        description="The delimiter to use. Used only if delimiterType is CUSTOM.",
    )


class TrimWhitespaceRequest(BaseModel):
    """
    Trims the whitespace (such as spaces, tabs, or new lines) in every cell in the specified range. This request removes all whitespace from the start and end of each cell's text, and reduces any subsequence of remaining whitespace characters to a single space. If the resulting trimmed text starts with a '+' or '=' character, the text remains as a string value and isn't interpreted as a formula.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#TrimWhitespaceRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range whose cells to trim.",
    )


class UnmergeCellsRequest(BaseModel):
    """
    Unmerges cells in the given range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UnmergeCellsRequest
    """

    range: Optional[GridRange] = Field(
        default=None,
        description="The range within which all cells should be unmerged. If the range spans multiple merges, all will be unmerged. The range must not partially span any merge.",
    )


class UpdateBandingRequest(BaseModel):
    """
    Updates properties of the supplied banded range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateBandingRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `bandedRange` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    banded_range: Optional[BandedRange] = Field(
        default=None,
        description="The banded range to update with the new properties.",
    )


class UpdateBordersRequest(BaseModel):
    """
    Updates the borders of a range. If a field is not set in the request, that means the border remains as-is. For example, with two subsequent UpdateBordersRequest: 1. range: A1:A5 `{ top: RED, bottom: WHITE }` 2. range: A1:A5 `{ left: BLUE }` That would result in A1:A5 having a borders of `{ top: RED, bottom: WHITE, left: BLUE }`. If you want to clear a border, explicitly set the style to NONE.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateBordersRequest
    """

    right: Optional[Border] = Field(
        default=None,
        description="The border to put at the right of the range.",
    )

    left: Optional[Border] = Field(
        default=None,
        description="The border to put at the left of the range.",
    )

    range: Optional[GridRange] = Field(
        default=None,
        description="The range whose borders should be updated.",
    )

    inner_vertical: Optional[Border] = Field(
        default=None,
        description="The vertical border to put within the range.",
    )

    bottom: Optional[Border] = Field(
        default=None,
        description="The border to put at the bottom of the range.",
    )

    inner_horizontal: Optional[Border] = Field(
        default=None,
        description="The horizontal border to put within the range.",
    )

    top: Optional[Border] = Field(
        default=None,
        description="The border to put at the top of the range.",
    )


class UpdateCellsRequest(BaseModel):
    """
    Updates all cells in a range with new data.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateCellsRequest
    """

    rows: Optional[List[RowData]] = Field(
        default=None,
        description="The data to write.",
    )

    start: Optional[GridCoordinate] = Field(
        default=None,
        description="The coordinate to start writing data at. Any number of rows and columns (including a different number of columns per row) may be written.",
    )

    range: Optional[GridRange] = Field(
        default=None,
        description="The range to write data to. If the data in rows does not cover the entire requested range, the fields matching those set in fields will be cleared.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description="The fields of CellData that should be updated. At least one field must be specified. The root is the CellData; 'row.values.' should not be specified. A single `\"*\"` can be used as short-hand for listing every field.",
        ),
    ] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> UpdateCellsRequest:
        provided = [n for n in ("start", "range") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(f"Exactly one of 'start', 'range' must be set, found: {provided}")
        return self


class UpdateChartSpecRequest(BaseModel):
    """
    Updates a chart's specifications. (This does not move or resize a chart. To move or resize a chart, use UpdateEmbeddedObjectPositionRequest.)

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateChartSpecRequest
    """

    chart_id: Optional[int] = Field(
        default=None,
        description="The ID of the chart to update.",
    )

    spec: Optional[ChartSpec] = Field(
        default=None,
        description="The specification to apply to the chart.",
    )


class UpdateConditionalFormatRuleRequest(BaseModel):
    """
    Updates a conditional format rule at the given index, or moves a conditional format rule to another index.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateConditionalFormatRuleRequest
    """

    new_index: Optional[int] = Field(
        default=None,
        description="The zero-based new index the rule should end up at.",
    )

    rule: Optional[ConditionalFormatRule] = Field(
        default=None,
        description="The rule that should replace the rule at the given index.",
    )

    sheet_id: Optional[int] = Field(
        default=None,
        description="The sheet of the rule to move. Required if new_index is set, unused otherwise.",
    )

    index: Optional[int] = Field(
        default=None,
        description="The zero-based index of the rule that should be replaced or moved.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> UpdateConditionalFormatRuleRequest:
        provided = [n for n in ("rule", "new_index") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(f"Exactly one of 'rule', 'new_index' must be set, found: {provided}")
        return self


class UpdateDataSourceRequest(BaseModel):
    """
    Updates a data source. After the data source is updated successfully, an execution is triggered to refresh the associated DATA_SOURCE sheet to read data from the updated data source. The request requires an additional `bigquery.readonly` OAuth scope if you are updating a BigQuery data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateDataSourceRequest
    """

    data_source: Optional[DataSource] = Field(
        default=None,
        description="The data source to update.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `dataSource` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateDeveloperMetadataRequest(BaseModel):
    """
    A request to update properties of developer metadata. Updates the properties of the developer metadata selected by the filters to the values provided in the DeveloperMetadata resource. Callers must specify the properties they wish to update in the fields parameter, as well as specify at least one DataFilter matching the metadata they wish to update.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateDeveloperMetadataRequest
    """

    developer_metadata: Optional[DeveloperMetadata] = Field(
        default=None,
        description="The value that all metadata matched by the data filters will be updated to.",
    )

    data_filters: Optional[List[DataFilter]] = Field(
        default=None,
        description="The filters matching the developer metadata entries to update.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `developerMetadata` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateDimensionGroupRequest(BaseModel):
    """
    Updates the state of the specified group.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateDimensionGroupRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `dimensionGroup` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    dimension_group: Optional[DimensionGroup] = Field(
        default=None,
        description="The group whose state should be updated. The range and depth of the group should specify a valid group on the sheet, and all other fields updated.",
    )


class UpdateDimensionPropertiesRequest(BaseModel):
    """
    Updates properties of dimensions within the specified range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateDimensionPropertiesRequest
    """

    data_source_sheet_range: Optional[DataSourceSheetDimensionRange] = Field(
        default=None,
        description="The columns on a data source sheet to update.",
    )

    properties: Optional[DimensionProperties] = Field(
        default=None,
        description="Properties to update.",
    )

    range: Optional[DimensionRange] = Field(
        default=None,
        description="The rows or columns to update.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `properties` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> UpdateDimensionPropertiesRequest:
        provided = [n for n in ("range", "data_source_sheet_range") if getattr(self, n) is not None]
        if len(provided) != 1:
            raise ValueError(
                f"Exactly one of 'range', 'data_source_sheet_range' must be set, found: {provided}"
            )
        return self


class UpdateEmbeddedObjectBorderRequest(BaseModel):
    """
    Updates an embedded object's border property.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateEmbeddedObjectBorderRequest
    """

    border: Optional[EmbeddedObjectBorder] = Field(
        default=None,
        description="The border that applies to the embedded object.",
    )

    object_id: Optional[int] = Field(
        default=None,
        description="The ID of the embedded object to update.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `border` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateEmbeddedObjectPositionRequest(BaseModel):
    """
    Update an embedded object's position (such as a moving or resizing a chart or image).

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateEmbeddedObjectPositionRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields of OverlayPosition that should be updated when setting a new position. Used only if newPosition.overlayPosition is set, in which case at least one field must be specified. The root `newPosition.overlayPosition` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    object_id: Optional[int] = Field(
        default=None,
        description="The ID of the object to moved.",
    )

    new_position: Optional[EmbeddedObjectPosition] = Field(
        default=None,
        description="An explicit position to move the embedded object to. If newPosition.sheetId is set, a new sheet with that ID will be created. If newPosition.newSheet is set to true, a new sheet will be created with an ID that will be chosen for you.",
    )


class UpdateFilterViewRequest(BaseModel):
    """
    Updates properties of the filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateFilterViewRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `filter` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    filter: Optional[FilterView] = Field(
        default=None,
        description="The new properties of the filter view.",
    )


class UpdateNamedRangeRequest(BaseModel):
    """
    Updates properties of the named range with the specified namedRangeId.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateNamedRangeRequest
    """

    named_range: Optional[NamedRange] = Field(
        default=None,
        description="The named range to update with the new properties.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `namedRange` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateProtectedRangeRequest(BaseModel):
    """
    Updates an existing protected range with the specified protectedRangeId.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateProtectedRangeRequest
    """

    protected_range: Optional[ProtectedRange] = Field(
        default=None,
        description="The protected range to update with the new properties.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `protectedRange` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateSheetPropertiesRequest(BaseModel):
    """
    Updates properties of the sheet with the specified sheetId.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateSheetPropertiesRequest
    """

    properties: Optional[SheetProperties] = Field(
        default=None,
        description="The properties to update.",
    )

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `properties` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None


class UpdateSlicerSpecRequest(BaseModel):
    """
    Updates a slicer's specifications. (This does not move or resize a slicer. To move or resize a slicer use UpdateEmbeddedObjectPositionRequest.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateSlicerSpecRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='The fields that should be updated. At least one field must be specified. The root `SlicerSpec` is implied and should not be specified. A single "*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    slicer_id: Optional[int] = Field(
        default=None,
        description="The id of the slicer to update.",
    )

    spec: Optional[SlicerSpec] = Field(
        default=None,
        description="The specification to apply to the slicer.",
    )


class UpdateSpreadsheetPropertiesRequest(BaseModel):
    """
    Updates properties of a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateSpreadsheetPropertiesRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description="The fields that should be updated. At least one field must be specified. The root 'properties' is implied and should not be specified. A single `\"*\"` can be used as short-hand for listing every field.",
        ),
    ] = None

    properties: Optional[SpreadsheetProperties] = Field(
        default=None,
        description="The properties to update.",
    )


class UpdateTableRequest(BaseModel):
    """
    Updates a table in the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateTableRequest
    """

    fields: Annotated[
        Optional[FieldMask],
        Format("field_mask"),
        Field(
            default=None,
            description='Required. The fields that should be updated. At least one field must be specified. The root `table` is implied and should not be specified. A single `"*"` can be used as short-hand for listing every field.',
        ),
    ] = None

    table: Optional[Table] = Field(
        default=None,
        description="Required. The table to update.",
    )


class InsertCommentRequest(BaseModel):
    """
    Inserts a CommentThread into the spreadsheet.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#InsertCommentRequest
    """

    content: Optional[str] = Field(
        default=None,
        description=(
            "The text of the comment, as plain text. This field cannot be empty, "
            "and must not exceed 2048 UTF-8 code units."
        ),
    )
    assignee_email_address: Optional[str] = Field(
        default=None,
        description=(
            "Optional. The email address of the assignee of the comment. Leave empty "
            "for a non-assigned comment. May not exceed 2048 UTF-8 code units."
        ),
    )
    coordinate: Optional[GridCoordinate] = Field(
        default=None,
        description="The GridCoordinate in the sheet that is tied to this comment.",
    )


class AddCommentReplyRequest(BaseModel):
    """
    Inserts a reply Post into a CommentThread.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#AddCommentReplyRequest
    """

    comment_id: Optional[str] = Field(
        default=None,
        description="The ID of the CommentThread to add the reply to.",
    )
    post: Optional[Post] = Field(
        default=None,
        description="The Post representing the reply.",
    )


class UpdateCommentPostRequest(BaseModel):
    """
    Updates a Post in a CommentThread.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#UpdateCommentPostRequest
    """

    comment_id: Optional[str] = Field(
        default=None,
        description="The ID of the CommentThread which the post belongs to.",
    )
    post_id: Optional[str] = Field(
        default=None,
        description="The ID of the post being updated.",
    )
    content: Optional[str] = Field(
        default=None,
        description=(
            "The new text of the comment, as plain text. This field cannot be empty, "
            "and must not exceed 2048 UTF-8 code units."
        ),
    )


class DeleteCommentRequest(BaseModel):
    """
    Deletes a CommentThread.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteCommentRequest
    """

    comment_id: Optional[str] = Field(
        default=None,
        description="The ID of the CommentThread that is being deleted.",
    )


class DeleteCommentReplyRequest(BaseModel):
    """
    Deletes a reply Post from a CommentThread.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#DeleteCommentReplyRequest
    """

    comment_id: Optional[str] = Field(
        default=None,
        description="The ID of the CommentThread which the post belongs to.",
    )
    post_id: Optional[str] = Field(
        default=None,
        description="The ID of the reply Post being deleted.",
    )


class Request(BaseModel):
    """
    A single kind of update to apply to a spreadsheet.

    Union field `kind`. The kind of update. Exactly one field is required.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/request#Request
    """

    update_spreadsheet_properties: Optional[UpdateSpreadsheetPropertiesRequest] = Field(
        default=None,
        description="Updates the spreadsheet's properties.",
    )
    update_sheet_properties: Optional[UpdateSheetPropertiesRequest] = Field(
        default=None,
        description="Updates a sheet's properties.",
    )
    update_dimension_properties: Optional[UpdateDimensionPropertiesRequest] = Field(
        default=None,
        description="Updates dimensions' properties.",
    )
    update_named_range: Optional[UpdateNamedRangeRequest] = Field(
        default=None,
        description="Updates a named range.",
    )
    repeat_cell: Optional[RepeatCellRequest] = Field(
        default=None,
        description="Repeats a single cell across a range.",
    )
    add_named_range: Optional[AddNamedRangeRequest] = Field(
        default=None,
        description="Adds a named range.",
    )
    delete_named_range: Optional[DeleteNamedRangeRequest] = Field(
        default=None,
        description="Deletes a named range.",
    )
    add_sheet: Optional[AddSheetRequest] = Field(
        default=None,
        description="Adds a sheet.",
    )
    delete_sheet: Optional[DeleteSheetRequest] = Field(
        default=None,
        description="Deletes a sheet.",
    )
    auto_fill: Optional[AutoFillRequest] = Field(
        default=None,
        description="Automatically fills in more data based on existing data.",
    )
    cut_paste: Optional[CutPasteRequest] = Field(
        default=None,
        description="Cuts data from one area and pastes it to another.",
    )
    copy_paste: Optional[CopyPasteRequest] = Field(
        default=None,
        description="Copies data from one area and pastes it to another.",
    )
    merge_cells: Optional[MergeCellsRequest] = Field(
        default=None,
        description="Merges cells together.",
    )
    unmerge_cells: Optional[UnmergeCellsRequest] = Field(
        default=None,
        description="Unmerges merged cells.",
    )
    update_borders: Optional[UpdateBordersRequest] = Field(
        default=None,
        description="Updates the borders in a range of cells.",
    )
    update_cells: Optional[UpdateCellsRequest] = Field(
        default=None,
        description="Updates many cells at once.",
    )
    add_filter_view: Optional[AddFilterViewRequest] = Field(
        default=None,
        description="Adds a filter view.",
    )
    append_cells: Optional[AppendCellsRequest] = Field(
        default=None,
        description="Appends cells after the last row with data in a sheet.",
    )
    clear_basic_filter: Optional[ClearBasicFilterRequest] = Field(
        default=None,
        description="Clears the basic filter on a sheet.",
    )
    delete_dimension: Optional[DeleteDimensionRequest] = Field(
        default=None,
        description="Deletes rows or columns in a sheet.",
    )
    delete_embedded_object: Optional[DeleteEmbeddedObjectRequest] = Field(
        default=None,
        description="Deletes an embedded object (e.g, chart, image) in a sheet.",
    )
    delete_filter_view: Optional[DeleteFilterViewRequest] = Field(
        default=None,
        description="Deletes a filter view from a sheet.",
    )
    duplicate_filter_view: Optional[DuplicateFilterViewRequest] = Field(
        default=None,
        description="Duplicates a filter view.",
    )
    duplicate_sheet: Optional[DuplicateSheetRequest] = Field(
        default=None,
        description="Duplicates a sheet.",
    )
    find_replace: Optional[FindReplaceRequest] = Field(
        default=None,
        description="Finds and replaces occurrences of some text with other text.",
    )
    insert_dimension: Optional[InsertDimensionRequest] = Field(
        default=None,
        description="Inserts new rows or columns in a sheet.",
    )
    insert_range: Optional[InsertRangeRequest] = Field(
        default=None,
        description="Inserts new cells in a sheet, shifting the existing cells.",
    )
    move_dimension: Optional[MoveDimensionRequest] = Field(
        default=None,
        description="Moves rows or columns to another location in a sheet.",
    )
    update_embedded_object_position: Optional[UpdateEmbeddedObjectPositionRequest] = Field(
        default=None,
        description="Updates an embedded object's (e.g. chart, image) position.",
    )
    paste_data: Optional[PasteDataRequest] = Field(
        default=None,
        description="Pastes data (HTML or delimited) into a sheet.",
    )
    text_to_columns: Optional[TextToColumnsRequest] = Field(
        default=None,
        description="Converts a column of text into many columns of text.",
    )
    update_filter_view: Optional[UpdateFilterViewRequest] = Field(
        default=None,
        description="Updates the properties of a filter view.",
    )
    delete_range: Optional[DeleteRangeRequest] = Field(
        default=None,
        description="Deletes a range of cells from a sheet, shifting the remaining cells.",
    )
    append_dimension: Optional[AppendDimensionRequest] = Field(
        default=None,
        description="Appends dimensions to the end of a sheet.",
    )
    add_conditional_format_rule: Optional[AddConditionalFormatRuleRequest] = Field(
        default=None,
        description="Adds a new conditional format rule.",
    )
    update_conditional_format_rule: Optional[UpdateConditionalFormatRuleRequest] = Field(
        default=None,
        description="Updates an existing conditional format rule.",
    )
    delete_conditional_format_rule: Optional[DeleteConditionalFormatRuleRequest] = Field(
        default=None,
        description="Deletes an existing conditional format rule.",
    )
    sort_range: Optional[SortRangeRequest] = Field(
        default=None,
        description="Sorts data in a range.",
    )
    set_data_validation: Optional[SetDataValidationRequest] = Field(
        default=None,
        description="Sets data validation for one or more cells.",
    )
    set_basic_filter: Optional[SetBasicFilterRequest] = Field(
        default=None,
        description="Sets the basic filter on a sheet.",
    )
    add_protected_range: Optional[AddProtectedRangeRequest] = Field(
        default=None,
        description="Adds a protected range.",
    )
    update_protected_range: Optional[UpdateProtectedRangeRequest] = Field(
        default=None,
        description="Updates a protected range.",
    )
    delete_protected_range: Optional[DeleteProtectedRangeRequest] = Field(
        default=None,
        description="Deletes a protected range.",
    )
    auto_resize_dimensions: Optional[AutoResizeDimensionsRequest] = Field(
        default=None,
        description="Automatically resizes one or more dimensions based on the contents of the cells in that dimension.",
    )
    add_chart: Optional[AddChartRequest] = Field(
        default=None,
        description="Adds a chart.",
    )
    update_chart_spec: Optional[UpdateChartSpecRequest] = Field(
        default=None,
        description="Updates a chart's specifications.",
    )
    update_banding: Optional[UpdateBandingRequest] = Field(
        default=None,
        description="Updates a banded range",
    )
    add_banding: Optional[AddBandingRequest] = Field(
        default=None,
        description="Adds a new banded range",
    )
    delete_banding: Optional[DeleteBandingRequest] = Field(
        default=None,
        description="Removes a banded range",
    )
    create_developer_metadata: Optional[CreateDeveloperMetadataRequest] = Field(
        default=None,
        description="Creates new developer metadata",
    )
    update_developer_metadata: Optional[UpdateDeveloperMetadataRequest] = Field(
        default=None,
        description="Updates an existing developer metadata entry",
    )
    delete_developer_metadata: Optional[DeleteDeveloperMetadataRequest] = Field(
        default=None,
        description="Deletes developer metadata",
    )
    randomize_range: Optional[RandomizeRangeRequest] = Field(
        default=None,
        description="Randomizes the order of the rows in a range.",
    )
    add_dimension_group: Optional[AddDimensionGroupRequest] = Field(
        default=None,
        description="Creates a group over the specified range.",
    )
    delete_dimension_group: Optional[DeleteDimensionGroupRequest] = Field(
        default=None,
        description="Deletes a group over the specified range.",
    )
    update_dimension_group: Optional[UpdateDimensionGroupRequest] = Field(
        default=None,
        description="Updates the state of the specified group.",
    )
    trim_whitespace: Optional[TrimWhitespaceRequest] = Field(
        default=None,
        description="Trims cells of whitespace (such as spaces, tabs, or new lines).",
    )
    delete_duplicates: Optional[DeleteDuplicatesRequest] = Field(
        default=None,
        description="Removes rows containing duplicate values in specified columns of a cell range.",
    )
    update_embedded_object_border: Optional[UpdateEmbeddedObjectBorderRequest] = Field(
        default=None,
        description="Updates an embedded object's border.",
    )
    add_slicer: Optional[AddSlicerRequest] = Field(
        default=None,
        description="Adds a slicer.",
    )
    update_slicer_spec: Optional[UpdateSlicerSpecRequest] = Field(
        default=None,
        description="Updates a slicer's specifications.",
    )
    add_data_source: Optional[AddDataSourceRequest] = Field(
        default=None,
        description="Adds a data source.",
    )
    update_data_source: Optional[UpdateDataSourceRequest] = Field(
        default=None,
        description="Updates a data source.",
    )
    delete_data_source: Optional[DeleteDataSourceRequest] = Field(
        default=None,
        description="Deletes a data source.",
    )
    refresh_data_source: Optional[RefreshDataSourceRequest] = Field(
        default=None,
        description="Refreshes one or multiple data sources and associated dbobjects.",
    )
    cancel_data_source_refresh: Optional[CancelDataSourceRefreshRequest] = Field(
        default=None,
        description="Cancels refreshes of one or multiple data sources and associated dbobjects.",
    )
    add_table: Optional[AddTableRequest] = Field(
        default=None,
        description="Adds a table.",
    )
    update_table: Optional[UpdateTableRequest] = Field(
        default=None,
        description="Updates a table.",
    )
    delete_table: Optional[DeleteTableRequest] = Field(
        default=None,
        description="A request for deleting a table.",
    )
    insert_comment: Optional[InsertCommentRequest] = Field(
        default=None,
        description="Inserts a CommentThread into the spreadsheet. Developer Preview.",
    )
    add_comment_reply: Optional[AddCommentReplyRequest] = Field(
        default=None,
        description="Adds a reply to a CommentThread. Developer Preview.",
    )
    update_comment_post: Optional[UpdateCommentPostRequest] = Field(
        default=None,
        description="Updates an existing post of a CommentThread. Developer Preview.",
    )
    delete_comment: Optional[DeleteCommentRequest] = Field(
        default=None,
        description="Deletes a CommentThread. Developer Preview.",
    )
    delete_comment_reply: Optional[DeleteCommentReplyRequest] = Field(
        default=None,
        description="Deletes a reply Post from a CommentThread. Developer Preview.",
    )

    @model_validator(mode="after")
    def _exactly_one(self) -> Request:
        provided = [
            n
            for n in (
                "update_spreadsheet_properties",
                "update_sheet_properties",
                "update_dimension_properties",
                "update_named_range",
                "repeat_cell",
                "add_named_range",
                "delete_named_range",
                "add_sheet",
                "delete_sheet",
                "auto_fill",
                "cut_paste",
                "copy_paste",
                "merge_cells",
                "unmerge_cells",
                "update_borders",
                "update_cells",
                "add_filter_view",
                "append_cells",
                "clear_basic_filter",
                "delete_dimension",
                "delete_embedded_object",
                "delete_filter_view",
                "duplicate_filter_view",
                "duplicate_sheet",
                "find_replace",
                "insert_dimension",
                "insert_range",
                "move_dimension",
                "update_embedded_object_position",
                "paste_data",
                "text_to_columns",
                "update_filter_view",
                "delete_range",
                "append_dimension",
                "add_conditional_format_rule",
                "update_conditional_format_rule",
                "delete_conditional_format_rule",
                "sort_range",
                "set_data_validation",
                "set_basic_filter",
                "add_protected_range",
                "update_protected_range",
                "delete_protected_range",
                "auto_resize_dimensions",
                "add_chart",
                "update_chart_spec",
                "update_banding",
                "add_banding",
                "delete_banding",
                "create_developer_metadata",
                "update_developer_metadata",
                "delete_developer_metadata",
                "randomize_range",
                "add_dimension_group",
                "delete_dimension_group",
                "update_dimension_group",
                "trim_whitespace",
                "delete_duplicates",
                "update_embedded_object_border",
                "add_slicer",
                "update_slicer_spec",
                "add_data_source",
                "update_data_source",
                "delete_data_source",
                "refresh_data_source",
                "cancel_data_source_refresh",
                "add_table",
                "update_table",
                "delete_table",
                "insert_comment",
                "add_comment_reply",
                "update_comment_post",
                "delete_comment",
                "delete_comment_reply",
            )
            if getattr(self, n) is not None
        ]
        if len(provided) != 1:
            raise ValueError(f"Exactly one request kind must be set, found: {provided}")
        return self

    model_config = ConfigDict(extra="forbid")


def _rebuild_forward_refs() -> None:
    for obj in list(globals().values()):
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == __name__
        ):
            obj.model_rebuild()


_rebuild_forward_refs()
