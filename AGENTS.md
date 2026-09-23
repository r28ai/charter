# AGENTS.md

Instructions for a coding agent working in this repository.

## What this library is

Charter turns an API endpoint into a Pydantic schema. The schema says where each field
goes on the wire (`Path`/`Query`/`Body`), how it is encoded (`Format`), who may see
it (`Mode`), how its key is spelled (`Case`), and what the model is told about it
beyond the API's own description (`Gloss`). A deterministic runtime does the
rest. There is no LLM inside Charter and no network call except the one the schema
describes.

## Rules

1. **Core dependencies are pydantic and httpx. That is the whole budget.**
   Anything else lives behind an extra, under `src/charter/adapters/` or
   `src/charter/providers/`. `tests/test_package.py` enforces this per-module; if you
   need a third dependency, the answer is almost always a stdlib implementation.
2. **No telemetry, ever.** No analytics, no version checks, no phone-home. The
   only network calls are the API calls the user defined.
3. **No secrets in the repo.** No `.env`, no tokens in tests, no real user data in
   fixtures. Every test runs offline against `respx`.
4. **Type-checked and tested.** `uv run pytest`, `uv run ruff check src tests
   examples`, and `uv run pyright --project . --pythonpath .venv/bin/python src`
   must all be clean before you are done. `--project .` is not optional: pyright
   walks *up* from the working directory for a config file, so a
   `pyrightconfig.json` in any parent silently replaces this project's settings.
   One in the r28 monorepo turned `reportArgumentType` off for two weeks of
   Charter development, and the 55 errors it was hiding only surfaced when the
   tree was copied somewhere else.
5. **Python floor is 3.10.** Test against it if you touch typing.
6. **Never widen egress silently.** `Mode("response_only")` / `Mode("disabled")`
   fields must stay absent from the generated LLM schema at every nesting depth —
   that guarantee is what `egress.py` reports and what `tests/test_egress.py`
   pins. A change that lets a withheld field reach the model is a breaking change
   to the product's central claim, not a schema tweak.

## Layout

```
src/charter/
  types/       markers, semantic types, protobuf models, errors
  transforms/  the Format registry and its built-ins
  execution/   casing, http, schema generation, validation, executor
  tool.py      the framework-free Tool
  factories.py api_key_tool_factory, oauth_tool_factory
  auth/        the whole of authentication, and the only place it lives:
               credentials.py (CredentialProvider + shipped providers),
               oauth.py (OAuth2Server/Client), flow.py (OAuth2Flow).
               Import from `charter.auth`; nothing here is re-exported
               from `charter`.
  egress.py    the egress map — what each tool can expose to the model
  derive.py    projections — Tool.derived's keep/drop/pin, resolved by path
  types/envelope.py    Envelope — how an API reports failure inside a 200
  types/pagination.py  Pagination — where an API keeps its cursor
  text.py      decode_base64url / html_to_text, for response handlers
  adapters/    openai, langchain, mcp  (extras)
  packs/       gmail, gcalendar, gsheets, gdocs, gdrive, gforms, slack, github,
               stripe, linear, shopify, firecrawl, notion, granola, tavily
```

## Common tasks

**A form-encoded API (Stripe, Twilio, OAuth2 token endpoints).** Set
`body_format="form"` on the factory — do not hand-encode a body.

**A value the host decides per call** (an idempotency key, a tenant or
connected-account selector). That is `ainvoke(args, headers={...})` — not a schema
field, and not something Charter generates. See [docs/tools/wire-contract.md](docs/tools/wire-contract.md).

**A constant the API wants on every request** (Azure `api-version`, a
`Notion-Version` header). Use `static_query` / `static_headers` on the factory.
Never put it in the schema: the model would see a field it must not set.

**An API that returns 200 on failure.** Do not write a per-tool check. Declare an
`Envelope` on the factory — see [docs/tools/envelopes.md](docs/tools/envelopes.md). If the
API's convention fits neither shape, extend `Envelope`; the point is that it stays
declared in one place per API.

**One resource, several operations, different field contracts.** `PUT` replaces
and `PATCH` merges, so the resource model is right for one and wrong for the
other: Gmail's `Label` needs a `name` to be created or replaced and needs
nothing to be patched. Derive the patch body with `partial_of(Label,
name="PatchLabelRequest")` rather than writing a second model beside the first,
which copies every description into a place nothing keeps in sync.
`tests/test_conformance.py::test_a_patch_body_mandates_nothing` refuses a
`PATCH` whose body mandates a field, however it was built. Requiredness and
visibility are separate axes and `Mode` only moves the second, so a field one
operation requires and another cannot see (`drafts.send` reading only a
`Draft.id`) still needs a hand-written body.

**A model that keeps getting one field wrong.** Declare a `Gloss` on the field.
Descriptions hold the API's own words so they can be diffed against the reference
page; a `Gloss` is the pack's own sentence, appended to the description in
`llm_schema()` only. Stripe's refund `amount` is the case: a 3B model read
`15.00` off a spreadsheet and sent `15`, which is a valid request for fifteen
cents. Prefer a constraint where one fits, since `ge`/`le`/`pattern` are checked
and a gloss is only read.

**Adding a transform.** Register it in `src/charter/transforms/registry.py` with its
semantic type, then add a round-trip test. The semantic type is what the LLM will
see, so it must be a type a model can fill in sensibly.

**Adding a pack.** See [skills/writing-charter-packs/SKILL.md](skills/writing-charter-packs/SKILL.md).
Add it to `PACK_NAMES` in `tests/test_conformance.py`; the cross-pack checks then
apply to it automatically.

**Conformance.** `tests/test_conformance.py` checks the properties every pack must
have, across all of them at once. Most of its checks exist because the property was
violated in a shipped pack and nothing raised.
`tests/test_conformance_is_not_vacuous.py` breaks each property on purpose and
asserts the check catches it — add a mutation whenever you add a check.

**Changing execution.** `src/charter/execution/` is the deterministic core. Behaviour
there is pinned by `tests/test_execution.py`; if a change makes one of those tests
fail, that is a finding, not an obstacle.

## Recursive schemas, and where the cost actually is

Linear's GraphQL filters are mutually referential: 56 of the 77 models generated
for one tool sit in a cycle. Seventeen of that pack's 128 tools reach it, each
coming to roughly 47,000 tokens of schema, and the other 111 are all under 1,793.
Anything that walks a schema has to survive that, and two different things go
wrong here with opposite fixes. Confusing them is how the wrong fix gets written.

**Building one expanded document: memoise globally.** Expanding each `$ref` at
each reference site re-expands a shared definition once per site, which is pure
waste — the output is one document and a definition expands the same way
everywhere it appears. Getting this wrong turned a 188 KB Linear schema into
115 MB in the harness's old inliner, and `langchain_core`'s `dereference_refs`
still does it (its `processed_refs` set is added to and removed around the
recursion, so it guards per branch): on `linear.teams_list` it had not returned
after 45 seconds and had allocated 1.92 GB.

**Enumerating addressable paths: do not memoise, bound the walk.** Here the
per-branch guard in `walk_paths` is correct and a global one would be a bug. A
model reached from two fields is addressable under both, and collapsing that
makes the second unselectable by a projection. The path set is genuinely that
large — `search_issues` has 2,271,553 paths — so the fix is to stop asking for
all of them:

- `schema_paths(schema, under=..., depth=...)` starts the walk where you asked
  instead of filtering a whole-schema walk afterwards. `Tool.paths()` used to
  build 2.3 million paths and return eight. `depth` counts from `under`, not from
  the root, so drilling reaches children rather than a `_MAX_DEPTH` ceiling
  already spent. The *cycle guard* does not restart, though: `_descend` returns
  the models passed through to reach `under` and they are seeded into the walk.
  Without that, `under` was a third way to get the per-branch guard wrong —
  starting fresh reopened a cycle the root walk closes, and one tool gave two
  answers about the same prefix.

  **A listing and a lookup are not the same question.** `schema_paths` is the
  listing and applies that guard. `_siblings`, which is how `keep` works out what
  to prune, must not: the caller already holds a concrete path and is asking what
  sits beside it. Routing it through the listing turned `keep` into a silent
  no-op below any cycle — `keep={"body.filter.and_.checkbox"}` handed back the
  whole tool instead of a projection. It reads the parent model's fields
  directly, which is one level and so has nothing to guard against. Anything new
  that asks "what is at this path" belongs on that side of the line.
- `resolve_path` confirms a full dotted path with `_field_at`, one dict lookup
  per segment, rather than searching a list for it.
- `find_paths` answers the short-name and class forms by working out on the model
  *graph* (77 nodes) which models can reach a match, then walking only those.
  Pruning a branch that holds no match cannot lose one, so the paths that come
  back, and their order, are what a full walk would have produced.

`_AMBIGUITY_LIMIT = 200` is where that search stops counting. Two matches settle
"is this ambiguous", but *nineteen fields named `index`* is a more useful error
than *several*, and 200 keeps the exact count for every schema in the catalogue
that terminates while bounding one that does not.

The same mistake has now been made five times in this repo, twice in code that
walks a *published* schema rather than the models: the harness's old `inline_refs`,
`langchain_core`'s `dereference_refs`, two drafts of `charter_arm.recursive_paths`,
and `tests/test_conformance.py::_described_leaves`, which produced **13,936,305
leaves in 30 seconds without finishing** on `linear.teams_list` and left the
conformance suite unable to complete for any pack after Linear. That one wanted a
single visited set: it asks whether any offered field is described as read-only,
so one route to a definition answers it and a million only bury the answer.

**Where the cost is not.** `to_json_schema()` is cached on first use: 0.24s to
generate and 0.01s to copy, and the copy is deliberate because adapters hand
`parameters` out by reference. It is not a hot spot and caching it again buys
nothing. Profile before changing anything here — the answer has been
`schema_paths` both times it has been asked.

**The store is shared, so it is threaded.** A pack factory owns one
`SchemaStore`, every tool it builds reads it, and views are derived on first use
— so the readers are whichever threads reach those tools. Two rules follow, and
both have been broken once:

- Nothing enters the store until it can validate. A generated model holds
  unresolved forward refs until `_rebuild_generated` runs at the end of the root
  walk, so the walk stages its models in `_pending` and publishes once, only the
  complete ones. Publishing as it went let a reader memoise a model that raises
  `not fully defined` on every call for the life of the process.
- One root walk per store at a time. `create_llm_schema` holds the store's lock
  across the whole walk, not around each access — two interleaved walks each
  build their own copy of a shared subtree and then read each other's, and the
  view that comes out holds two generations of one graph. That is a correctness
  bug that reads as a size bug (193KB → 382KB on `custom_view_create`), and
  serialising is also about 2.5× faster, because the second thread stops
  rebuilding what the first is already building.

A `Tool` also guards its own memo, which matters where there is no store at all —
a `Tool` built outside a factory. Lock order is always tool then store; nothing
inside a walk reaches back into a `Tool`.

## Things that look like bugs but are not

- **`model_dump()` returns snake_case** even though the wire gets camelCase. That
  is deliberate — the casing conversion happens at serialization, in `call_api`.
- **Custom `Mode` values are inert when the tool declares no mode.** Only
  `response_only` / `request_only` / `disabled` are unconditional.
- **`bytes` and `base64url` encode identically.** The separate name exists for
  fidelity with Google API specs.
- **The body shape follows the schema, not the call.** Unwrapping a single
  `Body()` field is decided by how many the *schema* declares, never by how many
  happen to be populated — otherwise the same tool would send different shapes on
  different calls.
- **A trimming handler must preserve the paging signal.** Dropping `has_more`
  leaves pagination with only the cursor to stop on, and some APIs (Stripe) always
  have one.
- **Response handlers only ever see successes.** HTTP errors and envelope
  failures both raise before the handler runs, so a handler needs no defensive
  check at the top.
- **A model from `partial_of` needs a `# type: ignore[valid-type]` where it is
  named as a type.** It is built by `create_model` at import, so a static
  checker cannot follow it into an annotation. Pydantic resolves it fine. The
  comment above `partial_of` in `execution/schema.py` records the alternative
  shape and the count at which it becomes worth building.
- **An unset field is omitted, never sent as `null`.** Bodies are dumped with
  `exclude_none=True`. That is Google-style patch, where absent means unchanged.
  An API using RFC 7396 merge-patch, where `null` deletes a field, cannot be
  expressed today.
- **A generated schema's property names are wire names.** `to_json_schema()`
  emits `filterData`; a projection selector names the field, `filter_data`. A
  path read off the JSON schema and passed to `keep`/`drop` is rejected as a
  field of no model. Walk `args_schema.model_fields` when the output feeds a
  projection.
- **`to_json_schema()` copies on every call, on purpose.** Adapters hand
  `parameters` out by reference, so a shared dict would let one caller's edit
  corrupt the tool for every later one. The copy is 0.08 ms on a small tool and
  **10.9 ms on a 188 KB Linear tool**, so an adapter rebuilding 20 fat tools per
  turn spends a quarter of a second copying. Projected, the same twenty cost
  2 ms. Do not remove the copy; narrow the tool.
- **`Tool.paths(by_cost=True)` is slow on purpose.** It prunes each path for real
  and regenerates the schema, so the number it reports is what `drop` will
  produce rather than an estimate from subtree size. One level of
  `search_issues` is about 15 seconds. That is the measurement being honest, not
  a regression; price a level, not a subtree.
- **`quota_cost` does nothing at runtime.** It records what one call costs against
  the provider's own rate limit, in that provider's units. It is metadata for a
  future budget policy, and it is expensive to re-derive, so it is carried now.

## What not to do

- Do not add orchestration — pagination loops, retries, multi-call compositions.
  They belong in the calling agent. See "What this can't express" in the README.
- Do not add a global config object or read ambient state. Everything the runtime
  needs arrives as an argument.
- Do not swallow a transform or validation failure. A silently untransformed value
  reaches the API as a confusing 400 that nobody can trace.
