# Charter

**Give an agent access to your users' accounts without giving it everything.**

Define tools as Pydantic schemas. Charter assembles the requests, refreshes each end
user's OAuth token, and decides what the model is allowed to see and send. Twelve
packs ship. Your API is a pack too, and your coding agent can write it.

```bash
pip install charter
```

Charter runs where you run it. No telemetry, no phone-home, no training on your traffic —
the library makes no network calls except the API calls you define. MIT, forever.

## What the agent can do

GitHub has one scope for repository access. `repo` grants read and write on code,
issues, pull requests, webhooks and collaborators, across every repository the user
can reach, public and private. There is no narrower one. Google's `gmail.modify`
covers reading every message in the mailbox, labelling, trashing, drafting and
sending.

So the grant is not where you say what an agent may do, and a sentence in a prompt is
not enforcement. The layer that assembles the request is the last place the question
can be answered mechanically, and that is this one. The GitHub pack holds a `repo`
token and hands the model twenty-nine named tools, none of which is "change a webhook".

The consent screen narrows with the toolset, because a pack declares what each tool
needs:

```python
from charter.auth import scopes_for
from charter.packs import gmail

scopes_for([gmail.messages_list])    # ['https://www.googleapis.com/auth/gmail.modify']
scopes_for([gmail.threads_delete])   # ['https://mail.google.com/']
```

Gmail's irreversible delete is the one endpoint `gmail.modify` does not cover, so your
users are asked for full mailbox access only if you actually hand out that tool.

Inside a tool the same thing happens per field, and because it is declared it can be
printed, from the same declarations the runtime executes, so it cannot drift from what
actually happens:

```python
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
    - body.payload  [response_only]
    - body.snippet  [response_only]
    ...
```

`egress_map()` returns the same content as JSON-serialisable data. Snapshot it in CI
and a schema change that widens what the model can see becomes a reviewable diff.

## Quickstart

A pack is four lines, with a token you already hold:

```python
from charter.auth import StaticTokenProvider
from charter.packs import gmail

gmail.configure(StaticTokenProvider(access_token))

await gmail.messages_send.ainvoke(
    body={"raw": {"to": "ada@example.com", "subject": "Hi", "body": "Hello"}}
)
```

Your own API is the same call, one factory away:

```python
import os
from typing import Annotated, Optional
from pydantic import BaseModel
from charter import Path, Query, api_key_tool_factory

class GetWeather(BaseModel):
    city: Annotated[str, Path()]
    units: Annotated[Optional[str], Query()] = "metric"

weather = api_key_tool_factory(
    base_url="https://api.openweathermap.org/",
    api_key_headers={"x-api-key": os.environ["OPENWEATHER_API_KEY"]},
)

get_current = weather(
    name="get_current_weather",
    description="Get the current weather for a city.",
    method="GET",
    url_template="data/2.5/weather/{city}",
    args_schema=GetWeather,
)

await get_current.ainvoke(city="Tokyo")
```

Values the *host* decides per call — an `Idempotency-Key`, a `Stripe-Account`
naming which connected account to act as, a correlation id — go through a separate
keyword-only channel, so a model filling in tool arguments can never set a header:

```python
import os
from charter.packs import stripe

stripe.configure(api_key=os.environ["STRIPE_API_KEY"])

# The key is yours and stable across your retries — Charter never mints one, because
# an idempotency key generated per call would defeat the point.
await stripe.refunds_create.ainvoke(
    {"charge": "ch_123"}, headers={"Idempotency-Key": "refund-order-6735"}
)
```

## Your API is a pack

Fifteen packs ship and they will never be the API you need. A pack is a Python module
that calls one factory function and exports the tools it builds, so there is no plugin
system and nothing to register.

What is hard is the schema: every enum value, which fields are response-only, what the
server does when a parameter is absent, and which documented defaults must not be
copied onto the model. That knowledge is written down for coding agents, as a checklist
of bugs rather than a style guide:

**[skills/writing-charter-packs/SKILL.md](skills/writing-charter-packs/SKILL.md)**

Point Claude Code, Cursor or any coding agent at it together with the API's
documentation and it writes the pack. It knows that a field with no default is required
in Pydantic v2, so an `Annotated[Optional[str], Query()]` missing its `= None` forces
the model to supply it on every call. It knows GitHub's `/user/repos` answers 422 when
`type` arrives beside `visibility`, so carrying all three documented defaults makes the
first call an agent ever makes a guaranteed failure.

Then the pack is held to the same [conformance suite](#conformance) as every pack here,
which is offline and knows nothing about any particular API.

If you write one, open a pull request.

## The contrast

Sending an email through Gmail means building a MIME message, encoding it base64url,
stripping the padding, and wrapping it in `{"raw": ...}` — and keeping the model away
from the dozen response-only fields on the same resource. That is the schema:

```python
from typing import Annotated, Optional
from pydantic import BaseModel, Field
from charter import Body, EmailContent, Format, Mode, Path

class Message(BaseModel):
    """https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages"""

    raw: Annotated[
        str,
        Field(..., description="The entire email message, RFC 2822 and base64url encoded."),
        Format("rfc822_base64"),
        Mode("request_only"),
    ]
    thread_id: Optional[str] = Field(None, description="Thread to attach this message to.")
    id: Annotated[Optional[str], Field(None), Mode("response_only")] = None
    label_ids: Annotated[Optional[list[str]], Field(None), Mode("response_only")] = None
    snippet: Annotated[Optional[str], Field(None), Mode("response_only")] = None

class MessagesSendRequest(BaseModel):
    user_id: Annotated[str, Field("me"), Path()] = "me"
    body: Annotated[Message, Field(...), Body()]
```

The model fills in `to`, `subject`, `body`. The MIME assembly, the encoding, the
padding, and the field policy are the runtime's problem. `id`, `label_ids` and
`snippet` never reach the model at all — Gmail returns them and never accepts them.

## What it bridges

| What the API expects | What the LLM sends | How Charter bridges it |
|---|---|---|
| `{"raw": "dG86IGFsaWNlQGV4YW1wbGUuY29tCk1JTUUtVmVyc2l..."}` | `EmailContent { to: "alice@example.com", subject: "Hello", body: "Hi Alice!" }` | `Format("rfc822_base64")` — builds the MIME message, encodes base64url, wraps in `{"raw": ...}` |
| `{"values": [[{"stringValue":"Name"},{"stringValue":"Age"}],[{"stringValue":"Alice"},{"numberValue":30}]]}` | `values: [["Name", "Age"], ["Alice", 30]]` | `Format("proto_json")` — converts plain JSON to the protobuf `Value` type, wrapping each cell |

## Credentials, and OAuth without a vendor SDK

An access token is good for an hour, which makes "a token you already hold" fine for
a script and useless for a product. So Charter refreshes one — against any OAuth 2.0
token endpoint, with no `google-auth`, no Slack client, nothing. A token endpoint is
a form POST, and what varies between servers is three fields, named the way
[RFC 8414](https://www.rfc-editor.org/rfc/rfc8414) names them:

```python
import os
from charter.auth import OAuth2Client, OAuth2Server
from charter.packs import gmail

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
)

gmail.configure(credential_provider=OAuth2Client(
    GOOGLE,
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
))
```

For the enterprise IdP nobody has heard of — almost always Okta, Entra ID, Auth0,
Keycloak or Ping — there is nothing to write down at all, because they publish their
own metadata: `await OAuth2Server.discover("https://login.acme-corp.com")`.

There is no built-in catalogue of vendors, on purpose: a constant shipped in a
release is pinned to that release, and a blessed-vendor list would imply that
unlisted servers are second class. Constants for the few APIs that publish no
metadata live in [the docs](docs/auth/authorization-servers.md), to copy.

The access token is held in memory until shortly before it expires, and concurrent
calls share one refresh rather than each starting their own — which matters because
some servers invalidate the previous refresh token on use, so twelve parallel tool
calls firing twelve refreshes poison eleven of them. A rotated refresh token is
adopted automatically: it announces itself by being in the response, so there is
nothing to declare.

Where the refresh token comes from is protocol too: `OAuth2Flow` builds the
authorization URL and exchanges the callback's code, while the route, the session
and storage stay yours — see [the flow guide](docs/auth/oauth-flow.md).

Serving many end users needs one more piece, since `get_credentials(provider)` names
the API and not the person:

```python
from charter.auth import SubjectProvider, use_subject
from charter.packs import gmail

def for_user(subject: str):
    return build_oauth_client_for(subject)   # your token store

gmail.configure(credential_provider=SubjectProvider(for_user))

with use_subject("user_1042"):
    ...   # every tool call in here acts for that user
```

Tools stay built once, and this works unchanged through LangChain, ADK, the OpenAI
tools interface and the Claude Agent SDK, because the lookup happens below every
adapter. An unset subject raises rather than falling back to a default.

**Charter refreshes a grant you already hold; it never obtains one.** The consent
redirect, `state`, PKCE and the callback route belong to your web framework. And
nothing here signs anything, so JWT-bearer and service-account grants are out of
scope by the same rule that excludes request signing.

## Coverage

Fifteen packs, 549 tools.

| Pack | Import | Tools | Auth | What it exercises |
|---|---|---|---|---|
| Gmail | `charter.packs.gmail` | 23 | OAuth bearer | `rfc822_base64` round-trip, response handler |
| Google Calendar | `charter.packs.gcalendar` | 13 | OAuth bearer | body + query casing |
| Google Sheets | `charter.packs.gsheets` | 17 | OAuth bearer | `proto_json` round-trip |
| Google Docs | `charter.packs.gdocs` | 3 | OAuth bearer | a 33-member `oneof` union, enforced locally |
| Google Drive | `charter.packs.gdrive` | 25 | OAuth bearer | camelCase query, PATCH via `partial_of`, response trimming |
| Google Forms | `charter.packs.gforms` | 6 | OAuth bearer | one resource, two operations, different field sets |
| Slack | `charter.packs.slack` | 18 | OAuth bearer | `ok:false` guard, response trimming |
| GitHub | `charter.packs.github` | 139 | OAuth bearer | constant headers beside a bearer token, page-number paging |
| Stripe | `charter.packs.stripe` | 59 | API key | form encoding, bracket query, derived cursor, DELETE with a body |
| Linear | `charter.packs.linear` | 128 | API key | GraphQL: constant document, nested cursor, `success:false` |
| Shopify | `charter.packs.shopify` | 22 | API key | GraphQL: per-store host, `userErrors`, money flattening |
| Notion | `charter.packs.notion` | 35 | OAuth bearer | snake_case wire, three-tier block nesting, `and`/`or` on the wire |
| Firecrawl | `charter.packs.firecrawl` | 43 | API key | POST-only REST, nested response handler |
| Granola | `charter.packs.granola` | 9 | API key | snake_case query and body, cursor paging, a discriminated actor union |
| Tavily | `charter.packs.tavily` | 9 | API key | snake_case REST, search/extract/crawl/map/research, async research polling |

Every tool in every pack has its LLM schema built, its egress map checked against that
schema, and its OpenAI function definition validated in the suite.

Slack is the pack that shows why a runtime beats a wrapper. Slack reports failure as
**HTTP 200 with `{"ok": false, "error": "..."}`** — so a generic HTTP client hands the
model an error payload as if the message had sent. That is not patched per tool; it is
declared once, as an [`Envelope`](docs/tools/envelopes.md) on the factory, and enforced by the
runtime on every call — including calls by tools somebody adds next year. The same one line handles any GraphQL API, whose failures are always a 200 with
an `errors` array. Slack's read tools additionally trim block trees and
eight-per-user avatar URLs down to what an agent can act on.

Stripe is the pack that exercises the wire contract hardest among the REST APIs:
form-encoded in both directions with bracket notation (`line_items[0][price]=…`), and
a cursor that is the last object's id rather than a token the API hands back
(`data[-1].id`). Both are declared once on the factory.

GitHub is the OAuth-plus-constant-header case: a bearer token from your credential
provider, alongside an `Accept`, an `X-GitHub-Api-Version` and a `User-Agent` that
GitHub requires and the model must never see. Those go in `static_headers`. It also
pages by number rather than by cursor — ask for page 1, 2, 3 and stop when a page comes
back short — which is the second pagination style `Pagination` declares.

Linear and Shopify are the GraphQL case, and the reason `static_body` exists. Every
tool in a GraphQL pack POSTs to the same URL; what makes `issues_list` different from
`issue_create` is the query document, which is a constant belonging to the tool rather
than a parameter. Putting it in `static_body` keeps it off the schema entirely — and
that is the whole boundary, because a GraphQL endpoint accepts arbitrary documents, so
a tool that let the model write the query would not be an integration, it would be a
shell.

Both also carry a failure GraphQL's own `errors` array does not: a mutation the server
understood and then declined comes back HTTP 200, with no `errors`, and the refusal in
the payload — Linear's `success: false`, Shopify's `userErrors`. Every signal a runtime
normally trusts says the write happened. So `Envelope` field names are paths, with `*`
standing for whichever operation the tool called:

```python
from charter import Envelope

Envelope(errors_field=("errors", "data.*.userErrors"))
```

One line on the factory, enforced by the runtime on every call — including calls by
tools added later. The same check written into each mutation's response handler would
pass the same tests and still be wrong, because it is opt-in per tool. Shopify additionally has no fixed host: a store lives at
`https://{shop}.myshopify.com/`, so its base URL is resolved per request from
`configure()` rather than being a schema field the model could point elsewhere.

Google tools also carry `quota_cost` — what one call costs against the provider's own rate limit, in the
provider's units (`messages_send` is 100, `messages_list` is 5) — plus a link to the
quota documentation. Nothing enforces it yet; it is the input a budget policy needs.

## Conformance

A declaration can be wrong in a way no per-tool test notices: the call returns 200,
the suite stays green, and the filter you declared was silently discarded on the way
out. So the properties that must hold for *every* pack are checked separately, without
knowing anything about any particular API: nineteen in all. Among them:

- a `Pagination` names fields the schema actually accepts, only endpoints that page
  declare one, and a walk over it terminates;
- no `model_validator` is lost on the way to the LLM view, so a `oneof` is enforced
  against the model's input and not only against the wire;
- failure detection is an `Envelope` on the factory and never logic inside a response
  handler, where the first tool added without one reports a failed write as a success;
- Google packs send camelCase query parameters, which Google requires and otherwise
  ignores without complaint;
- a `static_body`, `static_query` or `static_headers` constant is never also reachable
  as a tool argument;
- a `Gloss` reaches the model's schema and never the documented description, so the
  vendor's own text stays comparable to their reference page.

Most of these were written after a bug rather than before one. Four packs added in a
single week produced six, five of them silent — including a factory-level pagination
that labelled twenty-two retrieve and write endpoints with a cursor parameter they do
not accept.

A check that reads a declaration and compares it to itself passes forever and protects
nothing, so each one is also run against a pack broken on purpose, in the specific way
the bug it guards against broke it — eighteen mutations in
[`test_conformance_is_not_vacuous.py`](tests/test_conformance_is_not_vacuous.py),
each restored afterwards. One check was vacuous until that file caught it.

What none of this can tell you is whether a schema still matches the vendor's live
API. That is drift, and it needs the published spec rather than introspection — it is
on the roadmap, and until then `scripts/live_google_check.py` is the shape such a
check takes: deliberately not a test, because the suite is offline by rule.

## Adapters

A `Tool` is the object. These are projections of it.

```python
from charter.adapters.openai import to_openai_tools
from charter.packs import gmail

tools = to_openai_tools(gmail.TOOLS)
```

```python
from charter.adapters.langchain import to_langchain_tools
from charter.packs import gmail

tools = to_langchain_tools(gmail.TOOLS)   # pip install 'charter[langchain]'
```

```bash
pip install 'charter[mcp]'
python -m charter.mcp --pack gmail
```

The MCP entry point reads credentials from the environment:
`$GOOGLE_ACCESS_TOKEN` for the Google packs, `$SLACK_BOT_TOKEN` for Slack,
`$GITHUB_TOKEN` for GitHub, `$STRIPE_API_KEY` for Stripe, `$LINEAR_API_KEY` for
Linear, `$SHOPIFY_SHOP` + `$SHOPIFY_ACCESS_TOKEN` for Shopify (it needs both,
since the host is a property of the store), `$NOTION_API_KEY`, `$FIRECRAWL_API_KEY`,
`$GRANOLA_API_KEY`, and `$TAVILY_API_KEY` for the rest.

## Why a boundary

An agent is only as trustworthy as the layer between it and your real systems. That
layer is the one place where a guarantee can be *mechanical* rather than a prompt, a
score, or a policy someone wrote down — because it is the chokepoint every action
crosses. Charter puts three things in the contract itself:

**Egress — what the model can see.** The LLM's view of a schema is computed from
declarations before any request is made. A field marked `Mode("response_only")` is not
filtered out of a prompt after the fact; it is absent from the type the model is
handed, so it cannot reach a context window at all. Field-level data minimisation
toward your model vendor, by construction. It is also printable — see below.

`Mode` is the pack author's half and is fixed when the pack ships. The half you own is
`tool.derived(name=..., keep={...}, pin={...})`, which narrows a tool you did not write:
`keep` picks the capabilities this agent may use, `pin` fixes a value it can neither see
nor change. Google's `documents` scope grants all 33 kinds of Docs edit as one
indivisible grant, so the union member is the only place "may edit text, may not delete
content" can be said. Both print in the map below.

**Action — what the agent can send.** Path, query, and body routing, wire encoding,
and key casing are all resolved from the schema by a deterministic runtime. The model
supplies meaning; it never assembles a request. It cannot emit malformed base64 or a
field the endpoint doesn't accept, because it never touches either, and it cannot reach a
capability a projection removed.

**Change — what stays true when the model changes.** Behaviour lives in types and
tests rather than in accumulated prompt folklore, so the mechanics of a tool are
identical across models, and every pack is held to that [mechanically](#conformance).
What remains model-dependent is whether a given model fills the schema well, which
is a thing you measure and re-run rather than rewrite.

## What a call cost

A pack's job is to hand the model a fraction of what the API sent. Every call is
measured, so that is a number rather than a claim:

```python
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
```

```
stripe.list_charges    GET  v1/charges                 200     18ms  ↑     12 B  ↓    38.4 KB →     412 B  (99%)
stripe.list_charges    GET  v1/charges                 ✗ invalid_input — not sent, 1ms
```

Sizes, never values — arguments and bodies stay on the DEBUG path. The second line
is a call the model got wrong, rejected against the schema before anything was sent:
no request, no rate-limit budget, no charge.

Attach a sink for a run summary, or to forward each record to whatever you already
run — `ToolCall.to_dict()` uses OpenTelemetry's attribute names:

```python
import os
from typing import Annotated
from pydantic import BaseModel
from charter import CallCollector, Path, api_key_tool_factory, format_call_summary

class GetCharge(BaseModel):
    charge_id: Annotated[str, Path()]

calls = CallCollector()
stripe = api_key_tool_factory(
    base_url="https://api.stripe.com/",
    api_key_headers={"Authorization": f"Bearer {os.environ['STRIPE_API_KEY']}"},
    on_call=calls,
)
get_charge = stripe(
    name="get_charge",
    args_schema=GetCharge,
    method="GET",
    url_template="v1/charges/{charge_id}",
)

await get_charge.ainvoke(charge_id="ch_123")
print(format_call_summary(calls))
```

The timings are split by owner — `upstream_ms` is the provider's, everything else is
Charter's or yours — so `overhead_ms` answers "is this layer in my way?" without an
argument. Measurement is local and stays local: there is no default sink, no
phone-home, and no history. See [observability](docs/running/observability.md).

## What this can't express

The boundary is declarative, and declarative has edges. Charter describes *one request*.

**Out of scope by design** — these are orchestration, and orchestration belongs in
your agent where you can debug it:

- **Pagination loops.** Where the cursor lives *is* declared (`Pagination`), so you
  can page without knowing each API's convention — but the loop is yours to write.
- **Multi-call compositions** — "find the location key, then fetch its forecast" is
  two calls with a data dependency between them.
- **Retry policies** — backoff and partial-failure recovery. `APIError` carries
  `retry_after` when the server sent one, and you can pass a stable
  `Idempotency-Key` per call, but deciding whether and when to retry is yours.

**Not yet supported** — real gaps, named rather than hidden:

- **Multipart bodies / file upload.** `body_format` covers JSON and form encoding;
  `multipart/form-data` (Slack `files.upload`, Drive, OpenAI files) is not there yet.
- **Request signing.** AWS SigV4 and HMAC-signed payment APIs need to sign the
  serialised body, which needs a hook further down than the per-call header
  channel. Static headers, bearer tokens and per-call headers are covered.
- **Pagination markers in response headers.** `Pagination` reads the body, in
  either the cursor or the page-number style. GitHub also advertises its next page
  in a `Link` header (RFC 8288); Charter hands back the parsed body, so that marker is
  not reachable. The page number is, which is why the GitHub pack declares it.
- **Arbitrary GraphQL.** The document is a constant declared in `static_body`, and
  the variables are a typed schema — see the Linear and Shopify packs. What is not
  expressible is a *dynamic* selection set: each tool asks for the fields its
  document names. That is deliberate, since a model-authored query against a
  GraphQL endpoint is not a boundary, but it does mean one tool per operation.
- **Streaming and long-polling responses.** Every call is a single request/response.

The escape hatch for single-call shaping is `build_request` (pre-request) and
`response_handler` (post-request). Anything spanning calls goes in your agent.

Two more honest limits. Egress control governs what crosses the boundary — what your
own code does with a response afterwards is your prompt, not ours. And `Mode` is
schema visibility, not authorization: it decides what a tool exposes, never who may
call it.

## Roadmap

- **Policy markers** — `HITL`, `Budget`, `Approve` as first-class field and tool
  markers, so approval rules live in the schema next to everything else. `quota_cost`
  and `action_label` are already carried for exactly this.
- **Referential-integrity provenance** for identifier fields, so a model cannot pass
  an ID it never legitimately obtained.
- **A public API drift observatory** — detecting when an upstream API changes shape
  under a schema that claims to match it.

## Docs

- [Egress control](docs/boundary/egress-control.md) — what the model can see, and the audit artifact
- [Authorization servers](docs/auth/authorization-servers.md) — OAuth refresh without a vendor SDK
- [Getting the grant](docs/auth/oauth-flow.md) — the consent URL and the code exchange; what stays yours
- [What a call cost](docs/running/observability.md) — timings by owner, payload versus context
- [Envelopes](docs/tools/envelopes.md) — APIs that report failure with HTTP 200
- [The wire contract](docs/tools/wire-contract.md) — body format, static parameters, pagination
- [Transforms](docs/tools/transforms.md) — semantic types to wire formats
- [Mode system](docs/boundary/mode-system.md) · [quick reference](docs/boundary/mode-quick-reference.md)
- [Key case cascade](docs/tools/key-case-cascade.md)
- [LLM input auto-corrections](docs/running/llm-input-auto-corrections.md)
- [Tool validation and error handling](docs/running/tool-validation-error-handling.md)
- [`api_key_tool_factory`](docs/auth/api-key-tool-factory.md)
- [Writing a pack](skills/writing-charter-packs/SKILL.md) · [AGENTS.md](AGENTS.md)

## Development

```bash
uv venv
uv pip install -e ".[dev,langchain,mcp]"
uv run pytest
uv run ruff check src tests examples
uv run pyright --pythonpath .venv/bin/python src
```

## License

MIT — see [LICENSE](LICENSE).
