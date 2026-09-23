# AGENTS.md — charter-harness

Instructions for a coding agent working in `harness/`.

The harness runs against **real accounts over real API calls**. There are no mocks
and no recorded fixtures. Every scenario seeds live state, lets an arm act on it,
reads the result back, and tears the state down.

That means a run mutates accounts that belong to whoever configured it. Read the
guard section before running anything.

## Check the wiring before a run

`registry.all_scenarios(variants=True)` reports how many scenario instances are
runnable against the providers currently configured. Confirm it yourself rather
than trusting this file:

```bash
cd harness && .venv/bin/python scripts/check_auth.py
```

It makes one cheap call per provider and exits non-zero if any fail. It creates
nothing that it does not also delete. A green line per provider is the readiness
signal.

A provider whose variables are absent is dropped rather than failing loudly:
`Settings.available()` simply skips it, so a missing credential shows up as a
missing provider, not as an auth error. `settings.require(...)` names the exact
variables to set.

## Where the credentials go

**`harness/.env`** (gitignored). Not the package's `.env` at the repo root.

Both files can exist and both hold provider secrets, which is the trap. They use
different names for the same things. The harness reads only its own file, via
`settings.default_env_file()`, overridable with `CHARTER_HARNESS_ENV`.

| package `.env` (not read by the harness) | `harness/.env` (what the harness reads) |
| --- | --- |
| `STRIPE_TEST_SK` | `STRIPE_API_KEY` |
| `GITHUB_API_KEY` | `GITHUB_TOKEN` |
| `SHOPIFY_STORE_DOMAIN` | `SHOPIFY_SHOP` |

A value pasted into the wrong file fails as a missing provider, not as an auth
error.

`.env.example` lists every variable. Two of its comments are out of date: the
Slack scope list is missing `groups:history`, `channels:join` and
`channels:manage`, and `GOOGLE_REDIRECT_URI` defaults to port 8765 while the
script that mints the token listens on the port your OAuth client has registered.

The Slack app itself is also short two scopes the pack covers: `reactions:read`
(for `reactions_get`) and `im:write` (for `conversations_open`). The live suite
skips those two tools until they are granted, naming them — reinstall the app
after adding them, since a bot token does not gain a scope without it.

## The accounts, and what the harness does to them

Use accounts you are willing to have mutated. Do not point this at a mailbox or a
workspace that matters.

| Provider | What it needs | What the harness does |
| --- | --- | --- |
| Google (gmail, gcalendar, gsheets, gdocs, gdrive) | One OAuth consent covering all five scopes | Reads mail, creates and deletes labels, drafts, events, sheets, docs and Drive files. **Never sends email.** |
| GitHub | A token with Issues, Contents and Pull requests read/write | Creates issues, branches and pull requests in a sandbox repository only |
| Stripe | A **test-mode** key | Anything. `settings.load()` refuses a key that is not `sk_test_`/`rk_test_` |
| Linear | A throwaway workspace and a team key | Anything |
| Shopify | A development store | Anything. Use a store that exists only for this |
| Slack | A workspace and a channel created for this | Posts, edits, deletes and reacts in that one channel |
| Firecrawl | An API key | Scrapes the public sandbox repository |

## The guard

Three rules are mechanical rather than hoped for, enforced on every arm by
`charter_harness.guard`:

1. **Nothing is ever sent from the mailbox.** Neither `gmail.messages_send` nor
   `gmail.drafts_send` is in the Charter arm's tool set, and the raw arm may not
   POST to either path. Gmail has two ways to send, and a rule naming only one of
   them is a rule against half of sending.
2. **GitHub writes stay inside sandbox repositories.** Any non-GET call must
   target `<GITHUB_OWNER>/harness-*`. Existing repositories are read-only.
3. **Deletes and channel writes stay on what this run made.** A calendar event or
   a mail thread may only be deleted if this run created it, whether by the seed
   or by the agent itself. A Slack write may only go to the harness channel.

A fourth rule is about the comparison rather than safety: the raw arm may only
reach the endpoints the Charter arm has tools for. The allow-list is compiled
from the same pack tools the raw tool's description was derived from, so "same
endpoints on both arms" is enforced, not asserted.

## Provisioning, and the traps in each

**Google.** One consent covers all five packs. Mint `GOOGLE_REFRESH_TOKEN` with
`.venv/bin/python scripts/connect_google.py`, which prints a URL, listens on the
redirect port for one request, and prints the refresh token. Confirm the scopes
in `settings.GOOGLE_SCOPES` were all granted via `oauth2/v3/tokeninfo`.

The **Drive API must be enabled** in the Cloud project behind your OAuth client.
This is not optional and not only a teardown concern: `calendar_to_doc` and
`pr_to_doc` call `drive.files_list_eventually` inside `observe()`, so without it
those two cannot be graded at all, and five other teardowns leak files silently
because `Drive.file_delete` swallows 403.

**GitHub.** The harness needs a repository named `harness-sandbox` under the
owner in `GITHUB_OWNER`, initialised.

A fine-grained PAT **cannot create repositories at all**, whatever permissions it
carries. `POST /user/repos` returns 403 "Resource not accessible by personal
access token". `World.github.ensure_sandbox()` therefore only works because the
repo already exists: it does a `GET` first and returns early. Create it with the
`gh` CLI using a classic token with `repo` scope, not by rerunning the harness.

**The sandbox repo must be public.** `firecrawl_to_linear` has the model scrape
`gh.blob_url(...) + "?plain=1"` with no credentials, and Firecrawl cannot read a
private repo. Note that `ensure_sandbox()` hardcodes `"private": True`, so a
fresh bootstrap produces a repo that breaks that scenario and its five variants.
Fix with `gh repo edit --visibility public`.

**Shopify.** Provision through the CLI:

```bash
shopify store auth --store <your-store>.myshopify.com \
  --scopes read_products,write_products,read_customers,write_customers,\
read_inventory,write_inventory,read_locations
```

The CLI does not print the token. It writes it to
`~/Library/Preferences/shopify-cli-store-nodejs/config.json` under
`sessionsByUserId/<id>/accessToken`, from where it is copied into `.env`.

⚠️ **This token expires 24 hours after it is issued.** Despite its `shpat_`
prefix it is an *online* token with a real `expiresAt`, so a run started after
expiry gets 401s on the two Shopify scenarios. Re-run the command above and copy
the token out again. For a token that does not expire, create a custom app in the
store admin under Settings > Apps and sales channels > Develop apps.

**Slack.** Create an app, install it to a workspace you own, and put the bot into
one channel. `SLACK_CHANNEL` names it. The bot token needs the nine scopes the
pack's API calls use, plus `channels:manage` and `channels:join` so the channel
can be created and joined over the API rather than by hand.

Verify the round trip: `conversations.list`, `conversations.history`,
`conversations.replies`, `chat.postMessage`, `chat.delete`, `reactions.add`,
`users.list`, `users.info`. The `channel_join` message Slack posts when the bot
joins cannot be deleted by anyone and is expected to stay.

## The tool surface the arm presents

The Charter arm hands Inspect **exactly what `Tool.to_json_schema()` emits**.
That is a rule rather than an implementation detail: the moment the arm reshapes
a schema, every arm-to-arm number measures the harness instead of the product,
and nothing in the suite will tell you.

It was broken from the harness's first commit (99f21462, 2026-09-07) until
2026-09-15. `inline_refs` flattened `$ref`/`$defs` because
Inspect's `JSONSchema` has no reference fields, so **every Charter-arm token
number taken before 2026-09-15 was measured against a tool surface no SDK user is
given.** Treat those as void. Context-byte numbers are unaffected: they measure
tool output, not schemas.

Three properties of `inspect_ai` the arm is built around, all found the hard way:

1. **It re-resolves the tool source on every turn** of the react loop
   (`progressive_arm.py`'s own docstring says so), so anything expensive in
   building a `ToolDef` is paid per turn, not per run. `_PARAMS` memoises the
   built `ToolParams` for exactly this.
2. **It deep-copies every tool's parameter schema on every `generate`**:
   `_model.py:1319` → `_call_tools.py:915` → `_tool_def.py:253` → pydantic
   `model_copy` → `copy.deepcopy`. Schema *size* therefore costs CPU per turn
   even when it is built once, which is why memoising the old inliner fixed
   nothing on its own. It is also why `tests/test_tool_bridge.py` was a
   thirty-minute file, and a suite that slow is how an invariant goes unchecked.
3. **`JSONSchema` and `ToolParams` drop `$ref`/`$defs` silently.** They declare a
   fixed field set with no `extra`, so pydantic discards unknown keys at
   validation and `model_construct` does not help because the dump drops them
   too. `_open_inspect_schema()` reopens both with `extra="allow"` and
   `model_rebuild(force=True)`, after which references survive validation, the
   dump and the wire. Fireworks accepts them and the models resolve them.

`_PARAMS` is keyed on `(pack, name, prune, pins)`, never on `pack.name` alone. A
projection keeps the name of the tool it narrowed, so `linear.issues_list` names
two different schemas once `pack_tools` has run, and a name-only key served
whichever was built first for both.

## Why the arm projects Linear

`RECURSIVE_FIELD` and `recursive_paths()` narrow the seventeen Linear tools that
reach the pack's filter cycle. This is not a context optimisation. Without it
Fireworks refuses the request outright:

```
400 JSON Schema not supported: schema depth exceeds maximum limit of 50.
```

The cap is on depth *after* resolving `$ref`, which a cycle exceeds without
bound, and the **whole request** is rejected rather than the one tool. The turn
produces no tool call and the run reads as an agent that did nothing.

Three things about that rule, each of which cost a debugging round:

- The marker is matched **case-insensitively, as a substring**, because the name
  is not one name. `search_issues` carries `variables.filter`;
  `custom_view_create` carries `filter_data`, `project_filter_data`,
  `initiative_filter_data` and `feed_item_filter_data` a level deeper. Matching
  the literal `filter` left that one tool at 193 KB, one loaded tool away from
  taking a run down.
- It walks the **request model**, not the generated JSON schema. The JSON schema
  carries wire names (`filterData`) while a projection selects on field names
  (`filter_data`), so paths read off it are rejected as fields of no model.
- Only tools over `_PROJECT_OVER_BYTES` are narrowed. Width is not the problem:
  `gsheets.spreadsheets_batch_update` has 201 definitions and
  `gcalendar.events_insert` 21, none in a cycle, and narrowing those would remove
  arguments the model legitimately needs for no gain.

Verified end to end on `linear_triage`, progressive arm: 2/2 runs, 0 tool errors,
0 guard rejections. Every Linear tool is under 7.2 KB afterwards.

## When a run stalls

Get the stack before theorising. The night of 2026-09-14 went to rate limiting,
connection pooling and a shared client; one dump showed the process at 84% CPU
inside `copy.deepcopy`, with no request ever in flight.

```bash
kill -USR1 $(pgrep -f "charter_harness.campaign run" | head -1)
tail -60 /tmp/charter-stacks.txt
```

Read the symptoms the other way round from the obvious one:

- **Nothing reaching the provider** usually means nothing is *trying*, not that
  the provider is slow.
- **CLOSE_WAIT piling up** means nothing local is reading the socket, which is
  what a CPU-pegged event loop looks like from outside. Healthy is many
  ESTABLISHED, no CLOSE_WAIT, and the process near **0.1% CPU**, because it
  should be waiting on the model.
- **A fix that changes nothing** is evidence the theory is wrong, not that the
  fix was partial.

Then ask what the failing runs have in common before proposing a mechanism. Every
batch that stalled that night contained a Linear scenario and every clean batch
did not, which was available from the first stall.

And an exclusion made on a wrong diagnosis removes the evidence that would have
corrected it. Firecrawl was excluded for failing 4/4 when the failing scenario
was `firecrawl_to_linear` and the cause was Linear's schema. Write the reason
next to an exclusion, and re-test it once the suspected cause is fixed.

## Before a long run

1. Run `scripts/check_auth.py`. A green line per provider is the readiness signal.
2. Check the Shopify token has not aged out.
3. Remember the mailbox is real. Scenarios relabel messages and create drafts
   there. Nothing sends.

## The live suite

`tests/live` calls every pack tool directly, with hardcoded arguments, against the
same accounts the scenarios use. No model, so it costs no inference; the whole run
is about two minutes.

```bash
cd harness
.venv/bin/python -m pytest tests/live -m live            # all providers
.venv/bin/python -m pytest tests/live -m live -k stripe  # one
.venv/bin/python -m pytest tests/live -m live -q -rs     # with the skip reasons
```

It is **deselected by default** (`addopts = -m 'not live'`), because the rest of
the suite is offline by rule. `-m live` on the command line replaces that.

What it is for: the offline suite proves a declaration is self-consistent, and the
scenarios prove an agent can use it, but neither asks the provider whether the
declaration is *true*. A renamed field, a dropped enum value, a filter the API
ignores rather than rejects — all three pass a respx mock and fail in production.
Every finding in the first run was of that kind.

Reading the output:

- **skipped** is the normal state of a partly-wired checkout. A provider with no
  credentials, a token without a scope, an account with no disputes to read — each
  skips with the reason and, where there is one, the command to fix it.
- **xfailed** is a known hole in a pack, with the diagnosis in the marker. They are
  `strict=True`, so fixing the pack turns the test red until the marker goes.
- **failed** means a provider disagrees with a declaration. That is the whole point
  of the file.

Two rules for adding to it:

1. **Teardown goes through `charter_harness.world`, never through the pack.**
   Deleting a test's leftovers with the tool under test lets a broken delete read
   as a clean run.
2. **Assert through the response handler, not around it.** What the trim keeps is
   what the agent sees. Where a field is trimmed away, prove the argument arrived
   by the behaviour it caused — a manual-capture intent reaching `requires_capture`
   rather than `succeeded`.
