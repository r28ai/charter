# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Notion — thirty-five tools over the Notion REST API.

    from charter import StaticTokenProvider
    from charter.packs import notion

    notion.configure(StaticTokenProvider(token))   # ntn_... integration secret
    await notion.pages_create.ainvoke(
        body={
            "parent": {"data_source_id": DATA_SOURCE_ID},
            "properties": {"Name": {"title": [{"text": {"content": "Ship it"}}]}},
        },
    )

``configure()`` is optional if ``$NOTION_API_KEY`` is set.

Four things about Notion that this pack absorbs:

**A database is no longer the table.** Since the ``2025-09-03`` version a
database is a *container* and a **data source** is the table inside it: the
columns live on the data source, the rows are queried from it, and a page's
parent is a ``data_source_id``. The old spelling still works against a database
with one table and breaks against one with several, so this pack is written the
new way throughout. Reading a database is how you find the data source to query
— ``databases_retrieve`` keeps the ``data_sources`` list for exactly that.

**It dates its versions, and the header is not optional.** ``Notion-Version`` is
required on every request; omit it and the answer is ``400 missing_version``.
It is pinned to :data:`API_VERSION` in :data:`NOTION_HEADERS` and sent verbatim,
so this pack's behaviour is a property of this file rather than of the day it
runs. That pin is load-bearing here in a way it is not everywhere: the version
below is the one that renamed ``archived`` to ``in_trash`` and replaced the
``after`` parameter on block append with ``position``.

**Everything is rich text, and that is most of the payload.** Notion has no
plain strings: a title, a heading, a table cell and a comment are all arrays of
runs, each carrying its annotations, a ``plain_text`` copy, an ``href`` and a
type tag. A one-line title is ~200 bytes of JSON for ~20 characters. Every read
tool has a response handler that collapses a run array to the string it spells
and a property to its value, and they project rather than filter — dropping a
row would corrupt the page length a walk depends on.

**Failure is always a status code.** There is no ``{"ok": false}`` here and no
errors array, so there is no :class:`~charter.types.envelope.Envelope` on the
factory — the runtime's own 4xx handling is the whole story.

Known limits, named rather than hidden:

* **Sending file bytes is not a tool.** A file becomes Notion-hosted content in
  three steps, and the middle one — ``POST /v1/file_uploads/{id}/send`` — takes
  ``multipart/form-data`` with raw bytes, which Charter's wire contract does not
  encode and which a model filling in arguments could not supply anyway. The
  other four upload endpoints are here, and ``mode="external_url"`` works end to
  end from this pack: Notion fetches the file itself and there is no send step.
* **Coverage is the content API.** Users, pages, blocks, databases, data
  sources, search, comments, file uploads, custom emojis and async tasks — the
  surface an agent reading and writing a workspace needs. Notion's agent and
  session platform (``/v1/agents``, ``/v1/sessions``), the Views API
  (``/v1/views``) and meeting notes (``/v1/blocks/meeting_notes``) are not
  modelled. Neither are the OAuth token endpoints, which belong to an
  authorization server rather than to a tool — see :mod:`charter.oauth`.
* **Two levels of nesting per write.** Notion accepts at most 100 blocks and two
  levels of children in one call. The schema carries the 100; the depth is a
  server rule, and the way past it is to append to the blocks that come back.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.notion.response_handlers import (
    trim_block,
    trim_blocks,
    trim_comments,
    trim_data_source,
    trim_database,
    trim_page,
    trim_pages,
    trim_users,
)
from charter.packs.notion.types import (
    AsyncTasksRetrieveRequest,
    BlocksChildrenAppendRequest,
    BlocksChildrenListRequest,
    BlocksDeleteRequest,
    BlocksRetrieveRequest,
    BlocksUpdateRequest,
    CommentsCreateRequest,
    CommentsDeleteRequest,
    CommentsListRequest,
    CommentsRetrieveRequest,
    CommentsUpdateRequest,
    CustomEmojisListRequest,
    DatabasesCreateRequest,
    DatabasesRetrieveRequest,
    DatabasesUpdateRequest,
    DataSourcesCreateRequest,
    DataSourcesQueryRequest,
    DataSourcesRetrieveRequest,
    DataSourcesTemplatesListRequest,
    DataSourcesUpdateRequest,
    FileUploadsCompleteRequest,
    FileUploadsCreateRequest,
    FileUploadsListRequest,
    FileUploadsRetrieveRequest,
    PagesCreateRequest,
    PagesMoveRequest,
    PagesRetrieveMarkdownRequest,
    PagesRetrievePropertyItemRequest,
    PagesRetrieveRequest,
    PagesUpdateMarkdownRequest,
    PagesUpdateRequest,
    SearchRequest,
    UsersListRequest,
    UsersRetrieveMeRequest,
    UsersRetrieveRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://api.notion.com/"
QUOTA_DOC_URL = "https://developers.notion.com/reference/request-limits"

# The API version this pack is written against. Notion dates its versions and
# requires the header on every request — there is no "unpinned" to fall back to,
# and this is the version that renamed `archived` to `in_trash` and replaced
# block append's `after` parameter with `position`.
# https://developers.notion.com/reference/versioning
API_VERSION = "2026-03-11"

# Sent verbatim on every request, beside the bearer token. The version is not
# the model's business, so it is declared once here rather than as a field it
# could change.
NOTION_HEADERS = {"Notion-Version": API_VERSION}

# Notion's permissions are *capabilities*, granted to an integration in Notion's
# own settings, and they are never sent on a request — there is no scope
# parameter to put them in. So these are spelled the way Notion's console spells
# them, which is what a reader has to go and tick, rather than as invented
# identifiers that would look like wire values and match nothing.
#
# Declared per tool rather than on the factory. A consent screen built from the
# factory's list would tell someone reading a page that the call needs to insert
# comments, which is how a permission prompt teaches people to stop reading it.
READ = ["Read content"]
INSERT = ["Insert content"]
UPDATE = ["Update content"]
READ_COMMENTS = ["Read comments"]
INSERT_COMMENTS = ["Insert comments"]
READ_USERS = ["Read user information"]

# Everything the pack collectively needs, under the name every pack uses for
# this metadata. Charter never sends it; it exists for consent screens and
# approval UIs, which is the role Notion's capabilities play.
SCOPES = READ + UPDATE + INSERT + READ_COMMENTS + INSERT_COMMENTS + READ_USERS

# One cursor convention across the whole API: `start_cursor` out, `next_cursor`
# back, and `has_more` saying whether to keep going. `has_more` is declared
# because it is authoritative — Notion is explicit that `next_cursor` is only
# meaningful when `has_more` is true.
# https://developers.notion.com/reference/intro#pagination
NOTION_PAGINATION = Pagination(
    cursor_field="next_cursor",
    cursor_param="start_cursor",
    more_field="has_more",
)

# Search and the data source query take their filters in a body, so their paging
# markers go in the body too — the cursor path reaches into the body argument
# rather than sitting beside it.
NOTION_BODY_PAGINATION = Pagination(
    cursor_field="next_cursor",
    cursor_param="body.start_cursor",
    more_field="has_more",
)

_credentials = DeferredCredentialProvider("notion", env_var="NOTION_API_KEY")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_notion = oauth_tool_factory(
    pack="notion",
    base_url=BASE_URL,
    provider="notion",
    credential_provider=_credentials,
    # Notion is snake_case on the wire, in bodies and query parameters alike.
    # It matters more here than in most packs: a page's `properties` map is
    # keyed by the column names someone typed in Notion, and any conversion at
    # all would rewrite them.
    body_case="snake",
    query_case="snake",
    path_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=NOTION_HEADERS,
)

# ---------- users ----------

users_list = _notion(
    name="users_list",
    scopes_override=READ_USERS,
    args_schema=UsersListRequest,
    method="GET",
    url_template="v1/users",
    description=(
        "List the people and bots in the workspace. Guests are excluded, and there "
        "is no way to filter by name or email — page through and match locally. A "
        "personal access token cannot call this."
    ),
    action_label="Lists Notion users.",
    response_handler=trim_users,
    pagination_override=NOTION_PAGINATION,
)

users_retrieve = _notion(
    name="users_retrieve",
    scopes_override=READ_USERS,
    args_schema=UsersRetrieveRequest,
    method="GET",
    url_template="v1/users/{user_id}",
    description="Get one user by ID.",
    action_label="Reads a Notion user.",
    response_handler=trim_users,
)

users_retrieve_me = _notion(
    name="users_retrieve_me",
    scopes_override=READ_USERS,
    args_schema=UsersRetrieveMeRequest,
    method="GET",
    url_template="v1/users/me",
    description=(
        "Get the bot this token authenticates as, including which workspace it is "
        "in. The cheapest way to check a credential works."
    ),
    action_label="Checks the Notion connection.",
    response_handler=trim_users,
)

# ---------- search ----------

search = _notion(
    name="search",
    scopes_override=READ,
    args_schema=SearchRequest,
    method="POST",
    url_template="v1/search",
    description=(
        "Search the titles of pages and data sources shared with this integration. "
        "Titles only — it does not search page content — and it returns nothing "
        "that has not been shared. With no query it lists everything visible, "
        "which is how you find the IDs to start from."
    ),
    action_label="Searches Notion.",
    response_handler=trim_pages,
    pagination_override=NOTION_BODY_PAGINATION,
)

# ---------- pages ----------

pages_create = _notion(
    name="pages_create",
    scopes_override=INSERT,
    args_schema=PagesCreateRequest,
    method="POST",
    url_template="v1/pages",
    description=(
        "Create a page — as a subpage of another page, or as a row of a database "
        "by giving its `data_source_id` as the parent. Content comes as `children` "
        "blocks, as a `markdown` string Notion parses for you, or from a template: "
        "one of the three, never two."
    ),
    action_label="Creates a Notion page.",
    response_handler=trim_page,
)

pages_retrieve = _notion(
    name="pages_retrieve",
    scopes_override=READ,
    args_schema=PagesRetrieveRequest,
    method="GET",
    url_template="v1/pages/{page_id}",
    description=(
        "Get a page's properties. This does not return the page's content — the "
        "blocks are read with `blocks_children_list`, or all at once as Markdown "
        "with `pages_retrieve_markdown`. A property holding more than 25 entries "
        "comes back truncated; read it in full with `pages_retrieve_property_item`."
    ),
    action_label="Reads a Notion page.",
    response_handler=trim_page,
)

pages_update = _notion(
    name="pages_update",
    scopes_override=UPDATE,
    args_schema=PagesUpdateRequest,
    method="PATCH",
    url_template="v1/pages/{page_id}",
    description=(
        "Update a page's property values, icon, cover, or trash state. Properties "
        "not named are left alone, and a value set to null is cleared. This cannot "
        "move a page — use `pages_move`."
    ),
    action_label="Updates a Notion page.",
    response_handler=trim_page,
)

pages_move = _notion(
    name="pages_move",
    scopes_override=UPDATE,
    args_schema=PagesMoveRequest,
    method="POST",
    url_template="v1/pages/{page_id}/move",
    description="Move a page under a different parent page or data source.",
    action_label="Moves a Notion page.",
    response_handler=trim_page,
)

pages_retrieve_property_item = _notion(
    name="pages_retrieve_property_item",
    scopes_override=READ,
    args_schema=PagesRetrievePropertyItemRequest,
    method="GET",
    url_template="v1/pages/{page_id}/properties/{property_id}",
    description=(
        "Read one property of a page in full. Worth reaching for when a title, "
        "text, relation or people property holds more than the 25 entries a page "
        "object carries — those come back paginated here."
    ),
    action_label="Reads a Notion page property.",
    pagination_override=NOTION_PAGINATION,
)

pages_retrieve_markdown = _notion(
    name="pages_retrieve_markdown",
    scopes_override=READ,
    args_schema=PagesRetrieveMarkdownRequest,
    method="GET",
    url_template="v1/pages/{page_id}/markdown",
    description=(
        "Get a page's whole content as Markdown, rendered by Notion. One call "
        "instead of recursing through `blocks_children_list`, and the cheapest way "
        "to read a page you only need to understand rather than edit."
    ),
    action_label="Reads a Notion page as Markdown.",
)

pages_update_markdown = _notion(
    name="pages_update_markdown",
    scopes_override=UPDATE,
    args_schema=PagesUpdateMarkdownRequest,
    method="PATCH",
    url_template="v1/pages/{page_id}/markdown",
    description=(
        "Replace a page's content with Markdown, which Notion parses into blocks. "
        "This replaces the whole body, so read it first if you mean to edit rather "
        "than overwrite."
    ),
    action_label="Rewrites a Notion page.",
)

# ---------- blocks ----------

blocks_retrieve = _notion(
    name="blocks_retrieve",
    scopes_override=READ,
    args_schema=BlocksRetrieveRequest,
    method="GET",
    url_template="v1/blocks/{block_id}",
    description=(
        "Get one block. Its children are not included — `has_children` says "
        "whether there are any, and `blocks_children_list` reads them."
    ),
    action_label="Reads a Notion block.",
    response_handler=trim_block,
)

blocks_update = _notion(
    name="blocks_update",
    scopes_override=UPDATE,
    args_schema=BlocksUpdateRequest,
    method="PATCH",
    url_template="v1/blocks/{block_id}",
    description=(
        "Update a block's content, or trash and restore it with `in_trash`. Send "
        "the field matching the block's existing type: a type cannot be changed "
        "here, and neither can children — append or delete those instead. "
        "Whatever is sent replaces the whole value, so `rich_text` replaces the "
        "entire array rather than adding to it."
    ),
    action_label="Updates a Notion block.",
    response_handler=trim_block,
)

blocks_delete = _notion(
    name="blocks_delete",
    scopes_override=UPDATE,
    args_schema=BlocksDeleteRequest,
    method="DELETE",
    url_template="v1/blocks/{block_id}",
    description=(
        "Move a block to the trash. This is a soft delete: the block comes back "
        "with `in_trash` true and `blocks_update` can restore it."
    ),
    action_label="Deletes a Notion block.",
    response_handler=trim_block,
)

blocks_children_list = _notion(
    name="blocks_children_list",
    scopes_override=READ,
    args_schema=BlocksChildrenListRequest,
    method="GET",
    url_template="v1/blocks/{block_id}/children",
    description=(
        "List the direct children of a block, or of a page when given a page ID. "
        "One level only: a child reporting `has_children` is read with another "
        "call using its own ID."
    ),
    action_label="Reads Notion page content.",
    response_handler=trim_blocks,
    pagination_override=NOTION_PAGINATION,
)

blocks_children_append = _notion(
    name="blocks_children_append",
    scopes_override=INSERT,
    args_schema=BlocksChildrenAppendRequest,
    method="PATCH",
    url_template="v1/blocks/{block_id}/children",
    description=(
        "Append blocks to a page or a block. At most 100 per call and two levels "
        "of nesting; build deeper trees by appending to the blocks that come back. "
        "Append-only — it cannot move or reorder what is already there, though "
        "`position` chooses where the new blocks land."
    ),
    action_label="Adds content to Notion.",
    response_handler=trim_blocks,
)

# ---------- databases ----------

databases_create = _notion(
    name="databases_create",
    scopes_override=INSERT,
    args_schema=DatabasesCreateRequest,
    method="POST",
    url_template="v1/databases",
    description=(
        "Create a database on a page or at the top of the workspace. Give it an "
        "`initial_data_source` with the columns it starts with, or a "
        "`database_type` to take Notion's own schema for tasks, projects or skills."
    ),
    action_label="Creates a Notion database.",
    response_handler=trim_database,
)

databases_retrieve = _notion(
    name="databases_retrieve",
    scopes_override=READ,
    args_schema=DatabasesRetrieveRequest,
    method="GET",
    url_template="v1/databases/{database_id}",
    description=(
        "Get a database and the data sources it contains. The columns are not here "
        "— a database is a container. Follow a returned data source ID to "
        "`data_sources_retrieve` for the schema, or `data_sources_query` for rows."
    ),
    action_label="Reads a Notion database.",
    response_handler=trim_database,
)

databases_update = _notion(
    name="databases_update",
    scopes_override=UPDATE,
    args_schema=DatabasesUpdateRequest,
    method="PATCH",
    url_template="v1/databases/{database_id}",
    description=(
        "Update a database's title, description, icon, cover, inline display or "
        "trash state, or move it to a new parent. Columns belong to the data "
        "source — change those with `data_sources_update`."
    ),
    action_label="Updates a Notion database.",
    response_handler=trim_database,
)

# ---------- data sources ----------

data_sources_create = _notion(
    name="data_sources_create",
    scopes_override=INSERT,
    args_schema=DataSourcesCreateRequest,
    method="POST",
    url_template="v1/data_sources",
    description=(
        "Add another table to an existing database. Exactly one column must be the "
        "`title` type. To create a database and its first table together, use "
        "`databases_create` instead."
    ),
    action_label="Creates a Notion data source.",
    response_handler=trim_data_source,
)

data_sources_retrieve = _notion(
    name="data_sources_retrieve",
    scopes_override=READ,
    args_schema=DataSourcesRetrieveRequest,
    method="GET",
    url_template="v1/data_sources/{data_source_id}",
    description=(
        "Get a data source's column schema — the names, types and select options a "
        "write has to match. This returns the schema, not the rows; "
        "`data_sources_query` returns those."
    ),
    action_label="Reads a Notion data source schema.",
    response_handler=trim_data_source,
)

data_sources_update = _notion(
    name="data_sources_update",
    scopes_override=UPDATE,
    args_schema=DataSourcesUpdateRequest,
    method="PATCH",
    url_template="v1/data_sources/{data_source_id}",
    description=(
        "Change a data source's columns, title or icon. A key that is not already "
        'a column adds one, `{"name": ...}` renames one, and mapping a key to '
        "null removes it along with its data."
    ),
    action_label="Updates a Notion data source schema.",
    response_handler=trim_data_source,
)

data_sources_query = _notion(
    name="data_sources_query",
    scopes_override=READ,
    args_schema=DataSourcesQueryRequest,
    method="POST",
    url_template="v1/data_sources/{data_source_id}/query",
    description=(
        "Get the rows of a data source, optionally filtered and sorted. The filter "
        "grammar is one condition per column type, composed with `and` and `or` up "
        "to two levels deep. Read the schema first if you do not know the column "
        "names — a filter naming a column that is not there is a 400."
    ),
    action_label="Queries a Notion database.",
    response_handler=trim_pages,
    pagination_override=NOTION_BODY_PAGINATION,
)

data_sources_templates_list = _notion(
    name="data_sources_templates_list",
    scopes_override=READ,
    args_schema=DataSourcesTemplatesListRequest,
    method="GET",
    url_template="v1/data_sources/{data_source_id}/templates",
    description="List the page templates defined on a data source.",
    action_label="Lists Notion templates.",
    response_handler=trim_pages,
    pagination_override=NOTION_PAGINATION,
)

# ---------- comments ----------

comments_create = _notion(
    name="comments_create",
    scopes_override=INSERT_COMMENTS,
    args_schema=CommentsCreateRequest,
    method="POST",
    url_template="v1/comments",
    description=(
        "Comment on a page or block, or reply to an existing discussion with its "
        "`discussion_id`. One or the other, never both."
    ),
    action_label="Comments in Notion.",
    response_handler=trim_comments,
)

comments_list = _notion(
    name="comments_list",
    scopes_override=READ_COMMENTS,
    args_schema=CommentsListRequest,
    method="GET",
    url_template="v1/comments",
    description=(
        "List the unresolved comments on a page or block. Resolved discussions are not returned."
    ),
    action_label="Reads Notion comments.",
    response_handler=trim_comments,
    pagination_override=NOTION_PAGINATION,
)

comments_retrieve = _notion(
    name="comments_retrieve",
    scopes_override=READ_COMMENTS,
    args_schema=CommentsRetrieveRequest,
    method="GET",
    url_template="v1/comments/{comment_id}",
    description="Get one comment by ID.",
    action_label="Reads a Notion comment.",
    response_handler=trim_comments,
)

comments_update = _notion(
    name="comments_update",
    scopes_override=INSERT_COMMENTS,
    args_schema=CommentsUpdateRequest,
    method="PATCH",
    url_template="v1/comments/{comment_id}",
    description="Edit a comment's content, replacing it entirely.",
    action_label="Edits a Notion comment.",
    response_handler=trim_comments,
)

comments_delete = _notion(
    name="comments_delete",
    scopes_override=INSERT_COMMENTS,
    args_schema=CommentsDeleteRequest,
    method="DELETE",
    url_template="v1/comments/{comment_id}",
    description="Delete a comment.",
    action_label="Deletes a Notion comment.",
)

# ---------- file uploads ----------

file_uploads_create = _notion(
    name="file_uploads_create",
    scopes_override=INSERT,
    args_schema=FileUploadsCreateRequest,
    method="POST",
    url_template="v1/file_uploads",
    description=(
        'Start a file upload. With `mode="external_url"` Notion fetches the file '
        "from a public HTTPS URL itself and no further upload step is needed — the "
        "one mode that completes without sending raw bytes, which this pack cannot "
        "do. Poll `file_uploads_retrieve` until the status is `uploaded`, then "
        "reference the ID as a `file_upload` on a page, block or files property."
    ),
    action_label="Starts a Notion file upload.",
)

file_uploads_complete = _notion(
    name="file_uploads_complete",
    scopes_override=INSERT,
    args_schema=FileUploadsCompleteRequest,
    method="POST",
    url_template="v1/file_uploads/{file_upload_id}/complete",
    description=(
        "Finish a multi-part upload once every part has been sent. Single-part and "
        "external-URL uploads complete on their own."
    ),
    action_label="Completes a Notion file upload.",
)

file_uploads_retrieve = _notion(
    name="file_uploads_retrieve",
    scopes_override=READ,
    args_schema=FileUploadsRetrieveRequest,
    method="GET",
    url_template="v1/file_uploads/{file_upload_id}",
    description=(
        "Get a file upload and its status. Only an upload whose status is "
        "`uploaded` can be attached to anything."
    ),
    action_label="Checks a Notion file upload.",
)

file_uploads_list = _notion(
    name="file_uploads_list",
    scopes_override=READ,
    args_schema=FileUploadsListRequest,
    method="GET",
    url_template="v1/file_uploads",
    description="List this integration's file uploads, optionally by status.",
    action_label="Lists Notion file uploads.",
    pagination_override=NOTION_PAGINATION,
)

# ---------- workspace odds and ends ----------

custom_emojis_list = _notion(
    name="custom_emojis_list",
    scopes_override=READ,
    args_schema=CustomEmojisListRequest,
    method="GET",
    url_template="v1/custom_emojis",
    description=(
        "List the workspace's own uploaded emoji. Their IDs are what a "
        "`custom_emoji` icon references."
    ),
    action_label="Lists Notion custom emoji.",
    pagination_override=NOTION_PAGINATION,
)

async_tasks_retrieve = _notion(
    name="async_tasks_retrieve",
    scopes_override=READ,
    args_schema=AsyncTasksRetrieveRequest,
    method="GET",
    url_template="v1/async_tasks/{task_id}",
    description=(
        "Check work Notion took in the background. Creating or rewriting a page "
        "from a large Markdown body with `allow_async` answers with a task instead "
        "of the page; this is how you find out whether it finished."
    ),
    action_label="Checks a Notion background task.",
)

TOOLS: list[Tool] = [
    users_list,
    users_retrieve,
    users_retrieve_me,
    search,
    pages_create,
    pages_retrieve,
    pages_update,
    pages_move,
    pages_retrieve_property_item,
    pages_retrieve_markdown,
    pages_update_markdown,
    blocks_retrieve,
    blocks_update,
    blocks_delete,
    blocks_children_list,
    blocks_children_append,
    databases_create,
    databases_retrieve,
    databases_update,
    data_sources_create,
    data_sources_retrieve,
    data_sources_update,
    data_sources_query,
    data_sources_templates_list,
    comments_create,
    comments_list,
    comments_retrieve,
    comments_update,
    comments_delete,
    file_uploads_create,
    file_uploads_complete,
    file_uploads_retrieve,
    file_uploads_list,
    custom_emojis_list,
    async_tasks_retrieve,
]

__all__ = [
    "users_list",
    "users_retrieve",
    "users_retrieve_me",
    "search",
    "pages_create",
    "pages_retrieve",
    "pages_update",
    "pages_move",
    "pages_retrieve_property_item",
    "pages_retrieve_markdown",
    "pages_update_markdown",
    "blocks_retrieve",
    "blocks_update",
    "blocks_delete",
    "blocks_children_list",
    "blocks_children_append",
    "databases_create",
    "databases_retrieve",
    "databases_update",
    "data_sources_create",
    "data_sources_retrieve",
    "data_sources_update",
    "data_sources_query",
    "data_sources_templates_list",
    "comments_create",
    "comments_list",
    "comments_retrieve",
    "comments_update",
    "comments_delete",
    "file_uploads_create",
    "file_uploads_complete",
    "file_uploads_retrieve",
    "file_uploads_list",
    "custom_emojis_list",
    "async_tasks_retrieve",
    "TOOLS",
    "configure",
    "API_VERSION",
    "BASE_URL",
    "NOTION_HEADERS",
    "NOTION_PAGINATION",
    "NOTION_BODY_PAGINATION",
    "SCOPES",
]
