# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""The OData query options Outlook's collections take, and how a page follows the last.

Graph spells its system query options with a ``$`` (``$top``, ``$filter``), which
no case convention reaches from a field name, so each one is declared once here
with its ``WireName`` and Microsoft's description and reused by every tool that
accepts it. A reword in Microsoft's documentation lands everywhere at once.

**Paging is a URL, not a token.** Graph answers a long collection with
``@odata.nextLink``, the whole URL of the next page, and is explicit that it is
opaque: "Don't try to extract the ``$skiptoken`` or ``$skip`` value and use it in
a different request." Messages page with ``$skip``, delta with ``$skiptoken``,
and which one a given request gets is Graph's business. So a paging tool takes
the link back verbatim in ``next_link``, and :func:`follow_next_link` sends the
link's own query string in place of every parameter the tool would otherwise
build.

**The link also names the collection.** Its path says which folder the page is
of, and that is not a detail: the folder is a path parameter, so it is not in
the query, and following a Drafts link with no ``folder_id`` used to fetch the
next page of the *whole mailbox* — while a delta link sent with another folder
is ``410 SyncStateInvalid``, which reads as an expired token. The link's path is
therefore matched against the tool's own routes and its placeholders taken from
there. The host and the route still always come from the tool: a link chooses
*which page of which folder*, never *which endpoint*, and one that matches none
of the tool's routes is refused rather than followed.
"""

from __future__ import annotations

import re
from string import Formatter
from typing import Annotated, Any, Callable, Dict, Optional, Pattern, Sequence, Tuple, Union
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import AfterValidator, BaseModel, Field

from charter.types import Query, ToolValidationError, TransportOverride, WireName

__all__ = [
    "Count",
    "DeltaLink",
    "Expand",
    "Filter",
    "NextLink",
    "OrderBy",
    "Select",
    "follow_next_link",
    "graph_link",
    "query_fields",
]

GRAPH_HOST = "graph.microsoft.com"
GRAPH_VERSION_PREFIX = "/v1.0/"

SELECT_DESCRIPTION = (
    "Use the $select query parameter to return a subset of properties for a resource. "
    "With $select, you can specify a subset or a superset of the default properties. "
    "For example, `from,subject` returns only the from and subject properties."
)
EXPAND_DESCRIPTION = (
    "Use the $expand query string parameter to include the expanded resource or "
    "collection referenced by a single relationship (navigation property) in your results."
)
FILTER_DESCRIPTION = "Use the $filter query parameter to get just a subset of a collection."
ORDERBY_DESCRIPTION = (
    "Use the $orderby query parameter to specify the sort order of the items returned "
    "from Microsoft Graph. The default order is ascending. To sort results in ascending "
    "or descending order, append either `asc` or `desc` to the field name, separated by "
    "a space; for example, `receivedDateTime desc`."
)
COUNT_DESCRIPTION = (
    "Use $count=true to include a count of the total number of items in a collection "
    "alongside the page of data values returned from Microsoft Graph."
)
DELTA_LINK_DESCRIPTION = (
    "The `next_link` or `delta_link` a previous call returned (Graph's "
    "`@odata.nextLink` / `@odata.deltaLink`). A `delta_link` ends a round and starts "
    "the next one, returning only what changed since. Either link carries every "
    "parameter of the first request, the folder included, so when it is set the others "
    "are ignored."
)
NEXT_LINK_DESCRIPTION = (
    "The `next_link` the previous page of this same call returned (Graph's "
    "`@odata.nextLink`), to fetch the page after it. The link carries every parameter "
    "of the first request, the folder included, so when it is set the others are "
    "ignored."
)


def graph_link(value: Optional[str]) -> Optional[str]:
    """A ``next_link`` must be a Graph v1.0 URL — the only kind Graph hands back."""
    if value is None:
        return value
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or parts.hostname != GRAPH_HOST
        or not parts.path.startswith(GRAPH_VERSION_PREFIX)
    ):
        raise ValueError(
            "must be the next_link a previous page returned, unchanged: an "
            f"https://{GRAPH_HOST}{GRAPH_VERSION_PREFIX}... URL"
        )
    return value


Select = Annotated[
    Optional[str],
    Field(None, description=SELECT_DESCRIPTION),
    Query(),
    WireName("$select"),
]
Expand = Annotated[
    Optional[str],
    Field(None, description=EXPAND_DESCRIPTION),
    Query(),
    WireName("$expand"),
]
Filter = Annotated[
    Optional[str],
    Field(None, description=FILTER_DESCRIPTION),
    Query(),
    WireName("$filter"),
]
OrderBy = Annotated[
    Optional[str],
    Field(None, description=ORDERBY_DESCRIPTION),
    Query(),
    WireName("$orderby"),
]
Count = Annotated[
    Optional[bool],
    Field(None, description=COUNT_DESCRIPTION),
    Query(),
    WireName("$count"),
]
NextLink = Annotated[
    Optional[str],
    Field(None, description=NEXT_LINK_DESCRIPTION),
    Query(),
    AfterValidator(graph_link),
]

DeltaLink = Annotated[
    Optional[str],
    Field(None, description=DELTA_LINK_DESCRIPTION),
    Query(),
    AfterValidator(graph_link),
]


def query_fields(model: type[BaseModel]) -> list[str]:
    """Every field ``model`` sends in the query string."""
    return [
        name
        for name, field in model.model_fields.items()
        if any(isinstance(marker, Query) for marker in field.metadata)
    ]


def _link_query(tool_input: BaseModel) -> Optional[Dict[str, Any]]:
    """The query a ``next_link`` stands for, or ``None`` when there is no link."""
    link = getattr(tool_input, "next_link", None)
    if not link:
        return None
    # Every parameter the schema would have built goes; the link's own replace
    # them. A None removes a key from the request rather than sending it empty.
    query: Dict[str, Any] = {name: None for name in query_fields(type(tool_input))}
    query.update(parse_qsl(urlsplit(link).query, keep_blank_values=True))
    return query


# `mailFolders('drafts')` — OData's key syntax, which Graph writes into its
# links for a request that said `mailFolders/drafts`. A quote inside the key is
# doubled, and the quotes and parentheses may arrive percent-encoded.
_KEY_SEGMENT = re.compile(r"([A-Za-z]+)\('((?:[^']|'')*)'\)")
_ENCODED_DELIMITERS = {"%27": "'", "%28": "(", "%29": ")"}
_ENCODED = re.compile("|".join(_ENCODED_DELIMITERS), re.IGNORECASE)
# A link can name the signed-in user rather than say `me`.
_USER = re.compile(r"^users/[^/]+/", re.IGNORECASE)


def _plain_segment(match: re.Match[str]) -> str:
    """``name('key')`` as ``name/key``, with a doubled quote in the key undoubled."""
    key = match.group(2).replace("''", "'")
    return f"{match.group(1)}/{key}"


def _link_path(link: str) -> str:
    """The link's path relative to the version, with OData keys as plain segments."""
    path = urlsplit(link).path[len(GRAPH_VERSION_PREFIX) :]
    path = _ENCODED.sub(lambda m: _ENCODED_DELIMITERS[m.group(0).lower()], path)
    return _USER.sub("me/", _KEY_SEGMENT.sub(_plain_segment, path))


def _route_pattern(template: str) -> Tuple[Pattern[str], Tuple[str, ...]]:
    """``template`` as a pattern whose groups are its placeholders, and their names."""
    pattern, names = "", []
    for literal, name, _, _ in Formatter().parse(template):
        pattern += re.escape(literal)
        if name:
            pattern += f"(?P<{name}>[^/]+)"
            names.append(name)
    return re.compile(pattern, re.IGNORECASE), tuple(names)


def follow_next_link(
    routes: Union[str, Sequence[str]],
) -> Callable[[BaseModel], TransportOverride]:
    """``build_request`` for a paging tool served at ``routes``.

    With no ``next_link`` it changes nothing. With one, the request is the
    link's query at the tool's route the link's path matches, its placeholders
    filled from the link: the folder a page belongs to is in the path, not the
    query, and taking it from the arguments instead fetched another collection.
    Each placeholder must be the field's own name, as every Outlook route's is.
    """
    templates = (routes,) if isinstance(routes, str) else tuple(routes)
    patterns = [_route_pattern(template) for template in templates]
    placeholders = {name for _, names in patterns for name in names}

    def build(tool_input: BaseModel) -> TransportOverride:
        link = getattr(tool_input, "next_link", None)
        query = _link_query(tool_input)
        if not link or query is None:
            return {}
        path = _link_path(link)
        for pattern, names in patterns:
            match = pattern.fullmatch(path)
            if match is None:
                continue
            # Every placeholder the link does not fill is cleared, so a
            # `folder_id` passed beside a whole-mailbox link cannot narrow it.
            filled: Dict[str, Any] = {name: None for name in placeholders}
            filled.update({name: unquote(match.group(name)) for name in names})
            return {"path": filled, "query": query}
        raise ToolValidationError(
            "next_link is not a page of this tool's results: pass the next_link or "
            "delta_link this same tool returned, unchanged."
        )

    return build
