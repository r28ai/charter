---
title: "The wire contract"
description: "Body format, a body in another media type, routes, static parameters, per-call headers, per-call context, header arguments, pagination, and Retry-After."
---

Beyond where a field goes and how it is encoded, an API has a handful of
constants: what its bodies look like, what it demands on every request, and where
it keeps its cursor. Each of these is declared once per API, not repeated per
tool.

## Body format

`call_api` sends JSON by default. Set `body_format="form"` for
`application/x-www-form-urlencoded`, which is what **Stripe**, **Twilio**,
**Mailgun** and every **OAuth2 token endpoint** expect:

```python stripe_factory.py
stripe = api_key_tool_factory(
    pack="mystripe",
    base_url="https://api.stripe.com/",
    api_key_headers={"Authorization": f"Bearer {SECRET_KEY}"},
    body_format="form",
    body_case="snake",
)
```

Nested values use bracket notation — the Rack/Stripe convention:

| Schema value | On the wire |
|---|---|
| `{"amount": 2000}` | `amount=2000` |
| `{"metadata": {"order_id": "x1"}}` | `metadata[order_id]=x1` |
| `{"items": [{"price": "p1"}]}` | `items[0][price]=p1` |
| `{"expand": ["customer"]}` | `expand[0]=customer` |
| `{"capture": False}` | `capture=false` |
| `{"note": None}` | *omitted* |

Key casing still applies before flattening, so the cascade works as it does for
JSON.

One constraint: a form body must be a mapping of named fields. A single
[`Body()`](/reference/markers#body) field carrying a *list* unwraps to that bare
list, which would produce `[0][price]=…` — meaningless to any server. That raises
a clear error; use `Body(envelop=True)` to keep the field name, or mark several
fields `Body()`. A single `Body()` **scalar** needs nothing: it keeps its own
name, so `customer=Body()` sends `customer=cus_1`.

### Bracket notation in the query too

Some APIs serialise structured *query* values the same way they serialise bodies.
`query_format="bracket"` sends `expand[0]=customer` and `created[gte]=1700000000`
rather than repeated keys; `"repeat"` (the default) sends `labelIds=A&labelIds=B`,
which is what Google and most REST APIs expect.

### One constraint on unwrapping

A schema that declares exactly one `Body()` field unwraps: that field's value
*is* the body. The count comes from the schema, not from which fields a
particular call populated — otherwise a schema with several optional body fields
would unwrap whenever only one of them was set, and the wire shape would depend
on the arguments rather than on the contract.

Unwrapping promotes a nested structure's own fields to the root, so a lone
*scalar* is the exception: it has no fields to promote and keeps its name.
`join(channel=Body())` sends `{"channel": "C1"}`, not `"C1"` — which no API
accepts, and which a form body cannot even represent.

### A body in another media type

Some operations take their body in more than one format. Microsoft Graph's
`sendMail` takes a JSON message, or the same message as a base64 MIME document
sent as `text/plain`. One operation is one tool, so the second format is an
argument: mark it [`Body(media_type=...)`](/reference/markers#body).

```python graph_send_mail.py
class SendMail(BaseModel):
    message: Annotated[Optional[Message], Body()] = None
    save_to_sent_items: Annotated[Optional[bool], Body()] = None
    mime: Annotated[
        Optional[str], Format("mime_base64"), Body(media_type="text/plain")
    ] = None
```

When `mime` is set, its value — after its `Format` — is the whole body, sent
with that `Content-Type`, and no key casing touches it. When it is not, the body
is the JSON it always was: a media-typed field is not counted when deciding
whether the other body fields unwrap, so a create that gains a MIME alternative
still unwraps its message.

The field excludes every other body field, and that rule is derived from the
marker rather than written beside it. It is enforced in the view the model fills
in, like a [`ConflictsWith`](#parameters-that-exclude-each-other), and
[`format_conflicts`](/reference/observability#format_conflicts) lists it:

```text
mime cannot be combined with message, saveToSentItems. It is the whole request
body, sent as text/plain.
```

## Routes

Some operations are served at more than one path, where the extra segment only
scopes the collection: Graph lists messages at `/me/messages` and a folder's at
`/me/mailFolders/{id}/messages`; GitLab lists issues at `/issues`,
`/projects/:id/issues` and `/groups/:id/issues`. Declared as two tools, the model
has to pick between near-identical functions, which is picking a URL. Declared as
one, the scope is an optional argument, and the runtime picks the URL.

`url_template` takes the routes most specific first. A call goes to the first one
whose placeholders it filled:

```python graph_messages_list.py
messages_list = graph(
    name="messages_list",
    args_schema=MessagesList,  # folder_id: Annotated[Optional[str], Path()] = None
    method="GET",
    url_template=("me/mailFolders/{folder_id}/messages", "me/messages"),
)
```

| Call | Request |
|---|---|
| `messages_list(top=10)` | `GET /me/messages?$top=10` |
| `messages_list(folder_id="inbox", top=10)` | `GET /me/mailFolders/inbox/messages?$top=10` |

Nothing about routes reaches the model: the schema it is given has an optional
`folder_id`, and no adapter reads a URL. Path values are escaped per value as
always, so a `folder_id` cannot reach another route. `Tool.url_template` is the
first route and `Tool.url_templates` all of them; a
[`ToolCall`](/reference/observability) records the route the call took.

A sequence is checked when the tool is built, and refused with a
[`DeclarationError`](/reference/errors#declarationerror) if a placeholder is not a
`Path()` field, a `Path()` field appears in no route, an earlier route would win
every time a later one could, or the last route needs a value a call may leave
out.

## Static parameters

Values an API demands on every request, which the model should never see or set:

```python azure_factory.py
azure = api_key_tool_factory(
    pack="azure",
    base_url="https://management.azure.com/",
    api_key_headers={"Authorization": f"Bearer {token}"},
    static_query={"api-version": "2024-01-01"},
)

notion = oauth_tool_factory(
    pack="mynotion",
    base_url="https://api.notion.com/",
    provider="notion",
    credential_provider=provider,
    static_headers={"Notion-Version": "2022-06-28"},
)
```

A request has three places to put something, and constants exist for all three.
The third is the body — declared per tool, since a constant in the body belongs to
one operation rather than to the API:

```python linear_issues_list.py
issues_list = linear(
    name="issues_list",
    args_schema=IssuesListRequest,      # one `variables` field, Body(envelop=True)
    method="POST",
    url_template="graphql",
    static_body={"query": ISSUES_DOCUMENT},
)
```

That is what makes a GraphQL API expressible. Every tool POSTs to the same URL;
the query document is what distinguishes `issues_list` from `issue_create`, and
it is a constant, not a parameter. Keeping it in `static_body` keeps it off the
schema — which is the whole boundary, because a GraphQL endpoint accepts arbitrary
documents. A tool that let the model write the query would not be an integration
with a boundary, it would be a shell.

All three are sent verbatim. `static_query` and `static_body` keys are **not**
case-converted — an `api-version` stays `api-version` rather than becoming
`apiVersion`, and a GraphQL document stays under `query` — and none of them appear
in the tool's LLM schema, so they cost nothing in context and cannot be set by a
model. All three are applied last, so tool input cannot overwrite infrastructure:
a schema field named `query` loses to the document.

The alternative before this existed was to put them in the schema with a default
(the model sees a field it must not touch) or to spend `build_request` on them
(the escape hatch, gone for anything else). Both were wrong.

A `build_request` header override still wins over `static_headers`, so the escape
hatch remains above the declaration.

## A base URL that is not a constant

Usually the host is a property of the API. For a single-tenant-per-installation
API it is a property of the *installation*: a Shopify store lives at
`https://{shop}.myshopify.com/`, a Zendesk account at
`https://{subdomain}.zendesk.com/`. `base_url` therefore accepts a callable,
resolved on every request:

```python shopify_factory.py
shopify = api_key_tool_factory(
    pack="myshopify",
    base_url=lambda: f"https://{configured_shop}.myshopify.com/",
    api_key_headers=headers,
)
```

The host must never be a schema field. A [`Path()`](/reference/markers#path) parameter for the subdomain
would let the model choose which server the request goes to, which is the one
thing a boundary cannot permit. An unresolved base URL raises before anything
leaves the process, the same way an unconfigured credential does.

## Per-call headers

`static_headers` covers values that are constant for an API. Some values are
decided per call by the host application:

| API | Header | Why per call |
|---|---|---|
| Stripe | `Idempotency-Key` | must be stable across *your* retry of one write |
| Stripe Connect | `Stripe-Account` | which connected account this call acts as |
| Xero | `Xero-Tenant-Id` | which tenant |
| PayPal | `PayPal-Request-Id` | idempotency |
| anything | `X-Request-Id` | correlation / tracing |

```python
key = f"refund-{order_id}"          # yours, stable across retries
await tool.ainvoke(args, headers={"Idempotency-Key": key})
```

Two properties are deliberate:

**The caller owns the value.** Charter does not generate idempotency keys. A key minted
fresh on every call is worse than none, because the entire point is that a retry
sends the *same* key — and Charter does not own retries, so it does not own the key.
This is a channel, not a feature.

**The model cannot reach it.** `headers` is keyword-only and is never merged into
`args`, so it does not appear in the tool's LLM schema and a model filling in
arguments has no path to it. Which connected account a call acts as is the host's
decision, structurally rather than by convention.

Precedence, lowest to highest: auth → `static_headers` → a
[`Header()`](#header-arguments) argument → a `build_request` override → per-call
`headers`. The call site is the most specific authority, so it is the final word.
A `None` value is dropped rather than sent empty, which lets a caller pass an
optional header unconditionally.

## Per-call context

Some rules depend on a fact only the host knows: whom the agent is acting for.
"Only this customer's orders", "nothing before the customer is verified" and "no
change without their confirmation" cannot be decided from the arguments, because
the model fills those in, and a model can be talked into naming somebody else's
order or account. Declare the fact as a field marked
[`FromContext()`](/reference/markers#fromcontext), and pass its value per call
as `context`:

```python
from typing import Annotated

from pydantic import BaseModel, Field, model_validator
from charter import FromContext, Path


class GetOrder(BaseModel):
    order_id: Annotated[str, Path()] = Field(description="The order.")
    customer_id: Annotated[str, FromContext()]

    @model_validator(mode="after")
    def _own_order(self) -> "GetOrder":
        if owner_of(self.order_id) != self.customer_id:
            raise ValueError("That order belongs to another customer.")
        return self


await get_order.ainvoke(args, context={"customer_id": session.customer_id})
```

The model is offered `order_id` and nothing else. The rule reads
`self.customer_id`, typed like any field, and a call it refuses never reaches the
API: the model reads the reason as the tool's result, like any other refusal.

**Requiring it and reading it are one declaration.** A field with no default is
required, so a call whose context lacks `customer_id` is refused with a
[`ContextError`](/reference/errors#contexterror) before any rule runs. There is no
list of keys to keep in step with the rules that read them, and no rule can be
written so that a missing value lets the call through. A field with a default
takes it when the host leaves the key out.

**The model cannot reach it.** The field is not in the tool's schema, and an
argument of that name is an undeclared field, refused like any other. `context`
itself is keyword-only, as `headers` is.

**A missing or mistyped value is the host's error.** `ContextError` says so in its
message, which matters because the adapters hand a `CharterError` back to the
model as the tool's result: told only that a field was missing, a model would try
to supply it. A rule that refuses *because of* the host's value ("verify the
customer first") is a refusal like any other, for the model to read and act on.

**On its own it never reaches the wire.** It is there for the rules. Add
`Path()`, `Query()`, `Body()` or `Header()` and it is sent there as well, which is
a [pin](/tools/projections#pin) whose value arrives with each call:

```python
class ListOrders(BaseModel):
    customer_id: Annotated[str, Query(), FromContext()]
    status: Annotated[Optional[Literal["open", "closed"]], Query()] = None
```

The list is scoped to the customer the host verified, and the model can neither
see nor change the filter. `FromContext("customer")` reads a different key than
the field's name.

**A reviewer sees it.** [`egress_map`](/boundary/egress-control) lists the field
as withheld with the reason `context`, and the key it is read from:

```text
shop_orders_list  (GET v1/orders)
  visible to the model (1):
    + status
  withheld (1):
    - customer_id  [context] <- context['customer_id']
```

A `FromContext` field is top-level only, is never one a `Mode` withholds, and is
outside what a projection reaches: `keep` leaves it alone, and naming it in `drop`
or `pin` is refused, since a value comes from one place.

`invoke` and [`ToolSession.dispatch`](/reference/tool-discovery#toolsession) take
`context` too, and every adapter carries it: the OpenAI `run(..., context=...)`,
LangChain's `CharterMiddleware`, which reads the agent's own context, and
`build_server(..., context=...)` for MCP. See
[passing the host's context](/using/adapters#passing-the-hosts-context).

### Rules that read the context directly

A rule on a nested model cannot see its parent's fields, so it reads the host's
mapping instead, as Pydantic's validation context:

```python
from pydantic import ValidationInfo, field_validator


class Line(BaseModel):
    order_id: str

    @field_validator("order_id")
    @classmethod
    def _own_order(cls, value: str, info: ValidationInfo) -> str:
        if owner_of(value) != info.context.get("customer_id"):
            raise ValueError("That order belongs to another customer.")
        return value
```

Inside `ainvoke`, `info.context` is always a mapping, empty when the host passed
nothing. The rule then decides what a missing key means, and the one above
refuses, which is the safe reading. Prefer `FromContext` wherever it reaches: it
makes that decision once, for every rule.

Two things hold for any rule, whichever way it reads the host's value:

- **A field validator does not run on a field the model leaves out.** Pydantic
  validates what was given, and an omitted field takes its default unchecked. A
  rule that must hold on every call goes on a `model_validator(mode="after")`, or
  the field takes `Field(validate_default=True)`.
- **A rule on the whole call reads the call as it is sent.** A field the
  projection cut or a `Mode` withholds reads as its default, which is what the API
  receives; a pinned field reads as its pin, and a `FromContext` field as the
  host's value.

## Header arguments

Some APIs take an argument the *model* decides as a header rather than in the
query or the body. Microsoft Graph sizes a delta page with
`Prefer: odata.maxpagesize=10`, and offers nothing else that does it. That is a
schema field marked [`Header()`](/reference/markers#header):

```python
max_page_size: Annotated[
    Optional[int],
    Field(None, ge=1, description="The maximum number of messages in each page."),
    Header("Prefer", template="odata.maxpagesize={}"),
] = None
```

The two kinds of header answer different questions, and the line between them is
who decides. A per-call `headers` value is the host's — which account, which
idempotency key — and a model can never reach it. A `Header()` field is an
argument like any other, in the schema and filled in by the model, that happens
to travel as a header. A `Header()` field cannot name the credential's header or
one the tool already sets in `static_headers`, and a value containing a line
break is refused before the request is built.

## Pagination

Where an API keeps its place in a list. Universal concept, never the same
location — and, it turns out, not always a cursor. A [`Pagination`](/reference/envelopes-and-pagination#pagination) declares one of
two styles.

**Cursor style.** The API hands back a token you send on the next call:

```python slack_pagination.py
from charter import Pagination

SLACK = Pagination(
    cursor_field="response_metadata.next_cursor",
    cursor_param="cursor",
    more_field="has_more",
)
GOOGLE = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")

# Stripe's cursor is the last object's id, not a token it hands back.
STRIPE = Pagination(
    cursor_field="data[-1].id",
    cursor_param="starting_after",
    more_field="has_more",
)

# Relay: the cursor comes back nested, and goes out nested too.
LINEAR = Pagination(
    cursor_field="pageInfo.endCursor",
    cursor_param="variables.after",
    more_field="pageInfo.hasNextPage",
)
```

**Page-number style.** There is no token at all. You ask for page 1, 2, 3 and stop
when a page comes back shorter than you asked for. GitHub works this way:

```python github_pagination.py
GITHUB = Pagination(page_param="page", per_page_param="per_page")

# ...unless the list is wrapped, as GitHub's search endpoints wrap theirs.
GITHUB_SEARCH = Pagination(
    page_param="page", per_page_param="per_page", items_field="items"
)
```

`items_field` names where the array lives; `None` means the response body *is* the
array. Both `page_param` and `per_page_param` are required, because without the
page size there is no way to tell a full page from the last one.

`cursor_field` and `more_field` are paths into the response — dotted for nesting,
with optional list indices such as `data[-1]` for APIs whose cursor is derived
from the page rather than returned. `cursor_param` names the schema field that
carries the cursor back, and may itself be dotted to reach into a nested argument:
a GraphQL tool carries its cursor at `variables.after`, because that is where the
wire puts it. The declaration says where the marker goes; it does not invent a
parameter, so the field it names must exist on the schema.

Declare `more_field` whenever the API offers one. Without it the fallback is "a
non-empty cursor means another page", which is wrong for every API that returns a
cursor on its last page — a Relay connection does exactly that, and the walk never
terminates.

Paging then does not require knowing the convention:

```python paginate_loop.py
args = {"channel": "C123"}
while args is not None:
    page = await tool.ainvoke(args)
    handle(page)
    args = tool.pagination.next_page_args(page, args)
```

An empty cursor counts as absent — Slack returns `""` on the last page, and
treating that as a cursor loops forever. When `more_field` is declared it wins
over the cursor, because some APIs send a stale cursor on the final page. In
page-number style a short page is the only end signal there is, so pass the
previous arguments to `next_page_args` — that is where the page size lives.

One caution for pack authors: a response handler that trims a list must keep
whatever the declaration reads — the object `id` for a derived cursor, and
`has_more` even when it is `False`. Drop the latter and a derived cursor, which is
always present, leaves the loop with nothing to stop on.

This declares the location. It does not loop; see "What this can't express" in
the README.

## Retry-After

`APIError.retry_after` carries the parsed `Retry-After` header when the server
sent one — usual on 429, common on 503. Charter never retries; it just refuses to
discard the server's own answer to "when?".

```python
except APIError as e:
    if e.retry_after:
        await asyncio.sleep(e.retry_after)
```

Only the delta-seconds form is parsed. The HTTP-date form is legal but rare in
JSON APIs, and guessing at clock skew is worse than reporting nothing.

## Parameters that exclude each other

APIs state these in prose and answer them with a `400`. Declare the rule on the
field it is about with [`ConflictsWith`](/reference/markers#conflictswith), and
the runtime builds the check:

```python
i_cal_uid: Annotated[
    Optional[str], Field(None), Query(), WireName("iCalUID"),
    ConflictsWith("sync_token", reason="Drop syncToken to run a fresh query."),
]
```

Written as a validator instead, the rule needs a list of the fields it covers,
which is a second place to keep in step: add a parameter and the list forgets it,
delete one and the list keeps naming a field that is gone. Google Calendar's
`calendarList.list` had exactly that — the validator named
`showOwnOrganizationOnly`, the schema had no such field, and nothing exercised
either.

Every conflict is reported in one message rather than one per call, and each
field is named the way the API names it, taking a
[`WireName`](/reference/markers#wirename) when there is one:

```text
iCalUID, q, timeMin cannot be combined with syncToken. An incremental sync
continues the query the token came from.
```

Rules of a different shape — "exactly one of `a` or `b`", "`b` is required when
`a` is set", "this flag may be set but not to `False`" — stay a
`@model_validator(mode="after")`. `ConflictsWith` says "not both" and nothing
else.

## Related

- [`ConflictsWith`](/reference/markers#conflictswith) — the marker
- [`format_conflicts`](/reference/observability#format_conflicts) — every rule in a pack, read back
- [Envelopes](/tools/envelopes) — when a 200 is not a success
- [Key case cascade](/tools/key-case-cascade)
