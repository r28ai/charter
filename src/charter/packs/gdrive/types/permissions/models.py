"""
Permission resource.

API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

PermissionType = Literal["user", "group", "domain", "anyone"]
PermissionRole = Literal[
    "owner",
    "organizer",
    "fileOrganizer",
    "writer",
    "commenter",
    "reader",
    "publishedReader",
]
PermissionView = Literal["published", "metadata"]
PermissionDetailsType = Literal["file", "member"]


class PermissionDetails(BaseModel):
    """
    Details of whether the permissions on this item are inherited or are
    directly on this item.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions#Permission.PermissionDetails
    """

    inherited_from: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The ID of the item from which this permission is "
                "inherited. This is only populated for items in shared drives."
            ),
        ),
        Mode("response_only"),
    ] = None
    permission_type: Annotated[
        Optional[PermissionDetailsType],
        Field(
            None,
            description=(
                "Output only. The permission type for this user. Supported values "
                "include: `file`, `member`."
            ),
        ),
        Mode("response_only"),
    ] = None
    role: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The primary role for this user. Supported values "
                "include: `owner`, `organizer`, `fileOrganizer`, `writer`, "
                "`commenter`, `reader`."
            ),
        ),
        Mode("response_only"),
    ] = None
    inherited: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether this permission is inherited. This field is "
                "always populated. This is an output-only field."
            ),
        ),
        Mode("response_only"),
    ] = None


class TeamDrivePermissionDetails(BaseModel):
    """
    Deprecated: Output only. Use `permissionDetails` instead.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions#Permission
    """

    inherited_from: Annotated[
        Optional[str],
        Field(
            None,
            description="Deprecated: Output only. Use `permissionDetails/inheritedFrom` instead.",
        ),
        Mode("disabled"),
    ] = None
    role: Annotated[
        Optional[str],
        Field(
            None,
            description="Deprecated: Output only. Use `permissionDetails/role` instead.",
        ),
        Mode("disabled"),
    ] = None
    team_drive_permission_type: Annotated[
        Optional[str],
        Field(
            None,
            description="Deprecated: Output only. Use `permissionDetails/permissionType` instead.",
        ),
        Mode("disabled"),
    ] = None
    inherited: Annotated[
        Optional[bool],
        Field(
            None,
            description="Deprecated: Output only. Use `permissionDetails/inherited` instead.",
        ),
        Mode("disabled"),
    ] = None


class Permission(BaseModel):
    """
    A permission for a file. A permission grants a user, group, domain, or the
    world access to a file or a folder hierarchy.

    By default, permission requests only return a subset of fields. Use
    `permissions.get` with the permission ID from `permissions.list` for the
    rest.

    API Reference: https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions#Permission
    """

    type: PermissionType = Field(
        ...,
        description=(
            "The type of the grantee. Supported values include: `user`, `group`, "
            "`domain`, `anyone`. When creating a permission, if `type` is `user` "
            "or `group`, you must provide an `emailAddress` for the user or group. "
            "If `type` is `domain`, you must provide a `domain`. If `type` is "
            "`anyone`, no extra information is required."
        ),
    )
    role: PermissionRole = Field(
        ...,
        description=(
            "The role granted by this permission. Supported values include: "
            "`owner`, `organizer`, `fileOrganizer`, `writer`, `commenter`, "
            "`reader`. For more information, see Roles and permissions."
        ),
    )
    email_address: Optional[str] = Field(
        None,
        description=(
            "The email address of the user or group to which this permission "
            "refers. Required when creating a permission of type `user` or `group`."
        ),
    )
    domain: Optional[str] = Field(
        None,
        description=(
            "The domain to which this permission refers. Required when creating a "
            "permission of type `domain`."
        ),
    )
    allow_file_discovery: Optional[bool] = Field(
        None,
        description=(
            "Whether the permission allows the file to be discovered through "
            "search. This is only applicable for permissions of type `domain` or "
            "`anyone`."
        ),
    )
    expiration_time: Optional[str] = Field(
        None,
        description=(
            "The time at which this permission will expire (RFC 3339 date-time). "
            "Expiration times have the following restrictions: they can only be "
            "set on user and group permissions; the time must be in the future; "
            "the time cannot be more than a year in the future."
        ),
    )
    pending_owner: Optional[bool] = Field(
        None,
        description=(
            "Whether the account associated with this permission is a pending "
            "owner. Only populated for permissions of type `user` for files that "
            "aren't in a shared drive."
        ),
    )
    view: Optional[PermissionView] = Field(
        None,
        description=(
            "Indicates the view for this permission. Only populated for permissions "
            "that belong to a view. The only supported values are `published` and "
            "`metadata`: `published` — the permission's role is `publishedReader`; "
            "`metadata` — the item is only visible to the `metadata` view because "
            "the item has limited access and the scope has at least read access to "
            "the parent. The `metadata` view is only supported on folders."
        ),
    )
    inherited_permissions_disabled: Optional[bool] = Field(
        None,
        description=(
            "When `true`, only organizers, owners, and users with permissions added "
            "directly on the item can access it."
        ),
    )

    id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. The ID of this permission. This is a unique identifier "
                "for the grantee, and is published in the User resource as "
                "`permissionId`. IDs should be treated as opaque values."
            ),
        ),
        Mode("response_only"),
    ] = None
    display_name: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                'Output only. The "pretty" name of the value of the permission. '
                "The following is a list of examples for each type of permission: "
                "`user` — User's full name, as defined for their Google Account; "
                "`group` — Name of the Google Group; `domain` — String domain name; "
                "`anyone` — No `displayName` is present."
            ),
        ),
        Mode("response_only"),
    ] = None
    photo_link: Annotated[
        Optional[str],
        Field(
            None,
            description="Output only. A link to the user's profile photo, if available.",
        ),
        Mode("response_only"),
    ] = None
    kind: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Output only. Identifies what kind of resource this is. Value: the "
                'fixed string `"drive#permission"`.'
            ),
        ),
        Mode("response_only"),
    ] = None
    deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Output only. Whether the account associated with this permission "
                "has been deleted. This field only pertains to permissions of type "
                "`user` or `group`."
            ),
        ),
        Mode("response_only"),
    ] = None
    permission_details: Annotated[
        Optional[List[PermissionDetails]],
        Field(
            None,
            description=(
                "Output only. Details of whether the permissions on this item are "
                "inherited or are directly on this item."
            ),
        ),
        Mode("response_only"),
    ] = None
    team_drive_permission_details: Annotated[
        Optional[List[TeamDrivePermissionDetails]],
        Field(
            None,
            description="Output only. Deprecated: Output only. Use `permissionDetails` instead.",
        ),
        Mode("disabled"),
    ] = None
