"""
Google Drive — files, sharing, comments, revisions, shared drives and quota.

    from charter import StaticTokenProvider
    from charter.packs import gdrive

    gdrive.configure(StaticTokenProvider(access_token))
    await gdrive.files_list.ainvoke(q="trashed = false")

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.

This pack sends metadata, not bytes. ``files.create`` makes a folder, a Google
Doc, or an empty blob; writing into a Doc or Sheet is the Docs and Sheets packs.
``files.export`` is the other direction: a Workspace document comes back as
text. ``files.delete`` is permanent — to trash, ``files.update`` with
``trashed=true``.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gdrive.response_handlers import (
    extract_about,
    extract_comment,
    extract_comments,
    extract_drive,
    extract_drives,
    extract_export,
    extract_file,
    extract_files,
    extract_permission,
    extract_permissions,
    extract_reply,
    extract_revision,
    extract_revisions,
)
from charter.packs.gdrive.types import (
    AboutGetRequest,
    CommentsCreateRequest,
    CommentsDeleteRequest,
    CommentsListRequest,
    CommentsUpdateRequest,
    DrivesGetRequest,
    DrivesListRequest,
    FilesCopyRequest,
    FilesCreateRequest,
    FilesDeleteRequest,
    FilesEmptyTrashRequest,
    FilesExportRequest,
    FilesGetRequest,
    FilesListRequest,
    FilesUpdateRequest,
    PermissionsCreateRequest,
    PermissionsDeleteRequest,
    PermissionsGetRequest,
    PermissionsListRequest,
    PermissionsUpdateRequest,
    RepliesCreateRequest,
    RepliesDeleteRequest,
    RepliesUpdateRequest,
    RevisionsGetRequest,
    RevisionsListRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://www.googleapis.com/"
# Google list endpoints page with an opaque nextPageToken.
GOOGLE_PAGINATION = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")

QUOTA_DOC_URL = "https://developers.google.com/workspace/drive/api/guides/limits"
SCOPES = ["https://www.googleapis.com/auth/drive"]

_credentials = DeferredCredentialProvider("gdrive", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_drive = oauth_tool_factory(
    pack="gdrive",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google's query parameters are camelCase (`pageSize`, `supportsAllDrives`),
    # like its bodies. Without this the default snake casing sends `page_size`,
    # which Google silently ignores — the worst kind of wrong, because the call
    # succeeds and returns unfiltered results.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
)


files_list = _drive(
    name="files_list",
    args_schema=FilesListRequest,
    method="GET",
    url_template="drive/v3/files",
    description=(
        "List the user's files. Returns all files by default, including trashed "
        "files; add `trashed = false` to `q` to hide them. `q` is Drive's search "
        "grammar — `name contains 'Q3' and mimeType = 'application/vnd.google-apps.folder'`."
    ),
    action_label="Lists Drive files.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_files,
)

files_get = _drive(
    name="files_get",
    args_schema=FilesGetRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}",
    description=(
        "Get a file's metadata by ID. Pass `alt=media` for the binary contents of "
        "a file stored in Drive; for Google Docs, Sheets and Slides use "
        "files_export instead."
    ),
    action_label="Reads a Drive file.",
    quota_cost=1,
    response_handler=extract_file,
)

files_export = _drive(
    name="files_export",
    args_schema=FilesExportRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/export",
    description=(
        "Export a Google Workspace document to the requested MIME type and return "
        "the exported content. Limited to 10 MB. Common MIME types: text/plain, "
        "text/html, text/csv, application/pdf."
    ),
    action_label="Exports a Workspace document.",
    quota_cost=1,
    response_handler=extract_export,
)

files_create = _drive(
    name="files_create",
    args_schema=FilesCreateRequest,
    method="POST",
    url_template="drive/v3/files",
    description=(
        "Create a file's metadata: a folder (`mimeType` "
        "`application/vnd.google-apps.folder`), a Google Doc / Sheet / Slide, or "
        "an empty blob. Media upload is not expressed here. `parents` takes at "
        "most one folder ID."
    ),
    action_label="Creates a Drive file or folder.",
    quota_cost=1,
    response_handler=extract_file,
)

files_update = _drive(
    name="files_update",
    args_schema=FilesUpdateRequest,
    method="PATCH",
    url_template="drive/v3/files/{file_id}",
    description=(
        "Change part of a file's metadata. Send only the fields being changed; "
        "the rest keep their stored values. To trash a file, set `trashed` to "
        "true. To move a file, use `addParents` and `removeParents` rather than "
        "`parents`."
    ),
    action_label="Updates a Drive file.",
    quota_cost=1,
    response_handler=extract_file,
)

files_copy = _drive(
    name="files_copy",
    args_schema=FilesCopyRequest,
    method="POST",
    url_template="drive/v3/files/{file_id}/copy",
    description=(
        "Create a copy of a file and apply any requested updates with patch "
        "semantics. Typically send a new `name` and optionally `parents`."
    ),
    action_label="Copies a Drive file.",
    quota_cost=1,
    response_handler=extract_file,
)

files_delete = _drive(
    name="files_delete",
    args_schema=FilesDeleteRequest,
    method="DELETE",
    url_template="drive/v3/files/{file_id}",
    description=(
        "Permanently delete a file owned by the user without moving it to the "
        "trash. If the target is a folder, descendants owned by the user are also "
        "deleted. To move a file to the trash instead, use files_update with "
        "trashed=true."
    ),
    action_label="Permanently deletes a Drive file.",
    quota_cost=1,
)

files_empty_trash = _drive(
    name="files_empty_trash",
    args_schema=FilesEmptyTrashRequest,
    method="DELETE",
    url_template="drive/v3/files/trash",
    description=(
        "Permanently delete all of the user's trashed files. Pass `driveId` to "
        "empty a shared drive's trash instead."
    ),
    action_label="Empties Drive trash.",
    quota_cost=1,
)

permissions_create = _drive(
    name="permissions_create",
    args_schema=PermissionsCreateRequest,
    method="POST",
    url_template="drive/v3/files/{file_id}/permissions",
    description=(
        "Create a permission for a file or shared drive. `type` is `user`, "
        "`group`, `domain` or `anyone`; `role` is `owner`, `organizer`, "
        "`fileOrganizer`, `writer`, `commenter` or `reader`. For `user` or "
        "`group`, send `emailAddress`. Concurrent permission writes on the same "
        "file are not supported."
    ),
    action_label="Shares a Drive file.",
    quota_cost=1,
    response_handler=extract_permission,
)

permissions_list = _drive(
    name="permissions_list",
    args_schema=PermissionsListRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/permissions",
    description="List a file's or shared drive's permissions.",
    action_label="Lists who can access a file.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_permissions,
)

permissions_get = _drive(
    name="permissions_get",
    args_schema=PermissionsGetRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/permissions/{permission_id}",
    description="Get a permission by ID.",
    action_label="Reads a sharing permission.",
    quota_cost=1,
    response_handler=extract_permission,
)

permissions_update = _drive(
    name="permissions_update",
    args_schema=PermissionsUpdateRequest,
    method="PATCH",
    url_template="drive/v3/files/{file_id}/permissions/{permission_id}",
    description=(
        "Update a permission with patch semantics. Send only the fields being "
        "changed. Concurrent permission writes on the same file are not supported."
    ),
    action_label="Updates a sharing permission.",
    quota_cost=1,
    response_handler=extract_permission,
)

permissions_delete = _drive(
    name="permissions_delete",
    args_schema=PermissionsDeleteRequest,
    method="DELETE",
    url_template="drive/v3/files/{file_id}/permissions/{permission_id}",
    description=(
        "Delete a permission. Concurrent permission writes on the same file are "
        "not supported."
    ),
    action_label="Removes a sharing permission.",
    quota_cost=1,
)

comments_list = _drive(
    name="comments_list",
    args_schema=CommentsListRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/comments",
    description=(
        "List a file's comments. The `fields` parameter is required — for example "
        "`comments(id,content,author,createdTime,resolved)`."
    ),
    action_label="Lists comments on a file.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_comments,
)

comments_create = _drive(
    name="comments_create",
    args_schema=CommentsCreateRequest,
    method="POST",
    url_template="drive/v3/files/{file_id}/comments",
    description=(
        "Create a comment on a file. The `fields` parameter is required. Set "
        "`content` to the plain text of the comment."
    ),
    action_label="Adds a comment on a file.",
    quota_cost=1,
    response_handler=extract_comment,
)

comments_update = _drive(
    name="comments_update",
    args_schema=CommentsUpdateRequest,
    method="PATCH",
    url_template="drive/v3/files/{file_id}/comments/{comment_id}",
    description=(
        "Update a comment with patch semantics. The `fields` parameter is "
        "required. Typically send a new `content`."
    ),
    action_label="Updates a comment.",
    quota_cost=1,
    response_handler=extract_comment,
)

comments_delete = _drive(
    name="comments_delete",
    args_schema=CommentsDeleteRequest,
    method="DELETE",
    url_template="drive/v3/files/{file_id}/comments/{comment_id}",
    description="Delete a comment.",
    action_label="Deletes a comment.",
    quota_cost=1,
)

replies_create = _drive(
    name="replies_create",
    args_schema=RepliesCreateRequest,
    method="POST",
    url_template="drive/v3/files/{file_id}/comments/{comment_id}/replies",
    description=(
        "Create a reply to a comment. Send `content`, or an `action` of `resolve` "
        "or `reopen`. `content` is required if no `action` is specified."
    ),
    action_label="Replies to a comment.",
    quota_cost=1,
    response_handler=extract_reply,
)

replies_update = _drive(
    name="replies_update",
    args_schema=RepliesUpdateRequest,
    method="PATCH",
    url_template="drive/v3/files/{file_id}/comments/{comment_id}/replies/{reply_id}",
    description="Update a reply with patch semantics. Typically send a new `content`.",
    action_label="Updates a comment reply.",
    quota_cost=1,
    response_handler=extract_reply,
)

replies_delete = _drive(
    name="replies_delete",
    args_schema=RepliesDeleteRequest,
    method="DELETE",
    url_template="drive/v3/files/{file_id}/comments/{comment_id}/replies/{reply_id}",
    description="Delete a reply.",
    action_label="Deletes a comment reply.",
    quota_cost=1,
)

revisions_list = _drive(
    name="revisions_list",
    args_schema=RevisionsListRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/revisions",
    description=(
        "List a file's revisions. The list might be incomplete for files with a "
        "large revision history, including frequently edited Google Docs, Sheets "
        "and Slides."
    ),
    action_label="Lists file revisions.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_revisions,
)

revisions_get = _drive(
    name="revisions_get",
    args_schema=RevisionsGetRequest,
    method="GET",
    url_template="drive/v3/files/{file_id}/revisions/{revision_id}",
    description="Get a revision's metadata by ID.",
    action_label="Reads a file revision.",
    quota_cost=1,
    response_handler=extract_revision,
)

drives_list = _drive(
    name="drives_list",
    args_schema=DrivesListRequest,
    method="GET",
    url_template="drive/v3/drives",
    description=(
        "List the user's shared drives. `q` is Drive's shared-drive search grammar."
    ),
    action_label="Lists shared drives.",
    quota_cost=1,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_drives,
)

drives_get = _drive(
    name="drives_get",
    args_schema=DrivesGetRequest,
    method="GET",
    url_template="drive/v3/drives/{drive_id}",
    description="Get a shared drive's metadata by ID.",
    action_label="Reads a shared drive.",
    quota_cost=1,
    response_handler=extract_drive,
)

about_get = _drive(
    name="about_get",
    args_schema=AboutGetRequest,
    method="GET",
    url_template="drive/v3/about",
    description=(
        "Get information about the user, the user's Drive, and system "
        "capabilities. The `fields` parameter is required — for example "
        "`user,storageQuota`."
    ),
    action_label="Reads Drive account info.",
    quota_cost=1,
    response_handler=extract_about,
)

TOOLS: list[Tool] = [
    files_list,
    files_get,
    files_export,
    files_create,
    files_update,
    files_copy,
    files_delete,
    files_empty_trash,
    permissions_create,
    permissions_list,
    permissions_get,
    permissions_update,
    permissions_delete,
    comments_list,
    comments_create,
    comments_update,
    comments_delete,
    replies_create,
    replies_update,
    replies_delete,
    revisions_list,
    revisions_get,
    drives_list,
    drives_get,
    about_get,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "GOOGLE_PAGINATION",
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
]
