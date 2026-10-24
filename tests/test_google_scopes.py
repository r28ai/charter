# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Every Google tool offers only scopes Google accepts, and asks for nothing restricted it can avoid.

``scopes_for`` is the consent screen, and for Google the consent screen decides
what launching costs: one restricted scope means a security assessment before
other people can connect, repeated every year. A pack-wide scope made every
Gmail tool ask for ``gmail.modify``, so an agent that only sent mail needed
the assessment too. Each tool now lists the scopes Google accepts for its
method (less those reaching only part of what the tool can do), narrowest first,
and ``scopes_for`` picks the narrowest set the tools handed out need.

``scripts/live_google_scopes_check.py`` asks Google the same question of a real
account: each tool with exactly each option it declares, and with none.
"""

from __future__ import annotations

import pytest

from charter.auth import AnyOf, scopes_for
from charter.packs import gcalendar, gdocs, gdrive, gforms, gmail, gsheets
from charter.packs._google import GOOGLE_SCOPE_ORDER

PACKS = (gmail, gdrive, gcalendar, gdocs, gsheets, gforms)
_AUTH = "https://www.googleapis.com/auth/"

# The scopes Google lists for each method, read from the discovery documents
# (``https://gmail.googleapis.com/$discovery/rest?version=v1`` and the same for
# drive v3, calendar v3, docs v1, sheets v4, forms v1) on 2026-10-23. These are
# the "Authorization scopes" sections of the reference pages. The Workspace
# add-on scopes are left out: no tool here runs inside an add-on.
ACCEPTED = {
    "gmail.messages_send": (
        "gmail.users.messages.send",
        "gmail.compose gmail.modify gmail.send mail.google.com",
    ),
    "gmail.messages_list": (
        "gmail.users.messages.list",
        "gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.messages_get": (
        "gmail.users.messages.get",
        "gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.messages_attachments_get": (
        "gmail.users.messages.attachments.get",
        "gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.messages_modify": ("gmail.users.messages.modify", "gmail.modify mail.google.com"),
    "gmail.messages_batch_modify": (
        "gmail.users.messages.batchModify",
        "gmail.modify mail.google.com",
    ),
    "gmail.threads_list": (
        "gmail.users.threads.list",
        "gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.threads_get": (
        "gmail.users.threads.get",
        "gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.threads_modify": ("gmail.users.threads.modify", "gmail.modify mail.google.com"),
    "gmail.threads_trash": ("gmail.users.threads.trash", "gmail.modify mail.google.com"),
    "gmail.threads_untrash": ("gmail.users.threads.untrash", "gmail.modify mail.google.com"),
    "gmail.threads_delete": ("gmail.users.threads.delete", "mail.google.com"),
    "gmail.drafts_create": (
        "gmail.users.drafts.create",
        "gmail.compose gmail.modify mail.google.com",
    ),
    "gmail.drafts_get": (
        "gmail.users.drafts.get",
        "gmail.compose gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.drafts_list": (
        "gmail.users.drafts.list",
        "gmail.compose gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.drafts_update": (
        "gmail.users.drafts.update",
        "gmail.compose gmail.modify mail.google.com",
    ),
    "gmail.drafts_delete": (
        "gmail.users.drafts.delete",
        "gmail.compose gmail.modify mail.google.com",
    ),
    "gmail.drafts_send": ("gmail.users.drafts.send", "gmail.compose gmail.modify mail.google.com"),
    "gmail.labels_list": (
        "gmail.users.labels.list",
        "gmail.labels gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.labels_get": (
        "gmail.users.labels.get",
        "gmail.labels gmail.metadata gmail.modify gmail.readonly mail.google.com",
    ),
    "gmail.labels_create": (
        "gmail.users.labels.create",
        "gmail.labels gmail.modify mail.google.com",
    ),
    "gmail.labels_update": (
        "gmail.users.labels.update",
        "gmail.labels gmail.modify mail.google.com",
    ),
    "gmail.labels_patch": ("gmail.users.labels.patch", "gmail.labels gmail.modify mail.google.com"),
    "gmail.labels_delete": (
        "gmail.users.labels.delete",
        "gmail.labels gmail.modify mail.google.com",
    ),
    "gdrive.files_list": (
        "drive.files.list",
        "drive drive.appdata drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.files_get": (
        "drive.files.get",
        "drive drive.appdata drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.files_export": (
        "drive.files.export",
        "drive drive.file drive.meet.readonly drive.readonly",
    ),
    "gdrive.files_create": ("drive.files.create", "drive drive.appdata drive.file"),
    "gdrive.files_update": (
        "drive.files.update",
        "drive drive.appdata drive.file drive.metadata drive.scripts",
    ),
    "gdrive.files_copy": (
        "drive.files.copy",
        "drive drive.appdata drive.file drive.photos.readonly",
    ),
    "gdrive.files_delete": ("drive.files.delete", "drive drive.appdata drive.file"),
    "gdrive.files_empty_trash": ("drive.files.emptyTrash", "drive"),
    "gdrive.permissions_create": ("drive.permissions.create", "drive drive.file"),
    "gdrive.permissions_list": (
        "drive.permissions.list",
        "drive drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.permissions_get": (
        "drive.permissions.get",
        "drive drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.permissions_update": ("drive.permissions.update", "drive drive.file"),
    "gdrive.permissions_delete": ("drive.permissions.delete", "drive drive.file"),
    "gdrive.comments_list": (
        "drive.comments.list",
        "drive drive.file drive.meet.readonly drive.readonly",
    ),
    "gdrive.comments_create": ("drive.comments.create", "drive drive.file"),
    "gdrive.comments_update": ("drive.comments.update", "drive drive.file"),
    "gdrive.comments_delete": ("drive.comments.delete", "drive drive.file"),
    "gdrive.replies_create": ("drive.replies.create", "drive drive.file"),
    "gdrive.replies_update": ("drive.replies.update", "drive drive.file"),
    "gdrive.replies_delete": ("drive.replies.delete", "drive drive.file"),
    "gdrive.revisions_list": (
        "drive.revisions.list",
        "drive drive.appdata drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.revisions_get": (
        "drive.revisions.get",
        "drive drive.appdata drive.file drive.meet.readonly drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gdrive.drives_list": ("drive.drives.list", "drive drive.readonly"),
    "gdrive.drives_get": ("drive.drives.get", "drive drive.readonly"),
    "gdrive.about_get": (
        "drive.about.get",
        "drive drive.appdata drive.file drive.metadata drive.metadata.readonly drive.photos.readonly drive.readonly",
    ),
    "gcalendar.events_get": (
        "calendar.events.get",
        "calendar calendar.app.created calendar.events calendar.events.freebusy calendar.events.owned calendar.events.owned.readonly calendar.events.public.readonly calendar.events.readonly calendar.readonly",
    ),
    "gcalendar.events_list": (
        "calendar.events.list",
        "calendar calendar.app.created calendar.events calendar.events.freebusy calendar.events.owned calendar.events.owned.readonly calendar.events.public.readonly calendar.events.readonly calendar.readonly",
    ),
    "gcalendar.events_instances": (
        "calendar.events.instances",
        "calendar calendar.app.created calendar.events calendar.events.freebusy calendar.events.owned calendar.events.owned.readonly calendar.events.public.readonly calendar.events.readonly calendar.readonly",
    ),
    "gcalendar.events_insert": (
        "calendar.events.insert",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.events_update": (
        "calendar.events.update",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.events_patch": (
        "calendar.events.patch",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.events_move": (
        "calendar.events.move",
        "calendar calendar.events calendar.events.owned",
    ),
    "gcalendar.events_quick_add": (
        "calendar.events.quickAdd",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.events_import": (
        "calendar.events.import",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.events_delete": (
        "calendar.events.delete",
        "calendar calendar.app.created calendar.events calendar.events.owned",
    ),
    "gcalendar.calendar_list_list": (
        "calendar.calendarList.list",
        "calendar calendar.calendarlist calendar.calendarlist.readonly calendar.readonly",
    ),
    "gcalendar.calendar_list_get": (
        "calendar.calendarList.get",
        "calendar calendar.app.created calendar.calendarlist calendar.calendarlist.readonly calendar.readonly",
    ),
    "gcalendar.calendars_get": (
        "calendar.calendars.get",
        "calendar calendar.app.created calendar.calendars calendar.calendars.readonly calendar.readonly",
    ),
    "gdocs.documents_get": (
        "docs.documents.get",
        "documents documents.readonly drive drive.file drive.readonly",
    ),
    "gdocs.documents_create": ("docs.documents.create", "documents drive drive.file"),
    "gdocs.documents_batch_update": ("docs.documents.batchUpdate", "documents drive drive.file"),
    "gsheets.spreadsheets_values_get": (
        "sheets.spreadsheets.values.get",
        "drive drive.file drive.readonly spreadsheets spreadsheets.readonly",
    ),
    "gsheets.spreadsheets_values_update": (
        "sheets.spreadsheets.values.update",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_values_append": (
        "sheets.spreadsheets.values.append",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_values_clear": (
        "sheets.spreadsheets.values.clear",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_values_batch_get": (
        "sheets.spreadsheets.values.batchGet",
        "drive drive.file drive.readonly spreadsheets spreadsheets.readonly",
    ),
    "gsheets.spreadsheets_values_batch_update": (
        "sheets.spreadsheets.values.batchUpdate",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_values_batch_clear": (
        "sheets.spreadsheets.values.batchClear",
        "drive drive.file spreadsheets",
    ),
    "gsheets.values_batch_get_by_data_filter": (
        "sheets.spreadsheets.values.batchGetByDataFilter",
        "drive drive.file spreadsheets",
    ),
    "gsheets.values_batch_update_by_data_filter": (
        "sheets.spreadsheets.values.batchUpdateByDataFilter",
        "drive drive.file spreadsheets",
    ),
    "gsheets.values_batch_clear_by_data_filter": (
        "sheets.spreadsheets.values.batchClearByDataFilter",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_create": ("sheets.spreadsheets.create", "drive drive.file spreadsheets"),
    "gsheets.spreadsheets_get": (
        "sheets.spreadsheets.get",
        "drive drive.file drive.readonly spreadsheets spreadsheets.readonly",
    ),
    "gsheets.spreadsheets_batch_update": (
        "sheets.spreadsheets.batchUpdate",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_sheets_copy_to": (
        "sheets.spreadsheets.sheets.copyTo",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_get_by_data_filter": (
        "sheets.spreadsheets.getByDataFilter",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_developer_metadata_get": (
        "sheets.spreadsheets.developerMetadata.get",
        "drive drive.file spreadsheets",
    ),
    "gsheets.spreadsheets_developer_metadata_search": (
        "sheets.spreadsheets.developerMetadata.search",
        "drive drive.file spreadsheets",
    ),
    "gforms.forms_create": ("forms.forms.create", "drive drive.file forms.body"),
    "gforms.forms_get": (
        "forms.forms.get",
        "drive drive.file drive.readonly forms.body forms.body.readonly",
    ),
    "gforms.forms_batch_update": ("forms.forms.batchUpdate", "drive drive.file forms.body"),
    "gforms.forms_set_publish_settings": (
        "forms.forms.setPublishSettings",
        "drive drive.file forms.body",
    ),
    "gforms.forms_responses_get": (
        "forms.forms.responses.get",
        "drive drive.file forms.responses.readonly",
    ),
    "gforms.forms_responses_list": (
        "forms.forms.responses.list",
        "drive drive.file forms.responses.readonly",
    ),
}


# Google's restricted category, from the Gmail and Drive scope pages
# (developers.google.com/workspace/gmail/api/auth/scopes and
# developers.google.com/workspace/drive/api/guides/api-specific-auth). Every
# Calendar, Sheets, Docs and Forms scope a tool here declares is sensitive or
# non-sensitive.
RESTRICTED = {
    "https://mail.google.com/",
    *(
        _AUTH + s
        for s in (
            "gmail.readonly",
            "gmail.compose",
            "gmail.modify",
            "gmail.metadata",
            "drive",
            "drive.readonly",
            "drive.metadata",
            "drive.metadata.readonly",
        )
    ),
}


def _short(scope: str) -> str:
    return scope.removeprefix(_AUTH).removeprefix("https://").rstrip("/")


def _options(tool):
    return [o for r in tool.scopes for o in (r.options if isinstance(r, AnyOf) else (r,))]


def _tools():
    return [
        (f"{pack.__name__.rsplit('.', 1)[1]}.{t.name}", t) for pack in PACKS for t in pack.TOOLS
    ]


def test_every_google_tool_is_in_the_table():
    assert sorted(name for name, _ in _tools()) == sorted(ACCEPTED)


@pytest.mark.parametrize(("name", "tool"), _tools(), ids=lambda v: v if isinstance(v, str) else "")
def test_each_tool_offers_only_scopes_google_accepts_for_its_method(name, tool):
    method, accepted = ACCEPTED[name]
    assert len(tool.scopes) == 1, f"{name}: one requirement per Google method"
    offered = [_short(o) for o in _options(tool)]
    unaccepted = [o for o in offered if o not in accepted.split()]
    assert not unaccepted, f"{name}: Google does not list {unaccepted} for {method}"


@pytest.mark.parametrize(("name", "tool"), _tools(), ids=lambda v: v if isinstance(v, str) else "")
def test_each_tools_options_run_narrowest_first(name, tool):
    options = _options(tool)
    assert options == sorted(options, key=GOOGLE_SCOPE_ORDER.index), name


def test_a_restricted_scope_is_first_only_where_google_offers_nothing_else():
    """Where Google accepts a scope outside the restricted set, it comes first.

    Google also opens some readers to ``drive.file``, which reaches only files
    the app created: offered there, ``files_get`` could not read a file the
    user made, so those are not counted as alternatives.
    """
    reaches_part = {
        "drive.file",
        "drive.appdata",
        "drive.meet.readonly",
        "drive.photos.readonly",
        "drive.scripts",
    }
    for name, tool in _tools():
        first = _options(tool)[0]
        if first not in RESTRICTED:
            continue
        _, accepted = ACCEPTED[name]
        open_ = {
            s
            for s in accepted.split()
            if _AUTH + s not in RESTRICTED and s != "mail.google.com" and s not in reaches_part
        }
        assert not open_, f"{name} offers {_short(first)} first but Google also accepts {open_}"


@pytest.mark.parametrize(
    "tools",
    [
        [gmail.messages_send],
        [*(t for t in gmail.TOOLS if t.name.startswith("labels_"))],
        [gdrive.files_create, gdrive.about_get],
        [gdocs.documents_create],
        [gsheets.spreadsheets_create],
        [gforms.forms_create],
        [*gcalendar.TOOLS, gmail.messages_send, gdocs.documents_get],
    ],
    ids=[
        "send",
        "labels",
        "drive-create",
        "docs-create",
        "sheets-create",
        "forms-create",
        "calendar-send-read-docs",
    ],
)
def test_these_agents_ask_for_nothing_restricted(tools):
    assert not set(scopes_for(tools)) & RESTRICTED, scopes_for(tools)


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        ([gmail.messages_send], ["gmail.send"]),
        (
            [gmail.messages_list, gmail.messages_get, gmail.threads_list, gmail.threads_get],
            ["gmail.readonly"],
        ),
        (
            [gmail.threads_list, gmail.threads_get, gmail.threads_modify, gmail.labels_list],
            ["gmail.modify"],
        ),
        ([gmail.drafts_create, gmail.drafts_get, gmail.drafts_list], ["gmail.compose"]),
        ([gmail.drafts_create, gmail.threads_get], ["gmail.compose", "gmail.readonly"]),
        ([gmail.labels_list, gmail.labels_create], ["gmail.labels"]),
        ([t for t in gmail.TOOLS if t is not gmail.threads_delete], ["gmail.modify"]),
        (gmail.TOOLS, ["mail.google.com"]),
        ([gdrive.files_list, gdrive.files_get, gdrive.files_export], ["drive.readonly"]),
        ([gdrive.files_list, gdocs.documents_get], ["drive.readonly"]),
        ([gdocs.documents_get, gdocs.documents_batch_update], ["documents"]),
        ([gdocs.documents_create, gdocs.documents_batch_update], ["documents"]),
        ([gcalendar.events_list, gcalendar.events_get], ["calendar.events.readonly"]),
        ([gcalendar.events_list, gcalendar.events_insert], ["calendar.events"]),
    ],
    ids=[
        "send",
        "read",
        "read-and-relabel",
        "draft",
        "draft-replies",
        "labels",
        "all-but-delete",
        "all",
        "drive-read",
        "drive-and-docs-read",
        "docs-read-edit",
        "docs-create-fill",
        "calendar-read",
        "calendar-read-write",
    ],
)
def test_scopes_for_asks_for_the_narrowest_set_that_covers_the_job(tools, expected):
    assert [_short(s) for s in scopes_for(tools)] == expected


def test_all_six_packs_together_order_their_scopes_one_way():
    scopes_for([t for pack in PACKS for t in pack.TOOLS])  # raises on a disagreement


def test_each_pack_scopes_constant_is_what_a_consent_for_the_pack_asks_for():
    for pack in PACKS:
        assert pack.SCOPES == scopes_for(pack.TOOLS), pack.__name__
