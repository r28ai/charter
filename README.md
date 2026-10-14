<div align="center">

<img src="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-mark-144.png" alt="" width="72" height="72">

<h3>Decide what your agent sees, sends and gets back, in every API it touches.</h3>

<p>
<a href="https://docs.r28.ai/charter">Documentation</a> ·
<a href="https://docs.r28.ai/charter/start/quickstart">Quickstart</a> ·
<a href="https://docs.r28.ai/charter/packs/overview">Packs</a> ·
<a href="https://docs.r28.ai/charter/start/coding-agents">Write a pack</a> ·
<a href="https://github.com/r28ai/charter/issues">Request a pack</a>
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

Charter is an open-source Python library for building agent tools from API declarations.
You describe an API call as a Pydantic model, with each field marked as path, query or
body. Charter makes the request and handles auth, and you control what the model sees and
what it gets back. It works with any HTTP API, including your own.

A library, not a service.
Runs in your process. No proxy, no per-call pricing, no telemetry.

## Highlights

- **Any HTTP API.** A tool is a Pydantic model and a URL. A coding agent can write one
  from the API's docs with [the skill](https://github.com/r28ai/charter/blob/main/skills/declaring-charter-tools/SKILL.md).
- **Shape what the model sees.** Price a tool's schema, cut it to the job, add guidance on
  a single field, and keep hundreds of tools behind one search tool.
- **Control what it sends.** Wire formats (MIME, base64, GraphQL) are built for the model,
  bad arguments are refused before sending with errors it can act on, and values can be
  pinned out of its reach.
- **Control what comes back.** Responses are trimmed to what the model needs, and APIs
  that report failure inside a `200` raise.
- **Your users' accounts.** Per-user OAuth with refresh and rotation, and API keys, with no
  OAuth library or vendor SDK.
- **Auditable.** `egress_map` lists what every tool lets the model reach, so a change to it
  is a diff in review.
- **Fits your stack.** LangChain, any OpenAI-compatible API, and MCP.

## Installation

```bash
pip install charter-ai
```

Requires Python 3.10+. The only dependencies are `pydantic` and `httpx`.

## Quickstart

```python
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from charter import Body, Path, Query, api_key_tool_factory


class CreateEvent(BaseModel):
    calendar: Annotated[str, Path()] = Field(description="Which calendar, e.g. 'primary'.")
    notify: Annotated[bool, Query()] = Field(False, description="Email the attendees.")
    title: Annotated[str, Body()] = Field(description="What the meeting is about.")
    start: Annotated[datetime, Body()] = Field(description="When it starts.")
    attendees: Annotated[list[str], Body()] = Field([], description="Who to invite, by email.")


calendar_api = api_key_tool_factory(
    pack="calendar",
    base_url="https://httpbin.org/anything/",  # stands in for a calendar API
    api_key_headers={"Authorization": "Bearer sk_live_123"},
)
create_event = calendar_api(
    name="create_event",
    description="Put a meeting on a calendar.",
    method="POST",
    url_template="calendars/{calendar}/events",
    args_schema=CreateEvent,
)

print(create_event.to_json_schema())  # the function definition the model gets
create_event.invoke({"calendar": "primary", "notify": True, "title": "Coffee with Ada",
                     "start": "2026-10-20T10:00:00", "attendees": ["ada@example.com"]})
```

The request that goes out (httpbin echoes it back):

```
POST https://httpbin.org/anything/calendars/primary/events?notify=true
Authorization: Bearer sk_live_123
{"title": "Coffee with Ada", "start": "2026-10-20T10:00:00", "attendees": ["ada@example.com"]}
```

Charter adds the key. The model never sees it.

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
| the full mirror | 187,655 | 22/30 | **400 ×30** | **400 ×30** |
| curated | 15,531 | 28/30 | **30/30** | 4/30 |

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
your own tools, and [contributions are welcome](https://github.com/r28ai/charter/blob/main/CONTRIBUTING.md).

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
and your users authorize you. It's as direct as the vendors' own libraries and about as
easy as a platform, without the platform's downsides: no per-call billing, no remote
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
