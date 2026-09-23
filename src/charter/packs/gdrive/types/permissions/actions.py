# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the Permissions collection.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.execution.schema import partial_of
from charter.types import Body, Mode, Path, Query

from .._shared import (
    FILE_OR_DRIVE_ID,
    EnforceExpansiveAccess,
    IncludePermissionsForView,
    PageToken,
    SupportsAllDrives,
    SupportsTeamDrives,
    TransferOwnership,
    UseDomainAdminAccess,
)
from .models import Permission

PERMISSION_ID = "The ID of the permission."
EMAIL_MESSAGE = "A plain text custom message to include in the notification email."
MOVE_TO_NEW_OWNERS_ROOT = (
    "This parameter only takes effect if the item isn't in a shared drive and "
    "the request is attempting to transfer the ownership of the item. If set to "
    "`true`, the item is moved to the new owner's My Drive root folder and all "
    "prior parents removed. If set to `false`, parents aren't changed."
)
SEND_NOTIFICATION_EMAIL = (
    "Whether to send a notification email when sharing to users or groups. This "
    "defaults to `true` for users and groups, and is not allowed for other "
    "requests. It must not be disabled for ownership transfers."
)
PAGE_SIZE = (
    "The maximum number of permissions to return. The service may return fewer "
    "than this value. If unspecified, at most 100 permissions will be returned "
    "for shared drives, and the entire list of permissions for non-shared drives. "
    "The maximum value is 100; values above 100 will be coerced to 100."
)
REMOVE_EXPIRATION = "Whether to remove the expiration date."


class PermissionsCreateRequest(BaseModel):
    """
    Creates a permission for a file or shared drive.

    Warning: Concurrent permissions operations on the same file aren't supported;
    only the last update is applied.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/create
    """

    file_id: Annotated[str, Field(..., description=FILE_OR_DRIVE_ID), Path()]
    permission: Annotated[
        Permission,
        Field(..., description="The permission to create."),
        Body(),
    ]
    email_message: Annotated[Optional[str], Field(None, description=EMAIL_MESSAGE), Query()] = None
    send_notification_email: Annotated[
        Optional[bool], Field(None, description=SEND_NOTIFICATION_EMAIL), Query()
    ] = None
    transfer_ownership: TransferOwnership = None
    move_to_new_owners_root: Annotated[
        Optional[bool], Field(None, description=MOVE_TO_NEW_OWNERS_ROOT), Query()
    ] = None
    use_domain_admin_access: UseDomainAdminAccess = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_expansive_access: EnforceExpansiveAccess = None
    enforce_single_parent: Annotated[
        Optional[bool],
        Field(None, description="Deprecated: See `moveToNewOwnersRoot` for details."),
        Query(),
        Mode("disabled"),
    ] = None

    @model_validator(mode="after")
    def _grantee_matches_type(self) -> PermissionsCreateRequest:
        """When creating a permission, the type decides which identifying field is required."""
        permission = self.permission
        if permission.type in ("user", "group") and not permission.email_address:
            raise ValueError(
                "When type is 'user' or 'group', emailAddress is required for the user or group."
            )
        if permission.type == "domain" and not permission.domain:
            raise ValueError("When type is 'domain', domain is required.")
        return self


class PermissionsListRequest(BaseModel):
    """
    Lists a file's or shared drive's permissions.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/list
    """

    file_id: Annotated[str, Field(..., description=FILE_OR_DRIVE_ID), Path()]
    page_size: Annotated[
        Optional[int], Field(None, ge=1, le=100, description=PAGE_SIZE), Query()
    ] = None
    page_token: PageToken = None
    include_permissions_for_view: IncludePermissionsForView = None
    use_domain_admin_access: UseDomainAdminAccess = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None


class PermissionsGetRequest(BaseModel):
    """
    Gets a permission by ID.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/get
    """

    file_id: Annotated[str, Field(..., description="The ID of the file."), Path()]
    permission_id: Annotated[str, Field(..., description=PERMISSION_ID), Path()]
    use_domain_admin_access: UseDomainAdminAccess = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None


PatchPermission = partial_of(
    Permission,
    name="PatchPermission",
    doc="""Request body for Drive `permissions.update`.

    Create requires `type` and `role`; patch leaves out what it is not changing,
    so it needs nothing. Derived rather than written out, so the field
    descriptions have one home.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/update
    """,
)


class PermissionsUpdateRequest(BaseModel):
    """
    Updates a permission with patch semantics.

    Warning: Concurrent permissions operations on the same file aren't supported;
    only the last update is applied.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/update
    """

    file_id: Annotated[str, Field(..., description=FILE_OR_DRIVE_ID), Path()]
    permission_id: Annotated[str, Field(..., description=PERMISSION_ID), Path()]
    permission: Annotated[
        PatchPermission,  # type: ignore[valid-type]
        Field(
            ...,
            description=(
                "The permission resource. Only populate fields you want to modify; "
                "the rest keep their stored values."
            ),
        ),
        Body(),
    ]
    remove_expiration: Annotated[
        Optional[bool], Field(None, description=REMOVE_EXPIRATION), Query()
    ] = None
    transfer_ownership: TransferOwnership = None
    use_domain_admin_access: UseDomainAdminAccess = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_expansive_access: EnforceExpansiveAccess = None


class PermissionsDeleteRequest(BaseModel):
    """
    Deletes a permission.

    Warning: Concurrent permissions operations on the same file aren't supported;
    only the last update is applied.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions/delete
    """

    file_id: Annotated[str, Field(..., description=FILE_OR_DRIVE_ID), Path()]
    permission_id: Annotated[str, Field(..., description=PERMISSION_ID), Path()]
    use_domain_admin_access: UseDomainAdminAccess = None
    supports_all_drives: SupportsAllDrives = None
    supports_team_drives: SupportsTeamDrives = None
    enforce_expansive_access: EnforceExpansiveAccess = None
