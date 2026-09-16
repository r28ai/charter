"""Request schemas for Slack's `reactions.*` methods.

API reference: https://docs.slack.dev/reference/methods/reactions.add
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, Field

from charter.types import Body, Query


class ReactionsAddRequest(BaseModel):
    """Input schema for Slack `reactions.add`.

    Adds an emoji reaction to a message.

    API Reference: https://docs.slack.dev/reference/methods/reactions.add
    """

    channel: Annotated[
        str,
        Field(..., description="Channel where the message to add reaction to was posted."),
        Body(),
    ]
    timestamp: Annotated[
        str,
        Field(..., description="Timestamp of the message to add reaction to."),
        Body(),
    ]
    name: Annotated[
        str,
        Field(
            ...,
            description=(
                "Reaction (emoji) name, without surrounding colons — e.g. 'thumbsup'. "
                "Skin tone modifiers are supported, e.g. 'thumbsup::skin-tone-6'."
            ),
        ),
        Body(),
    ]


class ReactionsRemoveRequest(BaseModel):
    """Input schema for Slack `reactions.remove`.

    Answers a bare `{"ok": true}` with no entity attached, unlike most of Slack.

    API Reference: https://docs.slack.dev/reference/methods/reactions.remove
    """

    name: Annotated[
        str,
        Field(..., description="Reaction (emoji) name, without surrounding colons."),
        Body(),
    ]
    channel: Annotated[
        str,
        Field(..., description="Channel where the reacted-to message was posted."),
        Body(),
    ]
    timestamp: Annotated[
        str,
        Field(..., description="Timestamp of the message to take the reaction off."),
        Body(),
    ]


class ReactionsGetRequest(BaseModel):
    """Input schema for Slack `reactions.get`.

    The only GET among the methods this pack adds, so its arguments go in the
    query string rather than a form body.

    The reactions come back nested: under `message.reactions` for a message, and
    the top-level `type` says which kind of thing was read.

    API Reference: https://docs.slack.dev/reference/methods/reactions.get
    """

    channel: Annotated[
        str,
        Field(..., description="Channel where the message was posted."),
        Query(),
    ]
    timestamp: Annotated[
        str,
        Field(..., description="Timestamp of the message to read reactions from."),
        Query(),
    ]
    full: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Return the complete reaction list rather than Slack's abbreviated "
                "one."
            ),
        ),
        Query(),
    ]
