# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Request schemas for open extensions: an app's own named data on a message.

The other way to store such data, a legacy extended property, has no endpoint
of its own. It is written by patching the message or folder it sits on —
``messages_update`` and ``mail_folders_update`` carry the property lists — and
read back through ``$expand`` on ``messages_get`` and ``mail_folders_get``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from charter.types import Body, Path
from charter.types.model import PackModel

from .._common import MESSAGE_ID_DESCRIPTION
from ..common import OpenTypeExtension

__all__ = ["OpenExtensionCreateRequest", "OpenExtensionRequest"]

MessageId = Annotated[str, Field(..., description=MESSAGE_ID_DESCRIPTION), Path()]


class OpenExtensionRequest(PackModel):
    """Identify an open extension on a message, to get or delete it.

    API Reference: https://learn.microsoft.com/en-us/graph/api/opentypeextension-get?view=graph-rest-1.0
    """

    message_id: MessageId
    extension_id: Annotated[
        str,
        Field(
            ...,
            description=(
                "An extension name which is a unique text identifier for an extension, or a "
                "fully qualified name which concatenates the extension type and unique text "
                "identifier. The fully qualified name is returned in the id property when you "
                "create the extension."
            ),
        ),
        Path(),
    ]


class OpenExtensionCreateRequest(PackModel):
    """Create an open extension and add custom properties in an existing message.

    API Reference: https://learn.microsoft.com/en-us/graph/api/opentypeextension-post-opentypeextension?view=graph-rest-1.0
    """

    message_id: MessageId
    extension: Annotated[
        OpenTypeExtension,
        Field(
            ...,
            description=(
                "An openTypeExtension: the required extensionName, and any other custom "
                "data as name-value pairs of primitive types, or arrays of primitive types."
            ),
        ),
        Body(),
    ]
