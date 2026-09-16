"""
The world: the accounts as seen by the harness, not by the model.

Seeding fixtures, reading state back to grade a run, and tearing fixtures down
all happen here, over raw httpx, with the same credentials the arms use. It is
kept separate from Charter on purpose — the grader must not share a code path
with the thing it grades.
"""

from __future__ import annotations

from charter.packs import github as github_pack
from charter.packs import shopify as shopify_pack
from charter.packs import stripe as stripe_pack

from charter_harness.settings import GOOGLE_PACKS, Wiring
from charter_harness.world._http import Http, WorldError, eventually
from charter_harness.world.firecrawl import Firecrawl
from charter_harness.world.github import GitHub
from charter_harness.world.google import Calendar, Docs, Drive, Gmail, Sheets
from charter_harness.world.linear import Linear
from charter_harness.world.shopify import Shopify
from charter_harness.world.slack import Slack
from charter_harness.world.stripe import Stripe

__all__ = ["World", "WorldError", "eventually"]


class World:
    """Lazily-built clients, one per provider, bound to the run's credentials."""

    def __init__(self, wiring: Wiring) -> None:
        self.wiring = wiring
        self.settings = wiring.settings
        self._http: dict[str, Http] = {}
        self._gmail: Gmail | None = None
        self._calendar: Calendar | None = None
        self._sheets: Sheets | None = None
        self._docs: Docs | None = None
        self._drive: Drive | None = None
        self._stripe: Stripe | None = None
        self._github: GitHub | None = None
        self._linear: Linear | None = None
        self._shopify: Shopify | None = None
        self._slack: Slack | None = None
        self._firecrawl: Firecrawl | None = None

    # ---- transports

    def _google_http(self, base_url: str) -> Http:
        if base_url not in self._http:
            wiring = self.wiring

            async def headers() -> dict[str, str]:
                return {"Authorization": f"Bearer {await wiring.google_token()}"}

            self._http[base_url] = Http(base_url, headers)
        return self._http[base_url]

    def _static_http(self, base_url: str, static: dict[str, str]) -> Http:
        if base_url not in self._http:

            async def headers() -> dict[str, str]:
                return dict(static)

            self._http[base_url] = Http(base_url, headers)
        return self._http[base_url]

    async def aclose(self) -> None:
        for http in self._http.values():
            await http.aclose()

    # ---- providers

    @property
    def gmail(self) -> Gmail:
        if self._gmail is None:
            self.settings.require("gmail")
            self._gmail = Gmail(self._google_http("https://gmail.googleapis.com/"))
        return self._gmail

    @property
    def calendar(self) -> Calendar:
        if self._calendar is None:
            self.settings.require("gcalendar")
            self._calendar = Calendar(self._google_http("https://www.googleapis.com/"))
        return self._calendar

    @property
    def sheets(self) -> Sheets:
        if self._sheets is None:
            self.settings.require("gsheets")
            self._sheets = Sheets(self._google_http("https://sheets.googleapis.com/"))
        return self._sheets

    @property
    def docs(self) -> Docs:
        if self._docs is None:
            self.settings.require("gdocs")
            self._docs = Docs(self._google_http("https://docs.googleapis.com/"))
        return self._docs

    @property
    def drive(self) -> Drive:
        if self._drive is None:
            self.settings.require(*GOOGLE_PACKS)
            self._drive = Drive(self._google_http("https://www.googleapis.com/"))
        return self._drive

    @property
    def stripe(self) -> Stripe:
        if self._stripe is None:
            self.settings.require("stripe")
            self._stripe = Stripe(
                self._static_http(
                    "https://api.stripe.com/",
                    {
                        "Authorization": f"Bearer {self.settings.stripe_api_key}",
                        "Stripe-Version": stripe_pack.API_VERSION,
                    },
                )
            )
        return self._stripe

    @property
    def github(self) -> GitHub:
        if self._github is None:
            self.settings.require("github")
            self._github = GitHub(
                self._static_http(
                    "https://api.github.com/",
                    {"Authorization": f"Bearer {self.settings.github_token}", **github_pack.GITHUB_HEADERS},
                ),
                owner=self.settings.github_owner or "",
                sandbox_repo=self.settings.github_sandbox_repo,
            )
        return self._github

    @property
    def linear(self) -> Linear:
        if self._linear is None:
            self.settings.require("linear")
            self._linear = Linear(
                self._static_http("https://api.linear.app/", {"Authorization": self.settings.linear_api_key or ""}),
                team_key=self.settings.linear_team_key or "",
            )
        return self._linear

    @property
    def shopify(self) -> Shopify:
        if self._shopify is None:
            self.settings.require("shopify")
            self._shopify = Shopify(
                self._static_http(
                    f"https://{self.settings.shopify_shop}/",
                    {"X-Shopify-Access-Token": self.settings.shopify_access_token or ""},
                ),
                shop=self.settings.shopify_shop or "",
                api_version=shopify_pack.API_VERSION,
            )
        return self._shopify

    @property
    def slack(self) -> Slack:
        if self._slack is None:
            self.settings.require("slack")
            self._slack = Slack(
                self._static_http("https://slack.com/api/", {"Authorization": f"Bearer {self.settings.slack_bot_token}"}),
                channel_name=self.settings.slack_channel,
            )
        return self._slack

    @property
    def firecrawl(self) -> Firecrawl:
        if self._firecrawl is None:
            self.settings.require("firecrawl")
            self._firecrawl = Firecrawl(
                self._static_http(
                    "https://api.firecrawl.dev/v2/", {"Authorization": f"Bearer {self.settings.firecrawl_api_key}"}
                )
            )
        return self._firecrawl
