# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the spreadsheets.values collection.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values

Descriptions are the API's own words rather than a summary of them: they are the
only guide the model has, and paraphrasing them is how a pack drifts from the
documentation it was written against. Where several endpoints share a parameter,
the text lives in one constant below and is applied at each use.
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

from ..spreadsheets.models import DataFilter, Dimension
from .models import (
    DataFilterValueRange,
    DateTimeRenderOption,
    InsertDataOption,
    ValueInputOption,
    ValueRange,
    ValueRenderOption,
)

# ──────────────────────────────────────────────────────────
# Descriptions shared between endpoints
# ──────────────────────────────────────────────────────────

SPREADSHEET_ID_READ = "The ID of the spreadsheet to retrieve data from."
SPREADSHEET_ID_WRITE = "The ID of the spreadsheet to update."
VALUE_INPUT_OPTION = "How the input data should be interpreted."
INSERT_DATA_OPTION = "How the input data should be inserted."
VALUE_RENDER_OPTION = (
    "How values should be represented in the output. The default render option is FORMATTED_VALUE."
)
DATE_TIME_RENDER_OPTION = (
    "How dates, times, and durations should be represented in the output. This is "
    "ignored if valueRenderOption is FORMATTED_VALUE. The default dateTime render "
    "option is SERIAL_NUMBER."
)
RESPONSE_VALUE_RENDER_OPTION = (
    "Determines how values in the response should be rendered. The default render "
    "option is FORMATTED_VALUE."
)
RESPONSE_DATE_TIME_RENDER_OPTION = (
    "Determines how dates, times, and durations in the response should be rendered. "
    "This is ignored if responseValueRenderOption is FORMATTED_VALUE. The default "
    "dateTime render option is SERIAL_NUMBER."
)
INCLUDE_VALUES_IN_RESPONSE_APPEND = (
    "Determines if the update response should include the values of the cells that "
    "were appended. By default, responses do not include the updated values."
)
INCLUDE_VALUES_IN_RESPONSE_UPDATE = (
    "Determines if the update response should include the values of the cells that "
    "were updated. By default, responses do not include the updated values. If the "
    "range to write was larger than the range actually written, the response "
    "includes all values in the requested range (excluding trailing empty rows and "
    "columns)."
)
INCLUDE_VALUES_IN_RESPONSE_BATCH = (
    "Determines if the update response should include the values of the cells that "
    "were updated. By default, responses do not include the updated values. The "
    "updatedData field within each of the BatchUpdateValuesResponse.responses "
    "contains the updated values. If the range to write was larger than the range "
    "actually written, the response includes all values in the requested range "
    "(excluding trailing empty rows and columns)."
)
MAJOR_DIMENSION_GET = (
    "The major dimension that results should use. For example, if the spreadsheet "
    "data in Sheet1 is: A1=1,B1=2,A2=3,B2=4, then requesting "
    "range=Sheet1!A1:B2?majorDimension=ROWS returns [[1,2],[3,4]], whereas "
    "requesting range=Sheet1!A1:B2?majorDimension=COLUMNS returns [[1,3],[2,4]]."
)
MAJOR_DIMENSION_BATCH_GET = (
    "The major dimension that results should use. For example, if the spreadsheet "
    'data is: A1=1,B1=2,A2=3,B2=4, then requesting ranges=["A1:B2"],majorDimension='
    'ROWS returns [[1,2],[3,4]], whereas requesting ranges=["A1:B2"],majorDimension='
    "COLUMNS returns [[1,3],[2,4]]."
)
MAJOR_DIMENSION_FILTER = (
    "The major dimension that results should use. For example, if the spreadsheet "
    "data is: A1=1,B1=2,A2=3,B2=4, then a request that selects that range and sets "
    "majorDimension=ROWS returns [[1,2],[3,4]], whereas a request that sets "
    "majorDimension=COLUMNS returns [[1,3],[2,4]]."
)


_SpreadsheetIdRead = Annotated[str, Field(..., description=SPREADSHEET_ID_READ), Path()]
_SpreadsheetIdWrite = Annotated[str, Field(..., description=SPREADSHEET_ID_WRITE), Path()]


# ──────────────────────────────────────────────────────────
# Reading
# ──────────────────────────────────────────────────────────


class SpreadsheetsValuesGetRequest(BaseModel):
    """
    Returns a range of values from a spreadsheet. The caller must specify the
    spreadsheet ID and a range.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/get
    """

    spreadsheet_id: _SpreadsheetIdRead
    range: Annotated[
        str,
        Field(
            ...,
            description=("The A1 notation or R1C1 notation of the range to retrieve values from."),
        ),
        Path(),
    ]
    major_dimension: Annotated[
        Optional[Dimension],
        Field(None, description=MAJOR_DIMENSION_GET),
        Query(),
    ]
    value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=VALUE_RENDER_OPTION),
        Query(),
    ]
    date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=DATE_TIME_RENDER_OPTION),
        Query(),
    ]


class SpreadsheetsValuesBatchGetRequest(BaseModel):
    """
    Returns one or more ranges of values from a spreadsheet. The caller must
    specify the spreadsheet ID and one or more ranges.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGet
    """

    spreadsheet_id: _SpreadsheetIdRead
    ranges: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            description=("The A1 notation or R1C1 notation of the range to retrieve values from."),
        ),
        Query(),
    ]
    major_dimension: Annotated[
        Optional[Dimension],
        Field(None, description=MAJOR_DIMENSION_BATCH_GET),
        Query(),
    ]
    value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=VALUE_RENDER_OPTION),
        Query(),
    ]
    date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=DATE_TIME_RENDER_OPTION),
        Query(),
    ]


class SpreadsheetsValuesBatchGetByDataFilterRequest(BaseModel):
    """
    Returns one or more ranges of values that match the specified data filters.
    The caller must specify the spreadsheet ID and one or more DataFilters.
    Ranges that match any of the data filters in the request will be returned.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchGetByDataFilter
    """

    spreadsheet_id: _SpreadsheetIdRead
    data_filters: Annotated[
        List[DataFilter],
        Field(
            ...,
            min_length=1,
            description=(
                "The data filters used to match the ranges of values to retrieve. "
                "Ranges that match any of the specified data filters are included in "
                "the response."
            ),
        ),
        Body(),
    ]
    major_dimension: Annotated[
        Optional[Dimension],
        Field(None, description=MAJOR_DIMENSION_FILTER),
        Body(),
    ]
    value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=VALUE_RENDER_OPTION),
        Body(),
    ]
    date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=DATE_TIME_RENDER_OPTION),
        Body(),
    ]


# ──────────────────────────────────────────────────────────
# Writing
# ──────────────────────────────────────────────────────────


class SpreadsheetsValuesUpdateRequest(BaseModel):
    """
    Sets values in a range of a spreadsheet. The caller must specify the
    spreadsheet ID, range, and a valueInputOption.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/update
    """

    spreadsheet_id: _SpreadsheetIdWrite
    range: Annotated[
        str,
        Field(..., description="The A1 notation of the values to update."),
        Path(),
    ]
    value_input_option: Annotated[
        ValueInputOption,
        Field(..., description=VALUE_INPUT_OPTION),
        Query(),
    ]
    include_values_in_response: Annotated[
        Optional[bool],
        Field(None, description=INCLUDE_VALUES_IN_RESPONSE_UPDATE),
        Query(),
    ]
    response_value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=RESPONSE_VALUE_RENDER_OPTION),
        Query(),
    ]
    response_date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=RESPONSE_DATE_TIME_RENDER_OPTION),
        Query(),
    ]
    value_range: Annotated[
        ValueRange,
        Field(..., description="The request body contains an instance of ValueRange."),
        Body(),
    ]


class SpreadsheetsValuesAppendRequest(BaseModel):
    """
    Appends values to a spreadsheet. The input range is used to search for existing
    data and find a "table" within that range. Values will be appended to the next
    row of the table, starting with the first column of the table.

    The caller must specify the spreadsheet ID, range, and a valueInputOption.
    The valueInputOption only controls how the input data will be added to the
    sheet (column-wise or row-wise), it does not influence what cell the data
    starts being written to.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append
    """

    spreadsheet_id: _SpreadsheetIdWrite
    range: Annotated[
        str,
        Field(
            ...,
            description=(
                "The A1 notation of a range to search for a logical table of data. "
                "Values are appended after the last row of the table."
            ),
        ),
        Path(),
    ]
    value_input_option: Annotated[
        ValueInputOption,
        Field(..., description=VALUE_INPUT_OPTION),
        Query(),
    ]
    insert_data_option: Annotated[
        Optional[InsertDataOption],
        Field(None, description=INSERT_DATA_OPTION),
        Query(),
    ]
    include_values_in_response: Annotated[
        Optional[bool],
        Field(None, description=INCLUDE_VALUES_IN_RESPONSE_APPEND),
        Query(),
    ]
    response_value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=RESPONSE_VALUE_RENDER_OPTION),
        Query(),
    ]
    response_date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=RESPONSE_DATE_TIME_RENDER_OPTION),
        Query(),
    ]
    value_range: Annotated[
        ValueRange,
        Field(..., description="The request body contains an instance of ValueRange."),
        Body(),
    ]


class SpreadsheetsValuesBatchUpdateRequest(BaseModel):
    """
    Sets values in one or more ranges of a spreadsheet. The caller must specify
    the spreadsheet ID, a valueInputOption, and one or more ValueRanges.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate
    """

    spreadsheet_id: _SpreadsheetIdWrite
    value_input_option: Annotated[
        ValueInputOption,
        Field(..., description=VALUE_INPUT_OPTION),
        Body(),
    ]
    data: Annotated[
        List[ValueRange],
        Field(
            ...,
            min_length=1,
            description="The new values to apply to the spreadsheet.",
        ),
        # envelop=True so a nested proto_json transform cannot replace the
        # whole body with this list. Several Body() fields merge under their
        # names; without the envelope the transformer treats `data` as the body.
        Body(envelop=True),
    ]
    include_values_in_response: Annotated[
        Optional[bool],
        Field(None, description=INCLUDE_VALUES_IN_RESPONSE_BATCH),
        Body(),
    ]
    response_value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=RESPONSE_VALUE_RENDER_OPTION),
        Body(),
    ]
    response_date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=RESPONSE_DATE_TIME_RENDER_OPTION),
        Body(),
    ]


class SpreadsheetsValuesBatchUpdateByDataFilterRequest(BaseModel):
    """
    Sets values in one or more ranges of a spreadsheet. The caller must specify
    the spreadsheet ID, a valueInputOption, and one or more DataFilterValueRanges.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdateByDataFilter
    """

    spreadsheet_id: _SpreadsheetIdWrite
    value_input_option: Annotated[
        ValueInputOption,
        Field(..., description=VALUE_INPUT_OPTION),
        Body(),
    ]
    data: Annotated[
        List[DataFilterValueRange],
        Field(
            ...,
            min_length=1,
            description=(
                "The new values to apply to the spreadsheet. If more than one range "
                "is matched by the specified DataFilter the specified values are "
                "applied to all of those ranges."
            ),
        ),
        Body(envelop=True),
    ]
    include_values_in_response: Annotated[
        Optional[bool],
        Field(None, description=INCLUDE_VALUES_IN_RESPONSE_BATCH),
        Body(),
    ]
    response_value_render_option: Annotated[
        Optional[ValueRenderOption],
        Field(None, description=RESPONSE_VALUE_RENDER_OPTION),
        Body(),
    ]
    response_date_time_render_option: Annotated[
        Optional[DateTimeRenderOption],
        Field(None, description=RESPONSE_DATE_TIME_RENDER_OPTION),
        Body(),
    ]


# ──────────────────────────────────────────────────────────
# Clearing
# ──────────────────────────────────────────────────────────


class SpreadsheetsValuesClearRequest(BaseModel):
    """
    Clears values from a spreadsheet. The caller must specify the spreadsheet ID
    and range. Only values are cleared -- all other properties of the cell (such
    as formatting, data validation, etc..) are kept.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/clear
    """

    spreadsheet_id: _SpreadsheetIdWrite
    range: Annotated[
        str,
        Field(
            ...,
            description="The A1 notation or R1C1 notation of the values to clear.",
        ),
        Path(),
    ]


class SpreadsheetsValuesBatchClearRequest(BaseModel):
    """
    Clears one or more ranges of values from a spreadsheet. The caller must
    specify the spreadsheet ID and one or more ranges. Only values are cleared --
    all other properties of the cell (such as formatting and data validation) are
    kept.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchClear
    """

    spreadsheet_id: _SpreadsheetIdWrite
    ranges: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            description=("The ranges to clear, in A1 notation or R1C1 notation."),
        ),
        Body(envelop=True),
    ]


class SpreadsheetsValuesBatchClearByDataFilterRequest(BaseModel):
    """
    Clears one or more ranges of values from a spreadsheet. The caller must
    specify the spreadsheet ID and one or more DataFilters. Ranges matching any
    of the specified data filters will be cleared. Only values are cleared -- all
    other properties of the cell (such as formatting, data validation, etc.) are
    kept.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchClearByDataFilter
    """

    spreadsheet_id: _SpreadsheetIdWrite
    data_filters: Annotated[
        List[DataFilter],
        Field(
            ...,
            min_length=1,
            description="The DataFilters used to determine which ranges to clear.",
        ),
        Body(envelop=True),
    ]
