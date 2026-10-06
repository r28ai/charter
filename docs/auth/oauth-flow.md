---
title: "Getting the grant"
description: "Build the authorization URL and exchange the callback's code. The route, session, and storage stay yours."
sidebarTitle: "Getting the grant"
---

<Note>
This page is the flow **inside your app**, for a product whose users each
connect their own account. Connecting one account — yours — to a script or an
agent you run needs none of it: [your own account](/auth/your-own-account)
names what each pack needs, and each guide ends in a working call. For what
each pack's users connect with, and the server constants, see
[every pack](/auth/your-users).
</Note>

Charter's OAuth surface has two halves. [`OAuth2Client`](/auth/authorization-servers)
*uses* a grant: inject, cache, refresh, rotate, die loudly.
[`OAuth2Flow`](/reference/oauth#oauth2flow) *obtains* one — and does only the two
steps of that which are protocol rather than product:

1. **[Build the authorization URL](/reference/oauth#oauth2flow-authorize)** — RFC
   6749 §4.1.1, PKCE per RFC 7636. A pure function: no I/O, no state, no
   framework.
2. **[Exchange the code for tokens](/reference/oauth#oauth2flow-exchange)** — RFC
   6749 §4.1.3. One form POST to the same `token_endpoint` the refresh uses.

Everything between those two steps belongs to your web framework, and the
library holds nothing across the gap — `authorize()` hands `state` and the PKCE
verifier back *to you*, and `exchange()` takes the verifier back. That is not a
missing feature; it is the line. Only your framework knows which browser is
which, so the session is yours, and a library that quietly grew one would have
grown a wrong one.

## The split, precisely

<img
  className="split-diagram split-diagram-light"
  src="/images/oauth-split-light.webp"
  alt="Two lanes, Charter and you, with seven numbered steps alternating between them. Charter: flow.authorize() builds the authorization URL, PKCE verifier and challenge, and state. A dashed band across both lanes: the redirect and the consent screen, on the authorization server, where neither of you is running. You: the callback route, then states_match() verifying state. Charter: flow.exchange() turns the code into tokens. You: storing the refresh token. Charter: OAuth2Client.from_grant() refreshing, caching and rotation from then on. A bracket down your lane, from the authorization URL to the state check, marks what your session holds across the redirect: state and the PKCE verifier."
/>
<img
  className="split-diagram split-diagram-dark"
  src="/images/oauth-split-dark.webp"
  alt=""
/>

Charter's two touches are brief and yours is continuous, which is the same thing
the bracket says: the verifier exists on your side for the whole time the browser
is somewhere else. Row by row, with each half's link:

| step | owner |
|---|---|
| authorization URL, PKCE verifier + challenge, `state` generation | **Charter** — [`flow.authorize()`](/reference/oauth#oauth2flow-authorize) |
| the redirect, the consent screen | the authorization server |
| the callback route | **you** |
| holding `state` + verifier between redirect and callback | **you** (your session) |
| verifying `state` | **you**, with [`states_match()`](/reference/oauth#states_match) |
| code → tokens | **Charter** — [`flow.exchange()`](/reference/oauth#oauth2flow-exchange) |
| storing the refresh token | **you** (your database) |
| refreshing, caching, rotation from then on | **Charter** — [`OAuth2Client.from_grant(...)`](/reference/oauth#oauth2client-from_grant) |

## The flow

```python oauth_routes.py
from charter.auth import OAuth2Client, OAuth2Flow, OAuth2Server, scopes_for, states_match
from charter.packs import gmail

# The constant as it is maintained on /auth/providers/google.
GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)

flow = OAuth2Flow(
    GOOGLE,
    client_id=os.environ["GOOGLE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
    redirect_uri="https://app.example.com/oauth/google/callback",
)

# your route
request = flow.authorize(scopes=scopes_for(gmail.TOOLS), login_hint=user.email)
session["oauth"] = {"state": request.state, "verifier": request.code_verifier}
return redirect(request.url)

# your callback route
if not states_match(session["oauth"]["state"], received_state):
    abort(400)
grant = await flow.exchange(code, code_verifier=session["oauth"]["verifier"])
await db.grants.put(user.id, "google", grant.refresh_token)

gmail.configure(credential_provider=OAuth2Client.from_grant(
    GOOGLE, grant,
    client_id=..., client_secret=...,
    on_refresh=partial(save, user.id),
))
```

[`scopes_for(gmail.TOOLS)`](/reference/oauth#scopes_for) reads the `scopes` metadata every tool is declared
with — deduped, first-seen order — so the consent screen asks for exactly what
the agent can do, and stays in lockstep with the tool set instead of being
hand-maintained beside it.

`from_grant` seeds the client's cache with the grant's access token, so the
first tool call after connecting does not spend a refresh. A grant with no
refresh token is refused there: a client that can never refresh is a footgun,
not a convenience.

## The failure this flow exists to catch

The dangerous parameters in OAuth are the ones that fail *silently* when
omitted. Google without `access_type=offline` returns no refresh token: nothing
errors, the access token works, the integration dies an hour later. Two
defenses, layered:

- The lore is **declared**, once, as `authorization_params` on the
  [`OAuth2Server`](/reference/oauth#oauth2server) — copy it from [the Google page](/auth/providers/google) with
  the rest of that server's constants.
- The exchange **checks the result**: [`exchange()`](/reference/oauth#oauth2flow-exchange)
  defaults to `expect_refresh_token=True` and raises a
  [`CredentialError`](/reference/errors#credentialerror) naming
  `access_type=offline` / `prompt=consent` when no refresh token came back.
  Pass `expect_refresh_token=False` only for a server that genuinely never
  issues one.

## More than one process

The client caches a user's access token and refreshes it under a lock, so
twelve concurrent tool calls in one process share one refresh. That lock is
per process. Run several workers (gunicorn, a few containers, serverless
instances) and each builds its own client for the same user, each holding its
own copy of the grant.

Against a server that keeps one refresh token for the life of the grant, as
Google does, that costs nothing. Against one that rotates (Stripe, Linear,
Slack with rotation on), a copy goes stale the moment another worker
refreshes: the server has spent that refresh token and handed its successor to
someone else. The stale worker's next refresh answers `invalid_grant`, and
Charter reports that the user has to authorize again, for a grant that is fine.
Stripe goes further: a refresh also revokes the previous *access* token, within
a few seconds. Two workers that each refresh fail each other's next call, and
then refresh again.

So the workers share the grant through your store. Hand the client a function
that reads it, where you would have passed the refresh token, and have
`on_refresh` write all three values back:

```python stripe_workers.py
async def stripe_for(user_id: str):
    async def stored_grant():
        row = await db.grants.get(user_id, "stripe")
        return TokenGrant(
            access_token=row.access_token,
            refresh_token=row.refresh_token,
            expires_at=row.expires_at,
        )

    async def store(credentials, refresh_token):
        await db.grants.put(
            user_id, "stripe", refresh_token,
            access_token=credentials.token, expires_at=credentials.expires_at,
        )

    return OAuth2Client(
        STRIPE_APPS,
        client_id=os.environ["STRIPE_APP_CLIENT_ID"],
        client_secret=os.environ["STRIPE_SECRET_KEY"],
        refresh_token=stored_grant,
        on_refresh=store,
    )
```

Whenever a worker's own token is due, or the API has refused it, the client
reads the store first. A stored access token that is still good, and isn't the
one just refused, is used as it is: one refresh serves every worker. Otherwise
the client refreshes with the stored refresh token, and if the server answers
`invalid_grant` it reads the store once more, in case another worker stored a
successor in the moment between. `on_refresh` has finished before the call that
triggered the refresh goes out.

A loader may return only the refresh token, as a string. That is enough
against a server that rotates refresh tokens but leaves earlier access tokens
alone. Returning the whole grant is right everywhere, and it saves the extra
refreshes.

### What each provider does

OAuth leaves all of this to the server. [RFC 6749 §6](https://www.rfc-editor.org/rfc/rfc6749#section-6)
lets it issue a new refresh token or not, and lets it revoke the old one; the
fate of earlier access tokens isn't specified at all. So the providers differ,
and the table is what each one's own documentation says. Where a cell was
measured rather than read, it says so.

| Provider | Access token | Refresh token | A refresh retires the previous access token | A spent refresh token, presented again |
|---|---|---|---|---|
| [Google](https://developers.google.com/identity/protocols/oauth2/web-server#offline) | `expires_in` sent | not rotated | not documented | — |
| [Slack](https://docs.slack.dev/authentication/using-token-rotation), rotation on | 12 hours, `expires_in` sent | rotated; the old one revoked "after a short grace period" | at most two are active: a refresh beyond that revokes the oldest | fails |
| [GitHub App](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/refreshing-user-access-tokens), expiry on | 8 hours, `expires_in` sent; refresh token 6 months | rotated | yes, at once | not documented |
| [Linear](https://linear.app/developers/oauth-2-0-authentication) | 24 hours, `expires_in` sent | rotated | not documented | accepted for 30 minutes, "to allow for network errors" |
| [Notion](https://developers.notion.com/reference/refresh-a-token) | not documented; no `expires_in` | a `refresh_token` comes back; rotation not documented | not documented | not documented |
| [Shopify](https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens/offline-access-tokens), expiring offline token | 1 hour, `expires_in` sent; refresh token 90 days | rotated | documented: it "retires your previous expiring offline token". Measured: still accepted 10 minutes after the refresh | usable until the newer one is used, or for 30 days (measured: accepted) |
| [Stripe App](https://docs.stripe.com/stripe-apps/api-authentication/oauth) | 1 hour, **no `expires_in`**: declare `default_expires_in=3600`. Measured: accepted at 58 minutes, refused at 60 with a `401` | rotated | yes, [`platform_api_key_expired`](https://docs.stripe.com/error-codes/platform-api-key-expired); measured at 2 to 7 seconds | refused, and the grant survives (measured) |

Two things follow for several workers. Wherever a refresh retires the previous
access token (GitHub, Stripe, and Slack beyond two), the workers have to share
the access token as well as the refresh token, so the loader returns the whole
grant. Returning it is right for the others too: it saves the refreshes. And none of the seven documents reuse detection, so for these
the lock below is a safeguard rather than a requirement. GitHub and Notion
don't say either way.

### A lock around the refresh

Two workers that find the stored token due at the same moment both read the
store before either has written to it, so both refresh with the same token.
What that costs depends on the server:

- **Stripe, and servers like it**, accept both refreshes. Stripe then revokes
  the access token of whichever finished first, so one call fails and the
  next reads the other's token from the store. A lock is optional.
- **A server with reuse detection** treats the second presentation as theft.
  [RFC 9700 §4.14](https://www.rfc-editor.org/rfc/rfc9700#section-4.14) says
  it "will revoke the active refresh token", and it recommends this design.
  Nothing fails at first: the loser takes the winner's stored access token.
  An hour later no refresh token is left, and the user has to connect again.
  Reading the store after `invalid_grant` cannot help, because the grant is
  already gone. Here the lock is mandatory.

Charter holds no connection to your store, so you supply the lock, as an async
context manager scoped to the grant. The client holds it while it reads the
store, refreshes if it still has to, and runs `on_refresh`. Whoever takes it
next reads the stored result instead of refreshing again:

```python grant_lock.py
from contextlib import asynccontextmanager


def grant_lock(user_id: str, provider: str):
    @asynccontextmanager
    async def held():
        async with pool.acquire() as conn, conn.transaction():
            # Postgres: released when the transaction ends, whatever happens.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{user_id}:{provider}")
            yield

    return held


async def stripe_for(user_id: str):
    ...
    return OAuth2Client(
        STRIPE_APPS,
        client_id=os.environ["STRIPE_APP_CLIENT_ID"],
        client_secret=os.environ["STRIPE_SECRET_KEY"],
        refresh_token=stored_grant,
        on_refresh=store,
        refresh_lock=grant_lock(user_id, "stripe"),
    )
```

A Redis lock with a timeout works the same way. The lock needs a loader: a
refresh token passed as a string is a copy, and holding a lock cannot make a
copy current, so `refresh_lock` without one raises `ValueError`. A lock that
cannot be taken raises `CredentialError` and makes no refresh.

`on_refresh` carries more weight here than in one process. An `on_refresh` that
raises is logged and the call goes ahead, since the token is still good for
this process. But the store then holds a refresh token the server has already
spent, and the next worker presents it. Against reuse detection, that one
failed write disconnects the user, so make sure it alerts you.

## Security invariants

**PKCE always.** On by default, S256 only — there is no `plain` method and
never will be. `pkce=False` exists solely for a server that rejects unknown
parameters; it is not a documented path.

**Verify `state`, in constant time.** The `state` check at your callback is the
CSRF defense that keeps an attacker from splicing their authorization code into
your user's session. [`states_match(expected, received)`](/reference/oauth#states_match)
is `==` minus the timing leak — use it instead of `==`, and reject the callback
when it fails.

**`redirect_uri` never comes from user input.** It is a registration fact,
fixed at `OAuth2Flow` construction and sent identically in both steps. Building
it per-request from a `Host` header or a `next=` parameter is how open
redirectors and token leaks happen.

**Identity cannot be smuggled through params.** `authorization_params` and
`extra_params` may add vendor parameters, but overriding `client_id`,
`redirect_uri`, `state` or `code_challenge*` through either raises `ValueError`.

**Secrets stay out of reprs and errors.** `OAuth2Flow`,
[`TokenGrant`](/reference/oauth#tokengrant) and
[`OAuth2Client`](/reference/oauth#oauth2client) all print with their secrets
masked; a grant in a log line leaks nothing. Servers quote what they refuse
("Refresh token does not exist: rt_..."), so a token endpoint's error has every
credential the request sent replaced by `***` before it becomes a
`CredentialError`.

## Trying it from a terminal

[`examples/connect_google.py`](https://github.com/r28ai/charter/blob/main/examples/connect_google.py) runs the whole
flow for a personal account with a stdlib `http.server` loopback callback — an
example you own and can read in one screen, not a library API. The two calls
above are the only Charter in it; everything else is the redirect and the wait,
which is the point.

[Set up Google](/auth/setup/google) wraps that script in the rest of the
job — what to register with Google first, what to store afterwards, and the one
call that proves the scopes were right.

## Non-goals

- **Device authorization grant (RFC 8628)** — out of this iteration; a
  legitimate future candidate, since it is form-POST-only and would fix the
  CLI on-ramp.
- **JWT-bearer / service accounts** — never: they need a signature, and nothing
  in Charter signs anything, by the same rule that keeps AWS SigV4 out.
