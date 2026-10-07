---
title: "Authorization servers"
description: "Refresh an OAuth 2.0 grant against any token endpoint, with no vendor SDK."
---

Charter talks to any OAuth 2.0 token endpoint with no vendor SDK — not `google-auth`,
not a Slack client, nothing. A token endpoint is a form POST, and what differs
between servers is a handful of fields, named the way [RFC 8414][rfc8414] names
them.

There is deliberately **no built-in catalogue of vendors**. A constant shipped in
a release is pinned to that release, so when it changes everyone on an older
version is broken until you upgrade — whereas a constant in your own code you fix
in ten seconds. And a blessed-vendor list would imply that unlisted servers are
second class, which is the opposite of what is true here.

So: discover it, or copy four lines from a page here.

## Most servers describe themselves

Okta, Microsoft Entra ID, Auth0, Keycloak, Ping and Google all publish a metadata
document. One call to [`OAuth2Server.discover`](/reference/oauth#oauth2server-discover)
builds the declaration, and it cannot go stale:

```python discover_server.py
from charter.auth import OAuth2Server

server = await OAuth2Server.discover("https://login.acme-corp.com")
```

This tries OpenID Connect Discovery (`/.well-known/openid-configuration`), then
RFC 8414 (`/.well-known/oauth-authorization-server`). If a server publishes
neither, it tells you both URLs it tried.

This is the path for the enterprise IdP nobody has heard of — which is almost
always one of the products above, and therefore *more* discoverable than the
consumer APIs the packs talk to, not less.

Discovery fills in the `authorization_endpoint` too, when the document has one,
and the `revocation_endpoint` that a disconnect button needs.
What it can never fill in is `authorization_params` — see
[Google](/auth/providers/google), where those two parameters decide whether the
integration lives past its first hour.

**Entra ID**: the tenant lives in the path, so discover per tenant —
`await OAuth2Server.discover(f"https://login.microsoftonline.com/{tenant}/v2.0")`.
The `common` and `organizations` pseudo-tenants work the same way.

## Servers you write down

Copy the block. Paste it into your code. It documents itself there forever, and
you own the value. Google is here despite publishing discovery, because a
network round trip at import time is worse than a constant.

### The three the packs use

Each has a page carrying its constant, the scopes its packs declare, the wiring,
and the refresh traps that cost people an afternoon. The constants live there
and nowhere else, so there is one copy to be wrong:

| server | packs | page |
|---|---|---|
| Google | `gmail`, `gcalendar`, `gsheets`, `gdocs`, `gdrive` | [Google](/auth/providers/google) |
| Slack | `slack` | [Slack](/auth/providers/slack) |
| GitHub | `github` | [GitHub](/auth/providers/github) |

Google's constant is additionally checked against the live server by
`scripts/live_google_check.py`, which fails if Google's own discovery document
stops agreeing with what the page says. Run it with Application Default
Credentials:

```bash
gcloud auth application-default login
python scripts/live_google_check.py
```

It is a script rather than a test on purpose — the suite is offline by rule, and
this needs the network and a real grant.

### Linear, Stripe, Notion and Shopify

Each of these departs from the RFC somewhere: Linear and Shopify join scopes
with commas, Stripe authenticates its token endpoint with your secret key,
Notion wants JSON and takes no scopes. Their constants are on
[Connect your users' accounts](/auth/your-users), beside the flow that uses
them, and each departure is a field on the declaration rather than code.

## Anything else

One field is mandatory and the rest have sensible defaults — every one of them
is specified on [`OAuth2Server`](/reference/oauth#oauth2server):

| field | what it is |
|---|---|
| `token_endpoint` | where the form POST goes |
| `token_endpoint_auth_method` | `client_secret_post` (credentials in the body, the common case), `client_secret_basic` (credentials in an HTTP Basic header), or `secret_key_basic` (the secret alone as the Basic username — Stripe) |
| `issuer` | optional, for your own readability |
| `authorization_endpoint` | where [`OAuth2Flow.authorize()`](/reference/oauth#oauth2flow-authorize) sends the user; optional — leave it off for a refresh-only declaration |
| `authorization_params` | extra consent-screen parameters the vendor requires but discovery cannot know (Google's `access_type=offline`); default empty |
| `uses_scopes` | `False` for a server whose permissions are set where the app is registered (Notion, Stripe Apps): `authorize()` then takes no scopes and sends no `scope`; default `True` |
| `scope_separator` | how the consent link joins scopes: the RFC's space by default, `","` for Linear and Shopify |
| `token_request_format` | `"form"`, as the RFC says, or `"json"` for a token endpoint that takes only JSON (Notion) |
| `revocation` | how the server ends a grant, a [`Revocation`](/reference/oauth#revocation): RFC 7009 by default; see [Disconnecting a user](#disconnecting-a-user) |

If a wrong choice fails loudly it is safe to write down — a server expecting
Basic answers `invalid_client` on the first call. That is why these are declared
and `rotates_refresh_token` is not: rotation guessed wrongly fails silently,
days later. `authorization_params` is the exception that proves the rule — it
*does* fail silently when wrong, which is exactly why it belongs written on the
declaration where the constants live, and why
[`exchange()`](/reference/oauth#oauth2flow-exchange) checks the result (see
[the flow guide](/auth/oauth-flow)).

## Getting the grant

Everything above assumed a refresh token you already hold. When your product's
users connect their own accounts, the grant has to be obtained first —
[`OAuth2Flow`](/reference/oauth#oauth2flow) does the two protocol steps, your
framework does everything between them. [The flow guide](/auth/oauth-flow) has the shape end to end, and each
provider page has it wired for that server, including the vendor parameters that
decide whether a refresh token comes back at all.

## Using it

A declaration plus your registration is an
[`OAuth2Client`](/reference/oauth#oauth2client), and that credential provider is
what a factory like [`oauth_tool_factory`](/reference/factories#oauth_tool_factory)
or a pack takes:

```python acme_client.py
from charter import oauth_tool_factory
from charter.auth import OAuth2Client

acme = oauth_tool_factory(
    pack="acme",
    base_url="https://api.acme-corp.com/",
    provider="acme",
    credential_provider=OAuth2Client(
        server,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        refresh_token=stored_refresh_token,
        on_refresh=save_to_db,
    ),
)
```

For a shipped pack the same provider goes to its [`configure()`](/reference/configuration#configure) —
`gmail.configure(credential_provider=...)`, wired in full on
[the Google page](/auth/providers/google). For many end users, wrap it in
[`SubjectProvider`](#serving-many-users).

## Serving many users

[`get_credentials(provider)`](/reference/credentials#credentialprovider) names
the API, not the person — the runtime has no business knowing there is a person.
So identity travels out of band, read by *your provider* through
[`SubjectProvider`](/reference/credentials#subjectprovider) and
[`use_subject`](/reference/credentials#use_subject), never by the runtime:

```python acme_many_users.py
from charter import oauth_tool_factory
from charter.auth import OAuth2Client, SubjectProvider, use_subject

async def for_user(subject: str):
    row = await db.grants.get(subject, "acme")
    return OAuth2Client(
        server, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        refresh_token=row.refresh_token,
        on_refresh=partial(save, subject),
    )

acme = oauth_tool_factory(
    pack="acme",
    base_url="https://api.acme-corp.com/",
    provider="acme",
    credential_provider=SubjectProvider(for_user),
)

# then, per request
with use_subject(request.user_id):
    await agent.ainvoke(...)
```

A pack takes it the same way: `gmail.configure(credential_provider=SubjectProvider(for_user))`.

Tools are built once at import and work unchanged through LangChain, ADK, the
OpenAI tools interface and the Claude Agent SDK, because the lookup happens below
every adapter. A `ContextVar` is per-task in asyncio, so concurrent requests
sharing one set of tools cannot see each other's subject — and an unset subject
raises rather than falling back to a default, because acting as the wrong
principal is the one failure a boundary layer cannot ship.

Providers are capped (`max_subjects`, default 1000) and evicted
least-recently-used. Each carries its own cached token *and* its own refresh
lock, so eviction removes both together.

## What the cache does, precisely

Three behaviours worth knowing, because all three are deliberate and all three
are visible:

**Renewal is capped at half the granted lifetime.** `leeway_seconds` (default 90)
renews a token shortly before it expires. But a server issuing 60-second tokens
would make every token born already inside its own renewal window, so every call
would refresh — turning one request into two, and churning a new refresh token per
call against a rotating server. The leeway is therefore capped at half whatever
lifetime the server granted, so early renewal still happens for an hour-long token
and quietly stops mattering for a very short one.

**A revoked grant is asked about once a minute, not once a call.** `invalid_grant`
means the refresh token is dead until a human re-authorizes; retrying cannot help.
Token endpoints rate-limit per *client*, so an agent that keeps calling tools for a
revoked user would degrade every other user of your app. The client remembers the
refusal for 60 seconds and raises the same [`CredentialError`](/reference/errors#credentialerror) without asking again.
Call `reset()` — or build a new client — after re-authorizing. The error's
`reauthorize` is true, so your app can tell this from a failure worth retrying.
A server that names a dead grant its own way declares the codes in
`dead_grant_errors`: Slack answers `invalid_refresh_token` or `token_revoked`,
GitHub `bad_refresh_token`, Linear `invalid_request`.

**A token the API refuses is dropped, not kept until it expires.** A token can
die early: an app uninstalled and reinstalled, a secret rotated, a grant revoked
and given again. When a call comes back `401`, or with an envelope's credential
error, the runtime tells the provider that issued the token, and the client
forgets it, so the next call fetches a new one. Before this a running server
sent the dead token until the expiry it was issued with, which for Shopify is a
day. The call that was refused still raises: retrying is yours to decide. Only
that token is dropped — if a concurrent call has already replaced it, the
replacement stays — and the grant is kept, so a dead *grant* still lands on the
cool-down above.

A provider of your own can take part by defining `invalidate(credentials)`.
`SubjectProvider` passes it on to the current subject's provider, and the packs'
own providers pass it on to the client they hold.

## Disconnecting a user

Deleting a stored refresh token does not disconnect anybody. The grant stays
live at the server with every scope it was given, the app stays on the user's
list of connected apps, and for a server whose refresh tokens never expire,
Google's among them, that is permanent. Disconnecting is a request to the
server, and it is one more piece of protocol:
[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009) token revocation.

The server says how it takes that request in its declaration, as
[`revocation`](/reference/oauth#revocation), and the client sends it:

```python acme_disconnect.py
from charter.auth import OAuth2Client, OAuth2Server, Revocation

server = OAuth2Server(
    token_endpoint="https://login.acme-corp.com/oauth2/v1/token",
    revocation=Revocation("https://login.acme-corp.com/oauth2/v1/revoke"),
)

client = OAuth2Client(
    server, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
    refresh_token=stored_refresh_token,
)
await client.revoke()   # True: revoked. False: it was already gone.
await db.grants.delete(user.id, "acme")
```

[`discover()`](/reference/oauth#oauth2server-discover) fills `revocation` in
from the server's `revocation_endpoint`, so most enterprise IdPs need nothing
written. The vendors depart from the RFC in small ways, each a field on
`Revocation`: GitHub, Slack and Shopify end a grant given a live access token
rather than the refresh token, GitHub and Shopify with a `DELETE`. The
declarations on the provider pages already carry them. One server departs
further: Stripe Apps ends a grant by uninstalling the app, two requests and
no token, so its declaration is a [`Revoker`](/reference/oauth#revoker), a
procedure kept in the Stripe pack, and the call is still `revoke()`.

Serving many users, [`SubjectProvider.revoke(user_id)`](/reference/credentials#subjectprovider)
builds that user's client from your store, revokes, and forgets it, in one
call:

```python acme_disconnect_route.py
from charter.auth import SubjectProvider

users = SubjectProvider(for_user)  # give this one to the factory, and keep it


async def disconnect(user_id: str):
    await users.revoke(user_id)
    await db.grants.delete(user_id, "acme")
```

A token you hold as a string, with no client around it, is
[`revoke_token(server, refresh_token=..., access_token=...)`](/reference/oauth#revoke_token).

**Already gone is not an error.** A user who removed the app from their
account settings first, or a grant that expired, comes back as the server's
"invalid token". `revoke()` returns `False` rather than raising, since the
user is disconnected either way. Any other refusal, such as a wrong client
secret, raises [`CredentialError`](/reference/errors#credentialerror) and
leaves the client as it was, so the call can be retried. RFC 7009 itself has
a server answer `200` for a token it does not know, and a server that follows
it, Notion among them, never says "already gone": there `revoke()` returns
`True` either way.

**A revoked client does not refresh.** Afterwards `get_credentials` raises a
`CredentialError` whose `reauthorize` is true, without asking the token
endpoint. A client built with a [`GrantLoader`](/reference/oauth#grantloader)
recovers on its own once the store holds a new grant: the user connected
again.

**Delete your row after the revocation, not before.** The client needs the
refresh token to send. A loader-backed client reads the store under its
`refresh_lock` first, so in a multi-process deployment the token revoked is
the one the store holds, not one another process has already rotated away
from.

| server | what disconnecting sends | page |
|---|---|---|
| Google | the refresh token, alone | [Google](/auth/providers/google#disconnecting) |
| Slack | `apps.uninstall`, with the bot token | [Slack](/auth/providers/slack#disconnecting) |
| GitHub | `DELETE /applications/{client_id}/grant`, with an access token | [GitHub](/auth/providers/github#disconnecting) |
| Linear | the refresh token, with `token_type_hint` | [Your users](/auth/your-users#disconnecting-a-user) |
| Notion | the access token, as JSON with Basic auth | [Your users](/auth/your-users#disconnecting-a-user) |
| Shopify | `DELETE api_permissions/current.json`, which uninstalls the app | [Your users](/auth/your-users#disconnecting-a-user) |
| Stripe Apps | an uninstall through the App Installs API, `StripeAppUninstall` | [Your users](/auth/your-users#disconnecting-a-user) |

## What Charter does not do

**It does not hold anything between `authorize()` and `exchange()`.** The two
protocol steps of obtaining a grant are `OAuth2Flow`'s ([the flow
guide](/auth/oauth-flow)); the callback route, the session holding `state` and the
PKCE verifier, storage and the consent UI belong to your web framework, forever.

**It does not sign anything.** JWT-bearer, Google service accounts and anything
else needing a signed assertion are out of scope — the same rule that keeps AWS
SigV4 out. Two grants are supported, both a plain form POST:
`refresh_token` and `client_credentials`.

**It does not store a token.** The access token lives in memory for the seconds
it is valid. Persistence is yours, through `on_refresh` — which is also how a
multi-process deployment shares one refresh: your store is the shared cache.
Deleting the row when a user disconnects is yours for the same reason;
revoking the grant at the server is Charter's.

[rfc8414]: https://www.rfc-editor.org/rfc/rfc8414
