---
title: "Tool names across packs"
description: "Why a tool's name stays plain, and who qualifies it when several packs share one surface."
---

A tool's `name` is what the API calls the endpoint. `events_list` is
`events_list` whether you hand it to LangChain, publish it over MCP, or call it
directly. Charter does not prefix it.

That is not a gap. It is the convention every surface Charter targets already
follows: an MCP server publishes plain names and the **host** composes
`mcp__<server>__<tool>` from the server it was configured with; OpenAI
constrains a function name to `[A-Za-z0-9_-]{1,64}` and defines no namespace at
all; LangChain resolves a call against the list you gave it. Qualifying inside
the library would produce `mcp__gcalendar__gcalendar__events_list` the moment a
host did its job.

So the rule is that **whoever assembles tools into one namespace owns the
names** — and Charter ships the one convention they should use.

## The collision

Two packs can declare the same tool name, because two APIs can.

```python
from charter.packs import stripe, shopify

both = list(stripe.TOOLS) + list(shopify.TOOLS)
# stripe.products_list and shopify.products_list
# stripe.customers_list and shopify.customers_list
```

Published bare, that surface lists 23 tools and can route only 21. The model
sees a name twice and its call reaches whichever tool was built last.

## `pack`, and why it is not `provider`

Every tool carries three pieces of identity, answering three different
questions. All three are needed.

| field | question | `gcalendar.events_list` |
| --- | --- | --- |
| `pack` | which namespace | `gcalendar` |
| `provider` | which credential | `google` |
| `base_url` | which host | `https://www.googleapis.com/` |

`provider` cannot stand in for `pack`: **gmail, gcalendar, gsheets, gdocs, gdrive and
gforms all authenticate as `google`** and deliberately share one refresh token. Naming by
provider would collapse six packs into one namespace.

`base_url` cannot either: gmail, calendar, sheets, docs and forms use five different
hosts (Drive shares Calendar's), so the mapping runs the wrong way, and `shopify`'s base URL is not known until
`configure()` is called.

Declare it once, on the factory:

```python
_acme = api_key_tool_factory(
    base_url="https://api.acme.test/v1/",
    pack="acme",
    api_key_headers=...,
)
```

## Qualifying

```python
from charter import qualified_names

qualified_names(gcalendar.TOOLS)
# {"gcalendar__events_list": Tool(...), ...}

qualified_names(list(stripe.TOOLS) + list(shopify.TOOLS))
# {"stripe__products_list": ..., "shopify__products_list": ...}
```

The three shipped adapters call it, so a pack is named the same way inline,
through LangChain, and over MCP. Three properties are worth knowing.

**A name never depends on its neighbours.** Qualifying only once a second pack
appeared would rename every tool in the first the day someone added one, and
break saved prompts, allow-lists, logged traces and eval fixtures without a
word. An MCP server publishes the same names whatever else is installed; so does
this. A host composes `mcp__<server>__<tool>` on top, and the MCP entry point
names its server `charter`, so the result reads
`mcp__charter__gcalendar__events_list` — each segment a different fact. It is
also a budget: the host takes `<server>` from the key it was configured under,
the whole name must fit 64, and one server holding every pack is what keeps the
pack out of that prefix.

**All of them, or none of them.** Neither function qualifies "just the
collisions". A surface where `stripe__products_list` sits beside a bare
`balance_retrieve` makes the pack a substring of some names and not others, so
every filter over it — a `+stripe` in a tool search, a log grep, an allow-list —
silently misses the unqualified half. A filter that works on most names is worse
than none, because nothing tells you which half you got.

**The separator is doubled.** Tool names contain single underscores, so
`stripe_products_list` cannot be split back into its pack and its tool while
`stripe__products_list` can. MCP doubles it for the same reason.

A tool with no `pack` cannot be qualified, and saying so is a `DeclarationError`
rather than a silent fall back to the bare name — which would produce exactly
the half-qualified surface above.
