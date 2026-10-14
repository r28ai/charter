# Needs GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REFRESH_TOKEN, from my_google.py.
"""Keep each user's Google grant fresh. Charter refreshes an expired token on its own and
hands you the new one to store, so a restart or another worker starts from it.
"""

import os

from charter.auth import Credentials, OAuth2Client, OAuth2Server, SubjectProvider, use_subject
from charter.packs import gdrive

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
)

# Your database, one row per user. Ada connected earlier, through my_google.py's flow.
grants = {"ada": {"refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"], "access_token": None}}


def client_for(user: str) -> OAuth2Client:
    async def store(credentials: Credentials, refresh_token: str | None) -> None:
        grants[user]["access_token"] = credentials.token
        if refresh_token:  # Google keeps the same one; Linear, Slack and Stripe rotate it
            grants[user]["refresh_token"] = refresh_token
        print(f"  refreshed {user}'s token, good until {credentials.expires_at:%H:%M}, stored")

    return OAuth2Client(
        GOOGLE,
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        refresh_token=grants[user]["refresh_token"],
        on_refresh=store,
    )


gdrive.configure(credential_provider=SubjectProvider(client_for))  # once, at startup

with use_subject("ada"):
    for call in ("first call ", "second call"):
        me = gdrive.about_get.invoke({"fields": "user"})["user"]["emailAddress"]
        print(f"{call}  Drive says this is {me}")
#   refreshed ada's token, good until 15:42, stored
# first call   Drive says this is ada@example.com
# second call  Drive says this is ada@example.com     <- no refresh: the token is still good
