"""
Charter — the schema is the contract.

Define AI-agent tools as Pydantic schemas; auth, wire formats, casing, field
policy, and response trimming are handled by a deterministic runtime.

Charter runs where you run it. No telemetry, no phone-home: the library makes no
network calls except the API calls you define. It does measure every call it
makes — see :mod:`charter.observability` — and hands the numbers to you, in your
process, with nowhere else to send them.

    from typing import Annotated, Optional
    from pydantic import BaseModel
    from charter import Path, Query, api_key_tool_factory

    class GetWeather(BaseModel):
        city: Annotated[str, Path()]
        units: Annotated[Optional[str], Query()] = "metric"

    weather = api_key_tool_factory(
        base_url="https://api.openweathermap.org/",
        api_key_headers={"x-api-key": KEY},
    )
    get_current = weather(
        name="get_current_weather",
        args_schema=GetWeather,
        method="GET",
        url_template="data/2.5/weather/{city}",
    )

    await get_current.ainvoke(city="Tokyo")

Credentials and OAuth are not here: they live in :mod:`charter.auth`, one import
path for the whole of authentication. Errors stay here, the whole hierarchy, so
``except CharterError`` catches the entire surface from one namespace.
"""

import logging

from charter.conflicts import conflict_map, format_conflicts
from charter.derive import PathCost
from charter.discovery import json_tokens, schema_tokens
from charter.egress import egress_map, format_egress_map
from charter.execution.executor import ResponseHandler
from charter.execution.schema import partial_of
from charter.factories import api_key_tool_factory, oauth_tool_factory
from charter.naming import qualified_name, qualified_names
from charter.observability import (
    CallCollector,
    CallSink,
    ToolCall,
    collecting,
    format_call_line,
    format_call_summary,
)
from charter.session import ToolSession
from charter.text import decode_base64url, html_to_text
from charter.tool import Tool
from charter.transforms import (
    TransformRegistry,
    TransformSpec,
    apply_transform,
    get_transform,
    register_transform,
)
from charter.types import (
    GRAPHQL_ENVELOPE,
    APIError,
    Body,
    CalendarEvent,
    Case,
    CharterError,
    ConflictsWith,
    CredentialError,
    DeclarationError,
    DocumentContent,
    EmailContent,
    Envelope,
    FieldMask,
    FileContent,
    Format,
    Gloss,
    KeyCase,
    ListValue,
    Mode,
    NullValue,
    Pagination,
    Path,
    Query,
    Struct,
    ToolValidationError,
    TransformError,
    TransportOverride,
    Value,
    WireName,
)

__version__ = "0.1.0"

# The public surface, deliberately.
#
# The plan for this package locked a narrower list — Tool, the factories,
# markers, semantic types, errors. Three groups were added while building, each
# because a documented workflow is impossible without them:
#
#   * protobuf models (Value, Struct, ListValue, FieldMask) — you cannot write a
#     Sheets-shaped schema without Value, and docs/tools/transforms.md tells you to.
#   * the transform registry — docs/tools/transforms.md documents registering your own
#     transform, which needs register_transform / TransformRegistry.
#   * decode_base64url / html_to_text — the skill file tells pack authors to write
#     response handlers; these are the two decodings those handlers keep needing.
#   * the observability records — a response handler's whole job is to shrink what
#     the model sees, and until ToolCall existed there was no way for the author
#     of one to find out whether it worked.
#
# What is no longer here: credentials and OAuth. They were the largest cluster in
# this namespace — 18 names, more than a third of it — and the only one with a
# noun of its own, which the docs had already sorted into docs/auth/ while the
# module tree stayed flat. They now live in `charter.auth`, with no alias left
# behind: a second import path for the same object is a thing to keep in sync
# forever, and packs generated from the skill file would split between the two.
#
# The errors stay, the whole hierarchy. A host writes `except (APIError,
# CredentialError)`, and splitting one member of a hierarchy into another
# namespace costs more than filing it correctly buys.
#
# Everything else stays private. `charter.execution` in particular is the runtime,
# not an API: import from it and expect it to move.

# The library never configures logging for its host: it attaches a NullHandler so
# that emitting a record is a no-op until the application opts in.
logging.getLogger("charter").addHandler(logging.NullHandler())

__all__ = [
    "qualified_name",
    "qualified_names",
    "__version__",
    # tool + factories
    "Tool",
    # progressive disclosure — the tool surface the model actually sees
    "ToolSession",
    "schema_tokens",
    "json_tokens",
    "api_key_tool_factory",
    "oauth_tool_factory",
    "ResponseHandler",
    # deriving one operation's view of a resource
    "partial_of",
    "PathCost",
    # response-handler primitives
    "decode_base64url",
    "html_to_text",
    # egress control
    "egress_map",
    "format_egress_map",
    # the rules a pack declares between its parameters
    "conflict_map",
    "format_conflicts",
    # observability — measured locally, kept locally
    "ToolCall",
    "CallSink",
    "CallCollector",
    "collecting",
    "format_call_line",
    "format_call_summary",
    # envelope — how an API reports failure inside a 200
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
    # semantic types
    "EmailContent",
    "CalendarEvent",
    "DocumentContent",
    "FileContent",
    # protobuf types
    "Value",
    "ListValue",
    "Struct",
    "FieldMask",
    "NullValue",
    # transforms
    "TransformRegistry",
    "TransformSpec",
    "register_transform",
    "get_transform",
    "apply_transform",
    # errors
    "CharterError",
    "DeclarationError",
    "CredentialError",
    "ToolValidationError",
    "TransformError",
    "APIError",
]
