"""
Connect the Google account the harness runs against — once.

Runs the OAuth consent flow for all four Google packs in a single grant
(gmail.modify, calendar, spreadsheets, documents) and prints the refresh token
to put in ``harness/.env`` as ``GOOGLE_REFRESH_TOKEN``. Sign in with the
*secondary* account: the harness relabels messages, creates drafts, events,
spreadsheets and documents in whatever account consents here.

    cd oss/harness
    .venv/bin/python scripts/connect_google.py

Reads GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI from
``harness/.env``. The redirect URI must be registered on the OAuth client and
must be a localhost URL — this script listens on it for exactly one request.
"""

from __future__ import annotations

import asyncio
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from charter.auth import OAuth2Flow, states_match

from charter_harness.settings import GOOGLE, GOOGLE_SCOPES, load


def wait_for_callback(host: str, port: int) -> dict:
    captured: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            captured.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Connected - you can close this tab and return to the terminal.")

        def log_message(self, *_):  # keep the terminal for the token
            pass

    with HTTPServer((host, port), Callback) as server:
        server.handle_request()
    return captured


async def main() -> int:
    settings = load()
    if not (settings.google_client_id and settings.google_client_secret):
        print(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in harness/.env", file=sys.stderr
        )
        return 2

    redirect = urlparse(settings.google_redirect_uri)
    if redirect.hostname not in ("localhost", "127.0.0.1") or not redirect.port:
        print(
            f"GOOGLE_REDIRECT_URI must be a localhost URL with a port, got {settings.google_redirect_uri}",
            file=sys.stderr,
        )
        return 2

    flow = OAuth2Flow(
        GOOGLE,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
    )
    request = flow.authorize(GOOGLE_SCOPES)
    print("Open this in a browser and sign in with the SECONDARY account:\n")
    print(request.url)
    print(f"\nWaiting for the redirect on {settings.google_redirect_uri} ...")
    params = wait_for_callback(redirect.hostname or "localhost", redirect.port)

    if "error" in params:
        print(f"Google returned an error: {params['error']}", file=sys.stderr)
        return 1
    if not states_match(request.state, params.get("state", "")):
        print("state mismatch — start over", file=sys.stderr)
        return 1

    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)
    if not grant.refresh_token:
        print(
            "No refresh token was returned. Revoke the app's access at "
            "myaccount.google.com/permissions and run again so consent is re-prompted.",
            file=sys.stderr,
        )
        return 1

    print("\nAdd this line to harness/.env:\n")
    print(f"GOOGLE_REFRESH_TOKEN={grant.refresh_token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
