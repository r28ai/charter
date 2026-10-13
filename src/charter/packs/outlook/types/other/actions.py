# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for MailTips and Exchange ID translation.

``getMailTips`` is the one Graph action here whose parameters are documented
in PascalCase — ``EmailAddresses``, ``MailTipsOptions`` — so they carry their
wire names. Its options are a flags enumeration, which travels as one
comma-separated string rather than a JSON array.
"""

from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import Field

from charter.types import Body, Gloss, WireName
from charter.types.model import PackModel

from ..common import ExchangeIdFormat

__all__ = ["MAIL_TIPS_TYPES", "MailTipsRequest", "TranslateExchangeIdsRequest"]

# https://learn.microsoft.com/en-us/graph/api/user-getmailtips#request-body
MAIL_TIPS_TYPES = (
    "automaticReplies",
    "customMailTip",
    "deliveryRestriction",
    "externalMemberCount",
    "mailboxFullStatus",
    "maxMessageSize",
    "moderationStatus",
    "recipientScope",
    "recipientSuggestions",
    "totalMemberCount",
)
_ONE = "(?:" + "|".join(MAIL_TIPS_TYPES) + ")"


class MailTipsRequest(PackModel):
    """Get the MailTips of one or more recipients as available to the signed-in user.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-getmailtips?view=graph-rest-1.0
    """

    email_addresses: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            description="A collection of SMTP addresses of recipients to get MailTips for.",
        ),
        Body(),
        WireName("EmailAddresses"),
    ]
    mail_tips_options: Annotated[
        Optional[str],
        Field(
            None,
            pattern=rf"^{_ONE}(?:\s*,\s*{_ONE})*$",
            description=(
                "A enumeration of flags that represents the requested mailtips. The possible "
                "values are: `automaticReplies`, `customMailTip`, `deliveryRestriction`, "
                "`externalMemberCount`, `mailboxFullStatus`, `maxMessageSize`, "
                "`moderationStatus`, `recipientScope`, `recipientSuggestions`, and "
                "`totalMemberCount`."
            ),
        ),
        Body(),
        WireName("MailTipsOptions"),
        Gloss(
            "One string, not a list: separate several flags with commas, as in "
            "`automaticReplies, mailboxFullStatus`."
        ),
    ]


class TranslateExchangeIdsRequest(PackModel):
    """Translate identifiers of Outlook-related resources between formats.

    API Reference: https://learn.microsoft.com/en-us/graph/api/user-translateexchangeids?view=graph-rest-1.0
    """

    input_ids: Annotated[
        List[str],
        Field(
            ...,
            min_length=1,
            max_length=1000,
            description=(
                "A collection of identifiers to convert. All identifiers in the collection "
                "MUST have the same source ID type, and MUST be for items in the same "
                "mailbox. Maximum size of this collection is 1,000 strings."
            ),
        ),
        Body(),
    ]
    source_id_type: Annotated[
        ExchangeIdFormat,
        Field(
            ...,
            description=(
                "The ID type of the identifiers in the inputIds parameter. `entryId`: the "
                "binary entry ID format used by MAPI clients. `ewsId`: the ID format used by "
                "Exchange Web Services clients. `immutableEntryId`: the binary "
                "MAPI-compatible immutable ID format. `restId`: the default ID format used by "
                "Microsoft Graph. `restImmutableEntryId`: the immutable ID format used by "
                "Microsoft Graph."
            ),
        ),
        Body(),
    ]
    target_id_type: Annotated[
        ExchangeIdFormat,
        Field(..., description="The requested ID type to convert to."),
        Body(),
    ]
