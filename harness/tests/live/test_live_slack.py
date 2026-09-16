"""Slack, against the real workspace, in one channel.

Slack answers everything with HTTP 200 and puts the failure in ``ok: false``,
which is the one API shape where a mock is actively misleading: a test double
returns ``{"ok": true}`` for a request Slack would have refused, and the refusal
is the whole of Slack's error reporting. Three tests here assert a *documented
refusal* rather than a success, because on a one-bot workspace that is the only
honest way to reach the endpoint at all — and a refusal still proves the request
was built, sent, and parsed.

Everything posted carries the run tag and is deleted on the way out. The one
exception is the channel ``conversations_create`` makes: Slack has no delete,
only archive, so teardown archives it.
"""

from __future__ import annotations

import time

import pytest
from charter.packs import slack
from charter.types.errors import CharterError, CredentialError

pytestmark = pytest.mark.live


async def _channel_id(world) -> str:
    return await world.slack.channel_id()


async def _bot_user_id(world) -> str:
    """Who the bot token is. ``auth.test`` is not in the pack — identity is the
    host's business, not the agent's — so the world client answers it."""
    return (await world.slack.call("auth.test", json={}))["user_id"]


async def _post(world, trash, channel: str, text: str, **fields) -> str:
    """A message through the pack, deleted on the way out."""
    posted = await slack.chat_post_message.ainvoke({"channel": channel, "text": text, **fields})
    assert posted["ok"] is True
    ts = posted["ts"]
    trash.later(lambda: world.slack.delete(ts))
    return ts


# -----------------------------------------------------
# Resolving a channel name, which everything else needs
# -----------------------------------------------------


async def test_a_channel_name_resolves_to_an_id(needs, world, settings):
    """Every other Slack tool takes an id. ``conversations_list`` is how an agent
    holding "#harness" gets one, and the ``types`` filter is a comma-joined
    string rather than an array — a shape a mock would accept either way."""
    needs("slack")
    listing = await slack.conversations_list.ainvoke(
        {"types": "public_channel,private_channel", "exclude_archived": True, "limit": 200}
    )
    named = [c for c in listing["channels"] if c["name"] == settings.slack_channel]
    assert named, f"no channel named #{settings.slack_channel}"
    assert named[0]["id"] == await _channel_id(world)


# -----------------------------------------------------
# A message, end to end
# -----------------------------------------------------


async def test_a_message_is_posted_edited_and_deleted(needs, world, trash, run_tag):
    """Four tools on one message, in the order an agent uses them."""
    needs("slack")
    channel = await _channel_id(world)

    ts = await _post(world, trash, channel, f"live check {run_tag}")

    edited = await slack.chat_update.ainvoke(
        {"channel": channel, "ts": ts, "text": f"live check {run_tag}, edited"}
    )
    assert edited["text"] == f"live check {run_tag}, edited"

    history = await slack.conversations_history.ainvoke({"channel": channel, "limit": 20})
    mine = [m for m in history["messages"] if m["ts"] == ts]
    assert mine and mine[0]["text"] == f"live check {run_tag}, edited"

    deleted = await slack.chat_delete.ainvoke({"channel": channel, "ts": ts})
    assert deleted["ts"] == ts


async def test_a_reaction_is_added_read_and_removed(needs, world, trash, run_tag, scope_skip):
    """``reactions_get`` closes the pair that used to be write-only: the pack
    could add a reaction and never see one. Its own test, so that a token
    without ``reactions:read`` costs the read and not the write."""
    needs("slack")
    channel = await _channel_id(world)
    ts = await _post(world, trash, channel, f"live reaction {run_tag}")

    await slack.reactions_add.ainvoke({"channel": channel, "timestamp": ts, "name": "eyes"})

    try:
        got = await slack.reactions_get.ainvoke(
            {"channel": channel, "timestamp": ts, "full": True}
        )
    except CharterError as exc:
        scope_skip(exc, scope="reactions:read")
        raise
    assert [r["name"] for r in got["message"]["reactions"]] == ["eyes"]

    await slack.reactions_remove.ainvoke({"channel": channel, "timestamp": ts, "name": "eyes"})
    gone = await slack.reactions_get.ainvoke({"channel": channel, "timestamp": ts})
    assert "reactions" not in gone["message"]


async def test_a_thread_reads_back_in_order(needs, world, trash, run_tag):
    """``thread_ts`` on the reply and ``ts`` on the read: the same string plays
    two roles, which is the part that gets written the wrong way round."""
    needs("slack")
    channel = await _channel_id(world)

    parent = await _post(world, trash, channel, f"live thread {run_tag}")
    reply = await _post(
        world, trash, channel, f"live reply {run_tag}", thread_ts=parent
    )

    thread = await slack.conversations_replies.ainvoke(
        {"channel": channel, "ts": parent, "limit": 50}
    )
    assert [m["ts"] for m in thread["messages"]] == [parent, reply]
    assert thread["messages"][0]["reply_count"] == 1


async def test_an_ephemeral_message_returns_only_its_timestamp(needs, world, run_tag):
    """``chat.postEphemeral`` answers ``message_ts`` and nothing else — there is
    no message to update, delete or react to afterwards, which is why nothing is
    registered for teardown here. It vanishes on its own."""
    needs("slack")
    channel = await _channel_id(world)

    posted = await slack.chat_post_ephemeral.ainvoke(
        {
            "channel": channel,
            "user": await _bot_user_id(world),
            "text": f"live ephemeral {run_tag}",
        }
    )
    assert posted["message_ts"]
    assert "ts" not in posted


async def test_a_scheduled_message_is_accepted_and_then_cancelled(needs, world, run_tag):
    """The returned ``scheduled_message_id`` is the only handle on a message that
    has not been posted yet.

    Cancelling goes through the world: ``chat.deleteScheduledMessage`` is not in
    the pack, and without it this test would leave a message that posts itself
    into the channel minutes after the run ends.
    """
    needs("slack")
    channel = await _channel_id(world)
    post_at = int(time.time()) + 600

    scheduled = await slack.chat_schedule_message.ainvoke(
        {"channel": channel, "post_at": post_at, "text": f"live scheduled {run_tag}"}
    )
    assert scheduled["scheduled_message_id"]
    assert scheduled["post_at"] == post_at

    cancelled = await world.slack.call(
        "chat.deleteScheduledMessage",
        json={"channel": channel, "scheduled_message_id": scheduled["scheduled_message_id"]},
    )
    assert cancelled["ok"] is True


# -----------------------------------------------------
# Channels and people
# -----------------------------------------------------


async def test_a_channel_is_created_and_somebody_is_invited(
    needs, world, trash, run_tag, scope_skip
):
    """``conversations_create`` then ``conversations_invite``, in the order they
    are used: an agent asked to open a channel for something has to put people in
    it, and inviting is the half that used to be missing.

    Teardown archives. Slack's API cannot delete a channel outside Enterprise
    Grid, so an archived one named after the run is the tidiest end available.
    """
    needs("slack")
    made = await slack.conversations_create.ainvoke(
        {"name": f"live-{run_tag}", "is_private": False}
    )
    channel = made["channel"]["id"]
    trash.later(lambda: world.slack.call("conversations.archive", json={"channel": channel}))
    assert made["channel"]["name"] == f"live-{run_tag}"

    people = await slack.users_list.ainvoke({"limit": 100})
    human = next(
        m for m in people["members"] if not m.get("is_bot") and m["name"] != "slackbot"
    )

    try:
        invited = await slack.conversations_invite.ainvoke(
            {"channel": channel, "users": human["id"]}
        )
    except CharterError as exc:
        scope_skip(exc, scope="channels:write.invites")
        raise
    assert invited["channel"]["id"] == channel

    profile = await slack.users_info.ainvoke({"user": human["id"], "include_locale": True})
    assert profile["user"]["id"] == human["id"]


async def test_a_direct_message_channel_can_be_opened(needs, world, scope_skip):
    """``conversations_open`` is how a person becomes a channel id. The schema
    refuses a call naming neither users nor a channel, which the API would accept
    and answer uselessly — so the refusal is local and this is the shape that
    works."""
    needs("slack")
    people = await slack.users_list.ainvoke({"limit": 100})
    human = next(
        m for m in people["members"] if not m.get("is_bot") and m["name"] != "slackbot"
    )

    try:
        opened = await slack.conversations_open.ainvoke(
            {"users": human["id"], "return_im": True}
        )
    except CharterError as exc:
        scope_skip(exc, scope="im:write")
        raise
    assert opened["channel"]["id"].startswith("D")


async def test_search_needs_a_user_token_and_says_so(needs):
    """``search.messages`` is not available to a bot token at all. The pack's
    docstring says so; this is the check that the claim is Slack's and not ours,
    and that the refusal arrives as an error rather than as an empty result set.

    It arrives as a ``CredentialError`` rather than an ``APIError`` because the
    envelope lists ``not_allowed_token_type`` among the codes that mean the
    credential is the problem — which is the right call and worth pinning, since
    a host retrying this after a token refresh would loop forever otherwise.
    """
    needs("slack")
    with pytest.raises(CredentialError) as refused:
        await slack.search_messages.ainvoke({"query": "live check", "count": 1})
    assert "not_allowed_token_type" in str(refused.value)


async def test_the_bot_can_join_a_public_channel(needs, world):
    """Joining a channel the bot is already in succeeds with a warning, which
    makes this the one write in the pack that is safe to call repeatedly.

    ``channel`` is this pack's lone scalar body field, so until the unwrap rule
    was fixed the request was the bare string ``"C0…"`` and the tool could never
    run — see ``test_a_lone_scalar_body_field_reaches_the_network`` in the Stripe
    file for the rule itself.
    """
    needs("slack")
    joined = await slack.conversations_join.ainvoke({"channel": await _channel_id(world)})
    assert joined["ok"] is True
