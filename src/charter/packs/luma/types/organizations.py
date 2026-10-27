# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma organizations operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field

from charter.packs.luma.types.common import (
    LaunchStatus,
    OrganizationsCalendarsCreateLocation,
    SortDirection,
)
from charter.types import Body, Gloss, Query
from charter.types.model import PackModel

__all__ = [
    "OrganizationsAdminsListRequest",
    "OrganizationsCalendarsListRequest",
    "OrganizationsEventsListRequest",
    "OrganizationsCalendarsCreateRequest",
    "OrganizationsEventsTransferCalendarRequest",
]


class OrganizationsAdminsListRequest(PackModel):
    """List Organization Admins

    List all admins for the organization.

    API Reference: https://docs.luma.com/reference/get_v1-organizations-admins-list
    """


class OrganizationsCalendarsListRequest(PackModel):
    """List Organization Calendars

    List all calendars belonging to the organization.

    API Reference: https://docs.luma.com/reference/get_v1-organizations-calendars-list
    """

    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]


class OrganizationsEventsListRequest(PackModel):
    """List Organization Events

    List all events across all calendars belonging to the organization. Events are
    deduplicated if they appear on multiple calendars within the organization.

    API Reference: https://docs.luma.com/reference/get_v1-organizations-events-list
    """

    before: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Query(),
    ]
    after: Annotated[
        Optional[str],
        Field(None, description="ISO 8601 Datetime. For example, 2022-10-19T03:27:13.673Z"),
        Query(),
    ]
    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]
    sort_direction: Annotated[
        Optional[SortDirection],
        Field(None),
        Query(),
        Gloss("Sort order. The `nulls last` variants put entries with no value at the end."),
    ]


class OrganizationsCalendarsCreateRequest(PackModel):
    """Create Calendar

    Create a new calendar within the organization. The calendar will be managed by the API
    key owner.

    API Reference: https://docs.luma.com/reference/post_v2-organizations-calendars-create
    """

    name: Annotated[
        str,
        Field(..., description="Name of the calendar."),
        Body(),
    ]
    slug: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "URL slug for the calendar page (e.g. 'my-community' → lu.ma/my-community)."
            ),
        ),
        Body(),
    ]
    description: Annotated[
        Optional[str],
        Field(None, description="Short description of the calendar."),
        Body(),
    ]
    avatar_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Specify an image that has been uploaded to the Luma CDN. If not "
                "provided, a random default avatar will be used."
            ),
        ),
        Body(),
    ]
    tint_color: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Tint color for the calendar in hex format (e.g. '#E3CBEF'). If not "
                "provided, a random color matching the default avatar will be used."
            ),
        ),
        Body(),
    ]
    launch_status: Annotated[
        Optional[LaunchStatus],
        Field(
            None,
            description=(
                "Defaults to `launched` (Active). Use `coming-soon` to show a "
                "placeholder page while you set the calendar up."
            ),
        ),
        Body(),
    ]
    website: Annotated[
        Optional[str],
        Field(None, description="Website URL. `https://` is added if missing."),
        Body(),
    ]
    instagram_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Instagram handle or profile URL (e.g. 'luma' or 'https://instagram.com/luma')."
            ),
        ),
        Body(),
    ]
    twitter_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "X (Twitter) handle or profile URL (e.g. '@luma' or 'https://x.com/luma')."
            ),
        ),
        Body(),
    ]
    youtube_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "YouTube handle or channel URL (e.g. '@luma' or 'https://youtube.com/@luma')."
            ),
        ),
        Body(),
    ]
    tiktok_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "TikTok handle or profile URL (e.g. '@luma' or 'https://tiktok.com/@luma')."
            ),
        ),
        Body(),
    ]
    linkedin_handle: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "LinkedIn company or profile URL (e.g. 'https://linkedin.com/company/luma')."
            ),
        ),
        Body(),
    ]
    location: Annotated[
        Optional[OrganizationsCalendarsCreateLocation],
        Field(
            None,
            description=(
                "City the calendar is based in. Use `{ type: 'lookup', query }` to "
                "search Google Maps for a city, or `{ type: 'google', place_id }` with "
                "a city's Google Places ID. The calendar's timezone and coordinate come"
                " from the city."
            ),
        ),
        Body(),
    ]


class OrganizationsEventsTransferCalendarRequest(PackModel):
    """Transfer Event Calendar

    Transfer an event from its current managing calendar to a different calendar within the
    organization. The event's managing calendar changes to the destination calendar. Both
    the source and destination calendars must belong to the organization.

    API Reference:
    https://docs.luma.com/reference/post_v1-organizations-events-transfer-calendar
    """

    event_id: Annotated[
        str,
        Field(..., description="Event ID, this usually starts with evt-"),
        Body(),
    ]
    calendar_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "Destination calendar ID, this usually starts with cal-. Must belong to"
                " the organization."
            ),
        ),
        Body(),
    ]
