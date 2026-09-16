---
title: "Mode quick reference"
description: "The Mode cheat sheet: types, cascading, common patterns, and how to inspect a result."
---

## Cheat sheet

```python mode_cheatsheet.py
from typing import Annotated
from pydantic import BaseModel, Field
from charter import Mode

# Single mode
field: Annotated[str, Field(...), Mode("A")]

# Multiple modes
field: Annotated[str, Field(...), Mode("A, B, C")]

# Special modes
id: Annotated[str, Field(...), Mode("response_only")]
internal: Annotated[str, Field(...), Mode("disabled")]
```

Declaring the mode on a tool:

```python tool_mode.py
tool = factory(
    name="my_tool",
    args_schema=MySchema,
    method="POST",
    url_template="v1/thing",
    mode="A",
)
```

## Mode types

| Mode              | Meaning                    | Use case                          |
|-------------------|----------------------------|-----------------------------------|
| `"response_only"` | only in API responses      | IDs, timestamps, computed fields  |
| `"request_only"`  | input-only, always shown   | write-only payload fields         |
| `"disabled"`      | never exposed to the LLM   | internal / deprecated fields      |
| `"A"`, `"B"`, ... | custom modes               | different operations (send/read)  |
| `"A, B"`          | multiple modes             | fields used in several contexts   |
| *(no mode)*       | always included            | common fields                     |

## Cascading

```python
# Parent carries the mode
parent: Annotated[Child, Mode("B")]  # Child's fields inherit Mode B

class Child(BaseModel):
    inherited: str = Field(...)              # gets Mode B from the parent
    override: Annotated[str, Mode("A")]      # overrides to Mode A
```

## Common patterns

```python
Mode("read")    # GET operations
Mode("write")   # POST/PUT operations

Mode("v1")
Mode("v2")
Mode("v1, v2")  # both versions
```

## Debugging

```python
print(sorted(tool.llm_schema().model_fields))
```

Or without a tool:

```python inspect_schema.py
from charter.execution.schema import create_llm_schema

schema = create_llm_schema(MyModel, mode="A")
print(f"Fields in mode A: {sorted(schema.model_fields)}")
```

## Related

- [`Mode`](/reference/markers#mode) — the marker reference
- [`Tool.llm_schema`](/reference/tool#tool-llm_schema) — what the debugging call above returns
- [Mode system](/boundary/mode-system) — the same rules, explained
