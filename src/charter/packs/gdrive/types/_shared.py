# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Text shared by more than one of this pack's resources.

Google documents ``supportsAllDrives``, ``fileId`` and the domain-admin flag
identically across Files, Permissions, Comments and Drives. A description
copied into each actions file is several places for a vendor rewording to
land, with nothing to notice when only some of them get it.
"""

from typing import Annotated, Optional

from pydantic import Field

from charter.types import Mode, Query

FILE_ID = "The ID of the file."
FILE_OR_DRIVE_ID = "The ID of the file or shared drive."
SUPPORTS_ALL_DRIVES = (
    "Whether the requesting application supports both My Drives and shared drives."
)
SUPPORTS_TEAM_DRIVES = "Deprecated: Use `supportsAllDrives` instead."
USE_DOMAIN_ADMIN_ACCESS = (
    "Issue the request as a domain administrator. If set to `true`, and if the "
    "following additional conditions are met, the requester is granted access: "
    "(1) The file ID parameter refers to a shared drive. (2) The requester is an "
    "administrator of the domain to which the shared drive belongs. For more "
    "information, see Manage shared drives as domain administrators."
)
INCLUDE_PERMISSIONS_FOR_VIEW = (
    "Specifies which additional view's permissions to include in the response. "
    "Only `published` is supported."
)
INCLUDE_LABELS = (
    "A comma-separated list of IDs of labels to include in the `labelInfo` part of the response."
)
KEEP_REVISION_FOREVER = (
    "Whether to set the `keepForever` field in the new head revision. This is "
    "only applicable to files with binary content in Google Drive. Only 200 "
    "revisions for the file can be kept forever. If the limit is reached, try "
    "deleting pinned revisions."
)
OCR_LANGUAGE = "A language hint for OCR processing during image import (ISO 639-1 code)."
IGNORE_DEFAULT_VISIBILITY = (
    "Whether to ignore the domain's default visibility settings for the created "
    "file. Domain administrators can choose to make all uploaded files visible "
    "to the domain by default; this parameter bypasses that behavior for the "
    "request. Permissions are still inherited from parent folders."
)
USE_CONTENT_AS_INDEXABLE_TEXT = "Whether to use the uploaded content as indexable text."
ENFORCE_SINGLE_PARENT = "Deprecated: Creating files in multiple folders is no longer supported."
ENFORCE_EXPANSIVE_ACCESS = "Deprecated: All requests use the expansive access rules."
PAGE_TOKEN = (
    "The token for continuing a previous list request on the next page. This "
    "should be set to the value of `nextPageToken` from the previous response."
)
ACKNOWLEDGE_ABUSE = (
    "Whether the user is acknowledging the risk of downloading known malware or "
    "other abusive files. This is only applicable when the `alt` parameter is "
    "set to `media` and the user is the owner of the file or an organizer of the "
    "shared drive in which the file resides."
)
TRANSFER_OWNERSHIP = (
    "Whether to transfer ownership to the specified user and downgrade the "
    "current owner to a writer. This parameter is required as an acknowledgement "
    "of the side effect. For more information, see Transfer file ownership."
)
FIELDS = (
    "Required. The `fields` parameter must be set. To return the exact fields "
    "you need, see Return specific fields. Example: `user,storageQuota` for "
    "about.get, or `comments(id,content,author,createdTime,resolved)` for "
    "comments.list."
)

# Deprecated query parameters stay on the wire schema so a Python caller can
# still send them, and stay out of the model's view so it cannot waste a turn
# composing a parameter the API will not act on.
SupportsTeamDrives = Annotated[
    Optional[bool],
    Field(None, description=SUPPORTS_TEAM_DRIVES),
    Query(),
    Mode("disabled"),
]
EnforceSingleParent = Annotated[
    Optional[bool],
    Field(None, description=ENFORCE_SINGLE_PARENT),
    Query(),
    Mode("disabled"),
]
EnforceExpansiveAccess = Annotated[
    Optional[bool],
    Field(None, description=ENFORCE_EXPANSIVE_ACCESS),
    Query(),
    Mode("disabled"),
]
SupportsAllDrives = Annotated[Optional[bool], Field(None, description=SUPPORTS_ALL_DRIVES), Query()]
UseDomainAdminAccess = Annotated[
    Optional[bool], Field(None, description=USE_DOMAIN_ADMIN_ACCESS), Query()
]
IncludePermissionsForView = Annotated[
    Optional[str], Field(None, description=INCLUDE_PERMISSIONS_FOR_VIEW), Query()
]
IncludeLabels = Annotated[Optional[str], Field(None, description=INCLUDE_LABELS), Query()]
KeepRevisionForever = Annotated[
    Optional[bool], Field(None, description=KEEP_REVISION_FOREVER), Query()
]
OcrLanguage = Annotated[Optional[str], Field(None, description=OCR_LANGUAGE), Query()]
IgnoreDefaultVisibility = Annotated[
    Optional[bool], Field(None, description=IGNORE_DEFAULT_VISIBILITY), Query()
]
UseContentAsIndexableText = Annotated[
    Optional[bool], Field(None, description=USE_CONTENT_AS_INDEXABLE_TEXT), Query()
]
PageToken = Annotated[Optional[str], Field(None, description=PAGE_TOKEN), Query()]
AcknowledgeAbuse = Annotated[Optional[bool], Field(None, description=ACKNOWLEDGE_ABUSE), Query()]
TransferOwnership = Annotated[Optional[bool], Field(None, description=TRANSFER_OWNERSHIP), Query()]
