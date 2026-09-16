"""
Credentials, and the one place they are turned into configured packs.

Everything the harness needs to talk to a real account arrives through the
environment (``.env`` beside ``pyproject.toml`` is loaded if present). Nothing
here is read ambiently by the rest of the harness: :func:`load` returns a
:class:`Settings`, :func:`wire_packs` turns it into configured Charter packs and
a :class:`Wiring` the raw arm and the world clients draw the *same* credentials
from. Same tokens on every arm is one of the fairness rules, and this module is
where it is made true.

Two refusals live here on purpose. A Stripe key that is not a test key is
rejected before anything is configured, and a missing provider fails with the
exact variable names to set rather than a 401 three scenarios in.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from charter.auth import CredentialProvider, OAuth2Client, OAuth2Server
from dotenv import dotenv_values

__all__ = [
    "PROVIDERS",
    "GOOGLE_PACKS",
    "GOOGLE_SCOPES",
    "GOOGLE",
    "Settings",
    "Wiring",
    "load",
    "wire_packs",
    "MissingCredentials",
]

# The providers the harness runs against.
PROVIDERS: frozenset[str] = frozenset(
    {
        "gmail", "gcalendar", "gsheets", "gdocs", "gdrive",
        "stripe", "github", "linear", "shopify", "slack", "firecrawl", "tavily",
    }
)
GOOGLE_PACKS = ("gmail", "gcalendar", "gsheets", "gdocs", "gdrive")

# One consent covers all five Google packs. `calendar` rather than the packs'
# narrower `calendar.events` because `calendar_list_list` needs it. `drive`
# covers the Drive pack and also teardown of spreadsheets and documents the
# seed made.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)

# Which environment variables each provider needs. The error message for a
# missing provider is built from this, so it names exactly what to set.
REQUIRED_VARS: dict[str, tuple] = {
    "gmail": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "gcalendar": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "gsheets": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "gdocs": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "gdrive": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
    "stripe": ("STRIPE_API_KEY",),
    "github": ("GITHUB_TOKEN",),
    "linear": ("LINEAR_API_KEY", "LINEAR_TEAM_KEY"),
    "shopify": ("SHOPIFY_SHOP", "SHOPIFY_ACCESS_TOKEN"),
    "slack": ("SLACK_BOT_TOKEN",),
    "firecrawl": ("FIRECRAWL_API_KEY",),
    "tavily": ("TAVILY_API_KEY",),
}


class MissingCredentials(RuntimeError):
    """A scenario needs a provider the environment does not configure."""


def default_env_file() -> Path:
    """``harness/.env``, or wherever ``CHARTER_HARNESS_ENV`` points."""
    override = os.environ.get("CHARTER_HARNESS_ENV")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".env"


@dataclass(frozen=True)
class Settings:
    fireworks_api_key: str | None = None

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:10002/auth/provider/callback"
    google_refresh_token: str | None = None

    stripe_api_key: str | None = None

    github_token: str | None = None
    github_owner: str | None = None
    github_sandbox_repo: str = "harness-sandbox"

    linear_api_key: str | None = None
    linear_team_key: str | None = None

    shopify_shop: str | None = None
    shopify_access_token: str | None = None

    slack_bot_token: str | None = None
    slack_channel: str = "harness"

    firecrawl_api_key: str | None = None

    tavily_api_key: str | None = None

    timezone: str = "Europe/Paris"

    raw: dict[str, str] = field(default_factory=dict, repr=False)

    def available(self) -> frozenset[str]:
        """The providers whose variables are all set."""
        return frozenset(p for p in PROVIDERS if all(self.raw.get(v) for v in REQUIRED_VARS[p]))

    def require(self, *providers: str) -> None:
        missing = {
            p: [v for v in REQUIRED_VARS[p] if not self.raw.get(v)]
            for p in providers
            if p not in self.available()
        }
        if missing:
            lines = [f"  {p}: set {', '.join(vs)}" for p, vs in missing.items()]
            raise MissingCredentials(
                "The harness is missing credentials for "
                + ", ".join(sorted(missing))
                + ":\n"
                + "\n".join(lines)
                + f"\n(read from {default_env_file()} and the environment)"
            )


def load(env_file: Path | None = None) -> Settings:
    """Read ``.env`` and build Settings.

    A non-empty environment variable wins over the file. An *empty* one does not:
    ``set -a; source .env`` in a shell before a key was filled in leaves
    ``FIRECRAWL_API_KEY=`` exported, and that blank must not shadow the value
    that has since been written to the file.
    """
    path = env_file or default_env_file()
    file_values: dict[str, str | None] = dotenv_values(path) if path.exists() else {}

    def get(name: str) -> str | None:
        value = os.environ.get(name, "").strip() or (file_values.get(name) or "").strip()
        return value or None

    raw = {name: v for name in {v for vs in REQUIRED_VARS.values() for v in vs} if (v := get(name))}

    stripe_key = get("STRIPE_API_KEY")
    if stripe_key and not stripe_key.startswith(("sk_test_", "rk_test_")):
        # The harness issues refunds and creates customers. That is fine against a
        # sandbox and unacceptable against a live account, so a live-looking key is
        # refused here rather than trusted to a scenario author's care.
        raise MissingCredentials(
            "STRIPE_API_KEY must be a test-mode key (sk_test_... / rk_test_...); refusing to run "
            "the harness against a live Stripe account."
        )

    return Settings(
        fireworks_api_key=get("FIREWORKS_API_KEY"),
        google_client_id=get("GOOGLE_CLIENT_ID"),
        google_client_secret=get("GOOGLE_CLIENT_SECRET"),
        google_redirect_uri=get("GOOGLE_REDIRECT_URI") or "http://localhost:10002/auth/provider/callback",
        google_refresh_token=get("GOOGLE_REFRESH_TOKEN"),
        stripe_api_key=stripe_key,
        github_token=get("GITHUB_TOKEN"),
        github_owner=get("GITHUB_OWNER"),
        github_sandbox_repo=get("GITHUB_SANDBOX_REPO") or "harness-sandbox",
        linear_api_key=get("LINEAR_API_KEY"),
        linear_team_key=get("LINEAR_TEAM_KEY"),
        shopify_shop=get("SHOPIFY_SHOP"),
        shopify_access_token=get("SHOPIFY_ACCESS_TOKEN"),
        slack_bot_token=get("SLACK_BOT_TOKEN"),
        slack_channel=(get("SLACK_CHANNEL") or "harness").lstrip("#"),
        firecrawl_api_key=get("FIRECRAWL_API_KEY"),
        tavily_api_key=get("TAVILY_API_KEY"),
        timezone=get("HARNESS_TIMEZONE") or "Europe/Paris",
        raw=raw,
    )


@dataclass
class Wiring:
    """The configured credentials, in the shapes the raw arm and the world need.

    The Charter packs are configured as a side effect of :func:`wire_packs`; this
    object is what everything *else* uses so that no second copy of a token is
    ever read from the environment.
    """

    settings: Settings
    google: CredentialProvider | None = None

    async def google_token(self) -> str:
        if self.google is None:
            raise MissingCredentials("Google is not configured")
        return (await self.google.get_credentials("google")).token

    @property
    def shopify_graphql_url(self) -> str:
        from charter.packs import shopify

        return f"https://{self.settings.shopify_shop}/admin/api/{shopify.API_VERSION}/graphql.json"


def wire_packs(settings: Settings, providers: frozenset[str] | None = None) -> Wiring:
    """Configure every available (or requested) pack from ``settings``.

    Returns the :class:`Wiring` the other layers share. Packs whose credentials
    are absent are left unconfigured; ``settings.require(...)`` is the check to
    run before a scenario that needs them.
    """
    wanted = providers if providers is not None else settings.available()
    wiring = Wiring(settings=settings)

    if wanted & set(GOOGLE_PACKS):
        settings.require(*(p for p in GOOGLE_PACKS if p in wanted))
        assert settings.google_client_id and settings.google_client_secret
        # One client, one token cache, five packs: a refresh made for gmail is
        # the access token gsheets sends a second later.
        wiring.google = OAuth2Client(
            GOOGLE,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            refresh_token=settings.google_refresh_token,
        )
        from charter.packs import gcalendar, gdocs, gdrive, gmail, gsheets

        for pack in (gmail, gcalendar, gsheets, gdocs, gdrive):
            pack.configure(wiring.google)

    if "stripe" in wanted:
        settings.require("stripe")
        from charter.packs import stripe

        stripe.configure(api_key=settings.stripe_api_key or "")

    if "github" in wanted:
        settings.require("github")
        from charter.auth import StaticTokenProvider
        from charter.packs import github

        github.configure(StaticTokenProvider(settings.github_token or ""))

    if "linear" in wanted:
        settings.require("linear")
        from charter.packs import linear

        linear.configure(api_key=settings.linear_api_key or "")

    if "shopify" in wanted:
        settings.require("shopify")
        from charter.packs import shopify

        shopify.configure(
            shop=settings.shopify_shop or "", access_token=settings.shopify_access_token or ""
        )

    if "slack" in wanted:
        settings.require("slack")
        from charter.auth import StaticTokenProvider
        from charter.packs import slack

        slack.configure(StaticTokenProvider(settings.slack_bot_token or ""))

    if "firecrawl" in wanted:
        settings.require("firecrawl")
        from charter.packs import firecrawl

        firecrawl.configure(api_key=settings.firecrawl_api_key or "")

    if "tavily" in wanted:
        settings.require("tavily")
        from charter.packs import tavily

        tavily.configure(api_key=settings.tavily_api_key or "")

    return wiring
