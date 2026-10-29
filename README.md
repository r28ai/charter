<div align="center">

<img src="https://raw.githubusercontent.com/r28ai/charter/main/docs/images/charter-mark-144.png" alt="" width="72" height="72">

<h3>Your agent's access to customer accounts, enforced per field, diffed in review.</h3>

<p>Answer "what can your agent access?" straight from the code that runs.</p>

<p>
<a href="https://docs.r28.ai/charter/start/quickstart">Quickstart</a> ·
<a href="https://github.com/r28ai/charter/tree/main/examples">Examples</a> ·
<a href="https://docs.r28.ai/charter">Documentation</a> ·
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

Charter is an open-source Python library for agents that act in your customers' accounts
through APIs. Each tool is a Pydantic model that mirrors the API field by field, with your
rules on top, and every call is checked against it before it's sent. Your app says whose
account each call is for, and the model can't change it. The same declarations list
everything each tool can reach, for code review and for your customer's security team. It
works for any HTTP API, public or private.

A library, not a service.
Runs in your process. No proxy, no per-call pricing, no telemetry.

## Installation

```bash
pip install charter-ai
```

Requires Python 3.10+. The only dependencies are `pydantic` and `httpx`.

## Quickstart

An agent acting for one customer looks up two orders. A rule like "only this customer's
orders" needs to know whose account the call is for, and that has to come from your app, not
from the model. Mark the field `FromContext()` and pass its value per call:

```python
from typing import Annotated

from pydantic import BaseModel, model_validator

from charter import FromContext, Path, ToolValidationError, api_key_tool_factory, format_egress_map

OWNERS = {"ord_1": "cus_42", "ord_2": "cus_7"}  # from your database


class GetOrder(BaseModel):
    order_id: Annotated[str, Path()]
    customer_id: Annotated[str, FromContext()]  # your app's, per call

    @model_validator(mode="after")
    def _their_own(self) -> "GetOrder":
        if OWNERS.get(self.order_id) != self.customer_id:
            raise ValueError("That order belongs to another customer.")
        return self


shop = api_key_tool_factory(
    pack="shop",
    base_url="https://httpbin.org/anything/",  # stands in for your API
    api_key_headers={"Authorization": "Bearer sk_test_123"},
)
get_order = shop(
    name="orders_get",
    description="Get one of the customer's orders.",
    method="GET",
    url_template="v1/orders/{order_id}",
    args_schema=GetOrder,
)

for order_id in ("ord_1", "ord_2"):
    try:
        get_order.invoke({"order_id": order_id}, context={"customer_id": "cus_42"})
        print(order_id, "sent")
    except ToolValidationError as refused:
        print(order_id, "refused:", refused.errors[0]["msg"])

print(format_egress_map([get_order]))
```

```
ord_1 sent
ord_2 refused: Value error, That order belongs to another customer.
shop_orders_get  (GET v1/orders/{order_id})
  visible to the model (1):
    + order_id
  withheld (1):
    - customer_id  [context] <- context['customer_id']
```

The model fills in `order_id` and nothing else. A model talked into naming another customer's
order is refused before anything is sent, and so is a call your app made without saying whose
it is. The map comes from the same declarations the runtime executes: commit it, and a change
to what your agent can reach is a diff in review, the list your customer's security team asks
for. [`14_act_for_one_customer.py`](https://github.com/r28ai/charter/blob/main/examples/basics/14_act_for_one_customer.py)
runs it, and [per-call context](https://docs.r28.ai/charter/tools/wire-contract#per-call-context)
has the rest.

## Your rules on any field

Each tool mirrors the API field by field, so your
[coding agent](https://github.com/r28ai/charter/blob/main/skills/declaring-charter-tools/SKILL.md)
can check it against the API's docs. Your own rules go on the same fields: a limit, an allowed
list, or any check you can write in Python. Charter builds the request from the model, and a
unit test can check every rule without anything reaching the API.

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

## What else Charter does

| | What Charter does | Measured |
|---|---|---|
| **Sees** | Cuts a tool down to the fields the job needs | Google Docs' write tool has 33 kinds of edit; cut to the 3 a job needs, its schema goes from 7,336 tokens to 1,553 ([details](https://docs.r28.ai/charter/tools/projections#why-the-tool-is-shaped-this-way)) |
| **Sends** | Builds wire formats like MIME, base64 and GraphQL, so the model fills in plain fields | Over 534 runs, a raw HTTP tool sent 32 malformed GraphQL documents and tried 10 calls to endpoints never declared; Charter did neither ([details](#control-what-goes-out)). Of six calls that break the vendor's own documented rules, Charter refused all six before sending; the APIs' own or most-starred MCP servers let four of five through ([details](https://docs.r28.ai/charter/guarantees/benchmarks#the-same-calls-through-each-tool-layer)) |
| **Gets back** | Trims responses, and raises when a `200` is really a failure | GitHub sends 346.6 KB, the model gets 10.7 KB ([details](#control-what-comes-back)) |

## Who it's for

| If you're... | Charter gives you |
|---|---|
| Facing a security review | What the agent can see and send, enforced in code and diffed in review: whose account a call acts in, set by your app per call ([`FromContext`](https://docs.r28.ai/charter/reference/markers#fromcontext)), values it can't see or change ([`pin`](https://docs.r28.ai/charter/tools/projections#pin)), fields per pricing tier or region ([`Mode`](https://docs.r28.ai/charter/boundary/mode-system)), OAuth scopes worked out from the tools you hand out ([`scopes_for`](https://docs.r28.ai/charter/auth/permissions)), and a list of everything each tool can reach ([`egress_map`](https://docs.r28.ai/charter/reference/observability#egress_map)) |
| A SaaS adding an agent that works in your users' Gmail, Stripe or Notion | [Per-user OAuth](https://docs.r28.ai/charter/auth/your-users) with your app's name on the consent screen, and [ready-made tools](https://docs.r28.ai/charter/packs/overview) |
| On Composio or Zapier | Tools you own, and your users' tokens and data stay on your servers ([how it compares](#how-charter-compares)) |
| Writing tool glue by hand | Catches the bugs hand-written glue lets through: a bad argument is [refused before it's sent](#your-rules-on-any-field), and an [`Envelope`](https://docs.r28.ai/charter/reference/envelopes-and-pagination#envelope) raises when a `200` is really a failure |
| Running a small or open model | Tools cut down to the fields the job needs ([`derived`](https://docs.r28.ai/charter/tools/projections)), and a one-line hint on the exact field it keeps getting wrong ([`Gloss`](https://docs.r28.ai/charter/reference/markers#gloss)) |

## Examples

[`examples/basics/`](https://github.com/r28ai/charter/tree/main/examples/basics) has fourteen
short scripts, numbered in reading order, and none of them needs a key or an account.

| Example | Shows |
|---|---|
| [`03_errors_for_the_model.py`](https://github.com/r28ai/charter/blob/main/examples/basics/03_errors_for_the_model.py) | A bad argument refused before sending, with a fix the model can apply |
| [`08_many_tools.py`](https://github.com/r28ai/charter/blob/main/examples/basics/08_many_tools.py) | 687 tools in one session, starting from 5,009 tokens |
| [`11_one_tool_per_plan.py`](https://github.com/r28ai/charter/blob/main/examples/basics/11_one_tool_per_plan.py) | One tool with a different field set per plan |
| [`14_act_for_one_customer.py`](https://github.com/r28ai/charter/blob/main/examples/basics/14_act_for_one_customer.py) | Your app says whose account each call is for: another customer's order is refused |
| [`use_a_pack.py`](https://github.com/r28ai/charter/blob/main/examples/connect/use_a_pack.py) | A shipped tool, with your GitHub token: GitHub sends 346.6 KB, the model gets 10.7 KB |
| [`openai_loop.py`](https://github.com/r28ai/charter/blob/main/examples/frameworks/openai_loop.py) | Tools in Charter's own agent loop, with any OpenAI-compatible model (needs a model key) |
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

See also [`06_cut_a_tool.py`](https://github.com/r28ai/charter/blob/main/examples/basics/06_cut_a_tool.py), and
[`09_rules_on_fields.py`](https://github.com/r28ai/charter/blob/main/examples/basics/09_rules_on_fields.py) for hints on a single field
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

scopes_for([gmail.messages_list])    # ['https://www.googleapis.com/auth/gmail.readonly']
scopes_for([gmail.threads_delete])   # ['https://mail.google.com/']
```

More controls:

- `pin` sets a value the model can't see or change ([`10_pin_a_value.py`](https://github.com/r28ai/charter/blob/main/examples/basics/10_pin_a_value.py))
- `Mode` gives a tool different fields per plan or region ([`11_one_tool_per_plan.py`](https://github.com/r28ai/charter/blob/main/examples/basics/11_one_tool_per_plan.py))
- `egress_map` lists everything the model can reach, for code review ([`13_review_the_boundary.py`](https://github.com/r28ai/charter/blob/main/examples/basics/13_review_the_boundary.py))

## Control what comes back

Packs trim their responses by default, and you can do the same on your own tools with
`response_handler` ([`04_trim_responses.py`](https://github.com/r28ai/charter/blob/main/examples/basics/04_trim_responses.py)). Some APIs answer a failure with
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
  client ([`openai_loop.py`](https://github.com/r28ai/charter/blob/main/examples/frameworks/openai_loop.py))
- `CharterMiddleware` adds a session to a LangChain agent
  ([`frameworks/`](https://github.com/r28ai/charter/tree/main/examples/frameworks))
- `charter-mcp --pack gmail` serves a pack over MCP

## Ready-made tools

687 tools across seventeen APIs ship with Charter, from Gmail and Slack to Stripe and Linear
([full list](https://docs.r28.ai/charter/packs/overview#coverage)). You can extend them with
your own tools, [request a pack](https://github.com/r28ai/charter/issues), and [contributions are welcome](https://github.com/r28ai/charter/blob/main/CONTRIBUTING.md).

## How Charter compares

Identity and access layers for agents (Keycard, Arcade, Permit, WorkOS and others) decide
which token, scope or tool an agent gets. Charter works one level down, inside each call:
which fields the model can set, which values it sends, and whose account the call is for.
`gmail.readonly` lets an agent read every email; Charter decides which query it may send.
The two stack: the token layer narrows the grant, and Charter narrows each call made with it.

Hosted tool platforms like Composio run each call on their own servers. Charter runs in your
process, so your users' tokens and data never pass through a third party, and a call costs
what the API does. In [our benchmark](https://docs.r28.ai/charter/guarantees/benchmarks#time-and-money-per-call),
Composio added about 0.7 s per call.

Guardrail frameworks like NeMo Guardrails, Guardrails AI and Parlant work on the conversation:
what goes into the prompt, or the text going in and out, often checked by another model.
Charter checks the call itself, in code, so a rule holds the same on every model.

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
