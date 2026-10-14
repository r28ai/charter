# Needs FIREWORKS_API_KEY, and `pip install openai`.
"""Give tools to a model with Charter's own loop, no framework.

JSONPlaceholder, a free fake API, plays your API. Any OpenAI-compatible client works;
this one points at an open model on Fireworks.
"""

import asyncio
import os
from typing import Annotated, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from charter import Query, ToolSession, api_key_tool_factory
from charter.adapters.openai import run


class FindUsers(BaseModel):
    username: Annotated[Optional[str], Query()] = Field(None, description="Leave out for all.")


class ListTodos(BaseModel):
    userId: Annotated[int, Query()]
    completed: Annotated[Optional[bool], Query()] = None


myapi = api_key_tool_factory(
    pack="myapi",
    base_url="https://jsonplaceholder.typicode.com/",
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
find_users = myapi(name="find_users", description="Find users by username.", method="GET",
                   url_template="users", args_schema=FindUsers)  # fmt: skip
list_todos = myapi(name="list_todos", description="List a user's todos.", method="GET",
                   url_template="todos", args_schema=ListTodos)  # fmt: skip


async def main() -> None:
    if not os.environ.get("FIREWORKS_API_KEY"):
        raise SystemExit(
            "Set FIREWORKS_API_KEY first: export FIREWORKS_API_KEY=fw_...  "
            "(make one at https://fireworks.ai/account/api-keys)"
        )
    client = AsyncOpenAI(
        base_url="https://api.fireworks.ai/inference/v1", api_key=os.environ["FIREWORKS_API_KEY"]
    )
    result = await run(
        client,
        model=os.environ.get("MODEL", "accounts/fireworks/models/kimi-k3"),
        messages=[{"role": "user", "content": "How many todos does Antonette have left?"}],
        session=ToolSession([find_users, list_todos], progressive=False),
    )
    print(result.content)
    # Antonette (Ervin Howell) has 12 todos left to complete. They are: 1. suscipit repellat ...


if __name__ == "__main__":
    asyncio.run(main())
