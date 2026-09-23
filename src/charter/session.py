# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

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

A session is also where a :class:`~charter.Mode` is resolved for a whole surface
at once. ``ToolSession(tools, mode="pro")`` puts that label in force on every tool
it holds, *beside* the one the tool shipped with, so one pack serves a plan tier,
a region or a scope without a tool set per value::

    session = ToolSession(reports.TOOLS, mode=plan_of(request.user))

Once, when the session is constructed, and not per call: a schema is already in a
prompt the model is reading. See :meth:`Tool.with_mode <charter.Tool.with_mode>`.
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
from charter.tool import Tool, _check_mode
from charter.types.errors import ToolValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    import httpx

__all__ = ["ToolSession"]


def _max_results(value: Any) -> int:
    """``max_results`` as the integer :meth:`ToolSession.search` needs.

    ``ToolSearch`` is the one tool on the surface whose arguments never pass
    through :func:`~charter.execution.validation.validate_input`, because it is
    answered by the session rather than by a :class:`~charter.tool.Tool`. That
    left a bare ``int(...)`` as the only thing reading them, and a model
    answering an integer parameter with a word — which they do — raised
    ``ValueError``. Every adapter catches
    :class:`~charter.types.errors.CharterError` and nothing else, so it went
    straight past the OpenAI loop and the MCP server instead of coming back to
    the model as a correctable mistake.

    ``None`` and an absent value mean "use the default", which is what the
    schema's optionality already says. A float that is a whole number is
    accepted — JSON has one number type and a model that writes ``5.0`` means
    five. Anything else is the model's to fix.
    """
    if value is None:
        return DEFAULT_MAX_RESULTS
    if isinstance(value, bool):
        # bool is an int in Python and is not one here: `max_results: true`
        # would quietly become 1.
        raise ToolValidationError(
            f"{SEARCH_TOOL_NAME}: max_results must be an integer, not a boolean. "
            f"Omit it for the default of {DEFAULT_MAX_RESULTS}.",
            tool_name=SEARCH_TOOL_NAME,
            errors=[{"loc": ("max_results",), "msg": "expected an integer"}],
        )
    if isinstance(value, int):
        return value or DEFAULT_MAX_RESULTS
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = None
    if number is None or number != int(number):
        raise ToolValidationError(
            f"{SEARCH_TOOL_NAME}: max_results must be an integer, but got {value!r}. "
            f"Omit it for the default of {DEFAULT_MAX_RESULTS}.",
            tool_name=SEARCH_TOOL_NAME,
            errors=[{"loc": ("max_results",), "msg": "expected an integer"}],
        )
    return int(number) or DEFAULT_MAX_RESULTS


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
    mode:
        Put this :class:`~charter.Mode` in force on every tool the session holds,
        beside the label each was declared with. ``None``, the default, leaves
        each tool exactly as it was given. See
        :meth:`Tool.with_mode <charter.Tool.with_mode>`.

        Beside, not instead of: this only ever *adds* the fields carrying the
        label. A pack that uses ``Mode`` to separate ``create`` from ``update``
        keeps that split under every session mode, which is what makes the
        parameter safe to point at a pack you have not read.

        A label, or ``None``. An empty string is refused rather than read as
        ``None``: ``None`` is the *widest* view, since a custom ``Mode`` is
        inert with nothing to match it against, so a tier that came back empty
        would be served every tier's fields.

    Constructing one is also :meth:`Tool.prepare <charter.Tool.prepare>` for
    every tool it is given: partitioning sizes each schema, and sizing one
    derives it. That is about 2.5 seconds for Linear's 128 tools, synchronously,
    on whichever thread builds the session — so build it at startup rather than
    per request. ``progressive=False`` skips the partition and leaves the tools
    to derive on first use.

    **The mode resolves once, here.** Credentials resolve per call, through a
    ContextVar, because the subject can change between two calls of one
    conversation. A schema cannot: it was serialised into a prompt the model is
    still reading, and a tool whose parameters changed underneath a model that
    has already been shown them is a tool it will call wrong. The session is the
    per-conversation object, so this is where the per-conversation answer
    belongs. A surface that has to change means a new session.
    """

    def __init__(
        self,
        tools: Iterable[Tool],
        *,
        progressive: bool = True,
        threshold: int = DEFAULT_THRESHOLD,
        mode: Optional[str] = None,
    ) -> None:
        # Checked here as well as in `Tool`, which is where every mode that
        # resolves anything is checked. A session holding no tools reaches no
        # `Tool.__init__` at all, and accepting a mode nothing would ever apply
        # is how a surface that grows later inherits a label nobody vetted.
        _check_mode(mode, "on ToolSession")
        self.mode = mode
        # Resolved before anything else reads them, so every projection below
        # sees the resolved tools: the partition, `visible`, `search`,
        # `dispatch`, `view_of`, and the egress map a reviewer runs over
        # `session.tools`. There is no second list to keep in step.
        #
        # The `is not None` guard says "leave each tool as it was given",
        # which is not the same as resolving every tool at None: a caller may
        # hand in variants that already carry a deployment's label, and a
        # session that names no surface of its own has no business clearing
        # theirs. For a tool straight from a pack the two agree — `with_mode`
        # returns the tool itself when the label it is given is the one already
        # applied — so what the guard buys there is not having to rely on that.
        self.tools: Dict[str, Tool] = qualified_names(
            tool.with_mode(mode) if mode is not None else tool for tool in tools
        )
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
            ToolValidationError: if the name is not a tool this session holds, is
                a deferred tool that has not been loaded, or is ``ToolSearch``
                called with arguments that do not satisfy its own schema. All
                three messages are written for the model to read and act on.
        """
        args = arguments or {}
        if name == SEARCH_TOOL_NAME and self.deferrable:
            result = self.search(str(args.get("query", "")), _max_results(args.get("max_results")))
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
            f"Unknown tool: {name!r}. Available: {', '.join(sorted(self.visible())) or '(none)'}.",
            tool_name=name,
        )

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Forget what has been loaded, for reuse across conversations."""
        self.loaded.clear()

    def __repr__(self) -> str:
        mode = f", mode={self.mode!r}" if self.mode is not None else ""
        return (
            f"ToolSession({len(self.tools)} tools, {len(self.resident)} resident, "
            f"{len(self.loaded)}/{len(self.deferrable)} loaded{mode})"
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
