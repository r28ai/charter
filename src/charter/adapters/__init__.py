"""
Views onto a :class:`~charter.tool.Tool` for other frameworks.

The Tool is the object; these are projections of it. Each adapter is a thin
shim over ``Tool.ainvoke`` — no execution logic lives here.

- :mod:`~charter.adapters.openai` — OpenAI-style function definitions (no extra deps)
- :mod:`~charter.adapters.langchain` — LangChain ``StructuredTool`` (extra ``[langchain]``)
- :mod:`~charter.adapters.mcp` — an MCP stdio server (extra ``[mcp]``)
"""

from charter.adapters.openai import to_openai_tool, to_openai_tools

__all__ = ["to_openai_tool", "to_openai_tools"]
