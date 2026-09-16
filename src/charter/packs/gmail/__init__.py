"""
Gmail — twenty-three tools over the Gmail REST API.

The flagship demo of what the boundary buys you: ``messages_send`` takes an
``EmailContent``, and ``Format("rfc822_base64")`` produces the base64url RFC822
blob Gmail's ``raw`` field requires. No MIME assembly in your agent.

    from charter import StaticTokenProvider
    from charter.packs import gmail

    gmail.configure(StaticTokenProvider(access_token))
    await gmail.messages_send.ainvoke(
        body={"raw": {"to": "ada@example.com", "subject": "Hi", "body": "Hello"}}
    )

``configure()`` is optional if ``$GOOGLE_ACCESS_TOKEN`` is set.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.gmail.response_handlers import (
    extract_draft_text,
    extract_label,
    extract_labels,
    extract_message_text,
    extract_thread_list,
    extract_thread_text,
)
from charter.packs.gmail.types import (
    DraftsCreateRequest,
    DraftsDeleteRequest,
    DraftsGetRequest,
    DraftsListRequest,
    DraftsSendRequest,
    DraftsUpdateRequest,
    LabelsCreateRequest,
    LabelsDeleteRequest,
    LabelsGetRequest,
    LabelsListRequest,
    LabelsPatchRequest,
    LabelsUpdateRequest,
    MessagesBatchModifyRequest,
    MessagesGetRequest,
    MessagesListRequest,
    MessagesModifyRequest,
    MessagesSendRequest,
    ThreadsDeleteRequest,
    ThreadsGetRequest,
    ThreadsListRequest,
    ThreadsModifyRequest,
    ThreadsTrashRequest,
    ThreadsUntrashRequest,
)
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://gmail.googleapis.com/"
# Google list endpoints page with an opaque nextPageToken.
GOOGLE_PAGINATION = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")

QUOTA_DOC_URL = "https://developers.google.com/workspace/gmail/api/reference/quota"
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
# threads.delete is the only endpoint here that gmail.modify does not cover;
# Google requires full-mailbox access for the irreversible delete. It is
# declared on that tool alone, so a consent screen built with scopes_for()
# asks for it only when the tool is actually handed out.
FULL_MAILBOX_SCOPE = "https://mail.google.com/"

_credentials = DeferredCredentialProvider("gmail", env_var="GOOGLE_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_gmail = oauth_tool_factory(
    pack="gmail",
    base_url=BASE_URL,
    provider="google",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Google's query parameters are camelCase (`maxResults`, `singleEvents`),
    # like its bodies. Without this the default snake casing sends `max_results`,
    # which Google silently ignores — the worst kind of wrong, because the call
    # succeeds and returns unfiltered results.
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    # Pagination is a property of a list endpoint, not of the API: declaring it
    # on the factory labels every retrieve and write with a cursor parameter
    # they do not accept. It is declared per tool below.
)

threads_list = _gmail(
    name="threads_list",
    args_schema=ThreadsListRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/threads",
    description="List Gmail threads.",
    action_label="Shows inbox conversations.",
    quota_cost=10,
    pagination_override=GOOGLE_PAGINATION,
    response_handler=extract_thread_list,
)

threads_get = _gmail(
    name="threads_get",
    args_schema=ThreadsGetRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/threads/{id}",
    description="Read a Gmail thread.",
    action_label="Reads messages in a conversation.",
    response_handler=extract_thread_text,
    quota_cost=40,
)

threads_modify = _gmail(
    name="threads_modify",
    args_schema=ThreadsModifyRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/threads/{id}/modify",
    description="Modify the labels on a thread, and so on every message in it.",
    action_label="Updates labels on a conversation.",
    response_handler=extract_thread_text,
    quota_cost=10,
)

threads_trash = _gmail(
    name="threads_trash",
    args_schema=ThreadsTrashRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/threads/{id}/trash",
    description="Move a thread and all of its messages to the trash.",
    action_label="Moves a conversation to the trash.",
    response_handler=extract_thread_text,
    quota_cost=20,
)

threads_untrash = _gmail(
    name="threads_untrash",
    args_schema=ThreadsUntrashRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/threads/{id}/untrash",
    description="Take a thread and all of its messages back out of the trash.",
    action_label="Restores a conversation from the trash.",
    response_handler=extract_thread_text,
    quota_cost=10,
)

threads_delete = _gmail(
    name="threads_delete",
    args_schema=ThreadsDeleteRequest,
    method="DELETE",
    url_template="gmail/v1/users/{userId}/threads/{id}",
    description=(
        "Permanently delete a thread and every message in it. This cannot be "
        "undone; threads_trash is the reversible one."
    ),
    action_label="Deletes a conversation for good.",
    scopes_override=[FULL_MAILBOX_SCOPE],
    quota_cost=20,
)

messages_list = _gmail(
    name="messages_list",
    args_schema=MessagesListRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/messages",
    description="List messages in the user's mailbox.",
    action_label="Lists Gmail messages.",
    quota_cost=5,
    pagination_override=GOOGLE_PAGINATION,
)

messages_get = _gmail(
    name="messages_get",
    args_schema=MessagesGetRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/messages/{id}",
    description="Read one message, by the id messages_list returns.",
    action_label="Reads a single email.",
    response_handler=extract_message_text,
    quota_cost=20,
)

messages_modify = _gmail(
    name="messages_modify",
    args_schema=MessagesModifyRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/messages/{id}/modify",
    description="Modify labels on a specific message.",
    action_label="Updates labels on a single message.",
    quota_cost=5,
    response_handler=extract_message_text,
)

messages_batch_modify = _gmail(
    name="messages_batch_modify",
    args_schema=MessagesBatchModifyRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/messages/batchModify",
    description="Modify labels on multiple messages at once.",
    action_label="Updates labels on messages in bulk.",
    quota_cost=50,
)

# Gmail write endpoints (send, drafts) require { "raw": "<base64url RFC-822>" }.
# The "payload" representation is response-only (returned on reads, ignored on
# writes). Message.raw is marked Mode("request_only") and Format("rfc822_base64"),
# so the LLM sees EmailContent fields (to, subject, body, ...) and the transform
# builds the wire format automatically.

messages_send = _gmail(
    name="messages_send",
    args_schema=MessagesSendRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/messages/send",
    description="Send an email via the Gmail API.",
    action_label="Sends an email right away.",
    quota_cost=100,
    response_handler=extract_message_text,
)

drafts_create = _gmail(
    name="drafts_create",
    args_schema=DraftsCreateRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/drafts",
    description="Save an email draft to Gmail.",
    action_label="Saves a draft in Gmail.",
    quota_cost=10,
    response_handler=extract_draft_text,
)

drafts_get = _gmail(
    name="drafts_get",
    args_schema=DraftsGetRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/drafts/{id}",
    description="Read a saved draft, including the message it holds.",
    action_label="Reads a saved draft.",
    response_handler=extract_draft_text,
    quota_cost=20,
)

drafts_list = _gmail(
    name="drafts_list",
    args_schema=DraftsListRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/drafts",
    description="List the drafts in the user's mailbox.",
    action_label="Lists saved drafts.",
    quota_cost=5,
    pagination_override=GOOGLE_PAGINATION,
)

drafts_update = _gmail(
    name="drafts_update",
    args_schema=DraftsUpdateRequest,
    method="PUT",
    url_template="gmail/v1/users/{userId}/drafts/{id}",
    description="Replace a saved draft's content with a new message.",
    action_label="Rewrites a saved draft.",
    quota_cost=15,
    response_handler=extract_draft_text,
)

drafts_delete = _gmail(
    name="drafts_delete",
    args_schema=DraftsDeleteRequest,
    method="DELETE",
    url_template="gmail/v1/users/{userId}/drafts/{id}",
    description="Permanently delete a draft. It is not moved to the trash.",
    action_label="Deletes a draft for good.",
    quota_cost=10,
)

drafts_send = _gmail(
    name="drafts_send",
    args_schema=DraftsSendRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/drafts/send",
    description="Send a saved draft to the recipients in its To, Cc and Bcc headers.",
    action_label="Sends a saved draft.",
    quota_cost=100,
    response_handler=extract_message_text,
)

labels_list = _gmail(
    name="labels_list",
    args_schema=LabelsListRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/labels",
    description="List all labels in the user's mailbox.",
    action_label="Lists Gmail labels.",
    quota_cost=1,
    response_handler=extract_labels,
)

labels_get = _gmail(
    name="labels_get",
    args_schema=LabelsGetRequest,
    method="GET",
    url_template="gmail/v1/users/{userId}/labels/{id}",
    description="Read one label, including its message and thread counts.",
    action_label="Reads a single label.",
    quota_cost=1,
    response_handler=extract_label,
)

labels_create = _gmail(
    name="labels_create",
    args_schema=LabelsCreateRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/labels",
    description="Create a new Gmail label.",
    action_label="Creates a new label.",
    quota_cost=5,
    response_handler=extract_label,
)

labels_update = _gmail(
    name="labels_update",
    args_schema=LabelsUpdateRequest,
    method="PUT",
    url_template="gmail/v1/users/{userId}/labels/{id}",
    description="Replace a label's name, visibility and colour.",
    action_label="Rewrites a label.",
    quota_cost=5,
    response_handler=extract_label,
)

labels_patch = _gmail(
    name="labels_patch",
    args_schema=LabelsPatchRequest,
    method="PATCH",
    url_template="gmail/v1/users/{userId}/labels/{id}",
    description="Change some of a label's fields, leaving the rest as they are.",
    action_label="Updates part of a label.",
    # Google's per-method quota table lists every labels.* method except patch.
    # This mirrors labels.update, which is the same write with patch semantics.
    quota_cost=5,
    response_handler=extract_label,
)

labels_delete = _gmail(
    name="labels_delete",
    args_schema=LabelsDeleteRequest,
    method="DELETE",
    url_template="gmail/v1/users/{userId}/labels/{id}",
    description="Delete a label and remove it from every message and thread it is on.",
    action_label="Deletes a label for good.",
    quota_cost=5,
)

TOOLS: list[Tool] = [
    messages_send,
    messages_list,
    messages_get,
    messages_modify,
    messages_batch_modify,
    threads_list,
    threads_get,
    threads_modify,
    threads_trash,
    threads_untrash,
    threads_delete,
    drafts_create,
    drafts_get,
    drafts_list,
    drafts_update,
    drafts_delete,
    drafts_send,
    labels_list,
    labels_get,
    labels_create,
    labels_update,
    labels_patch,
    labels_delete,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "FULL_MAILBOX_SCOPE",
    "QUOTA_DOC_URL",
    "GOOGLE_PAGINATION",
    "extract_thread_text",
    "extract_message_text",
    "extract_draft_text",
    "messages_send",
    "messages_list",
    "messages_get",
    "messages_modify",
    "messages_batch_modify",
    "threads_list",
    "threads_get",
    "threads_modify",
    "threads_trash",
    "threads_untrash",
    "threads_delete",
    "drafts_create",
    "drafts_get",
    "drafts_list",
    "drafts_update",
    "drafts_delete",
    "drafts_send",
    "labels_list",
    "labels_get",
    "labels_create",
    "labels_update",
    "labels_patch",
    "labels_delete",
]
