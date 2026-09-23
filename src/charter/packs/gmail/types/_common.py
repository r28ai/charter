# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Descriptions Gmail documents once and every resource repeats.

``userId`` is a path parameter on all 23 endpoints and Google words it the same
way on all 23 reference pages. Written out per schema it drifted into five
wordings, one of them carrying markdown bold into a field description, and the
generated reference showed all five for what is one parameter. Constants keep
the text Google's, in one place, so a reword lands everywhere at once.
"""

from __future__ import annotations

__all__ = ["USER_ID_DESCRIPTION", "PAGE_TOKEN_DESCRIPTION"]

USER_ID_DESCRIPTION = (
    "The user's email address. The special value 'me' can be used to indicate "
    "the authenticated user."
)

PAGE_TOKEN_DESCRIPTION = "Page token to retrieve a specific page of results in the list."
