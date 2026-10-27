# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Request schemas for the luma memberships operations.

Drafted from https://public-api.luma.com/openapi.json by scripts/openapi_to_pack.py.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from charter.packs.luma.types.common import (
    RegistrationAnswerAgreeCheck,
    RegistrationAnswerCompany,
    RegistrationAnswerGithub,
    RegistrationAnswerPhoneNumber,
    RegistrationAnswerSelect,
    RegistrationAnswerSelect2,
    RegistrationAnswerTerms,
    RegistrationAnswerUrl,
)
from charter.types import Body, Gloss, Query
from charter.types.model import PackModel

__all__ = [
    "MembershipsTiersListRequest",
    "MembershipsMembersAddRequest",
    "MembershipsMembersUpdateStatusRequest",
]


class MembershipsTiersListRequest(PackModel):
    """List Membership Tiers

    List the calendar's membership tiers, including hidden ones (see is_hidden).

    API Reference: https://docs.luma.com/reference/get_v1-memberships-tiers-list
    """

    pagination_cursor: Annotated[
        Optional[str],
        Field(None, description="Value of `next_cursor` from a previous request."),
        Query(),
    ]
    pagination_limit: Annotated[
        Optional[float],
        Field(
            None,
            description=(
                "The number of items to return. The server will enforce a maximum number."
            ),
        ),
        Query(),
    ]


class MembershipsMembersAddRequest(PackModel):
    """Add Member to Tier

    Add a user to a membership tier. For paid tiers, set skip_payment to true if you are
    handling payment externally.

    API Reference: https://docs.luma.com/reference/post_v1-memberships-members-add
    """

    email: Annotated[
        str,
        Field(
            ...,
            pattern=r"^(?:[A-Za-z0-9_'+\-]+\.)*[A-Za-z0-9_'+\-]*[A-Za-z0-9_+-]@(?:[A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}$",
        ),
        Body(),
        Gloss("Email of the person to add to the tier."),
    ]
    membership_tier_id: Annotated[
        str,
        Field(...),
        Body(),
        Gloss("The tier to add them to, from `memberships_tiers_list`."),
    ]
    registration_answers: Annotated[
        Optional[
            List[
                Union[
                    RegistrationAnswerAgreeCheck,
                    RegistrationAnswerCompany,
                    RegistrationAnswerPhoneNumber,
                    RegistrationAnswerSelect,
                    RegistrationAnswerSelect2,
                    RegistrationAnswerTerms,
                    RegistrationAnswerGithub,
                    RegistrationAnswerUrl,
                ]
            ]
        ],
        Field(None),
        Body(),
        Gloss("Their answers to the tier's registration questions."),
    ]
    skip_payment: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Set to true for paid tiers when handling payment externally. Required "
                "for paid tiers."
            ),
        ),
        Body(),
    ]


class MembershipsMembersUpdateStatusRequest(PackModel):
    """Update Member Status

    Update a member's membership status. Approving a paid tier member captures their
    payment. Declining cancels any active subscription.

    API Reference: https://docs.luma.com/reference/post_v1-memberships-members-update-status
    """

    user_id: Annotated[
        str,
        Field(..., description="User ID (e.g., 'usr-xxx') or email address"),
        Body(),
    ]
    status: Annotated[
        Literal["approved", "declined"],
        Field(...),
        Body(),
        Gloss(
            "`approved` admits the member and, on a paid tier, captures their payment; "
            "`declined` cancels any active subscription."
        ),
    ]
