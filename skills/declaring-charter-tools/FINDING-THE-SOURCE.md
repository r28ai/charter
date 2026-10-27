# Finding the source of truth

Step 1 of [`SKILL.md`](SKILL.md) says to close the documentation graph. This page is
about where to start, because the prose reference is rarely the best source available
and is never the only one.

The rule underneath everything here: **prefer a machine-readable source, then settle
the details against the prose.** A spec is complete about paths and field names and
wrong about nothing, because it is what the vendor's own tooling reads. Prose is
written by hand, relays the spec, and drops things when it does — most often enum
members, which is exactly the failure that costs you a 400 you cannot reproduce.

Neither source is authoritative alone. The traps below are the ones that have actually
bitten a pack in this repo.

## Look for a spec before you read a page

In rough order of how often it pays off:

- **`openapi.json` / `openapi.yaml`.** Try the documentation host and the API host.
  It is frequently published without being linked from anywhere a reader would look.
- **A GraphQL schema.** If the API is GraphQL, the SDL exists by definition. See below.
- **`llms.txt`.** A list of documentation URLs, meant for exactly this. Useful, and
  incomplete often enough that it cannot be your only path list.
- **A discovery document.** Google publishes one per API, and it is the source its own
  client libraries are generated from.

If none of those exist, crawl the prose, and expect to follow every link: one endpoint
routinely spans ten pages, because the request body references a resource, the resource
references an enum, and the enum is documented somewhere else entirely.

## GraphQL: build from the SDL, not from the docs

Introspect the schema and work from it. Then **validate every document you write
against it** before shipping — a field that does not exist is a runtime error the
schema would have caught for free.

This is not a preference. A GraphQL API's prose documentation is a curated subset of
its schema, and the parts it omits are the parts an agent eventually needs. Both
GraphQL packs here were built this way.

## Google: append `.md.txt`

Any Google REST reference page has a plain-markdown mirror at the same URL with
`.md.txt` appended. It is far easier to parse than the rendered page and it carries the
same content.

Three things to watch for in the mirror:

- Tables lose their alignment and can run together. Read them carefully rather than
  pattern-matching on column position.
- Enum values and their descriptions are in the same cell, so splitting naively
  mangles both.
- A `oneof` union's members are listed in the parent's table, not given their own
  section. Miss it and you will ship a union with the popular members and silently no
  others.

## Notion: the spec beats the prose

`openapi.json` is ground truth. The prose reference relays it and **drops enum
values** when it does. Take field names, types and enums from the spec, and read the
prose only for behaviour the spec cannot express.

## Stripe: the spec lags the prose

The opposite failure, so the two sources swap roles:

- **Sweep paths and field names with the OpenAPI spec.** It is complete about what
  exists.
- **Settle enums against the `.md` prose.** The spec's enum lists trail the
  documentation, so a value the prose documents may be absent from the spec entirely.

Carrying a closed `Literal` from a stale spec rejects a valid call, and the model
cannot tell that apart from the API refusing it, so it has no way to recover.

## Microsoft Graph: the CSDL with descriptions, then the markdown

Graph publishes its v1.0 schema as OData CSDL at
`https://graph.microsoft.com/v1.0/$metadata`, which is what Graph validates
against — types, enum members, and every bound action's parameters. The copy at
`msgraph-metadata/clean_v10_metadata/cleanMetadataWithDescriptionsv1.0.xml` on
GitHub is the same schema with each property's description attached, which is
most of a pack's field text in one file. The reference pages are markdown in
`microsoftgraph/microsoft-graph-docs-contrib` under `api-reference/v1.0/api/`
and `.../resources/`; fetch them raw rather than the rendered site.

Four traps:

- **Required is not in the schema.** CSDL marks almost nothing non-nullable, so
  what a create needs comes from the prose ("Required." in a parameter table, or
  "At minimum, specify..." in the intro).
- **"Read-only" in a CSDL description is not always true.** `internetMessageHeaders`
  and an extended property's `id` say it and are written on create; a category's
  `displayName` says it and is required on create. Read the operation's own page.
- **Action parameters are documented in two casings.** The CSDL spells them
  `DestinationId`; most pages and examples send `destinationId`. `getMailTips`
  and `createUploadSession` are the exceptions whose examples keep PascalCase
  (`EmailAddresses`, `AttachmentItem`); follow the example.
- **A summary that names an endpoint may name the wrong one.** "Permanently
  delete" is the `permanentDelete` action, not `DELETE`, which moves to Deleted
  Items; the MIME reply is `/reply` with `text/plain`, not `sendMail`. Each page
  lists its own HTTP requests; that list is the endpoint.

## Luma: the spec is the reference

`https://public-api.luma.com/openapi.json` (OpenAPI 3.1, no auth needed) is what
docs.luma.com renders: each reference page's `.md` mirror embeds the same
operation. So generate from the spec, and read only the overview pages
(getting started, rate limits, conventions, formats). Three facts live there and
nowhere in the spec:

- **A key is one calendar.** A calendar key reaches the calendar it was made on.
- **An organization key picks a calendar with `x-luma-calendar-id`.** That is a
  per-call header the host sets, never a tool argument.
- **Arrays in the query repeat the key** (`?platforms=luma&platforms=external`).

The spec moves often (two event themes were added on the day the pack was
drafted). To see what changed, draft it again beside the pack and diff:

```
uv run python scripts/openapi_to_pack.py https://public-api.luma.com/openapi.json \
    --pack luma --out /tmp/luma --cursor-param pagination_cursor \
    --cursor-field next_cursor --more-field has_more \
    --reference-url 'https://docs.luma.com/reference/{method}_{slug}'
diff -r /tmp/luma src/charter/packs/luma
```

The review's own edits show up in that diff too; they are the glosses on about
sixty parameters the spec leaves undescribed, the conflict rules, two
validators, and the tool descriptions and docstring.

## `llms.txt` is a starting point, not a path list

Granola's omits `/v1/audit`. Assume any `llms.txt` is missing endpoints, cross-check
against the spec or the navigation, and never conclude an endpoint does not exist
because it is not listed there.

## Record what you used

Put the source you built from in the pack's module docstring — the spec URL, the SDL
endpoint, or the reference root. Two reasons:

1. **It is how the pack gets checked later.** A declaration can be diffed against the
   source it came from: do the fields still exist, are the enums still these values,
   are there new required fields the pack does not carry. Without the URL, that check
   starts with an archaeology problem.
2. **It is how the next person regenerates it.** The same reason every model's
   docstring carries its reference URL, one level up.

## When a pack is added

Extend this page. The knowledge here is per-provider and accumulates; the rules in
[`SKILL.md`](SKILL.md) are provider-agnostic and should stay that way. If you found a
vendor's machine-readable source, or found the trap in it, that belongs here so the
next author does not pay for it twice.
