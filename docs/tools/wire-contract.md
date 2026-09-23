---
title: "The wire contract"
description: "Body format, static parameters, per-call headers, pagination, and Retry-After."
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

Precedence, lowest to highest: auth → `static_headers` → a `build_request`
override → per-call `headers`. The call site is the most specific authority, so it
is the final word. A `None` value is dropped rather than sent empty, which lets a
caller pass an optional header unconditionally.

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
