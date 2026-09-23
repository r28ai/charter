# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schema for Notion's async task endpoint.

API Reference: https://developers.notion.com/reference/retrieve-an-async-task
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from charter.types import Path

__all__ = ["AsyncTasksRetrieveRequest"]


class AsyncTasksRetrieveRequest(BaseModel):
    """Check on work Notion took in the background.

    Creating a page from a large Markdown body with `allow_async` answers 202
    and an async task instead of the finished page. This is how you find out
    whether it worked: the task's status goes from `queued` or `running` to a
    terminal one.

    API Reference: https://developers.notion.com/reference/retrieve-an-async-task
    """

    task_id: Annotated[str, Field(..., description="The ID of the async task."), Path()]
