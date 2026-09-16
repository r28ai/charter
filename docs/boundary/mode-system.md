---
title: "Mode system"
description: "How a field's visibility to the model is declared, cascaded, and resolved."
---

## Overview

[`Mode`](/reference/markers#mode) gives fine-grained control over which schema
fields are exposed to the LLM. It matters most for APIs where one resource is used by several operations
with different field sets — Gmail's `Message` being the canonical case: `send`
accepts only `raw`, while reads return a structured `payload` tree.

It has a second job that is easy to miss and is arguably the more valuable one:
because the LLM view is computed from these declarations before any request is
made, `Mode` is also **field-level data minimisation toward your model vendor** —
a withheld field cannot reach a context window, by construction. See
[egress control](/boundary/egress-control), including the audit artifact that renders
it.

## Core concepts

### The marker

```python mode_marker.py
from typing import Annotated
from pydantic import BaseModel, Field
from charter import Mode

class MyModel(BaseModel):
    field_a: Annotated[str, Field(...), Mode("A")]       # only in mode A
    field_b: Annotated[str, Field(...), Mode("B")]       # only in mode B
    field_ab: Annotated[str, Field(...), Mode("A, B")]   # in both
```

### Special modes

Always enforced, whatever mode the tool declares:

- **`response_only`** — the API returns it and never accepts it. Hidden from the
  LLM. IDs, timestamps, computed fields.
- **`request_only`** — input-only. Always shown.
- **`disabled`** — never exposed. Internal or deprecated fields.

### Custom modes

Any other string. A custom mode narrows the view **only when the tool declares a
mode**. With no `mode=` on the tool, custom-moded fields are all visible — setting
`mode=` is what makes `create` and `update` mutually exclusive.

## Features

### Multi-mode

```python
field: Annotated[str, Field(...), Mode("A, B, C")]
```

### Cascading

Child fields inherit the parent's modes, so you mark the parent once:

```python cascading_modes.py
class Message(BaseModel):
    payload: Annotated[Optional[MessagePart], Field(None), Mode("B")]

class MessagePart(BaseModel):
    part_id: Optional[str] = Field(None)    # inherits Mode B
    mime_type: Optional[str] = Field(None)  # inherits Mode B
```

A `response_only` parent hides its whole subtree.

### Mode + Format together

```python
raw: Annotated[
    Optional[str],
    Field(None),
    Format("rfc822_base64"),  # transform to EmailContent
    Mode("A"),                # only visible in mode A
]
```

## Processing order

1. **Mode filtering** — fields are checked against the effective mode.
2. **Format transformation** — only included fields are retyped.
3. **Metadata preservation** — every marker survives onto the generated schema.

## Declaring a mode on a tool

The [builder's](/reference/factories#the-builder) `mode=` parameter picks the
effective mode for that tool:

```python messages_send_tool.py
send_tool = gmail(
    name="messages_send",
    args_schema=MessagesSendRequest,
    method="POST",
    url_template="gmail/v1/users/{userId}/messages/send",
    mode="A",  # mode A: only `raw` is visible
)
```

## Worked example: Gmail

**Problem.** `messages.send` accepts only `raw` (RFC-822). Reads return a
structured `payload` MIME tree. One schema for both confuses the model into
sending fields the endpoint ignores.

**Solution.**

```python gmail_message_schema.py
class Message(BaseModel):
    # Response-only
    id: Annotated[Optional[str], Field(None), Mode("response_only")]
    snippet: Annotated[Optional[str], Field(None), Mode("response_only")]

    # Mode A: send (raw RFC-822)
    raw: Annotated[str, Field(...), Format("rfc822_base64"), Mode("request_only")]

    # Mode B: read (parsed MIME tree)
    payload: Annotated[Optional[MessagePart], Field(None), Mode("response_only")]

    # Both
    thread_id: Optional[str] = Field(None)
```

Result:

- `mode="A"` sees `raw`, `thread_id`
- `mode="B"` sees `payload`, `thread_id`
- `mode=None` sees everything except `response_only` and `disabled`

## Inspecting the result

[`Tool.llm_schema`](/reference/tool#tool-llm_schema) builds the filtered view —
what the model is actually handed:

```python
schema = tool.llm_schema()
print(sorted(schema.model_fields))
```

## Do's and don'ts

**Do**

- lean on cascading instead of marking every nested field
- say *why* a field has a mode, in the field description
- test each mode configuration
- use semantic mode names

**Don't**

- mark every nested field redundantly
- mix concerns into one name (`Mode("admin_read_v2")`)
- forget to set `mode=` on the tool when the schema depends on it
- use modes for authorization — they are a schema-visibility tool, not a
  permission system

## Related

- [`Mode`](/reference/markers#mode) — the marker, its values, and the cascade rules
- [`Format`](/reference/markers#format) — the retyping that runs after mode filtering
- [`Tool.llm_schema`](/reference/tool#tool-llm_schema) — the filtered schema the model sees
- [Egress control](/boundary/egress-control) — the audit artifact these declarations produce
