# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Slack's `conversations.*` methods.

API reference: https://docs.slack.dev/reference/methods/conversations.list
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types import Body, Gloss, Query


class ConversationsListRequest(BaseModel):
    """Input schema for Slack `conversations.list`.

    Lists all channels in a Slack team.

    API Reference: https://docs.slack.dev/reference/methods/conversations.list
    """

    types: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Mix and match channel types by providing a comma-separated list. "
                "Valid values: 'public_channel', 'private_channel', 'mpim', 'im'. "
                "For example 'public_channel,private_channel'. Defaults to "
                "'public_channel'."
            ),
        ),
        Query(),
    ]
    exclude_archived: Annotated[
        Optional[bool],
        Field(None, description="Set to true to exclude archived channels from the list."),
        Query(),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            100,
            ge=1,
            le=999,
            description=(
                "The maximum number of items to return. Fewer than the requested "
                "number of items may be returned, even if the end of the list has "
                "not been reached. Must be an integer under 1000."
            ),
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Paginate through collections of data by setting this to the "
                "next_cursor attribute returned by a previous request's "
                "response_metadata."
            ),
        ),
        Query(),
    ]
    team_id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Encoded team id to list channels in. Required if the token belongs "
                "to an org-wide app."
            ),
        ),
        Query(),
    ]


class ConversationsHistoryRequest(BaseModel):
    """Input schema for Slack `conversations.history`.

    Fetches a conversation's history of messages and events.

    API Reference: https://docs.slack.dev/reference/methods/conversations.history
    """

    channel: Annotated[
        str,
        Field(..., description="Conversation ID to fetch history for."),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Paginate through collections of data by setting this to the "
                "next_cursor attribute returned by a previous request's "
                "response_metadata."
            ),
        ),
        Query(),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            100,
            ge=1,
            le=999,
            description=(
                "The maximum number of items to return. Fewer than the requested "
                "number of items may be returned, even if the end of the "
                "conversation history hasn't been reached. Maximum of 999."
            ),
        ),
        Query(),
    ]
    oldest: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only messages after this Unix timestamp will be included in "
                "results. Defaults to 0."
            ),
        ),
        Gloss(
            'Seconds, not milliseconds: "1700000000", not "1700000000000". A '
            'Slack ts carries a fraction, as in "1405894322.002768".'
        ),
        Query(),
    ]
    latest: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only messages before this Unix timestamp will be included in "
                "results. Default is the current time."
            ),
        ),
        Gloss(
            'Seconds, not milliseconds: "1700000000", not "1700000000000". A '
            'Slack ts carries a fraction, as in "1405894322.002768".'
        ),
        Query(),
    ]
    inclusive: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Include messages with 'oldest' or 'latest' timestamps in results. "
                "Ignored unless either timestamp is specified."
            ),
        ),
        Query(),
    ]
    include_all_metadata: Annotated[
        Optional[bool],
        Field(None, description="Return all metadata associated with this message."),
        Query(),
    ]


class ConversationsRepliesRequest(BaseModel):
    """Input schema for Slack `conversations.replies`.

    Retrieves a thread of messages posted to a conversation.

    API Reference: https://docs.slack.dev/reference/methods/conversations.replies
    """

    channel: Annotated[
        str,
        Field(..., description="Conversation ID to fetch the thread from."),
        Query(),
    ]
    ts: Annotated[
        str,
        Field(
            ...,
            description=(
                "Unique identifier of either a thread's parent message or a message "
                "in the thread. Prefer the parent message's ts."
            ),
        ),
        Query(),
    ]
    cursor: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Paginate through collections of data by setting this to the "
                "next_cursor attribute returned by a previous request's "
                "response_metadata."
            ),
        ),
        Query(),
    ]
    limit: Annotated[
        Optional[int],
        Field(
            100,
            ge=1,
            le=1000,
            description=(
                "The maximum number of items to return. Fewer than the requested "
                "number of items may be returned, even if the end of the list has "
                "not been reached."
            ),
        ),
        Query(),
    ]
    oldest: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only messages after this Unix timestamp will be included in "
                "results. Defaults to 0."
            ),
        ),
        Gloss(
            'Seconds, not milliseconds: "1700000000", not "1700000000000". A '
            'Slack ts carries a fraction, as in "1405894322.002768".'
        ),
        Query(),
    ]
    latest: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Only messages before this Unix timestamp will be included in "
                "results. Defaults to the current time."
            ),
        ),
        Gloss(
            'Seconds, not milliseconds: "1700000000", not "1700000000000". A '
            'Slack ts carries a fraction, as in "1405894322.002768".'
        ),
        Query(),
    ]
    inclusive: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Include messages with 'oldest' or 'latest' timestamps in results. "
                "Ignored unless either timestamp is specified."
            ),
        ),
        Query(),
    ]
    include_all_metadata: Annotated[
        Optional[bool],
        Field(None, description="Return all metadata associated with this message."),
        Query(),
    ]


class ConversationsOpenRequest(BaseModel):
    """Input schema for Slack `conversations.open`.

    Opening a direct message is how an agent reaches a person rather than a
    channel. The channel id to post into comes back at `channel.id`, not at the
    top level.

    Calling this twice for the same people returns the existing conversation
    rather than making another, so it is safe to call before every message.

    API Reference: https://docs.slack.dev/reference/methods/conversations.open
    """

    users: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "Comma-separated user IDs, between one and eight. One opens a direct "
                "message, several open a group one. The caller is always included "
                "and should not be listed."
            ),
        ),
        Body(),
    ]
    channel: Annotated[
        Optional[str],
        Field(
            None,
            description="Resume an existing conversation by id, instead of naming users.",
        ),
        Body(),
    ]
    return_im: Annotated[
        Optional[bool],
        Field(None, description="Return the full conversation object rather than just its id."),
        Body(),
    ]
    prevent_creation: Annotated[
        Optional[bool],
        Field(
            None,
            description="Check whether the conversation exists without creating one.",
        ),
        Body(),
    ]

    @model_validator(mode="after")
    def _names_who_or_which(self) -> ConversationsOpenRequest:
        """Slack marks both optional because they are alternatives, not because
        a request may name neither."""
        if not self.users and not self.channel:
            raise ValueError(
                "Give `users` to open a conversation with people, or `channel` to "
                "resume one. A request with neither names nobody."
            )
        return self


class ConversationsCreateRequest(BaseModel):
    """Input schema for Slack `conversations.create`.

    API Reference: https://docs.slack.dev/reference/methods/conversations.create
    """

    name: Annotated[
        str,
        Field(
            ...,
            description=(
                "The channel name, lowercase, without spaces or periods and at most "
                "80 characters. Slack answers `name_taken` if it already exists."
            ),
        ),
        Body(),
    ]
    is_private: Annotated[
        Optional[bool],
        Field(None, description="Create a private channel rather than a public one."),
        Body(),
    ]


class ConversationsInviteRequest(BaseModel):
    """Input schema for Slack `conversations.invite`.

    With `force` set, Slack can answer `ok: true` alongside a list of the users it
    could not add, so a success here is worth reading rather than assuming.

    API Reference: https://docs.slack.dev/reference/methods/conversations.invite
    """

    channel: Annotated[str, Field(..., description="The channel to invite people to."), Body()]
    users: Annotated[
        str,
        Field(..., description="Comma-separated user IDs, up to a thousand."),
        Body(),
    ]
    force: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Invite everyone who can be invited rather than failing the whole "
                "call on the first bad id."
            ),
        ),
        Body(),
    ]


class ConversationsJoinRequest(BaseModel):
    """Input schema for Slack `conversations.join`.

    Joining a channel the bot is already in succeeds and adds a warning.

    API Reference: https://docs.slack.dev/reference/methods/conversations.join
    """

    channel: Annotated[str, Field(..., description="The channel to join."), Body()]
