"""Google Drive pack — wire behaviour and response trimming."""

from __future__ import annotations

import json
from typing import get_args

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.packs import gdrive
from charter.packs.gdrive.types.files.actions import Corpora
from charter.packs.gdrive.types.permissions.models import PermissionRole, PermissionType

API = "https://www.googleapis.com/"
FILES = f"{API}drive/v3/files"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gdrive.configure(StaticTokenProvider("ya29.test"))


def file(**overrides):
    base = {
        "kind": "drive#file",
        "id": "1abc",
        "name": "Q3 plan",
        "mimeType": "application/vnd.google-apps.document",
        "parents": ["root"],
        "createdTime": "2026-09-01T12:00:00.000Z",
        "modifiedTime": "2026-09-07T12:00:00.000Z",
        "webViewLink": "https://docs.google.com/document/d/1abc/edit",
        "iconLink": "https://drive-thirdparty.googleusercontent.com/16/type/icon",
        "thumbnailLink": "https://lh3.googleusercontent.com/thumb",
        "owners": [{"displayName": "Ada", "emailAddress": "ada@example.com", "me": True}],
        "capabilities": {
            "canEdit": True,
            "canComment": True,
            "canShare": True,
            "canDownload": True,
            "canCopy": True,
            "canRename": True,
            "canDelete": False,
        },
        "exportLinks": {
            "text/plain": "https://docs.google.com/feeds/download/documents/export?id=1abc",
            "application/pdf": "https://docs.google.com/feeds/download/documents/export?id=1abc&exportFormat=pdf",
        },
        "md5Checksum": "d" * 32,
        "quotaBytesUsed": "4096",
        "version": "12",
        "spaces": ["drive"],
    }
    base.update(overrides)
    return base


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_every_documented_endpoint():
    assert {t.name for t in gdrive.TOOLS} == {
        "files_list",
        "files_get",
        "files_export",
        "files_create",
        "files_update",
        "files_copy",
        "files_delete",
        "files_empty_trash",
        "permissions_create",
        "permissions_list",
        "permissions_get",
        "permissions_update",
        "permissions_delete",
        "comments_list",
        "comments_create",
        "comments_update",
        "comments_delete",
        "replies_create",
        "replies_update",
        "replies_delete",
        "revisions_list",
        "revisions_get",
        "drives_list",
        "drives_get",
        "about_get",
    }
    assert all(isinstance(t, Tool) for t in gdrive.TOOLS)


def test_every_tool_with_something_to_trim_has_a_handler():
    trimming = {t.name for t in gdrive.TOOLS if t._executor._response_handler}
    assert trimming == {t.name for t in gdrive.TOOLS} - {
        "files_delete",
        "files_empty_trash",
        "permissions_delete",
        "comments_delete",
        "replies_delete",
    }


def test_google_query_parameters_are_camel_cased():
    for tool in gdrive.TOOLS:
        assert tool.query_case == "camel", tool.name


def test_closed_literals_hold_the_documented_enums():
    assert set(get_args(Corpora)) == {"user", "domain", "drive", "allDrives"}
    assert set(get_args(PermissionType)) == {"user", "group", "domain", "anyone"}
    assert set(get_args(PermissionRole)) == {
        "owner",
        "organizer",
        "fileOrganizer",
        "writer",
        "commenter",
        "reader",
        "publishedReader",
    }


def test_response_only_file_fields_are_absent_from_the_llm_schema():
    body = gdrive.files_create.llm_schema().model_fields["file"].annotation
    offered = set(body.model_fields)
    for hidden in (
        "kind",
        "capabilities",
        "export_links",
        "owners",
        "md5_checksum",
        "web_view_link",
        "permissions",
        "size",
        "version",
    ):
        assert hidden not in offered, hidden
    for visible in ("name", "mime_type", "parents", "starred", "trashed", "description"):
        assert visible in offered, visible


def test_deprecated_query_parameters_are_hidden_from_the_model():
    offered = set(gdrive.files_list.to_json_schema()["parameters"].get("properties") or {})
    for hidden in ("supportsTeamDrives", "includeTeamDriveItems", "corpus", "teamDriveId"):
        assert hidden not in offered, hidden
    assert "supports_team_drives" in gdrive.files_list.args_schema.model_fields


def test_a_patch_permission_mandates_nothing():
    body = gdrive.permissions_update.llm_schema().model_fields["permission"].annotation
    required = [n for n, f in body.model_fields.items() if f.is_required()]
    assert required == []
    create = gdrive.permissions_create.llm_schema().model_fields["permission"].annotation
    assert create.model_fields["type"].is_required()
    assert create.model_fields["role"].is_required()


def test_a_patch_comment_mandates_nothing():
    body = gdrive.comments_update.llm_schema().model_fields["comment"].annotation
    required = [n for n, f in body.model_fields.items() if f.is_required()]
    assert required == []
    create = gdrive.comments_create.llm_schema().model_fields["comment"].annotation
    assert create.model_fields["content"].is_required()


# -----------------------------------------------------
# Wire
# -----------------------------------------------------


@respx.mock
async def test_list_sends_its_filters_as_the_query_names_google_documents():
    route = respx.get(FILES).mock(return_value=httpx.Response(200, json={"files": []}))

    await gdrive.files_list.ainvoke(
        q="trashed = false",
        page_size=10,
        order_by="modifiedTime desc",
        supports_all_drives=True,
        corpora="user",
    )

    params = dict(route.calls.last.request.url.params)
    assert params == {
        "q": "trashed = false",
        "pageSize": "10",
        "orderBy": "modifiedTime desc",
        "supportsAllDrives": "true",
        "corpora": "user",
    }
    assert "page_size" not in params
    assert route.calls.last.request.headers["authorization"] == "Bearer ya29.test"


@respx.mock
async def test_the_no_argument_list_sends_no_query_defaults():
    """Documented defaults are what the server applies when the field is absent."""
    route = respx.get(FILES).mock(return_value=httpx.Response(200, json={"files": []}))

    await gdrive.files_list.ainvoke({})

    assert dict(route.calls.last.request.url.params) == {}


@respx.mock
async def test_create_unwraps_the_file_body_and_camel_cases_it():
    route = respx.post(FILES).mock(return_value=httpx.Response(200, json=file()))

    await gdrive.files_create.ainvoke(
        file={
            "name": "Notes",
            "mime_type": "application/vnd.google-apps.folder",
            "parents": ["1parent"],
        }
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "name": "Notes",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["1parent"],
    }


@respx.mock
async def test_update_sends_add_parents_as_a_query_parameter():
    route = respx.patch(f"{FILES}/1abc").mock(return_value=httpx.Response(200, json=file()))

    await gdrive.files_update.ainvoke(
        file_id="1abc",
        file={"name": "Renamed"},
        add_parents="1new",
        remove_parents="1old",
    )

    params = dict(route.calls.last.request.url.params)
    assert params["addParents"] == "1new"
    assert params["removeParents"] == "1old"
    assert json.loads(route.calls.last.request.content) == {"name": "Renamed"}


@respx.mock
async def test_export_sends_mime_type_as_the_documented_query_name():
    route = respx.get(f"{FILES}/1abc/export").mock(
        return_value=httpx.Response(200, text="exported", headers={"content-type": "text/plain"})
    )

    result = await gdrive.files_export.ainvoke(file_id="1abc", mime_type="text/plain")

    assert dict(route.calls.last.request.url.params) == {"mimeType": "text/plain"}
    assert result == {"content": "exported"}


@respx.mock
async def test_empty_trash_hits_files_trash():
    route = respx.delete(f"{FILES}/trash").mock(return_value=httpx.Response(204))

    result = await gdrive.files_empty_trash.ainvoke({})

    assert result == {}
    assert route.called


@respx.mock
async def test_permissions_create_requires_email_for_a_user():
    with pytest.raises(ToolValidationError, match="emailAddress"):
        await gdrive.permissions_create.ainvoke(
            file_id="1abc",
            permission={"type": "user", "role": "reader"},
        )


@respx.mock
async def test_permissions_create_sends_the_permission_as_the_json_body():
    route = respx.post(f"{FILES}/1abc/permissions").mock(
        return_value=httpx.Response(
            200,
            json={"id": "p1", "type": "user", "role": "reader", "emailAddress": "ada@example.com"},
        )
    )

    result = await gdrive.permissions_create.ainvoke(
        file_id="1abc",
        permission={"type": "user", "role": "reader", "email_address": "ada@example.com"},
        send_notification_email=False,
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"type": "user", "role": "reader", "emailAddress": "ada@example.com"}
    assert dict(route.calls.last.request.url.params)["sendNotificationEmail"] == "false"
    assert result["emailAddress"] == "ada@example.com"


@respx.mock
async def test_about_get_requires_fields():
    with pytest.raises(ToolValidationError, match="fields"):
        await gdrive.about_get.ainvoke({})


@respx.mock
async def test_about_get_sends_fields_as_a_query_parameter():
    route = respx.get(f"{API}drive/v3/about").mock(
        return_value=httpx.Response(
            200,
            json={
                "user": {"displayName": "Ada", "emailAddress": "ada@example.com", "me": True},
                "storageQuota": {"limit": "15000000000", "usage": "1000", "usageInDrive": "800"},
                "driveThemes": [{"id": "t1", "colorRgb": "#000000"}] * 20,
            },
        )
    )

    result = await gdrive.about_get.ainvoke(fields="user,storageQuota")

    assert dict(route.calls.last.request.url.params) == {"fields": "user,storageQuota"}
    assert result["user"]["emailAddress"] == "ada@example.com"
    assert "driveThemes" not in result


def test_drive_id_without_corpora_drive_is_refused():
    with pytest.raises(ValidationError, match="corpora must be 'drive'"):
        gdrive.files_list.llm_schema()(driveId="0ANdrive", corpora="user")


def test_replies_create_requires_content_or_action():
    with pytest.raises(ValidationError, match="content is required"):
        gdrive.replies_create.llm_schema()(fileId="1abc", commentId="c1", reply={})


# -----------------------------------------------------
# Trimming
# -----------------------------------------------------


@respx.mock
async def test_list_trimming_keeps_what_an_agent_acts_on():
    payload = {
        "kind": "drive#fileList",
        "incompleteSearch": False,
        "files": [file()],
        "nextPageToken": "CAc",
    }
    respx.get(FILES).mock(return_value=httpx.Response(200, json=payload))

    result = await gdrive.files_list.ainvoke({})
    item = result["files"][0]

    assert item["id"] == "1abc"
    assert item["name"] == "Q3 plan"
    assert item["mimeType"] == "application/vnd.google-apps.document"
    assert item["parents"] == ["root"]
    assert item["webViewLink"].startswith("https://docs.google.com/")
    assert result["nextPageToken"] == "CAc"

    blob = json.dumps(result)
    for dropped in ("capabilities", "exportLinks", "md5Checksum", "iconLink", "quotaBytesUsed"):
        assert dropped not in blob, dropped


@respx.mock
async def test_trimming_is_a_large_reduction():
    payload = {"files": [file(id=f"f{i}", name=f"File {i}") for i in range(40)]}
    respx.get(FILES).mock(return_value=httpx.Response(200, json=payload))

    result = await gdrive.files_list.ainvoke({})
    before, after = len(json.dumps(payload)), len(json.dumps(result))
    assert len(result["files"]) == 40
    assert after < before * 0.5, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_export_truncates_a_payload_too_big_to_inline():
    huge = "x" * 40_000
    respx.get(f"{FILES}/1abc/export").mock(
        return_value=httpx.Response(200, text=huge, headers={"content-type": "text/plain"})
    )

    result = await gdrive.files_export.ainvoke(file_id="1abc", mime_type="text/plain")

    assert result["truncated"] is True
    assert result["length"] == 40_000
    assert len(result["content"]) == 32_768


@respx.mock
async def test_paging_survives_trimming():
    respx.get(FILES).mock(
        return_value=httpx.Response(
            200, json={"files": [file()], "nextPageToken": "page-2", "incompleteSearch": True}
        )
    )

    result = await gdrive.files_list.ainvoke({})
    assert result["nextPageToken"] == "page-2"
    assert result["incompleteSearch"] is True
