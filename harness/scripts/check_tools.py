"""
Can every tool the campaign will call actually be called?

``check_auth.py`` proves a credential answers. This proves the *capabilities* the
scenario suite exercises, which is a different question: a Google refresh token
minted without ``drive.file`` passes check_auth and then fails three scenarios
into a campaign, and a Shopify token that went inactive last week is
indistinguishable from a working one until something writes.

Every probe calls a real Charter tool through ``tool.ainvoke`` with hardcoded
arguments. **No model is invoked and no inference is billed** - zero Fireworks
calls, zero tokens. Anything a probe creates, it also deletes.

    cd oss/harness
    .venv/bin/python scripts/check_tools.py
    .venv/bin/python scripts/check_tools.py --only gdrive,slack
    .venv/bin/python scripts/check_tools.py --skip-billable

Two probes spend provider credits rather than tokens - ``firecrawl.scrape`` and
``tavily.search``, one call each. ``--skip-billable`` leaves them out.

Exits 0 when every probe passes, 1 when any fails, 2 when the only gaps were
packs that are not configured. Reads ``harness/.env`` (see AGENTS.md: a
different file from ``oss/.env``).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from charter_harness.settings import REQUIRED_VARS, default_env_file, load, wire_packs
from charter_harness.world import World

OK, FAIL, SKIP = "ok", "FAIL", "--"

# One stamp per run, so anything a crashed probe orphans is greppable by eye.
STAMP = f"charter-preflight-{int(time.time())}"

# These spend provider credits per call. One call each, and --skip-billable
# drops them.
BILLABLE = {"firecrawl", "tavily"}


def tool(pack: str, name: str):
    module = importlib.import_module(f"charter.packs.{pack}")
    for candidate in module.TOOLS:
        if candidate.name == name:
            return candidate
    raise LookupError(f"{pack}.{name} does not exist")


async def call(pack: str, name: str, args: dict):
    return await tool(pack, name).ainvoke(args)


def count(result, *keys) -> str:
    """Best-effort item count out of a trimmed response."""
    if isinstance(result, list):
        return str(len(result))
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return str(len(value))
    return "?"


def ident(result, *keys) -> str:
    """The id a probe needs to clean up after itself.

    Raises rather than returning None: a write probe that cannot find the id it
    just created has leaked something, and that must be loud.
    """
    if isinstance(result, dict):
        for key in keys:
            if value := result.get(key):
                return str(value)
    raise RuntimeError(
        f"no {' / '.join(keys)} in response; cannot clean up (got {type(result).__name__})"
    )


# --------------------------------------------------------------------------
# probes - hardcoded arguments, no model in the loop
# --------------------------------------------------------------------------


async def gmail_read(w: World) -> str:
    labels = await call("gmail", "labels_list", {})
    await call("gmail", "messages_list", {"maxResults": 1})
    return f"{count(labels, 'labels')} labels, message list ok"


async def gmail_label_write(w: World) -> str:
    created = await call("gmail", "labels_create", {"body": {"name": STAMP}})
    label_id = ident(created, "id")
    try:
        return f"created and deleted {label_id}"
    finally:
        await call("gmail", "labels_delete", {"id": label_id})


async def gmail_draft_write(w: World) -> str:
    # Compose scope, exercised without ever sending: AGENTS.md is explicit that
    # the harness never sends email.
    #
    # `raw` takes an EmailContent, not RFC822 base64 - the pack owns the
    # semantic-to-wire compilation, so a caller that hand-rolls MIME is refused.
    message = {"raw": {"to": "nobody@example.com", "subject": STAMP, "body": "preflight"}}
    created = await call("gmail", "drafts_create", {"body": {"message": message}})
    draft_id = ident(created, "id")
    try:
        return f"draft {draft_id} created and deleted (nothing sent)"
    finally:
        await call("gmail", "drafts_delete", {"id": draft_id})


async def gcalendar_read(w: World) -> str:
    cals = await call("gcalendar", "calendar_list_list", {})
    await call("gcalendar", "events_list", {"calendarId": "primary", "maxResults": 1})
    return f"{count(cals, 'items')} calendars, event list ok"


async def gcalendar_write(w: World) -> str:
    event = {
        "summary": STAMP,
        "start": {"dateTime": "2030-01-01T00:00:00Z", "timeZone": "UTC"},
        "end": {"dateTime": "2030-01-01T00:30:00Z", "timeZone": "UTC"},
    }
    created = await call("gcalendar", "events_insert", {"calendarId": "primary", "event": event})
    event_id = ident(created, "id")
    try:
        return f"event {event_id} created and deleted"
    finally:
        await call("gcalendar", "events_delete", {"calendarId": "primary", "eventId": event_id})


async def gsheets_write(w: World) -> str:
    created = await call(
        "gsheets", "spreadsheets_create", {"spreadsheet": {"properties": {"title": STAMP}}}
    )
    sheet_id = ident(created, "spreadsheetId")
    try:
        await call(
            "gsheets",
            "spreadsheets_values_update",
            {
                "spreadsheetId": sheet_id,
                "range": "A1:B1",
                "valueInputOption": "RAW",
                "valueRange": {"range": "A1:B1", "values": [["preflight", STAMP]]},
            },
        )
        read = await call(
            "gsheets", "spreadsheets_values_get", {"spreadsheetId": sheet_id, "range": "A1:B1"}
        )
        wrote_back = STAMP in str(read)
        return f"create, write, read back {'ok' if wrote_back else 'MISMATCH'}"
    finally:
        # Deleting a spreadsheet is a Drive call, which is why gsheets scenarios
        # need the Drive scope even though they never name a Drive tool.
        await call("gdrive", "files_delete", {"fileId": sheet_id})


async def gdrive_read(w: World) -> str:
    about = await call("gdrive", "about_get", {"fields": "user,storageQuota"})
    listed = await call("gdrive", "files_list", {"pageSize": 1})
    user = (about or {}).get("user", {}) if isinstance(about, dict) else {}
    return f"{user.get('emailAddress', 'unknown user')}, file list ok ({count(listed, 'files')})"


async def gdrive_write(w: World) -> str:
    # The scope the user asked about by name. A folder needs no upload leg, so
    # this isolates the write permission from the media-upload path.
    created = await call(
        "gdrive",
        "files_create",
        {"file": {"name": STAMP, "mimeType": "application/vnd.google-apps.folder"}},
    )
    file_id = ident(created, "id", "fileId")
    try:
        return f"folder {file_id} created and deleted"
    finally:
        await call("gdrive", "files_delete", {"fileId": file_id})


async def slack_read(w: World) -> str:
    convos = await call("slack", "conversations_list", {"limit": 5})
    return f"{count(convos, 'channels')} conversations visible"


async def slack_write(w: World) -> str:
    channel = await w.slack.channel_id()
    posted = await call(
        "slack", "chat_post_message", {"channel": channel, "text": f"{STAMP} (preflight)"}
    )
    ts = ident(posted, "ts", "messageTs")
    try:
        return f"posted and deleted {ts} in {channel}"
    finally:
        await call("slack", "chat_delete", {"channel": channel, "ts": ts})


async def slack_reactions(w: World) -> str:
    # AGENTS.md flags reactions:read and im:write as scopes the app may lack.
    # add/remove need reactions:write, which is a third scope again.
    channel = await w.slack.channel_id()
    posted = await call(
        "slack", "chat_post_message", {"channel": channel, "text": f"{STAMP} (reaction probe)"}
    )
    ts = ident(posted, "ts", "messageTs")
    try:
        await call(
            "slack",
            "reactions_add",
            {"channel": channel, "timestamp": ts, "name": "white_check_mark"},
        )
        await call(
            "slack",
            "reactions_remove",
            {"channel": channel, "timestamp": ts, "name": "white_check_mark"},
        )
        return "reactions:write ok"
    finally:
        await call("slack", "chat_delete", {"channel": channel, "ts": ts})


async def stripe_read(w: World) -> str:
    balance = await call("stripe", "balance_retrieve", {})
    if isinstance(balance, dict) and balance.get("livemode"):
        raise RuntimeError("STRIPE_API_KEY is a LIVE key")
    await call("stripe", "customers_list", {"limit": 1})
    return "test mode, customer list ok"


async def stripe_write(w: World) -> str:
    # The pack has no customer delete, so teardown goes through the world client
    # - the same route the scenarios use. Without it every run leaked a customer.
    created = await call(
        "stripe", "customers_create", {"name": STAMP, "description": "charter preflight"}
    )
    customer = ident(created, "id")
    try:
        await call(
            "stripe",
            "customers_update",
            {"customer": customer, "description": "charter preflight (updated)"},
        )
        return f"create + update ok, {customer} deleted"
    finally:
        await w.stripe.customer_delete(customer)


async def github_read(w: World) -> str:
    me = await call("github", "users_get_authenticated", {})
    repo = await w.github.ensure_sandbox()
    owner, name = repo["full_name"].split("/", 1)
    await call("github", "branches_list", {"owner": owner, "repo": name, "perPage": 1})
    login = me.get("login", "?") if isinstance(me, dict) else "?"
    visibility = "private (BREAKS firecrawl scenarios)" if repo["private"] else "public"
    return f"{login} on {repo['full_name']}, {visibility}"


async def github_write(w: World) -> str:
    repo = await w.github.ensure_sandbox()
    owner, name = repo["full_name"].split("/", 1)
    created = await call(
        "github",
        "issues_create",
        {"owner": owner, "repo": name, "body": {"title": STAMP, "body": "charter preflight"}},
    )
    number = ident(created, "number", "issueNumber")
    # REST has no issue delete; closing is the idiom and proves the write scope.
    await call(
        "github",
        "issues_update",
        {"owner": owner, "repo": name, "issueNumber": int(number), "body": {"state": "closed"}},
    )
    return f"issue #{number} opened and closed"


async def gdocs_write(w: World) -> str:
    created = await call("gdocs", "documents_create", {"body": {"title": STAMP}})
    doc_id = ident(created, "documentId", "id")
    try:
        await call(
            "gdocs",
            "documents_batch_update",
            {
                "documentId": doc_id,
                "body": {
                    "requests": [{"insertText": {"location": {"index": 1}, "text": f"{STAMP}\n"}}]
                },
            },
        )
        read = await call("gdocs", "documents_get", {"documentId": doc_id})
        return f"create, batch update, read back {'ok' if STAMP in str(read) else 'MISMATCH'}"
    finally:
        # Docs has no delete of its own; teardown is a Drive call, same as sheets.
        await call("gdrive", "files_delete", {"fileId": doc_id})


async def linear_read(w: World) -> str:
    teams = await call("linear", "teams_list", {"variables": {}})
    return f"team {w.linear.team_key}, teams_list ok ({count(teams, 'nodes', 'teams')})"


async def linear_write(w: World) -> str:
    team_id = await w.linear.team_id()
    created = await call(
        "linear",
        "issue_create",
        {
            "variables": {
                "input": {"teamId": team_id, "title": STAMP, "description": "charter preflight"}
            }
        },
    )
    # The pack unwraps the GraphQL envelope, but tolerate either shape.
    payload = created.get("issue", created) if isinstance(created, dict) else created
    issue_id = ident(payload, "id")
    try:
        await call(
            "linear",
            "issue_update",
            {"variables": {"id": issue_id, "input": {"title": f"{STAMP} (updated)"}}},
        )
        return f"issue {issue_id[:8]} created, updated and deleted"
    finally:
        await call("linear", "issue_delete", {"variables": {"id": issue_id}})


async def shopify_read(w: World) -> str:
    shop = await call("shopify", "shop_get", {"variables": {}})
    name = (shop or {}).get("name", "?") if isinstance(shop, dict) else "?"
    return f"shop {name}"


async def shopify_write(w: World) -> str:
    # write_products / write_customers are the scopes both shopify templates
    # need, and the ones a read-only probe would not notice were missing. The
    # pack has no delete for either, so teardown goes through the world client -
    # the same route the scenarios use.
    product = await call(
        "shopify",
        "product_create",
        {"variables": {"product": {"title": STAMP, "tags": ["charter-preflight"]}}},
    )
    product_id = ident(
        product.get("product", product) if isinstance(product, dict) else product, "id"
    )
    try:
        customer = await call(
            "shopify",
            "customer_create",
            # An email (or phone) is required - the pack refuses a customer with
            # neither before Shopify ever sees the call.
            {
                "variables": {
                    "input": {
                        "email": f"{STAMP}@example.com",
                        "firstName": "Charter",
                        "tags": ["charter-preflight"],
                    }
                }
            },
        )
        customer_id = ident(
            customer.get("customer", customer) if isinstance(customer, dict) else customer, "id"
        )
        try:
            return "product and customer created and deleted"
        finally:
            await w.shopify.customer_delete(customer_id)
    finally:
        await w.shopify.product_delete(product_id)


async def firecrawl_scrape(w: World) -> str:
    page = await call(
        "firecrawl", "scrape", {"url": "https://example.com", "formats": ["markdown"]}
    )
    return f"scraped example.com ({len(str(page))} chars back) - 1 credit spent"


async def tavily_search(w: World) -> str:
    found = await call("tavily", "search", {"query": "charter preflight", "maxResults": 1})
    return f"search returned {count(found, 'results')} result(s) - 1 credit spent"


@dataclass(frozen=True)
class Probe:
    pack: str
    capability: str
    tools: tuple[str, ...]
    run: Callable[[World], Awaitable[str]]


PROBES: tuple[Probe, ...] = (
    Probe("gmail", "read", ("labels_list", "messages_list"), gmail_read),
    Probe("gmail", "label write", ("labels_create", "labels_delete"), gmail_label_write),
    Probe("gmail", "draft write", ("drafts_create", "drafts_delete"), gmail_draft_write),
    Probe("gcalendar", "read", ("calendar_list_list", "events_list"), gcalendar_read),
    Probe("gcalendar", "write", ("events_insert", "events_delete"), gcalendar_write),
    Probe(
        "gsheets",
        "create+write+read",
        ("spreadsheets_create", "spreadsheets_values_update", "spreadsheets_values_get"),
        gsheets_write,
    ),
    Probe(
        "gdocs",
        "create+update+read",
        ("documents_create", "documents_batch_update", "documents_get"),
        gdocs_write,
    ),
    Probe("gdrive", "read", ("about_get", "files_list"), gdrive_read),
    Probe("gdrive", "write", ("files_create", "files_delete"), gdrive_write),
    Probe("slack", "read", ("conversations_list",), slack_read),
    Probe("slack", "post write", ("chat_post_message", "chat_delete"), slack_write),
    Probe("slack", "reactions", ("reactions_add", "reactions_remove"), slack_reactions),
    Probe("stripe", "read", ("balance_retrieve", "customers_list"), stripe_read),
    Probe("stripe", "write", ("customers_create", "customers_update"), stripe_write),
    Probe("linear", "read", ("teams_list",), linear_read),
    Probe("linear", "write", ("issue_create", "issue_update", "issue_delete"), linear_write),
    Probe("shopify", "read", ("shop_get",), shopify_read),
    Probe("shopify", "write", ("product_create", "customer_create"), shopify_write),
    Probe("github", "read", ("users_get_authenticated", "branches_list"), github_read),
    Probe("github", "write", ("issues_create", "issues_update"), github_write),
    Probe("firecrawl", "scrape", ("scrape",), firecrawl_scrape),
    Probe("tavily", "search", ("search",), tavily_search),
)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--only", help="comma-separated packs to probe (default: all)")
    parser.add_argument(
        "--skip-billable",
        action="store_true",
        help=f"skip probes that spend credits: {', '.join(sorted(BILLABLE))}",
    )
    args = parser.parse_args()

    wanted = {p.strip() for p in args.only.split(",")} if args.only else {p.pack for p in PROBES}
    if args.skip_billable:
        wanted -= BILLABLE

    settings = load()
    available = set(settings.available())
    world = World(wire_packs(settings, providers=settings.available()))

    failures: list[str] = []
    unconfigured: set[str] = set()
    current = None

    print(f"stamp: {STAMP}\n")
    for probe in PROBES:
        if probe.pack not in wanted:
            continue
        if probe.pack != current:
            current = probe.pack
            print(probe.pack)
        touched = ", ".join(probe.tools)
        if probe.pack not in available:
            missing = ", ".join(REQUIRED_VARS[probe.pack])
            print(
                f"  {SKIP:4} {probe.capability:18} {touched:52} not configured; set {missing} in {default_env_file()}"
            )
            unconfigured.add(probe.pack)
            continue
        try:
            detail = await probe.run(world)
            print(f"  {OK:4} {probe.capability:18} {touched:52} {detail}")
        except Exception as exc:  # noqa: BLE001 - one line per probe is the point
            print(f"  {FAIL:4} {probe.capability:18} {touched:52} {str(exc).splitlines()[0][:120]}")
            failures.append(f"{probe.pack}.{probe.capability}")

    await world.aclose()

    if failures:
        print(f"\nFAILED ({len(failures)}): {', '.join(failures)}")
        print(
            "Fix these before spending inference budget - each one is a scenario that would die mid-campaign."
        )
        return 1
    if unconfigured:
        print(f"\nNot configured: {', '.join(sorted(unconfigured))}")
        return 2
    print("\nEvery probed capability answered. Safe to spend inference budget.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
