# Changelog

Notable changes to Charter. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0, minor versions may break the public API. Anything that does will say so
here, with the migration in the same entry.

## [Unreleased]

### Changed

- **The documentation URL is `docs.r28.ai/charter`.** `DOCS_BASE` is, by its own
  docstring, the one place a URL is spelled, and it named `charter.r28.ai`, a
  host that does not resolve. Every one of the 56 `docs=` slugs in the library
  rendered a link there, and so did the agent-setup prompt, the `llms.txt` and
  `.md` instructions in *Coding agents*, and `reference/errors`. All fourteen
  references now point at the site that is actually served, as does
  `pyproject.toml`'s `Documentation` URL. An error you have seen before prints a
  different link.

### Fixed

- **The pyright gate was never running Charter's own configuration.** Pyright
  searches *upward* from the working directory for a config file, and the
  monorepo this tree was developed in has one at its root, written for a
  different package, which turns `reportArgumentType` off. Every run made from
  `oss/` read that file instead of this project's `pyproject.toml`, so the gate
  reported zero errors on a tree that had fifty-five. Copying the tree to a
  different parent directory is what surfaced them, which is not a way to find
  out. Every invocation — both workflows and the one in `AGENTS.md` — now passes
  `--project .`, which pins the config to this repository and makes the result
  independent of where the checkout sits.

  What was hiding under it, none of it caught by a test because all four are
  matters of what the code *says* rather than what it does:

  - `ToolExecutor` and `Tool` each assigned six `Literal`-typed parameters
    (`method`, the three `KeyCase`s, `body_format`, `query_format`) to bare
    attributes. Inference widens a literal to `str` on the way into an
    attribute, so the values handed straight back to `call_api` no longer
    matched the `Literal`s it declares. Written out now.
  - `Pagination.has_more` and `next_page_args` read `per_page_param`,
    `page_param` and `cursor_param` — `Optional` on the dataclass, guaranteed
    present by `__post_init__` for whichever style is in use — without saying
    so. They take the local-plus-assert the `page` branch already used.
  - `Envelope.credential_errors` was annotated `FrozenSet[str]` while the
    class's own docstring, three docs pages and the Slack pack all pass a set
    literal that `__post_init__` freezes. It is `AbstractSet[str]` now, which is
    what the constructor has always accepted; the stored value is unchanged.
  - Eighty-eight fields across the thirty request models that are used as a
    `default_factory` spelled their default positionally, `Field(None, ...)`.
    Pyright does not read that as a default, so those models appeared to have
    required arguments and passing one as a factory was an error. They are
    `Field(default=None, ...)` now. The same spelling is still used by fields
    elsewhere in the packs, where nothing depends on the checker seeing the
    default; a user who constructs one of those models with no arguments in
    checked code will see it reported as missing arguments until that is
    changed too.

- **Two threads sharing a schema store no longer splice two type graphs into one
  tool.** Holding a model back until it can validate closed one hazard in a
  shared store and left the other open: the store is read and written without
  coordination, so two walks of the same graph interleave. Each builds its own
  copy of a subtree, then adopts, for a branch it has not reached yet, a model
  the other published — which references *that* walk's copies of children this
  one already built. What comes out is one view holding two generations of the
  same types. Where the two generations are identical pydantic folds them back
  together and nothing shows; where they are not it emits both. On
  `linear.custom_view_create` it emitted both: 80 definitions became 136 and a
  193KB schema became 382KB. It is intermittent: eight threads onto a cold pack
  produced it on some runs and not others, never on a serial one. That is the
  whole problem, because Fireworks refuses a Linear tool past a depth of 50 and
  the refusal takes every other tool in the request with it. A schema that
  doubles on a process which happened to start busy is not a slow path, it is an
  outage that does not reproduce.

  The lock belongs on the store, not on the tool: one store is read by every tool
  in a pack, so two threads building two *different* tools still meet inside the
  same graph. `SchemaStore` is that store and carries it, held across a whole
  root walk rather than around each access — the hazard is a stale generation,
  not a torn entry. A plain dict is still accepted, as the documented
  caller-owned argument it has always been, and falls back to one process-wide
  lock rather than to no guard. Serialising is also *faster*, because the second
  thread stops rebuilding what the first is already building: 145 Linear tools
  first-touched by eight threads go from 21.1–22.4s to 7.8–9.2s, with the
  duplication gone in 3 of 3 runs. No shape of use regresses — where every thread
  wants every tool and waiting gains nothing, it is 3.7s either way.

- **The first call against a tool no longer blocks the event loop, and no longer
  reports its build as validation.** Deriving on first use moved seconds of pure
  CPU out of import and into whichever call arrives first. `ainvoke` is a
  coroutine and the build ran inline, so on a cold `linear.issues_list` the loop
  went 1,634ms without a tick — every other call in that process stalled behind
  one tool being built for the first time. It also ran inside the validation
  timer, so that call reported 1,630ms of *input validation*, in the field a host
  watches to find out whether the model is sending malformed arguments.

  The build now runs on a worker thread — the worst stall measured on the same
  tool is 68–102ms, the GIL rather than the work — and is reported as
  `schema_ms`, zero on every call but the first. `validate_ms` on that call is
  0.1–0.3ms and means what it says again. `Tool.prepare()` below is how it stops
  happening inside a request at all.

- **A schema whose annotations do not resolve fails at declaration again.**
  Deriving on first use was argued safe because everything that can fail stayed
  eager, and two things were kept for it: `derived()` resolves its selectors
  before a `Tool` exists, and a pinned tool builds its exec view at construction.
  Neither covers the walk itself. A model pydantic left incomplete — a forward
  reference naming a class that was renamed, a `model_rebuild()` a pack forgot —
  declared a tool without complaint and then raised a bare
  `PydanticUndefinedAnnotation` out of the first agent run to touch it. That is
  the shape which once left 17 Linear tools unable to emit a schema at all, and
  the shipped packs are only covered against it because the conformance suite
  touches every tool; a pack someone else writes is not. Construction now walks
  the source models and raises a `DeclarationError` naming the class and the fix.
  The walk is on the graph, where each model appears once, and a factory
  remembers what it has already cleared — 6.5ms for Linear's 145 tools, 25ms
  across all 566 the packs declare, against 208ms for Linear without the memo,
  since its tools share one filter graph. Nothing is recorded by a walk that
  raised, so a failure cannot certify the models it had reached. Import is
  unchanged: 2.19s to 2.28s for Linear, 5.62s to 5.52s for ten packs, measured
  interleaved in matched worktrees with warm bytecode.

- **Drilling in with `Tool.paths(under=...)` no longer reopens a cycle the root
  walk closed.** Starting the walk at `under` started it with an empty cycle
  guard, so a field whose type is already its own ancestor was listed again and
  one tool gave two answers about the same prefix: `paths("body.filter.and_")` on
  `notion.data_sources_query` offered 27 children of a filter that *is* that
  filter, while `paths("", depth=4)` said the prefix has none. Eight schemas
  across gmail, gsheets and notion disagreed with their own root walk this way,
  at the third level rather than the eighth the docstring claimed. The models
  passed through to reach `under` are now handed to the guard, and a differential
  run against a naive full walk — 529 terminating schemas, every model-valued
  prefix, depths 1 to 3 — agrees on all of them. Such a path stays addressable if
  written out; dropping one is the negative-cost case, since it splits a shared
  `$def` rather than removing anything.

  Only the *listing* changed. `keep` resolves a selector and prunes its
  siblings, and it was asking for those siblings through this same function —
  so the first version of this fix silently turned `keep` into a no-op below any
  cycle: `keep={"body.filter.and_.checkbox"}` returned the whole 21,849-byte tool
  where it had returned a 3,383-byte projection. A projection that quietly grants
  everything is the failure this module exists to prevent, so the two questions
  are answered separately: `paths()` lists, and the sibling lookup reads the
  parent model's fields directly, which is one level and has nothing to guard
  against. Checked against the previous implementation on all 12,394 paths of
  every tool in the 15 packs: identical.

  **Migration:** `paths(under=...)` returns `[]` for a prefix whose type is
  already its own ancestor, where it used to list that type's fields again. Ask
  one level up: `paths("body.filter")` names the same fields, because
  `body.filter.and_` is that same filter. Projections are unaffected, and so is
  `paths()` anywhere a type does not repeat on its own path.

- **A schema store no longer hands out a view that cannot validate.** Deriving a
  tool's view on first use moved the build off the import thread, where it was
  serialised by the import lock, onto whichever caller reached the tool first —
  and a `Tool` is a process-wide object that several threads reach at once
  (`Tool.invoke` is synchronous, so a WSGI worker pool, a sync LangChain agent on
  an executor, and `to_openai_tools` inside the turn loop all put it there). A
  generated model is unusable until the walk resolves its forward references at
  the very end: mid-walk, 49 of the 78 models Linear's filter graph produces are
  still incomplete, and every one of them was published into the factory's store
  as it was built. A second thread reading the store in that window took one for
  finished, and **memoised it permanently** — the tool then advertised a schema
  to the model and raised `... is not fully defined` on every call made against
  it, for the life of the process. Reproduced on `charter.packs.linear`: six
  threads first-touching ten list tools left three of them broken for good. The
  same trail of half-built models was left behind, with no second thread
  involved, by any walk that raised before the rebuild.

  The store is now written once, at the end of the root call, and only with
  models that are complete; a walk that raises leaves it exactly as it found it.
  A tool's own memo is guarded, so callers that arrive together get one view
  rather than two, and the second no longer overwrites the one the first handed
  out.

- **A projection rebuilds nothing the tool it narrows already built.** `derived()`
  rebuilt a `Tool` by listing its arguments and did not pass the factory's schema
  store, so every projection derived the whole type graph alone. Only subtrees no
  prune path reaches are ever shared, which is exactly the set an added prune
  cannot change — the condition `path_costs` already relies on to price a level
  against one store. Eight projections of `linear.issues_list` cost 11.3s of
  first use and now cost 1.6s, measured in matched worktrees with warm bytecode
  on both sides; importing a pack is unchanged. This is the deployer's path, and
  it was also the packs' own: Linear ships 17 projections, and its curated list
  tools — the ones a session exposes — are all of them. A test now reads
  `Tool.__init__`'s signature and fails if `derived()` drops another argument.

### Performance

- **Importing a pack no longer builds every tool's view.** `charter.packs.linear`
  took 29.5 seconds to import. Two causes, both in how the model-facing view is
  derived. Tools in a pack reach the same types constantly — Linear's 128 tools
  share one filter graph — and each tool rebuilt the whole graph for itself, so
  constructing the pack called `create_llm_schema` 16,149 times; a factory now
  owns one of the caller-owned caches that function already documents, and a type
  no prune reaches is built once for the pack. And the view was derived at
  construction on the reasoning that building it is cheap, which holds for one
  tool and not for 128 that a session will never all expose; it is now derived on
  first use and memoised.

  Linear imports in 2.2s, and ten packs together in 4.9s against 37.5s. Nor is
  the cost merely moved — first use of a six-tool session adds 0.25s, and
  touching all 128 tools adds 1.4s, which is still less than the 2.9s the eager
  build cost at import.

  What stays a declaration-time error: `derived()` still resolves its keep/drop
  paths before a `Tool` exists, a pinned tool still builds its exec view at
  construction, and — added after this entry first claimed more than it had
  earned — construction checks that every model the schema reaches can resolve
  its own annotations, which is the one error the walk itself actually raises.
  See the entry under **Fixed**.

### Changed

- **Linear's filters are curated for the model, and the whole filter is still
  there.** Every list tool mirrored Linear's complete filter input, which made
  one tool 187KB across 77 definitions — the recursion through `and_`, `or_`,
  `parent` and `children` is most of that. Measured on the `linear_triage` task,
  thirty generations per cell at temperature 0: given a tool with the filter
  removed, three of three models never filtered and paged the whole team 250
  issues at a time; given the full 187KB mirror, `glm-5p3-flash` filtered 22/30
  and `deepseek-v4p1-flash` and `nemotron-lightning-3.5` **rejected the request
  outright**, 30 times out of 30; given a curated filter, 28/30, 30/30 and 4/30.
  What is rejected is the recursion, not the size: the same models accept
  `gsheets.spreadsheets_batch_update` at 195KB, which is larger and has no cycle.
  A rejection takes every other tool in the request with it. Each filter now
  offers the entity's own comparators plus one level into its single-valued
  relations, by one mechanical policy in `charter.packs.linear.curation` rather
  than sixteen judgements. No tool a model is offered exceeds 50KB. Nothing is
  lost: every narrowed tool keeps an undiminished twin — `issues_list_full`,
  `teams_list_full`, and so on — carrying the complete filter and deliberately
  absent from `TOOLS`, so a caller who needs boolean composition reaches for it
  by name. **Migration:** `and_`/`or_`, collection conditions and sub-issue
  filters on a narrowed tool now fail validation before a request is built; move
  those calls to the `*_full` twin.

- **`issues_list` stops fetching what only one issue needs.** The list path and
  the single-issue path shared one field selection, so every node in a page of
  250 carried its full `description` — a paragraph, or a pasted stack trace.
  The list now asks for what identifies an issue and `issue_get` keeps the whole
  selection. This is the GraphQL form of the cap `gcalendar.events_list` puts on
  `description`: Calendar returns the whole event whether or not the caller wants
  it, so the weight has to come off in the response handler, while here it can
  simply not be requested.

### Added

- **`Tool.prepare()` — derive a tool's view at startup rather than in a request.**
  Importing a pack no longer builds its tools' views, which is right: a session
  exposes a handful of a pack's tools and deriving all 128 of Linear's would be
  most of the import. But the cost did not disappear, it moved onto whichever
  call arrives first, and on a recursive schema that is about 1.8s. `prepare()`
  builds both views and the JSON schema, returns the tool, and is idempotent and
  thread-safe:

  ```python
  from charter.packs.linear import TOOLS

  for tool in TOOLS:
      tool.prepare()
  ```

  `ainvoke` derives what it needs on a worker thread if this was never called, so
  skipping it costs latency on one call rather than the event loop. Nothing can
  do that for a synchronous caller — `to_openai_tools` is documented to run
  inside the turn loop and calls `to_json_schema`, which blocks the thread it is
  on. Constructing a `ToolSession` is already `prepare()` for the tools it holds,
  because partitioning sizes every schema and sizing one builds it: about 2.5s
  for Linear's 128, on whichever thread builds the session. That is now written
  down where it can be read, along with `progressive=False` as the way out of it.

- **`ToolCall.schema_ms` — what deriving a tool's view cost, on the call that
  paid.** Zero on every other call, and reported separately because it was being
  reported as `validate_ms`. It also appears in `to_dict()` as
  `charter.duration.schema_ms` and on the INFO log line, which otherwise reports
  a one-off build as a slow call and leaves the API holding the blame. After a
  startup pass with `prepare()`, a non-zero `schema_ms` in production means a
  tool nobody prepared.

- **`ToolSession.dispatch` takes a `client`.** `Tool.ainvoke` has always
  accepted an `httpx.AsyncClient` to reuse, so a loop you drive yourself can hold
  one connection pool open instead of paying a TLS handshake — about 114ms
  against the APIs these packs cover — on every tool call. A session sat in the
  middle of that and dropped the argument, so anyone routing through `dispatch`
  could not reach it. It is now passed through unchanged. `ToolSearch` makes no
  request, so a client passed alongside one is inert. A call that names no client
  behaves exactly as before.

- **Google Forms, six tools over two collections.** `forms_create`,
  `forms_get`, `forms_batch_update` and `forms_set_publish_settings` on the
  forms collection; `forms_responses_get` and `forms_responses_list` on the
  responses one. The whole `Item` graph is modelled: every question kind, its
  options, its media and its quiz grading, with each documented `oneof`
  enforced as a validator against the model's own input rather than by a 400.

  Two things this pack is the first case of. `Info` is one resource that two
  operations disagree about: `documentTitle` can be set on create and cannot be
  modified by a `batchUpdate`, and the form description is the other way round.
  Rather than two near-identical models that drift, `Info` carries
  `Mode("create")` and `Mode("update")` and each tool declares which it is, so
  neither endpoint is offered a field Google would refuse. And the two halves of
  the API take different scopes: `forms.body` does not reach the responses, so
  the two response readers carry `forms.responses.readonly` instead of the pack
  default.

  `forms_get` has no response handler on purpose. Google's documented way to
  change a question is to read the form, edit your copy of the item and write it
  back with the IDs unchanged, so a reshaped item is one that cannot be written
  back. The responses collection is trimmed, where nothing is written back: an
  answer arrives as 64 bytes of nesting around 3 bytes of value, and
  `forms.responses.list` returns up to 5000 of them.

  Two entries were added to `_SERVER_OWNED_EXCEPTIONS` with Google's own
  contradicting sentence beside each: `documentTitle` is "Output only" and "can
  be set on create", and `questionId` is "Read only" and is what
  `UpdateItemRequest` reads to identify the question being changed.

- **`Gloss`, for what a model needs to know and the API does not say.** A field's
  `description` is the provider's own text, which is what makes it checkable: it
  can be diffed against the reference page, and anything that does not match is
  either an API change or a mistake. That left nowhere to put a sentence the
  docs do not contain, so the sentence went into the description and the two
  became indistinguishable.

  A gloss is a note written beside a text its writer may not alter, which is
  the position a pack is in. `Gloss("Cents, not dollars: $15.00 is 1500.")` is
  declared beside the description and appended to it in `llm_schema()` only.
  Every adapter reads that view, so a pack declares the gloss and nothing else;
  the wire schema keeps the documented text exactly.

  Stripe's `POST /v1/refunds` is the case it came from. "A positive integer in
  the smallest currency unit" is Stripe's phrase and it is correct. A 3B model
  reading `15.00` off a spreadsheet sent `amount=15` and refunded fifteen cents,
  which nothing rejects: units are the caller's to get right, the request is
  valid, and the API answers `200`. `refunds_create` now declares the gloss, and
  its reference page prints it.

  Prefer a constraint where one fits. `ge`/`le`/`pattern` and `ConflictsWith`
  are checked before the request leaves and a gloss is only read.

- **Two fields checked against the vendor's own reference, and one of them was
  wrong.** Google Calendar documents
  `conferenceData.createRequest.status.statusCode` as Read-only. `createRequest`
  is a field a caller does send, so the status rode along into the LLM view of
  every write that can attach a conference: a field the model could only get
  wrong, on three tools. It is `Mode("response_only")` now.

  `test_no_field_the_vendor_calls_server_owned_reaches_the_model` asks the
  published schema rather than the declarations, because the `Mode` cascade
  means a withheld parent covers its children and the declarations alone cannot
  answer it. Four fields are enumerated as exceptions with the vendor's sentence
  beside each: two are conditionally read-only (Sheets' `gridProperties` only
  for a DATA_SOURCE sheet, `importFunctionsExternalUrlAccessAllowed` only while
  true), and two are sentences about something else (Drive's content
  restriction, whose *meaning* is read-only, and Calendar's `syncToken`, where
  "read-only fields" describes other fields in the same sentence).

- **Slack: a description from the wrong method, and a default the docs state.**
  `conversations.history`'s `limit` said "even if the end of the users list has
  not been reached", which is Slack's wording for `conversations.replies` and
  `users.list`; for this method Slack writes "the end of the conversation
  history". `latest` dropped Slack's "Default is the current time", and the
  `replies` pair stated neither documented default. All four `oldest`/`latest`
  parameters are strings, so a millisecond value is accepted and selects an
  empty window rather than failing, and they now say so.

  `chat.scheduleMessage`'s `post_at` is the shape the marker was written for.
  Slack's sentence is "Unix timestamp representing the future time the message
  should post to Slack"; the pack had paraphrased it, added "in seconds", and
  folded in the 120-day limit and the thirty-per-five-minutes rate limit from
  elsewhere on the page. Slack's sentence is restored and all three additions
  are in the gloss, where they are the pack's own words and diffing the
  description still means something.

- **`google.type.TimeOfDay`'s bounds are not carried after all.** They were
  added in this entry's first pass and taken back out: the model is reachable
  only under `dataSourceSchedules`, which Google documents Output only and the
  pack marks `Mode("response_only")`. A constraint exists to turn a 400 into a
  local error, and there is no request here to reject. `outlier_percentile`
  keeps its bound, which is on `spreadsheets_create` and
  `spreadsheets_batch_update`.

- **Every money and timestamp field in the packs now tells the model its unit.**
  `refunds_create` was the field a 3B model got wrong in the harness. Grepping
  for the phrase that made it wrong found the rest: nine money fields across
  Stripe carrying "smallest currency unit", and twelve epoch-seconds fields.
  `payment_intents_create.amount` is the one that matters most, since it is
  required and it charges a customer.

  Also glossed: Shopify's `price` and `compare_at_price`, which are decimal
  strings and so the exact inverse of Stripe's integer cents, and the two
  Firecrawl timeouts that carry no documented bound. The other seven timeouts
  across Firecrawl and Tavily needed nothing: they already carry the bound the
  vendor documents, so a wrong unit is a local validation error naming the
  bound, which beats a sentence.

  Two checks hold the class rather than the instances. Every Stripe field whose
  description says "currency unit" must carry a gloss, and so must every one
  that says "Unix timestamp" or "Epoch time". The second found
  `invoices.due_date`, which the source sweep had missed because its
  description is an f-string.

- **Stripe's `unit_amount_decimal` said "as a string" and not what the string
  means.** Stripe writes "a decimal value in the smallest currency unit with at
  most 12 decimal places"; three copies of the field had paraphrased that down
  to "The amount with decimal places, as a string", which drops the unit. A
  model reading it writes `"15.00"` for fifteen dollars and prices the item at
  fifteen cents, silently, on a recurring price. The vendor's sentence is
  restored on all three, and the gloss covers what it still cannot say: the
  decimal places are fractions of a cent.

- **Five documented bounds that were prose only.** `google.type.TimeOfDay`'s
  `hours`, `minutes`, `seconds` and `nanos` state their ranges in the
  description and enforced none of them, and so did a histogram's
  `outlier_percentile`. Where Google hedges ("typically must be", "an API may
  allow"), the permissive bound is the one carried: `le=60` for the leap second
  and `le=24` for a closing time, because a constraint that refuses a value the
  API accepts turns a valid call into a local error the model cannot tell from
  anything recoverable.

- **Three transport facts the wire contract could not previously state.**
  Each was added for an endpoint GitHub actually serves and each is off by
  default, so nothing already shipped changes behaviour.

  `follow_redirects`, on both factories and per tool, for the endpoints whose
  *answer* is a redirect — GitHub hands out Actions logs and artifacts as a 302
  to a signed URL that lives one minute, and a caller that does not follow it
  receives an empty body and no second chance. `False` by default because on a
  JSON API a 3xx is usually a wrong URL and following it silently hides that.
  httpx drops `Authorization` when a redirect leaves the origin, so the bearer
  token does not travel to the storage host.

  `body_format="raw"`, for the endpoints that take a *file* rather than a
  document: the body's bytes are sent with no encoding, and the `Content-Type`
  is the declaration's to set, because nothing can be inferred from an arbitrary
  byte string. `static_body` is refused against a raw body rather than silently
  dropped — there is no object to add a key to.

  **A response that is not text keeps its bytes.** `resp.text` decodes against
  the declared charset and *replaces* whatever does not fit, so a ZIP or a PNG
  came back as replacement characters that read as content — the "decode that
  degrades instead of failing" failure, one layer below where a response handler
  could catch it. A non-textual body is now returned as
  `{"raw_base64", "content_type", "size_bytes"}` instead. A declared `charset`
  is what marks a body as text, which is the one signal that covers the vendor
  media types no list can enumerate.

- **GitHub — 110 more tools, taking the pack from 29 to 139.** CI debugging,
  code review down to a line of a diff, the Git object store, issue metadata,
  releases, notifications and security alerts.

  The two blocks that change what an agent can *do* rather than what it can see:

  `actions_download_job_logs` and its siblings answer the question the pack
  could not — *why* did the build fail. GitHub serves a job log as a 302 to a
  signed URL that lives one minute, so those tools set `follow_redirects`, and
  what comes back is not the file: a job log is routinely megabytes, and the
  handler keeps the last 200 lines plus every line that looks like the failure,
  with the real length stated beside it. `checks_list_annotations` is the cheap
  path to the same answer where the check reported one — a file, a line and a
  message GitHub has already extracted.

  `pulls_create_review_comment` is the primitive reviewing is made of.
  `pulls_create_review` leaves a verdict on a whole change; this leaves a remark
  on the line that earned it. Its three placement rules are validators rather
  than round trips, and `in_reply_to` is refused alongside them: GitHub *ignores*
  the placement fields on a reply, so a model that sets both gets a 201 and a
  comment somewhere it did not choose.

  `git_trees_create` + `git_commits_create` + `git_refs_update` is the atomic
  multi-file commit. `repos_create_or_update_file` is one file per commit, so a
  refactor across six files was six commits and six CI runs; this is one. The
  two ways it goes wrong are declared: omitting `base_tree` writes a tree
  containing only the listed entries, which commits as a deletion of everything
  else, and an omitted `parents` is a root commit whose failure surfaces a step
  later as a non-fast-forward. Both are refused locally with the reason.

  Three places GitHub leaves the shape the pack assumed, each declared rather
  than worked around: `pulls_get_diff` is `pulls_get` asked for a different
  representation through `Accept`, so it is a second factory with the header
  pinned rather than a schema field the model could set; `releases_upload_asset`
  posts raw bytes to `uploads.github.com`, so it is a third factory with its own
  base URL and `body_format="raw"`; and a run's logs arrive as a ZIP where a
  job's arrive as text, so that handler opens the archive.

  Not modelled, and said so in the pack docstring: Projects v2 and resolving a
  review thread are GraphQL-only, and the Actions secrets *write* endpoints take
  a libsodium-sealed box, which is a dependency this library does not have.
  `actions_list_repo_secrets` reads the names, which is the part an agent
  debugging a workflow needs and the one endpoint that cannot return a value.

- **Notion — 35 tools over the REST API.** Users, pages, blocks, databases, data
  sources, search, comments, file uploads, custom emojis and async tasks.

  Written for the `2025-09-03` split, where a database is a container and a
  **data source** is the table inside it: columns belong to the data source,
  rows are queried from it, and a page created in a database takes a
  `data_source_id` as its parent. `databases_retrieve` keeps the `data_sources`
  list so the ID for the next call is in the response.

  `Notion-Version` is pinned to `2026-03-11` in `static_headers`. Notion requires
  the header on every request — omitting it is `400 missing_version` — so there is
  no unpinned mode, and this is the version that renamed `archived` to `in_trash`
  and replaced block append's `after` with `position`.

  Blocks nest in three declared tiers rather than recursively, because Notion
  accepts two levels per request and publishes a schema per tier: `Block` (31
  kinds), `NestedBlock` (29 — no `column` or `column_list`) and `LeafBlock` (28,
  holding nothing — a `table` is its rows). A tree too deep is refused locally
  instead of by a 400.

  Enums come from Notion's own OpenAPI document rather than its prose: the code
  languages are the full 90, and `apiColor` carries 20 values including
  `default_background`. `number.format` is declared an open string there, so it is
  modelled as `str` rather than as a closed `Literal` that would start refusing
  valid values.

  Not modelled: sending file bytes, which is `multipart/form-data` and outside the
  wire contract — `mode="external_url"` completes an upload without it. Notion's
  agent and session platform, the Views API and meeting notes are not covered.

- **`Mode` now applies inside a `Dict[str, Model]`.** `create_llm_schema` walked
  nested models and lists of them and copied a dict of them across whole, so every
  `response_only` field under one was offered to the model. That is an egress hole
  rather than an ergonomic lapse: a withheld field is how a pack keeps something
  out of a model's context window. Notion's page `properties` is the shape that
  found it — a map of column name to value, a third of whose types the server
  computes and rejects on write. `egress_map` walks dicts for the same reason, so
  the printed map and the schema agree.

- **A model serializer survives onto the LLM view.** `create_model` drops
  validators and serializers alike, and `_carry_validators` put only the first
  back. The LLM view is the instance the runtime dumps, so a dropped serializer
  changes the bytes on the wire and nothing raises. It is what lets a field Python
  will not let you name reach the API under its own spelling: Notion's compound
  filter is `{"and": [...]}`, and `WireName` cannot reach it, since key conversion
  carries per-field markers at the top level of a body only.

- **Every OAuth pack's page says where the first grant comes from.** The signpost
  was rendered only for a server with a provider page of its own, so a pack
  without one showed a snippet reading a refresh token out of the environment and
  never said how it got there.

- **`Tool.derived()` — a projection of a tool, narrowed by whoever deploys it.**
  `Mode` is the pack author's lever, fixed when the pack is written. This is the
  other half: `keep`, `drop` and `pin` narrow a tool you did not declare and
  cannot edit.

  `keep` selects within the sibling group it names, so keeping three members of
  the Docs `Request` union drops the other 30 and leaves `document_id` alone.
  `drop` removes a path. `pin` removes a path from the view the model fills in and
  keeps it in the one the runtime executes, so the field is neither visible to the
  model nor reachable by it, and a pinned value is indistinguishable on the wire
  from one passed by hand.
  Selectors are dotted paths, unambiguous field names, or the model class a field
  is annotated with; `Tool.paths()` lists them.

  The tool underneath is unchanged — same URL, credentials, validators and
  `extra="forbid"` — so a projection can only ever remove, and an argument outside
  it raises `ToolValidationError` before a request is built. Naming nothing,
  naming several things, or dropping a field the API requires raises
  `DeclarationError` at declaration rather than at the first 400.

  Two things this is for, and the second is the reason it exists. Context:
  `documents_batch_update` is 8,874 tokens of schema before the model reads the
  task, and narrowing it to three edits is 1,942, or 78% smaller. Permission:
  Google's `documents` scope grants all 33 edits as one indivisible grant, with
  no scope for "may edit text, may not delete content". The union member is the
  capability, so pruning it is the only place that permission can be expressed.

  Both halves print in `egress_map()`, with a pinned field carrying its value,
  because a restriction a reviewer cannot read is not a control. See
  [docs/tools/projections.md](docs/tools/projections.md).

- **Google Sheets goes from 5 tools to 17 — every method the v4 reference
  documents.** The pack could read a range and append to one, but not update,
  clear, or address several at once. Added `spreadsheets_values_update`,
  `spreadsheets_values_clear`, `spreadsheets_values_batch_get`,
  `spreadsheets_values_batch_update` and `spreadsheets_values_batch_clear`;
  the three `values_batch_*_by_data_filter` tools; `spreadsheets_sheets_copy_to`
  and `spreadsheets_get_by_data_filter`; and both
  `spreadsheets.developerMetadata` methods, `spreadsheets_developer_metadata_get`
  and `spreadsheets_developer_metadata_search`.

  The `batchUpdate` `Request` union carries all 74 documented edits, each a
  oneof the schema enforces before the call, and the spreadsheet resource is
  modelled down to the Developer Preview comment types — `CommentThread`,
  `Post`, `CommentAnchor` — with every `Output only` field withheld from the
  model.

  `test_pack_ships_every_documented_endpoint` names the method list rather than
  counting it, so the next method Google adds fails the suite instead of
  passing it quietly.

- **Gmail goes from 9 tools to 23.** The pack could list message ids but not
  read one, save a draft but not find it again, create a label but not recolour
  it. Added `messages_get`; `drafts_get`, `drafts_list`, `drafts_update`,
  `drafts_delete` and `drafts_send`; `labels_get`, `labels_update`,
  `labels_patch` and `labels_delete`; `threads_modify`, `threads_trash`,
  `threads_untrash` and `threads_delete`.

  `messages_get` and `drafts_get` run trimming response handlers, as do the
  three thread writes, so a MIME tree reaches your model on none of them.
  `messages_get` accepts Gmail's full `format` enum: `raw` is parsed rather
  than handed back, and `minimal` returns no `bodyText` key rather than an
  empty one, because "the message is empty" and "you did not ask" are
  different facts.

  **`threads_delete` asks for a scope the rest of the pack does not.** Google
  covers every other Gmail endpoint here with `gmail.modify` and requires
  `https://mail.google.com/` for the delete that cannot be undone. It is
  declared on that tool, not on the pack, so `scopes_for` widens a consent
  screen only when you hand that tool out — drop `threads_delete` from your
  list and your users see `gmail.modify` and nothing more.

- **`partial_of(model, name=..., doc=...)`** derives a model with every
  top-level field optional: the body of a `PATCH`. One resource routinely
  serves create, update and patch and the operations disagree about what is
  mandatory, so the patch body is derived from the resource rather than copied
  out beside it. Descriptions, constraints and the `Path`/`Query`/`Body`/
  `Mode`/`Format` markers all come across, and so do validators, so partial
  does not mean unconstrained. Nested models are left alone. See
  `docs/reference/markers.md`.

### Changed

- **A lone `Body()` field carrying a scalar keeps its name.** Unwrapping promotes
  a nested structure's fields to the root of the request, which is right for a
  model — GitHub's `issues_create`, every Google pack — and meaningless for a
  scalar, which has no fields to promote. Taken literally it built a request no
  API accepts: a bare `"C0123"` as the whole JSON document, or, on a form-encoded
  API, a local `DeclarationError` before anything was sent. `unwraps_body` now
  decides this in one place, for both `call_api` and the transform routing.

  **Migration:** a tool of your own whose only body field is a scalar now sends
  `{"field": value}` where it sent `value`. A bare scalar is no longer an
  expressible body — the transform routing follows the same rule, so a `Format` on
  such a field no longer replaces the body either. Nothing in any pack ever sent
  the bare form successfully, so no pack changed behaviour except the five tools
  below, which began working. Lists still unwrap: a list, unlike a scalar, is a
  document.

- **Two Gmail quota costs were pre-2026-05 figures.** Google republished its
  per-method table on 2026-05-01: `threads_get` costs 40 and `messages_modify`
  costs 5, not 10 and 10. `quota_cost` is metadata and gates nothing at
  runtime, so this changes no behaviour.

### Fixed

- **Naming a path on a recursive schema no longer takes half a minute.**
  `Tool.paths()` built every addressable path in the schema and then filtered to
  the level asked for. On a pack whose types reach themselves that is not a
  detail: Linear's filters put 56 of one tool's 77 generated models in a cycle,
  so `search_issues` has 2,271,553 addressable paths, and the eight that
  `paths("variables")` returns cost ten seconds of building the other 2,271,545
  and discarding them. `derived()` was worse, because `resolve_path` built the
  same list to look one selector up in it.

  | | before | after |
  |---|---:|---:|
  | `search_issues.paths()` | 10.4s | 0.00s |
  | `derived(drop={"variables.filter"})` | 34.9s | 0.00s |
  | `derived(drop={"filter"})` | 9.6s | 0.01s |
  | `documents_batch_update.derived(keep={...})` | — | 0.02s |

  Three changes, none of which alters which paths come back. `schema_paths` now
  takes `under` and `depth` and starts the walk there rather than filtering a
  whole-schema walk afterwards. `resolve_path` confirms a full dotted path by
  walking it, one lookup per segment, instead of searching a list for it. And a
  short name or a model class is resolved by first working out, on the model
  *graph* where each model appears once, which models can reach a match, then
  walking only those — pruning a branch that holds no match cannot lose one.

  The cycle guard stays per branch, deliberately. A model reached from two fields
  is addressable under both, and a guard that visited each model once would make
  the second unselectable. The path count is a large answer, not redundant work,
  so the fix is to stop asking for all of it.

  **Two behaviour changes.** `depth` now counts from `under` rather than from the
  root, so drilling into a deep field reaches its children instead of finding the
  internal depth ceiling already spent; this shows only below the eighth level.
  And an ambiguous selector is counted exactly up to 200 candidates and reported
  as "more than 200" beyond that, because on a cyclic schema the exact number was
  never going to arrive. Every schema in the packs that terminates is still
  counted exactly; the worst is the 19 fields named `index` in the Docs batch
  update.

- **`search_users` reported no matches however many it found.** It was built on
  `trim_user`, the projection for the single object `GET /user` returns. Run over
  the search envelope it found none of the keys it looks for and returned `{}` —
  with no error anywhere. Split into `trim_user` and `trim_users`, one per shape.
  Found by running the pack against the real API; nothing offline had put the two
  shapes together.

- **GitHub's search endpoints sent `order=desc` on every call.** A documented
  server-side default copied onto the field, so it went out even with no `sort`
  to order — a parameter nobody asked for on the pack's most-called read. It now
  defaults to `None` and the description says what GitHub does without it.

- **`repos_delete_file` offered a commit `date` GitHub has never accepted.**
  `PUT /contents/{path}` takes `name`, `email` and `date`; `DELETE` takes the
  first two. One model across both put a field in front of the model that the
  delete endpoint ignores, so the timestamp was silently dropped on every call.
  The two now share `CommitIdentity` and the write extends it. Found by reading
  the pack's own egress map against GitHub's OpenAPI description, which is now a
  test.

- **`Mode` now applies inside a `Dict[str, Model]`.** `create_llm_schema` walked
  nested models and lists of them and copied a dict of them across whole, so every
  `response_only` field under one was offered to the model. That is an egress hole
  rather than an ergonomic lapse: a withheld field is how a pack keeps something
  out of a model's context window. Notion's page `properties` is the shape that
  found it — a map of column name to value, a third of whose types the server
  computes and rejects on write. `egress_map` walks dicts for the same reason, so
  the printed map and the schema agree.

- **A model serializer survives onto the LLM view.** `create_model` drops
  validators and serializers alike, and `_carry_validators` put only the first
  back. The LLM view is the instance the runtime dumps, so a dropped serializer
  changes the bytes on the wire and nothing raises. It is what lets a field Python
  will not let you name reach the API under its own spelling: Notion's compound
  filter is `{"and": [...]}`, and `WireName` cannot reach it, since key conversion
  carries per-field markers at the top level of a body only.

- **Every OAuth pack's page says where the first grant comes from.** The signpost
  was rendered only for a server with a provider page of its own, so a pack
  without one showed a snippet reading a refresh token out of the environment and
  never said how it got there.

- **`Tool.derived()` — a projection of a tool, narrowed by whoever deploys it.**
  `Mode` is the pack author's lever, fixed when the pack is written. This is the
  other half: `keep`, `drop` and `pin` narrow a tool you did not declare and
  cannot edit.

  `keep` selects within the sibling group it names, so keeping three members of
  the Docs `Request` union drops the other 30 and leaves `document_id` alone.
  `drop` removes a path. `pin` removes a path from the view the model fills in and
  keeps it in the one the runtime executes, so the field is neither visible to the
  model nor reachable by it, and a pinned value is indistinguishable on the wire
  from one passed by hand.
  Selectors are dotted paths, unambiguous field names, or the model class a field
  is annotated with; `Tool.paths()` lists them.

  The tool underneath is unchanged — same URL, credentials, validators and
  `extra="forbid"` — so a projection can only ever remove, and an argument outside
  it raises `ToolValidationError` before a request is built. Naming nothing,
  naming several things, or dropping a field the API requires raises
  `DeclarationError` at declaration rather than at the first 400.

  Two things this is for, and the second is the reason it exists. Context:
  `documents_batch_update` is 8,874 tokens of schema before the model reads the
  task, and narrowing it to three edits is 1,942, or 78% smaller. Permission:
  Google's `documents` scope grants all 33 edits as one indivisible grant, with
  no scope for "may edit text, may not delete content". The union member is the
  capability, so pruning it is the only place that permission can be expressed.

  Both halves print in `egress_map()`, with a pinned field carrying its value,
  because a restriction a reviewer cannot read is not a control. See
  [docs/tools/projections.md](docs/tools/projections.md).

- **Google Sheets goes from 5 tools to 17 — every method the v4 reference
  documents.** The pack could read a range and append to one, but not update,
  clear, or address several at once. Added `spreadsheets_values_update`,
  `spreadsheets_values_clear`, `spreadsheets_values_batch_get`,
  `spreadsheets_values_batch_update` and `spreadsheets_values_batch_clear`;
  the three `values_batch_*_by_data_filter` tools; `spreadsheets_sheets_copy_to`
  and `spreadsheets_get_by_data_filter`; and both
  `spreadsheets.developerMetadata` methods, `spreadsheets_developer_metadata_get`
  and `spreadsheets_developer_metadata_search`.

  The `batchUpdate` `Request` union carries all 74 documented edits, each a
  oneof the schema enforces before the call, and the spreadsheet resource is
  modelled down to the Developer Preview comment types — `CommentThread`,
  `Post`, `CommentAnchor` — with every `Output only` field withheld from the
  model.

  `test_pack_ships_every_documented_endpoint` names the method list rather than
  counting it, so the next method Google adds fails the suite instead of
  passing it quietly.

- **Gmail goes from 9 tools to 23.** The pack could list message ids but not
  read one, save a draft but not find it again, create a label but not recolour
  it. Added `messages_get`; `drafts_get`, `drafts_list`, `drafts_update`,
  `drafts_delete` and `drafts_send`; `labels_get`, `labels_update`,
  `labels_patch` and `labels_delete`; `threads_modify`, `threads_trash`,
  `threads_untrash` and `threads_delete`.

  `messages_get` and `drafts_get` run trimming response handlers, as do the
  three thread writes, so a MIME tree reaches your model on none of them.
  `messages_get` accepts Gmail's full `format` enum: `raw` is parsed rather
  than handed back, and `minimal` returns no `bodyText` key rather than an
  empty one, because "the message is empty" and "you did not ask" are
  different facts.

  **`threads_delete` asks for a scope the rest of the pack does not.** Google
  covers every other Gmail endpoint here with `gmail.modify` and requires
  `https://mail.google.com/` for the delete that cannot be undone. It is
  declared on that tool, not on the pack, so `scopes_for` widens a consent
  screen only when you hand that tool out — drop `threads_delete` from your
  list and your users see `gmail.modify` and nothing more.

- **`partial_of(model, name=..., doc=...)`** derives a model with every
  top-level field optional: the body of a `PATCH`. One resource routinely
  serves create, update and patch and the operations disagree about what is
  mandatory, so the patch body is derived from the resource rather than copied
  out beside it. Descriptions, constraints and the `Path`/`Query`/`Body`/
  `Mode`/`Format` markers all come across, and so do validators, so partial
  does not mean unconstrained. Nested models are left alone. See
  `docs/reference/markers.md`.

### Changed

- **A lone `Body()` field carrying a scalar keeps its name.** Unwrapping promotes
  a nested structure's fields to the root of the request, which is right for a
  model — GitHub's `issues_create`, every Google pack — and meaningless for a
  scalar, which has no fields to promote. Taken literally it built a request no
  API accepts: a bare `"C0123"` as the whole JSON document, or, on a form-encoded
  API, a local `DeclarationError` before anything was sent. `unwraps_body` now
  decides this in one place, for both `call_api` and the transform routing.

  **Migration:** a tool of your own whose only body field is a scalar now sends
  `{"field": value}` where it sent `value`. A bare scalar is no longer an
  expressible body — the transform routing follows the same rule, so a `Format` on
  such a field no longer replaces the body either. Nothing in any pack ever sent
  the bare form successfully, so no pack changed behaviour except the five tools
  below, which began working. Lists still unwrap: a list, unlike a scalar, is a
  document.

- **Two Gmail quota costs were pre-2026-05 figures.** Google republished its
  per-method table on 2026-05-01: `threads_get` costs 40 and `messages_modify`
  costs 5, not 10 and 10. `quota_cost` is metadata and gates nothing at
  runtime, so this changes no behaviour.

### Fixed

- **A scheduled subscription cancellation could not be undone.** Stripe clears
  `cancel_at` with an empty string, which `subscriptions_update` did not accept,
  and `cancel_at_period_end=false` clears the flag rather than a timestamp — so
  an agent could schedule a cancellation and had no way to take it back. The
  update schema takes `""` now; create still refuses it, having nothing to
  clear. Stripe's reference documents the three sentinels and not this, so it is
  pinned by a test asserting the empty value reaches the wire.

- **`shopify.locations_list` offered a `reverse` argument it then dropped.**
  `LocationsVariables` inherits `ConnectionVariables`, so the model could ask for
  the reverse sort order, but the `Locations` document never declared
  `$reverse` — Shopify answered 200 with the list in its original order and
  nothing reported a problem. The same silent-success shape as a misspelled
  query parameter. The document declares it now, and a new test asserts, for
  every tool in the pack, that each variable the schema offers is one its
  document declares: the inheritance that caused this applies to every
  connection, so the instance was the wrong thing to pin.

  Found by validating the pack's GraphQL documents against the published
  schemas rather than by reading them.

- **Five tools could not send a request at all**, all for the same reason as the
  `Body()` change above: `slack.conversations_join` and
  `stripe.payment_methods_attach` take a *required* scalar, so every call failed;
  `stripe.payment_intents_cancel`, `stripe.invoices_finalize` and
  `github.actions_rerun_workflow` failed whenever their one optional scalar was
  given. Found by `harness/tests/live`, which calls every tool against the real
  API; a respx mock answers whatever it was told to and cannot see this.
- **`stripe.payment_intents_create` declared `confirm` and could not satisfy it.**
  Stripe offers an intent whatever payment methods the account has enabled, some
  of which redirect, so confirming needs a `return_url` or
  `automatic_payment_methods[allow_redirects]="never"` — and the schema had
  neither. Every confirmed payment was a 400, which left `payment_intents_capture`
  unreachable: nothing could put an intent into `requires_capture`. Both
  parameters are now declared.
- **`shopify.customer_update` could not name the customer.** It shared
  `CustomerInput` with create, which has no `id`, so the tool's own docstring
  asked for a field the schema forbade — and create's "email or phone required"
  validator applied to edits, so changing a note meant restating the contact
  details. `CustomerUpdateInput` now carries a required `id` and no such rule.
- **`shopify.inventory_adjust_quantities` was rejected at the GraphQL layer.**
  Shopify has required `changeFromQuantity` on every change since the version this
  pack pins, making the mutation a compare-and-set; without it the call never ran.
  Now declared and required, with `variant_inventory_level` named as where the
  expected quantity comes from.
- **`github.repos_create_or_update_file` returned `{}`.** It shared `trim_content`
  with the two read tools, but a PUT answers `{content, commit}` where none of the
  read's keys are at the top level, so the projection emptied it: a write
  indistinguishable from one that did nothing, and the new blob sha — which that
  tool's docstring tells the next write to send — was dropped with it.
- **A partly captured Stripe charge overstated what it took.** `amount` on a
  charge is the authorisation and does not move when less than all of it is
  captured, so a charge authorised at 5000 and captured at 4000 read 5000.
  `amount_captured` and `captured` now survive the trim.
- **Three descriptions said things the APIs do not do.** `final_capture` is
  *refused* on an intent without multi-capture rather than ignored, which an
  online card payment always is; Linear's workflow-state types omitted
  `duplicate` and `triage`; and Shopify's `@idempotent` key does not replay a
  first response — an identical retry is executed again and refused by the
  compare-and-set, which is what actually makes the retry safe.

- **A `PATCH` body that reuses its resource model can no longer ship
  unnoticed.** `test_a_patch_body_mandates_nothing` refuses a partial update
  whose body mandates a field, across every pack, with its mutation in
  `tests/test_conformance_is_not_vacuous.py`.
- **Gmail's raw representation returned undecoded headers.** A message read
  with `format=raw` came back with RFC 2047 encoded-words (`=?utf-8?b?...?=`)
  where the same message read as a payload came back decoded, so the two
  disagreed about one subject line. Filenames were affected too.
- **Gmail's `Color` now enforces the rule Google documents:** `textColor` and
  `backgroundColor` are both required to set a label's colour, or neither. A
  half-set colour was a 400 the model could not tell from a bad label id.
- **Six Sheets unions the reference calls `exactly one` accepted none.**
  `ChartSpec.chart`, `ChartData.type`, `ConditionValue.value`,
  `ConditionalFormatRule.rule`, `EmbeddedObjectPosition.location` and
  `PivotValue.value` were enforced as `at most one`, so the empty object Google
  answers 400 for passed validation — a ChartSpec carrying a title and no chart
  reached the API before anything objected.
- **Sheets' `ChartData` rejected the shape its own reference documents.** The
  `type` oneof holds `sourceRange` and `columnReference`; `groupRule` and
  `aggregateType` sit outside it and say how a data source chart buckets and
  aggregates whichever one it reads. All four were swept into one mutual
  exclusion, so a domain that grouped its source range failed validation
  locally — the failure a model cannot tell from the API refusing the call.
  The rule is now `exactly one of sourceRange, columnReference`, as documented.
- **Three Sheets response models raised on any use.**
  `charter.packs.gsheets.types.spreadsheets.responses` used `Annotated` and
  `Mode` without importing either, leaving `Response`,
  `BatchUpdateSpreadsheetResponse` and `AddTableResponse` with an unresolved
  forward reference: they imported, they exported, and they raised the moment
  anything asked for their schema. Nothing in the tool graph reaches them, so
  nothing failed. `test_every_schema_in_the_pack_builds` now asks every model
  in the pack for its JSON schema.
- **Four gaps in the Sheets spreadsheet resource, against the reference.**
  `Spreadsheet.comments` and `commentsViewMode`, `Sheet.commentAnchors` and the
  `CommentAnchor` model were absent; `Post` was missing five of its eleven
  fields and marked none of its eight `Output only` ones, so `postId`,
  `author` and `createTime` were offered to the model as writable.
  `DeveloperMetadataLocation` is a three-way union with no rule enforcing it.
- **A conformance check reported a marker doing its job.**
  `test_every_cross_field_rule_survives_into_the_llm_view` walked the wire
  schema through fields the LLM view withholds, so a rule reachable only
  through a `Mode("response_only")` field looked like a rule that had been
  dropped. It now skips those subtrees, with the exemption pinned from both
  sides in `tests/test_conformance_is_not_vacuous.py`.


- **Getting the grant, not just using one.** `OAuth2Flow` covers the two steps
  of the authorization-code grant that are protocol rather than product:
  `authorize()` builds the consent URL (RFC 6749 §4.1.1, PKCE on by default,
  S256 only) and `exchange()` trades the callback's code for a `TokenGrant`
  (§4.1.3). It is stateless between the two — `state` and the PKCE verifier are
  returned to you and taken back — so the callback route, the session and
  storage stay the host's. `OAuth2Client.from_grant()` seeds a client from a
  fresh grant, so the first tool call after connecting spends no refresh.
- **The silent Google failure, made loud.** `exchange()` defaults to
  `expect_refresh_token=True` and raises a `CredentialError` naming
  `access_type=offline` / `prompt=consent` when the response carries no refresh
  token — the failure that otherwise works for an hour and then dies.
  `OAuth2Server` grew `authorization_endpoint` (filled in by `discover()`) and
  `authorization_params`, which is the one field discovery can never know.
- **`scopes_for(tools)`** turns the `scopes` every tool is declared with into
  the consent request, deduped in first-seen order, so the consent screen stays
  in lockstep with the tool set. **`states_match()`** is the constant-time
  `state` compare for your callback. See `docs/auth/oauth-flow.md`.
- **Errors carry a link to the page that fixes them.** `CharterError` grew
  `docs`, a documentation slug, and `docs_url`, the rendered link that `str(exc)`
  appends. Twenty-five raise sites set one: the pack credential errors point at
  that pack's page, a rejected token points at that provider's setup page, and
  the OAuth failures point at the flow or the server declaration. A slug rather
  than a URL, so moving a page is one edit and `tests/test_error_docs.py` can
  resolve every link the library can print against the docs that ship with it.

  Not every error gets one. The rule is that a link is for a procedure a message
  could never contain, never for a fix it already states, so `"pass the header"`
  carries none. `ToolValidationError` and `APIError` take no `docs` argument at
  all: the first is written to go back to a model, which pays for the URL in
  context and cannot follow it, and the second is the upstream API's failure to
  explain rather than Charter's.
- **`DeclarationError`**, for a schema or pack declared in a shape the runtime
  cannot use: a field with no `Path()`/`Query()`/`Body()` marker, a `Pagination`
  naming half a style, an `Envelope` that could never detect a failure, a
  `Format` naming an unregistered transform. Fifteen sites that raised a bare
  `ValueError` now raise this, which is what lets them carry a `docs` link to
  the page explaining the mechanism. It subclasses both `CharterError` and
  `ValueError`, so `except ValueError` around a declaration keeps working and
  pydantic still converts the ones raised inside a validator.
- **A model never sees a link.** `ToolValidationError` strips any rendered
  documentation URL from its message and its per-field errors. pydantic quotes a
  validator's error text verbatim, so a link on a schema type the model fills in
  would otherwise reach the model inside a tool result. The guarantee is a
  property of the class rather than a rule each raise site has to remember, and
  it applies at `format_validation_error` too, which the LangChain adapter wires
  in directly without ever building a `ToolValidationError`.

- **`Pagination.max_items`**, for an API that serves fewer results than it
  counts. GitHub's search reports `total_count` in the tens of thousands and
  then refuses anything past the first 1,000 matches, so `has_more` stayed
  `True` right up to the wall and the documented walk ended by *raising* rather
  than finishing. `github.SEARCH_PAGINATION` declares the cap.
- **`Envelope.retry_after`**, a resolver that reads the wait out of a failing
  payload, for an API that reports a rate limit inside a `200`. Shopify's limit
  is a cost budget, not a request count: it prices each query, refuses one that
  will not fit with no header anywhere, and carries the cost, the balance and
  the refill rate in the same response. The pack computes the wait from those,
  so a throttled agent has something to back off on.
- **`trim_comments` and `trim_pull_files`** finish GitHub's response handlers.
  Measured on a hundred comments from a long cpython thread, the nested `user`
  object came to 119KB against 87KB for every word of every comment — the page
  drops from ~71,000 tokens to ~29,000 with nothing removed that anyone reads.
  `pulls_list_files` is the opposite case: 89% of it is `patch`, which is the
  diff and has to stay, so it saves 6% and the description now says to page
  through a large one.

- **Two search parameters GitHub documents and the pack omitted.**
  `search_issues` takes `advanced_search`, for `AND`/`OR` and nested queries, and
  `search_type` (`semantic` or `hybrid`), which went generally available in
  April 2026.

### Fixed

- **A truncated subscription reported itself as complete.** Stripe caps a
  subscription's nested `items` at 20 and says so in `items.has_more`, which the
  projection dropped — so an agent totalling a subscription read a short list as
  the whole one. Confirmed live with 25 items: 20 came back, flagged, and the
  flag was gone. `trim_subscriptions` now carries `items_has_more` when the list
  is short.
- **A declined payment said that it failed, never why.** `last_payment_error`
  was not projected onto a PaymentIntent, so an agent saw
  `status: "requires_payment_method"` and nothing else — unable to tell a
  retryable decline from a hard one, or to explain either. It is projected now:
  `code`, `decline_code`, `advice_code`, `message` and `doc_url`, without the
  nested payment method and charge that the intent already carries.
- **`ui_mode: "form"` escaped the Checkout validator.** `_IN_PAGE_UI_MODES`
  listed `embedded_page` and `elements` only, though `form` behaves identically
  — live Stripe answers 400 for `success_url` and `cancel_url` alike. The same
  mistake was caught locally for two modes and cost a round trip on the third,
  in front of a waiting customer.
- **Five deprecated fields, still resolving, on their way out.** Linear's
  `Team.private` (now `visibility`) and `Project.state` (now `status`); Shopify's
  `Customer.email`, `Customer.phone` and `ShopPlan.displayName`. Checked against
  Linear's live introspection and Shopify's published 2026-07 schema — a mocked
  suite cannot see a field that still works today going away tomorrow. Shopify's
  replacements wrap a scalar in an object, so the flattening that already existed
  for `MoneyBag` was generalised (`flatten_money` is now `flatten_wrappers`)
  rather than duplicated: `email` and `phone` come back exactly as before.
- **Two Shopify behaviours documented rather than fixed**, because they are the
  API's and not something the runtime can validate. An unrecognised search
  qualifier is *ignored* rather than rejected, so a typo like `vendorr:` returns
  the whole unfiltered set; and the search index is eventually consistent, so a
  record created moments ago is fetchable by id but invisible to a query for a
  few seconds — which is how an agent that confirms a write by searching for it
  creates duplicates. Both are on the `query` fields the model reads.

- **`DeclarationError` reaches you from a call, not only from a build.** A tool
  whose schema has an unmarked field builds without complaint and raises on the
  first `ainvoke`, because nothing inspects the markers until a request is
  assembled. The reference said the opposite, as advice about where to put a
  `try`. `except CharterError` around the call catches it; guarding only the
  declaration does not.
- **An unmarked field named a class you never wrote.** The message reported the
  generated `SendEmail_LLM` variant, so the fix was to go looking for a class
  that exists nowhere in your code. It names your own schema now.

- **Every error survives a pickle.** `Exception`'s default pickling replays
  `cls(*args)`, so `APIError` — whose `status_code` is a required keyword — could
  not cross a process boundary at all: a host running tools in a process pool or
  a task queue got a `TypeError` instead of its error. `CharterError.__reduce__`
  rebuilds from the instance dict, which also carries `provider`, `retry_after`
  and `docs` across intact. Present since 0.1.0.

- **Nine defects in the GitHub, Stripe and Shopify packs, found by reading the
  packs against the APIs' own current documentation.** Every one of them passed
  the test suite, because a test can check a pack against itself and not against
  the API it models.

  - **`repos_list_for_authenticated_user` was a guaranteed 422.** GitHub answers
    422 when `type` arrives beside `visibility` or `affiliation`, and the schema
    carried all three of GitHub's documented defaults — so the no-argument call,
    which is the one an agent makes first, sent all three. A documented default
    describes what the server applies to a request that *omits* the parameter; a
    default you send is not a default. All three now default to `None`, and the
    combination GitHub rejects is refused locally.
  - **`repos_get_content` handed the model mojibake for a binary file.** Base64
    was decoded with `errors="replace"`, so a PNG came back as replacement
    characters that read as content, and the "not decodable as text" branch was
    unreachable. It decodes strictly now, and the two cases where there is no
    text to hand over — a binary file, and a file over 1MB, which GitHub answers
    with `encoding: "none"` and an empty string — say which happened and keep the
    `download_url`.
  - **Search walks ran past GitHub's 1,000-result window.** `total_count` reports
    the true size of the match set while GitHub serves only the first 1,000, so a
    page-number walk kept asking and took a 422. `page × per_page` is checked
    against the window locally.
  - **`customers_update` offered Stripe a parameter Stripe rejects.** The update
    schema derived from create, which put create-only `payment_method` on it.
    Both now derive from a shared `CustomerFields`.
  - **A trimmed Stripe subscription had no billing period.** Stripe moved
    `current_period_start` and `current_period_end` off the Subscription object
    onto its items; the handler kept projecting them from the subscription, found
    nothing, and dropped both — an active subscription with no renewal date and
    nothing saying one was missing. `trim_subscriptions` reads them from the
    items, lifting the period when the items agree and reporting it per item when
    they do not.
  - **Three closed `Literal`s in the Shopify pack were subsets.** `OrderSortKeys`
    modelled 6 of Shopify's 14, and all three sort-key enums omitted `RELEVANCE`.
    A closed enum missing a value the API accepts rejects a valid call, and the
    model cannot tell that from the API refusing it.

### Changed

- **An argument the schema does not declare is now refused, not dropped.**
  *(Breaking.)* Generated LLM schemas set `extra="forbid"`, and
  `to_json_schema()` carries `additionalProperties: false` on the root and every
  nested object. Pydantic's default was to ignore unknown keys, which at a tool
  boundary produces the worst outcome available: not an error, a wrong answer
  that nothing marks as wrong. Verified against the live Stripe API —
  `customers_list(limit=2, created={"gt": ...})` sent `limit=2`, returned two
  arbitrary customers, and said nothing about the filter it had discarded; the
  agent then reasons over rows it believes were filtered. A plausible typo
  (`emails` for `email`) did the same, and is the likelier mistake.

  **Migration:** if you pass a key `ainvoke` does not declare and rely on it
  being ignored, that call now raises `ToolValidationError`. Remove the key, or
  declare it on the schema if it belonged on the wire. Per-call `headers` are
  unaffected — keyword-only, never part of the schema. For a model, the raise is
  the point: the message names the field and is written for the existing retry
  loop.

  Two consequences worth knowing. The three accepted spellings (camelCase,
  PascalCase, snake_case) are now *declared* aliases rather than ones
  `populate_by_name` tolerated, because with extras refused a merely-tolerated
  spelling would become an error; they are normalised through snake_case first,
  so a camelCase-authored schema keeps a working PascalCase form. And a pack's
  own filter types now reject what they never modelled — Linear's `IssueFilter`
  refuses `and`/`or` composition outright instead of dropping it and returning
  an unfiltered page.
- **A path parameter can no longer rewrite the request URL.** *(Breaking, for
  input that was already wrong.)* Path values are percent-encoded before
  interpolation; `..` raises `ToolValidationError`; `/` is encoded unless the
  field declares `Path(allow_slash=True)`. Reproduced against the live GitHub
  API: `repos_get_content` with `path="../../other/contents/README.md"` returned
  **200 and a different repository's file**, and `"../../../../user"` left the
  repository API altogether. Stripe escaped the same way, and `?` and `#` were
  live too, so a schema field could append query parameters of its own. These
  values come from a model that has usually just read untrusted text.

  **Migration:** GitHub's file path is the one field that legitimately spans
  segments and declares `allow_slash=True`. Characters legal inside a segment
  stay literal — a Calendar id is an email, a Sheets range is `Sheet1!A1:B2` —
  so no request that was already correct changes.
- **`APIError.retry_after` reads `X-RateLimit-Reset` when there is no
  `Retry-After`.** Only when `X-RateLimit-Remaining` is `0`, so an ordinary
  response carrying quota headers is not reported as a wait. GitHub needs it: it
  sends no `Retry-After` and answers **403**, not 429, so `retry_after` was
  always `None` and every backoff loop built on it spun. Confirmed by tripping
  the search limit — `retry_after` 23.

- **Stripe requests pin `Stripe-Version`.** An unpinned request does not use the
  latest version, it uses whichever version the *account* defaults to — set in a
  dashboard this library cannot see — so the same code answered differently for
  two callers and a schema written against one of them was right by luck. This is
  what let the subscription period defect above go unnoticed.
  `stripe.API_VERSION` is `2026-08-26.dahlia`; it is sent as `static_headers` and
  never appears in a tool's LLM schema.
- **Four rules Stripe documents are now enforced before the call.** A refund
  names exactly one of `charge` or `payment_intent`; a Checkout Session in
  `payment` or `subscription` mode needs `line_items`; one in `setup` mode needs
  `currency`; and `success_url`/`cancel_url` are refused when `ui_mode` is
  `embedded_page` or `elements`. Each was a documented 400, and a Checkout
  Session is usually created with a customer waiting on it. Rules that depend on
  parameters these schemas do not model are left to Stripe and named in the field
  descriptions instead.
- **`orders_list` names Shopify's 60-day window.** Shopify serves an app holding
  `read_orders` only the last 60 days of a store's orders, and truncates the rest
  silently — no error, no marker on the page. It is now in the tool description
  the model reads, on the `query` field, and in the pack's known limits.

- **Breaking: credentials and OAuth moved to `charter.auth`.** Eighteen names
  left the root namespace, which they were the largest cluster of, and now have
  one import path each: `Credentials`, `CredentialProvider`,
  `StaticTokenProvider`, `EnvTokenProvider`, `CallbackProvider`,
  `SubjectProvider`, `current_subject`, `use_subject`, `OAuth2Server`,
  `OAuth2Client`, `OAuth2Flow`, `AuthorizationRequest`, `TokenGrant`, `Grant`,
  `TokenEndpointAuthMethod`, `OnRefresh`, `states_match`, `scopes_for`.

  Migration is one line per import site:

  ```python
  from charter import OAuth2Client, EnvTokenProvider     # before
  from charter.auth import OAuth2Client, EnvTokenProvider  # after
  ```

  Nothing is re-exported from `charter` and there is no deprecation alias: a
  second import path for the same object is a thing to keep in sync forever, and
  packs generated from the skill file would split between the two. The five
  errors stay in `charter`, `CredentialError` among them, so
  `except (APIError, CredentialError)` still comes from one namespace.

  The `charter.oauth` module is gone as an import path. Its contents live in
  `charter.auth.oauth` and `charter.auth.flow`, which are where the code lives
  rather than what you import: import from `charter.auth`.

## [0.1.0] — 2026-08-30

First release.

### Added

- **The contract layer.** `Tool` binds a Pydantic schema to an HTTP endpoint and
  executes it locally. `Path`/`Query`/`Body` say where a field goes, `Format`
  says how it is encoded, `Mode` says who may see it, `Case` says how its key is
  spelled on the wire — and the runtime resolves all of it deterministically, so
  a model supplies meaning and never assembles a request.
- **Egress control.** A field marked `Mode("response_only")` is absent from the
  type the model is handed, so it cannot reach a context window at all.
  `egress_map()` prints the boundary from the same declarations the runtime
  executes, as JSON you can snapshot in CI.
- **Envelopes.** APIs that report failure inside an HTTP 200 — Slack's
  `{"ok": false}`, every GraphQL `errors` array, a mutation's `userErrors` —
  declared once per API and enforced on every call, including calls by tools
  added later.
- **Eleven packs, 86 tools.** Gmail, Google Calendar, Google Sheets, Google Docs,
  Slack, GitHub, Stripe, Linear, Shopify, Firecrawl, and AccuWeather.
- **OAuth 2.0 without a vendor SDK.** `OAuth2Server` declares a token endpoint in
  RFC 8414's vocabulary; `OAuth2Server.discover()` reads it from any server that
  publishes metadata. `OAuth2Client` refreshes the `refresh_token` and
  `client_credentials` grants over a plain form POST, caching the access token
  with single-flight refresh. `SubjectProvider` and `use_subject` resolve
  credentials per end user, below every framework adapter.
- **Measurement.** Every call produces a `ToolCall` — outcome, sizes on both
  sides of the boundary, and timings split by owner, so `overhead_ms` answers
  "is this layer in my way?". `CallCollector` and `format_call_summary` for a run
  summary; `to_dict()` uses OpenTelemetry attribute names. Local only: no default
  sink, no history.
- **Adapters** for LangChain, the OpenAI tools interface, and MCP —
  `python -m charter.mcp --pack gmail` serves any pack to any MCP client.
- **A conformance suite** that runs over every pack at once and knows nothing
  about any particular API, plus `tests/test_conformance_is_not_vacuous.py`,
  which breaks each property on purpose and asserts the check fires.

### Notes

- The core depends on `pydantic` and `httpx`, and nothing else. Adapters live
  behind extras.
- The library makes no network calls except the API calls you define, and
  `OAuth2Server.discover()` when you call it by name.
- Named limits, deliberately: no multipart bodies, no request signing, no
  pagination loops, no multi-call orchestration, no streaming. See *What this
  can't express* in the README.

[Unreleased]: https://github.com/r28ai/charter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/r28ai/charter/releases/tag/v0.1.0
