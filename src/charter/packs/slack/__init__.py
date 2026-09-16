"""
Slack — ten tools over the Slack Web API.

    from charter import StaticTokenProvider
    from charter.packs import slack

    slack.configure(StaticTokenProvider(bot_token))   # xoxb-...
    await slack.chat_post_message.ainvoke(channel="C123ABC456", text="Deploy finished")

``configure()`` is optional if ``$SLACK_BOT_TOKEN`` is set.

Three things about Slack that this pack absorbs so you do not have to:

**Failure arrives as HTTP 200.** Slack answers a rejected call with ``200 OK`` and
``{"ok": false, "error": "channel_not_found"}``. That is declared once, as
:data:`SLACK_ENVELOPE` on the factory, and the runtime enforces it on every call —
so a Slack failure raises the same ``CredentialError`` / ``APIError`` as any other
API, and there is no per-tool step anyone can forget.

**Rate limits are tiered, not metered.** Slack does not charge quota units per
call the way Google does; each method sits in a tier with a requests-per-minute
allowance. ``quota_cost`` is therefore left unset — a fabricated number would be
worse than none — and each tool records its tier in a comment below.

**Everything is snake_case**, so both body and query casing are ``"snake"``.

Not modelled: response objects. Slack's request schemas are flat argument lists
rather than the resource-shaped bodies Gmail uses, so there is no request type
that needs a ``Message`` or ``Channel`` model. Response shaping is handled by the
trimming handlers in :mod:`~charter.packs.slack.response_handlers`.
"""

from __future__ import annotations

from charter.auth import CredentialProvider
from charter.factories import oauth_tool_factory
from charter.packs._config import DeferredCredentialProvider
from charter.packs.slack.response_handlers import (
    extract_channel,
    extract_channels,
    extract_message_reactions,
    extract_messages,
    extract_post_result,
    extract_scheduled_message,
    extract_search_results,
    extract_user,
    extract_users,
)
from charter.packs.slack.types import (
    ChatDeleteRequest,
    ChatPostEphemeralRequest,
    ChatPostMessageRequest,
    ChatScheduleMessageRequest,
    ChatUpdateRequest,
    ConversationsCreateRequest,
    ConversationsHistoryRequest,
    ConversationsInviteRequest,
    ConversationsJoinRequest,
    ConversationsListRequest,
    ConversationsOpenRequest,
    ConversationsRepliesRequest,
    ReactionsAddRequest,
    ReactionsGetRequest,
    ReactionsRemoveRequest,
    SearchMessagesRequest,
    UsersInfoRequest,
    UsersListRequest,
)
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.pagination import Pagination

BASE_URL = "https://slack.com/api/"
QUOTA_DOC_URL = "https://docs.slack.dev/apis/web-api/rate-limits"

# Bot-token scopes for everything except search_messages, which is user-token only.
SCOPES = [
    "chat:write",
    "channels:read",
    "groups:read",
    "im:read",
    "mpim:read",
    "channels:history",
    "groups:history",
    "im:history",
    "mpim:history",
    "users:read",
    "reactions:write",
]

# Slack reports failure as 200 OK with {"ok": false, "error": "..."}. Declared
# once here; the runtime enforces it on every tool built from the factory below,
# so there is no per-tool step to forget.
# https://docs.slack.dev/reference/methods/chat.postmessage#errors
SLACK_ENVELOPE = Envelope(
    ok_field="ok",
    error_field="error",
    credential_errors={
        "invalid_auth",
        "not_authed",
        "no_permission",
        "token_revoked",
        "token_expired",
        "account_inactive",
        "missing_scope",
        "not_allowed_token_type",
        "ekm_access_denied",
        "org_login_required",
    },
    detail_fields=("needed", "warning"),
)

# Slack pages with an opaque cursor in response_metadata, and sends "" on the
# last page -- which is why an empty cursor must not count as another page.
# https://docs.slack.dev/apis/web-api/pagination
SLACK_PAGINATION = Pagination(
    cursor_field="response_metadata.next_cursor",
    cursor_param="cursor",
    more_field="has_more",
)

_credentials = DeferredCredentialProvider("slack", env_var="SLACK_BOT_TOKEN")


def configure(credential_provider: CredentialProvider) -> None:
    """Point this pack's tools at a credential provider."""
    _credentials.configure(credential_provider)


_slack = oauth_tool_factory(
    pack="slack",
    base_url=BASE_URL,
    provider="slack",
    credential_provider=_credentials,
    scopes=SCOPES,
    # Slack is snake_case on the wire, in both directions.
    body_case="snake",
    query_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
    envelope=SLACK_ENVELOPE,
    # Pagination is a property of a list endpoint, not of the API: declaring it
    # on the factory labels every retrieve and write with a cursor parameter
    # they do not accept. It is declared per tool below.
)

# ---------- chat ----------

chat_post_message = _slack(  # rate limit: special tier, ~1 message/sec/channel
    name="chat_post_message",
    args_schema=ChatPostMessageRequest,
    method="POST",
    url_template="chat.postMessage",
    description=(
        "Send a message to a Slack channel, private group, or DM. Provide `text` "
        "for a plain message; set `thread_ts` to reply inside an existing thread."
    ),
    action_label="Sends a Slack message.",
    response_handler=extract_post_result,
)

chat_update = _slack(  # rate limit: Tier 3
    name="chat_update",
    args_schema=ChatUpdateRequest,
    method="POST",
    url_template="chat.update",
    description=(
        "Update an existing Slack message. Only messages posted by the "
        "authenticated bot or user can be updated."
    ),
    action_label="Edits a Slack message.",
    response_handler=extract_post_result,
)

chat_delete = _slack(  # rate limit: Tier 3
    name="chat_delete",
    args_schema=ChatDeleteRequest,
    method="POST",
    url_template="chat.delete",
    description=(
        "Delete a Slack message. A bot token may only delete messages that bot "
        "posted."
    ),
    action_label="Deletes a Slack message.",
)

# ---------- conversations ----------

conversations_list = _slack(  # rate limit: Tier 2
    name="conversations_list",
    args_schema=ConversationsListRequest,
    method="GET",
    url_template="conversations.list",
    description=(
        "List channels in the workspace. Use this to resolve a channel name to the "
        "channel ID that every other Slack tool expects."
    ),
    action_label="Lists Slack channels.",
    response_handler=extract_channels,
    pagination_override=SLACK_PAGINATION,
)

conversations_history = _slack(  # rate limit: Tier 3
    name="conversations_history",
    args_schema=ConversationsHistoryRequest,
    method="GET",
    url_template="conversations.history",
    description="Fetch recent messages from a Slack channel.",
    action_label="Reads a Slack channel.",
    response_handler=extract_messages,
    pagination_override=SLACK_PAGINATION,
)

conversations_replies = _slack(  # rate limit: Tier 3
    name="conversations_replies",
    args_schema=ConversationsRepliesRequest,
    method="GET",
    url_template="conversations.replies",
    description=(
        "Fetch a thread of messages. Pass the parent message's `ts` as the thread "
        "identifier."
    ),
    action_label="Reads a Slack thread.",
    response_handler=extract_messages,
    pagination_override=SLACK_PAGINATION,
)

# ---------- users ----------

users_list = _slack(  # rate limit: Tier 2
    name="users_list",
    args_schema=UsersListRequest,
    method="GET",
    url_template="users.list",
    description=(
        "List members of the workspace. Use this to resolve a person's name to the "
        "user ID that Slack mentions and filters expect."
    ),
    action_label="Lists Slack members.",
    response_handler=extract_users,
    pagination_override=SLACK_PAGINATION,
)

users_info = _slack(  # rate limit: Tier 4
    name="users_info",
    args_schema=UsersInfoRequest,
    method="GET",
    url_template="users.info",
    description="Get profile information about a single Slack user.",
    action_label="Looks up a Slack user.",
    response_handler=extract_user,
)

# ---------- reactions ----------

reactions_add = _slack(  # rate limit: Tier 3
    name="reactions_add",
    args_schema=ReactionsAddRequest,
    method="POST",
    url_template="reactions.add",
    description="Add an emoji reaction to a Slack message.",
    action_label="Reacts to a Slack message.",
)

# ---------- search ----------

# search.messages is user-token only (search:read). A bot token gets
# not_allowed_token_type, which SLACK_ENVELOPE surfaces as a CredentialError.
search_messages = _slack(  # rate limit: Tier 2
    name="search_messages",
    args_schema=SearchMessagesRequest,
    method="GET",
    url_template="search.messages",
    description=(
        "Search messages across the workspace. Supports Slack search modifiers such "
        "as 'in:#channel', 'from:@user' and 'after:YYYY-MM-DD'. Requires a user "
        "token with the search:read scope — a bot token cannot call this."
    ),
    action_label="Searches Slack messages.",
    pagination_override=SLACK_PAGINATION,
    response_handler=extract_search_results,
)


# ---------- reaching a person ----------

conversations_open = _slack(  # rate limit: Tier 4
    name="conversations_open",
    args_schema=ConversationsOpenRequest,
    method="POST",
    url_template="conversations.open",
    description=(
        "Open a direct message with one person, or a group message with up to "
        "eight. The channel id for a following `chat_post_message` comes back at "
        "`channel.id`. Opening the same conversation twice returns the existing "
        "one rather than making another."
    ),
    action_label="Opens a Slack direct message.",
    response_handler=extract_channel,
)

conversations_create = _slack(  # rate limit: Tier 2
    name="conversations_create",
    args_schema=ConversationsCreateRequest,
    method="POST",
    url_template="conversations.create",
    description="Create a channel. Slack refuses a name that is already taken.",
    action_label="Creates a Slack channel.",
    response_handler=extract_channel,
)

conversations_invite = _slack(  # rate limit: Tier 3
    name="conversations_invite",
    args_schema=ConversationsInviteRequest,
    method="POST",
    url_template="conversations.invite",
    description=(
        "Add people to a channel. With `force` set, Slack adds everyone it can and "
        "reports the rest alongside a success, so read the result."
    ),
    action_label="Invites people to a Slack channel.",
    response_handler=extract_channel,
)

conversations_join = _slack(  # rate limit: Tier 3
    name="conversations_join",
    args_schema=ConversationsJoinRequest,
    method="POST",
    url_template="conversations.join",
    description=(
        "Join a public channel. Joining one the bot is already in succeeds with a "
        "warning."
    ),
    action_label="Joins a Slack channel.",
    response_handler=extract_channel,
)

# ---------- messages nobody else sees, and messages sent later ----------

chat_post_ephemeral = _slack(  # rate limit: Tier 4
    name="chat_post_ephemeral",
    args_schema=ChatPostEphemeralRequest,
    method="POST",
    url_template="chat.postEphemeral",
    description=(
        "Post a message only one person in a channel can see, and which vanishes "
        "when they reload. The response carries `message_ts` and nothing else."
    ),
    action_label="Posts a Slack message only one person sees.",
)

chat_schedule_message = _slack(  # rate limit: Tier 3
    name="chat_schedule_message",
    args_schema=ChatScheduleMessageRequest,
    method="POST",
    url_template="chat.scheduleMessage",
    description=(
        "Schedule a message for later, up to 120 days ahead. The returned "
        "`scheduled_message_id` is what cancels it."
    ),
    action_label="Schedules a Slack message.",
    response_handler=extract_scheduled_message,
)

# ---------- taking a reaction back ----------

reactions_remove = _slack(  # rate limit: Tier 3
    name="reactions_remove",
    args_schema=ReactionsRemoveRequest,
    method="POST",
    url_template="reactions.remove",
    description="Take an emoji reaction off a Slack message.",
    action_label="Removes a reaction from a Slack message.",
)

reactions_get = _slack(  # rate limit: Tier 3
    name="reactions_get",
    args_schema=ReactionsGetRequest,
    method="GET",
    url_template="reactions.get",
    description=(
        "Read the reactions on a message. They come back nested under "
        "`message.reactions`, each with the users who reacted."
    ),
    action_label="Reads reactions on a Slack message.",
    response_handler=extract_message_reactions,
)


TOOLS: list[Tool] = [
    chat_post_message,
    chat_update,
    chat_delete,
    conversations_list,
    conversations_history,
    conversations_replies,
    users_list,
    users_info,
    reactions_add,
    reactions_remove,
    reactions_get,
    conversations_open,
    conversations_create,
    conversations_invite,
    conversations_join,
    chat_post_ephemeral,
    chat_schedule_message,
    search_messages,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "SCOPES",
    "QUOTA_DOC_URL",
    "SLACK_ENVELOPE",
    "SLACK_PAGINATION",
    "extract_messages",
    "extract_channels",
    "extract_users",
    "extract_user",
    "extract_channel",
    "extract_post_result",
    "extract_scheduled_message",
    "extract_message_reactions",
    "extract_search_results",
    "chat_post_message",
    "chat_update",
    "chat_delete",
    "conversations_list",
    "conversations_history",
    "conversations_replies",
    "users_list",
    "users_info",
    "reactions_add",
    "search_messages",
]
