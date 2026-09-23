# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Tool discovery: the model is given names, and fetches schemas on demand.

A tool's parameter schema is an order of magnitude larger than the thing it
describes. Across the fifteen shipped packs the schemas come to about 518,000
tokens, while a trimmed tool result runs to roughly 1,300. Over 220 measured
agent runs the model called 3.6 of the 16.2 tools it had been given, so most of
that went out to describe calls that were never made.

This module is the other half of the contract. The schema is still the contract,
and a loaded tool is still fully typed — nothing here routes calls through a
generic ``execute(slug, arguments)`` blob. What changes is *when* the schema is
sent: a tool the model has not asked for is present as a name and absent as a
schema.

The mechanism is Claude Code's deferred tools, deliberately and exactly:

- **A flat catalogue of names**, with a notice that the schemas are not loaded
  and calling one will fail. No descriptions and no grouping: the pack is a
  substring of every qualified name, which is what makes ``+`` filtering enough
  on its own.
- **``ToolSearch``**, which turns names into loaded tools. ``select:a,b,c`` for
  exact names, bare keywords for a ranked search, ``+term`` to require a
  substring. Batching is the documented default.
- **An unloaded tool is not offered.** Not with an empty schema, not behind a
  wrapper: absent. Two earlier designs left them callable and the model called
  them, guessing arguments and failing validation three to four times a run.
  Making the wrong move unavailable removed that floor entirely.

Every tool is deferred, whatever its size and however few there are. Claude Code
keeps a hot set resident, but that set is its own built-in core; every tool
reached through a configured MCP server is deferred, all of them, however many.
A Charter tool is a configured tool, so this is the same line drawn in the same
place.

Deferring by size instead was measured and dropped. A resident tool only pays for
itself if it saves a ``ToolSearch`` round trip, and schema size is
anti-correlated with being the tool an agent reaches for *first*: an entry point
takes query parameters and a delete takes an id. A 200-token threshold, measured over the
eleven packs shipped at the time, kept 25 tools resident that no agent starts with and deferred 25 of
the 28 list and search tools. On gmail it kept ``threads_delete`` and
``labels_delete`` while deferring ``messages_list``, so the round trip was paid
anyway and the resident set cost 1,355 tokens to avoid nothing.

See :class:`~charter.session.ToolSession` for the object that holds this state
across a conversation and projects it onto OpenAI, LangChain and MCP.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

if TYPE_CHECKING:  # pragma: no cover - typing only
    from charter.tool import Tool

__all__ = [
    "SEARCH_TOOL_NAME",
    "DEFAULT_THRESHOLD",
    "DEFAULT_MAX_RESULTS",
    "json_tokens",
    "schema_tokens",
    "parse_query",
    "rank",
    "partition",
    "search_description",
    "SEARCH_PARAMETERS",
]

SEARCH_TOOL_NAME = "ToolSearch"

# Keep a tool resident when its schema is at or under this many tokens.
#
# Zero: nothing is held back on size. See the module docstring for the
# measurement that settled it. Kept as a knob because a hand-written pack may
# have a shape the shipped ones do not, not because the default is in doubt.
DEFAULT_THRESHOLD = 0

# Claude Code's default for the ranked query forms. Exact `select:` is unbounded:
# the caller named what it wants, and truncating that list would silently drop a
# tool the model is about to call.
DEFAULT_MAX_RESULTS = 5

_SEARCH_DESCRIPTION = """\
Fetches full schema definitions for deferred tools so they can be called.

Deferred tools are listed by name in the catalogue below. Until fetched, only \
the name is known — there is no parameter schema, so the tool cannot be \
invoked. This tool takes a query, matches it against the deferred tool list, \
and loads the matched tools' complete definitions. Once a tool has been loaded \
it is callable exactly like any other tool.

Load every tool you expect to need in ONE call — the select query accepts a \
comma-separated list. Do NOT load tools one at a time; each separate call \
wastes a full round-trip.

Query forms:
- "select:gmail__messages_list,gmail__labels_list" — fetch these exact tools by name
- "calendar event" — keyword search, up to max_results best matches
- "+stripe refund" — require "stripe" in the name, rank by remaining terms

Deferred tools (schemas NOT loaded — calling one before loading it will fail):
"""

SEARCH_PARAMETERS: Dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": (
                'Use "select:<tool_name>,<tool_name>" for direct selection, or keywords to search.'
            ),
        },
        "max_results": {
            "type": "integer",
            "description": (
                f"Maximum number of results to return (default: "
                f"{DEFAULT_MAX_RESULTS}). Ignored by select:."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


def json_tokens(value: Any) -> int:
    """Serialised-JSON characters over four.

    The one place the tokens-per-character rule is written down. Two callers
    measure schemas — the deferral threshold here and
    :meth:`Tool.paths(by_cost=True) <charter.Tool.paths>` — and a constant
    duplicated across them would eventually drift, which would make a saving
    reported against one number un-checkable against the other.

    It is a ratio, not a tokeniser. Good enough to compare two schemas, which is
    the only thing either caller does with it.
    """
    return len(json.dumps(value, default=str)) // 4


def schema_tokens(tool: Tool) -> int:
    """The size of a tool's parameter schema, in tokens.

    Measured on the same JSON that goes on the wire — ``$defs`` included, since
    that is what is actually sent. Close enough to compare two tools, which is
    all this is used for.
    """
    return json_tokens(tool.to_json_schema()["parameters"])


def parse_query(query: str) -> Tuple[Optional[List[str]], List[str], List[str]]:
    """``(exact names, required substrings, ranking terms)``.

    ``select:`` is exclusive: naming tools is not a search, so the other two
    lists are empty and nothing is ranked or truncated.
    """
    text = (query or "").strip()
    if text.lower().startswith("select:"):
        names = [n.strip() for n in text[len("select:") :].split(",")]
        return [n for n in names if n], [], []
    required: List[str] = []
    terms: List[str] = []
    for token in re.split(r"\s+", text):
        if not token:
            continue
        if token.startswith("+") and len(token) > 1:
            required.append(token[1:].lower())
        else:
            terms.append(token.lower())
    return None, required, terms


def rank(deferrable: Dict[str, Tool], required: List[str], terms: List[str]) -> List[str]:
    """Names matching every ``+term``, ordered by how well the rest match.

    A hit in the name outweighs one in the description: the catalogue shows
    names, so that is what the query was written against.

    A query with neither a required substring nor a term matches nothing rather
    than everything. ``ToolSearch`` with an empty query — which is also what
    arguments of ``null`` or ``{}`` decay to — otherwise scored every tool zero,
    kept them all, and returned the first ``max_results`` alphabetically, telling
    a model that asked for nothing that five unrelated tools were now loaded.
    """
    if not required and not terms:
        return []

    scored: List[Tuple[int, str]] = []
    for name, tool in deferrable.items():
        lowered = name.lower()
        if any(req not in lowered for req in required):
            continue
        description = (tool.description or "").lower()
        score = sum(2 for t in terms if t in lowered) + sum(1 for t in terms if t in description)
        if terms and score == 0:
            continue
        scored.append((-score, name))
    return [name for _, name in sorted(scored)]


def partition(
    by_name: Dict[str, Tool], *, threshold: int = DEFAULT_THRESHOLD
) -> Tuple[Dict[str, Tool], Dict[str, Tool]]:
    """``(resident, deferrable)``.

    A tool is deferrable when its schema is over ``threshold``, which at the
    default of zero is every tool.
    """
    resident: Dict[str, Tool] = {}
    deferrable: Dict[str, Tool] = {}
    for name, tool in by_name.items():
        if schema_tokens(tool) <= threshold:
            resident[name] = tool
        else:
            deferrable[name] = tool
    return resident, deferrable


def search_description(deferrable: Iterable[str]) -> str:
    """``ToolSearch``'s description: the instructions, then the catalogue.

    Names only. Descriptions would cost about five times as much and are what
    the keyword form exists to replace; the pack is a substring of a qualified
    name, so ``+`` filtering covers grouping without a grouping API.
    """
    return _SEARCH_DESCRIPTION + "\n".join(sorted(deferrable))
