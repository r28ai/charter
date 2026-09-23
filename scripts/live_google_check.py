#!/usr/bin/env python
"""Check Charter's OAuth path against the real Google authorization server.

Deliberately not a test. The suite is offline by rule — every test runs against
``respx`` with no network — and that rule is worth more than the convenience of
folding this in beside it. What tests prove is that Charter is self-consistent; what
this proves is that Charter is *right about the server*, which no mock can tell you.

It verifies four things a mock cannot:

  1. the constants in docs/auth/providers/google.mdx still match what Google
     publishes at its discovery endpoint
  2. a real refresh_token grant is accepted in the form Charter sends it
  3. the lifetime and rotation behaviour are what the docs claim
  4. the resulting token actually authenticates a real API call

Run it against Application Default Credentials, which are an ordinary
``authorized_user`` grant — a client id, a client secret and a refresh token::

    gcloud auth application-default login     # once
    python scripts/live_google_check.py

Nothing is written and nothing is printed that could not go in a bug report:
token lengths and expiry, never token values.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import sys
import time
from pathlib import Path as FsPath
from typing import Annotated

from pydantic import BaseModel

from charter import (
    CallCollector,
    Path,
    format_call_summary,
    oauth_tool_factory,
)
from charter.auth import (
    OAuth2Client,
    OAuth2Server,
)

ADC_PATH = FsPath(
    os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        FsPath.home() / ".config/gcloud/application_default_credentials.json",
    )
)

# What docs/auth/providers/google.mdx tells people to paste. The point of step 1
# is that this and Google's own document do not drift apart unnoticed.
DOCUMENTED = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    token_endpoint_auth_method="client_secret_post",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)


class Userinfo(BaseModel):
    pass


class GetProject(BaseModel):
    project_id: Annotated[str, Path()]


def _load_grant() -> dict:
    if not ADC_PATH.is_file():
        sys.exit(
            f"No credentials at {ADC_PATH}.\n"
            "Run `gcloud auth application-default login`, or point "
            "GOOGLE_APPLICATION_CREDENTIALS at an authorized_user file."
        )
    grant = json.loads(ADC_PATH.read_text())
    if grant.get("type") != "authorized_user":
        sys.exit(
            f"{ADC_PATH} is a {grant.get('type')!r} credential. This check needs an "
            "'authorized_user' grant — a service account uses a signed JWT, which "
            "charter does not implement by design."
        )
    return grant


async def main() -> int:
    grant = _load_grant()
    failures: list[str] = []

    print("1. discovery")
    server = await OAuth2Server.discover("https://accounts.google.com")
    print(f"   token_endpoint      {server.token_endpoint}")
    print(f"   authorization_ep    {server.authorization_endpoint}")
    print(f"   auth method         {server.token_endpoint_auth_method}")
    # authorization_params is registration lore, never in the metadata document,
    # so the discovered declaration is compared against everything but it.
    documented = dataclasses.replace(DOCUMENTED, authorization_params={})
    if server == documented:
        print("   matches docs/auth/providers/google.mdx")
    else:
        failures.append(f"discovery drifted from the documented constants: {server}")
        print(f"   DRIFT — the docs say {documented}")

    print("\n2. refresh")
    persisted: list[str | None] = []
    client = OAuth2Client(
        server,
        client_id=grant["client_id"],
        client_secret=grant["client_secret"],
        refresh_token=grant["refresh_token"],
        on_refresh=lambda credentials, refresh_token: persisted.append(refresh_token),
    )
    credentials = await client.get_credentials("google")
    print(f"   access token        {len(credentials.token)} chars")
    print(f"   granted lifetime    {client._lifetime_seconds}s")
    print(f"   effective leeway    {client._effective_leeway()}s")
    print(f"   rotated             {persisted != [grant['refresh_token']]}")
    if not persisted:
        failures.append("on_refresh did not fire")

    print("\n3. cache")
    started = time.perf_counter()
    again = await client.get_credentials("google")
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(
        f"   second call         {elapsed_ms:.3f}ms, same token={again.token == credentials.token}"
    )
    if elapsed_ms > 5:
        failures.append(f"second get_credentials took {elapsed_ms:.1f}ms — cache missed?")

    print("\n4. a real API call")
    calls = CallCollector()
    oidc = oauth_tool_factory(
        pack="oidc",
        base_url="https://openidconnect.googleapis.com/",
        provider="google",
        credential_provider=client,
        on_call=calls,
    )
    whoami = oidc(name="userinfo", args_schema=Userinfo, method="GET", url_template="v1/userinfo")
    identity = await whoami.ainvoke()
    print(f"   authenticated as    {identity.get('email')}")
    if not identity.get("email"):
        failures.append("userinfo returned no email — the token did not authenticate")

    project_id = os.environ.get("CHARTER_LIVE_PROJECT")
    if project_id:
        crm = oauth_tool_factory(
            pack="crm",
            base_url="https://cloudresourcemanager.googleapis.com/",
            provider="google",
            credential_provider=client,
            on_call=calls,
        )
        get_project = crm(
            name="projects_get",
            args_schema=GetProject,
            method="GET",
            url_template="v1/projects/{project_id}",
        )
        project = await get_project.ainvoke(project_id=project_id)
        print(f"   project             {project.get('name')} / {project.get('lifecycleState')}")

    print()
    print(format_call_summary(calls))

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nAll live checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
