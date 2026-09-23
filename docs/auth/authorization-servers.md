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

Discovery fills in the `authorization_endpoint` too, when the document has one.
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

### Linear

```python linear_server.py
LINEAR = OAuth2Server(
    issuer="https://linear.app",
    authorization_endpoint="https://linear.app/oauth/authorize",
    token_endpoint="https://api.linear.app/oauth/token",
    token_endpoint_auth_method="client_secret_post",
)
```

## Anything else

One field is mandatory and the rest have sensible defaults — every one of them
is specified on [`OAuth2Server`](/reference/oauth#oauth2server):

| field | what it is |
|---|---|
| `token_endpoint` | where the form POST goes |
| `token_endpoint_auth_method` | `client_secret_post` (credentials in the body, the common case) or `client_secret_basic` (credentials in an HTTP Basic header) |
| `issuer` | optional, for your own readability |
| `authorization_endpoint` | where [`OAuth2Flow.authorize()`](/reference/oauth#oauth2flow-authorize) sends the user; optional — leave it off for a refresh-only declaration |
| `authorization_params` | extra consent-screen parameters the vendor requires but discovery cannot know (Google's `access_type=offline`); default empty |

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

Two behaviours worth knowing, because both are deliberate and both are visible:

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
Call `reset()` — or build a new client — after re-authorizing.

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

[rfc8414]: https://www.rfc-editor.org/rfc/rfc8414
