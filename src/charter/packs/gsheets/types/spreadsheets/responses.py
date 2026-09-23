# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The ``batchUpdate`` response union.

A reply may have no fields set if the matching request had nothing to return.
Replies map 1:1 with the requests that produced them.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from charter.packs.gsheets.types.spreadsheets.models import (
    BandedRange,
    CommentThread,
    CommentUpdateState,
    ConditionalFormatRule,
    DataExecutionStatus,
    DataSource,
    DataSourceObjectReference,
    DeveloperMetadata,
    DimensionGroup,
    EmbeddedChart,
    EmbeddedObjectPosition,
    FilterView,
    NamedRange,
    Post,
    ProtectedRange,
    RefreshCancellationStatusErrorCode,
    RefreshCancellationStatusState,
    SheetProperties,
    Slicer,
    Spreadsheet,
    Table,
)
from charter.types import Mode


class AddBandingResponse(BaseModel):
    """
    The result of adding a banded range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddBandingResponse
    """

    banded_range: Optional[BandedRange] = Field(
        default=None,
        description="The banded range that was added.",
    )


class AddChartResponse(BaseModel):
    """
    The result of adding a chart to a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddChartResponse
    """

    chart: Optional[EmbeddedChart] = Field(
        default=None,
        description="The newly added chart.",
    )


class AddDataSourceResponse(BaseModel):
    """
    The result of adding a data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddDataSourceResponse
    """

    data_execution_status: Optional[DataExecutionStatus] = Field(
        default=None,
        description="The data execution status.",
    )

    data_source: Optional[DataSource] = Field(
        default=None,
        description="The data source that was created.",
    )


class AddDimensionGroupResponse(BaseModel):
    """
    The result of adding a group.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddDimensionGroupResponse
    """

    dimension_groups: Optional[List[DimensionGroup]] = Field(
        default=None,
        description="All groups of a dimension after adding a group to that dimension.",
    )


class AddFilterViewResponse(BaseModel):
    """
    The result of adding a filter view.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddFilterViewResponse
    """

    filter: Optional[FilterView] = Field(
        default=None,
        description="The newly added filter view.",
    )


class AddNamedRangeResponse(BaseModel):
    """
    The result of adding a named range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddNamedRangeResponse
    """

    named_range: Optional[NamedRange] = Field(
        default=None,
        description="The named range to add.",
    )


class AddProtectedRangeResponse(BaseModel):
    """
    The result of adding a new protected range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddProtectedRangeResponse
    """

    protected_range: Optional[ProtectedRange] = Field(
        default=None,
        description="The newly added protected range.",
    )


class AddSheetResponse(BaseModel):
    """
    The result of adding a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddSheetResponse
    """

    properties: Optional[SheetProperties] = Field(
        default=None,
        description="The properties of the newly added sheet.",
    )


class AddSlicerResponse(BaseModel):
    """
    The result of adding a slicer to a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddSlicerResponse
    """

    slicer: Optional[Slicer] = Field(
        default=None,
        description="The newly added slicer.",
    )


class AddTableResponse(BaseModel):
    """
    The result of adding a table.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddTableResponse
    """

    table: Annotated[
        Optional[Table],
        Mode("response_only"),
        Field(default=None, description="Output only. The table that was added."),
    ] = None


class CancelDataSourceRefreshResponse(BaseModel):
    """
    The response from cancelling one or multiple data source object refreshes.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#CancelDataSourceRefreshResponse
    """

    statuses: Optional[List[CancelDataSourceRefreshStatus]] = Field(
        default=None,
        description="The cancellation statuses of refreshes of all data source objects specified in the request. If is_all is specified, the field contains only those in failure status. Refreshing and canceling refresh the same data source object is also not allowed in the same `batchUpdate`.",
    )


class CancelDataSourceRefreshStatus(BaseModel):
    """
    The status of cancelling a single data source object refresh.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#CancelDataSourceRefreshStatus
    """

    reference: Optional[DataSourceObjectReference] = Field(
        default=None,
        description="Reference to the data source object whose refresh is being cancelled.",
    )

    refresh_cancellation_status: Optional[RefreshCancellationStatus] = Field(
        default=None,
        description="The cancellation status.",
    )


class CreateDeveloperMetadataResponse(BaseModel):
    """
    The response from creating developer metadata.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#CreateDeveloperMetadataResponse
    """

    developer_metadata: Optional[DeveloperMetadata] = Field(
        default=None,
        description="The developer metadata that was created.",
    )


class DeleteConditionalFormatRuleResponse(BaseModel):
    """
    The result of deleting a conditional format rule.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DeleteConditionalFormatRuleResponse
    """

    rule: Optional[ConditionalFormatRule] = Field(
        default=None,
        description="The rule that was deleted.",
    )


class DeleteDeveloperMetadataResponse(BaseModel):
    """
    The response from deleting developer metadata.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DeleteDeveloperMetadataResponse
    """

    deleted_developer_metadata: Optional[List[DeveloperMetadata]] = Field(
        default=None,
        description="The metadata that was deleted.",
    )


class DeleteDimensionGroupResponse(BaseModel):
    """
    The result of deleting a group.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DeleteDimensionGroupResponse
    """

    dimension_groups: Optional[List[DimensionGroup]] = Field(
        default=None,
        description="All groups of a dimension after deleting a group from that dimension.",
    )


class DeleteDuplicatesResponse(BaseModel):
    """
    The result of removing duplicates in a range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DeleteDuplicatesResponse
    """

    duplicates_removed_count: Optional[int] = Field(
        default=None,
        description="The number of duplicate rows removed.",
    )


class DuplicateFilterViewResponse(BaseModel):
    """
    The result of a filter view being duplicated.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DuplicateFilterViewResponse
    """

    filter: Optional[FilterView] = Field(
        default=None,
        description="The newly created filter.",
    )


class DuplicateSheetResponse(BaseModel):
    """
    The result of duplicating a sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#DuplicateSheetResponse
    """

    properties: Optional[SheetProperties] = Field(
        default=None,
        description="The properties of the duplicate sheet.",
    )


class FindReplaceResponse(BaseModel):
    """
    The result of the find/replace.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#FindReplaceResponse
    """

    values_changed: Optional[int] = Field(
        default=None,
        description="The number of non-formula cells changed.",
    )

    rows_changed: Optional[int] = Field(
        default=None,
        description="The number of rows changed.",
    )

    occurrences_changed: Optional[int] = Field(
        default=None,
        description='The number of occurrences (possibly multiple within a cell) changed. For example, if replacing `"e"` with `"o"` in `"Google Sheets"`, this would be `"3"` because `"Google Sheets"` -> `"Googlo Shoots"`.',
    )

    formulas_changed: Optional[int] = Field(
        default=None,
        description="The number of formula cells changed.",
    )

    sheets_changed: Optional[int] = Field(
        default=None,
        description="The number of sheets changed.",
    )


class RefreshCancellationStatus(BaseModel):
    """
    The status of a refresh cancellation. You can send a cancel request to explicitly cancel one or multiple data source object refreshes.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#RefreshCancellationStatus
    """

    state: Optional[RefreshCancellationStatusState] = Field(
        default=None,
        description="The state of a call to cancel a refresh in Sheets.",
    )

    error_code: Optional[RefreshCancellationStatusErrorCode] = Field(
        default=None,
        description="The error code.",
    )


class RefreshDataSourceObjectExecutionStatus(BaseModel):
    """
    The execution status of refreshing one data source object.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#RefreshDataSourceObjectExecutionStatus
    """

    reference: Optional[DataSourceObjectReference] = Field(
        default=None,
        description="Reference to a data source object being refreshed.",
    )

    data_execution_status: Optional[DataExecutionStatus] = Field(
        default=None,
        description="The data execution status.",
    )


class RefreshDataSourceResponse(BaseModel):
    """
    The response from refreshing one or multiple data source objects.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#RefreshDataSourceResponse
    """

    statuses: Optional[List[RefreshDataSourceObjectExecutionStatus]] = Field(
        default=None,
        description="All the refresh status for the data source object references specified in the request. If is_all is specified, the field contains only those in failure status.",
    )


class TrimWhitespaceResponse(BaseModel):
    """
    The result of trimming whitespace in cells.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#TrimWhitespaceResponse
    """

    cells_changed_count: Optional[int] = Field(
        default=None,
        description="The number of cells that were trimmed of whitespace.",
    )


class UpdateConditionalFormatRuleResponse(BaseModel):
    """
    The result of updating a conditional format rule.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#UpdateConditionalFormatRuleResponse
    """

    new_index: Optional[int] = Field(
        default=None,
        description="The index of the new rule.",
    )

    old_index: Optional[int] = Field(
        default=None,
        description="The old index of the rule. Not set if a rule was replaced (because it is the same as new_index).",
    )

    new_rule: Optional[ConditionalFormatRule] = Field(
        default=None,
        description="The new rule that replaced the old rule (if replacing), or the rule that was moved (if moved)",
    )

    old_rule: Optional[ConditionalFormatRule] = Field(
        default=None,
        description="The old (deleted) rule. Not set if a rule was moved (because it is the same as new_rule).",
    )


class UpdateDataSourceResponse(BaseModel):
    """
    The response from updating data source.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#UpdateDataSourceResponse
    """

    data_source: Optional[DataSource] = Field(
        default=None,
        description="The updated data source.",
    )

    data_execution_status: Optional[DataExecutionStatus] = Field(
        default=None,
        description="The data execution status.",
    )


class UpdateDeveloperMetadataResponse(BaseModel):
    """
    The response from updating developer metadata.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#UpdateDeveloperMetadataResponse
    """

    developer_metadata: Optional[List[DeveloperMetadata]] = Field(
        default=None,
        description="The updated developer metadata.",
    )


class UpdateEmbeddedObjectPositionResponse(BaseModel):
    """
    The result of updating an embedded object's position.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#UpdateEmbeddedObjectPositionResponse
    """

    position: Optional[EmbeddedObjectPosition] = Field(
        default=None,
        description="The new position of the embedded object.",
    )


class InsertCommentResponse(BaseModel):
    """
    The result of creating a comment.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#InsertCommentResponse
    """

    comment_thread: Optional[CommentThread] = Field(
        default=None,
        description="The newly-inserted comment thread.",
    )


class AddCommentReplyResponse(BaseModel):
    """
    The result of creating a reply.

    Developer Preview: available as part of the Google Workspace Developer
    Preview Program.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#AddCommentReplyResponse
    """

    post: Optional[Post] = Field(
        default=None,
        description="The newly-inserted reply Post.",
    )


class Response(BaseModel):
    """
    A single response from an update.

    Union field `kind`. The kind of reply. May have no fields set if the
    request had no response.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#Response
    """

    add_named_range: Optional[AddNamedRangeResponse] = Field(
        default=None,
        description="A reply from adding a named range.",
    )
    add_sheet: Optional[AddSheetResponse] = Field(
        default=None,
        description="A reply from adding a sheet.",
    )
    add_filter_view: Optional[AddFilterViewResponse] = Field(
        default=None,
        description="A reply from adding a filter view.",
    )
    duplicate_filter_view: Optional[DuplicateFilterViewResponse] = Field(
        default=None,
        description="A reply from duplicating a filter view.",
    )
    duplicate_sheet: Optional[DuplicateSheetResponse] = Field(
        default=None,
        description="A reply from duplicating a sheet.",
    )
    find_replace: Optional[FindReplaceResponse] = Field(
        default=None,
        description="A reply from doing a find/replace.",
    )
    update_embedded_object_position: Optional[UpdateEmbeddedObjectPositionResponse] = Field(
        default=None,
        description="A reply from updating an embedded object's position.",
    )
    update_conditional_format_rule: Optional[UpdateConditionalFormatRuleResponse] = Field(
        default=None,
        description="A reply from updating a conditional format rule.",
    )
    delete_conditional_format_rule: Optional[DeleteConditionalFormatRuleResponse] = Field(
        default=None,
        description="A reply from deleting a conditional format rule.",
    )
    add_protected_range: Optional[AddProtectedRangeResponse] = Field(
        default=None,
        description="A reply from adding a protected range.",
    )
    add_chart: Optional[AddChartResponse] = Field(
        default=None,
        description="A reply from adding a chart.",
    )
    add_banding: Optional[AddBandingResponse] = Field(
        default=None,
        description="A reply from adding a banded range.",
    )
    create_developer_metadata: Optional[CreateDeveloperMetadataResponse] = Field(
        default=None,
        description="A reply from creating a developer metadata entry.",
    )
    update_developer_metadata: Optional[UpdateDeveloperMetadataResponse] = Field(
        default=None,
        description="A reply from updating a developer metadata entry.",
    )
    delete_developer_metadata: Optional[DeleteDeveloperMetadataResponse] = Field(
        default=None,
        description="A reply from deleting a developer metadata entry.",
    )
    add_dimension_group: Optional[AddDimensionGroupResponse] = Field(
        default=None,
        description="A reply from adding a dimension group.",
    )
    delete_dimension_group: Optional[DeleteDimensionGroupResponse] = Field(
        default=None,
        description="A reply from deleting a dimension group.",
    )
    trim_whitespace: Optional[TrimWhitespaceResponse] = Field(
        default=None,
        description="A reply from trimming whitespace.",
    )
    delete_duplicates: Optional[DeleteDuplicatesResponse] = Field(
        default=None,
        description="A reply from removing rows containing duplicate values.",
    )
    add_slicer: Optional[AddSlicerResponse] = Field(
        default=None,
        description="A reply from adding a slicer.",
    )
    add_data_source: Optional[AddDataSourceResponse] = Field(
        default=None,
        description="A reply from adding a data source.",
    )
    update_data_source: Optional[UpdateDataSourceResponse] = Field(
        default=None,
        description="A reply from updating a data source.",
    )
    refresh_data_source: Optional[RefreshDataSourceResponse] = Field(
        default=None,
        description="A reply from refreshing data source objects.",
    )
    cancel_data_source_refresh: Optional[CancelDataSourceRefreshResponse] = Field(
        default=None,
        description="A reply from cancelling data source object refreshes.",
    )
    add_table: Optional[AddTableResponse] = Field(
        default=None,
        description="A reply from adding a table.",
    )
    insert_comment: Optional[InsertCommentResponse] = Field(
        default=None,
        description="The result of creating a comment. Developer Preview.",
    )
    add_comment_reply: Optional[AddCommentReplyResponse] = Field(
        default=None,
        description="The result of creating a reply. Developer Preview.",
    )
    model_config = ConfigDict(extra="forbid")


class BatchUpdateSpreadsheetResponse(BaseModel):
    """
    The reply for batch updating a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/response#BatchUpdateSpreadsheetResponse
    """

    replies: Optional[List[Response]] = Field(
        default=None,
        description="The reply of the updates. This maps 1:1 with the updates, although replies to some requests may be empty.",
    )

    updated_spreadsheet: Optional[Spreadsheet] = Field(
        default=None,
        description="The spreadsheet after updates were applied. This is only set if BatchUpdateSpreadsheetRequest.include_spreadsheet_in_response is `true`.",
    )

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    comment_update_state: Optional[CommentUpdateState] = Field(
        default=None,
        description=(
            "Whether comment updates were applied in the batch request. Developer Preview."
        ),
    )
