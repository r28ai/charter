# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Slack response trimming — context economy only.

Slack's failure convention (``200 OK`` with ``{"ok": false}``) is *not* handled
here. It is declared once as :data:`~charter.packs.slack.SLACK_ENVELOPE` and enforced
by the runtime on every call, so these handlers only ever see a successful
payload.

What is left is size. Slack message and user objects are large: block trees,
attachment arrays, edit history, profile image URLs in eight sizes. These keep
what a model can act on and drop the rest, preserving the pagination cursor so
the agent can still page.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "extract_messages",
    "extract_channels",
    "extract_users",
    "extract_user",
    "extract_channel",
    "extract_post_result",
    "extract_scheduled_message",
    "extract_message_reactions",
    "extract_search_results",
]


# -----------------------------------------------------
# Trimming
# -----------------------------------------------------


def _cursor(response: Dict[str, Any]) -> Optional[str]:
    """The cursor, read from the pack declaration rather than re-deriving it."""
    from charter.packs.slack import SLACK_PAGINATION

    return SLACK_PAGINATION.next_cursor(response)


def _trim_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """One Slack message, reduced to what an agent can act on."""
    out: Dict[str, Any] = {
        "ts": message.get("ts"),
        "user": message.get("user") or message.get("bot_id"),
        "text": message.get("text", ""),
    }
    for key in ("thread_ts", "reply_count", "subtype"):
        if message.get(key) is not None:
            out[key] = message[key]

    # Reactions collapse to name + count; the full user list is rarely actionable.
    reactions = message.get("reactions")
    if reactions:
        out["reactions"] = [{"name": r.get("name"), "count": r.get("count")} for r in reactions]

    # Say that structured content exists without inlining the block tree.
    if message.get("blocks"):
        out["has_blocks"] = True
    if message.get("files"):
        out["files"] = [
            {"id": f.get("id"), "name": f.get("name"), "mimetype": f.get("mimetype")}
            for f in message["files"]
        ]
    return out


async def extract_messages(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``conversations.history`` / ``conversations.replies``.

    Keeps the message list and the paging signals; drops block trees, edit
    records, and per-reaction user lists.
    """
    out: Dict[str, Any] = {"messages": [_trim_message(m) for m in response.get("messages") or []]}
    # Kept even when False: it is the paging signal, and a handler that drops it
    # leaves the caller relying on the cursor alone.
    if "has_more" in response:
        out["has_more"] = bool(response["has_more"])
    cursor = _cursor(response)
    if cursor:
        out["next_cursor"] = cursor
    return out


def _trim_channel(channel: Dict[str, Any]) -> Dict[str, Any]:
    """One Slack channel, reduced to what identifies and describes it."""
    entry: Dict[str, Any] = {
        "id": channel.get("id"),
        "name": channel.get("name"),
    }
    for key in ("is_private", "is_archived", "is_im", "is_mpim", "num_members"):
        if channel.get(key) is not None:
            entry[key] = channel[key]
    topic = (channel.get("topic") or {}).get("value")
    purpose = (channel.get("purpose") or {}).get("value")
    if topic:
        entry["topic"] = topic
    if purpose:
        entry["purpose"] = purpose
    return entry


async def extract_channels(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``conversations.list`` to what identifies and describes a channel."""
    out: Dict[str, Any] = {"channels": [_trim_channel(c) for c in response.get("channels") or []]}
    cursor = _cursor(response)
    if cursor:
        out["next_cursor"] = cursor
    return out


def _trim_user(member: Dict[str, Any]) -> Dict[str, Any]:
    profile = member.get("profile") or {}
    entry: Dict[str, Any] = {
        "id": member.get("id"),
        "name": member.get("name"),
        "real_name": member.get("real_name") or profile.get("real_name"),
    }
    # Only present when the token carries users:read.email.
    if profile.get("email"):
        entry["email"] = profile["email"]
    if profile.get("title"):
        entry["title"] = profile["title"]
    for key in ("is_bot", "is_admin", "is_owner", "deleted", "tz"):
        if member.get(key):
            entry[key] = member[key]
    return entry


async def extract_users(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``users.list`` — drops the eight avatar URLs Slack returns per user."""
    out: Dict[str, Any] = {"members": [_trim_user(m) for m in response.get("members") or []]}
    cursor = _cursor(response)
    if cursor:
        out["next_cursor"] = cursor
    return out


# -----------------------------------------------------
# Single objects
# -----------------------------------------------------


async def extract_user(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``users.info`` — the same projection ``users.list`` gets.

    One user object is most of a page of ``users.list``: the eight avatar URLs,
    the colour, the team id, and the whole ``profile`` sub-object arrive for a
    single lookup too.
    """
    user = response.get("user")
    if not isinstance(user, dict):
        return {"user": None}
    return {"user": _trim_user(user)}


async def extract_channel(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim the single channel returned by create / join / open / invite.

    Three things travel beside the channel and are *not* noise, so they survive
    the projection:

    * ``errors`` — ``conversations.invite`` with ``force`` reports the users it
      could not add here, alongside ``ok: true``. Dropping it would turn a
      partial failure into a clean success, which is the one thing a handler
      must never do.
    * ``warning`` / ``already_in_channel`` — joining a channel the bot is
      already in succeeds, and this is the only thing that says so.
    * ``no_op`` / ``already_open`` — the same for re-opening a DM.
    """
    out: Dict[str, Any] = {}
    channel = response.get("channel")
    if isinstance(channel, dict):
        out["channel"] = _trim_channel(channel)
    elif channel is not None:
        # conversations.open without return_im answers with a bare id.
        out["channel"] = channel

    for key in ("errors", "warning", "already_in_channel", "no_op", "already_open"):
        if response.get(key) is not None:
            out[key] = response[key]
    return out


async def extract_post_result(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``chat.postMessage`` / ``chat.update``.

    Both echo the message they just wrote, block tree included, which can be
    larger than the call that created it. ``channel`` and ``ts`` are the two
    values a following call needs — updating, deleting, replying in thread or
    reacting all key off them — so they stay at the top level where the
    description says they are.
    """
    out: Dict[str, Any] = {
        "channel": response.get("channel"),
        "ts": response.get("ts"),
    }
    message = response.get("message")
    if isinstance(message, dict):
        out["message"] = _trim_message(message)
    return out


async def extract_scheduled_message(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``chat.scheduleMessage`` — keeps the id that cancels it."""
    out: Dict[str, Any] = {
        "channel": response.get("channel"),
        "scheduled_message_id": response.get("scheduled_message_id"),
        "post_at": response.get("post_at"),
    }
    message = response.get("message")
    if isinstance(message, dict):
        out["message"] = _trim_message(message)
    return out


async def extract_message_reactions(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``reactions.get``.

    The reactions are nested inside a full message object, so this is the
    message projection plus the two fields that locate it. ``_trim_message``
    already collapses each reaction to name + count; the per-reaction ``users``
    list is dropped with it, which is the bulk of the payload on a message
    several people reacted to.
    """
    out: Dict[str, Any] = {
        "type": response.get("type"),
        "channel": response.get("channel"),
    }
    message = response.get("message")
    if isinstance(message, dict):
        out["message"] = _trim_message(message)
    return out


async def extract_search_results(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``search.messages``.

    Each match carries the message, a nested channel object, a permalink and
    the surrounding messages (``previous``, ``previous_2``, ``next``,
    ``next_2``) — four extra messages per hit that nobody asked for. This keeps
    one line per match plus the permalink, and reports ``total`` so the agent
    knows whether it is looking at all of them.
    """
    matches: List[Dict[str, Any]] = []
    messages = response.get("messages")
    if not isinstance(messages, dict):
        messages = {}

    for match in messages.get("matches") or []:
        entry = _trim_message(match)
        channel = match.get("channel")
        if isinstance(channel, dict):
            entry["channel"] = {"id": channel.get("id"), "name": channel.get("name")}
        elif channel is not None:
            entry["channel"] = channel
        if match.get("permalink"):
            entry["permalink"] = match["permalink"]
        matches.append(entry)

    out: Dict[str, Any] = {"matches": matches}
    if messages.get("total") is not None:
        out["total"] = messages["total"]
    cursor = _cursor(response)
    if cursor:
        out["next_cursor"] = cursor
    return out
