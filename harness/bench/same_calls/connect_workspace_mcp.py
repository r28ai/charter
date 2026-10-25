"""Give google_workspace_mcp the grant its own sign-in would, for the harness's test account.

The server signs a user in from inside a tool call and keeps the result in
``~/.google_workspace_mcp/credentials/<email>.json``. This runs the same consent with
the same scopes it asks for when started with ``--tools gmail calendar`` (its
``GMAIL_SCOPES``, ``CALENDAR_SCOPES`` and ``BASE_SCOPES``, v2.2.0) through a Desktop
OAuth client, and writes the file it would have written, so the server starts
signed in and every tool behaves as after its own flow.

    .venv/bin/python bench/same_calls/connect_workspace_mcp.py --client ~/Downloads/client_secret_....json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from charter.auth import OAuth2Flow, OAuth2Server, states_match

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)
PORT = 10019
CREDENTIALS = Path.home() / ".google_workspace_mcp" / "credentials"


def _callback() -> dict:
    captured: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            captured.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Connected - you can close this tab.")

        def log_message(self, *_):
            pass

    with HTTPServer(("localhost", PORT), Handler) as server:
        server.handle_request()
    return captured


async def main(client_file: str, expect: str) -> int:
    client = json.loads(Path(client_file).expanduser().read_text())["installed"]
    redirect = f"http://localhost:{PORT}"
    flow = OAuth2Flow(
        GOOGLE,
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        redirect_uri=redirect,
    )
    request = flow.authorize(SCOPES)
    print("Open this and sign in with the test account:\n")
    print(request.url, flush=True)
    params = _callback()
    if not states_match(request.state, params.get("state", "")):
        print("state mismatch")
        return 1
    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)
    async with httpx.AsyncClient() as http:
        email = (
            await http.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {grant.access_token}"},
            )
        ).json()["email"]
    if email != expect:
        print(f"refusing: signed in as {email}, expected {expect}")
        return 1
    CREDENTIALS.mkdir(parents=True, exist_ok=True)
    path = CREDENTIALS / f"{email}.json"
    path.write_text(
        json.dumps(
            {
                "token": grant.access_token,
                "refresh_token": grant.refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "scopes": list(grant.scopes or SCOPES),
                "expiry": grant.expires_at.replace(tzinfo=None).isoformat()
                if grant.expires_at
                else None,
            }
        )
    )
    os.chmod(path, 0o600)
    print(f"wrote credentials for {email}; granted {len(grant.scopes or [])} scopes")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True)
    ap.add_argument("--expect", required=True, help="the test account's address")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.client, a.expect)))
