"""
Is the harness ready to run? One cheap live call per provider.

Every scenario runs against a real account, so a missing or expired credential
should surface here in a few seconds rather than three scenarios into a campaign.
Each check makes the smallest call that proves the credential works, and anything
it creates it also deletes.

    cd oss/harness
    .venv/bin/python scripts/check_auth.py

Exits 0 when every configured provider answers, 1 when any fails, 2 when a
provider is not configured at all. Reads ``harness/.env`` (see AGENTS.md: that is
a different file from ``oss/.env``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from charter_harness.scenarios.registry import all_scenarios
from charter_harness.settings import PROVIDERS, REQUIRED_VARS, load, wire_packs
from charter_harness.world import World

OK, FAIL, SKIP = "ok", "FAIL", "--"


async def check_gmail(w: World) -> str:
    me = await w.gmail.http.json("GET", "gmail/v1/users/me/profile")
    return f"{me['emailAddress']} ({me['messagesTotal']} messages)"


async def check_gcalendar(w: World) -> str:
    data = await w.calendar.http.json("GET", "calendar/v3/users/me/calendarList")
    return f"{len(data.get('items', []))} calendars"


async def check_gsheets(w: World) -> str:
    sheet = await w.sheets.http.json("POST", "v4/spreadsheets", json={"properties": {"title": "harness-authcheck"}})
    await w.drive.file_delete(sheet["spreadsheetId"])
    return "create and delete"


async def check_gdocs(w: World) -> str:
    # Also proves the Drive API is enabled, which calendar_to_doc and pr_to_doc
    # need inside observe() and not merely for teardown.
    doc = await w.docs.http.json("POST", "v1/documents", json={"title": "harness-authcheck"})
    await w.drive.file_delete(doc["documentId"])
    found = await w.drive.files_list(name_contains="harness-authcheck")
    return f"create and delete, drive search returns {len(found)}"


async def check_gdrive(w: World) -> str:
    # gdrive is in PROVIDERS but had no check, so a Drive-scope failure surfaced
    # as a KeyError here and as a dead scenario later.
    about = await w.drive.http.json("GET", "drive/v3/about", params={"fields": "user"})
    return f"{about['user']['emailAddress']}"


async def check_stripe(w: World) -> str:
    balance = await w.stripe.http.json("GET", "v1/balance")
    if balance.get("livemode"):
        raise RuntimeError("STRIPE_API_KEY is a LIVE key")
    return "test mode"


async def check_github(w: World) -> str:
    repo = await w.github.ensure_sandbox()
    # firecrawl_to_linear scrapes a blob in this repo anonymously.
    visibility = "private (BREAKS firecrawl_to_linear)" if repo["private"] else "public"
    return f"{repo['full_name']}, {visibility}"


async def check_linear(w: World) -> str:
    return f"team {w.linear.team_key} -> {await w.linear.team_id()}"


async def check_shopify(w: World) -> str:
    return f"location {await w.shopify.location_id()}"


async def check_slack(w: World) -> str:
    ident = await w.slack.call("auth.test")
    channel = await w.slack.channel_id()
    members = await w.slack.call("conversations.members", params={"channel": channel, "limit": 100})
    if ident["user_id"] not in members.get("members", []):
        raise RuntimeError(f"bot is not a member of #{w.settings.slack_channel}")
    return f"{ident['user']} in #{w.settings.slack_channel} ({channel})"


async def check_firecrawl(w: World) -> str:
    url = w.github.blob_url(path="README.md", branch=await w.github.default_branch())
    page = await w.firecrawl.scrape_markdown(url + "?plain=1")
    return f"scraped the sandbox repo, {len(page.get('markdown', ''))} chars"


async def check_tavily(w: World) -> str:
    # `usage` rather than `search`: it proves the key and spends no credits,
    # which is the rule the rest of this file follows.
    from charter.packs import tavily

    usage = next(t for t in tavily.TOOLS if t.name == "usage")
    data = await usage.ainvoke({})
    key = (data or {}).get("key", {}) if isinstance(data, dict) else {}
    return f"usage endpoint ok ({key.get('usage', '?')} calls this cycle)"


CHECKS: dict[str, Callable[[World], Awaitable[str]]] = {
    "gmail": check_gmail,
    "gcalendar": check_gcalendar,
    "gsheets": check_gsheets,
    "gdocs": check_gdocs,
    "gdrive": check_gdrive,
    "stripe": check_stripe,
    "github": check_github,
    "linear": check_linear,
    "shopify": check_shopify,
    "slack": check_slack,
    "firecrawl": check_firecrawl,
    "tavily": check_tavily,
}


async def main() -> int:
    settings = load()
    available = settings.available()
    world = World(wire_packs(settings, providers=available))

    failures: list[str] = []
    unconfigured: list[str] = []

    for name in sorted(PROVIDERS):
        if name not in available:
            missing = ", ".join(v for v in REQUIRED_VARS[name] if not settings.raw.get(v))
            print(f"  {SKIP:4} {name:10} not configured; set {missing}")
            unconfigured.append(name)
            continue
        try:
            print(f"  {OK:4} {name:10} {await CHECKS[name](world)}")
        except Exception as exc:  # noqa: BLE001 - one line per provider is the point
            print(f"  {FAIL:4} {name:10} {str(exc).splitlines()[0][:150]}")
            failures.append(name)

    await world.aclose()

    instances = all_scenarios(variants=True)
    runnable = [s for s in instances if set(s.requires) <= available]
    print(f"\n{len(runnable)}/{len(instances)} scenario instances runnable, {len({s.template for s in runnable})}/16 templates")

    if failures:
        print(f"\nFAILED: {', '.join(failures)}")
        return 1
    if unconfigured:
        print(f"\nNot configured: {', '.join(unconfigured)}")
        return 2
    print("\nEvery provider answered. The harness is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
