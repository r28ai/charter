"""
OpenAI tool definitions, and the loop that drives them.

No dependency on the ``openai`` package: the definitions are plain dicts in the
shape the chat-completions and responses APIs expect, and :func:`run` asks the
client it is given for ``chat.completions.create``. Any object with that method
works, which is also how it is tested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from charter.session import ToolSession, ToolsLike, view_of
from charter.tool import Tool
from charter.types.errors import CharterError

__all__ = ["to_openai_tool", "to_openai_tools", "run", "RunResult"]


def to_openai_tool(tool: Tool) -> Dict[str, Any]:
    """One :class:`~charter.tool.Tool` as an OpenAI tool definition.

    The ``parameters`` schema is the tool's LLM view, so ``Mode("response_only")``
    fields are absent and ``Format`` fields carry their semantic type.
    """
    return {"type": "function", "function": tool.to_json_schema()}


def to_openai_tools(tools: ToolsLike) -> List[Dict[str, Any]]:
    """Tools as OpenAI tool definitions.

    Accepts a :class:`~charter.session.ToolSession` or a plain iterable. Prefer
    the session, and call this *inside* your loop rather than once above it::

        from charter import ToolSession
        from charter.packs import gmail

        session = ToolSession(gmail.TOOLS)
        response = client.chat.completions.create(
            tools=to_openai_tools(session), ...   # each turn
        )
        result = await session.dispatch(call.function.name, args)

    A session sends the schemas of the tools the model has actually reached for,
    plus a ``ToolSearch`` that loads the rest; the whole of Gmail costs 8 tools
    instead of 23. A plain iterable sends every schema, every turn, because
    there is nowhere in a list to record what a search loaded.

        tools = to_openai_tools(gmail.TOOLS)   # all of them, always

    Names are ``<pack>__<tool>``, because OpenAI has no namespace of its own:
    two packs that both declare ``products_list`` would otherwise send one
    function twice under one name, and the model's call could not be routed
    back. Qualified whatever else is loaded, so adding a pack never renames the
    tools already there.

    Unlike MCP and LangChain, the OpenAI APIs hand a tool call back to *you* to
    execute, so you need the same mapping this used to publish them.
    :func:`~charter.qualified_names` is it::

        from charter import qualified_names

        tools = list(gmail.TOOLS) + list(stripe.TOOLS)
        by_name = qualified_names(tools)          # name -> Tool
        definitions = to_openai_tools(tools)      # the same names

        call = response.choices[0].message.tool_calls[0]
        result = await by_name[call.function.name].ainvoke(
            json.loads(call.function.arguments)
        )
    """
    return [
        {"type": "function", "function": entry}
        if isinstance(entry, dict)
        else {"type": "function", "function": {**entry.to_json_schema(), "name": name}}
        for name, entry in view_of(tools)
    ]


@dataclass
class RunResult:
    """What :func:`run` came back with.

    Attributes
    ----------
    messages:
        The whole transcript, assistant and tool messages included, ready to
        append the next user turn to. The list passed in is not modified.
    content:
        The final assistant text, or ``None`` if the run stopped before the model
        produced one.
    turns:
        Model calls made.
    stop:
        ``"end"`` when the model answered without calling a tool, or
        ``"max_turns"`` when it ran out of turns first.
    """

    messages: List[Any] = field(default_factory=list)
    content: Optional[str] = None
    turns: int = 0
    stop: str = "end"


def _render(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


async def run(
    client: Any,
    *,
    model: str,
    messages: Sequence[Any],
    session: ToolSession,
    max_turns: int = 20,
    **kwargs: Any,
) -> RunResult:
    """Run the tool-calling loop against ``client`` until the model answers.

    Charter ships this rather than documenting it because the loop has one
    requirement that is invisible when you get it wrong: the tool list has to be
    rebuilt on every turn. Build it once above the loop and a tool loaded by
    ``ToolSearch`` never reaches the model, which from outside looks like a model
    that cannot stop searching. Here that is not something to remember.

        from charter import ToolSession
        from charter.adapters.openai import run
        from charter.packs import gmail, stripe

        session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
        result = await run(
            client,                       # openai.AsyncOpenAI, or anything with
            model="gpt-4o",               # chat.completions.create
            messages=[{"role": "user", "content": "..."}],
            session=session,
        )
        print(result.content)

    ``client`` is duck-typed: anything exposing an awaitable
    ``chat.completions.create(model=..., messages=..., tools=...)``. Extra
    keyword arguments (``temperature``, ``tool_choice``, ...) are passed through
    to it unchanged.

    A :class:`~charter.types.errors.CharterError` from a tool becomes that tool's
    result, because its message is written for a model to read and correct itself
    from — a rejected argument, or a tool that has not been loaded yet. Anything
    else propagates: a bug in your handler should not be quietly fed to a model
    as text.

    Parallel tool calls are executed in the order the model returned them, which
    is the order their results are appended in.
    """
    history: List[Any] = list(messages)

    for turn in range(1, max_turns + 1):
        # An empty `tools` is not the same as no `tools`: the OpenAI API
        # rejects `[]`, so a session holding no tools has to omit the argument
        # rather than send an empty one.
        offered = to_openai_tools(session)
        response = await client.chat.completions.create(
            model=model,
            messages=history,
            **({"tools": offered} if offered else {}),
            **kwargs,
        )
        message = response.choices[0].message
        history.append(message)

        calls = getattr(message, "tool_calls", None)
        if not calls:
            return RunResult(
                messages=history,
                content=getattr(message, "content", None),
                turns=turn,
                stop="end",
            )

        for call in calls:
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except ValueError as exc:
                # Malformed JSON from the model is the model's mistake to fix,
                # and it can only fix it if it is told.
                content = f"Arguments were not valid JSON: {exc}"
            else:
                try:
                    content = _render(await session.dispatch(call.function.name, arguments))
                except CharterError as exc:
                    content = str(exc)
            history.append(
                {"role": "tool", "tool_call_id": call.id, "content": content}
            )

    return RunResult(messages=history, content=None, turns=max_turns, stop="max_turns")
