# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Google Sheets — read, write, append and clear ranges, create, copy and
batch-update spreadsheets.

Sheets speaks protobuf JSON. ``Format("proto_json")`` lets the model send a plain
2-D array while the API receives the encoding it expects, and
``Format("field_mask")`` turns a list of paths into the comma-joined string a
``FieldMask`` serialises to.

    from charter import StaticTokenProvider
    from charter.packs import gsheets

    gsheets.configure(StaticTokenProvider(access_token))
    await gsheets.spreadsheets_values_get.ainvoke(
        spreadsheet_id="1abc", range="Sheet1!A1:C10"
    )

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gsheets.response_handlers import (
    extract_batch_update,
    extract_spreadsheet,
)
from charter.packs.gsheets.types import (
    SpreadsheetsBatchUpdateRequest,
    SpreadsheetsCreateRequest,
    SpreadsheetsDeveloperMetadataGetRequest,
    SpreadsheetsDeveloperMetadataSearchRequest,
    SpreadsheetsGetByDataFilterRequest,
    SpreadsheetsGetRequest,
    SpreadsheetsSheetsCopyToRequest,
    SpreadsheetsValuesAppendRequest,
    SpreadsheetsValuesBatchClearByDataFilterRequest,
    SpreadsheetsValuesBatchClearRequest,
    SpreadsheetsValuesBatchGetByDataFilterRequest,
    SpreadsheetsValuesBatchGetRequest,
    SpreadsheetsValuesBatchUpdateByDataFilterRequest,
    SpreadsheetsValuesBatchUpdateRequest,
    SpreadsheetsValuesClearRequest,
    SpreadsheetsValuesGetRequest,
    SpreadsheetsValuesUpdateRequest,
)
from charter.tool import Tool

BASE_URL = "https://sheets.googleapis.com/"
QUOTA_DOC_URL = "https://developers.google.com/workspace/sheets/api/limits"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_credentials = DeferredCredentialProvider("gsheets", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_sheets = oauth_tool_factory(
    pack="gsheets",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google's query parameters are camelCase (`maxResults`, `singleEvents`),
    # like its bodies. Without this the default snake casing sends `max_results`,
    # which Google silently ignores — the worst kind of wrong, because the call
    # succeeds and returns unfiltered results.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
)

spreadsheets_values_get = _sheets(
    name="spreadsheets_values_get",
    args_schema=SpreadsheetsValuesGetRequest,
    method="GET",
    url_template="v4/spreadsheets/{spreadsheet_id}/values/{range}",
    description="Returns a range of values from a spreadsheet.",
    action_label="Reads rows from a sheet.",
    quota_cost=1,
)

spreadsheets_values_update = _sheets(
    name="spreadsheets_values_update",
    args_schema=SpreadsheetsValuesUpdateRequest,
    method="PUT",
    url_template="v4/spreadsheets/{spreadsheet_id}/values/{range}",
    description="Sets values in a range of a spreadsheet.",
    action_label="Writes values to a range.",
    quota_cost=1,
)

spreadsheets_values_append = _sheets(
    name="spreadsheets_values_append",
    args_schema=SpreadsheetsValuesAppendRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values/{range}:append",
    description="Appends values to a spreadsheet.",
    action_label="Adds rows to a sheet.",
    quota_cost=1,
)

spreadsheets_values_clear = _sheets(
    name="spreadsheets_values_clear",
    args_schema=SpreadsheetsValuesClearRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values/{range}:clear",
    description="Clears values from a spreadsheet.",
    action_label="Clears values from a range.",
    quota_cost=1,
)

spreadsheets_values_batch_get = _sheets(
    name="spreadsheets_values_batch_get",
    args_schema=SpreadsheetsValuesBatchGetRequest,
    method="GET",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchGet",
    description="Returns one or more ranges of values from a spreadsheet.",
    action_label="Reads multiple ranges.",
    quota_cost=1,
)

spreadsheets_values_batch_update = _sheets(
    name="spreadsheets_values_batch_update",
    args_schema=SpreadsheetsValuesBatchUpdateRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchUpdate",
    description="Sets values in one or more ranges of a spreadsheet.",
    action_label="Writes multiple ranges.",
    quota_cost=1,
)

spreadsheets_values_batch_clear = _sheets(
    name="spreadsheets_values_batch_clear",
    args_schema=SpreadsheetsValuesBatchClearRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchClear",
    description="Clears one or more ranges of values from a spreadsheet.",
    action_label="Clears multiple ranges.",
    quota_cost=1,
)

# `spreadsheets_values_batch_*_by_data_filter` overruns the tool name budget: a
# host composes `mcp__<server>__gsheets__` over the name and the whole thing must
# stay ≤ 64, which leaves 41 under the single server the setup page configures
# (`mcp__charter__gsheets__`) and 33 if you run one server per pack and name it
# `charter-gsheets`, spelling `gsheets` twice. 41 is the number tested, and
# `spreadsheets_developer_metadata_search` already spends 38 of it.
values_batch_get_by_data_filter = _sheets(
    name="values_batch_get_by_data_filter",
    args_schema=SpreadsheetsValuesBatchGetByDataFilterRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchGetByDataFilter",
    description="Returns one or more ranges of values that match the specified data filters.",
    action_label="Reads ranges matching data filters.",
    quota_cost=1,
)

values_batch_update_by_data_filter = _sheets(
    name="values_batch_update_by_data_filter",
    args_schema=SpreadsheetsValuesBatchUpdateByDataFilterRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchUpdateByDataFilter",
    description="Sets values in one or more ranges of a spreadsheet.",
    action_label="Writes values matching data filters.",
    quota_cost=1,
)

values_batch_clear_by_data_filter = _sheets(
    name="values_batch_clear_by_data_filter",
    args_schema=SpreadsheetsValuesBatchClearByDataFilterRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/values:batchClearByDataFilter",
    description="Clears one or more ranges of values from a spreadsheet.",
    action_label="Clears ranges matching data filters.",
    quota_cost=1,
)

spreadsheets_create = _sheets(
    name="spreadsheets_create",
    args_schema=SpreadsheetsCreateRequest,
    method="POST",
    url_template="v4/spreadsheets",
    description="Create a new spreadsheet.",
    action_label="Creates a new spreadsheet.",
    quota_cost=1,
    response_handler=extract_spreadsheet,
)

spreadsheets_get = _sheets(
    name="spreadsheets_get",
    args_schema=SpreadsheetsGetRequest,
    method="GET",
    url_template="v4/spreadsheets/{spreadsheet_id}",
    description="Get spreadsheet metadata and structure.",
    action_label="Retrieves spreadsheet information.",
    quota_cost=1,
    response_handler=extract_spreadsheet,
)

spreadsheets_batch_update = _sheets(
    name="spreadsheets_batch_update",
    args_schema=SpreadsheetsBatchUpdateRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}:batchUpdate",
    description=(
        "Apply a list of updates to a spreadsheet. Each request sets exactly one "
        "kind of edit — add_sheet, update_cells, merge_cells and so on. Requests "
        "are applied in order, atomically: if any is invalid, none are applied."
    ),
    action_label="Updates spreadsheet formatting and structure.",
    quota_cost=1,
    response_handler=extract_batch_update,
)

spreadsheets_sheets_copy_to = _sheets(
    name="spreadsheets_sheets_copy_to",
    args_schema=SpreadsheetsSheetsCopyToRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/sheets/{sheet_id}:copyTo",
    description=(
        "Copy a single sheet from one spreadsheet to another. Returns the "
        "properties of the newly created sheet in the destination spreadsheet."
    ),
    action_label="Copies a sheet to another spreadsheet.",
    quota_cost=1,
)

spreadsheets_get_by_data_filter = _sheets(
    name="spreadsheets_get_by_data_filter",
    args_schema=SpreadsheetsGetByDataFilterRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}:getByDataFilter",
    description=(
        "Get a spreadsheet, selecting which ranges to return with DataFilters "
        "(an A1 range, a GridRange, or developer metadata). Grid data is omitted "
        "unless include_grid_data is true."
    ),
    action_label="Retrieves filtered spreadsheet information.",
    quota_cost=1,
    response_handler=extract_spreadsheet,
)

spreadsheets_developer_metadata_get = _sheets(
    name="spreadsheets_developer_metadata_get",
    args_schema=SpreadsheetsDeveloperMetadataGetRequest,
    method="GET",
    url_template="v4/spreadsheets/{spreadsheet_id}/developerMetadata/{metadata_id}",
    description=(
        "Get one developer metadata entry by its spreadsheet-scoped ID. Developer "
        "metadata is arbitrary data pinned to a row, column, sheet or the "
        "spreadsheet itself, which follows that location as the sheet is edited."
    ),
    action_label="Reads a developer metadata entry.",
    quota_cost=1,
)

spreadsheets_developer_metadata_search = _sheets(
    name="spreadsheets_developer_metadata_search",
    args_schema=SpreadsheetsDeveloperMetadataSearchRequest,
    method="POST",
    url_template="v4/spreadsheets/{spreadsheet_id}/developerMetadata:search",
    description=(
        "Find developer metadata matching one or more DataFilters. A filter that "
        "is a developer_metadata_lookup selects entries by key, value, visibility "
        "or location type; a filter that names a range returns the metadata "
        "associated with locations intersecting it."
    ),
    action_label="Searches developer metadata.",
    quota_cost=1,
)

TOOLS: list[Tool] = [
    spreadsheets_values_get,
    spreadsheets_values_update,
    spreadsheets_values_append,
    spreadsheets_values_clear,
    spreadsheets_values_batch_get,
    spreadsheets_values_batch_update,
    spreadsheets_values_batch_clear,
    values_batch_get_by_data_filter,
    values_batch_update_by_data_filter,
    values_batch_clear_by_data_filter,
    spreadsheets_create,
    spreadsheets_get,
    spreadsheets_batch_update,
    spreadsheets_sheets_copy_to,
    spreadsheets_get_by_data_filter,
    spreadsheets_developer_metadata_get,
    spreadsheets_developer_metadata_search,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "spreadsheets_values_get",
    "spreadsheets_values_update",
    "spreadsheets_values_append",
    "spreadsheets_values_clear",
    "spreadsheets_values_batch_get",
    "spreadsheets_values_batch_update",
    "spreadsheets_values_batch_clear",
    "values_batch_get_by_data_filter",
    "values_batch_update_by_data_filter",
    "values_batch_clear_by_data_filter",
    "spreadsheets_create",
    "spreadsheets_get",
    "spreadsheets_batch_update",
    "spreadsheets_sheets_copy_to",
    "spreadsheets_get_by_data_filter",
    "spreadsheets_developer_metadata_get",
    "spreadsheets_developer_metadata_search",
]
