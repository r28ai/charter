# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the ``spreadsheets.developerMetadata`` collection.

Developer metadata is arbitrary data pinned to a location in a spreadsheet — a
row, a column, a sheet, or the spreadsheet itself — that follows the location as
the sheet is edited. ``get`` fetches one entry by its spreadsheet-scoped id;
``search`` returns every entry a ``DataFilter`` selects, either by
``DeveloperMetadataLookup`` or by intersecting a region.

API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.developerMetadata
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Path

from ..spreadsheets.models import DataFilter


class SpreadsheetsDeveloperMetadataGetRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.developerMetadata.get``.

    Returns the developer metadata with the specified ID. The caller must specify
    the spreadsheet ID and the developer metadata's unique metadataId.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.developerMetadata/get
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The ID of the spreadsheet to retrieve metadata from."),
        Path(),
    ]
    metadata_id: Annotated[
        int,
        Field(..., description="The ID of the developer metadata to retrieve."),
        Path(),
    ]


class SpreadsheetsDeveloperMetadataSearchRequest(BaseModel):
    """
    Input schema for Google Sheets ``spreadsheets.developerMetadata.search``.

    Returns all developer metadata matching the specified DataFilter. If the
    provided DataFilter represents a DeveloperMetadataLookup object, this returns
    all DeveloperMetadata entries selected by it. If the DataFilter represents a
    location in a spreadsheet, this returns all developer metadata associated
    with locations intersecting that region.

    API Reference: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.developerMetadata/search
    """

    spreadsheet_id: Annotated[
        str,
        Field(..., description="The ID of the spreadsheet to retrieve metadata from."),
        Path(),
    ]
    # The only body field, so `envelop` is what keeps `dataFilters` as the root
    # key: an unwrapped single body would post the bare array Sheets rejects.
    data_filters: Annotated[
        Optional[List[DataFilter]],
        Field(
            None,
            description=(
                "The data filters describing the criteria used to determine which "
                "DeveloperMetadata entries to return. DeveloperMetadata matching "
                "any of the specified filters are included in the response."
            ),
        ),
        Body(envelop=True),
    ]
