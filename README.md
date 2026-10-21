<div align="center">

<img src="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-mark-144.png" alt="" width="72" height="72">

<h3>Decide what your agent sees, sends and gets back, in every API it touches.</h3>

<p>
<a href="https://docs.r28.ai/charter">Documentation</a> ·
<a href="https://docs.r28.ai/charter/start/quickstart">Quickstart</a> ·
<a href="https://docs.r28.ai/charter/start/coding-agents">Coding agents</a> ·
<a href="https://docs.r28.ai/charter/packs/overview">Packs</a>
</p>

<p>
<a href="https://pypi.org/project/charter-ai/"><img src="https://img.shields.io/pypi/v/charter-ai?v=11" alt="PyPI"></a>
<a href="https://pypi.org/project/charter-ai/"><img src="https://img.shields.io/pypi/pyversions/charter-ai" alt="Python versions"></a>
<a href="https://github.com/r28ai/charter/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
<a href="https://github.com/r28ai/charter/actions/workflows/ci.yml"><img src="https://github.com/r28ai/charter/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://docs.r28.ai/charter"><img src="https://img.shields.io/badge/docs-docs.r28.ai-blue" alt="Docs"></a>
</p>

</div>

# Charter

Charter is an open-source Python tool-definition layer for agents. Wire tools by hand and
you're hoping for the best, blind spots and all. Vendor toolkits, MCP servers and catalog
platforms hand you someone else's.

Charter lets you control every aspect of yours, and checks each call before it's sent. It
works for any HTTP API, including your own internal ones.

A library, not a service.
Runs in your process. No proxy, no per-call pricing, no telemetry.

## Installation

```bash
pip install charter-ai
```

Requires Python 3.10+. The only dependencies are `pydantic` and `httpx`.

## Quickstart

You write rules as an annotated Pydantic model that mirrors the API field by field, so your
[coding agent](https://github.com/r28ai/charter/blob/main/skills/declaring-charter-tools/SKILL.md) can check it against the docs for drift.

Then you can add your own rules on top of the API's, in Pydantic too, using any check you can
write in Python.

Unlike a plain Pydantic model, yours also marks each field as path, query or body, and Charter
builds the request from it. Unit tests can check every rule without anything reaching the API.

```python
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from charter import Body, ToolValidationError, api_key_tool_factory


class Refund(BaseModel):
    charge: Annotated[str, Body()]
    amount: Annotated[int, Body()] = Field(
        gt=0, le=10_000,  # yours: at most $100
    )
    reason: Annotated[
        Literal["duplicate", "requested_by_customer"],  # yours: no "fraudulent"
        Body(),
    ]


payments = api_key_tool_factory(
    pack="payments",
    base_url="https://httpbin.org/anything/",  # stands in for a payments API
    api_key_headers={"Authorization": "Bearer sk_test_123"},
    body_format="form",
)
refund = payments(
    name="refund",
    description="Refund a charge.",
    method="POST",
    url_template="v1/refunds",
    args_schema=Refund,
)

refund.invoke({"charge": "ch_3MmlLr", "amount": 1500, "reason": "duplicate"})  # sent

try:
    refund.invoke({"charge": "ch_3MmlLr", "amount": 15000, "reason": "fraudulent"})  # refused
except ToolValidationError as refused:
    print(refused)
```

The first call goes out (httpbin echoes it back):

```
POST https://httpbin.org/anything/v1/refunds
Authorization: Bearer sk_test_123
charge=ch_3MmlLr&amount=1500&reason=duplicate
```

The model fills in three fields. The key, the URL and the limits stay yours.

The second call is refused before it leaves your process, and the model gets this back,
naming each field and what it sent:

```
Validation error:
- **amount**: Input should be less than or equal to 10000 (got 15000)
- **reason**: Input should be 'duplicate' or 'requested_by_customer' (got 'fraudulent')
```

It can fix the call or stop; Charter never improvises.

## What your agent sees, sends and gets back

| | What Charter does | Measured |
|---|---|---|
| **Sees** | Cuts a tool down to the fields the job needs | On Linear's issue list, deepseek-v4p1 was refused 30/30 with the full filter and succeeded 30/30 with a curated one ([details](#shape-a-tool)) |
| **Sends** | Builds wire formats like MIME, base64 and GraphQL, so the model fills in plain fields | Over 534 runs, a raw HTTP tool sent 32 malformed GraphQL documents and tried 10 calls to endpoints never declared; Charter did neither ([details](#control-what-goes-out)) |
| **Gets back** | Trims responses, and raises when a `200` is really a failure | GitHub sends 346.6 KB, the model gets 10.7 KB ([details](#control-what-comes-back)) |

## Who it's for

| If you're... | Charter gives you |
|---|---|
| A SaaS adding an agent that works in your users' Gmail, Stripe or Notion | [Per-user OAuth](https://docs.r28.ai/charter/auth/your-users) with your app's name on the consent screen, and [ready-made tools](https://docs.r28.ai/charter/packs/overview) |
| On Composio or Zapier | Tools you own, with no per-call fees, and your users' data stays on your servers ([how it compares](#how-charter-compares)) |
| Writing tool glue by hand | Catches the bugs hand-written glue lets through: a bad argument is [refused before it's sent](#quickstart), and an [`Envelope`](https://docs.r28.ai/charter/reference/envelopes-and-pagination#envelope) raises when a `200` is really a failure |
| Running a small or open model | Tools cut down to the fields the job needs ([`derived`](https://docs.r28.ai/charter/tools/projections)), and a one-line hint on the exact field it keeps getting wrong ([`Gloss`](https://docs.r28.ai/charter/reference/markers#gloss)) |
| Facing a security review | What the agent can see and send, enforced in code and diffed in review: values it can't see or change ([`pin`](https://docs.r28.ai/charter/tools/projections#pin)), fields per pricing tier or region ([`Mode`](https://docs.r28.ai/charter/boundary/mode-system)), OAuth scopes worked out from the tools you hand out ([`scopes_for`](https://docs.r28.ai/charter/reference/oauth#scopes_for)), and a list of everything each tool can reach ([`egress_map`](https://docs.r28.ai/charter/reference/observability#egress_map)) |

## Examples

[`examples/`](https://github.com/r28ai/charter/tree/main/examples) has fifteen short
scripts, numbered in reading order. Most run without an account.

| Example | Shows |
|---|---|
| [`02_use_a_pack.py`](https://github.com/r28ai/charter/blob/main/examples/basics/02_use_a_pack.py) | A shipped tool: GitHub sends 346.6 KB, the model gets 10.7 KB |
| [`03_hand_to_a_model.py`](https://github.com/r28ai/charter/blob/main/examples/basics/03_hand_to_a_model.py) | Tools in Charter's own agent loop, with any OpenAI-compatible model |
| [`05_errors_for_the_model.py`](https://github.com/r28ai/charter/blob/main/examples/basics/05_errors_for_the_model.py) | A bad argument refused before sending, with a fix the model can apply |
| [`10_many_tools.py`](https://github.com/r28ai/charter/blob/main/examples/basics/10_many_tools.py) | 613 tools in one session, starting from 4,476 tokens |
| [`13_one_tool_per_plan.py`](https://github.com/r28ai/charter/blob/main/examples/basics/13_one_tool_per_plan.py) | One tool with a different field set per plan |
| [`connect/`](https://github.com/r28ai/charter/tree/main/examples/connect) | Your own account and your users', by OAuth or API key |

## Shape a tool

A tool's schema is in the prompt on every turn, so its size and shape change what the
model does. We tested this on Linear's issue list, thirty runs per cell at temperature 0:

| the filter the model was given | bytes | glm-5p3-flash | deepseek-v4p1 | nemotron-lightning |
|---|---:|---:|---:|---:|
| removed entirely | 1,131 | 0/30 | 0/30 | 0/30 |
| the API's full filter | 187,655 | 22/30 | **400 ×30** | **400 ×30** |
| curated | 15,531 | 28/30 | **30/30** | 4/30 |

**400 ×30** means the provider rejected the request all 30 times, before the model saw it: the full
filter is recursive and nests deeper than the provider accepts (`schema depth exceeds maximum limit of 50`).

`paths(by_cost=True)` shows where a tool's tokens go:

```python
from charter import schema_tokens
from charter.packs import linear

schema_tokens(linear.issues_list_full)            # 45072
linear.issues_list_full.paths(under="variables", by_cost=True)
# [PathCost(path='filter',   tokens=44828),
#  PathCost(path='order_by', tokens=52), ...]
```

`derived(keep=...)` trims it to what a triage agent needs:

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

Keep `team.key`, not `team`: a whole relation brings the recursive filter back and lands you at 46,313 tokens.
The shipped `linear.issues_list` is curated at 7,652 tokens.

See also [`08_cut_a_tool.py`](https://github.com/r28ai/charter/blob/main/examples/basics/08_cut_a_tool.py), and
[`11_rules_on_fields.py`](https://github.com/r28ai/charter/blob/main/examples/basics/11_rules_on_fields.py) for hints on a single field
instead of in the system prompt.

## Control what goes out

`Format` builds wire formats so the model fills in plain fields. Here the model writes
`to`, `subject` and `body`, and Charter sends base64url RFC 2822 under `raw`:

```python
from typing import Annotated

from pydantic import BaseModel

from charter import Body, EmailContent, Format


class SendEmail(BaseModel):
    raw: Annotated[EmailContent, Body(envelop=True), Format("rfc822_base64")]
```

We measured this over 534 runs on live accounts, against giving the model a generic HTTP
tool instead ([methodology](https://docs.r28.ai/charter/guarantees/measured-results)):

| Across 534 measured runs | raw HTTP tool | Charter |
|---|---:|---:|
| malformed GraphQL documents | 32 | **0** |
| calls to endpoints never declared | 10 | **0** |
| base64 the API rejected | 4 | **0** |

`scopes_for` works out the OAuth scopes to request from the tools you hand out:

```python
from charter.auth import scopes_for
from charter.packs import gmail

scopes_for([gmail.messages_list])    # ['https://www.googleapis.com/auth/gmail.modify']
scopes_for([gmail.threads_delete])   # ['https://mail.google.com/']
```

More controls:

- `pin` sets a value the model can't see or change ([`12_pin_a_value.py`](https://github.com/r28ai/charter/blob/main/examples/basics/12_pin_a_value.py))
- `Mode` gives a tool different fields per plan or region ([`13_one_tool_per_plan.py`](https://github.com/r28ai/charter/blob/main/examples/basics/13_one_tool_per_plan.py))
- `egress_map` lists everything the model can reach, for code review ([`15_review_the_boundary.py`](https://github.com/r28ai/charter/blob/main/examples/basics/15_review_the_boundary.py))

## Control what comes back

Packs trim their responses by default, and you can do the same on your own tools with
`response_handler` ([`06_trim_responses.py`](https://github.com/r28ai/charter/blob/main/examples/basics/06_trim_responses.py)). Some APIs answer a failure with
`200`, like Slack's `{"ok": false}` or a GraphQL `errors` list. An `Envelope` turns those
into errors:

```python
from charter import Envelope

Envelope(errors_field=("errors", "data.*.userErrors"))
```

## Use with your framework

```python
from charter import ToolSession
from charter.adapters.openai import to_openai_tools
from charter.packs import github

session = ToolSession(github.TOOLS)
tools = to_openai_tools(session)  # function definitions for any chat-completions API
```

- `charter.adapters.openai.run()` runs the tool-calling loop with any OpenAI-compatible
  client ([`03_hand_to_a_model.py`](https://github.com/r28ai/charter/blob/main/examples/basics/03_hand_to_a_model.py))
- `CharterMiddleware` adds a session to a LangChain agent
  ([`frameworks/`](https://github.com/r28ai/charter/tree/main/examples/frameworks))
- `charter-mcp --pack gmail` serves a pack over MCP

## Ready-made tools

613 tools across sixteen APIs ship with Charter, from Gmail and Slack to Stripe and Linear
([full list](https://docs.r28.ai/charter/packs/overview#coverage)). You can extend them with
your own tools, [request a pack](https://github.com/r28ai/charter/issues), and [contributions are welcome](https://github.com/r28ai/charter/blob/main/CONTRIBUTING.md).

## How Charter compares

If you're connecting an agent to your users' Gmail, Stripe or Notion, there are usually
two ways to go.

You can use each vendor's own library and wire it up yourself. That's direct and it's
yours, but every API comes with its own client, its own auth and its own plumbing to
write and keep up.

Or you can use a platform like Zapier or Composio. Easy too, but your users see
"Authorize Zapier" instead of your product's name, right when they're deciding whether to
connect. You pay for every tool call and get rate-limited on top. And your users' data
goes through someone else's servers.

Charter works like going direct. You register your own app with Google, Stripe or Notion,
and your users authorize you. It's as direct as the vendors' own libraries, without the
platform's downsides: no per-call billing, no remote
server, all yours.

It's not an agent framework either. LangChain, the OpenAI SDK or an MCP client runs the
loop, and Charter is the tools it calls.

## Limitations

Charter describes one request; loops, retries and multi-step flows belong in your agent.
Multipart upload, request signing and streaming are not supported yet. A session applies
one `Mode` label at a time, and `Mode` controls what a tool exposes, not who may call it.
See [limitations](https://docs.r28.ai/charter/guarantees/limitations).

## Documentation

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

## Contributing

```bash
uv venv
uv pip install -e ".[dev,langchain,mcp]"
uv run pytest
uv run ruff check src tests examples
uv run pyright --project . --pythonpath .venv/bin/python src
```

See [`CONTRIBUTING.md`](https://github.com/r28ai/charter/blob/main/CONTRIBUTING.md) for how
to contribute, and [`AGENTS.md`](https://github.com/r28ai/charter/blob/main/AGENTS.md) for
the codebase rules.

## License

Apache 2.0. See [LICENSE](https://github.com/r28ai/charter/blob/main/LICENSE) and [NOTICE](https://github.com/r28ai/charter/blob/main/NOTICE).

Charter is built by [R28](https://r28.ai).
