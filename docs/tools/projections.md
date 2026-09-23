---
title: "Projections"
description: "Narrowing a tool you did not declare: keep, drop and pin."
---

[`Mode`](/reference/markers#mode) is declared on a field, by whoever writes the
pack. A projection is the other lever, and it needs nothing from the pack at all.
Both belong to whoever deploys the tool, and they are not interchangeable: see
[which one to reach for](#a-projection-or-a-mode) below.

You did not write `documents_batch_update` and cannot edit it. You are the one
who knows that this agent may insert text and must never delete a range.

```python projection.py
from charter.packs import gdocs

edit_text = gdocs.documents_batch_update.derived(
    name="documents_edit_text",
    keep={"insert_text", "delete_content_range", "replace_all_text"},
)
```

The result is the same tool. Same URL, same credentials, same validators, same
`extra="forbid"`. Only the view narrows.

Narrowing the view does two things at once: it reduces what the tool can do, and how
much of the context window it occupies. This page is about the first. The second is a
[context-window lever](/optimization/context-window) in its own right, and on a
recursive schema it decides whether the tool is callable at all.

## Why the tool is shaped this way

The Google Docs API has three endpoints, and one of them carries every write.
`documents.batchUpdate` takes a list of requests, each setting exactly one of 33
kinds of edit. Charter models all 33, which is what makes the tool complete and
also what makes it cost 7,336 tokens of schema before the model reads the task.

Narrowing to three members takes that to 1,553, or 79% smaller.

The permission matters more than the tokens. Google's `documents` scope grants
every one of those 33 edits as a single indivisible grant. There is no scope for
"may edit text, may not delete content". The union member is the capability, so
pruning it is the only place that permission can be expressed.

## keep and drop

`keep` selects within the sibling group it names. Keeping three members of the
union drops the other 30 and leaves `document_id` and `body.write_control`
alone, so the tool is still callable.

`drop` removes one path outright:

```python drop.py
lean = gdocs.documents_batch_update.derived(
    name="documents_edit",
    drop={"write_control"},
)
```

Dropping a field the API requires raises
[`DeclarationError`](/reference/errors#declarationerror) when you build the
projection, not when the API answers 400.

## pin

`pin` removes a field and sends a fixed value on every request. The field is
neither visible to the model nor reachable by it:

```python pin.py
from charter.packs import gdrive

search_docs = gdrive.files_list.derived(
    name="search_documents",
    pin={"q": "mimeType='application/vnd.google-apps.document'"},
)
```

That is a search the agent cannot widen.

A pinned value is merged into the model the runtime executes, so it travels the
path a supplied value travels and is indistinguishable from one on the wire. It
goes where its [`Path()`](/reference/markers#path),
[`Query()`](/reference/markers#query) or [`Body()`](/reference/markers#body)
marker says, picks up the [`Format`](/reference/markers#format) transform, the
key casing cascade and the percent-encoding, and a single body field still
unwraps to become the body. A value that does not satisfy its field raises
[`DeclarationError`](/reference/errors#declarationerror) when you build the
projection.

Pin top-level fields. A nested path raises.

The field has to reach that executed model, so a field
[`Mode`](/reference/markers#mode) withholds cannot be pinned. `response_only` and
`disabled` are refused at every mode, so pinning one raises as soon as you build
the projection. A field carrying a custom mode is refused only at the labels that
do not name it, so it raises when a mode that hides it resolves the view, naming
the mode. Both used to be accepted and then fail every call with `Extra inputs
are not permitted`, on a field the caller never set.

## Naming a path

[`Tool.paths()`](/reference/tool#tool-paths) lists what a projection can select,
one level at a time:

```python paths.py
gdocs.documents_batch_update.paths()
# ['document_id', 'body']

gdocs.documents_batch_update.paths("body.requests")
# ['replace_all_text', 'insert_text', 'update_text_style', ...]
```

A selector is a dotted path, an unambiguous field name, or the model class a
field is annotated with. All three of these select the same field:

```python selectors.py
from charter.packs.gdocs.types.requests import InsertTextRequest

keep={"body.requests.insert_text"}
keep={"insert_text"}
keep={InsertTextRequest}
```

Every one of the 33 union members is unique by its own name, so the short form
works there. `index` names 19 different fields, and naming it raises an error
listing the candidates rather than guessing.

## What a path costs

A list of names does not say which branch is expensive, and on a large tool that
is the only thing you need to know. `search_issues_full` in the Linear pack has
one top-level field. Every projection worth writing lives underneath it.

Pass `by_cost=True` to price the level instead of naming it, most expensive
first:

```python by_cost.py
from charter.packs import linear

linear.search_issues_full.paths(by_cost=True)
# [PathCost(path='variables', tokens=47001)]

linear.search_issues_full.paths("variables", by_cost=True)
# [PathCost(path='filter', tokens=46630), PathCost(path='first', tokens=50), ...]
```

One recursive filter is nearly the whole of a 47,026 token tool. Dropping it
leaves 396:

```python narrow.py
lean = linear.search_issues_full.derived(
    name="search_issues_lean",
    drop={"filter"},
)
```

The pack applies this treatment already, which is why the un-narrowed schema is
reached here as `search_issues_full`: every filter-bearing Linear tool ships
curated, and keeps an undiminished twin under `*_full` for a caller who needs the
complete filter. `linear.search_issues` itself is 7,748 tokens.

The figure is measured, not estimated. Each path is pruned for real and the
schema regenerated, so what `by_cost` reports is what `drop` produces. Sizes
are [`schema_tokens()`](/reference/tool-discovery#schema_tokens), serialised
JSON characters over four.

Pricing costs one schema generation per path, so only the level being returned
is priced. Pass a prefix to drill, or `depth=2` to price a level and its
children in one call.

Four properties to read the numbers by. Each is something `drop` really does,
so the number is the warning:

- Costs do not sum to the total. Where two fields share a `$def`, dropping
  either one alone leaves it in place, so both price cheap and dropping both is
  worth more than the sum of the two.
- A negative cost means the drop makes the tool larger. Pruning inside a model
  several siblings share splits one `$def` into per-path copies. Dropping
  `body.requests.insert_text.location.index` takes `documents_batch_update` from
  7,336 tokens to 7,584, for a tool that can do less.
- A cost of zero means [`Mode`](/reference/markers#mode) already removed the
  path, so a projection naming it does nothing. `events_insert` prices
  `event.i_cal_uid` at 0 under `mode="write"`; `events_import` prices the same
  path at 103.
- A required path is priced even though `drop` refuses it.
  `documents_batch_update` cannot lose `body.requests`, and the price is what
  says whether `pin` is worth reaching for.

A projection prices what is left of it, not what the tool it came from had.

## What is enforced

A projection can only remove, and removal is checked by the schema rather than
requested in a prompt:

```python enforced.py
edit_text.invoke(
    document_id="1AbC",
    body={"requests": [{"insert_table": {"rows": 2, "columns": 2}}]},
)
# ToolValidationError: Validation error:
# - **body.requests.0.insert_table**: Extra inputs are not permitted
```

The narrowed schema keeps the validators of the schema it narrowed, so the
`Request` oneof rule still rejects a request that sets two edits at once.

## Composition

Deriving from a projection narrows what is left:

```python compose.py
insert_only = edit_text.derived(name="documents_insert_text", keep={"insert_text"})
```

## A projection or a mode

[`Tool.with_mode`](/reference/tool#tool-with_mode) and
[`ToolSession(tools, mode=...)`](/reference/tool-discovery#the-mode-a-session-resolves)
are the other way to narrow a tool you did not write. They read labels the pack
author already declared, so they work only where those labels exist, and they are
not a projection in the sense this page means.

| | `keep` / `drop` / `pin` | `mode=` |
|---|---|---|
| Needs the pack to have declared anything | no | yes, a `Mode` on the field |
| Selects by | path, field name or class | a label |
| Against the tool it came from | only removes | can remove or add |
| Sets a value | `pin` does | no |
| Resolved | when the projection is built | when the session is built |

"Only removes" is what makes a projection safe to hand to a deployment without
reading the pack: whatever it produces, the tool underneath can do less. A mode
rebuilds the view from the declarations, so `with_mode("max")` on a tool built
`mode="free"` is wider than what it started from. The floor still holds, because
`response_only` and `disabled` are refused without consulting the mode at all, so
no label reaches a field the author withheld unconditionally.

They compose, in either order, and the composition keeps both:

```python both.py
lean = gdocs.documents_batch_update.derived(name="documents_edit_text", keep=TEXT)
session = ToolSession([lean], mode="write")
```

The mode resolves the view and the `keep` is still in it. Which is the order a
deployment tends to write anyway: the projection is a startup decision about what
this agent may do, and the mode is a per-conversation one about which surface this
conversation gets.

## Reading the boundary

Both halves print in [`egress_map()`](/reference/observability), which reads the
same declarations the runtime executes:

```text egress.txt
gdocs__documents_edit_text  (POST v1/documents/{document_id}:batchUpdate)
  visible to the model (28):
    + document_id
    + body
    + body.requests
    + body.requests.replace_all_text
    ...
  withheld (30):
    - body.requests.update_text_style  [projection]
    - body.requests.create_paragraph_bullets  [projection]
    ...

gdrive__search_documents  (GET drive/v3/files)
  visible to the model (10):
    + page_size
    ...
  withheld (5):
    - q  [pinned] = "mimeType='application/vnd.google-apps.document'"
    - supports_team_drives  [disabled]
    ...
  pinned (1):
    = q  "mimeType='application/vnd.google-apps.document'"
```

A restriction a reviewer cannot read is not a control. This is the artifact that
answers what an agent can do, and it diffs in CI.

## Where projections live

In your code, not in the pack. Charter ships the mechanism and no named
projections, because a projection is a policy decision and the policy is yours.
`gdocs.documents_edit_text` in a pack namespace would be Charter deciding what
text editing means for every deployment that installs it.

Keeping them in your repo also puts them in your pull requests, next to the rest
of what your agent is allowed to do.

## Related

- [Context window](/optimization/context-window) — finding which tool is worth narrowing, and what it was worth
- [`Tool.derived`](/reference/tool#tool-derived) and [`Tool.paths`](/reference/tool#tool-paths)
- [Egress control](/boundary/egress-control) for what the map reports
- [The mode system](/boundary/mode-system) for the label-side half, and both ends of it
- [`DeclarationError`](/reference/errors#declarationerror) for what a bad selector raises
