# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request models for GitHub's users endpoints.

https://docs.github.com/en/rest/users
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["UsersGetAuthenticatedRequest"]


class UsersGetAuthenticatedRequest(BaseModel):
    """Get the authenticated user.

    This endpoint takes no parameters, so the schema has none. Useful to resolve
    "me" to a login before filtering issues or pull requests by author.

    API Reference: https://docs.github.com/en/rest/users/users#get-the-authenticated-user
    """
