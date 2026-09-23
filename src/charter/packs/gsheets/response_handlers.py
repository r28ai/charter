# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Google Sheets response trimming — context economy only.

The values endpoints are already lean: a range of cells comes back as a list of
lists and there is nothing in it to drop. The *spreadsheet* resource is not.
``properties`` carries ``spreadsheetTheme`` (851 bytes of font and theme
colours) and ``defaultFormat`` (417 bytes of padding, borders and text format)
on a payload whose useful half is a title, a time zone, and the names and sizes
of the sheets — the things a caller needs to build an A1 range.

Only the tools that return that resource have handlers here. A handler on
``values.get`` would save tens of bytes and add a way to be wrong.

``spreadsheets.batchUpdate`` is in that set and is easy to miss, because the
spreadsheet only comes back when the caller asks for it with
``include_spreadsheet_in_response``. When they do, it arrives untrimmed while
``spreadsheets.get`` trims the same object — the inconsistency is invisible
until someone sets the flag.
"""

from __future__ import annotations

from typing import Any, Dict, List

__all__ = [
    "extract_spreadsheet",
    "extract_batch_update",
]

# Read off properties; the rest of that object is theme and default cell format.
_PROPERTIES = ("title", "locale", "timeZone")
# Read off a sheet's properties; enough to name it and to size an A1 range.
_SHEET = ("sheetId", "title", "index", "sheetType")


def _sheet(sheet: Dict[str, Any]) -> Dict[str, Any]:
    properties = sheet.get("properties") or {}
    out: Dict[str, Any] = {k: properties[k] for k in _SHEET if properties.get(k) is not None}
    grid = properties.get("gridProperties") or {}
    kept = {k: grid[k] for k in ("rowCount", "columnCount", "frozenRowCount") if grid.get(k)}
    if kept:
        out["gridProperties"] = kept
    return out


async def extract_spreadsheet(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``spreadsheets.get`` and ``spreadsheets.create``.

    Keeps the identifiers, the title, the locale and time zone that decide how
    a written value is parsed, and the sheet list a range is built from.
    """
    out: Dict[str, Any] = {}
    for key in ("spreadsheetId", "spreadsheetUrl"):
        if response.get(key):
            out[key] = response[key]

    properties = response.get("properties") or {}
    kept = {k: properties[k] for k in _PROPERTIES if properties.get(k) is not None}
    if kept:
        out["properties"] = kept

    sheets: List[Dict[str, Any]] = [
        _sheet(s) for s in response.get("sheets") or [] if isinstance(s, dict)
    ]
    if sheets:
        out["sheets"] = sheets
    return out


async def extract_batch_update(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``spreadsheets.batchUpdate``.

    ``replies`` is the result the caller asked for and passes through whole —
    one reply per request, in the order they were sent, and a projection over
    that union of thirty reply types would be thirty ways to drop the one field
    that mattered. What is trimmed is ``updatedSpreadsheet``, which is the same
    resource :func:`extract_spreadsheet` already handles everywhere else.

    ``replies`` survives even when every entry is empty: Sheets sends ``{}`` for
    a request that has no reply, and the positions are what line the list up
    with the requests that were sent.
    """
    out: Dict[str, Any] = {}
    if response.get("spreadsheetId"):
        out["spreadsheetId"] = response["spreadsheetId"]
    if response.get("replies") is not None:
        out["replies"] = response["replies"]

    updated = response.get("updatedSpreadsheet")
    if isinstance(updated, dict):
        out["updatedSpreadsheet"] = await extract_spreadsheet(updated)
    return out
