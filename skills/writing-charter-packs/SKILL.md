---
name: writing-charter-packs
description: Build a Charter pack from an API's documentation — model every field, mark the HTTP locations, set the casing, pick the transforms, and test it offline.
---

# Writing a Charter pack

A pack is a set of `Tool`s for one API, plus the schemas they are built from. The
schema *is* the integration: if it is right, there is no glue code left to write.

Work through this checklist in order. Do not skip the crawl.

## 1. Crawl every linked page

**Look for a machine-readable source first.** Most APIs publish one — an OpenAPI
document, a GraphQL schema, a discovery document — and it is complete where the prose
reference is a hand-written relay that drops things. Which source to trust for which
vendor, and the trap in each, is
[`FINDING-THE-SOURCE.md`](FINDING-THE-SOURCE.md). Read it before you start crawling;
it is the difference between an afternoon and a week.

Then close the graph. One endpoint routinely spans ten documentation pages: the request
body references a resource; the resource references an enum; the enum has values
documented somewhere else entirely. Follow every link.

Miss one enum value and the model will eventually emit it and get a 400 you cannot
reproduce.

Record the source you built from in the pack's module docstring. It is what makes the
pack checkable against its provider later.

## 2. Model every field, exactly

Write the schema to match the documentation, not to be convenient:

- Keep the API's field names, converted to snake_case. The runtime converts back.
- Use `Literal[...]` for enums, with **every** documented value — not the handful
  the endpoint is usually called with. A closed `Literal` missing a value the API
  accepts rejects a valid call, and the model cannot tell that from the API
  refusing it, so it has no way to recover. Where the API says the set may grow,
  use `str`: a closed `Literal` starts rejecting valid values the day the API
  adds one.
- **A documented default is what the server applies to a request that omits the
  parameter. It is not always a value to put on the field.** Copy it onto the
  schema and it goes out on every call, which is a different request from the one
  the documentation describes — and where the API documents parameters that are
  mutually exclusive, copying each one's default sends the combination it
  rejects. GitHub's `/user/repos` documents defaults for `visibility`,
  `affiliation` and `type`, and answers 422 when `type` arrives beside either of
  the others; the pack carried all three, so the no-argument call — the first one
  an agent makes — was a guaranteed 422. Default to `None`, say what the server
  does when the field is absent in the description, and write the exclusion as a
  validator.
- **Model the whole union, however wide it is. Do not trim it to keep the schema
  small.** Google Docs' `batchUpdate` carries 33 kinds of edit and Sheets' carries
  74, each one a member of a oneof, and a pack that ships the popular six is a
  pack that silently cannot do the other sixty-eight. Completeness is safe here
  because narrowing happens at deployment, not in the pack: whoever uses the tool
  writes `tool.derived(name=..., keep={...})` and gets the members their agent
  needs. `gsheets.spreadsheets_batch_update` is 52,168 tokens of schema and a
  four-member projection of it is 14,027, so the cost of being complete is one
  line in the caller's own code. Say the size in the pack docstring rather than
  hiding it, the way `gdocs` does.
- Use `Optional[X] = None` for anything not required. **A field with no default is
  required in Pydantic v2** — an `Annotated[Optional[str], Query()]` with no `= None`
  forces the model to supply it on every call. This is the single most common bug in
  a hand-written pack.
- **When one resource serves several operations, they disagree about what is
  required, and the resource is not the place to settle it.** Gmail's `Label`
  needs a `name` to be created or replaced and needs nothing to be patched;
  `PUT` replaces, `PATCH` merges, and that is true of every REST API, not just
  this one. Reusing the resource model on the patch endpoint makes `name`
  required on the one operation whose purpose is not having to send it, so
  recolouring a label means reading it first just to echo the name back.
  Derive the patch body instead of writing a second model beside the first:

  ```python
  from charter import partial_of

  PatchLabelRequest = partial_of(Label, name="PatchLabelRequest")
  ```

  Descriptions, constraints, markers and validators all come across, so the
  descriptions keep one home. Writing it out by hand copies them into a second
  place that nothing keeps in sync: the field documentation drifts the day the
  vendor rewords one of them, and no check fires. `partial_of` relaxes only the
  fields the model declares, never a nested one. Step 12's
  `test_a_patch_body_mandates_nothing` refuses a `PATCH` whose body mandates
  anything, however you built it.

  The harder version of the same shape is a field that one operation *requires*
  and another cannot see at all: `drafts.send` takes a `Draft` and reads only
  its `id`, which `drafts.create` must never be offered. Requiredness and
  visibility are different axes, `Mode` only moves the second, and one
  occurrence is not a pattern. Write that body out by hand and say why in its
  docstring.
- Carry the documented constraints onto the field — `ge`/`le` for numeric ranges,
  `min_length`/`max_length` for strings and lists, `pattern` for documented formats.
  Each one turns a round trip and a 400 into a local validation error.
- Give every nested object its own model. `Dict[str, Any]` for a structure the docs
  describe throws away the field names, the types and the descriptions, which are
  the only things the model has to go on when filling it in.
- Put the documentation's own description on every field, in its words rather than
  a summary of them. It is the model's only guide, and it is free.
- **Anything you want to tell the model that the docs do not say is a `Gloss`, not
  an edit to the description.** A description that is the API's own text can be
  diffed against the reference page; once a sentence of your own is mixed into
  it, the next person to regenerate the field deletes your sentence without
  seeing it go. `Gloss("Cents, not dollars: $15.00 is 1500.")` is appended to the
  description in `llm_schema()` and absent from the wire schema. Reach for a
  constraint first: `ge`/`le`/`pattern` and `ConflictsWith` are checked, and a
  gloss is only read.
- Include the API reference URL in each model's docstring.

**"This parameter cannot accompany that one" is a marker, not a validator.**
Written as a validator the rule needs a list of the fields it covers, which is a
second place to keep in step: add a parameter and the list forgets it, delete one
and the list keeps naming a field that is gone. Declare it on the field and the
runtime builds the check, reporting every conflict in one message and naming each
field the way the API does:

```python
i_cal_uid: Annotated[
    Optional[str], Field(None), Query(), WireName("iCalUID"),
    ConflictsWith("sync_token", reason="Drop syncToken to run a fresh query."),
]
```

Google Calendar's `events.list` refuses `syncToken` beside eight other
parameters, and `calendarList.list` beside two. Both said so in prose and one of
them said it twice; each field says it once now.

Other rules that span fields — "exactly one of `a` or `b`", "`b` is required when
`a` is set", "this flag may be set but not to False" — belong in a
`@model_validator(mode="after")`, or a `@field_validator` where
one field can be judged alone. Write them: step 12 checks that they survive into
`llm_schema()`, because a rule enforced only against the wire schema never reaches
the input that actually needs checking.

## 3. Mark the HTTP location of every field

```python
user_id: Annotated[str, Path()]          # -> interpolated into url_template
max_results: Annotated[Optional[int], Query()] = None
body: Annotated[RequestBody, Body()]     # -> the JSON body
```

An unmarked field defaults to `Body()` and warns. Mark them all explicitly.

For the body, pick the shape the API actually wants:

- one `Body()` field — its contents are unwrapped to the root of the JSON
- one `Body(envelop=True)` field — its *name* is kept as the root key
- several `Body()` fields — merged into one object under their names

## 4. Declare the API's constants

Before writing tools, settle the facts that are true of every call:

- **Body format.** JSON is the default; set `body_format="form"` for Stripe,
  Twilio, or any OAuth2 token endpoint.
- **Constants.** An `api-version` query parameter, a version header, a GraphQL
  query document — these go in `static_query` / `static_headers` / `static_body`,
  never in the schema, where the model would see them and could change them.
  `static_body` is per tool; the other two are per factory.
- **The host.** Usually a constant. If it depends on the installation — a Shopify
  store, a Zendesk subdomain — pass a *callable* `base_url`. Never a schema field:
  that would let the model choose which server to talk to.
- **Pagination.** Declare it on the *list* endpoints, not on the factory, unless
  every tool in the pack pages — otherwise you label every "get one" endpoint with
  a marker it does not have. Two styles:
  `Pagination(cursor_field=..., cursor_param=...)` when the API hands back a
  token, and `Pagination(page_param=..., per_page_param=...)` when it does not and
  you count pages. `cursor_param` must name a real schema field, and may be dotted
  (`variables.after`) to reach into a nested argument.
  **Declare `more_field` whenever the API offers one** — the fallback is "a
  non-empty cursor means another page", which loops forever against any API that
  returns a cursor on its last page.

See [the wire contract](../../docs/tools/wire-contract.md).

## 5. Set the casing per the cascade

Defaults are `body_case="camel"`, `query_case="snake"`, `path_case="snake"`. Set
them on the factory for the whole API; override per endpoint or per field only where
the API is genuinely inconsistent. See [key-case-cascade.md](../../docs/tools/key-case-cascade.md).

**Never reach for `alias` to fix a casing problem.** It does not even work: the
runtime dumps by field name and converts the keys afterwards, so an `alias` set for
casing never reaches the wire. What it does reach is input validation, where it
replaces the camelCase and PascalCase spellings Charter otherwise accepts with the
single one you hardcoded.

`alias` has one legitimate use here — a field whose name Python or Pydantic has
already taken, where no other spelling is available:

```python
self_: Annotated[Optional[bool], Field(None, alias="self", description="...")]
```

**Use `WireName` where no convention reaches the documented name.** The
conversion capitalises each component, so `i_cal_uid` goes out as `iCalUid` where
Google Calendar documents `iCalUID` — and the same shape produces `htmlUrl` for
`htmlURL`, `ipAddress` for `IPAddress`. `Case` cannot help: it offers whole-word
conventions, and this is a word the convention gets wrong.

```python
i_cal_uid: Annotated[Optional[str], Field(None), Query(), WireName("iCalUID")]
```

Reach for it when an acronym sits inside a field name, and check the API's
reference rather than guessing which way it spells one — `eventId` and
`fileUrl` are camelCase in Google's own docs, so most acronyms need nothing.
This is the failure the wire-bytes assertion in step 11 exists to catch: the
misspelled filter was dropped, the unfiltered list came back, and the call
answered 200 for as long as the pack existed.

`type_`, `schema_`, `from_` and `class_` are the others you will meet; the gcalendar
and firecrawl packs carry several.

**Check the query casing separately from the body casing, and check it on the
wire.** They are different defaults and they are often the same convention, which
is exactly why this gets missed. Google's query parameters are camelCase like its
bodies; leaving `query_case` at its snake default sent `max_results` instead of
`maxResults` in three shipped packs here for weeks. Nothing failed — Google
ignores query parameters it does not recognise, so every call succeeded and every
filter was silently dropped. Assert the parameter names your API documents against
a `respx` route; do not read the schema and assume.

## 6. Mark `Mode("response_only")` on server-set fields

IDs, timestamps, computed counts, `etag`, anything the API returns and never
accepts. These are noise in the model's context and a source of confident, wrong
tool calls. Mark the parent and the whole subtree is hidden.

Use `Mode("disabled")` for deprecated fields, and a custom mode when one resource
serves two operations with different field sets.

This is also the pack's egress policy, not just its ergonomics: a withheld field
cannot reach a model's context window. When you think you are done, print the map
and read it as an auditor would — anything visible that should not be is a bug:

```python
from charter import format_egress_map
print(format_egress_map(TOOLS))
```

## 7. Pick `Format` transforms for wire formats

Any field whose documented type is an encoding rather than a meaning:

- base64 / base64url / `bytes` fields
- RFC822 message bodies -> `Format("rfc822_base64")`
- protobuf `Value`/`Struct`/`ListValue` -> `Format("proto_json")`
- `FieldMask` -> `Format("field_mask")`

If the API wants an encoding Charter has no transform for, register one — see
[transforms.md](../../docs/tools/transforms.md).

**Pin the version, and check what "unpinned" actually means.** Where an API
dates its releases, send the version you wrote against — `static_headers` for a
header, the path for Shopify, `static_query` for a query parameter. The
alternative is rarely "the latest version": Stripe serves each *account* its own
default, set in a dashboard your library cannot see, so an unpinned pack answers
differently for two callers and the schema you tested is right by luck. That is
how a handler ends up reading fields the API moved: Stripe took
`current_period_start` off the Subscription object and put it on the items, and
nothing failed — the projection just returned a subscription with no billing
period.

**A validation failure is not evidence that the type is wrong.** When the model
sends a primitive where the schema wants a structured type, the fix is a
`model_validator(mode="before")` that coerces the input, or a `Format` that handles
the wire conversion. It is never widening the annotation. `List[List[Value]]`
relaxed to `List[List[Any]]` makes the error go away and takes the validation, the
descriptions and the transform's hook with it.

## 8. Check how the API reports failure

Read the error section of the docs before writing any tool. If failures come back
with a 4xx, there is nothing to do. If the API answers `200 OK` and puts the
failure in the body — Slack's `{"ok": false}`, GraphQL's `errors` array,
`{"status": "error"}` — declare an `Envelope` on the factory:

```python
factory = oauth_tool_factory(
    ...,
    envelope=Envelope(ok_field="ok", error_field="error",
                      credential_errors={"invalid_auth", "missing_scope"}),
)
```

Getting this wrong is the worst failure mode in a pack: the model is told the
call succeeded when it did not. See [envelopes.md](../../docs/tools/envelopes.md).

**Look for failure in more than one place.** GraphQL's `errors` array carries
problems with the *document* — a syntax error, an unknown field. A mutation the
server understood and then declined comes back HTTP 200, with no `errors`, and the
refusal inside the payload: Linear's `success: false`, Shopify's `userErrors`.
Both other signals say the write happened.

Declare it; do not write it. Every field name on an `Envelope` is a path, and `*`
stands for whichever operation the tool called:

```python
Envelope(errors_field=("errors", "data.*.userErrors"))
```

One line on the factory covers every mutation in the pack, including the one you
add next year. Putting the same check in each mutation's `response_handler` looks
equivalent and is not: it is opt-in per tool, so the first tool added without it
reports a failed write as a success. That is the bug this whole layer exists to
make unwritable — see the `test_a_mutation_added_without_ceremony_is_still_guarded`
tests in the Linear and Shopify packs.

## 9. Add a response handler if the raw response is noisy

If a typical response carries more than roughly 2KB of envelope for the part that
matters — MIME trees, base64 attachment bodies, repeated metadata — write an async
`response_handler` that returns what the model should actually see.

**Then ask what the handler does with a response that is not the happy one.** A
projection drops what it cannot find, which is the right default and also the way
a handler goes quietly wrong: the model gets a well-formed object with a field
missing and nothing saying it was expected. Two cases are worth handling by name
every time.

*A decode that degrades instead of failing.* `decode_base64url` defaults to
`errors="replace"`, so a binary payload comes back as replacement characters that
read as content. Pass `errors="strict"` and handle the failure, or you have
handed the model something that looks like the file and is not.

*A placeholder where the content should be.* APIs answer "too big to inline" with
a shape rather than an error — GitHub sends `encoding: "none"` and an empty
string for a file over 1MB. Say which case it was and keep whichever URL or id
the caller can still act on.

Handlers must use stdlib + pydantic + `charter.*` only. No new dependencies —
`charter.decode_base64url` and `charter.html_to_text` cover the two decodings that
come up most, so do not write your own.

## 10. Wire up the pack module

```python
_credentials = DeferredCredentialProvider("mypack", env_var="MYPACK_TOKEN")

def configure(credential_provider): _credentials.configure(credential_provider)

_factory = oauth_tool_factory(base_url=..., provider=..., pack="mypack", credential_provider=_credentials)

my_tool = _factory(name=..., args_schema=..., method=..., url_template=..., description=..., action_label=...)

TOOLS = [my_tool, ...]
```

`pack` is the namespace your tools are qualified under when someone assembles
them beside another pack: `my_tool` becomes `mypack__my_tool`. Two APIs really
do declare the same tool name — `products_list` exists in both Stripe and
Shopify — and without a pack the two are indistinguishable, so one shadows the
other. It is a separate fact from the two fields beside it: `provider` is *which
credential* (Gmail, Calendar, Sheets and Docs all authenticate as `google`), and
`base_url` is *which host*. See [Tool names across packs](../../docs/tools/naming.md).

Name tools and schemas after the API's own names rather than an abstraction over
them: `users.messages.send` becomes the tool `messages_send` and the schema
`MessagesSendRequest`. Where the docs suggest no pattern, use `<resource>_<action>`
in snake_case and `<Resource><Action>Request` in PascalCase. The names are half of
what the model reads, and a pack that renames its endpoints cannot be checked
against the documentation it came from.

Give every tool a `description` (for the model) and an `action_label` (a short
user-facing phrase, for approval UIs). Tools are built at import so `TOOLS` is
importable without credentials.

## 11. Test it offline

Per pack, at minimum:

- every tool's `llm_schema()` builds and `to_json_schema()` is well-formed
- one GET and one POST against `respx`, asserting the actual bytes on the wire
- every `Format` field round-trips — decode the request body and check it
- `Mode("response_only")` fields are absent from `llm_schema()`
- the egress map reports nothing visible that the API does not accept
- an unconfigured pack raises `CredentialError` without making a request
- if the API returns 200 on failure, a failed body raises rather than returning
- **the query parameter names on the wire** are the ones the API documents
- every cross-field rule you wrote is enforced against `llm_schema()`, not just
  against the wire schema — that is the input that actually needs checking
- **the no-argument call.** Invoke every tool with only its required arguments
  and read the URL and body that come out. Everything the schema defaults into
  the request is on that line, which is where a default copied from the
  documentation shows itself as a parameter you did not mean to send
- each closed `Literal` holds the API's full enum, asserted against the values
  rather than against itself
- the response handler's unhappy paths: an empty page, a payload that fails to
  decode, a field the API has moved
- **a `PATCH` body that mandates nothing.** Assert the required list of the body
  model in `llm_schema()` is empty, and that the `PUT` beside it still requires
  what the API documents
- if list endpoints page, a two-page walk terminates

**Run the pack's tests before shipping.**

## 12. Let the conformance suite check the rest

`tests/test_conformance.py` runs over every pack at once and checks the
properties no pack should have to remember: that a pagination names fields the
schema accepts, that its walk both advances and terminates, that no response
handler decides whether a call failed, that every cross-field rule survives into
`llm_schema()`, that no `Optional` field is secretly required, that a `PATCH`
body mandates nothing, and that a constant is never also a tool argument.

A new pack is picked up automatically — add it to `PACK_NAMES`. Most of these
checks exist because the property was violated in a shipped pack and nothing
raised, so if one fails, read it as a report rather than a formality.

`tests/test_conformance_is_not_vacuous.py` breaks each property on purpose and
asserts the check catches it. If you add a check, add its mutation too: a check
that compares a declaration to itself passes forever and guards nothing.
