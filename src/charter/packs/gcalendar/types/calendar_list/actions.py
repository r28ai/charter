# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the CalendarList collection.

API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendarList
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import ConflictsWith, Path, Query

from .._shared import CALENDAR_ID
from .models import AccessRole

SYNC_TOKEN_REASON = (
    "An incremental sync continues the query the token came from, so narrowing it "
    "would leave the client state inconsistent. Drop syncToken to run a fresh "
    "query, or drop the others to continue the sync."
)
_NoSyncToken = ConflictsWith("sync_token", reason=SYNC_TOKEN_REASON)


class CalendarListGetRequest(BaseModel):
    """Returns a calendar from the user's calendar list.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/get
    """

    calendar_id: Annotated[str, Field(..., description=CALENDAR_ID), Path()]

    model_config = {"validate_assignment": True, "extra": "forbid"}


class CalendarListListRequest(BaseModel):
    """Returns the calendars on the user's calendar list.

    API Reference: https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list
    """

    # Path parameter (implicit)
    user_id: Annotated[
        str,
        Field(
            "me",
            description=(
                'User identifier. The special value "me" can be used to indicate '
                "the authenticated user. Other values are not supported by the REST API "
                "but the field is included for completeness and symmetry with other endpoints."
            ),
        ),
        Path(),
    ]

    # Query parameters
    max_results: Annotated[
        Optional[int],
        Field(
            None,
            ge=1,
            le=250,
            description=(
                "Maximum number of entries returned on one result page. By default the "
                "value is 100 entries. The page size can never be larger than 250 entries. "
                "Optional."
            ),
        ),
        Query(),
    ]
    min_access_role: Annotated[
        Optional[AccessRole],
        Field(
            None,
            description=(
                "The minimum access role for the user in the returned entries. Optional. "
                'The default is no restriction. Acceptable values are: "freeBusyReader" '
                '(the user can read free/busy information), "owner" (the user can read '
                'and modify events and access control lists), "reader" (the user can read '
                'events that are not private), "writer" (the user can read and modify '
                'events), "writerWithoutPrivateAccess" (the user can read and modify '
                "events that aren't private; the user can read free/busy information "
                "about private events but can't modify them)."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    page_token: Annotated[
        Optional[str],
        Field(None, description="Token specifying which result page to return. Optional."),
        Query(),
    ]
    show_deleted: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to include deleted calendar list entries in the result. Optional. "
                "The default is False."
            ),
        ),
        Query(),
    ]
    show_hidden: Annotated[
        Optional[bool],
        Field(None, description="Whether to show hidden entries. Optional. The default is False."),
        Query(),
    ]
    show_own_organization_only: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Whether to show only entries for calendars from the organization. This "
                "parameter is only applicable to Google Workspace users. Optional. The "
                "default is False."
            ),
        ),
        Query(),
        _NoSyncToken,
    ]
    sync_token: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Token obtained from the nextSyncToken field returned on the last page of "
                "results from the previous list request. It makes the result of this list "
                "request contain only entries that have changed since then. If only "
                "read-only fields such as calendar properties or ACLs have changed, the "
                "entry won't be returned. All entries deleted and hidden since the previous "
                "list request will always be in the result set and it is not allowed to set "
                "showDeleted neither showHidden to False. To ensure client state "
                "consistency minAccessRole and showOwnOrganizationOnly query parameters "
                "cannot be specified together with nextSyncToken. If the syncToken expires, "
                "the server will respond with a 410 GONE response code and the client "
                "should clear its storage and perform a full synchronization without any "
                "syncToken. Optional. The default is to return all entries."
            ),
        ),
        Query(),
    ]

    @model_validator(mode="after")
    def _sync_token_may_not_hide_what_it_reports(self) -> CalendarListListRequest:
        """The half of the rule that is not an exclusion.

        Which parameters syncToken refuses is declared by ``ConflictsWith`` on
        each of them. These two may be set, but not to False — a different
        predicate, and not worth a marker on two occurrences.
        """
        if self.sync_token is None:
            return self
        for field, wire in (("show_deleted", "showDeleted"), ("show_hidden", "showHidden")):
            if getattr(self, field) is False:
                raise ValueError(
                    f"{wire} cannot be False alongside syncToken: an incremental sync always "
                    f"reports the entries deleted and hidden since the token was issued, and "
                    f"hiding them would make the result silently incomplete."
                )
        return self

    model_config = {"validate_assignment": True, "extra": "forbid"}
