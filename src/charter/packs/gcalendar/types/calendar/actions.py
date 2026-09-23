# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the Calendars collection.

The Calendars resource is the calendar itself — its title, description and time
zone. CalendarList is the authenticated user's *view* of a calendar, carrying
their colour, their notification settings and their access role. They are
different resources with different endpoints, and this is the one that answers
"what time zone is this calendar in".

API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendars
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from charter.types import Path

from .._shared import CALENDAR_ID


class CalendarsGetRequest(BaseModel):
    """Returns metadata for a calendar.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendars/get
    """

    calendar_id: Annotated[str, Field(..., description=CALENDAR_ID), Path()]

    model_config = {"validate_assignment": True, "extra": "forbid"}
