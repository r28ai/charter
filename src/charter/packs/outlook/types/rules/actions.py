# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for the Inbox's message rules.

A rule is conditions, exceptions and actions. All three are wide — twenty-nine
predicates and eleven actions — and all of them are modelled: a rule the
schema cannot express is one the agent cannot create.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import Field

from charter import partial_of
from charter.types import Body, Gloss, Mode, Path, Query, WireName
from charter.types.model import PackModel

from .._odata import FILTER_DESCRIPTION, Select
from ..common import Importance, Recipient

__all__ = [
    "MessageRule",
    "MessageRuleActions",
    "MessageRulePredicates",
    "MessageRuleUpdate",
    "RuleIdRequest",
    "RulesCreateRequest",
    "RulesListRequest",
    "RulesUpdateRequest",
    "SizeRange",
]

# https://learn.microsoft.com/en-us/graph/api/resources/messagerulepredicates
MessageActionFlag = Literal[
    "any",
    "call",
    "doNotForward",
    "followUp",
    "fyi",
    "forward",
    "noResponseNecessary",
    "read",
    "reply",
    "replyToAll",
    "review",
]
Sensitivity = Literal["normal", "personal", "private", "confidential"]

RuleId = Annotated[str, Field(..., description="The unique identifier of the rule."), Path()]

_FOR_IT_TO_APPLY = "in order for the condition or exception to apply."


class SizeRange(PackModel):
    """Specifies the maximum and minimum sizes (in kilobytes) that an incoming message must fall in between.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/sizerange
    """

    maximum_size: Optional[int] = Field(
        None,
        description=(
            "The maximum size (in kilobytes) that an incoming message must have in order "
            "for a condition or exception to apply."
        ),
    )
    minimum_size: Optional[int] = Field(
        None,
        description=(
            "The minimum size (in kilobytes) that an incoming message must have in order "
            "for a condition or exception to apply."
        ),
    )


class MessageRulePredicates(PackModel):
    """Represents the set of conditions and exceptions that are available for a rule.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/messagerulepredicates
    """

    body_contains: Optional[List[str]] = Field(
        None,
        description=f"Represents the strings that should appear in the body of an incoming message {_FOR_IT_TO_APPLY}",
    )
    body_or_subject_contains: Optional[List[str]] = Field(
        None,
        description=f"Represents the strings that should appear in the body or subject of an incoming message {_FOR_IT_TO_APPLY}",
    )
    categories: Optional[List[str]] = Field(
        None,
        description=f"Represents the categories that an incoming message should be labeled with {_FOR_IT_TO_APPLY}",
    )
    from_addresses: Optional[List[Recipient]] = Field(
        None,
        description=f"Represents the specific sender email addresses of an incoming message {_FOR_IT_TO_APPLY}",
    )
    has_attachments: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must have attachments {_FOR_IT_TO_APPLY}",
    )
    header_contains: Optional[List[str]] = Field(
        None,
        description=f"Represents the strings that appear in the headers of an incoming message {_FOR_IT_TO_APPLY}",
    )
    importance: Optional[Importance] = Field(
        None,
        description=(
            "The importance that is stamped on an incoming message in order for the "
            "condition or exception to apply: `low`, `normal`, `high`."
        ),
    )
    is_approval_request: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be an approval request {_FOR_IT_TO_APPLY}",
    )
    is_automatic_forward: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be automatically forwarded {_FOR_IT_TO_APPLY}",
    )
    is_automatic_reply: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be an auto reply {_FOR_IT_TO_APPLY}",
    )
    is_encrypted: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be encrypted {_FOR_IT_TO_APPLY}",
    )
    is_meeting_request: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be a meeting request {_FOR_IT_TO_APPLY}",
    )
    is_meeting_response: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be a meeting response {_FOR_IT_TO_APPLY}",
    )
    is_non_delivery_report: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be a non-delivery report {_FOR_IT_TO_APPLY}",
    )
    is_permission_controlled: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether an incoming message must be permission controlled "
            f"(RMS-protected) {_FOR_IT_TO_APPLY}"
        ),
    )
    is_read_receipt: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be a read receipt {_FOR_IT_TO_APPLY}",
    )
    is_signed: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be S/MIME-signed {_FOR_IT_TO_APPLY}",
    )
    is_voicemail: Optional[bool] = Field(
        None,
        description=f"Indicates whether an incoming message must be a voice mail {_FOR_IT_TO_APPLY}",
    )
    message_action_flag: Optional[MessageActionFlag] = Field(
        None,
        description=(
            "Represents the flag-for-action value that appears on an incoming message in "
            "order for the condition or exception to apply. The possible values are: `any`, "
            "`call`, `doNotForward`, `followUp`, `fyi`, `forward`, `noResponseNecessary`, "
            "`read`, `reply`, `replyToAll`, `review`."
        ),
    )
    not_sent_to_me: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the owner of the mailbox must not be a recipient of an "
            f"incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    recipient_contains: Optional[List[str]] = Field(
        None,
        description=(
            "Represents the strings that appear in either the toRecipients or ccRecipients "
            f"properties of an incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    sender_contains: Optional[List[str]] = Field(
        None,
        description=f"Represents the strings that appear in the from property of an incoming message {_FOR_IT_TO_APPLY}",
    )
    sensitivity: Optional[Sensitivity] = Field(
        None,
        description=(
            "Represents the sensitivity level that must be stamped on an incoming message in "
            "order for the condition or exception to apply. The possible values are: "
            "`normal`, `personal`, `private`, `confidential`."
        ),
    )
    sent_cc_me: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the owner of the mailbox must be in the ccRecipients property "
            f"of an incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    sent_only_to_me: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the owner of the mailbox must be the only recipient in an "
            f"incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    sent_to_addresses: Optional[List[Recipient]] = Field(
        None,
        description=(
            "Represents the email addresses that an incoming message must have been sent to "
            f"{_FOR_IT_TO_APPLY}"
        ),
    )
    sent_to_me: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the owner of the mailbox must be in the toRecipients property "
            f"of an incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    sent_to_or_cc_me: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether the owner of the mailbox must be in either a toRecipients or "
            f"ccRecipients property of an incoming message {_FOR_IT_TO_APPLY}"
        ),
    )
    subject_contains: Optional[List[str]] = Field(
        None,
        description=f"Represents the strings that appear in the subject of an incoming message {_FOR_IT_TO_APPLY}",
    )
    within_size_range: Optional[SizeRange] = Field(
        None,
        description=(
            "Represents the minimum and maximum sizes (in kilobytes) that an incoming message "
            "must fall in between in order for the condition or exception to apply."
        ),
    )


class MessageRuleActions(PackModel):
    """Represents the set of actions that are available to a rule.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/messageruleactions
    """

    assign_categories: Optional[List[str]] = Field(
        None, description="A list of categories to be assigned to a message."
    )
    copy_to_folder: Optional[str] = Field(
        None, description="The ID of a folder that a message is to be copied to."
    )
    delete: Optional[bool] = Field(
        None, description="Indicates whether a message should be moved to the Deleted Items folder."
    )
    forward_as_attachment_to: Optional[List[Recipient]] = Field(
        None,
        description=(
            "The email addresses of the recipients to which a message should be forwarded "
            "as an attachment."
        ),
    )
    forward_to: Optional[List[Recipient]] = Field(
        None,
        description="The email addresses of the recipients to which a message should be forwarded.",
    )
    mark_as_read: Optional[bool] = Field(
        None, description="Indicates whether a message should be marked as read."
    )
    mark_importance: Optional[Importance] = Field(
        None,
        description="Sets the importance of the message, which can be: `low`, `normal`, `high`.",
    )
    move_to_folder: Optional[str] = Field(
        None, description="The ID of the folder that a message will be moved to."
    )
    permanent_delete: Optional[bool] = Field(
        None,
        description=(
            "Indicates whether a message should be permanently deleted and not saved to the "
            "Deleted Items folder."
        ),
    )
    redirect_to: Optional[List[Recipient]] = Field(
        None, description="The email addresses to which a message should be redirected."
    )
    stop_processing_rules: Optional[bool] = Field(
        None, description="Indicates whether subsequent rules should be evaluated."
    )


class MessageRule(PackModel):
    """A rule that applies to messages in the Inbox of a user.

    ``displayName``, ``sequence`` and ``actions`` are required to create one.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/messagerule
    """

    display_name: str = Field(..., description="The display name of the rule.")
    sequence: int = Field(
        ...,
        description="Indicates the order in which the rule is executed, among other rules.",
    )
    actions: MessageRuleActions = Field(
        ...,
        description=(
            "Actions to be taken on a message when the corresponding conditions, if any, are "
            "fulfilled."
        ),
    )
    conditions: Optional[MessageRulePredicates] = Field(
        None,
        description=(
            "Conditions that when fulfilled, will trigger the corresponding actions for that rule."
        ),
    )
    exceptions: Optional[MessageRulePredicates] = Field(
        None, description="Represents exception conditions for the rule."
    )
    is_enabled: Optional[bool] = Field(
        None, description="Indicates whether the rule is enabled to be applied to messages."
    )
    is_read_only: Optional[bool] = Field(
        None,
        description=(
            "Indicates if the rule is read-only and cannot be modified or deleted by the "
            "rules REST API."
        ),
    )
    has_error: Annotated[
        Optional[bool],
        Field(None, description="Indicates whether the rule is in an error condition."),
        Mode("response_only"),
    ]
    id: Annotated[
        Optional[str],
        Field(None, description="The unique identifier of the rule."),
        Mode("response_only"),
    ]


MessageRuleUpdate = partial_of(MessageRule, name="MessageRuleUpdate")


class RulesListRequest(PackModel):
    """Get all the messageRule objects defined for the user's inbox.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-list-messagerules?view=graph-rest-1.0
    """

    filter: Annotated[
        Optional[str],
        Field(None, description=FILTER_DESCRIPTION),
        Query(),
        WireName("$filter"),
        # Found against the live API: these two answer 400 "does not support
        # filtering". A mailbox holds a handful of rules, so listing them all is
        # the dependable way to find one.
        Gloss(
            "Most rule properties cannot be filtered on — isEnabled and sequence are "
            "refused with 400. To find a rule, list them all and read displayName."
        ),
    ]
    select: Select


class RuleIdRequest(PackModel):
    """A request that names one rule and sends nothing else.

    API Reference: https://learn.microsoft.com/en-us/graph/api/messagerule-get?view=graph-rest-1.0
    """

    rule_id: RuleId


class RulesCreateRequest(PackModel):
    """Create a messageRule object by specifying a set of conditions and actions.

    Outlook carries out those actions if an incoming message in the user's
    Inbox meets the specified conditions.

    API Reference: https://learn.microsoft.com/en-us/graph/api/mailfolder-post-messagerules?view=graph-rest-1.0
    """

    rule: Annotated[
        MessageRule,
        Field(..., description="The parameters that are applicable to your rule."),
        Body(),
    ]


class RulesUpdateRequest(PackModel):
    """Change writable properties on a messageRule object and save the changes.

    API Reference: https://learn.microsoft.com/en-us/graph/api/messagerule-update?view=graph-rest-1.0
    """

    rule_id: RuleId
    rule: Annotated[
        MessageRuleUpdate,  # type: ignore[valid-type]
        Field(..., description="The values for relevant fields that should be updated."),
        Body(),
    ]
