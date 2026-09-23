---
title: "Getting the grant"
description: "Build the authorization URL and exchange the callback's code. The route, session, and storage stay yours."
sidebarTitle: "Your users' accounts"
---

<Note>
This page is the flow **inside your app**, for a product whose users each
connect their own account. Connecting one account — yours — to a script or an
agent you run needs none of it: [your own account](/auth/your-own-account) is
five steps and ends in a working call.
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

**Secrets stay out of reprs.** `OAuth2Flow`,
[`TokenGrant`](/reference/oauth#tokengrant) and
[`OAuth2Client`](/reference/oauth#oauth2client) all print with their secrets
masked; a grant in a log line leaks nothing.

## Trying it from a terminal

[`examples/connect_google.py`](https://github.com/r28ai/charter/blob/main/examples/connect_google.py) runs the whole
flow for a personal account with a stdlib `http.server` loopback callback — an
example you own and can read in one screen, not a library API. The two calls
above are the only Charter in it; everything else is the redirect and the wait,
which is the point.

[Your own account](/auth/your-own-account) wraps that script in the rest of the
job — what to register with Google first, what to store afterwards, and the one
call that proves the scopes were right.

## Non-goals

- **Device authorization grant (RFC 8628)** — out of this iteration; a
  legitimate future candidate, since it is form-POST-only and would fix the
  CLI on-ramp.
- **JWT-bearer / service accounts** — never: they need a signature, and nothing
  in Charter signs anything, by the same rule that keeps AWS SigV4 out.
