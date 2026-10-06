#!/usr/bin/env python
"""Check Charter's OAuth path against a real provider, and the provider's docs against it.

Deliberately not a test, for the same reason as ``live_google_check.py``: the
suite is offline by rule. What the tests prove is that Charter is
self-consistent; what this proves is that the provider agrees, and that the
provider does what its documentation says.

Three steps, each its own command::

    uv run python scripts/live_oauth_check.py connect --provider linear
    uv run python scripts/live_oauth_check.py check   --provider linear
    uv run python scripts/live_oauth_check.py expiry  --provider linear   # waits out the token

``connect`` builds Charter's consent link and exchanges the code. The client ID
and secret come from ``<PROVIDER>_CLIENT_ID`` and ``<PROVIDER>_CLIENT_SECRET``.
``--link`` takes a link the provider gave you instead, and Charter builds its
own on the same endpoint with the same client ID: Stripe needs this, since an
unpublished app is only installable from its External test link. Stripe's
secret is ``STRIPE_SECRET_KEY``, in the mode of the link. Shopify takes
``--shop``.

A ``localhost`` redirect is caught by a listener on that port. Any other
redirect, such as the ``https`` one a live app must use, can't reach this
machine: approve in the browser, then paste the address the browser landed on,
even if that page shows an error.

``check`` uses only the stored grant, as a restarted server would. It calls
read-only tools, has two workers share one grant, hands it over at renewal,
and then sets what happens against what the provider's docs say: whether a
refresh retires the previous access token, and what a spent refresh token gets
when it comes back. A row that disagrees with the docs is a failure.
``expiry`` holds one access token until it lapses and confirms the client
renewed it first. For a provider that documents no lifetime it measures one.

Nothing writes to the account, and nothing prints a token: shapes, prefixes,
counts. Grants are kept in ``$CHARTER_LIVE_DIR`` (default ``~/.charter/live``),
readable by you alone.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import importlib
import json
import os
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path as FsPath
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

from charter.auth import (
    OAuth2Client,
    OAuth2Flow,
    OAuth2Server,
    StaticTokenProvider,
    TokenGrant,
    scopes_for,
    states_match,
)
from charter.auth.credentials import CredentialProvider, Credentials
from charter.types.errors import CharterError, CredentialError

# -----------------------------------------------------
# What the docs tell readers to paste. tests/test_docs_oauth.py holds each of
# these equal to its page, so a check that passes is a check of the page.
# -----------------------------------------------------

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)

SLACK = OAuth2Server(
    issuer="https://slack.com",
    authorization_endpoint="https://slack.com/oauth/v2/authorize",
    token_endpoint="https://slack.com/api/oauth.v2.access",
    token_endpoint_auth_method="client_secret_post",
)

GITHUB = OAuth2Server(
    issuer="https://github.com",
    authorization_endpoint="https://github.com/login/oauth/authorize",
    token_endpoint="https://github.com/login/oauth/access_token",
    token_endpoint_auth_method="client_secret_post",
)

LINEAR = OAuth2Server(
    issuer="https://linear.app",
    authorization_endpoint="https://linear.app/oauth/authorize",
    token_endpoint="https://api.linear.app/oauth/token",
    token_endpoint_auth_method="client_secret_post",
    scope_separator=",",
)

NOTION = OAuth2Server(
    issuer="https://api.notion.com",
    authorization_endpoint="https://api.notion.com/v1/oauth/authorize",
    token_endpoint="https://api.notion.com/v1/oauth/token",
    token_endpoint_auth_method="client_secret_basic",
    authorization_params={"owner": "user"},
    uses_scopes=False,
    token_request_format="json",
)

STRIPE_APPS = OAuth2Server(
    issuer="https://marketplace.stripe.com",
    authorization_endpoint="https://marketplace.stripe.com/oauth/v2/authorize",
    token_endpoint="https://api.stripe.com/v1/oauth/token",
    token_endpoint_auth_method="secret_key_basic",
    uses_scopes=False,
    default_expires_in=3600,
)


def shopify_server(shop: str) -> OAuth2Server:
    return OAuth2Server(
        authorization_endpoint=f"https://{shop}.myshopify.com/admin/oauth/authorize",
        token_endpoint=f"https://{shop}.myshopify.com/admin/oauth/access_token",
        scope_separator=",",
        exchange_params={"expiring": "1"},  # an offline token that expires, with a refresh token
    )


# -----------------------------------------------------
# Each provider: its server, a few read-only tools, and what its docs claim.
# None means the docs don't say, so the run reports what it saw.
# -----------------------------------------------------


@dataclass(frozen=True)
class Provider:
    name: str
    server: Optional[OAuth2Server]  # None: built per store (Shopify)
    pack: str
    reads: tuple[tuple[str, dict[str, Any]], ...]
    scopes: tuple[str, ...] = ()
    secret_env: Optional[str] = None  # default <NAME>_CLIENT_SECRET
    sends_expires_in: Optional[bool] = None
    rotates: Optional[bool] = None
    retires_previous_access: Optional[bool] = None
    spent_refresh_token: Optional[str] = None  # "refused" | "accepted"


def _scopes(pack: str, *tools: str) -> tuple[str, ...]:
    module = importlib.import_module(f"charter.packs.{pack}")
    chosen = [t for t in module.TOOLS if t.name.split(".")[-1] in tools]
    return tuple(scopes_for(chosen))


PROVIDERS = {
    "google": Provider(
        "google",
        GOOGLE,
        "gcalendar",
        reads=(("calendar_list_list", {"max_results": 1}),),
        scopes=_scopes("gcalendar", "calendar_list_list"),
        sends_expires_in=True,
        rotates=False,
    ),
    "slack": Provider(
        "slack",
        SLACK,
        "slack",
        reads=(("conversations_list", {"limit": 1}), ("users_list", {"limit": 1})),
        scopes=_scopes("slack", "conversations_list", "users_list"),
        sends_expires_in=True,
        rotates=True,
        retires_previous_access=False,  # at most two active; one refresh leaves the previous
        spent_refresh_token="refused",
    ),
    "github": Provider(
        "github",
        GITHUB,
        "github",
        reads=(("repos_list_for_authenticated_user", {"per_page": 1}),),
        scopes=_scopes("github", "repos_list_for_authenticated_user"),
        sends_expires_in=True,
        rotates=True,
        retires_previous_access=True,
    ),
    "linear": Provider(
        "linear",
        LINEAR,
        "linear",
        reads=(("viewer", {}), ("teams_list", {"variables": {"first": 1}})),
        scopes=("read",),
        sends_expires_in=True,
        rotates=True,
        spent_refresh_token="accepted",  # a 30-minute grace period
    ),
    "notion": Provider(
        "notion",
        NOTION,
        "notion",
        reads=(("users_retrieve_me", {}), ("search", {"body": {"page_size": 1}})),
        sends_expires_in=False,
    ),
    "shopify": Provider(
        "shopify",
        None,
        "shopify",
        reads=(("shop_get", {}), ("products_list", {"variables": {"first": 1}})),
        scopes=("read_products",),
        sends_expires_in=True,
        rotates=True,
        # Documented as retired, yet measured still accepted ten minutes after
        # the refresh, so the run reports what it sees rather than failing.
        retires_previous_access=None,
        spent_refresh_token="accepted",  # until the newer one is used, or 30 days
    ),
    "stripe": Provider(
        "stripe",
        STRIPE_APPS,
        "stripe",
        reads=(
            ("customers_list", {"limit": 1}),
            ("balance_retrieve", {}),
            ("products_list", {"limit": 1}),
        ),
        secret_env="STRIPE_SECRET_KEY",
        sends_expires_in=False,
        rotates=True,
        retires_previous_access=True,
        spent_refresh_token="refused",
    ),
}

# -----------------------------------------------------
# Reporting, and the grant on disk
# -----------------------------------------------------

failures: list[str] = []


def report(ok: Optional[bool], label: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "SEEN"}[ok]
    print(f"  {mark}  {label}{f' — {detail}' if detail else ''}", flush=True)
    if ok is False:
        failures.append(label)


def against_docs(label: str, documented: Any, observed: Any) -> None:
    """A row of the audit table, checked: PASS if it matches, SEEN if the docs are silent."""
    if documented is None:
        report(None, label, f"{observed} (not documented)")
    else:
        report(documented == observed, label, f"{observed}, documented {documented}")


def grant_path(provider: Provider) -> FsPath:
    root = FsPath(os.environ.get("CHARTER_LIVE_DIR", FsPath.home() / ".charter/live"))
    return root / f"{provider.name}.json"


def read_grant(provider: Provider) -> dict[str, Any]:
    path = grant_path(provider)
    if not path.is_file():
        sys.exit(f"No grant at {path}. Run `connect --provider {provider.name}` first.")
    return json.loads(path.read_text())


def write_grant(provider: Provider, **fields: Any) -> None:
    """Merge ``fields`` into the grant file, which is never readable by anyone else.

    Created 0600 rather than chmodded afterwards, so there is no moment when a
    refresh token sits in a file the umask left world-readable.
    """
    path = grant_path(provider)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = {**(json.loads(path.read_text()) if path.is_file() else {}), **fields}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(data))


def secret(provider: Provider) -> str:
    name = provider.secret_env or f"{provider.name.upper()}_CLIENT_SECRET"
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Set {name}.")
    return value


def server_for(provider: Provider) -> OAuth2Server:
    if provider.server is not None:
        return provider.server
    return shopify_server(read_grant(provider)["shop"])


# -----------------------------------------------------
# Workers: one process's client for the grant, as its SubjectProvider builds it
# -----------------------------------------------------


def worker(provider: Provider, refresh_token: Any = None) -> OAuth2Client:
    async def stored_grant() -> Any:
        row = read_grant(provider)
        if not row.get("access_token"):
            return row["refresh_token"]
        return TokenGrant(
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=row.get("expires_at"),
        )

    def store(credentials: Credentials, refresh_token: Optional[str]) -> None:
        expires_at = credentials.expires_at.isoformat() if credentials.expires_at else None
        write_grant(
            provider,
            access_token=credentials.token,
            expires_at=expires_at,
            refresh_token=refresh_token,
        )

    return OAuth2Client(
        server_for(provider),
        client_id=read_grant(provider)["client_id"],
        client_secret=secret(provider),
        refresh_token=refresh_token if refresh_token is not None else stored_grant,
        on_refresh=store,
    )


def refreshing_worker(provider: Provider) -> OAuth2Client:
    """A worker given only the refresh token: nothing to share, so it refreshes."""
    return worker(provider, lambda: read_grant(provider)["refresh_token"])


def pack(provider: Provider) -> Any:
    return importlib.import_module(f"charter.packs.{provider.pack}")


async def read_with(provider: Provider, credentials: CredentialProvider) -> Optional[str]:
    """Call the first read-only tool; None on success, else why it failed."""
    module = pack(provider)
    if provider.name == "shopify":
        module.configure(shop=read_grant(provider)["shop"], credential_provider=credentials)
    else:
        module.configure(credential_provider=credentials)
    name, args = provider.reads[0]
    try:
        await getattr(module, name).ainvoke(args)
        return None
    except CharterError as exc:
        return f"{type(exc).__name__}: {str(exc)[:140]}"


# -----------------------------------------------------
# connect
# -----------------------------------------------------


def wait_for_redirect(
    redirect_uri: str, listen: Optional[int] = None, landed_file: Optional[FsPath] = None
) -> dict[str, str]:
    """The callback's query: caught on localhost, or pasted from the address bar.

    ``listen`` catches it on a local port even though the redirect URL is
    public: a tunnel (ngrok, cloudflared) forwarding an ``https`` URL here, for
    a provider that refuses plain ``http`` redirects even to localhost, as
    Shopify does.
    """
    parts = urlsplit(redirect_uri)
    if listen is None and parts.hostname not in ("localhost", "127.0.0.1"):
        if landed_file is not None:
            print(f"Waiting for the address the browser landed on, in {landed_file}…", flush=True)
            while not (landed_file.is_file() and landed_file.read_text().strip()):
                time.sleep(1)
            landed = landed_file.read_text()
            return {k: v[0] for k, v in parse_qs(urlsplit(landed.strip()).query).items()}
        landed = input("Approve in the browser, then paste the address it landed on:\n> ")
        return {k: v[0] for k, v in parse_qs(urlsplit(landed.strip()).query).items()}

    captured: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urlsplit(self.path).path != parts.path:
                self.send_response(404)
                self.end_headers()
                return
            captured.update({k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Received. You can close this tab.")

        def log_message(self, *args: Any) -> None:
            pass

    host, port = (
        ("localhost", listen) if listen else (parts.hostname or "localhost", parts.port or 80)
    )
    with HTTPServer((host, port), Callback) as server:
        while not captured:
            server.handle_request()
    return captured


async def connect(
    provider: Provider,
    link: Optional[str],
    redirect: Optional[str],
    shop: Optional[str],
    listen: Optional[int] = None,
    landed_file: Optional[FsPath] = None,
) -> None:
    if provider.name == "shopify":
        if not shop:
            sys.exit("Shopify needs --shop, the store's subdomain.")
        write_grant(provider, shop=shop)
    server = server_for(provider)
    client_id = os.environ.get(f"{provider.name.upper()}_CLIENT_ID")
    if link:
        given = urlsplit(link)
        query = {k: v[0] for k, v in parse_qs(given.query).items()}
        client_id = query.get("client_id", client_id)
        redirect = redirect or query.get("redirect_uri")
        endpoint = f"{given.scheme}://{given.netloc}{given.path}"
        server = dataclasses.replace(server, authorization_endpoint=endpoint)
    if not client_id:
        sys.exit(f"Set {provider.name.upper()}_CLIENT_ID, or pass --link.")
    redirect_uri = redirect or "http://localhost:8765/callback"

    flow = OAuth2Flow(
        server, client_id=client_id, client_secret=secret(provider), redirect_uri=redirect_uri
    )
    request = flow.authorize(list(provider.scopes)) if server.uses_scopes else flow.authorize()
    print(f"Open this:\n\n{request.url}\n", flush=True)

    params = wait_for_redirect(redirect_uri, listen, landed_file)
    if "code" not in params:
        sys.exit(f"No code came back: {params.get('error')} {params.get('error_description', '')}")
    report(states_match(request.state, params.get("state", "")), "state matches")

    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)
    report(
        True,
        "code exchanged",
        f"access token {grant.access_token[:6]}…, refresh token {'yes' if grant.refresh_token else 'no'}",
    )
    against_docs(
        "the token response carries expires_in",
        provider.sends_expires_in,
        "expires_in" in grant.raw,
    )
    # Dated either by the response or by the server's declared lifetime: a
    # Stripe grant with no expiry means default_expires_in stopped applying.
    should_be_dated = bool(provider.sends_expires_in) or server.default_expires_in is not None
    report(
        (grant.expires_at is not None) == should_be_dated,
        "the grant's expiry",
        str(grant.expires_at) if grant.expires_at else "none",
    )
    write_grant(
        provider,
        client_id=client_id,
        access_token=grant.access_token,
        expires_at=grant.expires_at.isoformat() if grant.expires_at else None,
        refresh_token=grant.refresh_token,
    )
    print(f"Grant stored at {grant_path(provider)}.")


# -----------------------------------------------------
# check
# -----------------------------------------------------


async def check(provider: Provider) -> None:
    module = pack(provider)
    print("Read-only tools, from the stored grant alone:")
    first = worker(provider)
    for name, args in provider.reads:
        if provider.name == "shopify":
            module.configure(shop=read_grant(provider)["shop"], credential_provider=first)
        else:
            module.configure(credential_provider=first)
        try:
            await getattr(module, name).ainvoke(args)
            report(True, name)
        except CharterError as exc:
            report(False, name, f"{type(exc).__name__}: {str(exc)[:140]}")

    print("Two workers sharing one grant:")
    a, b = worker(provider), worker(provider)
    report(await read_with(provider, a) is None, "worker A reads")
    report(await read_with(provider, b) is None, "worker B reads")
    report(
        a._cached is not None and b._cached is not None and a._cached.token == b._cached.token,
        "B took A's stored token rather than refreshing",
    )

    print("The handover, with both workers inside the renewal window:")
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    for w in (a, b):
        assert w._cached is not None
        w._cached = w._cached.model_copy(update={"expires_at": soon})
    write_grant(provider, expires_at=soon.isoformat())
    before = a._cached.token
    report(await read_with(provider, a) is None, "worker A renews and reads")
    await asyncio.sleep(6)
    report(await read_with(provider, b) is None, "worker B reads, six seconds later")
    report(
        a._cached is not None
        and a._cached.token != before
        and b._cached is not None
        and b._cached.token == a._cached.token,
        "one refresh served both workers",
    )

    print("What a refresh does, against the docs:")
    previous = read_grant(provider)["access_token"]
    spent = read_grant(provider)["refresh_token"]
    report(
        await read_with(provider, refreshing_worker(provider)) is None,
        "a worker refreshes and reads",
    )
    rotated = read_grant(provider)["refresh_token"] != spent
    against_docs("the refresh token rotated", provider.rotates, rotated)
    # Retirement is not instant (Stripe's has landed anywhere from 2 to over 6
    # seconds), so poll for half a minute before calling the token kept.
    started, retired_after = time.monotonic(), None
    while time.monotonic() - started < 30:
        await asyncio.sleep(2)
        if await read_with(provider, StaticTokenProvider(previous)) is not None:
            retired_after = time.monotonic() - started
            break
    against_docs(
        "the previous access token was retired",
        provider.retires_previous_access,
        retired_after is not None,
    )
    if retired_after is not None:
        report(None, "retired after", f"about {retired_after:.0f} seconds")

    if rotated:
        # The replay keeps whatever it gets: a provider that accepts it may
        # retire the stored successor, and the grant has to survive either way.
        stale = worker(provider, spent)
        try:
            await stale.get_credentials(provider.name)
            outcome = "accepted"
        except CredentialError:
            outcome = "refused"
        against_docs(
            "a spent refresh token, presented again, is", provider.spent_refresh_token, outcome
        )
        report(
            await read_with(provider, refreshing_worker(provider)) is None,
            "the grant survives the replay",
        )


# -----------------------------------------------------
# expiry
# -----------------------------------------------------


async def expiry(provider: Provider, max_wait_minutes: int) -> None:
    client = worker(provider)
    reason = await read_with(provider, client)
    if reason:
        sys.exit(f"The grant doesn't read: {reason}")
    held = client._cached
    assert held is not None
    start = time.time()
    deadline = start + max_wait_minutes * 60
    if held.expires_at is not None:
        lapse = held.expires_at.timestamp() + 60
        if lapse > deadline:
            sys.exit(f"The token lasts until {held.expires_at:%H:%M} UTC, past --max-wait-minutes.")
        print(f"Holding a token dated {held.expires_at:%H:%M:%S} UTC. Waiting past it…", flush=True)
        deadline = lapse
    else:
        print(
            f"Holding a token with no stated lifetime. Probing every 5 minutes for {max_wait_minutes}…",
            flush=True,
        )

    alive = True
    while alive and time.time() < deadline:
        await asyncio.sleep(min(300, max(1, deadline - time.time())))
        alive = await read_with(provider, StaticTokenProvider(held.token)) is None
        print(
            f"  t+{(time.time() - start) / 60:4.1f}m: {'accepted' if alive else 'refused'}",
            flush=True,
        )

    if held.expires_at is None:
        report(
            None,
            "a token with no stated lifetime",
            "still accepted"
            if alive
            else f"refused after {(time.time() - start) / 60:.0f} minutes",
        )
        return
    report(not alive, "the provider refuses the token once its time is up")
    report(await read_with(provider, client) is None, "the same client reads without a failed call")
    report(
        client._cached is not None and client._cached.token != held.token,
        "it renewed the token first",
    )


# -----------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("connect", "check", "expiry"))
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    parser.add_argument(
        "--link", help="an install link the provider gave you (Stripe's External test link)"
    )
    parser.add_argument(
        "--redirect", help="the redirect URL, if not the link's or http://localhost:8765/callback"
    )
    parser.add_argument("--shop", help="Shopify: the store's subdomain")
    parser.add_argument(
        "--listen", type=int, help="catch a public (tunnelled) redirect on this local port"
    )
    parser.add_argument(
        "--landed-file",
        type=FsPath,
        help="read the address the browser landed on from this file, instead of a prompt",
    )
    parser.add_argument(
        "--max-wait-minutes", type=int, default=70, help="expiry: the longest it will wait"
    )
    args = parser.parse_args()
    provider = PROVIDERS[args.provider]

    if args.command == "connect":
        asyncio.run(
            connect(provider, args.link, args.redirect, args.shop, args.listen, args.landed_file)
        )
    elif args.command == "check":
        asyncio.run(check(provider))
    else:
        asyncio.run(expiry(provider, args.max_wait_minutes))

    if failures:
        sys.exit(f"\n{len(failures)} failed: {', '.join(failures)}")
    print("\nAll passed.")


if __name__ == "__main__":
    main()
