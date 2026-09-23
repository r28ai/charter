# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Qualified tool names, for when several packs share one tool surface.

A tool's ``name`` is what the API calls the endpoint, and it stays that way.
That is the convention every surface Charter targets already follows: an MCP
server publishes plain names and the *host* composes ``mcp__<server>__<tool>``
from the server it was configured with; OpenAI constrains names to
``[A-Za-z0-9_-]{1,64}`` and defines no namespace; LangChain leaves it to the
caller. Qualification belongs to whoever *assembles* tools into one namespace, and this
module is the one convention they should all reach for rather than each
inventing their own. Charter's own adapters call it, so a pack is named the same
way whether it is reached inline, through LangChain, or over MCP.

An MCP host composes ``mcp__<server>__<tool>`` on top, which is why the MCP
entry point names its server ``charter`` rather than after a pack: the result
reads ``mcp__charter__gcalendar__events_list``, each segment saying a different
thing, instead of repeating the pack twice.

That is a budget and not only a preference. The host builds ``<server>`` from
the key the server was *configured under*, and the whole composed name has to
fit the 64 characters OpenAI allows a function name. One server holding every
pack peaks at 61; naming a server after the pack it serves — ``charter-gsheets``
— spends eight more on saying ``gsheets`` a second time and puts three names
over. So ``--pack`` takes a list, and the setup page configures one server.

**Always, and identically.** A tool's published name is a function of that tool
alone, never of what happens to sit beside it. Qualifying only when a second
pack shows up would rename every tool in the first the day someone adds one,
breaking saved prompts, allow-lists, logged traces and eval fixtures in silence.
MCP has this property — a server publishes the same names whatever else is
installed, and the host prefixes with the server — and it is the property worth
copying.

**All of them or none of them.** :func:`qualified_names` never qualifies "just
the collisions". A surface where ``stripe__products_list`` sits beside a bare
``balance_retrieve`` makes the pack a substring of some names and not others, so
any filter over it — a ``+stripe`` in a tool search, a log grep, an
allow-list — silently misses the unqualified half. A filter that works on most
names is worse than none, because nothing tells you which half you got.

**Why the doubled underscore.** Tool names contain single underscores, so
``stripe_products_list`` cannot be split back into pack and tool, while
``stripe__products_list`` can. MCP doubles it for the same reason.

**A report is not a tool surface.** :func:`report_key` is the one place that
falls back to a bare name, for the dict an audit artifact keys by, and it is not
an exception to the rule above. The rule's reason is that a filter over a
half-qualified *surface* misses the unqualified half in silence. Nothing filters
or dispatches on a report key: each row carries its own ``pack``, and the
alternative was refusing to map a tool built without one, which is the tool the
quickstart teaches. What both keep is the property the rule is really about,
that the name is a function of the tool alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Dict, Union

from charter.types.errors import DeclarationError

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime, fine for typing
    from charter.tool import Tool

__all__ = ["SEPARATOR", "check_pack", "qualified_name", "qualified_names", "report_key"]

SEPARATOR = "__"

# What a name may contain, taken from the strictest surface Charter targets:
# OpenAI accepts `^[a-zA-Z0-9_-]{1,64}$` for a function name and nothing else. A
# dot or a space produces a name that is rejected there and unusable over MCP,
# so it is refused where it is declared rather than at the first call.
_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def _check(part: str, kind: str, tool_name: str) -> None:
    if not _SAFE.match(part):
        raise DeclarationError(
            f"{kind} {part!r} (on tool {tool_name!r}) is not usable in a tool name. "
            f"Use letters, digits, hyphen and underscore only — OpenAI accepts "
            f"[A-Za-z0-9_-] and nothing else.",
            docs="tools/naming",
        )
    if SEPARATOR in part:
        raise DeclarationError(
            f"{kind} {part!r} (on tool {tool_name!r}) contains {SEPARATOR!r}, which is "
            f"what separates the pack from the tool. A qualified name has to split "
            f"back into its two halves, and this one would not.",
            docs="tools/naming",
        )


def check_pack(pack: str, where: str) -> None:
    """Refuse a pack label at the factory, before any tool is built on it.

    :func:`qualified_name` checks the same thing, but it runs when an adapter
    publishes the tool, which is several steps and one import away from the line
    that has to change. The factory knows the label the moment it is handed one,
    and ``where`` names the call rather than a tool the reader has not written
    yet.
    """
    if not isinstance(pack, str) or not pack.strip():
        raise DeclarationError(
            f"{where} needs a non-empty pack label. It is the namespace every tool "
            f"built here is published under — `<pack>__<tool>` — so two APIs that "
            f"both declare `products_list` stay distinguishable.",
            docs="tools/naming",
        )
    if not _SAFE.match(pack):
        raise DeclarationError(
            f"Pack {pack!r} ({where}) is not usable in a tool name. Use letters, "
            f"digits, hyphen and underscore only — OpenAI accepts [A-Za-z0-9_-] "
            f"and nothing else.",
            docs="tools/naming",
        )
    if SEPARATOR in pack:
        raise DeclarationError(
            f"Pack {pack!r} ({where}) contains {SEPARATOR!r}, which is what separates "
            f"the pack from the tool. A qualified name has to split back into its two "
            f"halves, and this one would not.",
            docs="tools/naming",
        )


def qualified_name(tool: Tool) -> str:
    """``<pack>__<name>``.

    Raises:
        DeclarationError: if the tool declares no ``pack``; if either half is
            not usable in a tool name; or if either half contains ``__``, which
            would leave the result impossible to split back apart.

    Falling back to the bare name for a tool with no pack would produce the
    half-qualified surface this module exists to prevent, and silently.
    """
    if not tool.pack:
        raise DeclarationError(
            f"Tool {tool.name!r} declares no pack, so it cannot be qualified. "
            f"Pass pack=... to the tool factory, or to Tool(...) directly.",
            docs="tools/naming",
        )
    _check(tool.pack, "Pack", tool.name)
    _check(tool.name, "Tool name", tool.name)
    return f"{tool.pack}{SEPARATOR}{tool.name}"


def report_key(tool: Tool) -> str:
    """The row a tool gets in an audit artifact: ``<pack>__<tool>``, or its name.

    :func:`egress_map <charter.egress_map>` and
    :func:`conflict_map <charter.conflict_map>` both key a dict by tool, and both
    used to key it by the bare name. Across the fifteen shipped packs sixteen
    names collide, so the egress map of one assembled surface held 529 rows for
    549 tools and said nothing about the twenty it dropped. A report that loses
    rows is worse than no report: the reviewer cannot tell by reading it, which
    is the one failure mode an audit artifact must not have.

    Qualified wherever the tool declares a pack, so a row greps against a trace
    and against the name the adapters publish. A tool with no pack keeps its bare
    name, which :func:`qualified_name` refuses to do and is right to refuse: a
    half-qualified *tool surface* makes the pack a substring of some names and
    not others, so a filter over it misses the rest in silence. A report is not a
    tool surface. Nothing dispatches on these keys, the pack is carried in the
    row beside the name, and refusing would put the artifact out of reach of the
    hand-built tool the quickstart teaches. What both rules keep is the part that
    matters: the key is a function of the tool alone, never of what sits beside
    it.

    Callers must still refuse a duplicate rather than overwrite one. Two pack-less
    tools can share a name, and that is the case this cannot resolve alone.
    """
    return qualified_name(tool) if tool.pack else tool.name


def _rows(tools: Union[Iterable[Tool], Mapping[str, Tool]]) -> Iterable[Tool]:
    """The tools of a report, whether the surface came as a list or as a map.

    A surface assembled for a conversation is a :class:`~charter.ToolSession`,
    and the thing on it worth auditing is ``session.tools`` — which is a dict,
    keyed by the published name. Iterating one yields *strings*, so the call the
    mode docs send a reviewer to made both audit maps fail on
    ``'str' object has no attribute 'pack'``, which names neither the mistake nor
    the fix. Taking the values is what the reader meant in every case: a report
    is keyed by :func:`report_key`, so the mapping's own keys are discarded
    either way.
    """
    return tools.values() if isinstance(tools, Mapping) else tools


def _duplicate_row(key: str, tool: Tool) -> DeclarationError:
    """The refusal both audit maps raise rather than overwrite a row.

    One message, because two would drift: the rule is the same rule in both
    places, and the reader hitting it is the same reader.
    """
    fix = (
        "A pack cannot declare the same tool name twice."
        if tool.pack
        else "Declare a pack on each, with pack=... on the tool factory."
    )
    return DeclarationError(
        f"Two tools report under {key!r}, so one would overwrite the other and the "
        f"map would hold fewer rows than the tools it was handed. {fix}",
        docs="tools/naming",
    )


def qualified_names(tools: Iterable[Tool]) -> Dict[str, Tool]:
    """Every tool under ``<pack>__<name>``, keyed by the qualified name.

    Raises:
        DeclarationError: if a tool has no pack, or if two tools qualify to the
            same name — which means one pack declared the same tool twice, and
            a dict would otherwise drop one without saying so.
    """
    out: Dict[str, Tool] = {}
    for tool in tools:
        name = qualified_name(tool)
        if name in out:
            raise DeclarationError(
                f"Two tools qualify to {name!r}; a pack cannot declare the same tool name twice.",
                docs="tools/naming",
            )
        out[name] = tool
    return out
