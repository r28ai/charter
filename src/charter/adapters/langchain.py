# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

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

import dataclasses
import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel

from charter.discovery import DEFAULT_MAX_RESULTS, SEARCH_TOOL_NAME
from charter.execution.validation import format_validation_error
from charter.session import ToolSession, ToolsLike, view_of
from charter.tool import Tool
from charter.types.errors import CharterError, ToolValidationError, unexpected_failure_text

__all__ = ["to_langchain", "to_langchain_tools", "CharterMiddleware"]

logger = logging.getLogger("charter")

_INSTALL_HINT = "The LangChain adapter needs langchain-core. Install it with: pip install 'charter-ai[langchain]'"


def _require_structured_tool():
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(_INSTALL_HINT) from exc
    return StructuredTool


def to_langchain(
    tool: Tool, *, name: str | None = None, context: Optional[Mapping[str, Any]] = None
) -> Any:
    """Wrap a Charter :class:`~charter.tool.Tool` as a LangChain ``StructuredTool``.

    A failed call is returned as the tool result rather than raised, which is
    what LangChain agents expect. A validation error is the model's own mistake,
    already written for it to correct; any other :class:`CharterError` is handed
    back as ``Error: ...``. Anything that is not a Charter error — a bug in a
    response handler or a credential provider — is logged with its traceback on
    the ``charter`` logger, and the model is told the tool failed on its side
    and that changing the call will not help. A tool failing ends the call,
    never the agent.

    ``context`` is the host's per-call values, handed to every call this tool
    makes, for its ``FromContext`` fields and rules (see
    :meth:`~charter.tool.Tool.ainvoke`). Wrap per request when it varies by user.
    Inside an agent, :class:`CharterMiddleware` reads the agent's own context
    instead, call by call.
    """
    StructuredTool = _require_structured_tool()
    published = name or tool.name

    return StructuredTool.from_function(
        coroutine=_runner(tool, published, context),
        name=published,
        description=tool.description,
        args_schema=tool.llm_schema(),
        # LangChain validates against args_schema *before* the coroutine runs, so
        # a missing field never reaches _run. Without this, the raw pydantic error
        # escapes and the agent framework wraps it in its own template, dumping
        # the whole kwargs payload back at the model. This renders it the same way
        # ToolValidationError does.
        handle_validation_error=format_validation_error,
    )


def _runner(tool: Tool, published: str, context: Optional[Mapping[str, Any]]) -> Any:
    """The coroutine a LangChain tool runs: ``tool.ainvoke``, failures as results."""

    async def _run(**kwargs: Any) -> Any:
        try:
            return await tool.ainvoke(kwargs, context=context)
        except ToolValidationError as exc:
            # Hand the model its own mistake instead of crashing the agent loop.
            return str(exc)
        except CharterError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.exception("charter: tool %s raised %s", published, type(exc).__name__)
            return f"Error: {unexpected_failure_text(published, exc)}"

    return _run


def _as_context(value: Any) -> Optional[Mapping[str, Any]]:
    """An agent's run context, as the mapping Charter reads ``context`` as.

    LangChain types it with the agent's ``context_schema``, which its docs write
    as a dataclass, and which may as well be a ``TypedDict`` or a pydantic model.
    Read one level deep: a field holding a model stays that model, as it would
    in a dict the host built by hand.
    """
    if value is None or isinstance(value, Mapping):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in dataclasses.fields(value)}
    if isinstance(value, BaseModel):
        return dict(value)
    raise TypeError(
        f"The agent's context is a {type(value).__name__}. Charter reads it as a mapping, "
        "a dataclass or a pydantic model, keyed by the names its FromContext fields use."
    )


def _search_tool(session: Any, definition: Dict[str, Any]) -> Any:
    """``ToolSearch`` as a LangChain tool, loading into ``session``."""
    StructuredTool = _require_structured_tool()

    async def _run(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> str:
        try:
            return json.dumps(session.search(query, max_results), ensure_ascii=False)
        except CharterError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.exception("charter: %s raised %s", definition["name"], type(exc).__name__)
            return f"Error: {unexpected_failure_text(definition['name'], exc)}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=definition["name"],
        description=definition["description"],
    )


def to_langchain_tools(
    tools: ToolsLike, *, context: Optional[Mapping[str, Any]] = None
) -> List[Any]:
    """Wrap tools for LangChain.

    Names are ``<pack>_<tool>``. LangChain resolves a tool call by name against
    the list it was given, so two packs both declaring ``products_list`` would
    leave it picking whichever it saw first. Qualified whatever else is loaded,
    so adding a pack never renames the tools already there.

    Given a :class:`~charter.session.ToolSession` this returns what the model can
    see *now*, plus a ``ToolSearch`` that loads the rest. LangChain binds tools
    to a model at graph-construction time, so a growing list means rebinding: in
    LangGraph, call this inside the model node rather than passing a list to
    ``create_react_agent`` once. Given a plain iterable
    this returns everything, which is what a prebuilt agent expects.

    ``context`` is handed to every call any of them makes, as for
    :func:`to_langchain`.
    """
    return [
        _search_tool(tools, entry)
        if isinstance(entry, dict)
        else to_langchain(entry, name=name, context=context)
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

    The agent's own context reaches every Charter call, for the tools'
    ``FromContext`` fields and rules. It is whatever the run was given, read call
    by call, so one agent serves every user::

        await agent.ainvoke(messages, context=Context(customer_id=user.customer_id))

    A dataclass, a ``TypedDict`` or a pydantic model all work.

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
            """``request`` with the tool to run attached, if this session owns it.

            A Charter tool is handed this run's context. The wrapper is built once
            per tool and shared by every run, so the context is bound to a copy
            for this one call rather than stored on it: two users' runs share the
            middleware, and a value set on the wrapper would cross between them.
            """
            name = request.tool_call["name"]
            visible = self.session.visible()
            if name != SEARCH_TOOL_NAME and name not in visible:
                return request
            self._tools()  # make sure the wrapper exists
            tool = self._wrapped.get(name)
            if tool is None:
                return request
            context = _as_context(getattr(getattr(request, "runtime", None), "context", None))
            if context is not None and name in visible:
                tool = tool.model_copy(update={"coroutine": _runner(visible[name], name, context)})
            return request.override(tool=tool)

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
