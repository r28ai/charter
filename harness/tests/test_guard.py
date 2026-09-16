"""
The guard's decisions, offline, on both arms.

``decide`` is a pure function of (tool name, arguments, run context), so every
rule here is checked without an eval, a model, or a network — including the
rule that the raw arm can only reach the endpoints the Charter arm has tools for.
"""

from __future__ import annotations

import pytest

from charter_harness.arms.charter_arm import CharterArm, model_facing_names
from charter_harness.arms.raw_arm import RawArm, raw_tool_name
from charter_harness.guard import GuardContext, decide
from charter_harness.settings import Settings, Wiring

WIRING = Wiring(settings=Settings(shopify_shop="x.myshopify.com"))


def _ctx(arm: str, packs: list[str], **kwargs) -> GuardContext:
    ctx = GuardContext(arm=arm, github_owner="harness-owner", **kwargs)
    if arm == "charter":
        names = model_facing_names(packs)
        ctx.tool_index = {shown: [pack, tool] for (pack, tool), shown in names.items()}
    else:
        ctx.tool_index = {raw_tool_name(p): [p, raw_tool_name(p)] for p in packs}
    return ctx


# ---------------------------------------------------------------- charter arm


def test_charter_reads_are_approved():
    ctx = _ctx("charter", ["github", "gmail"])
    assert decide("github__repos_get", {"owner": "anyone", "repo": "anything"}, ctx) is None
    assert decide("gmail__messages_list", {"userId": "me"}, ctx) is None


def test_charter_github_writes_must_target_a_sandbox_repo():
    ctx = _ctx("charter", ["github"])
    assert decide("github__issues_create", {"owner": "harness-owner", "repo": "harness-abc", "body": {}}, ctx) is None
    assert decide("github__issues_create", {"owner": "harness-owner", "repo": "charter", "body": {}}, ctx)
    assert decide("github__issues_create", {"owner": "someone-else", "repo": "harness-abc", "body": {}}, ctx)
    assert decide("github__pulls_create", {"owner": "harness-owner", "repo": "real-project", "body": {}}, ctx)
    assert decide("github__issues_create_comment", {"owner": "harness-owner", "repo": "harness-x", "issueNumber": 1, "body": {}}, ctx) is None


def test_charter_calendar_deletes_only_touch_seeded_events():
    ctx = _ctx("charter", ["gcalendar"], owned={"gcalendar.event": ["ev1", "ev2"]})
    assert decide("gcalendar__events_delete", {"calendarId": "primary", "eventId": "ev1"}, ctx) is None
    assert decide("gcalendar__events_delete", {"calendarId": "primary", "eventId": "the-users-dentist"}, ctx)
    assert decide("gcalendar__events_insert", {"calendarId": "primary", "event": {}}, ctx) is None


def test_charter_slack_writes_only_reach_the_harness_channel():
    ctx = _ctx("charter", ["slack"], owned={"slack.channel": ["C123", "harness"]})
    assert decide("slack__chat_post_message", {"channel": "C123", "text": "hi"}, ctx) is None
    assert decide("slack__chat_post_message", {"channel": "#harness", "text": "hi"}, ctx) is None
    assert decide("slack__chat_post_message", {"channel": "C999", "text": "hi"}, ctx)
    assert decide("slack__chat_delete", {"channel": "general", "ts": "1"}, ctx)
    assert decide("slack__conversations_history", {"channel": "C999"}, ctx) is None


def test_charter_send_is_refused_even_if_it_were_registered():
    ctx = _ctx("charter", ["gmail"])
    ctx.tool_index = {**ctx.tool_index, "gmail__messages_send": ["gmail", "messages_send"]}
    assert decide("gmail__messages_send", {"userId": "me", "body": {}}, ctx)


def test_the_submit_tool_is_not_the_guards_business():
    ctx = _ctx("charter", ["gmail"])
    assert decide("submit", {"answer": "done"}, ctx) is None


def test_every_tool_name_is_qualified_by_its_pack():
    """``<pack>__<tool>``, always, after MCP's ``mcp__<server>__<tool>``.

    Unconditionally rather than only where two packs collide: the point is that
    the pack is a reliable substring of *every* name, which is what lets the
    progressive arm's ``+stripe`` filter pick a provider. A property that held
    for some names and not others would not be a property.

    The doubled underscore is what makes it reversible — tool names contain
    single underscores, so ``stripe_products_list`` cannot be split back apart.
    """
    names = model_facing_names(["stripe", "shopify"])
    assert names[("stripe", "products_list")] == "stripe__products_list"
    assert names[("shopify", "products_list")] == "shopify__products_list"
    assert names[("stripe", "balance_retrieve")] == "stripe__balance_retrieve"
    shown = {d.name for d in CharterArm().tools(["stripe", "shopify"], WIRING)}
    assert {"stripe__products_list", "shopify__products_list", "stripe__balance_retrieve"} <= shown
    assert all(name.count("__") == 1 for name in shown), shown


# -------------------------------------------------------------------- raw arm


def test_raw_arm_only_reaches_endpoints_the_pack_declares():
    ctx = _ctx("raw", ["gmail"])
    ok = {"method": "GET", "path": "gmail/v1/users/me/threads", "query": {"maxResults": 5}}
    assert decide("gmail_api", ok, ctx) is None
    # the same path with a scheme and host pasted in front
    assert decide("gmail_api", {"method": "GET", "path": "https://gmail.googleapis.com/gmail/v1/users/me/threads?q=x"}, ctx) is None
    # sending: never
    assert decide("gmail_api", {"method": "POST", "path": "gmail/v1/users/me/messages/send", "body": {}}, ctx)
    # an endpoint no Charter tool has: not on this arm either
    assert decide("gmail_api", {"method": "DELETE", "path": "gmail/v1/users/me/messages/abc"}, ctx)
    assert decide("gmail_api", {"method": "POST", "path": "gmail/v1/users/me/messages/abc/trash"}, ctx)


def test_raw_arm_slack_search_is_withheld_like_the_charter_tool():
    ctx = _ctx("raw", ["slack"], owned={"slack.channel": ["C123"]})
    assert decide("slack_api", {"method": "GET", "path": "conversations.history", "query": {"channel": "C1"}}, ctx) is None
    assert decide("slack_api", {"method": "GET", "path": "search.messages", "query": {"query": "x"}}, ctx)
    assert decide("slack_api", {"method": "POST", "path": "chat.postMessage", "body": {"channel": "C123", "text": "x"}}, ctx) is None
    assert decide("slack_api", {"method": "POST", "path": "chat.postMessage", "body": {"channel": "C777", "text": "x"}}, ctx)


def test_raw_arm_github_writes_are_sandboxed_by_path():
    ctx = _ctx("raw", ["github"])
    assert decide("github_api", {"method": "GET", "path": "repos/torvalds/linux"}, ctx) is None
    assert decide("github_api", {"method": "POST", "path": "repos/harness-owner/harness-42/issues", "body": {"title": "x"}}, ctx) is None
    assert decide("github_api", {"method": "POST", "path": "repos/harness-owner/charter/issues", "body": {"title": "x"}}, ctx)
    assert decide("github_api", {"method": "PATCH", "path": "repos/other/harness-42/issues/1", "body": {}}, ctx)
    # repo creation is not a Charter tool, so the raw arm cannot do it either
    assert decide("github_api", {"method": "POST", "path": "user/repos", "body": {"name": "harness-new"}}, ctx)


def test_raw_arm_calendar_deletes_only_touch_seeded_events():
    ctx = _ctx("raw", ["gcalendar"], owned={"gcalendar.event": ["ev1"]})
    assert decide("gcalendar_api", {"method": "DELETE", "path": "calendar/v3/calendars/primary/events/ev1"}, ctx) is None
    assert decide("gcalendar_api", {"method": "DELETE", "path": "calendar/v3/calendars/primary/events/dentist"}, ctx)


def test_raw_arm_graphql_documents_are_not_inspected():
    ctx = _ctx("raw", ["linear", "shopify"])
    assert decide("linear_graphql", {"query": "mutation { issueDelete(id: \"x\") { success } }"}, ctx) is None
    assert decide("shopify_graphql", {"query": "{ shop { name } }"}, ctx) is None


@pytest.mark.parametrize("pack", ["gmail", "gcalendar", "gsheets", "gdocs", "stripe", "github", "slack", "firecrawl"])
def test_every_charter_endpoint_is_reachable_on_the_raw_arm(pack):
    """The allow-list is derived from the same tools; a filled-in template must pass."""
    from charter_harness.arms.raw_arm import endpoints_for

    ctx = _ctx("raw", [pack], owned={"slack.channel": ["C1"], "gcalendar.event": ["X"], "gmail.thread": ["X"]})
    for ep in endpoints_for(pack):
        import re

        path = re.sub(r"\{[^}]+\}", "X", ep.template)
        if pack == "github" and ep.method != "GET":
            path = re.sub(r"^repos/X/X", "repos/harness-owner/harness-X", path)
        body = {"channel": "C1"} if pack == "slack" else {}
        assert decide(raw_tool_name(pack), {"method": ep.method, "path": path, "body": body}, ctx) is None, (
            ep,
            path,
        )


def test_raw_arm_tools_register_their_index():
    from charter_harness.context import run_context

    RawArm().tools(["stripe", "linear"], WIRING)
    assert run_context().tool_index["stripe_api"] == ["stripe", "stripe_api"]
    assert run_context().tool_index["linear_graphql"] == ["linear", "linear_graphql"]
    assert run_context().arm == "raw"


# ---------------------------------------------------------------- gmail, both arms


def test_neither_way_of_sending_is_offered_to_the_model():
    """Gmail has two. Withholding only the obvious one is how the guarantee is
    lost: `drafts_send` posts an existing draft to the same recipients."""
    from charter_harness.arms.charter_arm import EXCLUDED_TOOLS

    names = {d.name for d in CharterArm().tools(["gmail"], WIRING)}
    assert "gmail__messages_send" not in names
    assert "gmail__drafts_send" not in names
    assert {("gmail", "messages_send"), ("gmail", "drafts_send")} <= EXCLUDED_TOOLS
    # and the rest of the pack still is
    assert "gmail__messages_get" in names and "gmail__drafts_get" in names


def test_the_guard_refuses_either_send_even_if_it_were_registered():
    ctx = _ctx("charter", ["gmail"])
    for tool in ("messages_send", "drafts_send"):
        ctx.tool_index = {**ctx.tool_index, f"gmail__{tool}": ["gmail", tool]}
        assert decide(f"gmail__{tool}", {"userId": "me", "id": "d1"}, ctx)


def test_the_raw_arm_cannot_post_to_either_send_path():
    ctx = _ctx("raw", ["gmail"])
    for path in ("gmail/v1/users/me/messages/send", "gmail/v1/users/me/drafts/send"):
        assert decide("gmail_api", {"method": "POST", "path": path, "body": {}}, ctx), path


def test_only_seeded_threads_may_be_deleted_or_trashed():
    """threads.delete is permanent, and the mailbox holds real correspondence."""
    ctx = _ctx("charter", ["gmail"], owned={"gmail.thread": ["seeded"]})
    for tool in ("threads_delete", "threads_trash"):
        assert decide(f"gmail__{tool}", {"userId": "me", "id": "seeded"}, ctx) is None
        assert decide(f"gmail__{tool}", {"userId": "me", "id": "someones-real-mail"}, ctx)


def test_the_raw_arm_is_held_to_the_same_thread_rule():
    ctx = _ctx("raw", ["gmail"], owned={"gmail.thread": ["seeded"]})
    ok = "gmail/v1/users/me/threads/seeded"
    real = "gmail/v1/users/me/threads/someones-real-mail"
    assert decide("gmail_api", {"method": "DELETE", "path": ok}, ctx) is None
    assert decide("gmail_api", {"method": "DELETE", "path": real}, ctx)
    assert decide("gmail_api", {"method": "POST", "path": real + "/trash", "body": {}}, ctx)


# -----------------------------------------------------
# The agent may unmake what it made
# -----------------------------------------------------


def _charter_ctx(**owned):
    return GuardContext(
        arm="charter",
        tool_index={"gcalendar__events_delete": ["gcalendar", "events_delete"]},
        owned=owned,
    )


def test_an_event_the_agent_created_may_be_deleted():
    """Restricted to seeded fixtures, this rule cost a run its task: it wrote
    three events at the wrong offset, noticed, was refused all three deletes, and
    recreated them correctly — six events where three were expected. It punished
    the agent for recovering."""
    ctx = _charter_ctx(**{"gcalendar.event": ["seeded1", "agent-made"]})
    assert decide("gcalendar__events_delete", {"eventId": "agent-made"}, ctx) is None
    assert decide("gcalendar__events_delete", {"eventId": "seeded1"}, ctx) is None


def test_an_event_this_run_did_not_make_is_still_refused():
    ctx = _charter_ctx(**{"gcalendar.event": ["agent-made"]})
    reason = decide("gcalendar__events_delete", {"eventId": "somebody-elses"}, ctx)
    assert reason and "created for this task" in reason


def test_the_same_holds_on_the_raw_arm():
    ctx = GuardContext(
        arm="raw",
        tool_index={"gcalendar_api": ["gcalendar", "gcalendar_api"]},
        owned={"gcalendar.event": ["agent-made"]},
    )
    events = "calendar/v3/calendars/primary/events"
    assert decide("gcalendar_api", {"method": "DELETE", "path": f"{events}/agent-made"}, ctx) is None
    assert decide("gcalendar_api", {"method": "DELETE", "path": f"{events}/other"}, ctx)


def test_only_a_creating_call_grants_ownership():
    """A GET that happens to return an id must not license deleting it."""
    from charter_harness.arms.ownership import RAW_CREATORS, _identifier

    assert _identifier('{"id": "abc"}') == "abc"
    assert _identifier({"id": 42}) == "42"
    assert _identifier("not json at all") is None
    assert _identifier({"no": "id"}) is None
    assert all(method == "POST" for _, method, _, _ in RAW_CREATORS)
