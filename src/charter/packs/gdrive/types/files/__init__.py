"""
https://developers.google.com/workspace/drive/api/reference/rest/v3/files
"""

from .actions import (
    FilesCopyRequest,
    FilesCreateRequest,
    FilesDeleteRequest,
    FilesEmptyTrashRequest,
    FilesExportRequest,
    FilesGetRequest,
    FilesListRequest,
    FilesUpdateRequest,
)
from .models import File

__title__ = "Files"

__all__ = [
    "File",
    "FilesListRequest",
    "FilesGetRequest",
    "FilesExportRequest",
    "FilesCreateRequest",
    "FilesUpdateRequest",
    "FilesCopyRequest",
    "FilesDeleteRequest",
    "FilesEmptyTrashRequest",
]
