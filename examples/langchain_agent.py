"""
Bind Charter tools to a LangChain agent.

The adapter is a shim: `args_schema` is the Charter LLM view and the coroutine is
`Tool.ainvoke`, so execution stays in Charter and LangChain only supplies the
calling convention.

Run with:
    pip install 'charter-ai[langchain]'
    GOOGLE_ACCESS_TOKEN=... python examples/langchain_agent.py
"""

import asyncio

from charter.adapters.langchain import to_langchain_tools
from charter.packs import gmail


def build_tools():
    # gmail reads $GOOGLE_ACCESS_TOKEN on first use; call gmail.configure(...)
    # to supply a provider of your own instead.
    return to_langchain_tools(gmail.TOOLS)


async def main() -> None:
    tools = build_tools()

    for tool in tools:
        print(f"{tool.name:24} {tool.description}")

    # Bind to any tool-calling model and let it choose:
    #
    #   from langchain.chat_models import init_chat_model
    #   model = init_chat_model("claude-sonnet-5").bind_tools(tools)
    #   response = await model.ainvoke("Summarise my unread email")
    #
    # Or invoke one directly — the LangChain interface, Charter underneath:
    threads = next(t for t in tools if t.name == "threads_list")
    print(await threads.ainvoke({"q": "is:unread", "maxResults": 5}))


if __name__ == "__main__":
    asyncio.run(main())
