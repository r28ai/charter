# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Input schemas for the ``spreadsheets`` collection.

``spreadsheets.create`` takes a Spreadsheet as its body. ``spreadsheets.get``
is a GET with query filters. ``spreadsheets.batchUpdate`` is a list of
``Request`` oneofs applied atomically. ``spreadsheets.getByDataFilter`` is the
POST form of get, selecting ranges by ``DataFilter``. ``spreadsheets.sheets.copyTo``
copies one sheet into another spreadsheet.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path, Query

from .models import CommentsViewMode, DataFilter, Spreadsheet
from .requests import Request


class SpreadsheetsCreateRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.create``.

    Creates a spreadsheet, returning the newly created spreadsheet.
    The request body contains an instance of Spreadsheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/create
    """

    spreadsheet: Annotated[
        Spreadsheet,
        Field(
            default_factory=Spreadsheet,
            description=(
                "The spreadsheet to create. Contains properties (e.g., title), "
                "sheets, named ranges, and so on. Only the title and sheet "
                "structure are typically honoured on create; the spreadsheet is "
                "otherwise empty."
            ),
        ),
        Body(),
    ]


class SpreadsheetsGetRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.get``.

    Returns the spreadsheet at the given ID. The caller must specify the spreadsheet ID.
    By default, data within grids is not returned. You can include grid data in one of 2 ways:

    - Specify a field mask listing your desired fields using the ``fields`` URL parameter in HTTP
    - Set the ``includeGridData`` URL parameter to true. If a field mask is set, the ``includeGridData`` parameter is ignored

    For large spreadsheets, as a best practice, retrieve only the specific spreadsheet fields that you want.
    To retrieve only subsets of spreadsheet data, use the ``ranges`` URL parameter. Ranges are specified using A1 notation.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/get
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The spreadsheet to request."),
        Path(),
    ]
    ranges: Annotated[
        Optional[List[str]],
        Field(None, description="The ranges to retrieve from the spreadsheet."),
        Query(),
    ]
    include_grid_data: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True if grid data should be returned. This parameter is ignored "
                "if a field mask was set in the request."
            ),
        ),
        Query(),
    ]
    exclude_tables_in_banded_ranges: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True if tables should be excluded in the banded ranges. False if not set."
            ),
        ),
        Query(),
    ]


class SpreadsheetsBatchUpdateRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.batchUpdate``.

    Applies one or more updates to the spreadsheet.
    Each request is validated before being applied. If any request is not valid then
    the entire request will fail and nothing will be applied.
    Some requests have replies to give you some information about how they are applied.
    The replies will mirror the requests. For example, if you applied 4 updates and the
    3rd one had a reply, then the response will have 2 empty replies, the actual reply,
    and another empty reply, in that order.

    Due to the collaborative nature of spreadsheets, it is not guaranteed that the
    spreadsheet will reflect exactly your changes after this completes, however it is
    guaranteed that the updates in the request will be applied together atomically.
    Your changes may be altered with respect to collaborator changes. If there are no
    collaborators, the spreadsheet should reflect your changes.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The spreadsheet to apply the updates to."),
        Path(),
    ]
    requests: Annotated[
        List[Request],
        Field(
            ...,
            description=(
                "A list of updates to apply to the spreadsheet. Requests will be "
                "applied in the order they are specified. Each Request sets exactly "
                "one kind of update. If any request is not valid, no requests will "
                "be applied."
            ),
        ),
        Body(envelop=True),
    ]
    include_spreadsheet_in_response: Annotated[
        Optional[bool],
        Field(
            None,
            description="Determines if the update response should include the spreadsheet resource.",
        ),
        Body(),
    ]
    response_ranges: Annotated[
        Optional[List[str]],
        Field(
            None,
            description=(
                "Limits the ranges included in the response spreadsheet. Meaningful "
                "only if includeSpreadsheetInResponse is 'true'."
            ),
        ),
        Body(),
    ]
    response_include_grid_data: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True if grid data should be returned. Meaningful only if "
                "includeSpreadsheetInResponse is 'true'. This parameter is ignored "
                "if a field mask was set in the request."
            ),
        ),
        Body(),
    ]
    comments_view_mode: Annotated[
        Optional[CommentsViewMode],
        Field(
            None,
            description=(
                "The comments view mode to apply to the spreadsheet. This allows "
                "viewing the spreadsheet with comments omitted or included. If one "
                "is not specified, COMMENTS_VIEW_MODE_OMITTED is used. Meaningful "
                "only if includeSpreadsheetInResponse is 'true'. Developer Preview."
            ),
        ),
        Body(),
    ]


class CopySheetToAnotherSpreadsheetRequest(BaseModel):
    """
    The request to copy a sheet across spreadsheets.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.sheets/copyTo
    """

    destination_spreadsheet_id: str = Field(
        ...,
        description="The ID of the spreadsheet to copy the sheet to.",
    )


class SpreadsheetsSheetsCopyToRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.sheets.copyTo``.

    Copies a single sheet from a spreadsheet to another spreadsheet. Returns the
    properties of the newly created sheet.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.sheets/copyTo
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The ID of the spreadsheet containing the sheet to copy."),
        Path(),
    ]
    sheet_id: Annotated[
        int,
        Field(..., description="The ID of the sheet to copy."),
        Path(),
    ]
    body: Annotated[
        CopySheetToAnotherSpreadsheetRequest,
        Field(..., description="The destination spreadsheet."),
        Body(),
    ]


class SpreadsheetsGetByDataFilterRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.getByDataFilter``.

    Returns the spreadsheet at the given ID. This method differs from
    spreadsheets.get in that it allows selecting which subsets of spreadsheet
    data to return by specifying a ``dataFilters`` parameter. Multiple
    DataFilters can be specified. Specifying one or more data filters returns
    the portions of the spreadsheet that intersect ranges matched by any of
    the filters.

    By default, data within grids is not returned. You can include grid data
    in one of two ways:

    - Specify a field mask listing your desired fields using the ``fields`` URL parameter.
    - Set the ``includeGridData`` parameter to true. If a field mask is set, the
      ``includeGridData`` parameter is ignored.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/getByDataFilter
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The spreadsheet to request."),
        Path(),
    ]
    data_filters: Annotated[
        Optional[List[DataFilter]],
        Field(
            None,
            description=(
                "The DataFilters used to select which ranges to retrieve from the spreadsheet."
            ),
        ),
        Body(),
    ]
    include_grid_data: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True if grid data should be returned. This parameter is ignored "
                "if a field mask was set in the request."
            ),
        ),
        Body(),
    ]
    exclude_tables_in_banded_ranges: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "True if tables should be excluded in the banded ranges. False if not set."
            ),
        ),
        Body(),
    ]
    comments_view_mode: Annotated[
        Optional[CommentsViewMode],
        Field(
            None,
            description=(
                "The comments view mode to apply to the spreadsheet. This allows "
                "viewing the spreadsheet with comments omitted or included. If one "
                "is not specified, COMMENTS_VIEW_MODE_OMITTED is used. Developer Preview."
            ),
        ),
        Body(),
    ]
