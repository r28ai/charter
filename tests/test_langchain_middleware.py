"""
A growing tool surface inside an agent that binds its tools once.

``create_agent`` binds tools when the graph is built and a
:class:`~charter.session.ToolSession` grows, so these run a real agent with a
scripted model and check what it was bound to on each model call. Nothing here
inspects the middleware's hooks directly: the claim is about the agent.

Offline: the model is scripted and every request is answered by respx.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from langchain_core.messages import AIMessage

from charter import ToolSession
from charter.auth import StaticTokenProvider
from charter.packs import gmail, stripe

pytest.importorskip("langchain.agents")

from langchain.agents import create_agent  # noqa: E402
from langchain_core.language_models.fake_chat_models import (  # noqa: E402
    GenericFakeChatModel,
)

from charter.adapters.langchain import CharterMiddleware  # noqa: E402


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    for var in ("GOOGLE_ACCESS_TOKEN", "STRIPE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    gmail.configure(StaticTokenProvider("t"))
    stripe.configure(api_key="sk_test_x")


class Recording(GenericFakeChatModel):
    """A scripted model that records the tool names it was bound to."""

    bound: list = []

    def bind_tools(self, tools, **kwargs):
        self.bound.append([getattr(t, "name", None) or t["name"] for t in tools])
        return self


def agent_for(tools, script, extra=()):
    model = Recording(messages=iter(script))
    model.bound = []
    session = ToolSession(tools)
    agent = create_agent(
        model, tools=list(extra), middleware=[CharterMiddleware(session)]
    )
    return agent, model, session


def search(query, call_id="s"):
    return AIMessage(
        content="", tool_calls=[{"name": "ToolSearch", "args": {"query": query}, "id": call_id}]
    )


def invoke(name, args, call_id="c"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


USER = {"messages": [{"role": "user", "content": "go"}]}


async def test_the_agent_is_bound_to_the_catalogue_then_to_what_it_loaded():
    agent, model, _ = agent_for(
        gmail.TOOLS,
        [search("select:gmail__labels_list"), AIMessage(content="done")],
    )
    await agent.ainvoke(USER)
    assert model.bound[0] == ["ToolSearch"]
    assert model.bound[1] == ["ToolSearch", "gmail__labels_list"]


@respx.mock
async def test_a_loaded_tool_executes_and_reaches_the_api():
    """`wrap_tool_call` is what makes this work: the agent was built with no
    Charter tools, so it has no other way to run one."""
    respx.get(url__regex=r".*labels.*").mock(
        return_value=httpx.Response(200, json={"labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}]})
    )
    agent, _, _ = agent_for(
        gmail.TOOLS,
        [
            search("select:gmail__labels_list"),
            invoke("gmail__labels_list", {"userId": "me"}),
            AIMessage(content="one label"),
        ],
    )
    out = await agent.ainvoke(USER)
    results = {m.name: m.content for m in out["messages"] if m.type == "tool"}
    assert "INBOX" in results["gmail__labels_list"]
    assert out["messages"][-1].content == "one label"


async def test_charter_tools_sit_beside_the_agent_s_own():
    from langchain_core.tools import StructuredTool

    mine = StructuredTool.from_function(lambda: "ok", name="my_own_tool", description="Mine.")
    agent, model, _ = agent_for(
        gmail.TOOLS, [AIMessage(content="done")], extra=[mine]
    )
    await agent.ainvoke(USER)
    assert model.bound[0] == ["my_own_tool", "ToolSearch"]


async def test_two_packs_load_independently():
    agent, model, session = agent_for(
        [*gmail.TOOLS, *stripe.TOOLS],
        [
            search("+stripe refund", "a"),
            search("select:gmail__messages_list", "b"),
            AIMessage(content="done"),
        ],
    )
    await agent.ainvoke(USER)
    assert model.bound[0] == ["ToolSearch"]
    assert "stripe__refunds_create" in model.bound[1]
    assert "gmail__messages_list" not in model.bound[1]
    assert "gmail__messages_list" in model.bound[2]


async def test_the_tool_list_only_ever_grows():
    """Each model call must extend the last, so the bound prefix is stable."""
    agent, model, _ = agent_for(
        [*gmail.TOOLS, *stripe.TOOLS],
        [
            search("select:gmail__messages_list", "a"),
            search("select:stripe__customers_list", "b"),
            search("select:gmail__threads_list", "c"),
            AIMessage(content="done"),
        ],
    )
    await agent.ainvoke(USER)
    for before, after in zip(model.bound, model.bound[1:], strict=False):
        assert after[: len(before)] == before


def test_the_middleware_says_what_is_missing_without_the_agent_package(monkeypatch):
    import charter.adapters.langchain as adapter

    def missing():
        raise ImportError(
            "CharterMiddleware needs the langchain package (not just langchain-core). "
            "Install it with: pip install langchain"
        )

    monkeypatch.setattr(adapter, "_require_middleware", missing)
    with pytest.raises(ImportError, match="not just langchain-core"):
        adapter.CharterMiddleware(ToolSession(gmail.TOOLS))


# -----------------------------------------------------
# A synchronous run is refused, early and by name
# -----------------------------------------------------


def test_a_sync_agent_run_is_refused_with_something_to_act_on():
    """`agent.invoke` cannot work and used to fail late and unhelpfully.

    A Charter tool executes through `Tool.ainvoke`, async down to
    httpx.AsyncClient, so `to_langchain` builds a StructuredTool with a coroutine
    and no sync function. Driven synchronously LangChain bound the tools, spent
    the model call, and only then raised "StructuredTool does not support sync
    invocation" — after the expensive part, naming nothing the caller can do.

    The sync hooks now refuse at the first model call. Implementing them instead
    would mean sync-over-async, which raises inside a running event loop.
    """
    from charter.types.errors import CharterError

    agent, _, _ = agent_for(gmail.TOOLS, [AIMessage(content="done")])

    with pytest.raises(BaseException) as exc:
        agent.invoke(USER)

    # LangGraph wraps whatever a node raises; find ours in the chain.
    seen, error = set(), exc.value
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, CharterError):
            break
        error = error.__cause__ or error.__context__
    assert isinstance(error, CharterError), f"got {exc.value!r}"
    assert "await agent.ainvoke" in str(error)
    assert "agent.invoke" in str(error)


@pytest.mark.parametrize("hook", ["wrap_model_call", "wrap_tool_call"])
def test_both_sync_hooks_refuse_when_called_directly(hook):
    """`wrap_tool_call` cannot be reached through an agent — `wrap_model_call`
    refuses first, so a sync run never gets as far as a tool. It is kept as the
    second door and tested through the only path that opens it, rather than left
    to a mutation nothing catches.
    """
    from charter.types.errors import CharterError

    middleware = CharterMiddleware(ToolSession(gmail.TOOLS))
    with pytest.raises(CharterError, match="await agent.ainvoke"):
        getattr(middleware, hook)(object(), lambda request: request)


async def test_the_async_run_beside_it_still_works():
    """The refusal must not be a blanket one: ainvoke is the supported path."""
    agent, model, _ = agent_for(
        gmail.TOOLS, [search("select:gmail__labels_list"), AIMessage(content="done")]
    )
    out = await agent.ainvoke(USER)
    assert out["messages"][-1].content == "done"
    assert model.bound[1] == ["ToolSearch", "gmail__labels_list"]
