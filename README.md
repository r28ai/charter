<div align="center">

<img src="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-mark-144.png" alt="" width="72" height="72">

<h3>Agent tools you declare instead of implement.</h3>

<p>
<a href="https://docs.r28.ai/charter">Documentation</a> ·
<a href="https://docs.r28.ai/charter/start/quickstart">Quickstart</a> ·
<a href="https://docs.r28.ai/charter/packs/overview">Packs</a> ·
<a href="https://docs.r28.ai/charter/start/coding-agents">Write a pack</a> ·
<a href="https://github.com/r28ai/charter/issues">Request a pack</a>
</p>

<p>
<a href="https://pypi.org/project/charter-ai/"><img src="https://img.shields.io/pypi/v/charter-ai?v=9" alt="PyPI"></a>
<a href="https://pypi.org/project/charter-ai/"><img src="https://img.shields.io/pypi/pyversions/charter-ai" alt="Python versions"></a>
<a href="https://github.com/r28ai/charter/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
<a href="https://github.com/r28ai/charter/actions/workflows/ci.yml"><img src="https://github.com/r28ai/charter/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://docs.r28.ai/charter"><img src="https://img.shields.io/badge/docs-docs.r28.ai-blue" alt="Docs"></a>
</p>

<video src="https://github.com/user-attachments/assets/0fca6e12-ba3d-4a5c-9db3-75a76f373eca"
       poster="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-demo-still.webp"
       controls autoplay loop muted playsinline width="860">
  <img src="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-demo-still.webp"
       alt="Declaring a Gmail tool, the request Charter puts on the wire, and Gmail's 200 OK. Then pricing a Linear tool's schema and pinning a value out of the model's reach."
       width="860">
</video>

</div>

# Charter

You define the schema, the model fills in the args, and Charter does the plumbing:
the request, the auth, the wire format. The same declaration decides what the model
can see and send. No glue code.

A library, not a service.
Runs in your process. No proxy, no per-call pricing, no telemetry.

## Installation

```bash
pip install charter-ai
```

[550 tools across fifteen APIs](https://github.com/r28ai/charter#coverage) ship with
it, on two dependencies: `pydantic>=2.9,<3` and `httpx>=0.27,<1`. Packs never add more.
The upper bounds are so a fresh install cannot silently resolve to pydantic 3.0 the day
it ships.

> [!TIP]
> Need an API that isn't here? Point your coding agent at the
> [pack-writing skill](https://github.com/r28ai/charter/blob/main/skills/writing-charter-packs/SKILL.md) and it writes the pack.

## Call a tool that ships

Every pack is already declared. Point one at a credential and invoke it. Stripe takes
an [API key](https://docs.stripe.com/keys):

```python
import asyncio
import logging

from charter.packs import stripe

logging.basicConfig(format="%(message)s")
logging.getLogger("charter").setLevel(logging.INFO)

stripe.configure("sk_test_...")


async def main():
    await stripe.customers_create.ainvoke({"email": "ada@example.com", "name": "Ada Lovelace"})


asyncio.run(main())
```

```
customers_create       POST v1/customers               200    782ms  ↑     33 B  ↓     661 B →     111 B  (83%)
```

**`↓ 661 B → 111 B` is the part to look at.** Stripe answered with twenty-three fields and
the model read six. The rest never entered the context window. Every pack trims by
default, and `tool.derived(name=..., response_handler=...)` changes that on any tool.
`pass_through` hands back the whole response.
[Response handling](https://docs.r28.ai/charter/reference/response-handling). The line
itself is one INFO record per call, with no sink to configure.

Turn the level up to DEBUG and the record carries the URL, the headers and the body as
sent. Credentials are masked and base64 truncated before they reach the record, so a
log you paste into a bug report cannot leak a key:

```
HTTP → POST https://api.stripe.com/v1/customers
      headers: {"stripe-version": "2026-08-26.dahlia", "authorization": "Bearer sk_***"}
      body: {"email": "ada@example.com"}
```

**The pinned API version, the injected credential and the assembled body appear nowhere
in the code above.** [Seeing the wire](https://docs.r28.ai/charter/running/observability#seeing-the-wire)
has the ten-line formatter that renders it.

An OAuth pack is the same call with a credential provider instead of a key.
`EnvTokenProvider` comes from `charter.auth`:
`gmail.configure(EnvTokenProvider("GOOGLE_ACCESS_TOKEN"))`, then
`await gmail.messages_list.ainvoke({"q": "is:unread", "maxResults": 5})`.

## A tool is four markers and a URL

`Path`, `Query`, `Body`, `Format`. That is the core, and there is no abstraction
underneath it. You read the API's reference page and write down what it says, field by
field, in the dumbest possible way, on a pydantic model of your own:

```python
import asyncio
from typing import Annotated

from pydantic import BaseModel

from charter import Path, Query, api_key_tool_factory

class ListLineItems(BaseModel):
    session: Annotated[str, Path()]
    limit: Annotated[int, Query()] = 10

stripe = api_key_tool_factory(
    pack="mystripe",
    base_url="https://api.stripe.com/",
    api_key_headers={"Authorization": "Bearer sk_test_..."},
)

list_line_items = stripe(
    name="list_line_items",
    description="List the line items on a checkout session.",
    method="GET",
    url_template="v1/checkout/sessions/{session}/line_items",
    args_schema=ListLineItems,
)


async def main():
    await list_line_items.ainvoke({"session": "cs_test_123", "limit": 5})


asyncio.run(main())
```

Ordinary pydantic, ordinary types. `Path()` interpolates into the URL template and
`Query()` becomes a query parameter. Stripe authenticates with an API key, so this is
one you can paste and run.

`Format` is where a wire format the model should never construct is declared once:

```python
from typing import Annotated

from pydantic import BaseModel

from charter import Body, EmailContent, Format

class SendEmail(BaseModel):
    raw: Annotated[EmailContent, Body(envelop=True), Format("rfc822_base64")]
```

**The model never touches a wire format.** Not MIME headers, not base64 padding, not a
GraphQL document. Every format handled by hand is a library, a spec, and a thing that
drifts when the API moves. Here `Format("rfc822_base64")` is the whole of it: it builds
the RFC 2822 document and encodes it base64url, and `Body(envelop=True)` puts it under
`raw`. No email builder, no Google SDK, nothing added to the two dependencies.
[What that replaces](https://docs.r28.ai/charter/why-charter#what-the-hand-written-tool-carries).

There is no drift between the declaration and the vendor either, because it mirrors
[Gmail's own reference page](https://docs.r28.ai/charter/why-charter#the-declaration-mirrors-the-reference-page)
line for line, which is why a reviewer can check one against the other and
[a coding agent can write one](https://docs.r28.ai/charter/start/coding-agents).

## What no glue code buys

There is no per-endpoint code in Charter, generated or hidden. So when a tool call
fails it was the model's arguments, or it was the API. It was never the tool's logic,
because there is no tool logic. With that variable held still, you can finally tell a
better model from a worse one, and a better prompt from a worse one. Bad arguments do
not reach the API either — [see below](#when-the-model-gets-it-wrong).

Two campaigns, on 15 and 16 September 2026, against live accounts over real API calls,
with no mocks and no recorded fixtures. Two arms over the same tasks, models, prompts
and credentials, differing only in the tool surface: Charter's packs against one generic
HTTP tool per provider, where the model supplies the method, path, query and body
itself. That raw arm is the glue people write first, and its endpoint list is derived
from the pack's own tools so nobody hand-picked what it could reach.
[Full methodology](https://docs.r28.ai/charter/guarantees/measured-results).

| Across 534 measured runs | raw HTTP tool | Charter |
|---|---:|---:|
| malformed GraphQL documents | 32 | **0** |
| calls to endpoints never declared | 10 | **0** |
| base64 the API rejected | 4 | **0** |

## Auth, end to end, without an OAuth library

Declare the server, pick a strategy, done. An env key, a token you already hold, a full
authorization-code client with refresh and rotation, or one credential per end user:
same seam either way, and **no OAuth library**. You never install `google-auth` or a
vendor SDK. Single-flighted refresh, rotation and renewal timing are handled, and you
will not think about them again.

`gmail.configure(EnvTokenProvider(...))` above — `charter.auth.EnvTokenProvider` —
was the simplest of those. The hardest is
the same one line: `SubjectProvider` resolves a different credential per end user, per
call, through an authorization-code client you configure once, with refresh and rotation
handled.
[Getting the grant](https://docs.r28.ai/charter/auth/oauth-flow) has it end to end.

You do not have to know the server's details.
[`discover()`](https://docs.r28.ai/charter/auth/authorization-servers) reads them from
RFC 8414 metadata, which is why an enterprise IdP nobody has heard of needs no special
support. You do not have to know which scopes to ask for either.
[`scopes_for()`](https://docs.r28.ai/charter/auth/oauth-flow) computes them from the
tools you hand out:

```python
from charter.auth import scopes_for
from charter.packs import gmail

scopes_for([gmail.messages_list])    # ['https://www.googleapis.com/auth/gmail.modify']
scopes_for([gmail.threads_delete])   # ['https://mail.google.com/']
```

> [!NOTE]
> Your consent screen stops saying "read, send, delete and manage all your email"
> unless you hand out the tool that needs it. That is a signup-rate number before it
> is a security one.

## Policy that lives on the declaration

**[`pin`](https://docs.r28.ai/charter/tools/projections) fixes a value the model can neither see nor set.** Not a prompt instruction,
not a check afterwards: absent from the schema it fills in, present in the one the
runtime executes, indistinguishable on the wire from a value you passed by hand. A
customer id, a region, a year, a sandbox flag. One line where otherwise it is plumbing:

```python
from charter import format_egress_map
from charter.packs import gdrive

search_documents = gdrive.files_list.derived(
    name="search_documents",
    pin={"q": "mimeType='application/vnd.google-apps.document'"},
)

print(format_egress_map([search_documents]))
```

```
search_documents  (GET drive/v3/files)
  visible to the model (10):
    + page_size
    + page_token
    ...
  withheld (5):
    - q  [pinned] = "mimeType='application/vnd.google-apps.document'"
```

**[`Mode`](https://docs.r28.ai/charter/boundary/mode-system) makes one tool behave several ways.** The string is arbitrary, so one
schema covers whatever you need it to:

- **Versioning:** `Mode("v1")`, `Mode("v2")`
- **A/B testing:** `Mode("A")`, `Mode("B")`, `Mode("A, B")`
- **Plan tiers:** `Mode("pro")`, `Mode("max")`
- **Regional rules:** `Mode("uk")`, `Mode("fr")`, `Mode("us")`, `Mode("eu")`
- **Read vs write:** `Mode("read")`, `Mode("write")`

`ToolSession(tools, mode=plan_of(user))` puts a label in force across every tool it
holds, replacing a `TOOLSETS = {"free": [...], "pro": [...]}` dict and the code that
chooses between its entries. The label sits beside the one each tool was declared with
rather than replacing it, so a pack's own `create`/`update` split survives and you do
not have to read a pack to predict what keying it to a tier will do. `static_body`,
`static_query` and `static_headers` do the same at the factory, for a constant every
tool in a pack must send and the model must never see.

## Tune the surface before you tune the prompt

> [!IMPORTANT]
> A pack mirrors its API rather than abstracting it, so a tool is exactly as large as the
> endpoint behind it. That is the trade that keeps a declaration from drifting, and it is
> why some tools arrive enormous.

Linear's `IssueFilter` carries every condition the API accepts, which renders as 187KB of
schema. To address that, a [projection](https://docs.r28.ai/charter/tools/projections) does two things with one edit:

- **Scope.** It narrows what the tool can do.
- **Context.** It narrows how much of the context window the tool occupies. A schema is in
  the prompt on every turn, before the model has read the task, so it is part of what the
  model decides with.

We hit this on Linear, running the benchmark. The fix was to cut the filter down to the
conditions a triage agent actually uses. Thirty generations per cell, temperature 0, one
task:

| the filter the model was given | bytes | glm-5p3-flash | deepseek-v4p1 | nemotron-lightning |
|---|---:|---:|---:|---:|
| removed entirely | 1,131 | 0/30 | 0/30 | 0/30 |
| the full mirror | 187,655 | 22/30 | **400 ×30** | **400 ×30** |
| curated | 15,531 | 28/30 | **30/30** | 4/30 |

Deleting the filter is the first row: a list tool that cannot narrow a list, so all three
models page the whole team 250 issues at a time. A prompt does not reach this either. The
same model used the filter 21/21 times when the schema was accidentally flat and 0/40
after — the capability was never missing, the shape was. The `400`s are the extreme case.
The byte counts in that table are what the harness
actually sent in September; the token counts in the code below are what the current
package produces, which is why they do not divide into each other exactly.

> [!TIP]
> **The recipe, for a tool that is bigger than the job you have for it.**
> 1. `schema_tokens(tool)` — decide whether it is worth touching at all.
> 2. `tool.paths()`, then `paths(under=..., by_cost=True)` — find the branch that is the cost.
> 3. `tool.derived(name=..., keep={...})` — cut it, and name the result.
> 4. `schema_tokens` and `paths()` again — confirm you got what you meant, and
>    [`format_egress_map`](https://docs.r28.ai/charter/reference/observability) to see what the model can still reach.

Steps 1 and 2. `by_cost=True` prices a level instead of naming it, each path really pruned
and the schema regenerated, so the number is what cutting it will do:

```python
from charter import schema_tokens
from charter.packs import linear

schema_tokens(linear.issues_list_full)            # 45072
linear.issues_list_full.paths()                   # ['variables']
linear.issues_list_full.paths(under="variables")
# ['first', 'after', 'filter', 'order_by', 'include_archived']

linear.issues_list_full.paths(under="variables", by_cost=True)
# [PathCost(path='filter',   tokens=44828),
#  PathCost(path='order_by', tokens=52),
#  PathCost(path='first',    tokens=45), ...]
```

One field of five is 44,828 of the 45,072, and nothing about its name said so.

Step 3 is the only one with judgement in it, and the question is about the job rather than
the schema: which conditions does this agent narrow a list by? For triage, the issue's own
fields plus one level into the four relations that identify work. That is the curated row
above:

```python
from charter import schema_tokens
from charter.packs import linear

F = "variables.filter."

issues_list_triage = linear.issues_list_full.derived(
    name="issues_list_triage",
    keep={
        F + "id", F + "number", F + "title", F + "priority",
        F + "due_date", F + "created_at", F + "updated_at", F + "completed_at",
        F + "state.type", F + "state.name",
        F + "assignee.email", F + "assignee.name",
        F + "team.key", F + "team.name",
        F + "labels.name",
    },
)

schema_tokens(issues_list_triage)    # 3458
```

Write the full dotted path: `keep={"labels"}` matches more than 200 paths on this schema
and raises rather than guessing. And name `team.key`, not `team` — keeping a relation
keeps its whole subtree, which drags the cycle back in and lands you at 46,313 tokens,
larger than what you started with.

> [!NOTE]
> **For Linear you do not have to run this.** The pack ships narrowed: `linear.issues_list`
> is curated at 7,652 tokens, and sixteen more with it. Each keeps an undiminished `*_full`
> twin, held out of `TOOLS`, for a caller who needs the complete filter.

**The same edit is a permission.** A Google `documents` scope does all 33 kinds of edit
as one indivisible grant, and `keep` says "may edit text, may not delete content" about
it:

```python
from charter import schema_tokens
from charter.packs import gdocs

edit_text = gdocs.documents_batch_update.derived(
    name="documents_edit_text",
    keep={"insert_text", "delete_content_range", "replace_all_text"},
)

edit_text.paths(under="body.requests")
# ['replace_all_text', 'insert_text', 'delete_content_range']  — 33 down to 3
schema_tokens(edit_text)    # 1553, from 7336
```

A projection can only ever remove, which is what makes the saving and the restriction one
line of code, and what makes it safe to hand to whoever owns the deployment rather than
the pack.

**At the extreme, a schema is not expensive, it is refused.** `IssueFilter` refers back to
itself, and on a schema that does:

> [!WARNING]
> `400 JSON Schema not supported: schema depth exceeds maximum limit of 50` — from the
> provider, before the model saw anything, thirty times out of thirty. It takes every other
> tool in the request with it, so the turn makes no tool call. Recursion is what breaks it,
> not size: the same models accept a larger Sheets tool that has no cycle.

[The long version](https://docs.r28.ai/charter/optimization/context-window) covers the `$defs` arithmetic, what flattening clients do to
a cycle, and why deferral is the other half of this lever rather than a substitute.

## Control what comes back

A schema says what goes out. A [response handler](https://docs.r28.ai/charter/optimization/context-window) says how much of what comes back the
model ever sees, and one Gmail call can otherwise end a conversation on its own: a
base64 body, a dozen response-only fields, a block tree, avatar URLs eight to a user.

Across the same 534 runs the Charter arm handed the model roughly a quarter of the
bytes the raw arm did, 7,382 against 36,383 per run in one campaign and 10,581
against 39,785 in the other. In the second it had pulled *more* off the wire, not less.
It forwarded less, by the packs' own handlers, with nothing configured.

## Print the boundary

A property enforced by construction is only auditable if something prints it. Two do,
both generated from the declarations the runtime executes, so neither can drift:

- **[`egress_map()`](https://docs.r28.ai/charter/boundary/egress-control)** answers what a security review actually asks. Snapshot it in CI
  and a change to what the model can see becomes a reviewable diff on a pull request.
- **[`format_conflicts()`](https://docs.r28.ai/charter/reference/observability)** prints the rules an API keeps in prose. Google Calendar's
  `syncToken` refuses eight other parameters; that is a property of the schema here,
  checked on every call.

## When a 200 is not a success

Slack answers a rejected request with `200 OK` and `{"ok": false}`. Every GraphQL API
returns 200 with an `errors` array. Linear returns `success: false`, Shopify returns
`userErrors`. Every signal a runtime normally trusts says the write happened, and your
agent tells the user the message sent.

```python
from charter import Envelope

Envelope(errors_field=("errors", "data.*.userErrors"))
```

One line on the factory, enforced on every call including calls by tools added next
year. [The full measured record](https://docs.r28.ai/charter/guarantees/measured-results)
covers both campaigns, including where task success was a wash and the one template
that goes the other way.

## When the model gets it wrong

Errors go to whoever can act on them. That is what keeps a bad argument worth one turn.
A camelCase key inside a nested object, a nested object serialised as a JSON string: the
runtime [absorbs those](https://docs.r28.ai/charter/running/llm-input-auto-corrections),
and nobody is told. A declaration the runtime cannot use comes to you, with a link. What
is left is the model's to fix, and it fails before the request goes out, quoting what it
sent:

```
Validation error:
- **maxResults**: Input should be a valid integer, unable to parse string as an integer (got 'ten')
- **timeMin**: Input should be a valid datetime or date, invalid character in year (got 'next tuesday')
```

**"Invalid parameter" tells a model what to stop doing, not what to do instead.** So the
rule `format_conflicts()` prints for a reviewer above is the same one the model reads on
the turn it breaks it:

```
Validation error:
- **(input)**: Value error, q, timeMax, timeMin cannot be combined with syncToken.
  An incremental sync continues the query the token came from, so the filters have
  to be the ones already in effect. Drop syncToken to run a fresh query, or drop
  the others to continue the sync.
```

Three offenders in one message instead of three round trips, in the vendor's own
spelling, with both exits named. All of that comes out of one
`ConflictsWith(..., reason=...)` on the field. No documentation link either: a model pays
for the URL in context and cannot follow it.
[Errors](https://docs.r28.ai/charter/running/tool-validation-error-handling).

## The rest of the vocabulary

`Gloss` tells the model what the API's own description leaves out, without replacing
it, which is where a Stripe field that needs a hint gets one. `ConflictsWith` declares
which parameters an endpoint refuses together. Then
[`Case`, `KeyCase`, `WireName`, `TransportOverride`, `partial_of` and `Pagination`](https://docs.r28.ai/charter/reference/markers).

## Coverage

| Pack | Import | Tools | Auth | The awkward part |
|---|---|---|---|---|
| Gmail | `charter.packs.gmail` | 24 | OAuth bearer | Mail goes out as base64url RFC 2822 and comes back parsed |
| Google Calendar | `charter.packs.gcalendar` | 13 | OAuth bearer | camelCase in the query, snake_case in the body |
| Google Sheets | `charter.packs.gsheets` | 17 | OAuth bearer | Cells are protobuf JSON, not plain values |
| Google Docs | `charter.packs.gdocs` | 3 | OAuth bearer | One batch request, thirty-three alternative edit types |
| Google Drive | `charter.packs.gdrive` | 25 | OAuth bearer | PATCH takes a subset of the create body |
| Google Forms | `charter.packs.gforms` | 6 | OAuth bearer | One resource, different fields on create and update |
| Slack | `charter.packs.slack` | 18 | OAuth bearer | Rejected writes answer HTTP 200 |
| GitHub | `charter.packs.github` | 139 | OAuth bearer | Three constant headers, one of them a pinned API version |
| Stripe | `charter.packs.stripe` | 59 | API key | Form-encoded, bracketed query, DELETE with a body |
| Linear | `charter.packs.linear` | 128 | API key | GraphQL, with the cursor nested inside the response |
| Shopify | `charter.packs.shopify` | 22 | API key | No fixed host, and every price is a nested `MoneyBag` |
| Notion | `charter.packs.notion` | 35 | OAuth bearer | 100 blocks and two levels of children per write |
| Firecrawl | `charter.packs.firecrawl` | 43 | API key | camelCase wire, and some failures answer HTTP 200 |
| Granola | `charter.packs.granola` | 9 | API key | Four kinds of actor in one discriminated union |
| Tavily | `charter.packs.tavily` | 9 | API key | Research is asynchronous: create, then poll |

Every [pack](https://docs.r28.ai/charter/packs/overview) has its LLM schema built, its
egress map checked against that schema, and its OpenAI function definition validated in
the suite.

## What Charter is not

Three shapes sit near this one, and none of them is it:

- an **orchestrator** (LangChain, LangGraph, Google ADK) sits on top of the tool
  execution layer. It doesn't deal with the underlying request, and isn't designed to;
- a **catalogue** (Zapier, Composio, Arcade) runs the call for you, remotely, priced
  per call, and sells on catalogue size. Here you write the pack;
- a **protocol** (MCP) governs what the model sees and structurally cannot reach the
  API side, because it never talks to the upstream API.

Charter compiles to MCP and adapts to each of the others. None of them is a library you
run yourself that decides what goes out.

## Conformance

A declaration can be wrong in a way no per-tool test notices: the call returns 200, the
suite stays green, and the filter you declared was silently discarded on the way out. So
nineteen properties that must hold for *every* pack are checked separately, without
knowing anything about any particular API, and each one also runs against a pack broken
on purpose in the specific way the bug it guards against broke it. Most were written
after a bug rather than before one: four packs added in a single week produced six, five
of them silent, including a factory-level `Pagination` that labelled twenty-two retrieve
and write endpoints with a cursor parameter they do not accept. [Conformance](https://docs.r28.ai/charter/guarantees/conformance) has the
list.

What none of it tells you is whether a schema still matches the vendor's live API.
Catching that drift needs their published spec.

## What this can't express

Charter describes *one request*, and [declarative has edges](https://docs.r28.ai/charter/guarantees/limitations).
Pagination loops, multi-call compositions and retry policies are out of scope by design,
because that is orchestration and it belongs in your agent. Multipart upload, request
signing, header-based pagination markers, dynamic GraphQL selection sets and streaming
are not supported yet. A schema cannot change mid conversation, because it was
serialised into a prompt the model is still reading; a surface that has to change means
a new session. And `Mode` is schema visibility, not authorization: it decides what a
tool exposes, never who may call it.

## Docs

| | |
|---|---|
| **Start** | [Quickstart](https://docs.r28.ai/charter/start/quickstart) · [Installation](https://docs.r28.ai/charter/start/installation) · [Why Charter](https://docs.r28.ai/charter/why-charter) |
| **Packs** | [Overview](https://docs.r28.ai/charter/packs/overview) · [Write one with a coding agent](https://docs.r28.ai/charter/start/coding-agents) |
| **The boundary** | [Egress control](https://docs.r28.ai/charter/boundary/egress-control) · [Mode system](https://docs.r28.ai/charter/boundary/mode-system) · [Quick reference](https://docs.r28.ai/charter/boundary/mode-quick-reference) |
| **The wire** | [Wire contract](https://docs.r28.ai/charter/tools/wire-contract) · [Envelopes](https://docs.r28.ai/charter/tools/envelopes) · [Transforms](https://docs.r28.ai/charter/tools/transforms) · [Key case](https://docs.r28.ai/charter/tools/key-case-cascade) |
| **Credentials** | [Getting the grant](https://docs.r28.ai/charter/auth/oauth-flow) · [Authorization servers](https://docs.r28.ai/charter/auth/authorization-servers) · [API keys](https://docs.r28.ai/charter/auth/api-key-tool-factory) |
| **Running it** | [What a call cost](https://docs.r28.ai/charter/running/observability) · [Adapters and MCP](https://docs.r28.ai/charter/using/adapters) · [Errors](https://docs.r28.ai/charter/running/tool-validation-error-handling) |
| **Guarantees** | [Conformance](https://docs.r28.ai/charter/guarantees/conformance) · [Measured results](https://docs.r28.ai/charter/guarantees/measured-results) · [Limitations](https://docs.r28.ai/charter/guarantees/limitations) |
| **Reference** | [API reference](https://docs.r28.ai/charter/reference/overview) · [AGENTS.md](https://github.com/r28ai/charter/blob/main/AGENTS.md) |

## Development

```bash
uv venv
uv pip install -e ".[dev,langchain,mcp]"
uv run pytest
uv run ruff check src tests examples
uv run pyright --pythonpath .venv/bin/python src
```

## License

Apache 2.0. See [LICENSE](https://github.com/r28ai/charter/blob/main/LICENSE) and [NOTICE](https://github.com/r28ai/charter/blob/main/NOTICE).

Charter is built by [R28](https://r28.ai).
