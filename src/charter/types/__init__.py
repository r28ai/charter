# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
The Charter type system: request markers, semantic types, protobuf models, errors.

Three families live here:

- **Markers** (:mod:`charter.types.markers`) — ``Annotated`` metadata that says where a
  field goes on the wire (``Path``/``Query``/``Body``), how it is encoded
  (``Format``), when it is visible (``Mode``), how its key is cased (``Case``), and
  what the model is told about it beyond the API's own description (``Gloss``).
- **Semantic types** (:mod:`charter.types.semantic`) — what the LLM fills in
  (``EmailContent`` rather than a base64 MIME blob).
- **Protobuf models** (:mod:`charter.types.protobuf`) — Pydantic mirrors of the
  ``google.protobuf`` well-known types, for APIs that speak protobuf JSON.

Plus the exception hierarchy (:mod:`charter.types.errors`).
"""

from charter.types.envelope import GRAPHQL_ENVELOPE, Envelope
from charter.types.errors import (
    APIError,
    CharterError,
    CredentialError,
    DeclarationError,
    ToolValidationError,
    TransformError,
)
from charter.types.markers import (
    Body,
    Case,
    ConflictsWith,
    Format,
    Gloss,
    KeyCase,
    Mode,
    Path,
    Query,
    TransportOverride,
    WireName,
)
from charter.types.pagination import Pagination
from charter.types.protobuf import FieldMask, ListValue, NullValue, Struct, Value
from charter.types.semantic import CalendarEvent, DocumentContent, EmailContent, FileContent

__all__ = [
    # envelope
    "Envelope",
    "GRAPHQL_ENVELOPE",
    "Pagination",
    # markers
    "Path",
    "Query",
    "Body",
    "Format",
    "Mode",
    "Case",
    "ConflictsWith",
    "Gloss",
    "KeyCase",
    "TransportOverride",
    "WireName",
    # protobuf
    "Value",
    "ListValue",
    "Struct",
    "FieldMask",
    "NullValue",
    # semantic
    "EmailContent",
    "CalendarEvent",
    "DocumentContent",
    "FileContent",
    # errors
    "CharterError",
    "DeclarationError",
    "CredentialError",
    "ToolValidationError",
    "TransformError",
    "APIError",
]
