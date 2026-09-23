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

`create` and `update` are the common case, not the mechanism. The string is arbitrary,
so one resource model can serve any set of tool surfaces you can name:

| The label | One schema yields |
|---|---|
| `Mode("v1")`, `Mode("v2")` | a versioned surface, both built from one model |
| `Mode("A")`, `Mode("B")`, `Mode("A, B")` | an experiment, with the shared fields declared once |
| `Mode("pro")`, `Mode("max")` | a field set per plan |
| `Mode("eu")`, `Mode("us")` | a field required in one region and absent in another |
| `Mode("read")`, `Mode("write")` | a scope, expressed as a shape rather than a sentence |

```python
class Report(BaseModel):
    account_id: Annotated[str, Body()]
    raw_events: Annotated[Optional[list], Body(), Mode("pro, max")] = None
    model_weights: Annotated[Optional[dict], Body(), Mode("max")] = None
    eu_consent_id: Annotated[Optional[str], Body(), Mode("eu")] = None
```

```
mode="free"  ->  ['account_id']
mode="pro"   ->  ['account_id', 'raw_events']
mode="max"   ->  ['account_id', 'model_weights', 'raw_events']
mode="eu"    ->  ['account_id', 'eu_consent_id']
```

**The author declares the labels. The deployer puts one in force beside them.** `mode=`
on a tool is the parameter to reach for while writing tools.
[`Tool.with_mode`](/reference/tool#tool-with_mode) is the other end, for a pack that
already ships, and [`ToolSession(tools, mode=...)`](/reference/tool-discovery#toolsession)
applies it to a whole surface at once:

```python
session = ToolSession(reports.TOOLS, mode=plan_of(request.user))
```

One line instead of a `TOOLSETS = {"free": [...], "pro": [...]}` dict and the code that
chooses between its entries. The pack says which fields belong to which surface once;
the deployment says which surface this conversation is.

Three things to know about the deployer's end.

The session mode **adds to** the tool's own; it does not replace it. The two ends answer
different questions. The author's `mode=` says which *operation* this tool is — `create`
replaces and `update` merges — and that is not a deployment decision. The deployment's
label says which *surface* this conversation is. Both are in force at once, so a tool
declared `mode="create"` and resolved at `"pro"` keeps the fields that make it a create
and gains the ones that make it pro:

```
                       create tool   update tool   unlabelled tool
session mode None  ->  create        update        everything
session mode "pro" ->  create + pro  update + pro  pro
```

What follows is the property worth holding on to: **a session label only ever adds the
fields carrying it.** You do not have to read a pack to know what keying it to a tier
will do, and two packs with different internal labelling conventions behave the same
way under the same session mode.

It resolves **once**, when the session is built. Credentials resolve per call because
the subject can change mid conversation; a schema cannot, because it was already
serialised into a prompt the model is still reading. A surface that has to change means
a new session.

It cannot **widen past the declaration**. `response_only` and `disabled` are refused
without consulting the mode at all, so there is no string a deployment can pass that
reaches a field the author withheld unconditionally. What a mode moves is which of the
author's optional surfaces you get, and the map at
[egress control](/boundary/egress-control) prints which label resolved the view.

### A label, or `None`

`None` is the *widest* view, not the narrowest: a custom `Mode` is inert when there is
nothing to match it against, so with no mode every tiered field is offered. That is what
`None` means and it is the default.

An empty string is therefore refused with a
[`DeclarationError`](/reference/errors#declarationerror) rather than read as `None`. A
session mode comes from a runtime value — `plan_of(request.user)`, where a nullable plan
column or a `user.plan or ""` hands back `""` for the smallest tier — and reading that as
"no tier" would serve that user every tier, and would widen a tool the pack shipped at
`free` while it was at it. Every other way a label can be wrong fails closed: `"prro"`
matches nothing and withholds everything optional.

A label that withholds a field **the API requires** is refused the same way, and where it
is asked for rather than on every call. `Mode` moves visibility, and requiredness is a
separate axis, so a label can take a required field out of the view and leave nothing to
put it back: the tool would validate a call that never mentions the field and send a body
without it. [`drop`](/tools/projections) already refuses that removal when a projection
names the field by path; a label reaches the same end and is refused the same way. A
required field has to be visible at every label the pack offers — name each of them in
its `Mode()`, or leave it unlabelled — and a constant the API needs on every call belongs
in `static_body`/`static_query` on the factory.

This is not [`keep`, `drop` and `pin`](/tools/projections), and does not replace them. A
projection can only ever remove, works on fields and values, and needs no cooperation
from the pack. A mode reads labels the author wrote and can widen against the tool it
came from. Use a projection to narrow a tool nobody labelled; use a mode where the
labels already exist.

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
