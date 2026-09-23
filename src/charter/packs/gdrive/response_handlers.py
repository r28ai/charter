# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Google Drive response trimming — context economy only.

A Drive ``File`` resource is tens of kilobytes once ``capabilities``,
``permissions``, ``exportLinks`` and media metadata are on it. A list of fifty
files therefore arrives as hundreds of kilobytes to say fifty times what fits
in a line each.

These handlers keep what a model can act on — the identifier it needs to
update, share or export, the name and MIME type it matches on, the parent it
moves against — and drop the rest. Fields that are only *sometimes* meaningful
(a description, a star, trash, a shortcut target) are kept when present and
omitted when not.

``files.export`` is not JSON: the runtime wraps the body as ``{"raw": ...}``.
The handler surfaces that as ``content``, and names a truncation rather than
inlining a 10 MB export.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "extract_file",
    "extract_files",
    "extract_export",
    "extract_permission",
    "extract_permissions",
    "extract_comment",
    "extract_comments",
    "extract_reply",
    "extract_revision",
    "extract_revisions",
    "extract_drive",
    "extract_drives",
    "extract_about",
]

_EXPORT_LIMIT = 32_768


def _cursor(response: Dict[str, Any]) -> Optional[str]:
    """The page token, read from the pack declaration rather than re-derived."""
    from charter.packs.gdrive import GOOGLE_PAGINATION

    return GOOGLE_PAGINATION.next_cursor(response)


def _user(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    kept = {k: value[k] for k in ("displayName", "emailAddress", "me") if value.get(k) is not None}
    return kept or None


def _trim_file(file: Dict[str, Any]) -> Dict[str, Any]:
    """One file, reduced to what an agent can act on."""
    out: Dict[str, Any] = {
        "id": file.get("id"),
        "name": file.get("name", ""),
        "mimeType": file.get("mimeType"),
    }
    for key in ("parents", "webViewLink", "size", "modifiedTime", "createdTime", "driveId"):
        if file.get(key):
            out[key] = file[key]
    for key in ("description", "trashed", "starred", "shared"):
        if file.get(key):
            out[key] = file[key]
    shortcut = file.get("shortcutDetails") or {}
    if shortcut.get("targetId"):
        out["shortcutDetails"] = {"targetId": shortcut["targetId"]}
        if shortcut.get("targetMimeType"):
            out["shortcutDetails"]["targetMimeType"] = shortcut["targetMimeType"]
    return out


async def extract_file(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a single File resource, or pass through an ``alt=media`` body."""
    if "raw" in response and "id" not in response:
        return await extract_export(response)
    return _trim_file(response)


async def extract_files(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``files.list``. Keeps the files, the page token, and incompleteSearch."""
    out: Dict[str, Any] = {
        "files": [_trim_file(f) for f in response.get("files") or [] if isinstance(f, dict)]
    }
    if response.get("incompleteSearch"):
        out["incompleteSearch"] = True
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


async def extract_export(response: Dict[str, Any]) -> Dict[str, Any]:
    """Surface exported bytes as ``content``, and name a truncation."""
    raw = response.get("raw")
    if raw is None:
        return response
    text = raw if isinstance(raw, str) else str(raw)
    if len(text) > _EXPORT_LIMIT:
        return {"content": text[:_EXPORT_LIMIT], "truncated": True, "length": len(text)}
    return {"content": text}


def _trim_permission(permission: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": permission.get("id"),
        "type": permission.get("type"),
        "role": permission.get("role"),
    }
    for key in (
        "emailAddress",
        "domain",
        "displayName",
        "expirationTime",
        "deleted",
        "pendingOwner",
    ):
        if permission.get(key) is not None and permission.get(key) is not False:
            out[key] = permission[key]
    if permission.get("allowFileDiscovery"):
        out["allowFileDiscovery"] = True
    return out


async def extract_permission(response: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_permission(response)


async def extract_permissions(response: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "permissions": [
            _trim_permission(p) for p in response.get("permissions") or [] if isinstance(p, dict)
        ]
    }
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


def _trim_reply(reply: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"id": reply.get("id")}
    for key in ("content", "action", "createdTime", "modifiedTime"):
        if reply.get(key):
            out[key] = reply[key]
    if reply.get("deleted"):
        out["deleted"] = True
    author = _user(reply.get("author"))
    if author:
        out["author"] = author
    return out


def _trim_comment(comment: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"id": comment.get("id")}
    for key in ("content", "createdTime", "modifiedTime", "anchor"):
        if comment.get(key):
            out[key] = comment[key]
    for flag in ("resolved", "deleted"):
        if comment.get(flag):
            out[flag] = True
    author = _user(comment.get("author"))
    if author:
        out["author"] = author
    quoted = comment.get("quotedFileContent") or {}
    if quoted.get("value"):
        out["quotedFileContent"] = quoted["value"]
    replies = comment.get("replies")
    if replies:
        out["replies"] = [_trim_reply(r) for r in replies if isinstance(r, dict)]
    return out


async def extract_comment(response: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_comment(response)


async def extract_comments(response: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "comments": [
            _trim_comment(c) for c in response.get("comments") or [] if isinstance(c, dict)
        ]
    }
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


async def extract_reply(response: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_reply(response)


def _trim_revision(revision: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": revision.get("id"),
        "mimeType": revision.get("mimeType"),
    }
    for key in ("modifiedTime", "size", "originalFilename", "keepForever", "published"):
        if revision.get(key):
            out[key] = revision[key]
    return out


async def extract_revision(response: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_revision(response)


async def extract_revisions(response: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "revisions": [
            _trim_revision(r) for r in response.get("revisions") or [] if isinstance(r, dict)
        ]
    }
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


def _trim_drive(drive: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": drive.get("id"),
        "name": drive.get("name", ""),
    }
    for key in ("createdTime", "hidden", "colorRgb"):
        if drive.get(key):
            out[key] = drive[key]
    restrictions = drive.get("restrictions")
    if isinstance(restrictions, dict):
        kept = {
            k: restrictions[k]
            for k in (
                "domainUsersOnly",
                "driveMembersOnly",
                "copyRequiresWriterPermission",
                "sharingFoldersRequiresOrganizerPermission",
            )
            if restrictions.get(k)
        }
        if kept:
            out["restrictions"] = kept
    return out


async def extract_drive(response: Dict[str, Any]) -> Dict[str, Any]:
    return _trim_drive(response)


async def extract_drives(response: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "drives": [_trim_drive(d) for d in response.get("drives") or [] if isinstance(d, dict)]
    }
    cursor = _cursor(response)
    if cursor:
        out["nextPageToken"] = cursor
    return out


async def extract_about(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``about.get`` to the user, quota, and the maps an export is built from."""
    out: Dict[str, Any] = {}
    user = _user(response.get("user"))
    if user:
        out["user"] = user
    quota = response.get("storageQuota")
    if isinstance(quota, dict):
        kept = {
            k: quota[k]
            for k in ("limit", "usage", "usageInDrive", "usageInDriveTrash")
            if quota.get(k)
        }
        if kept:
            out["storageQuota"] = kept
    for key in ("maxUploadSize", "canCreateDrives", "appInstalled"):
        if response.get(key) is not None:
            out[key] = response[key]
    for key in ("importFormats", "exportFormats", "folderColorPalette"):
        if response.get(key):
            out[key] = response[key]
    return out
