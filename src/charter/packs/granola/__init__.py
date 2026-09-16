"""
Granola — nine tools over the Granola API: meeting notes, transcripts, folders,
webhooks and the workspace audit log.

    from charter.packs import granola

    granola.configure(api_key="grn_...")
    notes = await granola.notes_list.ainvoke(created_after="2026-01-27")
    note = await granola.notes_get.ainvoke(
        note_id=notes["notes"][0]["id"], include="transcript"
    )

``configure()`` is optional if ``$GRANOLA_API_KEY`` is set. Headers are resolved
per request, so configuring after the tools are built works, and an unconfigured
call raises ``CredentialError`` before anything is sent.

Four things about Granola that this pack absorbs:

**It is a read API with one write surface.** Notes and folders are created in
the Granola app during a meeting; the API has no endpoint that writes either
one. The only things a program can create, change or delete here are webhook
endpoints. Seven of the nine tools are GETs, and the pack does not pretend
otherwise by inventing a note-writing tool out of the summary fields.

**What a key can see is a property of the key.** An API key carries **Personal
notes** and/or **Public notes** access, chosen in the Granola app at the moment
the key is created, and no parameter on any endpoint widens it. There is no
``SCOPES`` constant here for that reason: an API-key factory has nowhere to put
one, and a listing that comes back short is a question about the key rather than
about the filter. The wire spellings ``personal``, ``public`` and ``workspace``
do exist, but only as values of a webhook endpoint's ``scopes`` field, where
they are on the schema and the model does set them.

**The wire is snake_case, with exactly one exception.** Parameters, bodies and
response fields are all snake_case — except ``hasMore``, the boolean that ends
every paginated response. It is declared in :data:`GRANOLA_PAGINATION` as the
authoritative end-of-list signal, because ``cursor`` is null on the last page
and reading the boolean is the answer the API actually gives.

**Failure is always a status code.** There is no ``{"ok": false}`` here and no
errors array, so there is no :class:`~charter.types.envelope.Envelope` on the
factory — the runtime's own 4xx handling is the whole story. The one status
worth knowing by name is ``413 TRANSCRIPT_TOO_LARGE``, which ``notes_get``
answers when a transcript will not inline; ``notes_transcript_get`` is the way
to read that transcript, a bounded page at a time.

Known limits, named rather than hidden:

* **Verifying a delivery is not a tool.** Granola signs every webhook delivery
  following the Standard Webhooks specification — an HMAC-SHA256 over
  ``{webhook-id}.{webhook-timestamp}.{body}``, keyed with the base64-decoded
  signing secret. That is a computation your receiver performs on an inbound
  request, not a call to an API, so it is not something a tool can express. The
  algorithm is written out at https://docs.granola.ai/webhooks#verify-deliveries.
* **The signing secret is returned once.** It appears in the response to
  ``webhook_endpoints_create`` and in no other response, and Granola cannot
  reissue it. A caller that discards it has to delete the endpoint and make
  another.
* **``webhook_endpoints_list`` does not page.** It is the one list endpoint here
  with no cursor and no ``hasMore``, so it declares no pagination. The other
  three all page the same way.
* **Notes without a summary are invisible.** The API only returns notes that
  already have a generated AI summary and transcript. One still processing is
  absent from ``notes_list`` and answers 404 from ``notes_get``, which is a
  different thing from not existing.
"""

from __future__ import annotations

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.granola.response_handlers import trim_note, trim_transcript
from charter.packs.granola.types import (
    AuditListRequest,
    FoldersListRequest,
    NotesGetRequest,
    NotesListRequest,
    NotesTranscriptGetRequest,
    WebhookEndpointsCreateRequest,
    WebhookEndpointsDeleteRequest,
    WebhookEndpointsListRequest,
    WebhookEndpointsUpdateRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://public-api.granola.ai/"
QUOTA_DOC_URL = "https://docs.granola.ai/introduction#rate-limits"

# Granola versions in the path rather than in a header: there is no
# `Granola-Version` to pin and no query parameter to send. `v1` is written into
# every url_template below, so moving to a later version is a deliberate edit to
# this pack rather than something that happens to it on a Tuesday.
# https://docs.granola.ai/api-reference/changelog
API_VERSION = "v1"

# One cursor convention across the three endpoints that page: `cursor` out,
# `cursor` back, and `hasMore` saying whether to keep going. `hasMore` is
# declared because it is the authoritative signal — `cursor` is null on the last
# page, so the fallback would work, but the API answers the question directly
# and there is no reason to infer it.
# https://docs.granola.ai/introduction
GRANOLA_PAGINATION = Pagination(
    cursor_field="cursor",
    cursor_param="cursor",
    more_field="hasMore",
)

_headers: DeferredApiKeyHeaders = api_key_headers(
    "granola",
    {"Authorization": "Bearer CHARTER_UNCONFIGURED"},
    "Authorization",
    "GRANOLA_API_KEY",
)


def configure(api_key: str) -> None:
    """Supply the Granola API key for this pack's tools."""
    _headers.configure(api_key)


_granola = api_key_tool_factory(
    pack="granola",
    base_url=BASE_URL,
    api_key_headers=_headers,
    # Granola is snake_case on the wire, in bodies and query parameters alike.
    # The query default is snake already; it is set explicitly because the two
    # are separate defaults and a reader should not have to know which way each
    # one falls.
    body_case="snake",
    query_case="snake",
    path_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
)

# ---------- notes ----------

notes_list = _granola(
    name="notes_list",
    args_schema=NotesListRequest,
    method="GET",
    url_template=f"{API_VERSION}/notes",
    description=(
        "List meeting notes, filtered by when they were created or last updated and "
        "optionally narrowed to one folder and its subfolders. "
        "Returns each note's id, title, owner and timestamps, not its content. "
        "Fetch that with notes_get. Only notes that already have a "
        "generated AI summary appear here."
    ),
    action_label="Lists Granola meeting notes.",
    pagination_override=GRANOLA_PAGINATION,
)

notes_get = _granola(
    name="notes_get",
    args_schema=NotesGetRequest,
    method="GET",
    url_template=f"{API_VERSION}/notes/{{note_id}}",
    description=(
        "Read one meeting note: its AI summary, the people who attended, the "
        "calendar event it was taken against, and the folders it belongs to. Pass "
        "include='transcript' to get the transcript inline as well. A transcript "
        "too large to inline answers 413 TRANSCRIPT_TOO_LARGE. Read it with "
        "notes_transcript_get instead."
    ),
    action_label="Reads a Granola meeting note.",
    response_handler=trim_note,
)

notes_transcript_get = _granola(
    name="notes_transcript_get",
    args_schema=NotesTranscriptGetRequest,
    method="GET",
    url_template=f"{API_VERSION}/notes/{{note_id}}/transcript",
    description=(
        "Read a meeting transcript one page at a time. Use this for any long "
        "transcript, and whenever notes_get answers 413 TRANSCRIPT_TOO_LARGE. Each "
        "item is one line of speech with who said it and when."
    ),
    action_label="Reads a Granola meeting transcript.",
    response_handler=trim_transcript,
    pagination_override=GRANOLA_PAGINATION,
)

# ---------- folders ----------

folders_list = _granola(
    name="folders_list",
    args_schema=FoldersListRequest,
    method="GET",
    url_template=f"{API_VERSION}/folders",
    description=(
        "List the folders this key can reach, sorted alphabetically. The listing is "
        "flat and each folder names its parent in parent_folder_id, so a hierarchy "
        "is reassembled from a full walk. Use it to find the folder_id that narrows "
        "a note listing or a webhook endpoint's deliveries."
    ),
    action_label="Lists Granola folders.",
    pagination_override=GRANOLA_PAGINATION,
)

# ---------- audit ----------

audit_list = _granola(
    name="audit_list",
    args_schema=AuditListRequest,
    method="GET",
    url_template=f"{API_VERSION}/audit",
    description=(
        "Read the workspace audit log: membership changes, note views, recordings "
        "and the rest, each with who did it and how the request reached Granola. "
        "Filter by action prefix and by date, within a one-year retention window. "
        "Events come back in collected_at order, not occurred_at order."
    ),
    action_label="Lists Granola audit events.",
    pagination_override=GRANOLA_PAGINATION,
)

# ---------- webhook endpoints ----------

webhook_endpoints_create = _granola(
    name="webhook_endpoints_create",
    args_schema=WebhookEndpointsCreateRequest,
    method="POST",
    url_template=f"{API_VERSION}/webhook-endpoints",
    description=(
        "Register an HTTPS URL to receive note events, so a program does not have to "
        "poll. Choose which notes with scopes and, optionally, which folders with "
        "folder_ids. The response carries the signing secret, and no later response "
        "ever does, so store it when this returns."
    ),
    action_label="Registers a Granola webhook endpoint.",
)

webhook_endpoints_list = _granola(
    name="webhook_endpoints_list",
    args_schema=WebhookEndpointsListRequest,
    method="GET",
    url_template=f"{API_VERSION}/webhook-endpoints",
    description=(
        "List the webhook endpoints this key can manage, with each one's URL, "
        "subscribed events, scopes and whether it is enabled. Never includes a "
        "signing secret. Takes no arguments and returns the whole list at once."
    ),
    action_label="Lists Granola webhook endpoints.",
)

webhook_endpoints_update = _granola(
    name="webhook_endpoints_update",
    args_schema=WebhookEndpointsUpdateRequest,
    method="PATCH",
    url_template=f"{API_VERSION}/webhook-endpoints/{{webhook_endpoint_id}}",
    description=(
        "Change a webhook endpoint, or pause it with enabled=false. Omitted fields "
        "are left alone; the list fields replace rather than merge, so sending one "
        "event name leaves the endpoint subscribed to that event only. Pausing "
        "keeps the signing secret, deleting does not."
    ),
    action_label="Updates a Granola webhook endpoint.",
)

webhook_endpoints_delete = _granola(
    name="webhook_endpoints_delete",
    args_schema=WebhookEndpointsDeleteRequest,
    method="DELETE",
    url_template=f"{API_VERSION}/webhook-endpoints/{{webhook_endpoint_id}}",
    description=(
        "Delete a webhook endpoint and stop its deliveries immediately. The signing "
        "secret goes with it. To stop deliveries and keep the configuration, set "
        "enabled=false with webhook_endpoints_update instead."
    ),
    action_label="Deletes a Granola webhook endpoint.",
)

TOOLS: list[Tool] = [
    notes_list,
    notes_get,
    notes_transcript_get,
    folders_list,
    audit_list,
    webhook_endpoints_create,
    webhook_endpoints_list,
    webhook_endpoints_update,
    webhook_endpoints_delete,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "API_VERSION",
    "GRANOLA_PAGINATION",
    "notes_list",
    "notes_get",
    "notes_transcript_get",
    "folders_list",
    "audit_list",
    "webhook_endpoints_create",
    "webhook_endpoints_list",
    "webhook_endpoints_update",
    "webhook_endpoints_delete",
]
