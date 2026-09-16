"""
The OpenAI loop Charter ships.

The loop has one requirement that is invisible when you get it wrong: its tool
list has to be rebuilt on every turn, or a tool loaded by ``ToolSearch`` never
reaches the model. These pin that it is rebuilt, and that everything a model can
get wrong comes back to it as something it can read.

The client is duck-typed, so the fake here is the whole dependency.
"""

from __future__ import annotations

import json
import types

import httpx
import pytest
import respx

from charter import ToolSession
from charter.adapters.openai import RunResult, run
from charter.auth import StaticTokenProvider
from charter.packs import gmail, stripe


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    for var in ("GOOGLE_ACCESS_TOKEN", "STRIPE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    gmail.configure(StaticTokenProvider("t"))
    stripe.configure(api_key="sk_test_x")


def message(content=None, tool_calls=None):
    return types.SimpleNamespace(content=content, tool_calls=tool_calls)


def tool_call(call_id, name, arguments):
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments)
    return types.SimpleNamespace(
        id=call_id, function=types.SimpleNamespace(name=name, arguments=arguments)
    )


class FakeClient:
    """Replays scripted messages and records the tools it was offered each turn."""

    def __init__(self, script):
        self.script = list(script)
        self.offered: list[list[str]] = []
        self.kwargs: list[dict] = []

    @property
    def chat(self):
        return types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    async def _create(self, *, model, messages, tools=None, **kwargs):
        self.offered.append([t["function"]["name"] for t in tools or []])
        self.kwargs.append({"tools": tools, **kwargs} if tools is not None else kwargs)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=self.script.pop(0))]
        )


USER = [{"role": "user", "content": "go"}]


async def test_a_loaded_tool_is_offered_on_the_next_turn():
    """The whole point. Turn one is the catalogue; turn two has the real tool."""
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([
        message(tool_calls=[tool_call("1", "ToolSearch", {"query": "select:gmail__messages_list"})]),
        message(content="answered"),
    ])
    result = await run(client, model="m", messages=USER, session=session)

    assert client.offered[0] == ["ToolSearch"]
    assert client.offered[1] == ["ToolSearch", "gmail__messages_list"]
    assert result == RunResult(messages=result.messages, content="answered", turns=2, stop="end")


@respx.mock
async def test_a_tool_call_reaches_the_api_and_its_result_reaches_the_model():
    respx.get(url__regex=r".*labels.*").mock(
        return_value=httpx.Response(200, json={"labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}]})
    )
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([
        message(tool_calls=[tool_call("1", "ToolSearch", {"query": "select:gmail__labels_list"})]),
        message(tool_calls=[tool_call("2", "gmail__labels_list", {"userId": "me"})]),
        message(content="you have one label"),
    ])
    result = await run(client, model="m", messages=USER, session=session)

    results = [m for m in result.messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert results[0]["tool_call_id"] == "1"
    assert "INBOX" in results[1]["content"]
    assert result.content == "you have one label"


async def test_the_caller_s_message_list_is_not_modified():
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([message(content="hi")])
    messages = list(USER)
    await run(client, model="m", messages=messages, session=session)
    assert messages == USER


async def test_extra_keyword_arguments_reach_the_client():
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([message(content="hi")])
    await run(client, model="m", messages=USER, session=session, temperature=0.2)
    assert client.kwargs[0]["temperature"] == 0.2


async def test_parallel_tool_calls_are_answered_in_order():
    session = ToolSession([*gmail.TOOLS, *stripe.TOOLS])
    client = FakeClient([
        message(tool_calls=[
            tool_call("a", "ToolSearch", {"query": "select:gmail__messages_list"}),
            tool_call("b", "ToolSearch", {"query": "select:stripe__refunds_create"}),
        ]),
        message(content="both"),
    ])
    result = await run(client, model="m", messages=USER, session=session)
    ids = [m["tool_call_id"] for m in result.messages if isinstance(m, dict) and m.get("role") == "tool"]
    assert ids == ["a", "b"]
    assert client.offered[1] == ["ToolSearch", "gmail__messages_list", "stripe__refunds_create"]


# -----------------------------------------------------
# What the model gets back when it is wrong
# -----------------------------------------------------


async def test_calling_a_tool_that_is_not_loaded_comes_back_as_the_tool_result():
    """A CharterError is written for a model to read, so the loop continues."""
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([
        message(tool_calls=[tool_call("1", "gmail__messages_list", {"userId": "me"})]),
        message(content="recovered"),
    ])
    result = await run(client, model="m", messages=USER, session=session)
    tool_result = next(m for m in result.messages if isinstance(m, dict) and m.get("role") == "tool")
    assert "select:gmail__messages_list" in tool_result["content"]
    assert result.content == "recovered"


async def test_malformed_arguments_come_back_as_the_tool_result():
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([
        message(tool_calls=[tool_call("1", "ToolSearch", "{not json")]),
        message(content="recovered"),
    ])
    result = await run(client, model="m", messages=USER, session=session)
    tool_result = next(m for m in result.messages if isinstance(m, dict) and m.get("role") == "tool")
    assert "not valid JSON" in tool_result["content"]


async def test_a_bug_in_a_tool_is_not_fed_to_the_model_as_text(monkeypatch):
    """Only CharterError becomes a tool result. A RuntimeError is a bug in the
    caller's code and has to reach the caller.

    monkeypatch, not assignment: a pack's tools are module-level singletons, and
    breaking one by hand breaks it for every test that runs afterwards.
    """
    session = ToolSession(gmail.TOOLS)
    session.search("select:gmail__messages_list")

    async def boom(*args, **kwargs):
        raise RuntimeError("handler is broken")

    monkeypatch.setattr(session.tools["gmail__messages_list"], "ainvoke", boom)
    client = FakeClient([message(tool_calls=[tool_call("1", "gmail__messages_list", {})])])
    with pytest.raises(RuntimeError, match="handler is broken"):
        await run(client, model="m", messages=USER, session=session)


async def test_max_turns_stops_the_loop_and_says_so():
    session = ToolSession(gmail.TOOLS)
    client = FakeClient([
        message(tool_calls=[tool_call(str(i), "ToolSearch", {"query": "+gmail"})])
        for i in range(10)
    ])
    result = await run(client, model="m", messages=USER, session=session, max_turns=3)
    assert result.stop == "max_turns"
    assert result.turns == 3
    assert result.content is None


async def test_a_session_with_no_tools_omits_the_argument():
    """`tools: []` is not the same as no `tools`: the OpenAI API rejects the
    empty array, so a run with nothing to offer must not send one."""
    client = FakeClient([message(content="nothing to do")])
    await run(client, model="m", messages=USER, session=ToolSession([]))
    assert "tools" not in client.kwargs[0]
    assert client.offered == [[]]


async def test_tools_are_sent_when_there_are_any():
    client = FakeClient([message(content="hi")])
    await run(client, model="m", messages=USER, session=ToolSession(gmail.TOOLS))
    assert client.offered[0] == ["ToolSearch"]
