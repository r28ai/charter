"""
https://developers.google.com/workspace/drive/api/reference/rest/v3/comments
"""

from .actions import (
    CommentsCreateRequest,
    CommentsDeleteRequest,
    CommentsListRequest,
    CommentsUpdateRequest,
)
from .models import Comment, Reply

__title__ = "Comments"

__all__ = [
    "Comment",
    "Reply",
    "CommentsListRequest",
    "CommentsCreateRequest",
    "CommentsUpdateRequest",
    "CommentsDeleteRequest",
]
