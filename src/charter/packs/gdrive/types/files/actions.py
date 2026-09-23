# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the Files collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files

Descriptions are the API's own words rather than a summary of them: they are the
only guide the model has, and paraphrasing them is how a pack drifts from the
documentation it was written against.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Mode, Path, Query

from .._shared import (
    FILE_ID,
    AcknowledgeAbuse,
    EnforceSingleParent,
    IgnoreDefaultVisibility,
    IncludeLabels,
    IncludePermissionsForView,
    KeepRevisionForever,
    OcrLanguage,
    PageToken,
    SupportsAllDrives,
    SupportsTeamDrives,
    UseContentAsIndexableText,
)
from .models import File

Corpora = Literal["user", "domain", "drive", "allDrives"]
Corpus = Literal["user", "domain"]
Alt = Literal["json", "media"]

PAGE_SIZE = (
    "The maximum number of files to return. The service may return fewer than "
    "this value. If unspecified, at most 100 files will be returned for shared "
    "drives, and the entire list of files for non-shared drives. The maximum "
    "value is 1000; values above 1000 will be coerced to 1000."
)
Q = (
    "A query for filtering the file results. For supported syntax, see Search "
    "for files and folders. This method returns all files by default, including "
    "trashed files. If you don't want trashed files to appear in the list, use "
    "`trashed = false` in `q`."
)
CORPORA = (
    "Specifies a collection of items (files or documents) to which the query "
    "applies. Supported items include: `user`, `domain`, `drive`, `allDrives`. "
    "Prefer `user` or `drive` to `allDrives` for efficiency. By default, corpora "
    "is set to `user`. However, this can change depending on the filter set "
    "through the `q` parameter. If `driveId` is specified, corpora must be `drive`."
)
DRIVE_ID = "ID of the shared drive to search."
ORDER_BY = (
    "A comma-separated list of sort keys. Valid keys are: `createdTime` (when "
    "the file was created; avoid using this key for queries on large item "
    "collections as it might result in timeouts or other issues; for time-related "
    "sorting on large item collections, use `modifiedTime desc` instead); "
    "`folder` (the folder ID, sorted using alphabetical ordering); "
    "`modifiedByMeTime`; `modifiedTime`; `name` (alphabetical, so 1, 12, 2, 22); "
    "`name_natural` (natural sort, so 1, 2, 12, 22); `quotaBytesUsed`; `recency`; "
    "`sharedWithMeTime`; `starred`; `viewedByMeTime`. Each key sorts ascending by "
    "default, but can be reversed with the `desc` modifier. Example usage: "
    "`folder,modifiedTime desc,name`."
)
SPACES = (
    "A comma-separated list of spaces to query within the corpora. Supported "
    "values are `drive` and `appDataFolder`. If omitted, the server queries the "
    "`drive` space."
)
INCLUDE_ITEMS_FROM_ALL_DRIVES = (
    "Whether both My Drive and shared drive items should be included in results."
)
ADD_PARENTS = "A comma-separated list of parent IDs to add."
REMOVE_PARENTS = "A comma-separated list of parent IDs to remove."
EXPORT_MIME_TYPE = (
    "Required. The MIME type of the format requested for this export. For a list "
    "of supported MIME types, see Export MIME types for Google Workspace "
    "documents. Common values: `text/plain`, `text/html`, `text/csv`, "
    "`application/pdf`, "
    "`application/vnd.openxmlformats-officedocument.wordprocessingml.document`, "
    "`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`."
)
ALT = (
    "If you provide `alt=media`, then the response includes the file contents in "
    "the response body. Downloading content with `alt=media` only works if the "
    "file is stored in Drive. To download Google Docs, Sheets, and Slides use "
    "`files.export` instead."
)
EMPTY_TRASH_DRIVE_ID = "If set, empties the trash of the provided shared drive."


class FilesListRequest(BaseModel):
    """
    Lists the user's files. This method accepts the `q` parameter, which is a
    search query combining one or more search terms. This method returns all
    files by default, including trashed files. If you don't want trashed files
    to appear in the list, use the `trashed=false` query term to remove trashed
    files from the results.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list
    """

    q: Annotated[Optional[str], Field(None, description=Q), Query()] = None
    page_size: Annotated[
        Optional[int], Field(None, ge=1, le=1000, description=PAGE_SIZE), Query()
    ] = None
    page_token: PageToken = None
    corpora: Annotated[Optional[Corpora], Field(None, description=CORPORA), Query()] = None
    drive_id: Annotated[Optional[str], Field(None, description=DRIVE_ID), Query()] = None
    order_by: Annotated[Optional[str], Field(None, description=ORDER_BY), Query()] = None
    spaces: Annotated[Optional[str], Field(None, description=SPACES), Query()] = None
    include_items_from_all_drives: Annotated[
        Optional[bool], Field(None, description=INCLUDE_ITEMS_FROM_ALL_DRIVES), Query()
    ] = None
    include_permissions_for_view: IncludePermissionsForView = None
    include_labels: IncludeLabels = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    include_team_drive_items: Annotated[
        Optional[bool],
        Field(None, description="Deprecated: Use `includeItemsFromAllDrives` instead."),
        Query(),
        Mode("disabled"),
    ] = None
    corpus: Annotated[
        Optional[Corpus],
        Field(None, description="Deprecated: The source of files to list. Use `corpora` instead."),
        Query(),
        Mode("disabled"),
    ] = None
    team_drive_id: Annotated[
        Optional[str],
        Field(None, description="Deprecated: Use `driveId` instead."),
        Query(),
        Mode("disabled"),
    ] = None

    @model_validator(mode="after")
    def _drive_id_requires_corpora_drive(self) -> FilesListRequest:
        """If `driveId` is specified, corpora must be `drive`."""
        if self.drive_id is not None and self.corpora != "drive":
            raise ValueError(
                "If driveId is specified, corpora must be 'drive'. Drop driveId to "
                "query another corpus, or set corpora to 'drive'."
            )
        return self


class FilesGetRequest(BaseModel):
    """
    Gets a file's metadata or content by ID. If you provide the URL parameter
    `alt=media`, then the response includes the file contents in the response
    body. Downloading content with `alt=media` only works if the file is stored
    in Drive. To download Google Docs, Sheets, and Slides use `files.export`
    instead.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/get
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    acknowledge_abuse: AcknowledgeAbuse = None
    include_permissions_for_view: IncludePermissionsForView = None
    include_labels: IncludeLabels = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    alt: Annotated[Optional[Alt], Field(None, description=ALT), Query()] = None


class FilesExportRequest(BaseModel):
    """
    Exports a Google Workspace document to the requested MIME type and returns
    exported byte content. Note that the exported content is limited to 10 MB.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/export
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    mime_type: Annotated[str, Field(..., description=EXPORT_MIME_TYPE), Query()]


class FilesCreateRequest(BaseModel):
    """
    Creates a file. This pack sends metadata only — a folder, a Google Doc, or
    an empty blob. Media upload (`/upload/drive/v3/files`) is not expressed;
    create the file here and then write content through the Docs or Sheets
    packs, or with a subsequent `files.update` of metadata.

    Apps creating shortcuts with the `create` method must specify the MIME type
    `application/vnd.google-apps.shortcut`. Apps should specify a file extension
    in the `name` property when inserting files with the API.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create
    """

    file: Annotated[
        File,
        Field(
            ...,
            description=(
                "The file resource to create. For a folder, set `mimeType` to "
                "`application/vnd.google-apps.folder`. For a Google Doc, Sheet or "
                "Slide, use the corresponding `application/vnd.google-apps.*` MIME "
                "type. `parents` takes at most one folder ID."
            ),
        ),
        Body(),
    ]
    ignore_default_visibility: IgnoreDefaultVisibility = None
    keep_revision_forever: KeepRevisionForever = None
    ocr_language: OcrLanguage = None
    use_content_as_indexable_text: UseContentAsIndexableText = None
    include_permissions_for_view: IncludePermissionsForView = None
    include_labels: IncludeLabels = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_single_parent: EnforceSingleParent = None


class FilesUpdateRequest(BaseModel):
    """
    Updates a file's metadata, content, or both. When calling this method, only
    populate fields in the request that you want to modify. When updating
    fields, some fields might be changed automatically, such as `modifiedDate`.
    This method supports patch semantics.

    Update requests must use the `addParents` and `removeParents` parameters to
    modify the parents list; `parents` in the body is ignored.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/update
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    file: Annotated[
        File,
        Field(
            ...,
            description=(
                "The file resource. Only populate fields you want to modify; the "
                "rest keep their stored values. To move a file, use `addParents` "
                "and `removeParents` rather than `parents`."
            ),
        ),
        Body(),
    ]
    add_parents: Annotated[Optional[str], Field(None, description=ADD_PARENTS), Query()] = None
    remove_parents: Annotated[Optional[str], Field(None, description=REMOVE_PARENTS), Query()] = (
        None
    )
    keep_revision_forever: KeepRevisionForever = None
    ocr_language: OcrLanguage = None
    use_content_as_indexable_text: UseContentAsIndexableText = None
    include_permissions_for_view: IncludePermissionsForView = None
    include_labels: IncludeLabels = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_single_parent: EnforceSingleParent = None


class FilesCopyRequest(BaseModel):
    """
    Creates a copy of a file and applies any requested updates with patch
    semantics.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/copy
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    file: Annotated[
        File,
        Field(
            ...,
            description=(
                "The file resource to apply on the copy, with patch semantics. "
                "Typically `name` and optionally `parents`. If `parents` is omitted, "
                "the copy inherits any discoverable parent of the source file."
            ),
        ),
        Body(),
    ]
    ignore_default_visibility: IgnoreDefaultVisibility = None
    keep_revision_forever: KeepRevisionForever = None
    ocr_language: OcrLanguage = None
    copy_comments: Annotated[
        Optional[bool],
        Field(None, description="Whether to copy the comments associated with the file."),
        Query(),
    ] = None
    include_permissions_for_view: IncludePermissionsForView = None
    include_labels: IncludeLabels = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_single_parent: EnforceSingleParent = None


class FilesDeleteRequest(BaseModel):
    """
    Permanently deletes a file owned by the user without moving it to the trash.
    If the file belongs to a shared drive, the user must be an `organizer` on
    the parent folder. If the target is a folder, all descendants owned by the
    user are also deleted.

    To move a file to the trash instead, use `files.update` with `trashed` set
    to `true`.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/delete
    """

    file_id: Annotated[str, Field(..., description=FILE_ID), Path()]
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_single_parent: EnforceSingleParent = None


class FilesEmptyTrashRequest(BaseModel):
    """
    Permanently deletes all of the user's trashed files.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/files/emptyTrash
    """

    drive_id: Annotated[Optional[str], Field(None, description=EMPTY_TRASH_DRIVE_ID), Query()] = (
        None
    )
    enforce_single_parent: EnforceSingleParent = None
