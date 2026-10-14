# Needs GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET, and `pip install fastapi uvicorn`.
"""A web app where each user connects their own GitHub: connect, act as them, disconnect.

Register an OAuth App with the callback http://localhost:8000/callback, run this, then
open http://localhost:8000/?user=ada
"""

import os
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from charter.auth import (
    OAuth2Flow,
    OAuth2Server,
    Revocation,
    StaticTokenProvider,
    SubjectProvider,
    revoke_token,
    scopes_for,
    states_match,
    use_subject,
)
from charter.packs import github

# GitHub's server, as on https://docs.r28.ai/charter/auth/providers/github
GITHUB = OAuth2Server(
    issuer="https://github.com",
    authorization_endpoint="https://github.com/login/oauth/authorize",
    token_endpoint="https://github.com/login/oauth/access_token",
    token_endpoint_auth_method="client_secret_post",
    revocation=Revocation(
        "https://api.github.com/applications/{client_id}/grant",
        token_type="access_token",
        auth_method="client_secret_basic",
        token_field="access_token",
        http_method="DELETE",
        request_format="json",
        gone_statuses=(404, 422),
    ),
)
if not (os.environ.get("GITHUB_CLIENT_ID") and os.environ.get("GITHUB_CLIENT_SECRET")):
    raise SystemExit(
        "Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET first, from an OAuth App with the "
        "callback http://localhost:8000/callback: https://github.com/settings/applications/new"
    )
CLIENT = {"client_id": os.environ["GITHUB_CLIENT_ID"], "client_secret": os.environ["GITHUB_CLIENT_SECRET"]}  # fmt: skip
flow = OAuth2Flow(GITHUB, **CLIENT, redirect_uri="http://localhost:8000/callback")

db = sqlite3.connect("grants.db")  # your database: one token per user
db.execute("create table if not exists grants (user text primary key, token text)")


def token_of(user: str) -> str | None:
    row = db.execute("select token from grants where user = ?", (user,)).fetchone()
    return row and row[0]


# Every call resolves the token of the user named by use_subject.
users = SubjectProvider(lambda user: StaticTokenProvider(token_of(user) or ""))
github.configure(credential_provider=users)
app = FastAPI()


@app.get("/")
async def home(user: str):
    if not token_of(user):
        return HTMLResponse(f'<a href="/connect?user={user}">Connect GitHub</a>')
    with use_subject(user):
        me = await github.users_get_authenticated.ainvoke({})
    return HTMLResponse(f'Hi {me["login"]}. <a href="/disconnect?user={user}">Disconnect</a>')


@app.get("/connect")
def connect(user: str):
    request = flow.authorize(scopes_for([github.users_get_authenticated]))
    response = RedirectResponse(request.url)
    response.set_cookie("oauth", f"{request.state}:{request.code_verifier}:{user}", httponly=True)
    return response  # a signed session is the production version of this cookie


@app.get("/callback")
async def callback(request: Request, code: str, state: str):
    expected, verifier, user = request.cookies["oauth"].split(":", 2)
    if not states_match(expected, state):
        return HTMLResponse("That link wasn't started here.", status_code=400)
    grant = await flow.exchange(code, code_verifier=verifier, expect_refresh_token=False)
    db.execute("insert or replace into grants values (?, ?)", (user, grant.access_token))
    db.commit()
    return RedirectResponse(f"/?user={user}")


@app.get("/disconnect")
async def disconnect(user: str):
    await revoke_token(GITHUB, access_token=token_of(user), **CLIENT)  # ends it at GitHub
    db.execute("delete from grants where user = ?", (user,))
    db.commit()
    users.forget(user)
    return RedirectResponse(f"/?user={user}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, port=8000)
