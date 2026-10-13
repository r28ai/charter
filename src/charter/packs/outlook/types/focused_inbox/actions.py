# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for Focused Inbox overrides: always-focused or always-other senders.

An override is keyed by the sender's SMTP address. Creating one for an address
that already has one updates it; patching one can change only ``classifyAs``.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import Field

from charter.types import Body, Path
from charter.types.model import PackModel

from ..common import EmailAddress, InferenceClassificationType

__all__ = [
    "InferenceOverrideCreate",
    "InferenceOverrideIdRequest",
    "InferenceOverrideUpdate",
    "InferenceOverridesCreateRequest",
    "InferenceOverridesUpdateRequest",
]

_CLASSIFY_AS = (
    "Specifies how incoming messages from a specific sender should always be classified as. "
    "The possible values are: `focused`, `other`."
)

OverrideId = Annotated[
    str, Field(..., description="The unique identifier of the override."), Path()
]


class InferenceOverrideIdRequest(PackModel):
    """A request that names one override and sends nothing else.

    API Reference: https://learn.microsoft.com/en-us/graph/api/inferenceclassificationoverride-delete?view=graph-rest-1.0
    """

    override_id: OverrideId


class InferenceOverrideCreate(PackModel):
    """An inferenceClassificationOverride, as it is created.

    API Reference: https://learn.microsoft.com/en-us/graph/api/resources/inferenceclassificationoverride
    """

    classify_as: InferenceClassificationType = Field(..., description=_CLASSIFY_AS)
    sender_email_address: EmailAddress = Field(
        ...,
        description="The email address information of the sender for whom the override is created.",
    )


class InferenceOverridesCreateRequest(PackModel):
    """Create an override for a sender identified by an SMTP address.

    If an override already exists with the same SMTP address, then the
    classifyAs and name fields of that override are updated with the provided
    values. The maximum number of overrides supported for a mailbox is 1000.

    API Reference: https://learn.microsoft.com/en-us/graph/api/inferenceclassification-post-overrides?view=graph-rest-1.0
    """

    override: Annotated[
        InferenceOverrideCreate,
        Field(..., description="A JSON representation of inferenceClassificationOverride object."),
        Body(),
    ]


class InferenceOverrideUpdate(PackModel):
    """The one field of an override a PATCH can change.

    API Reference: https://learn.microsoft.com/en-us/graph/api/inferenceclassificationoverride-update?view=graph-rest-1.0
    """

    classify_as: Optional[InferenceClassificationType] = Field(None, description=_CLASSIFY_AS)


class InferenceOverridesUpdateRequest(PackModel):
    """Change the classifyAs field of an override as specified.

    API Reference: https://learn.microsoft.com/en-us/graph/api/inferenceclassificationoverride-update?view=graph-rest-1.0
    """

    override_id: OverrideId
    override: Annotated[
        InferenceOverrideUpdate,
        Field(..., description="The new value for classifyAs."),
        Body(),
    ]
