# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Response models for Granola's audit endpoint.

Two things here are unlike the rest of the pack.

``actor`` is a four-way union rather than one object, discriminated by
``object``: an API key, a person, an automated process, or someone acting
through a share link without signing in. The four carry different fields, and
collapsing them into one optional-everything model would lose the fact that
``system`` and ``anonymous`` mean different things.

``data`` is genuinely open. Its fields depend on the action, and Granola
documents them per action rather than in the schema, so it stays a mapping. Its
keys are camelCase, unlike every other key in this API, because they are the
names Granola records internally.

API Reference: https://docs.granola.ai/api-reference/list-audit-events
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from charter.packs.granola.types.common import CursorPage
from charter.types import Mode

__all__ = [
    "ApiKeyActor",
    "UserActor",
    "SystemActor",
    "AnonymousActor",
    "Actor",
    "AuditContext",
    "AuditEvent",
    "ListAuditEventsOutput",
]


class ApiKeyActor(BaseModel):
    """A public API key authenticated the request.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    object: Annotated[
        Literal["api_key"],
        Field("api_key", description="The object type of the actor"),
        Mode("response_only"),
    ]
    id_suffix: Annotated[
        Optional[str],
        Field(
            None,
            description="The final eight characters of the non-secret API key identifier.",
        ),
        Mode("response_only"),
    ]


class UserActor(BaseModel):
    """A person in your workspace performed the action.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    object: Annotated[
        Literal["user"],
        Field("user", description="The object type of the actor"),
        Mode("response_only"),
    ]
    id: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The ID of the user who performed the action, or null if the "
                "recorded actor was not a resolvable user."
            ),
        ),
        Mode("response_only"),
    ]
    email: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The email of the user who performed the action, or null if the "
                "account no longer exists."
            ),
        ),
        Mode("response_only"),
    ]


class SystemActor(BaseModel):
    """No identifiable user performed the action.

    It came from an automated process, such as a scheduled job or an inbound
    webhook from a connected service. This variant carries no other fields.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    object: Annotated[
        Literal["system"],
        Field("system", description="The object type of the actor"),
        Mode("response_only"),
    ]


class AnonymousActor(BaseModel):
    """A person acted without signing in, so there is no account to name.

    Someone opening a note through a shared link, for example. Distinct from
    ``system``, which means no person was involved at all. This variant carries
    no other fields; the ``ip_address`` and ``user_agent`` in ``context`` are the
    only attribution available.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    object: Annotated[
        Literal["anonymous"],
        Field("anonymous", description="The object type of the actor"),
        Mode("response_only"),
    ]


# Discriminated on `object`, which every variant carries and no two share.
Actor = Annotated[
    Union[ApiKeyActor, UserActor, SystemActor, AnonymousActor],
    Field(discriminator="object"),
]


class AuditContext(BaseModel):
    """How the request that produced this event reached Granola.

    Every field is nullable: Granola records what it has, and an event reaching
    it by a path with no client attached has none of the three.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    ip_address: Annotated[
        Optional[str],
        Field(
            None,
            description=("The IP address the request came from, or null if it was not recorded."),
        ),
        Mode("response_only"),
    ]
    user_agent: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The user agent of the client that made the request, or null if it "
                "was not recorded."
            ),
        ),
        Mode("response_only"),
    ]
    client_version: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The Granola client version that made the request, or null if it was not recorded."
            ),
        ),
        Mode("response_only"),
    ]


class AuditEvent(BaseModel):
    """One recorded action: what happened, who did it, and how it arrived.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    id: Annotated[
        Optional[str],
        Field(None, description="The ID of the audit event"),
        Mode("response_only"),
    ]
    object: Annotated[
        Optional[str],
        Field(None, description="The object type of the audit event"),
        Mode("response_only"),
    ]
    action: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "The action that was recorded. See the audit events reference at "
                "https://docs.granola.ai/audit-events for every action and the "
                "`data` it carries. Actions are added over time, so treat this as "
                "an open set of strings rather than a fixed list."
            ),
        ),
        Mode("response_only"),
    ]
    occurred_at: Annotated[
        Optional[str],
        Field(None, description="When the action happened, to the millisecond"),
        Mode("response_only"),
    ]
    collected_at: Annotated[
        Optional[str],
        Field(
            None,
            description=(
                "When Granola recorded the event. Usually the same moment as "
                "`occurred_at`, but later for events we learn about after the fact. "
                "Events are returned in `collected_at` order, so this is the field "
                "that never moves under a cursor, and it carries microseconds to "
                "keep events that share a millisecond ordered."
            ),
        ),
        Mode("response_only"),
    ]
    actor: Annotated[
        Optional[Actor],
        Field(None, description="Who performed the action"),
        Mode("response_only"),
    ]
    data: Annotated[
        Optional[Dict[str, Any]],
        Field(
            None,
            description=(
                "Details of the action. The fields depend on the action, and their "
                "names are the ones Granola records internally, so they are "
                "camelCase rather than snake_case."
            ),
        ),
        Mode("response_only"),
    ]
    context: Annotated[
        Optional[AuditContext],
        Field(
            None,
            description="How the request that produced this event reached Granola",
        ),
        Mode("response_only"),
    ]


class ListAuditEventsOutput(CursorPage):
    """A page of audit events.

    ``hasMore`` is load-bearing here in a way it is not elsewhere: Granola says
    outright that a page can hold fewer than ``page_size`` events and still not
    be the last one, so a walk that stops on a short page stops early.

    API Reference: https://docs.granola.ai/api-reference/list-audit-events
    """

    events: Annotated[
        Optional[List[AuditEvent]],
        Field(None, description="The audit events on this page"),
        Mode("response_only"),
    ]
