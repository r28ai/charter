# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Format, Value

from ..spreadsheets.models import (
    DataFilter,
    Dimension,
)

ValueRenderOption = Literal["FORMATTED_VALUE", "UNFORMATTED_VALUE", "FORMULA"]

DateTimeRenderOption = Literal["SERIAL_NUMBER", "FORMATTED_STRING"]

InsertDataOption = Literal["OVERWRITE", "INSERT_ROWS"]

ValueInputOption = Literal["INPUT_VALUE_OPTION_UNSPECIFIED", "RAW", "USER_ENTERED"]


class ValueRange(BaseModel):
    """
    Data within a range of the spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values#resource:-valuerange
    """

    range: Optional[str] = Field(
        default=None,
        description=(
            "The range the values cover, in A1 notation. For output, this range "
            "indicates the entire requested range, even though the values will "
            "exclude trailing rows and columns. When appending values, this field "
            "represents the range to search for a table, after which values will "
            "be appended."
        ),
    )
    major_dimension: Optional[Dimension] = Field(
        default=None,
        description=(
            "The major dimension of the values. For output, if the spreadsheet data "
            "is: A1=1,B1=2,A2=3,B2=4, then requesting range=A1:B2,majorDimension=ROWS "
            "will return [[1,2],[3,4]], whereas requesting "
            "range=A1:B2,majorDimension=COLUMNS will return [[1,3],[2,4]]. "
            "For input, with range=A1:B2,majorDimension=ROWS then [[1,2],[3,4]] will "
            "set A1=1,B1=2,A2=3,B2=4. With range=A1:B2,majorDimension=COLUMNS then "
            "[[1,2],[3,4]] will set A1=1,B1=3,A2=2,B2=4. When writing, if this field "
            "is not set, it defaults to ROWS."
        ),
    )
    values: Annotated[
        Optional[List[List[Value]]],
        Format("proto_json"),
        Field(
            default=None,
            description=(
                "The data that was read or to be written. This is an array of arrays, "
                "the outer array representing all the data and each inner array "
                "representing a major dimension. Each item in the inner array "
                "corresponds with one cell. For output, empty trailing rows and "
                "columns will not be included. For input, supported value types are: "
                "bool, string, and double. Null values will be skipped. To set a cell "
                "to an empty value, set the string value to an empty string."
            ),
        ),
    ] = None


class DataFilterValueRange(BaseModel):
    """
    A range of values whose location is specified by a DataFilter.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdateByDataFilter#DataFilterValueRange
    """

    data_filter: Optional[DataFilter] = Field(
        default=None,
        description="The data filter describing the location of the values in the spreadsheet.",
    )
    major_dimension: Optional[Dimension] = Field(
        default=None,
        description="The major dimension of the values.",
    )
    values: Annotated[
        Optional[List[List[Value]]],
        Format("proto_json"),
        Field(
            default=None,
            description=(
                "The data to be written. If the provided values exceed any of the "
                "ranges matched by the data filter then the request fails. If the "
                "provided values are less than the matched ranges only the specified "
                "values are written, existing values in the matched ranges remain "
                "unaffected."
            ),
        ),
    ] = None


class UpdateValuesResponse(BaseModel):
    """
    The response when updating a range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/UpdateValuesResponse
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    updated_range: Optional[str] = Field(
        default=None,
        description="The range (in A1 notation) that updates were applied to.",
    )
    updated_rows: Optional[int] = Field(
        default=None,
        description="The number of rows where at least one cell in the row was updated.",
    )
    updated_columns: Optional[int] = Field(
        default=None,
        description="The number of columns where at least one cell in the column was updated.",
    )
    updated_cells: Optional[int] = Field(
        default=None,
        description="The number of cells updated.",
    )
    updated_data: Optional[ValueRange] = Field(
        default=None,
        description=(
            "The values of the cells after updates were applied. This is only "
            "included if the request's includeValuesInResponse field was true."
        ),
    )


class AppendValuesResponse(BaseModel):
    """
    The response when values are appended to a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    table_range: Optional[str] = Field(
        default=None,
        description=(
            "The range (in A1 notation) of the table that values are being appended "
            "to (before the values were appended). Empty if no table was found."
        ),
    )
    updates: Optional[UpdateValuesResponse] = Field(
        default=None,
        description="Information about the updates that were applied.",
    )


class ClearValuesResponse(BaseModel):
    """
    The response when clearing a range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/clear#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    cleared_range: Optional[str] = Field(
        default=None,
        description=(
            "The range (in A1 notation) that was cleared. (If the request was for an "
            "unbounded range or a range larger than the bounds of the sheet, this "
            "will be the actual range that was cleared, bounded to the sheet's limits.)"
        ),
    )


class BatchGetValuesResponse(BaseModel):
    """
    The response when retrieving more than one range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The ID of the spreadsheet the data was retrieved from.",
    )
    value_ranges: Optional[List[ValueRange]] = Field(
        default=None,
        description=(
            "The requested values. The order of the ValueRanges is the same as the "
            "order of the requested ranges."
        ),
    )


class BatchClearValuesResponse(BaseModel):
    """
    The response when clearing a range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchClear#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    cleared_ranges: Optional[List[str]] = Field(
        default=None,
        description=(
            "The ranges that were cleared, in A1 notation. If the requests are for "
            "an unbounded range or a range larger than the bounds of the sheet, this "
            "is the actual ranges that were cleared, bounded to the sheet's limits."
        ),
    )


class BatchUpdateValuesResponse(BaseModel):
    """
    The response when updating a range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    total_updated_rows: Optional[int] = Field(
        default=None,
        description="The total number of rows where at least one cell in the row was updated.",
    )
    total_updated_columns: Optional[int] = Field(
        default=None,
        description="The total number of columns where at least one cell in the column was updated.",
    )
    total_updated_cells: Optional[int] = Field(
        default=None,
        description="The total number of cells updated.",
    )
    total_updated_sheets: Optional[int] = Field(
        default=None,
        description="The total number of sheets where at least one cell in the sheet was updated.",
    )
    responses: Optional[List[UpdateValuesResponse]] = Field(
        default=None,
        description=(
            "One UpdateValuesResponse per requested range, in the same order as the "
            "requests appeared."
        ),
    )


class MatchedValueRange(BaseModel):
    """
    A value range that was matched by one or more data filters.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGetByDataFilter#MatchedValueRange
    """

    value_range: Optional[ValueRange] = Field(
        default=None,
        description="The values matched by the DataFilter.",
    )
    data_filters: Optional[List[DataFilter]] = Field(
        default=None,
        description="The DataFilters from the request that matched the range of values.",
    )


class BatchGetValuesByDataFilterResponse(BaseModel):
    """
    The response when retrieving more than one range of values in a spreadsheet
    selected by DataFilters.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGetByDataFilter#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The ID of the spreadsheet the data was retrieved from.",
    )
    value_ranges: Optional[List[MatchedValueRange]] = Field(
        default=None,
        description="The requested values with the list of data filters that matched them.",
    )


class UpdateValuesByDataFilterResponse(BaseModel):
    """
    The response when updating a range of values by a data filter in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdateByDataFilter#UpdateValuesByDataFilterResponse
    """

    updated_range: Optional[str] = Field(
        default=None,
        description="The range (in A1 notation) that updates were applied to.",
    )
    updated_rows: Optional[int] = Field(
        default=None,
        description="The number of rows where at least one cell in the row was updated.",
    )
    updated_columns: Optional[int] = Field(
        default=None,
        description="The number of columns where at least one cell in the column was updated.",
    )
    updated_cells: Optional[int] = Field(
        default=None,
        description="The number of cells updated.",
    )
    data_filter: Optional[DataFilter] = Field(
        default=None,
        description="The data filter that selected the range that was updated.",
    )
    updated_data: Optional[ValueRange] = Field(
        default=None,
        description=(
            "The values of the cells in the range matched by the dataFilter after "
            "all updates were applied. This is only included if the request's "
            "includeValuesInResponse field was true."
        ),
    )


class BatchUpdateValuesByDataFilterResponse(BaseModel):
    """
    The response when updating a range of values in a spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdateByDataFilter#response-body
    """

    spreadsheet_id: Optional[str] = Field(
        default=None,
        description="The spreadsheet the updates were applied to.",
    )
    total_updated_rows: Optional[int] = Field(
        default=None,
        description="The total number of rows where at least one cell in the row was updated.",
    )
    total_updated_columns: Optional[int] = Field(
        default=None,
        description="The total number of columns where at least one cell in the column was updated.",
    )
    total_updated_cells: Optional[int] = Field(
        default=None,
        description="The total number of cells updated.",
    )
    total_updated_sheets: Optional[int] = Field(
        default=None,
        description="The total number of sheets where at least one cell in the sheet was updated.",
    )
    responses: Optional[List[UpdateValuesByDataFilterResponse]] = Field(
        default=None,
        description="The response for each range updated.",
    )
