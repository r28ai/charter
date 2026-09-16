---
title: "Egress control"
description: "What the model can see is computed from declarations before any request is made."
---

## What the model can see is a declaration, not a prompt

[`Mode`](/reference/markers#mode) is usually introduced as context economy: hide
the fields the model does not need, spend fewer tokens. That is true, and it is
the smaller half.

The larger half is that the LLM view of a schema is **computed from declarations,
deterministically, before any request is made**. A field marked
`Mode("response_only")` or `Mode("disabled")` is not stripped out of a prompt
after the fact and it is not filtered by a model asked nicely to ignore it — it is
absent from the type the model is handed. It cannot be sent to the model provider,
because nothing in the pipeline can construct it.

That is field-level data minimisation toward your model vendor, enforced by
construction rather than by policy.

```python message_schema.py
class Message(BaseModel):
    raw: Annotated[str, Body(), Format("rfc822_base64"), Mode("request_only")]
    thread_id: Optional[str] = None
    id: Annotated[Optional[str], Body(), Mode("response_only")] = None
    payload: Annotated[Optional[MessagePart], Body(), Mode("response_only")] = None
    snippet: Annotated[Optional[str], Body(), Mode("response_only")] = None
```

Gmail returns `payload` — the entire MIME tree, base64 attachment bodies and all.
Marked `response_only`, it is never part of what the model is offered, so it never
crosses into a context window. The response is still available to *your* code; it
is the model that does not receive it.

## The half the deployment owns

`Mode` is declared by whoever wrote the pack, and is fixed by the time you install
it. [Projections](/tools/projections) are the other half, and they belong to you:

```python narrow.py
from charter.packs import gdocs

edit_text = gdocs.documents_batch_update.derived(
    name="documents_edit_text",
    keep={"insert_text", "delete_content_range", "replace_all_text"},
)
```

Google's `documents` scope grants all 33 kinds of edit as one indivisible grant.
There is no scope for "may edit text, may not delete content", so the union member
is the only place that permission can be said. `pin` does the same for values: a
pinned field leaves the schema and its value is sent on every request, so the agent
can neither see it nor change it.

Both print in the map below, with a pinned field carrying its value.

## The audit artifact

Because the boundary is declared, it can be printed.
[`egress_map`](/reference/observability#egress_map) reads the same declarations
the runtime executes, so it cannot drift from what actually happens:

```python print_egress_map.py
from charter import format_egress_map
from charter.packs import gmail

print(format_egress_map([gmail.messages_send]))
```

```
messages_send  (POST gmail/v1/users/{userId}/messages/send)
  visible to the model (4):
    + userId
    + body
    + body.threadId
    + body.raw
  withheld (8):
    - body.id  [response_only]
    - body.labelIds  [response_only]
    - body.snippet  [response_only]
    - body.history_id  [response_only]
    - body.internalDate  [response_only]
    - body.payload  [response_only]
    - body.sizeEstimate  [response_only]
    - body.classificationLabelValues  [response_only]
```

`egress_map` returns the same content as a plain dict, so it serialises to JSON
for a review packet or a CI artifact:

```python egress_map_json.py
from charter import egress_map
import json

json.dumps(egress_map(gmail.TOOLS), indent=2)
```

Useful ways to spend it:

- **Security review.** The answer to "what can the model see?" is a file, generated
  from source, not a paragraph someone wrote from memory.
- **CI.** Snapshot the map and diff it. A schema change that widens what the model
  can see shows up as a reviewable diff instead of a silent broadening.
- **Vendor questionnaires.** Per-field, per-tool, with the reason attached.

## What it does and does not promise

It promises: no field marked `response_only` or `disabled`, at any nesting depth,
appears in the type given to the model.

It does not promise anything about what you do with the response after the runtime
returns it. If your own code takes a withheld field out of the response and puts it
in a prompt, that is your prompt. The boundary governs the boundary.

Nor is it authorization — `Mode` is schema visibility, not permission. Two users
calling the same tool see the same shape; who may call it at all is your
application's decision.

## Related

- [Mode system](/boundary/mode-system) — the full marker semantics and cascading rules
- [Transforms](/tools/transforms) — the other half of what the contract carries
- [`egress_map`](/reference/observability#egress_map) and [`format_egress_map`](/reference/observability#format_egress_map) — the signatures and the dict shape
- [`Mode`](/reference/markers#mode) — the four values and what each one withholds
