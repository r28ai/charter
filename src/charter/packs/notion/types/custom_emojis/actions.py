# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schema for Notion's custom emoji endpoint.

API Reference: https://developers.notion.com/reference/emoji-object
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field

from charter.packs.notion.types.common import PaginatedQuery
from charter.types import Query

__all__ = ["CustomEmojisListRequest"]


class CustomEmojisListRequest(PaginatedQuery):
    """List the workspace's own uploaded emoji.

    Their IDs are what a `custom_emoji` icon references.

    API Reference: https://developers.notion.com/reference/list-custom-emojis
    """

    name: Annotated[
        Optional[str],
        Field(None, description="Return only emoji whose name matches this."),
        Query(),
    ]
