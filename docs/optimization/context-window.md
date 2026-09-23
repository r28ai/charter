---
title: "Context window"
sidebarTitle: "Context window"
description: "The two directions a tool spends context in — schemas going out, responses coming back — and what narrows each."
---

A tool spends your context window in two directions, and they are not fixed by
the same thing.

Going out, there is the schema. It is not sent once: it is sent on every turn of
the loop, before the model has read the task, and it is charged as input tokens
every time. That is the first half of this page, and the lever is a
[projection](/tools/projections).

Coming back, there is whatever the API answered with. That is the
[second half](#the-other-direction-responses-coming-back), and the lever is a
response handler. It is the half nobody chooses: a schema is something you wrote,
and a response is whatever the API felt like sending.

Most tools are small enough that this never comes up. A handful are not, and they
are not the ones you would guess. In the Linear pack, `comment_create` costs 791
tokens of schema and `search_issues_full` costs 45,168. They look alike from the
outside: both take one object, both read issues.

This page uses the Linear pack as it was before it was narrowed, because that is
the state you will find your own pack in. Every filter-bearing tool in it ships
curated today and keeps its original schema as a `*_full` twin, so the figures
below are all reachable — `search_issues` is 7,748 tokens and
`search_issues_full` is the 45,168 it was.

## Measure before narrowing

[`schema_tokens()`](/reference/tool-discovery#schema_tokens) prices a tool. Run
it across a pack and the distribution is usually lopsided:

```python survey.py
from charter import schema_tokens
from charter.packs import linear

fat = sorted(linear.TOOLS, key=schema_tokens, reverse=True)
for tool in fat[:5]:
    print(f"{schema_tokens(tool):>7,}  {tool.name}")
```

Run against the pack before curation, the five heaviest were:

```
 48,231  custom_view_create
 47,281  project_updates_list
 47,026  search_issues
 46,938  users_list
 46,918  project_milestones_list
```

Seventeen tools landed between 46,870 and 48,231. The eighteenth was
`project_update` at 1,793, and the remaining 110 were smaller than that.

A cliff like this is the signal. Sizes that cluster inside 3% of each other are
not seventeen expensive tools. They are one expensive thing, reached by
seventeen routes.

## Why the fat tools are fat

Linear's API is GraphQL, and its filter types are mutually referential. An
`IssueFilter` has an `and` and an `or` that hold more `IssueFilter`, and a `team`
that holds a `TeamFilter` that holds an `IssueFilter`. Fifty-six of the pack's 77
generated definitions sit in a cycle.

One `filter` argument reaches all of them, which is what makes the seventeen
sizes nearly equal: each of those tools is paying for the same graph. The 111
tools that never name a filter are all 1,555 tokens or less.

This is worth separating from merely large. `gsheets.spreadsheets_batch_update`
generates 201 definitions and `gdocs.documents_batch_update` generates 51, and
not one of either is in a cycle. Wide is a cost you can decide to pay. Recursive
is a different problem, because above a certain size it stops being a cost at
all and becomes a rejected request.

## Deferring is not the same as shrinking

[`ToolSession`](/reference/tool-discovery#toolsession) defers schemas: the model
gets a search tool, and a tool's parameters arrive only once it has asked for
that tool by name.

That is the right default and it is not sufficient here. Progressive disclosure
changes how many schemas are in the prompt. It does not change what one costs,
and once the model searches for a 47,026-token tool it has bought all of it, on
every turn from then until the end of the run.

Deferral and narrowing solve different halves. Use both.

## Find the branch, not the tool

The tool is not expensive. One field in it is, and a list of field names does not
say which. [`Tool.paths(by_cost=True)`](/reference/tool#tool-paths) prices the
level instead of naming it:

```python by_cost.py
from charter.packs import linear

linear.search_issues_full.paths(by_cost=True)
# [PathCost(path='variables', tokens=47001)]

linear.search_issues_full.paths("variables", by_cost=True)
# [PathCost(path='filter', tokens=46630), PathCost(path='first', tokens=50), ...]
```

`filter` is 46,630 of the tool's 47,026. `term`, `first` and `team_id` are the rest.

The figure is measured rather than estimated. Each path is pruned for real and
the schema regenerated, so what `by_cost` reports is what `drop` will produce.

## Narrow it

[`derived()`](/reference/tool#tool-derived) removes the branch. Two shapes, and
which one you want depends on what the tool's cost is made of.

`drop` when one branch is the whole cost:

```python drop.py
from charter.packs import linear

search = linear.search_issues_full.derived(
    name="search_issues",
    drop={"filter"},
)
```

```
linear.search_issues_full    45,168 tokens  ->  341    (132x)
```

`keep` when the cost is a union and you want a few of its members:

```python keep.py
from charter.packs import gdocs

edit_text = gdocs.documents_batch_update.derived(
    name="documents_edit_text",
    keep={"insert_text", "delete_content_range", "replace_all_text"},
)
```

```
gdocs.documents_batch_update    7,336 tokens  ->  1,553    (79% smaller)
```

Both tools still work. `search_issues` keeps its other seven arguments, including
the search term, the team and the ordering, which is what an agent triaging issues
actually sends. `documents_edit_text` still inserts, replaces and deletes text.

## Recursive schemas can fail outright

Above some size the problem stops being cost and becomes whether the tool is
callable at all. Providers cap how deep a tool schema may resolve, and a cycle
resolves deeper than anything a human writes.

Sending `linear.search_issues_full` to Fireworks returns:

```
400 JSON Schema not supported: schema depth exceeds maximum limit of 50.
Flatten deeply nested objects/arrays or raise `max_schema_depth` on the builder.
```

The whole request is rejected, not just that tool, so the turn produces no tool
call at all. `drop={"filter"}` removes the cycle and the same request is
accepted.

Two things follow, and neither is specific to this library:

- **The limit is the provider's, and they differ.** There is no schema a pack can
  emit that satisfies every one of them. The cap is a deployment fact, which is
  the layer a projection belongs to.
- **It fails as a request error, not a bad answer.** Nothing degrades gracefully.
  If a recursive tool is in the payload, the turn returns 400 and the agent makes
  no progress, so this shows up as an agent that does nothing rather than as a
  cost line.

A tool whose schema is a cycle needs a projection to be usable, not merely to be
cheap.

## Every tool carries its own definitions

One more reason the fat tools compound. `$defs` is scoped to a single schema
document, and in every tool-calling format a document is one tool. There is no
cross-tool definition space in an OpenAI `tools` array, in an MCP `tools/list`
response, or in an Anthropic `input_schema`, so a type two tools share is sent
twice.

Three Linear list tools — `teams_list_full`, `issues_list_full`,
`projects_list_full` — measured through the adapters this library ships:

```
OpenAI    541,407 bytes    77 $defs per tool, 79 distinct across the whole payload
MCP       540,743 bytes    77 $defs per tool
```

231 definition entries for 79 distinct types. Narrowing one recursive tool
therefore does not save its cost once. It saves it once per tool that reaches the
same type graph.

Which is also why this is not an artefact of how a pack was authored. The Linear
pack is generated from GraphQL, not from an OpenAPI document, and the duplication
is identical either way. It is a property of the protocol.

There is no dead weight in it to remove. Every definition in every tool measured
here is reachable from that tool's own properties: `teams_list_full` 77 of 77,
`gsheets.spreadsheets_batch_update` 201 of 201, `gdocs.documents_batch_update` 51
of 51. Nothing is emitted that the tool does not use, so the copies cannot be
trimmed, only made small.

Making them small is the whole of it, and it compounds the same way the cost
does. The same three tools with `drop={"filter"}` applied:

```
as shipped    541,407 bytes    77 $defs per tool
projected       3,530 bytes     1 $def  per tool
```

153x, because the saving lands once per tool rather than once. Progressive
disclosure is the other half of the same lever: it decides how many copies are in
the payload, while a projection decides what each copy weighs.

### Clients that flatten make it worse

Support for `$ref` in tool schemas is uneven, so some clients resolve references
before sending. Resolving is multiplicative, and on a cyclic schema there is no
size it converges to.

`langchain_core` 1.6.1 does this in `convert_to_openai_function`, which calls
`dereference_refs` and then discards `$defs`. Its cycle guard is per branch, so a
definition reached along ten paths is expanded ten times. On small Linear tools
the result is about twice the input. On the uncurated `teams_list_full` — 176 KB
and 77 definitions today — it had not returned after 45 seconds and had allocated
1.92 GB.

That is the shape of the problem rather than one library's bug. Expanding the
same schema with a depth cap of 12 produced 115 MB, and no cap that is generous
enough to keep an ordinary REST schema whole is small enough to bound a cyclic
one.

<Note>
The 1.92 GB and the 115 MB were measured against `langchain_core` 1.6.1 on the
pack as it stood, when that schema was 183 KB. The schema's size moves with the
pack and those two figures are not recomputed with it: what does not move is that
neither has a bound, because the expansion is multiplicative on a cycle.
</Note>

A projection fixes this at the source, because it removes the cycle rather than
bounding the expansion of one.

## The same edit is a permission

A projection can only remove. That is what lets the saving and the restriction be
the same line of code: `drop={"filter"}` is a smaller prompt and it is also an
agent that cannot construct an arbitrary query against your issue tracker.

Both halves print in [`egress_map()`](/reference/observability), so what was
narrowed is reviewable rather than implied:

```text egress.txt
search_issues  (POST graphql)
  visible to the model (8):
    + variables
    + variables.first
    + variables.after
    + variables.term
    + variables.team_id
    + variables.include_comments
    + variables.include_archived
    + variables.order_by
  withheld (1):
    - variables.filter  [projection]
```

Cost is the reason you go looking. It is rarely the best reason to keep the
change.

## The other direction: responses coming back

Everything above is about the schema, which is the half you can see in your own
code. The other half arrives from someone else.

Two fields separate them, and the gap between the two is the whole subject:

| field | what it counts |
|---|---|
| `payload_bytes` | the response body, as read off the wire |
| `context_bytes` | what the model actually receives, after the response handler |

A [response handler](/reference/response-handling) runs after a successful call
and returns whatever the model should see. Gmail's `threads_get` is the ordinary
case: the API answers with a MIME tree — nested parts, `multipart/alternative`
duplicates of the same text, base64 attachment bytes inline — and the pack's
handler returns an id, the headers worth keeping, the decoded body text, and
attachment *metadata* rather than attachment bodies. The attachment ids survive
because `messages.attachments.get` is the call the model makes next; dropping
them would save bytes and cost a turn.

Across the shipped packs, 286 tool definitions in 14 packs name a handler. None
of that is configuration you write.

### What it is worth

From the two campaigns on the [measured results](/guarantees/measured-results)
page, per run:

```
                      payload_bytes   context_bytes
breadth   Charter            35,190           8,397     4.2x
          raw                35,068          35,016     1.0x
depth     Charter            33,195           7,657     4.3x
          raw                34,317          32,685     1.0x
```

The first column is the point. Both arms pulled the same volume off the wire, to
within 3% — same scenarios, same APIs, same credentials — and differed only in
how much of it reached the model. Nothing was fetched less; it was forwarded
less.

Three things that number is not, all of which
[`ToolCall`](/running/observability#sizes-on-both-sides) is deliberate about:

- **It is not bandwidth.** `payload_bytes` is read after decompression. The
  currency here is the model's context window, not egress.
- **It is not tokens.** Tokens need a tokeniser this library does not ship, and a
  bytes-per-token constant is a guess with a decimal point in it.
- **It is not all trimming.** `payload_bytes` is the response as the server
  formatted it and `context_bytes` is compact JSON, so against an API that
  pretty-prints, some of the difference is that API's whitespace.

### Find your own

The same survey shape as the schema half, one axis over. Attach a sink, run the
thing you actually run, and sort by what the handler failed to remove:

```python survey_responses.py
from collections import defaultdict

from charter import CallCollector, collecting

calls = CallCollector()
with collecting(calls):
    await run_your_agent()

worst: dict[str, int] = defaultdict(int)
for call in calls.records:
    if call.context_bytes:
        worst[call.tool] += call.context_bytes

for tool, total in sorted(worst.items(), key=lambda kv: -kv[1])[:5]:
    print(f"{total:>9,}  {tool}")
```

A tool near the top with `saved_ratio` near zero is one whose handler is missing
or is not removing what the endpoint actually sends. `saved_bytes` going
*negative* is not hidden either — a handler that adds more than it removes is
worth seeing.

### Two things to keep

Trimming a list endpoint has exactly two ways to go wrong, and both cost a turn
rather than raising:

- **Keep what a [`Pagination`](/reference/envelopes-and-pagination) declaration
  reads** — the object `id` behind a derived cursor, and `has_more` even when it
  is `False`.
- **Keep what the model needs for the *next* call**, which is usually an id it
  would otherwise have to guess.

## Related

- [Projections](/tools/projections) for `keep`, `drop`, `pin` and what a selector may name
- [`Tool.paths`](/reference/tool#tool-paths) and [`PathCost`](/reference/tool#pathcost)
- [`ToolSession`](/reference/tool-discovery#toolsession) for deferring the schemas you keep
- [Egress control](/boundary/egress-control) for reading the boundary back
- [`ResponseHandler`](/reference/response-handling) for the return direction
- [Measured results](/guarantees/measured-results) for where the 4x comes from
