# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
https://developers.google.com/workspace/drive/api/reference/rest/v3/drives
"""

from .actions import DrivesGetRequest, DrivesListRequest

__title__ = "Shared drives"

__all__ = ["DrivesListRequest", "DrivesGetRequest"]
