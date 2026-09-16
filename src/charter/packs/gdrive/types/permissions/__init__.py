"""
https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions
"""

from .actions import (
    PermissionsCreateRequest,
    PermissionsDeleteRequest,
    PermissionsGetRequest,
    PermissionsListRequest,
    PermissionsUpdateRequest,
)
from .models import Permission

__title__ = "Permissions"

__all__ = [
    "Permission",
    "PermissionsCreateRequest",
    "PermissionsListRequest",
    "PermissionsGetRequest",
    "PermissionsUpdateRequest",
    "PermissionsDeleteRequest",
]
