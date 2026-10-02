"""Connect your own Google account for every Google pack, once, from a terminal. Needs a
"Desktop app" OAuth client — docs/auth/setup/google.mdx makes one. Run:
    GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python examples/connect_google.py"""

import asyncio
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from charter.auth import OAuth2Flow, OAuth2Server, scopes_for, states_match
from charter.packs import gcalendar, gdocs, gdrive, gforms, gmail, gsheets

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)


def build_flow() -> OAuth2Flow:
    return OAuth2Flow(
        GOOGLE,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        redirect_uri="http://localhost:8765/callback",
    )


def wait_for_callback() -> dict:
    captured: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            captured.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Connected - you can close this tab.")

    with HTTPServer(("localhost", 8765), Callback) as server:
        server.handle_request()
    return captured


async def main() -> None:
    scopes = scopes_for([t for p in (gmail, gcalendar, gsheets, gdocs, gdrive, gforms) for t in p.TOOLS])
    flow = build_flow()
    request = flow.authorize(scopes)
    print(f"Open this in a browser:\n{request.url}")
    params = wait_for_callback()
    if not states_match(request.state, params.get("state", "")):
        raise SystemExit(f"no grant ({params.get('error', 'state mismatch')}) — start over")
    grant = await flow.exchange(params["code"], code_verifier=request.code_verifier)
    for scope in sorted(set(scopes) - set(grant.scopes)):  # a box unticked on the consent screen
        print(f"not granted, so the tools that need it will answer 403: {scope}")
    print(f"export GOOGLE_REFRESH_TOKEN={grant.refresh_token}")


if __name__ == "__main__":
    asyncio.run(main())
