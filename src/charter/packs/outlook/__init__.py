# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Outlook — fifty-six tools over the Outlook mail API in Microsoft Graph v1.0.

    from charter.auth import StaticTokenProvider
    from charter.packs import outlook

    outlook.configure(StaticTokenProvider(access_token))
    await outlook.send_mail.ainvoke(
        message={
            "subject": "Hi",
            "body": {"contentType": "text", "content": "Hello"},
            "toRecipients": [{"emailAddress": {"address": "ada@example.com"}}],
        }
    )

``configure()`` is optional if ``$MICROSOFT_ACCESS_TOKEN`` is set — a delegated
Microsoft identity platform token for ``https://graph.microsoft.com``, which
lasts about an hour.

Built from the Graph v1.0 reference (https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0),
with types and enumerations checked against the v1.0 CSDL
(https://graph.microsoft.com/v1.0/$metadata).

**One tool per Graph operation, named after it.** ``messages_update`` is
``PATCH /me/messages/{id}`` and nothing else: marking a message read, flagging
it, categorising it and editing a draft are all that one operation, as they
are in Graph. A deployment that wants an action-sized tool narrows it with
:meth:`~charter.Tool.derived` — ``messages_update.derived(name="mark_read",
keep={"message_id", "message.is_read"})`` — which is where narrowing belongs.
Different resources stay different tools: a message and a mail folder each
have their own ``permanentDelete``, and so does this pack.

Two shapes Graph uses are declared on the operation rather than split into
tools, and neither reaches the model as anything but an optional argument:

**One operation, several paths.** Graph lists messages at ``/me/messages`` and
at ``/me/mailFolders/{id}/messages``, and folders at ``/me/mailFolders`` and
under a parent's ``childFolders``. Each is one tool with an optional
``folder_id`` or ``parent_folder_id``; the runtime calls the first route the
arguments fill (:mod:`charter.execution.routes`).

**One operation, two body formats.** ``send_mail``, ``messages_create``, and
the reply, reply-all and forward operations take JSON *or* a base64 MIME
document. ``mime`` is ``Body(media_type="text/plain")``: set, it is the whole
body and excludes the JSON arguments; unset, the JSON body is what it always
was. ``Format("mime_base64")`` builds the message from an ``EmailContent``, in
the standard base64 alphabet Graph decodes rather than Gmail's base64url.

Three things about Graph that this pack also absorbs:

**Paging is a URL.** A long collection answers with ``@odata.nextLink``, the
whole URL of the next page, and Microsoft is explicit that the ``$skip`` or
``$skiptoken`` inside it is not for extracting. The handlers return it as
``next_link``, every paging tool takes it back under that name, and its query
string replaces the arguments'. The folder a page is of is in the link's path,
so that is taken from the link too, matched against the tool's own routes: a
link of any other collection is refused, and the host and route are always the
tool's. Delta tools also return ``delta_link`` on their last page, which starts
the next round of change tracking the same way; ``messages_delta`` pages with
``max_page_size`` (``Prefer: odata.maxpagesize``), never ``$top``, which ends a
delta round early.

**Query options start with a dollar.** ``$top``, ``$filter``, ``$select`` and
the rest are declared once in ``types/_odata.py`` with their wire names and
Microsoft's descriptions.

**Failure is a status code.** Graph answers errors with 4xx and an ``error``
object, so there is no :class:`~charter.types.envelope.Envelope`.

Known limits, named rather than hidden:

* **Attachment bytes are text.** ``attachments_create`` and a message's inline
  ``attachments`` take a file's text and base64-encode it; a model has no
  binary to give. ``attachments_create_upload_session`` returns the upload URL;
  the byte-range ``PUT``s to it are the host's to make.
* **An item attachment is a message.** Graph also accepts an event or a
  contact as the item; those resources belong to the calendar and people APIs
  and are not modelled here.
* **The signed-in user's mailbox only.** Every route is under ``/me``. The
  ``/users/{id}`` forms are the same operations at another route, and adding
  them is a route per tool rather than a tool per route.
"""

from __future__ import annotations

from typing import List

from charter.auth import AnyOf, CredentialProvider, ScopeRefusal, scopes_for
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.outlook.response_handlers import (
    mime_text,
    raw_attachment,
    read_attachment,
    trim_attachments,
    trim_entity,
    trim_message,
    trim_message_delta,
    trim_messages,
    trim_page,
    upload_session,
)
from charter.packs.outlook.types import (
    AttachmentIdRequest,
    AttachmentsCreateRequest,
    AttachmentsGetRequest,
    AttachmentsListRequest,
    CategoriesCreateRequest,
    CategoriesListRequest,
    CategoriesUpdateRequest,
    CategoryIdRequest,
    InferenceOverrideIdRequest,
    InferenceOverridesCreateRequest,
    InferenceOverridesUpdateRequest,
    MailboxSettingsGetRequest,
    MailboxSettingsUpdateRequest,
    MailFolderIdRequest,
    MailFoldersCreateRequest,
    MailFoldersDeltaRequest,
    MailFoldersGetRequest,
    MailFoldersListRequest,
    MailFoldersMoveRequest,
    MailFoldersUpdateRequest,
    MailTipsRequest,
    MessageForwardRequest,
    MessageIdRequest,
    MessageMoveRequest,
    MessageReplyRequest,
    MessagesCreateRequest,
    MessagesDeltaRequest,
    MessagesGetRequest,
    MessagesListRequest,
    MessagesUpdateRequest,
    NoArgumentsRequest,
    OpenExtensionCreateRequest,
    OpenExtensionRequest,
    RuleIdRequest,
    RulesCreateRequest,
    RulesListRequest,
    RulesUpdateRequest,
    SendMailRequest,
    SupportedTimeZonesRequest,
    TranslateExchangeIdsRequest,
    UploadSessionCreateRequest,
)
from charter.packs.outlook.types._odata import follow_next_link
from charter.tool import Tool
from charter.types.pagination import Pagination

BASE_URL = "https://graph.microsoft.com/v1.0/"
QUOTA_DOC_URL = "https://learn.microsoft.com/en-us/graph/throttling-limits#outlook-service-limits"

# Delegated permissions. Each operation's reference page lists the least
# privileged permission and the higher ones it also accepts; a tool declares
# them all, least first, as one AnyOf, so scopes_for() over a reading tool and a
# writing one asks for Mail.ReadWrite alone rather than for it beside Mail.Read.
# Where a table lists only the least, the higher one is added when Microsoft's
# permissions reference says it includes it: every *.ReadWrite "allows the app
# to create, read, update, and delete". Pages read 2026-10-24.
#
# Left out, under the rule that an alternative must reach everything the tool
# can name: Mail.ReadBasic for the message readers (it has no body and no
# attachments), and Calendars.ReadWrite for the upload session (it reaches
# event attachments, not a message's).
_GRAPH = "https://graph.microsoft.com/"
MAIL_READ_BASIC = _GRAPH + "Mail.ReadBasic"
MAIL_READ = _GRAPH + "Mail.Read"
MAIL_READ_WRITE = _GRAPH + "Mail.ReadWrite"
MAIL_READ_SHARED = _GRAPH + "Mail.Read.Shared"
MAIL_SEND = _GRAPH + "Mail.Send"
MAILTIPS_READ_BASIC_SHARED = _GRAPH + "MailTips.ReadBasic.Shared"
MAILBOX_SETTINGS_READ = _GRAPH + "MailboxSettings.Read"
MAILBOX_SETTINGS_READ_WRITE = _GRAPH + "MailboxSettings.ReadWrite"
USER_READ = _GRAPH + "User.Read"
USER_READ_BASIC_ALL = _GRAPH + "User.ReadBasic.All"
USER_READ_ALL = _GRAPH + "User.Read.All"
USER_READ_WRITE = _GRAPH + "User.ReadWrite"
USER_READ_WRITE_ALL = _GRAPH + "User.ReadWrite.All"

READ_MAIL = AnyOf(MAIL_READ, MAIL_READ_WRITE)
READ_FOLDERS = AnyOf(MAIL_READ_BASIC, MAIL_READ, MAIL_READ_WRITE)
WRITE_MAIL = MAIL_READ_WRITE
SEND_MAIL = MAIL_SEND
READ_SETTINGS = AnyOf(MAILBOX_SETTINGS_READ, MAILBOX_SETTINGS_READ_WRITE)
WRITE_SETTINGS = MAILBOX_SETTINGS_READ_WRITE
READ_PROFILE = AnyOf(USER_READ, USER_READ_BASIC_ALL, USER_READ_ALL)
# translateExchangeIds names User.ReadBasic.All least privileged and User.Read
# among the higher ones; supportedLanguages names them the other way round. Both
# accept both, and User.Read reaches only the signed-in user, so it goes first
# in each. The AgentIdUser.* permissions it also lists are for agent identities.
TRANSLATE_IDS = AnyOf(
    USER_READ, USER_READ_BASIC_ALL, USER_READ_ALL, USER_READ_WRITE, USER_READ_WRITE_ALL
)
MAIL_TIPS = AnyOf(MAIL_READ, MAIL_READ_WRITE, MAIL_READ_SHARED, MAILTIPS_READ_BASIC_SHARED)

# Graph refuses a permission the token lacks with 403 ErrorAccessDenied and
# names none, so InsufficientScope reports what the tool declares.
# https://learn.microsoft.com/en-us/graph/errors
OUTLOOK_REFUSAL = ScopeRefusal(status=403, signal=r'"code"\s*:\s*"ErrorAccessDenied"')

# Graph hands back the next page's whole URL. The handlers return it as
# `next_link`, and the paging tools take it back under the same name.
OUTLOOK_PAGINATION = Pagination(cursor_field="next_link", cursor_param="next_link")

# The routes a paging tool's link is matched against, named once so that the
# tool's `url_template` and its `follow_next_link` cannot disagree. Most
# specific first, as every multi-route `url_template` is.
_MESSAGES = ("me/mailFolders/{folder_id}/messages", "me/messages")
_MESSAGES_DELTA = "me/mailFolders/{folder_id}/messages/delta"
_ATTACHMENTS = "me/messages/{message_id}/attachments"
_FOLDERS = ("me/mailFolders/{parent_folder_id}/childFolders", "me/mailFolders")
_FOLDERS_DELTA = "me/mailFolders/delta"

# `Prefer: outlook.body-content-type` is a header Graph documents on reading a
# message: without it, `body` and `uniqueBody` come back as HTML. Text is what
# a model reads, at a fraction of the tokens, so the reading tools ask for it.
# A host that wants the HTML — to edit a draft in its own formatting — passes
# `headers={"Prefer": 'outlook.body-content-type="html"'}` to ainvoke, which
# applies last.
PREFER_TEXT = {"Prefer": 'outlook.body-content-type="text"'}

_credentials = DeferredCredentialProvider("outlook", env_var="MICROSOFT_ACCESS_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


# Graph is camelCase on the wire, in bodies and in query parameters alike —
# `includeHiddenFolders`, `changeType`. The OData options carry their `$`
# spellings as wire names. Two factories, because static headers are a
# property of a factory: plain, and the reads that ask for text bodies.
_outlook = oauth_tool_factory(
    pack="outlook",
    base_url=BASE_URL,
    provider="microsoft",
    credential_provider=_credentials,
    scopes=[READ_MAIL],
    scope_refusals=[OUTLOOK_REFUSAL],
    body_case="camel",
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
)

_outlook_text = oauth_tool_factory(
    pack="outlook",
    base_url=BASE_URL,
    provider="microsoft",
    credential_provider=_credentials,
    scopes=[READ_MAIL],
    scope_refusals=[OUTLOOK_REFUSAL],
    body_case="camel",
    query_case="camel",
    quota_doc_url=QUOTA_DOC_URL,
    static_headers=PREFER_TEXT,
)

# =====================================================
# Messages
# =====================================================

messages_list = _outlook_text(
    name="messages_list",
    args_schema=MessagesListRequest,
    method="GET",
    url_template=_MESSAGES,
    description=(
        "List or search messages, across the mailbox or in one folder (an ID, or a "
        "well-known name such as inbox or sentitems). Filter with OData, or search with "
        "KQL. Bodies are left out; bodyPreview has the first 255 characters."
    ),
    action_label="Lists emails.",
    build_request=follow_next_link(_MESSAGES),
    pagination_override=OUTLOOK_PAGINATION,
    response_handler=trim_messages,
)

messages_get = _outlook_text(
    name="messages_get",
    args_schema=MessagesGetRequest,
    method="GET",
    url_template="me/messages/{message_id}",
    description=(
        "Read one message: sender, recipients, subject, date and the body as plain text. "
        "Expand attachments or extended properties with expand."
    ),
    action_label="Reads an email.",
    response_handler=trim_message,
)

messages_get_content = _outlook(
    name="messages_get_content",
    args_schema=MessageIdRequest,
    method="GET",
    url_template="me/messages/{message_id}/$value",
    description=(
        "Get a message's MIME content as text: every header, and each body part as encoded "
        "on the wire."
    ),
    action_label="Reads an email's source.",
    response_handler=mime_text,
)

messages_delta = _outlook(
    name="messages_delta",
    args_schema=MessagesDeltaRequest,
    method="GET",
    url_template=_MESSAGES_DELTA,
    description=(
        "Track changes to the messages in one folder. The first round returns every "
        "message a page at a time and ends with a delta_link; pass that as next_link later "
        "to get only what was created, updated or removed since."
    ),
    action_label="Checks a folder for changed emails.",
    build_request=follow_next_link(_MESSAGES_DELTA),
    pagination_override=OUTLOOK_PAGINATION,
    response_handler=trim_message_delta,
)

messages_create = _outlook(
    name="messages_create",
    args_schema=MessagesCreateRequest,
    method="POST",
    url_template=_MESSAGES,
    mode="create",
    description=(
        "Save a new draft, in Drafts unless folder_id names another folder, as a JSON "
        "message or as MIME. messages_send sends it later."
    ),
    action_label="Saves a draft.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_update = _outlook(
    name="messages_update",
    args_schema=MessagesUpdateRequest,
    method="PATCH",
    url_template="me/messages/{message_id}",
    mode="update",
    description=(
        "Change some of a message's properties, leaving the rest: isRead, flag, importance, "
        "categories, and on a draft its recipients, subject and body."
    ),
    action_label="Updates an email.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_delete = _outlook(
    name="messages_delete",
    args_schema=MessageIdRequest,
    method="DELETE",
    url_template="me/messages/{message_id}",
    description=(
        "Delete a message or a draft. It does not go to Deleted Items: Outlook keeps it in "
        "Recoverable Items (recoverableitemsdeletions) for the retention period. To put a "
        "message in Deleted Items, move it there with messages_move; "
        "messages_permanent_delete purges it."
    ),
    action_label="Deletes an email.",
    scopes_override=[WRITE_MAIL],
)

messages_permanent_delete = _outlook(
    name="messages_permanent_delete",
    args_schema=MessageIdRequest,
    method="POST",
    url_template="me/messages/{message_id}/permanentDelete",
    description=(
        "Permanently delete a message. Outlook clients can no longer reach it, and unless "
        "the mailbox is on hold it is purged after the retention period."
    ),
    action_label="Deletes an email for good.",
    scopes_override=[WRITE_MAIL],
)

messages_move = _outlook(
    name="messages_move",
    args_schema=MessageMoveRequest,
    method="POST",
    url_template="me/messages/{message_id}/move",
    description=(
        "Move a message to another folder — archive, deleteditems, or any folder ID. The "
        "moved message has a new id, which this returns."
    ),
    action_label="Moves an email.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_copy = _outlook(
    name="messages_copy",
    args_schema=MessageMoveRequest,
    method="POST",
    url_template="me/messages/{message_id}/copy",
    description="Copy a message into another folder, by folder ID or well-known name.",
    action_label="Copies an email.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_send = _outlook(
    name="messages_send",
    args_schema=MessageIdRequest,
    method="POST",
    url_template="me/messages/{message_id}/send",
    description="Send a saved draft — a new message, reply, reply-all or forward draft.",
    action_label="Sends a draft.",
    scopes_override=[SEND_MAIL],
)

messages_reply = _outlook(
    name="messages_reply",
    args_schema=MessageReplyRequest,
    method="POST",
    url_template="me/messages/{message_id}/reply",
    mode="create",
    description=(
        "Reply to the sender of a message right away. In JSON give a comment, or "
        "message.body to write the whole reply; or give the reply as MIME."
    ),
    action_label="Replies to an email.",
    scopes_override=[SEND_MAIL],
)

messages_reply_all = _outlook(
    name="messages_reply_all",
    args_schema=MessageReplyRequest,
    method="POST",
    url_template="me/messages/{message_id}/replyAll",
    mode="create",
    description=(
        "Reply to the sender and every recipient of a message right away, as JSON or MIME."
    ),
    action_label="Replies to everyone on an email.",
    scopes_override=[SEND_MAIL],
)

messages_forward = _outlook(
    name="messages_forward",
    args_schema=MessageForwardRequest,
    method="POST",
    url_template="me/messages/{message_id}/forward",
    mode="create",
    description=(
        "Forward a message right away. In JSON name the recipients once, in toRecipients "
        "or message.toRecipients; or give the forward as MIME."
    ),
    action_label="Forwards an email.",
    scopes_override=[SEND_MAIL],
)

messages_create_reply = _outlook(
    name="messages_create_reply",
    args_schema=MessageReplyRequest,
    method="POST",
    url_template="me/messages/{message_id}/createReply",
    mode="create",
    description=(
        "Create a draft reply to the sender of a message, to edit with messages_update and "
        "send with messages_send."
    ),
    action_label="Drafts a reply.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_create_reply_all = _outlook(
    name="messages_create_reply_all",
    args_schema=MessageReplyRequest,
    method="POST",
    url_template="me/messages/{message_id}/createReplyAll",
    mode="create",
    description="Create a draft reply to the sender and every recipient of a message.",
    action_label="Drafts a reply to everyone.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

messages_create_forward = _outlook(
    name="messages_create_forward",
    args_schema=MessageForwardRequest,
    method="POST",
    url_template="me/messages/{message_id}/createForward",
    mode="create",
    description="Create a draft forward of a message, to edit and send later.",
    action_label="Drafts a forward.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_message,
)

send_mail = _outlook(
    name="send_mail",
    args_schema=SendMailRequest,
    method="POST",
    url_template="me/sendMail",
    mode="create",
    description=(
        "Send a new email right away, as a JSON message or as MIME. It is saved to Sent "
        "Items unless saveToSentItems is false; Graph answers with no content."
    ),
    action_label="Sends an email right away.",
    scopes_override=[SEND_MAIL],
)

# =====================================================
# Attachments
# =====================================================

attachments_list = _outlook(
    name="attachments_list",
    args_schema=AttachmentsListRequest,
    method="GET",
    url_template=_ATTACHMENTS,
    description="List a message's attachments: name, type, size and id, without the contents.",
    action_label="Lists an email's attachments.",
    build_request=follow_next_link(_ATTACHMENTS),
    pagination_override=OUTLOOK_PAGINATION,
    response_handler=trim_attachments,
)

attachments_get = _outlook(
    name="attachments_get",
    args_schema=AttachmentsGetRequest,
    method="GET",
    url_template="me/messages/{message_id}/attachments/{attachment_id}",
    description=(
        "Read one attachment. A text file comes back as its text; a binary file is "
        "described, not decoded. An attached message comes back with expand set to "
        "microsoft.graph.itemattachment/item."
    ),
    action_label="Reads an email attachment.",
    response_handler=read_attachment,
)

attachments_get_content = _outlook(
    name="attachments_get_content",
    args_schema=AttachmentIdRequest,
    method="GET",
    url_template="me/messages/{message_id}/attachments/{attachment_id}/$value",
    description=(
        "Get an attachment's raw contents: a file's bytes (as text when they are text, "
        "otherwise base64), or an attached message's MIME."
    ),
    action_label="Downloads an email attachment.",
    response_handler=raw_attachment,
)

attachments_create = _outlook(
    name="attachments_create",
    args_schema=AttachmentsCreateRequest,
    method="POST",
    url_template="me/messages/{message_id}/attachments",
    description=(
        "Attach a file (under 3 MB) or a message to a draft. A file's content is its text, "
        "which is base64-encoded for you."
    ),
    action_label="Attaches a file to a draft.",
    scopes_override=[WRITE_MAIL],
    response_handler=read_attachment,
)

attachments_create_upload_session = _outlook(
    name="attachments_create_upload_session",
    args_schema=UploadSessionCreateRequest,
    method="POST",
    url_template="me/messages/{message_id}/attachments/createUploadSession",
    description=(
        "Start attaching a file of 3 MB to 150 MB to a draft: returns the uploadUrl the "
        "file's bytes are then PUT to, in ranges of up to 4 MB, before expirationDateTime."
    ),
    action_label="Starts a large attachment upload.",
    scopes_override=[WRITE_MAIL],
    response_handler=upload_session,
)

attachments_delete = _outlook(
    name="attachments_delete",
    args_schema=AttachmentIdRequest,
    method="DELETE",
    url_template="me/messages/{message_id}/attachments/{attachment_id}",
    description="Delete an attachment from a message or a draft.",
    action_label="Removes an attachment.",
    scopes_override=[WRITE_MAIL],
)

# =====================================================
# Mail folders
# =====================================================

mail_folders_list = _outlook(
    name="mail_folders_list",
    args_schema=MailFoldersListRequest,
    method="GET",
    url_template=_FOLDERS,
    description=(
        "List the folders under the mailbox root, or under parent_folder_id, with their "
        "unread and total counts. One level at a time; hidden folders only with "
        "includeHiddenFolders."
    ),
    action_label="Lists mail folders.",
    scopes_override=[READ_FOLDERS],
    build_request=follow_next_link(_FOLDERS),
    pagination_override=OUTLOOK_PAGINATION,
    response_handler=trim_page,
)

mail_folders_get = _outlook(
    name="mail_folders_get",
    args_schema=MailFoldersGetRequest,
    method="GET",
    url_template="me/mailFolders/{folder_id}",
    description=(
        "Read one folder, by ID or well-known name, with its unread and total counts. "
        "Expand extended properties with expand."
    ),
    action_label="Reads a mail folder.",
    scopes_override=[READ_FOLDERS],
    response_handler=trim_entity,
)

mail_folders_create = _outlook(
    name="mail_folders_create",
    args_schema=MailFoldersCreateRequest,
    method="POST",
    url_template=_FOLDERS,
    description=(
        "Create a folder under the root or under parent_folder_id, or a search folder — a "
        "saved filter over folders you name. A folder can be made hidden only here."
    ),
    action_label="Creates a mail folder.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

mail_folders_update = _outlook(
    name="mail_folders_update",
    args_schema=MailFoldersUpdateRequest,
    method="PATCH",
    url_template="me/mailFolders/{folder_id}",
    description=(
        "Rename a folder or set its extended properties, or change a search folder's "
        "source folders or filter."
    ),
    action_label="Updates a mail folder.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

mail_folders_delete = _outlook(
    name="mail_folders_delete",
    args_schema=MailFolderIdRequest,
    method="DELETE",
    url_template="me/mailFolders/{folder_id}",
    description=(
        "Delete a folder, or a search folder, and what is in it. It does not go to Deleted "
        "Items; to put a folder there, move it with mail_folders_move. "
        "mail_folders_permanent_delete purges it."
    ),
    action_label="Deletes a mail folder.",
    scopes_override=[WRITE_MAIL],
)

mail_folders_permanent_delete = _outlook(
    name="mail_folders_permanent_delete",
    args_schema=MailFolderIdRequest,
    method="POST",
    url_template="me/mailFolders/{folder_id}/permanentDelete",
    description=(
        "Permanently delete a folder and remove its items from the mailbox. Unlike a "
        "message, a folder is not kept in the purges folder: it is gone."
    ),
    action_label="Deletes a mail folder for good.",
    scopes_override=[WRITE_MAIL],
)

mail_folders_move = _outlook(
    name="mail_folders_move",
    args_schema=MailFoldersMoveRequest,
    method="POST",
    url_template="me/mailFolders/{folder_id}/move",
    description="Move a folder and everything in it into another folder.",
    action_label="Moves a mail folder.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

mail_folders_copy = _outlook(
    name="mail_folders_copy",
    args_schema=MailFoldersMoveRequest,
    method="POST",
    url_template="me/mailFolders/{folder_id}/copy",
    description="Copy a folder and everything in it into another folder.",
    action_label="Copies a mail folder.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

mail_folders_delta = _outlook(
    name="mail_folders_delta",
    args_schema=MailFoldersDeltaRequest,
    method="GET",
    url_template=_FOLDERS_DELTA,
    description=(
        "Track changes to the mailbox's folders. The first round returns every folder and "
        "ends with a delta_link; pass that as next_link later to get only what changed."
    ),
    action_label="Checks for changed mail folders.",
    scopes_override=[READ_FOLDERS],
    build_request=follow_next_link(_FOLDERS_DELTA),
    pagination_override=OUTLOOK_PAGINATION,
    response_handler=trim_page,
)

# =====================================================
# Categories
# =====================================================

master_categories_list = _outlook(
    name="master_categories_list",
    args_schema=CategoriesListRequest,
    method="GET",
    url_template="me/outlook/masterCategories",
    description="List the categories defined for the mailbox, with their colors.",
    action_label="Lists email categories.",
    scopes_override=[READ_SETTINGS],
    response_handler=trim_page,
)

master_categories_get = _outlook(
    name="master_categories_get",
    args_schema=CategoryIdRequest,
    method="GET",
    url_template="me/outlook/masterCategories/{category_id}",
    description="Read one category.",
    action_label="Reads an email category.",
    scopes_override=[READ_SETTINGS],
    response_handler=trim_entity,
)

master_categories_create = _outlook(
    name="master_categories_create",
    args_schema=CategoriesCreateRequest,
    method="POST",
    url_template="me/outlook/masterCategories",
    description="Create a category. Its name is fixed once created; only the color can change.",
    action_label="Creates an email category.",
    scopes_override=[WRITE_SETTINGS],
    response_handler=trim_entity,
)

master_categories_update = _outlook(
    name="master_categories_update",
    args_schema=CategoriesUpdateRequest,
    method="PATCH",
    url_template="me/outlook/masterCategories/{category_id}",
    description="Change a category's color.",
    action_label="Recolors an email category.",
    scopes_override=[WRITE_SETTINGS],
    response_handler=trim_entity,
)

master_categories_delete = _outlook(
    name="master_categories_delete",
    args_schema=CategoryIdRequest,
    method="DELETE",
    url_template="me/outlook/masterCategories/{category_id}",
    description="Delete a category from the mailbox's list.",
    action_label="Deletes an email category.",
    scopes_override=[WRITE_SETTINGS],
)

# =====================================================
# Inbox rules
# =====================================================

message_rules_list = _outlook(
    name="message_rules_list",
    args_schema=RulesListRequest,
    method="GET",
    url_template="me/mailFolders/inbox/messageRules",
    description="List the Inbox rules, in the order they run.",
    action_label="Lists inbox rules.",
    scopes_override=[READ_SETTINGS],
    response_handler=trim_page,
)

message_rules_get = _outlook(
    name="message_rules_get",
    args_schema=RuleIdRequest,
    method="GET",
    url_template="me/mailFolders/inbox/messageRules/{rule_id}",
    description="Read one Inbox rule: its conditions, exceptions and actions.",
    action_label="Reads an inbox rule.",
    scopes_override=[READ_SETTINGS],
    response_handler=trim_entity,
)

message_rules_create = _outlook(
    name="message_rules_create",
    args_schema=RulesCreateRequest,
    method="POST",
    url_template="me/mailFolders/inbox/messageRules",
    description=(
        "Create an Inbox rule: when an incoming message meets the conditions, and none of "
        "the exceptions, Outlook takes the actions."
    ),
    action_label="Creates an inbox rule.",
    scopes_override=[WRITE_SETTINGS],
    response_handler=trim_entity,
)

message_rules_update = _outlook(
    name="message_rules_update",
    args_schema=RulesUpdateRequest,
    method="PATCH",
    url_template="me/mailFolders/inbox/messageRules/{rule_id}",
    description="Change some of an Inbox rule's properties, leaving the rest as they are.",
    action_label="Edits an inbox rule.",
    scopes_override=[WRITE_SETTINGS],
    response_handler=trim_entity,
)

message_rules_delete = _outlook(
    name="message_rules_delete",
    args_schema=RuleIdRequest,
    method="DELETE",
    url_template="me/mailFolders/inbox/messageRules/{rule_id}",
    description="Delete an Inbox rule.",
    action_label="Deletes an inbox rule.",
    scopes_override=[WRITE_SETTINGS],
)

# =====================================================
# Mailbox settings
# =====================================================

mailbox_settings_get = _outlook(
    name="mailbox_settings_get",
    args_schema=MailboxSettingsGetRequest,
    method="GET",
    url_template="me/mailboxSettings",
    description=(
        "Read the mailbox's settings: automatic replies (out of office), time zone, working "
        "hours, language, and date and time formats."
    ),
    action_label="Reads mailbox settings.",
    scopes_override=[READ_SETTINGS],
    response_handler=trim_entity,
)

mailbox_settings_update = _outlook(
    name="mailbox_settings_update",
    args_schema=MailboxSettingsUpdateRequest,
    method="PATCH",
    url_template="me/mailboxSettings",
    description=(
        "Change some of the mailbox's settings, leaving the rest: automatic replies, time "
        "zone, working hours, language, formats."
    ),
    action_label="Changes mailbox settings.",
    scopes_override=[WRITE_SETTINGS],
    response_handler=trim_entity,
)

supported_languages = _outlook(
    name="supported_languages",
    args_schema=NoArgumentsRequest,
    method="GET",
    url_template="me/outlook/supportedLanguages",
    description="List the languages and locales the user's mailbox server supports.",
    action_label="Lists supported languages.",
    scopes_override=[READ_PROFILE],
    response_handler=trim_page,
)

supported_time_zones = _outlook(
    name="supported_time_zones",
    args_schema=SupportedTimeZonesRequest,
    method="GET",
    url_template=(
        "me/outlook/supportedTimeZones"
        "(TimeZoneStandard=microsoft.graph.timeZoneStandard'{time_zone_standard}')",
        "me/outlook/supportedTimeZones",
    ),
    description="List the time zones the user's mailbox server supports, as Windows or IANA names.",
    action_label="Lists supported time zones.",
    scopes_override=[READ_PROFILE],
    response_handler=trim_page,
)

# =====================================================
# Focused Inbox
# =====================================================

inference_overrides_list = _outlook(
    name="inference_overrides_list",
    args_schema=NoArgumentsRequest,
    method="GET",
    url_template="me/inferenceClassification/overrides",
    description="List the senders whose mail is always sorted into Focused or Other.",
    action_label="Lists Focused Inbox overrides.",
    response_handler=trim_page,
)

inference_overrides_create = _outlook(
    name="inference_overrides_create",
    args_schema=InferenceOverridesCreateRequest,
    method="POST",
    url_template="me/inferenceClassification/overrides",
    description=(
        "Always sort a sender's future mail into Focused or Other. If the sender already "
        "has an override, it is updated."
    ),
    action_label="Adds a Focused Inbox override.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

inference_overrides_update = _outlook(
    name="inference_overrides_update",
    args_schema=InferenceOverridesUpdateRequest,
    method="PATCH",
    url_template="me/inferenceClassification/overrides/{override_id}",
    description="Switch an override between Focused and Other.",
    action_label="Changes a Focused Inbox override.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

inference_overrides_delete = _outlook(
    name="inference_overrides_delete",
    args_schema=InferenceOverrideIdRequest,
    method="DELETE",
    url_template="me/inferenceClassification/overrides/{override_id}",
    description="Remove an override, so the sender's mail is sorted automatically again.",
    action_label="Removes a Focused Inbox override.",
    scopes_override=[WRITE_MAIL],
)

# =====================================================
# Open extensions
# =====================================================

extensions_get = _outlook(
    name="extensions_get",
    args_schema=OpenExtensionRequest,
    method="GET",
    url_template="me/messages/{message_id}/extensions/{extension_id}",
    description="Read an open extension — an app's own named data — stored on a message.",
    action_label="Reads app data on an email.",
    response_handler=trim_entity,
)

extensions_create = _outlook(
    name="extensions_create",
    args_schema=OpenExtensionCreateRequest,
    method="POST",
    url_template="me/messages/{message_id}/extensions",
    description=(
        "Store an open extension on a message: an extensionName and any custom name-value "
        "pairs of primitive values or arrays of them."
    ),
    action_label="Stores app data on an email.",
    scopes_override=[WRITE_MAIL],
    response_handler=trim_entity,
)

extensions_delete = _outlook(
    name="extensions_delete",
    args_schema=OpenExtensionRequest,
    method="DELETE",
    url_template="me/messages/{message_id}/extensions/{extension_id}",
    description="Delete an open extension from a message.",
    action_label="Removes app data from an email.",
    scopes_override=[WRITE_MAIL],
)

# =====================================================
# User actions
# =====================================================

get_mail_tips = _outlook(
    name="get_mail_tips",
    args_schema=MailTipsRequest,
    method="POST",
    url_template="me/getMailTips",
    description=(
        "Check recipients before sending: automatic replies, full mailboxes, delivery "
        "restrictions, moderation, external recipients and distribution-list sizes."
    ),
    action_label="Checks recipients before sending.",
    scopes_override=[MAIL_TIPS],
    response_handler=trim_page,
)

translate_exchange_ids = _outlook(
    name="translate_exchange_ids",
    args_schema=TranslateExchangeIdsRequest,
    method="POST",
    url_template="me/translateExchangeIds",
    description=(
        "Convert up to 1,000 Outlook item IDs from one format to another — for example from "
        "restId to the immutable restImmutableEntryId, which survives a move."
    ),
    action_label="Converts Outlook IDs.",
    scopes_override=[TRANSLATE_IDS],
    response_handler=trim_page,
)

TOOLS: List[Tool] = [
    # messages
    messages_list,
    messages_get,
    messages_get_content,
    messages_delta,
    messages_create,
    messages_update,
    messages_delete,
    messages_permanent_delete,
    messages_move,
    messages_copy,
    messages_send,
    messages_reply,
    messages_reply_all,
    messages_forward,
    messages_create_reply,
    messages_create_reply_all,
    messages_create_forward,
    send_mail,
    # attachments
    attachments_list,
    attachments_get,
    attachments_get_content,
    attachments_create,
    attachments_create_upload_session,
    attachments_delete,
    # mail folders
    mail_folders_list,
    mail_folders_get,
    mail_folders_create,
    mail_folders_update,
    mail_folders_delete,
    mail_folders_permanent_delete,
    mail_folders_move,
    mail_folders_copy,
    mail_folders_delta,
    # categories
    master_categories_list,
    master_categories_get,
    master_categories_create,
    master_categories_update,
    master_categories_delete,
    # inbox rules
    message_rules_list,
    message_rules_get,
    message_rules_create,
    message_rules_update,
    message_rules_delete,
    # mailbox settings
    mailbox_settings_get,
    mailbox_settings_update,
    supported_languages,
    supported_time_zones,
    # focused inbox
    inference_overrides_list,
    inference_overrides_create,
    inference_overrides_update,
    inference_overrides_delete,
    # open extensions
    extensions_get,
    extensions_create,
    extensions_delete,
    # user actions
    get_mail_tips,
    translate_exchange_ids,
]

# Everything the whole pack needs, for a consent screen that hands out all of
# it: four permissions, because Mail.ReadWrite covers every reader.
SCOPES = scopes_for(TOOLS)

__all__ = [
    "TOOLS",
    "OUTLOOK_REFUSAL",
    "configure",
    "BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "OUTLOOK_PAGINATION",
    "PREFER_TEXT",
    "messages_list",
    "messages_get",
    "messages_get_content",
    "messages_delta",
    "messages_create",
    "messages_update",
    "messages_delete",
    "messages_permanent_delete",
    "messages_move",
    "messages_copy",
    "messages_send",
    "messages_reply",
    "messages_reply_all",
    "messages_forward",
    "messages_create_reply",
    "messages_create_reply_all",
    "messages_create_forward",
    "send_mail",
    "attachments_list",
    "attachments_get",
    "attachments_get_content",
    "attachments_create",
    "attachments_create_upload_session",
    "attachments_delete",
    "mail_folders_list",
    "mail_folders_get",
    "mail_folders_create",
    "mail_folders_update",
    "mail_folders_delete",
    "mail_folders_permanent_delete",
    "mail_folders_move",
    "mail_folders_copy",
    "mail_folders_delta",
    "master_categories_list",
    "master_categories_get",
    "master_categories_create",
    "master_categories_update",
    "master_categories_delete",
    "message_rules_list",
    "message_rules_get",
    "message_rules_create",
    "message_rules_update",
    "message_rules_delete",
    "mailbox_settings_get",
    "mailbox_settings_update",
    "supported_languages",
    "supported_time_zones",
    "inference_overrides_list",
    "inference_overrides_create",
    "inference_overrides_update",
    "inference_overrides_delete",
    "extensions_get",
    "extensions_create",
    "extensions_delete",
    "get_mail_tips",
    "translate_exchange_ids",
]
