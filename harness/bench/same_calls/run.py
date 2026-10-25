"""The same calls through each tool layer: does the layer tell you when it went wrong?

No model is involved. Each case is one call a vendor documents as failing inside a
2xx, as breaking its contract, or as needing wire formatting, and it is sent the
same way through every layer: Charter's pack tool, the API's most popular MCP
server (``servers.py``), and a plain HTTP request, which is what the API itself
does with it. What each layer hands back is classified with a fixed vocabulary:

- **failure inside a 2xx**: ``reported the failure`` (an exception or MCP's
  ``isError``), ``returned the error as data`` (no flag, but the error code is in
  the text the model reads), or ``reported success`` (neither);
- **a call outside the documented contract**: ``refused`` (by the layer or the API,
  with an error) or ``silently accepted`` (a success, with the value clamped,
  ignored or answered with nothing);
- **wire format**: the draft read back through Gmail's own API, ``exact`` or the
  fields that came out wrong.

Every case states the vendor's sentence it rests on. The harness's guard applies:
nothing is sent from the mailbox, Slack writes go to channels the harness made, and
everything a case creates is deleted.

    cd harness && CHARTER_HARNESS_ENV=... .venv/bin/python bench/same_calls/run.py

Writes ``results/bench/same_calls.jsonl`` and ``results/bench/same_calls.md``. The
Google test account's address and the Shopify test store's domain appear in some
layers' replies; the records replace them with ``example.com`` names.
"""

from __future__ import annotations

import asyncio
import base64
import email
import email.header
import email.policy
import json
import sys
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "src"))

from charter import CharterError, ToolValidationError  # noqa: E402
from charter.packs import gcalendar, github, gmail, linear, shopify, slack, stripe  # noqa: E402
from mcp_layer import Result, call, connect  # noqa: E402
from servers import _env as _env_value  # noqa: E402
from servers import servers  # noqa: E402

from charter_harness.settings import load, wire_packs  # noqa: E402

OUT = HERE.parent.parent / "results" / "bench"
HARNESS_CHANNEL = "C0C03BZL5TQ"
ARCHIVED_CHANNEL = "C0C0YQJHLNB"  # live-lv94ed1d, made and archived by the harness's live suite
MISSING_UUID = "00000000-0000-4000-8000-000000000000"
PUBLIC_REPO = ("octocat", "Hello-World")  # read-only, and it has more than 100 issues


@dataclass
class Outcome:
    flagged: bool
    text: str
    refused_locally: bool = False
    data: Any = None


@dataclass
class Case:
    id: str
    api: str
    kind: str  # "failure", "contract" or "wire"
    doc: str
    layers: dict[str, Callable[[Any, dict], Awaitable[Outcome]]]
    error_codes: tuple[str, ...] = ()
    setup: Callable[[Any], Awaitable[dict]] | None = None
    teardown: Callable[[Any, dict], Awaitable[None]] | None = None
    judge: Callable[[Any, dict, Outcome], Awaitable[str]] | None = None
    note: str = ""


# -----------------------------------------------------------------------------
# Layers
# -----------------------------------------------------------------------------


async def charter_call(tool, args: dict) -> Outcome:
    try:
        out = await tool.ainvoke(args)
    except ToolValidationError as exc:
        return Outcome(True, str(exc), refused_locally=True)
    except CharterError as exc:
        return Outcome(True, str(exc))
    return Outcome(False, json.dumps(out, default=str)[:4000], data=out)


async def mcp_call(ctx, server: str, tool: str, args: dict) -> Outcome:
    session = await ctx.session(server)
    result: Result = await call(session, tool, args)
    return Outcome(result.is_error, result.text[:4000], data=result.text)


COMPOSIO = "https://backend.composio.dev/api/v3/tools/execute"


async def composio_call(ctx, tool: str, arguments: dict) -> Outcome:
    """A Composio tool, executed by Composio's servers for the benchmark's connected
    Gmail account, as its SDK's ``tools.execute`` does."""
    r = await ctx.http.post(
        f"{COMPOSIO}/{tool}",
        headers={"x-api-key": ctx.composio_key},
        json={
            "connected_account_id": ctx.composio_account,
            "user_id": "charter-benchmark",
            "arguments": arguments,
            "version": "latest",
        },
        timeout=120,
    )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    flagged = r.status_code >= 400 or not body.get("successful", False)
    ctx.composio_versions.add(str(body.get("version") or body.get("data", {}).get("version") or ""))
    return Outcome(flagged, json.dumps(body)[:4000] if body else r.text[:4000], data=body)


async def raw_call(ctx, method: str, url: str, **kw) -> Outcome:
    r = await ctx.http.request(method, url, **kw)
    return Outcome(r.status_code >= 400, r.text[:4000], data=r)


def _rest(ctx, api: str) -> dict[str, str]:
    return ctx.headers[api]


# -----------------------------------------------------------------------------
# Context
# -----------------------------------------------------------------------------


class Context:
    def __init__(
        self,
        stack: AsyncExitStack,
        http: httpx.AsyncClient,
        headers: dict,
        shopify_url: str = "",
    ) -> None:
        self.stack = stack
        self.http = http
        self.headers = headers
        self.shopify_url = shopify_url
        self.sessions: dict[str, Any] = {}
        self.servers = servers(
            [HARNESS_CHANNEL, ARCHIVED_CHANNEL],
            shopify=(headers["shopify"]["X-Shopify-Access-Token"], shopify_url.split("/")[2])
            if shopify_url
            else None,
        )
        self.unavailable: dict[str, str] = {}
        self.composio_key = _composio("COMPOSIO_API_KEY")
        self.composio_account = _composio("COMPOSIO_BENCH_ACCOUNT")
        self.composio_versions: set[str] = set()

    async def session(self, name: str):
        if name in self.unavailable:
            raise RuntimeError(self.unavailable[name])
        if name not in self.sessions:
            try:
                self.sessions[name] = await self.stack.enter_async_context(
                    connect(self.servers[name])
                )
            except BaseException as exc:  # a server that will not start is recorded, not fatal
                self.unavailable[name] = f"{type(exc).__name__}: {str(exc)[:200]}"
                raise RuntimeError(self.unavailable[name]) from None
        return self.sessions[name]


def _composio(name: str) -> str:
    from servers import _env

    return _env(name)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


async def deleted_slack_message(ctx) -> dict:
    h = _rest(ctx, "slack")
    posted = (
        await ctx.http.post(
            "https://slack.com/api/chat.postMessage",
            headers=h,
            json={"channel": HARNESS_CHANNEL, "text": "[charter-bench] deploy 2.3.1 finished"},
        )
    ).json()
    await ctx.http.post(
        "https://slack.com/api/chat.delete",
        headers=h,
        json={"channel": HARNESS_CHANNEL, "ts": posted["ts"]},
    )
    return {"ts": posted["ts"]}


async def reply_target(ctx) -> dict:
    """The newest message in the test inbox, to draft a reply to."""
    h = _rest(ctx, "google")
    listing = (
        await ctx.http.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=h,
            params={"maxResults": 1, "labelIds": "INBOX"},
        )
    ).json()
    message = (
        await ctx.http.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{listing['messages'][0]['id']}",
            headers=h,
            params={"format": "metadata", "metadataHeaders": ["Message-ID", "Subject"]},
        )
    ).json()
    headers = {x["name"].lower(): x["value"] for x in message["payload"]["headers"]}
    return {
        "message_id": message["id"],
        "thread_id": message["threadId"],
        "rfc822_id": headers.get("message-id", ""),
        "subject": headers.get("subject", ""),
        "drafts_before": await _draft_ids(ctx),
    }


async def _draft_ids(ctx) -> set[str]:
    out = (
        await ctx.http.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
            headers=_rest(ctx, "google"),
            params={"maxResults": 100},
        )
    ).json()
    return {d["id"] for d in out.get("drafts", [])}


async def drafts_baseline(ctx) -> dict:
    return {"drafts_before": await _draft_ids(ctx)}


async def delete_new_drafts(ctx, fx: dict) -> None:
    for draft_id in await _draft_ids(ctx) - fx["drafts_before"]:
        await ctx.http.delete(
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}",
            headers=_rest(ctx, "google"),
        )


# -----------------------------------------------------------------------------
# Judges
# -----------------------------------------------------------------------------


def failure_label(case: Case, out: Outcome) -> str:
    if out.flagged:
        return "reported the failure"
    if any(code.lower() in out.text.lower() for code in case.error_codes):
        return "returned the error as data"
    return "reported success"


def contract_label(out: Outcome, accepted: bool) -> str:
    if out.flagged:
        return "refused before sending" if out.refused_locally else "refused"
    return "silently accepted" if accepted else "accepted, as documented"


WANT_TO = "Zoë Müller <zoe.muller@example.com>"
WANT_CC = ["ana.lopez@example.com", "ben.okafor@example.com"]
WANT_BODY = "Café at 3? Déjà vu — see you there ✅"


async def read_new_draft(ctx, fx: dict) -> email.message.EmailMessage | None:
    new = await _draft_ids(ctx) - fx["drafts_before"]
    if len(new) != 1:
        return None
    draft = (
        await ctx.http.get(
            f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{new.pop()}",
            headers=_rest(ctx, "google"),
            params={"format": "raw"},
        )
    ).json()
    fx["draft_thread"] = draft["message"].get("threadId")
    raw = base64.urlsafe_b64decode(draft["message"]["raw"] + "==")
    return email.message_from_bytes(raw, policy=email.policy.default)


def _decoded(value: str | None) -> str:
    return str(email.header.make_header(email.header.decode_header(value or "")))


async def judge_draft(ctx, fx: dict, out: Outcome, *, want: dict[str, Any]) -> str:
    if out.flagged:
        return "refused" + (" before sending" if out.refused_locally else "")
    message = await read_new_draft(ctx, fx)
    if message is None:
        return "no draft found"
    wrong = []
    if "to" in want and _decoded(message["To"]) != want["to"]:
        wrong.append(f"To read back as {_decoded(message['To'])!r}")
    if "cc" in want:
        got = sorted(a.strip() for a in _decoded(message["Cc"]).split(",") if a.strip())
        if got != sorted(want["cc"]):
            wrong.append(f"Cc read back as {got}")
    if "body" in want:
        part = message.get_body(preferencelist=("plain", "html"))
        text = part.get_content().strip() if part else ""
        if want["body"] not in text:
            wrong.append(f"body read back as {text[:80]!r}")
    if "thread" in want:
        if fx.get("draft_thread") != want["thread"]:
            wrong.append("not in the original thread")
        if want["in_reply_to"] not in (message["In-Reply-To"] or ""):
            wrong.append("no In-Reply-To")
        if want["in_reply_to"] not in (message["References"] or ""):
            wrong.append("no References")
    return "exact" if not wrong else "wrong: " + "; ".join(wrong)


# -----------------------------------------------------------------------------
# Cases
# -----------------------------------------------------------------------------


def _slack_h(ctx):
    return _rest(ctx, "slack")


def _google_h(ctx):
    return _rest(ctx, "google")


def _linear_gql(ctx, query: str, variables: dict):
    return raw_call(
        ctx,
        "POST",
        "https://api.linear.app/graphql",
        headers=_rest(ctx, "linear"),
        json={"query": query, "variables": variables},
    )


class NotOffered(Exception):
    """The layer has no way to express the call: the parameter is not in its schema."""


async def not_offered(ctx, fx) -> Outcome:
    raise NotOffered


def _shopify_gql(ctx, query: str, variables: dict):
    return raw_call(
        ctx,
        "POST",
        ctx.shopify_url,
        headers=_rest(ctx, "shopify"),
        json={"query": query, "variables": variables},
    )


async def _sync_token(ctx) -> dict:
    """A real syncToken for the primary calendar, from a full listing."""
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    params: dict[str, Any] = {"maxResults": 2500}
    while True:
        body = (await ctx.http.get(url, headers=_google_h(ctx), params=params)).json()
        if "nextSyncToken" in body:
            return {"sync_token": body["nextSyncToken"]}
        params["pageToken"] = body["nextPageToken"]


SHOPIFY_200 = (
    "'the GraphQL API can return a 200 OK response code in cases that would typically "
    "produce 4xx or 5xx errors in REST' (shopify.dev/docs/api/admin-graphql)"
)
MISSING_PRODUCT = "gid://shopify/Product/1"
MISSING_CUSTOMER = "gid://shopify/Customer/1"

CASES: list[Case] = [
    # ---------------------------------------------------------- failure inside a 2xx
    Case(
        "shopify-update-missing-product",
        "shopify",
        "failure",
        SHOPIFY_200,
        {
            "charter": lambda ctx, fx: charter_call(
                shopify.product_update,
                {
                    "variables": {
                        "product": {"id": MISSING_PRODUCT, "title": "[charter-bench] renamed"}
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "shopify",
                "update-product",
                {"id": MISSING_PRODUCT, "title": "[charter-bench] renamed"},
            ),
            "raw": lambda ctx, fx: _shopify_gql(
                ctx,
                "mutation($product: ProductUpdateInput!) "
                "{ productUpdate(product: $product) { product { id } userErrors { field message } } }",
                {"product": {"id": MISSING_PRODUCT, "title": "[charter-bench] renamed"}},
            ),
        },
        error_codes=("does not exist", "not found", "userErrors"),
    ),
    Case(
        "shopify-update-missing-customer",
        "shopify",
        "failure",
        SHOPIFY_200,
        {
            "charter": lambda ctx, fx: charter_call(
                shopify.customer_update,
                {"variables": {"input": {"id": MISSING_CUSTOMER, "firstName": "[charter-bench]"}}},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx, "shopify", "update-customer", {"id": "1", "firstName": "[charter-bench]"}
            ),
            "raw": lambda ctx, fx: _shopify_gql(
                ctx,
                "mutation($input: CustomerInput!) "
                "{ customerUpdate(input: $input) { customer { id } userErrors { field message } } }",
                {"input": {"id": MISSING_CUSTOMER, "firstName": "[charter-bench]"}},
            ),
        },
        error_codes=("does not exist", "not found", "userErrors"),
    ),
    Case(
        "slack-react-deleted-message",
        "slack",
        "failure",
        "reactions.add, Errors: message_not_found: Message does not exist. "
        "Slack Web API: 'a top-level boolean property ok that indicates success or failure' "
        "(docs.slack.dev/reference/methods/reactions.add, docs.slack.dev/apis/web-api)",
        {
            "charter": lambda ctx, fx: charter_call(
                slack.reactions_add,
                {"channel": HARNESS_CHANNEL, "timestamp": fx["ts"], "name": "white_check_mark"},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "slack",
                "reactions_add",
                {"channel_id": HARNESS_CHANNEL, "timestamp": fx["ts"], "emoji": "white_check_mark"},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "POST",
                "https://slack.com/api/reactions.add",
                headers=_slack_h(ctx),
                json={
                    "channel": HARNESS_CHANNEL,
                    "timestamp": fx["ts"],
                    "name": "white_check_mark",
                },
            ),
        },
        error_codes=("message_not_found",),
        setup=deleted_slack_message,
    ),
    Case(
        "slack-post-archived-channel",
        "slack",
        "failure",
        "chat.postMessage, Errors: is_archived: Channel has been archived "
        "(docs.slack.dev/reference/methods/chat.postMessage)",
        {
            "charter": lambda ctx, fx: charter_call(
                slack.chat_post_message,
                {"channel": ARCHIVED_CHANNEL, "text": "[charter-bench] status: green"},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "slack",
                "conversations_add_message",
                {"channel_id": ARCHIVED_CHANNEL, "payload": "[charter-bench] status: green"},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "POST",
                "https://slack.com/api/chat.postMessage",
                headers=_slack_h(ctx),
                json={"channel": ARCHIVED_CHANNEL, "text": "[charter-bench] status: green"},
            ),
        },
        error_codes=("is_archived",),
    ),
    Case(
        "linear-update-missing-issue",
        "linear",
        "failure",
        "'GraphQL queries can partially succeed with a 200 HTTP status, returning some data "
        "while including errors for failed fields.' (linear.app/developers/graphql)",
        {
            "charter": lambda ctx, fx: charter_call(
                linear.issue_update,
                {"variables": {"id": MISSING_UUID, "input": {"title": "[charter-bench] renamed"}}},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "linear",
                "save_issue",
                {"id": MISSING_UUID, "title": "[charter-bench] renamed"},
            ),
            "raw": lambda ctx, fx: _linear_gql(
                ctx,
                "mutation($id: String!, $input: IssueUpdateInput!) "
                "{ issueUpdate(id: $id, input: $input) { success } }",
                {"id": MISSING_UUID, "input": {"title": "[charter-bench] renamed"}},
            ),
        },
        error_codes=("not found", "Entity not found", "could not find"),
    ),
    Case(
        "linear-comment-missing-issue",
        "linear",
        "failure",
        "'GraphQL queries can partially succeed with a 200 HTTP status' (linear.app/developers/graphql)",
        {
            "charter": lambda ctx, fx: charter_call(
                linear.comment_create,
                {
                    "variables": {
                        "input": {"issueId": MISSING_UUID, "body": "[charter-bench] shipped"}
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "linear",
                "save_comment",
                {"issueId": MISSING_UUID, "body": "[charter-bench] shipped"},
            ),
            "raw": lambda ctx, fx: _linear_gql(
                ctx,
                "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success } }",
                {"input": {"issueId": MISSING_UUID, "body": "[charter-bench] shipped"}},
            ),
        },
        error_codes=("not found", "Entity not found", "could not find"),
    ),
    Case(
        "gmail-update-missing-label",
        "gmail",
        "failure",
        "Not documented: found live on 2026-10-23. A label update for an id that does not "
        "exist answers 200 with the request echoed back, and changes nothing.",
        {
            "charter": lambda ctx, fx: charter_call(
                gmail.labels_update,
                {"id": "Label_999999999", "body": {"name": "charter-bench-renamed"}},
            ),
            # Charter offers both of Gmail's verbs; the server's "update" reads the
            # label first. Both are recorded rather than the one that scores better.
            "charter (labels_patch)": lambda ctx, fx: charter_call(
                gmail.labels_patch,
                {"id": "Label_999999999", "body": {"name": "charter-bench-renamed"}},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "manage_gmail_label",
                {
                    "action": "update",
                    "label_id": "Label_999999999",
                    "name": "charter-bench-renamed",
                },
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx,
                "GMAIL_PATCH_LABEL",
                {"userId": "me", "id": "Label_999999999", "name": "charter-bench-renamed"},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "PUT",
                "https://gmail.googleapis.com/gmail/v1/users/me/labels/Label_999999999",
                headers=_google_h(ctx),
                json={"name": "charter-bench-renamed"},
            ),
        },
        error_codes=("not found", "notFound", "404"),
        note="undocumented, found live",
    ),
    # ------------------------------------------------------------ outside the contract
    Case(
        "gmail-list-over-max",
        "gmail",
        "contract",
        "users.messages.list maxResults: 'The maximum allowed value for this field is 500.' "
        "(Gmail v1 discovery document)",
        {
            "charter": lambda ctx, fx: charter_call(gmail.messages_list, {"maxResults": 1000}),
            "mcp": lambda ctx, fx: mcp_call(
                ctx, "google", "search_gmail_messages", {"query": "in:anywhere", "page_size": 1000}
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx, "GMAIL_FETCH_EMAILS", {"max_results": 1000, "ids_only": True}
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers=_google_h(ctx),
                params={"maxResults": 1000},
            ),
        },
        note="the API answers with 500 messages and says nothing",
    ),
    Case(
        "calendar-sync-token-with-filter",
        "gcalendar",
        "contract",
        "events.list syncToken: 'There are several query parameters that cannot be specified "
        "together with nextSyncToken to ensure consistency of the client state.' "
        "(Calendar v3 discovery document)",
        {
            "charter": lambda ctx, fx: charter_call(
                gcalendar.events_list,
                {
                    "calendarId": "primary",
                    "syncToken": fx["sync_token"],
                    "timeMin": "2026-01-01T00:00:00Z",
                },
            ),
            "mcp": not_offered,
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=_google_h(ctx),
                params={"syncToken": fx["sync_token"], "timeMin": "2026-01-01T00:00:00Z"},
            ),
        },
        setup=_sync_token,
        note="the API refuses it itself, with 400: a control",
    ),
    Case(
        "calendar-empty-window",
        "gcalendar",
        "contract",
        "events.list timeMax: 'If timeMin is set, timeMax must be greater than timeMin.' "
        "(Calendar v3 discovery document)",
        {
            "charter": lambda ctx, fx: charter_call(
                gcalendar.events_list,
                {
                    "calendarId": "primary",
                    "timeMin": "2026-12-01T00:00:00Z",
                    "timeMax": "2026-01-01T00:00:00Z",
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "get_events",
                {"time_min": "2026-12-01T00:00:00Z", "time_max": "2026-01-01T00:00:00Z"},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=_google_h(ctx),
                params={"timeMin": "2026-12-01T00:00:00Z", "timeMax": "2026-01-01T00:00:00Z"},
            ),
        },
        note="the API answers 200 with no events",
    ),
    Case(
        "calendar-over-max",
        "gcalendar",
        "contract",
        "events.list maxResults: 'The page size can never be larger than 2500 events.' "
        "(Calendar v3 discovery document)",
        {
            "charter": lambda ctx, fx: charter_call(
                gcalendar.events_list, {"calendarId": "primary", "maxResults": 5000}
            ),
            "mcp": lambda ctx, fx: mcp_call(ctx, "google", "get_events", {"max_results": 5000}),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                headers=_google_h(ctx),
                params={"maxResults": 5000},
            ),
        },
    ),
    Case(
        "github-page-over-max",
        "github",
        "contract",
        "List repository issues, per_page: 'The number of results per page (max 100).' "
        "(docs.github.com/rest/issues/issues#list-repository-issues)",
        {
            "charter": lambda ctx, fx: charter_call(
                github.issues_list_for_repo,
                {"owner": PUBLIC_REPO[0], "repo": PUBLIC_REPO[1], "state": "all", "perPage": 500},
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "github",
                "list_issues",
                {"owner": PUBLIC_REPO[0], "repo": PUBLIC_REPO[1], "state": "OPEN", "perPage": 500},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                f"https://api.github.com/repos/{PUBLIC_REPO[0]}/{PUBLIC_REPO[1]}/issues",
                headers=_rest(ctx, "github"),
                params={"state": "all", "per_page": 500},
            ),
        },
        note="the API answers with 100 issues and says nothing",
    ),
    Case(
        "stripe-page-over-max",
        "stripe",
        "contract",
        "List all customers, limit: 'Limit can range between 1 and 100, and the default is 10.' "
        "(docs.stripe.com/api/customers/list)",
        {
            "charter": lambda ctx, fx: charter_call(stripe.customers_list, {"limit": 500}),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "stripe",
                "stripe_api_read",
                {"stripe_api_operation_id": "GetCustomers", "parameters": {"limit": 500}},
            ),
            "raw": lambda ctx, fx: raw_call(
                ctx,
                "GET",
                "https://api.stripe.com/v1/customers",
                headers=_rest(ctx, "stripe"),
                params={"limit": 500},
            ),
        },
    ),
    # ------------------------------------------------------------------- wire format
    Case(
        "gmail-draft-non-ascii-name",
        "gmail",
        "wire",
        "RFC 5322 headers are ASCII; a display name outside it is encoded as RFC 2047 "
        "(datatracker.ietf.org/doc/html/rfc2047). Read back through users.drafts.get.",
        {
            "charter": lambda ctx, fx: charter_call(
                gmail.drafts_create,
                {
                    "body": {
                        "message": {
                            "raw": {
                                "to": [WANT_TO],
                                "subject": "[charter-bench] lunch",
                                "body": "See you.",
                            }
                        }
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "draft_gmail_message",
                {"to": WANT_TO, "subject": "[charter-bench] lunch", "body": "See you."},
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx,
                "GMAIL_CREATE_EMAIL_DRAFT",
                {
                    "recipient_email": WANT_TO,
                    "subject": "[charter-bench] lunch",
                    "body": "See you.",
                },
            ),
        },
        setup=drafts_baseline,
        teardown=delete_new_drafts,
        judge=lambda ctx, fx, out: judge_draft(ctx, fx, out, want={"to": WANT_TO}),
    ),
    Case(
        "gmail-draft-cc",
        "gmail",
        "wire",
        "users.drafts.create stores the message as given; Cc read back through users.drafts.get.",
        {
            "charter": lambda ctx, fx: charter_call(
                gmail.drafts_create,
                {
                    "body": {
                        "message": {
                            "raw": {
                                "to": ["team@example.com"],
                                "cc": WANT_CC,
                                "subject": "[charter-bench] notes",
                                "body": "Notes attached.",
                            }
                        }
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "draft_gmail_message",
                {
                    "to": "team@example.com",
                    "cc": ", ".join(WANT_CC),
                    "subject": "[charter-bench] notes",
                    "body": "Notes attached.",
                },
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx,
                "GMAIL_CREATE_EMAIL_DRAFT",
                {
                    "recipient_email": "team@example.com",
                    "cc": WANT_CC,
                    "subject": "[charter-bench] notes",
                    "body": "Notes attached.",
                },
            ),
        },
        setup=drafts_baseline,
        teardown=delete_new_drafts,
        judge=lambda ctx, fx, out: judge_draft(ctx, fx, out, want={"cc": WANT_CC}),
    ),
    Case(
        "gmail-draft-non-ascii-body",
        "gmail",
        "wire",
        "A body outside ASCII needs a charset and a transfer encoding (RFC 2045). Read back "
        "through users.drafts.get.",
        {
            "charter": lambda ctx, fx: charter_call(
                gmail.drafts_create,
                {
                    "body": {
                        "message": {
                            "raw": {
                                "to": ["team@example.com"],
                                "subject": "[charter-bench] café",
                                "body": WANT_BODY,
                            }
                        }
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "draft_gmail_message",
                {"to": "team@example.com", "subject": "[charter-bench] café", "body": WANT_BODY},
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx,
                "GMAIL_CREATE_EMAIL_DRAFT",
                {
                    "recipient_email": "team@example.com",
                    "subject": "[charter-bench] café",
                    "body": WANT_BODY,
                },
            ),
        },
        setup=drafts_baseline,
        teardown=delete_new_drafts,
        judge=lambda ctx, fx, out: judge_draft(ctx, fx, out, want={"body": WANT_BODY}),
    ),
    Case(
        "gmail-draft-reply-in-thread",
        "gmail",
        "wire",
        "users.drafts.create: 'The requested threadId must be specified on the Message or Draft.Message "
        "... The References and In-Reply-To headers must be set in compliance with the RFC 2822 standard. "
        "The Subject headers must match.' (developers.google.com/workspace/gmail/api/guides/threads)",
        {
            "charter": lambda ctx, fx: charter_call(
                gmail.drafts_create,
                {
                    "body": {
                        "message": {
                            "threadId": fx["thread_id"],
                            "raw": {
                                "to": ["team@example.com"],
                                "subject": "Re: " + fx["subject"],
                                "body": "Thanks, noted.",
                                "in_reply_to": fx["rfc822_id"],
                                "references": fx["rfc822_id"],
                            },
                        }
                    }
                },
            ),
            "mcp": lambda ctx, fx: mcp_call(
                ctx,
                "google",
                "draft_gmail_message",
                {
                    "to": "team@example.com",
                    "body": "Thanks, noted.",
                    "thread_id": fx["thread_id"],
                    "in_reply_to": fx["rfc822_id"],
                    "references": fx["rfc822_id"],
                },
            ),
            "composio": lambda ctx, fx: composio_call(
                ctx,
                "GMAIL_CREATE_EMAIL_DRAFT",
                {
                    "recipient_email": "team@example.com",
                    "body": "Thanks, noted.",
                    "subject": "Re: " + fx["subject"],
                    "thread_id": fx["thread_id"],
                },
            ),
        },
        setup=reply_target,
        teardown=delete_new_drafts,
        judge=lambda ctx, fx, out: judge_draft(
            ctx, fx, out, want={"thread": fx["thread_id"], "in_reply_to": fx["rfc822_id"]}
        ),
    ),
]


async def _accepted(case: Case, layer: str, out: Outcome) -> bool:
    """For a contract case, whether a success was a silent clamp, ignore or empty answer."""
    if out.flagged:
        return False
    # Every contract case here asks for something the docs rule out; the API answered
    # it anyway, so any success means the layer passed it through.
    return True


async def run_case(ctx, case: Case) -> list[dict[str, Any]]:
    rows = []
    for layer, fn in case.layers.items():
        fx = await case.setup(ctx) if case.setup else {}
        started = time.time()
        try:
            out = await fn(ctx, fx)
            if case.kind == "failure":
                label = failure_label(case, out)
            elif case.kind == "contract":
                label = contract_label(out, await _accepted(case, layer, out))
            else:
                label = await case.judge(ctx, fx, out)
        except NotOffered:
            out, label = Outcome(False, ""), "not offered"
        except RuntimeError as exc:  # the server would not start
            out, label = Outcome(True, str(exc)), "server unavailable"
        finally:
            if case.teardown:
                await case.teardown(ctx, fx)
        rows.append(
            {
                "case": case.id,
                "api": case.api,
                "kind": case.kind,
                "layer": layer,
                "server": ctx.servers[_server_for(case.api)].name if layer == "mcp" else layer,
                "label": label,
                "flagged": out.flagged,
                "text": out.text[:600],
                "seconds": round(time.time() - started, 2),
                "doc": case.doc,
                "note": case.note,
            }
        )
        print(f"{case.id:32} {layer:8} {label}")
    return rows


def _server_for(api: str) -> str:
    return {"gmail": "google", "gcalendar": "google"}.get(api, api)


async def main(only: str = "") -> None:
    settings = load()
    wiring = wire_packs(
        settings,
        frozenset({"gmail", "gcalendar", "slack", "github", "linear", "stripe", "shopify"}),
    )
    google = f"Bearer {await wiring.google_token()}"
    headers = {
        "google": {"Authorization": google},
        "slack": {"Authorization": f"Bearer {settings.slack_bot_token}"},
        "github": {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        },
        "linear": {"Authorization": settings.linear_api_key},
        "stripe": {"Authorization": f"Bearer {settings.stripe_api_key}"},
        "shopify": {"X-Shopify-Access-Token": await wiring.shopify_token()},
    }
    rows: list[dict[str, Any]] = []
    async with AsyncExitStack() as stack, httpx.AsyncClient(timeout=60) as http:
        ctx = Context(stack, http, headers, shopify_url=wiring.shopify_graphql_url)
        for case in CASES:
            if only and only not in case.id:
                continue
            rows += await run_case(ctx, case)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "same_calls.jsonl"
    # The test accounts' own names appear in some replies; the records keep neither.
    redact = {
        _env_value("GOOGLE_TEST_EMAIL"): "test-account@example.com",
        settings.shopify_shop: "test-store.myshopify.com",
    }
    with out.open("a" if only else "w") as f:
        for row in rows:
            line = json.dumps({**row, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            for real, shown in redact.items():
                line = line.replace(real, shown) if real else line
            f.write(line + "\n")
    print(f"\n{len(rows)} rows -> {out}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else ""))
