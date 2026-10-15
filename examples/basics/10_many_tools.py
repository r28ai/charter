"""Hundreds of tools, without hundreds of schemas in the prompt.

A ToolSession holds every tool and sends none of their schemas up front. The model starts
with one search tool, and a tool's schema goes out once the model has looked for it.
"""

import importlib
import pkgutil

import charter.packs
from charter import ToolSession, json_tokens, schema_tokens
from charter.adapters.openai import to_openai_tools

packs = [m.name for m in pkgutil.iter_modules(charter.packs.__path__) if m.name[0] != "_"]
tools = [tool for name in packs for tool in importlib.import_module(f"charter.packs.{name}").TOOLS]
session = ToolSession(tools)

every_schema = sum(schema_tokens(tool) for tool in tools)
print(f"all {len(tools)} tools, up front  {every_schema:>8,} tokens")
print(
    f"the first turn sends    {json_tokens(to_openai_tools(session)):>8,} tokens, one search tool"
)
found = session.search("gmail send")["loaded"]
print(
    f"after one search        {json_tokens(to_openai_tools(session)):>8,} tokens, {', '.join(found)}"
)
# all 613 tools, up front   471,451 tokens
# the first turn sends       4,476 tokens, one search tool
# after one search           7,498 tokens, gmail_drafts_create, gmail_drafts_send, ...
