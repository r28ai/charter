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

An MCP host composes ``mcp__<server>__<tool>`` on top, which is why
``charter-mcp`` names its server ``charter`` rather than after a pack: the
result reads ``mcp__charter__gcalendar__events_list``, each segment saying a
different thing, instead of repeating the pack twice.

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
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Dict

from charter.types.errors import DeclarationError

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime, fine for typing
    from charter.tool import Tool

__all__ = ["SEPARATOR", "qualified_name", "qualified_names"]

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
                f"Two tools qualify to {name!r}; a pack cannot declare the same "
                f"tool name twice.",
                docs="tools/naming",
            )
        out[name] = tool
    return out
