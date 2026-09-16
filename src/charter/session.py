"""
A tool surface that grows: what the model can see, right now.

Charter's adapters are pure projections — a list of tools in, a list of
definitions out. That is the right shape for a fixed tool set and the wrong one
for a growing one, because a projection has nowhere to remember what has been
loaded. MCP has a session and so does an Inspect ``ToolSource``; the OpenAI and
LangChain APIs hand you a list and let you own the loop.

:class:`ToolSession` is that missing piece. You hold one, and hand it to whatever
runs the loop::

    from charter import ToolSession
    from charter.adapters.openai import run
    from charter.packs import gmail, stripe

    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    result = await run(client, model="gpt-4o", messages=messages, session=session)

The loop has to rebuild its tool list on every turn or a loaded tool never
reaches the model, so Charter ships the loops rather than asking for that in
writing: ``run()`` for the OpenAI APIs, ``CharterMiddleware`` for LangChain,
and the MCP server for MCP, where the protocol carries it. The projections
underneath are public and you can drive them yourself, but nothing has to.

Nothing about the contract changes. A loaded tool is the same fully typed tool
it would have been if it had never been deferred; there is no generic
``execute(slug, arguments)`` here, and no tool is ever offered with a schema it
does not have. The session only decides *when* each schema goes out.

Every tool is deferred, whatever its size and however few there are, which is
the line Claude Code draws around configured tools. Pass ``progressive=False``
to send every schema up front instead.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple, Union

from charter.discovery import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_THRESHOLD,
    SEARCH_PARAMETERS,
    SEARCH_TOOL_NAME,
    parse_query,
    partition,
    rank,
    search_description,
)
from charter.naming import qualified_names
from charter.tool import Tool
from charter.types.errors import ToolValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

__all__ = ["ToolSession"]


class ToolSession:
    """The tools of one conversation, and which of their schemas have been sent.

    Parameters
    ----------
    tools:
        The Charter tools this conversation may reach. Named as
        ``<pack>__<tool>`` throughout, by :func:`~charter.qualified_names`.
    progressive:
        ``True`` (the default) defers every schema. ``False`` sends them all up
        front and never offers ``ToolSearch``.
    threshold:
        Keep a tool resident when its schema is at or under this many tokens.
        Zero by default, so nothing is. See :mod:`charter.discovery` for the
        measurement behind that.

    Constructing one is also :meth:`Tool.prepare <charter.Tool.prepare>` for
    every tool it is given: partitioning sizes each schema, and sizing one
    derives it. That is about 2.5 seconds for Linear's 128 tools, synchronously,
    on whichever thread builds the session — so build it at startup rather than
    per request. ``progressive=False`` skips the partition and leaves the tools
    to derive on first use.
    """

    def __init__(
        self,
        tools: Iterable[Tool],
        *,
        progressive: bool = True,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> None:
        self.tools: Dict[str, Tool] = qualified_names(tools)
        self.threshold = threshold

        if progressive:
            self.resident, self.deferrable = partition(self.tools, threshold=threshold)
        else:
            self.resident, self.deferrable = dict(self.tools), {}
        # A list, not a set: load order is what keeps the tool list a growing
        # prefix rather than a resorted one. A prompt whose tools reorder on
        # every load invalidates the cache that makes the prefix cheap.
        self.loaded: List[str] = []

    # ------------------------------------------------------------------
    # what the model sees
    # ------------------------------------------------------------------

    @property
    def progressive(self) -> bool:
        """Whether anything is being deferred at all."""
        return bool(self.deferrable)

    def visible(self) -> Dict[str, Tool]:
        """The tools the model may call this turn, in the order to send them.

        Resident tools first, in declaration order, then whatever ``ToolSearch``
        has loaded, in the order it loaded them. Both halves are append-only, so
        each turn's tool list extends the last one instead of reshuffling it and
        the cached prompt prefix survives.

        A deferred tool that has not been loaded is absent — not present with an
        empty schema. Offering a tool the model cannot successfully call is how
        it learns to guess arguments.
        """
        out = dict(self.resident)
        for name in self.loaded:
            tool = self.deferrable.get(name)
            if tool is not None:
                out[name] = tool
        return out

    def offers_search(self) -> bool:
        """Whether ``ToolSearch`` should be on the tool list this turn.

        Dropped once everything is loaded: at that point the catalogue is dead
        weight in a prompt that is already carrying every schema.
        """
        return bool(self.deferrable) and not set(self.deferrable) <= set(self.loaded)

    def search_definition(self) -> Dict[str, Any]:
        """``ToolSearch`` as an OpenAI-shaped function definition.

        The catalogue lists every deferrable tool, including the loaded ones,
        rather than shrinking as they load. It sits in the prompt prefix, and
        rewriting it each turn would invalidate the cache that makes the prefix
        cheap.

        Deep-copied, because this is handed to callers who edit tool definitions
        — adding ``strict``, rewording a description — and
        :data:`~charter.discovery.SEARCH_PARAMETERS` is one dict for the whole
        process. Returning it by reference made every session in the process
        share one mutable object, which is the same defect as a pack's tools
        sharing one ``on_call``.
        """
        return {
            "name": SEARCH_TOOL_NAME,
            "description": search_description(self.deferrable),
            "parameters": deepcopy(SEARCH_PARAMETERS),
        }

    # ------------------------------------------------------------------
    # loading and calling
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = DEFAULT_MAX_RESULTS) -> Dict[str, Any]:
        """Run one ``ToolSearch`` query, loading what it matched.

        Returns the result the model reads: what was loaded, and — when a name
        was wrong or nothing matched — the catalogue to pick from instead.
        """
        exact, required, terms = parse_query(query)
        if exact is not None:
            found = [n for n in exact if n in self.deferrable]
            missing = sorted(set(exact) - set(found))
        else:
            found = rank(self.deferrable, required, terms)[: max(1, max_results)]
            missing = []

        for name in found:
            if name not in self.loaded:
                self.loaded.append(name)
        out: Dict[str, Any] = {
            "loaded": sorted(found),
            "note": "These tools are now available with their full parameters.",
        }
        if missing:
            out["unknown"] = {"names": missing, "available": sorted(self.deferrable)}
        if not found and not missing:
            out["note"] = (
                "No tool matched. Name one exactly with select:<name>, or search "
                "with a keyword from the list."
            )
            out["available"] = sorted(self.deferrable)
        return out

    async def dispatch(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Any:
        """Route one tool call from the model.

        ``ToolSearch`` loads tools and returns its result as JSON; anything else
        goes to :meth:`~charter.tool.Tool.ainvoke` unchanged.

        ``client`` is an ``httpx.AsyncClient`` to reuse for this call, passed
        through to ``ainvoke`` unchanged. A loop you drive yourself can hold one
        open across a run rather than paying a TLS handshake per tool call.

        Raises:
            ToolValidationError: if the name is not a tool this session holds, or
                is a deferred tool that has not been loaded. Both messages are
                written for the model to read and act on.
        """
        args = arguments or {}
        if name == SEARCH_TOOL_NAME and self.deferrable:
            result = self.search(
                str(args.get("query", "")),
                int(args.get("max_results") or DEFAULT_MAX_RESULTS),
            )
            return json.dumps(result, ensure_ascii=False)

        tool = self.visible().get(name)
        if tool is not None:
            return await tool.ainvoke(args, client=client)

        if name in self.deferrable:
            raise ToolValidationError(
                f"{name!r} is deferred and its schema is not loaded, so it cannot be "
                f"called yet. Load it first with {SEARCH_TOOL_NAME}: "
                f'query="select:{name}".',
                tool_name=name,
            )
        raise ToolValidationError(
            f"Unknown tool: {name!r}. Available: "
            f"{', '.join(sorted(self.visible())) or '(none)'}.",
            tool_name=name,
        )

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Forget what has been loaded, for reuse across conversations."""
        self.loaded.clear()

    def __repr__(self) -> str:
        return (
            f"ToolSession({len(self.tools)} tools, {len(self.resident)} resident, "
            f"{len(self.loaded)}/{len(self.deferrable)} loaded)"
        )


# The shape every adapter accepts.
ToolsLike = Union[ToolSession, Iterable[Tool]]

# One entry of a tool surface: a name, and either the Charter tool behind it or
# the ``ToolSearch`` definition.
Entry = Tuple[str, Union[Tool, Dict[str, Any]]]


def view_of(tools: ToolsLike) -> List[Entry]:
    """The tool surface to publish now, in the order to publish it.

    The one place the adapters agree on what "a tool list" means, and on the
    order, which is not cosmetic: resident tools first, then ``ToolSearch``, then
    whatever has been loaded, in load order. Every fixed part comes before every
    growing part, so each turn's tool list *extends* the previous one and the
    cached prompt prefix survives. Put the search after the loaded tools instead
    and every single load shifts it, re-serialising the prefix each turn.

    A plain iterable publishes every tool with every schema, because a bare list
    has nowhere to record what a search loaded: a stateless projection cannot
    grow, and a ``ToolSearch`` whose results evaporate is worse than none. That
    is the whole reason :class:`ToolSession` exists.
    """
    if not isinstance(tools, ToolSession):
        return list(qualified_names(tools).items())

    entries: List[Entry] = list(tools.resident.items())
    if tools.offers_search():
        entries.append((SEARCH_TOOL_NAME, tools.search_definition()))
    for name in tools.loaded:
        tool = tools.deferrable.get(name)
        if tool is not None:
            entries.append((name, tool))
    return entries
