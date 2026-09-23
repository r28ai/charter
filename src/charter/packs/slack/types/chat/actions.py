# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Slack's `chat.*` methods.

API reference: https://docs.slack.dev/reference/methods/chat.postmessage
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Gloss


class MessageMetadata(BaseModel):
    """Application-specific metadata attached to a message.

    API Reference: https://docs.slack.dev/reference/methods/chat.postmessage
    """

    event_type: str = Field(..., description="The name of the metadata event, e.g. 'task_created'.")
    event_payload: Dict[str, Any] = Field(
        ..., description="A JSON object of the data associated with the event."
    )


class ChatPostMessageRequest(BaseModel):
    """Input schema for Slack `chat.postMessage`.

    Sends a message to a channel.

    API Reference: https://docs.slack.dev/reference/methods/chat.postmessage
    """

    channel: Annotated[
        str,
        Field(
            ...,
            description=(
                "An encoded ID or channel name that represents a channel, private "
                "group, or IM channel to send the message to. Prefer the encoded ID "
                "(e.g. 'C123ABC456')."
            ),
        ),
        Body(),
    ]
    text: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The main body text of the message. Required unless blocks or "
                "attachments are provided. Used as the fallback string for "
                "notifications when blocks are provided, so it is worth setting "
                "even then."
            ),
        ),
        Body(),
    ]
    blocks: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(
            None,
            description="A JSON-based array of structured Block Kit blocks.",
        ),
        Body(),
    ]
    attachments: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(None, description="A JSON-based array of structured attachments."),
        Body(),
    ]
    thread_ts: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Provide another message's 'ts' value to make this message a reply "
                "in that thread. Avoid using a reply's ts value; use the parent's."
            ),
        ),
        Body(),
    ]
    reply_broadcast: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Used in conjunction with thread_ts and indicates whether the reply "
                "should be made visible to everyone in the channel. Defaults to false."
            ),
        ),
        Body(),
    ]
    markdown_text: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Accepts message text formatted in markdown. Limit this field to "
                "12,000 characters. Cannot be used together with blocks or text."
            ),
        ),
        Body(),
    ]
    mrkdwn: Annotated[
        Optional[bool],
        Field(
            None,
            description="Disable Slack markup parsing by setting to false. Defaults to true.",
        ),
        Body(),
    ]
    parse: Annotated[
        Optional[str],
        Field(
            None,
            description="Change how messages are treated. Accepts 'none' or 'full'.",
        ),
        Body(),
    ]
    link_names: Annotated[
        Optional[bool],
        Field(None, description="Find and link user groups."),
        Body(),
    ]
    unfurl_links: Annotated[
        Optional[bool],
        Field(None, description="Pass true to enable unfurling of primarily text-based content."),
        Body(),
    ]
    unfurl_media: Annotated[
        Optional[bool],
        Field(None, description="Pass false to disable unfurling of media content."),
        Body(),
    ]
    unfurl_app_links: Annotated[
        Optional[bool],
        Field(
            None,
            description="Pass true to enable unfurling of links to installed apps.",
        ),
        Body(),
    ]
    username: Annotated[
        Optional[str],
        Field(
            None,
            description="Set the bot's user name. Requires the chat:write.customize scope.",
        ),
        Body(),
    ]
    icon_url: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "URL to an image to use as the icon for this message. Requires the "
                "chat:write.customize scope."
            ),
        ),
        Body(),
    ]
    icon_emoji: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Emoji to use as the icon for this message, e.g. ':chart_with_upwards_trend:'. "
                "Requires the chat:write.customize scope."
            ),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[MessageMetadata],
        Field(None, description="Application-specific metadata to attach to the message."),
        Body(),
    ]


class ChatUpdateRequest(BaseModel):
    """Input schema for Slack `chat.update`.

    Updates a message. Only messages posted by the authenticated user or bot can
    be updated, and ephemeral messages cannot be updated at all.

    API Reference: https://docs.slack.dev/reference/methods/chat.update
    """

    channel: Annotated[
        str,
        Field(
            ...,
            description=(
                "Channel containing the message to be updated. For direct messages "
                "use the DM ID (starting with 'D')."
            ),
        ),
        Body(),
    ]
    ts: Annotated[
        str,
        Field(..., description="Timestamp of the message to be updated."),
        Body(),
    ]
    text: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The new body text of the message, limited to 4,000 characters. "
                "Required unless blocks or attachments are provided."
            ),
        ),
        Body(),
    ]
    blocks: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(None, description="A JSON-based array of structured Block Kit blocks."),
        Body(),
    ]
    attachments: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(None, description="A JSON-based array of structured attachments."),
        Body(),
    ]
    file_ids: Annotated[
        Optional[List[str]],
        Field(None, description="Array of new file IDs to attach to the message."),
        Body(),
    ]
    reply_broadcast: Annotated[
        Optional[bool],
        Field(
            None,
            description=("Broadcast an existing thread reply to the channel. Defaults to false."),
        ),
        Body(),
    ]
    metadata: Annotated[
        Optional[MessageMetadata],
        Field(None, description="Application-specific metadata to attach to the message."),
        Body(),
    ]


class ChatDeleteRequest(BaseModel):
    """Input schema for Slack `chat.delete`.

    Deletes a message. A bot token may only delete messages posted by that bot.

    API Reference: https://docs.slack.dev/reference/methods/chat.delete
    """

    channel: Annotated[
        str,
        Field(..., description="Channel containing the message to be deleted."),
        Body(),
    ]
    ts: Annotated[
        str,
        Field(
            ...,
            description="Timestamp of the message to be deleted, e.g. '1405894322.002768'.",
        ),
        Body(),
    ]


class ChatPostEphemeralRequest(BaseModel):
    """Input schema for Slack `chat.postEphemeral`.

    An ephemeral message is visible to one person in a channel and disappears when
    they reload. Useful for answering someone without adding to the channel.

    The response is `{"ok": true, "message_ts": ...}` and nothing else: no channel
    and no message object, and the timestamp is `message_ts` rather than `ts`.

    API Reference: https://docs.slack.dev/reference/methods/chat.postEphemeral
    """

    channel: Annotated[str, Field(..., description="The channel to post in."), Body()]
    user: Annotated[
        str,
        Field(..., description="The user who will see the message. Nobody else does."),
        Body(),
    ]
    text: Annotated[
        str,
        Field(..., description="The message text, as Slack markup."),
        Body(),
    ]
    thread_ts: Annotated[
        Optional[str],
        Field(None, description="Post into this thread rather than the channel."),
        Body(),
    ]


class ChatScheduleMessageRequest(BaseModel):
    """Input schema for Slack `chat.scheduleMessage`.

    The returned `scheduled_message_id` is what cancels it later.

    API Reference: https://docs.slack.dev/reference/methods/chat.scheduleMessage
    """

    channel: Annotated[str, Field(..., description="The channel to post in."), Body()]
    post_at: Annotated[
        int,
        Field(
            ...,
            description=(
                "Unix timestamp representing the future time the message should post to Slack."
            ),
        ),
        Body(),
        Gloss(
            "Seconds, not milliseconds: 1700000000, not 1700000000000. At most 120 "
            "days ahead, beyond which Slack answers `time_too_far`, and at most "
            "thirty scheduled messages per channel in any five minutes."
        ),
    ]
    text: Annotated[str, Field(..., description="The message text, as Slack markup."), Body()]
    thread_ts: Annotated[
        Optional[str],
        Field(None, description="Post into this thread rather than the channel."),
        Body(),
    ]
