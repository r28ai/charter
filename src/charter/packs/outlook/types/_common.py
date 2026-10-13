# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Descriptions Microsoft writes once and every Outlook endpoint repeats.

A message ID and a folder ID are path parameters on most of this pack's
tools. Written out per schema they drift; constants keep one wording, and the
folder one carries the well-known names, which work in place of an ID
regardless of the mailbox's locale.
"""

from __future__ import annotations

__all__ = ["FOLDER_ID_DESCRIPTION", "MESSAGE_ID_DESCRIPTION", "WELL_KNOWN_FOLDER_NAMES"]

MESSAGE_ID_DESCRIPTION = "The ID of the message."

# https://learn.microsoft.com/en-us/graph/api/resources/mailfolder#well-known-folder-names
WELL_KNOWN_FOLDER_NAMES = (
    "archive",
    "clutter",
    "conflicts",
    "conversationhistory",
    "deleteditems",
    "drafts",
    "inbox",
    "junkemail",
    "localfailures",
    "msgfolderroot",
    "outbox",
    "recoverableitemsdeletions",
    "scheduled",
    "searchfolders",
    "sentitems",
    "serverfailures",
    "syncissues",
)

FOLDER_ID_DESCRIPTION = (
    "The folder ID, or a well-known folder name. Well-known names work regardless of "
    "the locale of the user's mailbox: " + ", ".join(WELL_KNOWN_FOLDER_NAMES) + "."
)
