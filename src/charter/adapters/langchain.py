"""
LangChain adapter (extra ``[langchain]``).

``to_langchain(tool)`` returns a ``StructuredTool`` whose ``args_schema`` is the
Charter LLM view and whose coroutine is ``Tool.ainvoke``. Execution stays in Charter;
LangChain only supplies the calling convention.

For an agent, use :class:`CharterMiddleware`. ``create_agent`` binds its tools
once, and a :class:`~charter.session.ToolSession` grows, so the two are joined
where LangChain provides for it rather than by rebuilding the agent::

    from langchain.agents import create_agent
    from charter import ToolSession
    from charter.adapters.langchain import CharterMiddleware
    from charter.packs import gmail, stripe

    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    agent = create_agent(model, tools=[], middleware=[CharterMiddleware(session)])
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from charter.discovery import DEFAULT_MAX_RESULTS, SEARCH_TOOL_NAME
from charter.execution.validation import format_validation_error
from charter.session import ToolSession, ToolsLike, view_of
from charter.tool import Tool
from charter.types.errors import CharterError, ToolValidationError

__all__ = ["to_langchain", "to_langchain_tools", "CharterMiddleware"]

_INSTALL_HINT = (
    "The LangChain adapter needs langchain-core. Install it with: pip install 'charter[langchain]'"
)


def _require_structured_tool():
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(_INSTALL_HINT) from exc
    return StructuredTool


def to_langchain(tool: Tool, *, name: str | None = None) -> Any:
    """Wrap a Charter :class:`~charter.tool.Tool` as a LangChain ``StructuredTool``.

    Validation errors are returned as the tool result rather than raised, which
    is what LangChain agents expect: the message is already written for a model
    to read and correct itself from. Everything else propagates.
    """
    StructuredTool = _require_structured_tool()

    async def _run(**kwargs: Any) -> Any:
        try:
            return await tool.ainvoke(kwargs)
        except ToolValidationError as exc:
            # Hand the model its own mistake instead of crashing the agent loop.
            return str(exc)
        except CharterError as exc:
            return f"Error: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=name or tool.name,
        description=tool.description,
        args_schema=tool.llm_schema(),
        # LangChain validates against args_schema *before* the coroutine runs, so
        # a missing field never reaches _run. Without this, the raw pydantic error
        # escapes and the agent framework wraps it in its own template, dumping
        # the whole kwargs payload back at the model. This renders it the same way
        # ToolValidationError does.
        handle_validation_error=format_validation_error,
    )


def _search_tool(session: Any, definition: Dict[str, Any]) -> Any:
    """``ToolSearch`` as a LangChain tool, loading into ``session``."""
    StructuredTool = _require_structured_tool()

    async def _run(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
        return json.dumps(session.search(query, max_results), ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=_run,
        name=definition["name"],
        description=definition["description"],
    )


def to_langchain_tools(tools: ToolsLike) -> List[Any]:
    """Wrap tools for LangChain.

    Names are ``<pack>__<tool>``. LangChain resolves a tool call by name against
    the list it was given, so two packs both declaring ``products_list`` would
    leave it picking whichever it saw first. Qualified whatever else is loaded,
    so adding a pack never renames the tools already there.

    Given a :class:`~charter.session.ToolSession` this returns what the model can
    see *now*, plus a ``ToolSearch`` that loads the rest. LangChain binds tools
    to a model at graph-construction time, so a growing list means rebinding: in
    LangGraph, call this inside the model node rather than passing a list to
    ``create_react_agent`` once. Given a plain iterable
    this returns everything, which is what a prebuilt agent expects.
    """
    return [
        _search_tool(tools, entry) if isinstance(entry, dict) else to_langchain(entry, name=name)
        for name, entry in view_of(tools)
    ]


def _needs_async(hook: str) -> CharterError:
    """The error a synchronous agent run gets, at the first model call."""
    return CharterError(
        f"Charter tools are asynchronous, so an agent holding them has to be run "
        f"with `await agent.ainvoke(...)` rather than `agent.invoke(...)`. "
        f"(CharterMiddleware.{hook} was reached, which only a synchronous run "
        f"does.) Tool.ainvoke goes down to httpx.AsyncClient and has no blocking "
        f"form; running it from synchronous code would deadlock inside an event "
        f"loop, which is where an agent usually is."
    )


def _require_middleware():
    try:
        from langchain.agents.middleware import AgentMiddleware
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "CharterMiddleware needs the langchain package (not just langchain-core). "
            "Install it with: pip install langchain"
        ) from exc
    return AgentMiddleware


def CharterMiddleware(session: ToolSession) -> Any:  # noqa: N802 - it is a class
    """A :class:`~charter.session.ToolSession` as LangChain agent middleware.

    ``create_agent`` binds its tool list when the graph is built, and a session's
    list grows as ``ToolSearch`` loads things. LangChain provides for exactly
    this — its docs call it runtime tool registration, and name MCP servers as
    the case — through two hooks, and both are needed:

    * ``wrap_model_call`` puts this turn's tools on the request, so a tool loaded
      on the previous turn is offered on this one.
    * ``wrap_tool_call`` supplies the tool to execute, because the agent has no
      way to run something that was not in its original list.

    So the agent is built with no Charter tools at all and the middleware
    provides them::

        agent = create_agent(model, tools=[], middleware=[CharterMiddleware(session)])
        await agent.ainvoke({"messages": [{"role": "user", "content": "..."}]})

    Charter tools sit alongside anything passed to ``tools=``: this only ever
    adds to the request and only claims calls whose names it recognises.

    A function rather than a class statement so that importing this module
    without the ``langchain`` package still works — ``to_langchain_tools`` needs
    only ``langchain-core``, and a class body cannot defer its base.
    """
    AgentMiddleware = _require_middleware()

    class _CharterMiddleware(AgentMiddleware):  # type: ignore[misc, valid-type]
        """Holds the session and rebuilds the tool list on every model call."""

        def __init__(self) -> None:
            super().__init__()
            self.session = session
            # Wrapping rebuilds an args_schema from pydantic, so do it once per
            # tool rather than once per turn. Keyed by the published name.
            self._wrapped: Dict[str, Any] = {}

        def _tools(self) -> List[Any]:
            out: List[Any] = []
            for name, entry in view_of(self.session):
                if name not in self._wrapped:
                    self._wrapped[name] = (
                        _search_tool(self.session, entry)
                        if isinstance(entry, dict)
                        else to_langchain(entry, name=name)
                    )
                out.append(self._wrapped[name])
            return out

        def _claim(self, request: Any) -> Any:
            """``request`` with the tool to run attached, if this session owns it."""
            name = request.tool_call["name"]
            if name != SEARCH_TOOL_NAME and name not in self.session.visible():
                return request
            self._tools()  # make sure the wrapper exists
            tool = self._wrapped.get(name)
            return request if tool is None else request.override(tool=tool)

        # The synchronous hooks refuse rather than work.
        #
        # A Charter tool executes through `Tool.ainvoke`, which is async all the
        # way down to httpx.AsyncClient, so `to_langchain` builds a
        # StructuredTool with a coroutine and no sync function. Driven with
        # `agent.invoke(...)`, LangChain calls these hooks, binds the tools,
        # spends the model call, and only then raises "StructuredTool does not
        # support sync invocation" — an error that names nothing the caller can
        # act on and arrives after the expensive part.
        #
        # Implementing them by running the coroutine would mean sync-over-async:
        # `asyncio.run` raises inside a running loop, which is where an agent
        # usually is. Refusing at the first model call costs nothing and says
        # what to do instead.

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            raise _needs_async("wrap_model_call")

        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            return await handler(request.override(tools=[*request.tools, *self._tools()]))

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            raise _needs_async("wrap_tool_call")

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            return await handler(self._claim(request))

    return _CharterMiddleware()
