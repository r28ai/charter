# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schema for Granola's audit endpoint.

The one endpoint in this API that is not about a note. It reads the workspace's
audit log: membership changes, note views, recordings, whatever Granola records.

API Reference: https://docs.granola.ai/api-reference/list-audit-events
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import CURSOR_DESCRIPTION
from charter.types import Query

__all__ = ["AuditListRequest"]

# One year is the whole window, and a date outside it is rejected rather than
# quietly clamped. Both bounds say so, because a caller who gets it wrong gets a
# 400 and no page.
_RETENTION = "Must fall within the one-year retention window; an earlier date is rejected."


class AuditListRequest(BaseModel):
    """List audit events, filtered by action and by when they happened.

    Events come back in ``collected_at`` order rather than ``occurred_at``
    order. Granola learns about some events after the fact, so ``occurred_at``
    can move backwards down a page while ``collected_at`` never does, which is
    what makes the cursor stable.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    action: Annotated[
        Optional[str],
        Field(
            None,
            pattern=r"^[a-z][a-z0-9_.-]*$",
            description=(
                "Return only events with this exact action, or events whose action "
                "starts with it followed by a dot (`workspace` returns "
                "`workspace.member_added` but not `workspace_automation.created`). "
                "Lowercase, as actions are."
            ),
        ),
        Query(),
    ]
    occurred_before: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                f"Return events that occurred before this date. {_RETENTION} "
                "A date (`2026-01-27`) or a date-time (`2026-01-27T15:30:00Z`)."
            ),
        ),
        Query(),
    ]
    occurred_after: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                f"Return events that occurred after this date. {_RETENTION} "
                "A date (`2026-01-27`) or a date-time (`2026-01-27T15:30:00Z`)."
            ),
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(None, description=CURSOR_DESCRIPTION),
        Query(),
    ]
    page_size: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=30,
            description=(
                "Maximum number of audit events to return per page. The server "
                "returns 10 when this is absent."
            ),
        ),
        Query(),
    ]
