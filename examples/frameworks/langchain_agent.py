# Needs FIREWORKS_API_KEY, and `pip install "charter-ai[langchain]" langchain-fireworks`.
"""Charter tools in a LangChain agent. JSONPlaceholder, a free fake API, plays your API."""

import asyncio
import os
from typing import Annotated, Optional

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from charter import Query, ToolSession, api_key_tool_factory
from charter.adapters.langchain import CharterMiddleware


class ListTodos(BaseModel):
    userId: Annotated[int, Query()]
    completed: Annotated[Optional[bool], Query()] = None


myapi = api_key_tool_factory(
    pack="myapi",
    base_url="https://jsonplaceholder.typicode.com/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
list_todos = myapi(name="list_todos", description="List a user's todos.", method="GET",
                   url_template="todos", args_schema=ListTodos)  # fmt: skip


def build_agent(model):
    session = ToolSession([list_todos], progressive=False)
    return create_agent(model, tools=[], middleware=[CharterMiddleware(session)])


async def main() -> None:
    if not os.environ.get("FIREWORKS_API_KEY"):
        raise SystemExit(
            "Set FIREWORKS_API_KEY first: export FIREWORKS_API_KEY=fw_...  "
            "(make one at https://fireworks.ai/account/api-keys)"
        )
    model = init_chat_model(os.environ.get("MODEL", "fireworks:accounts/fireworks/models/kimi-k3"))
    question = "How many todos has user 2 not finished yet?"
    state = await build_agent(model).ainvoke({"messages": [{"role": "user", "content": question}]})
    print(state["messages"][-1].text)  # User 2 has 12 unfinished todos.


if __name__ == "__main__":
    asyncio.run(main())
