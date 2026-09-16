"""Slack pack — wire behaviour, the ok:false guard, and response trimming."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from charter import APIError, CredentialError, Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.packs import slack

API = "https://slack.com/api/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    slack.configure(StaticTokenProvider("xoxb-test"))


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_eighteen_tools():
    assert len(slack.TOOLS) == 18
    assert all(isinstance(t, Tool) for t in slack.TOOLS)


def test_every_tool_builds_its_schemas():
    for tool in slack.TOOLS:
        assert tool.llm_schema().model_fields
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_every_tool_is_bearer_auth_against_slack():
    for tool in slack.TOOLS:
        assert tool.provider == "slack"
        assert tool.api_key_headers is None
        assert tool.base_url == API


def test_slack_is_snake_case_on_the_wire():
    """Slack uses snake_case everywhere; camel defaults would corrupt every call."""
    for tool in slack.TOOLS:
        assert tool.body_case == "snake"
        assert tool.query_case == "snake"


def test_no_quota_cost_is_claimed():
    """Slack rate-limits by tier, not by metered units. A number here would be invented."""
    for tool in slack.TOOLS:
        assert tool.quota_cost is None
        assert tool.quota_doc_url == slack.QUOTA_DOC_URL


def test_token_is_not_a_schema_field():
    """Slack documents `token` as an argument, but it travels in the Authorization
    header. Modelling it would invite the model to pass a credential."""
    for tool in slack.TOOLS:
        assert "token" not in tool.args_schema.model_fields


def test_every_tool_inherits_the_ok_false_envelope():
    """Declared once on the factory — not something a tool author can forget."""
    for tool in slack.TOOLS:
        assert tool.envelope is slack.SLACK_ENVELOPE, tool.name


def test_only_the_tools_with_nothing_to_trim_lack_a_handler():
    """The ok:false check moved to the envelope, so a handler is present only
    where there is genuinely something to trim.

    Asserted as the *absence* set rather than the presence set: these four
    answer with `{"ok": true}` and at most a channel and a ts, so a projection
    would have nothing to do. Every other tool echoes a message, a user or a
    channel object and must trim it. A new tool added without a handler lands
    in this set and fails here, which is the point.
    """
    bare = {t.name for t in slack.TOOLS if t._executor._response_handler is None}
    assert bare == {
        "chat_delete",
        "chat_post_ephemeral",
        "reactions_add",
        "reactions_remove",
    }


# -----------------------------------------------------
# The ok:false guard — the thing that makes this pack correct
# -----------------------------------------------------


@respx.mock
async def test_slack_error_body_raises_despite_http_200():
    """Slack answers failure with 200 OK. Unguarded, the model reads it as success."""
    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "channel_not_found"})
    )

    with pytest.raises(APIError) as excinfo:
        await slack.chat_post_message.ainvoke(channel="C_NOPE", text="hi")

    assert route.called  # the request really was made and really returned 200
    assert "channel_not_found" in str(excinfo.value)
    assert excinfo.value.status_code == 200


@respx.mock
@pytest.mark.parametrize(
    "code", ["invalid_auth", "not_authed", "token_revoked", "missing_scope", "account_inactive"]
)
async def test_auth_errors_become_credential_errors(code):
    respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": code})
    )
    with pytest.raises(CredentialError) as excinfo:
        await slack.chat_post_message.ainvoke(channel="C1", text="hi")
    assert excinfo.value.provider == "slack"


@respx.mock
async def test_missing_scope_surfaces_the_needed_scope():
    respx.post(f"{API}reactions.add").mock(
        return_value=httpx.Response(
            200, json={"ok": False, "error": "missing_scope", "needed": "reactions:write"}
        )
    )
    with pytest.raises(CredentialError, match="reactions:write"):
        await slack.reactions_add.ainvoke(channel="C1", timestamp="1.0", name="tada")


@respx.mock
async def test_bot_token_calling_search_is_a_credential_error():
    """search.messages is user-token only; Slack says not_allowed_token_type."""
    respx.get(f"{API}search.messages").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "not_allowed_token_type"})
    )
    with pytest.raises(CredentialError):
        await slack.search_messages.ainvoke(query="deploy")


@respx.mock
async def test_a_real_http_error_still_raises_normally():
    respx.get(f"{API}users.info").mock(return_value=httpx.Response(429, text="rate limited"))
    with pytest.raises(APIError) as excinfo:
        await slack.users_info.ainvoke(user="U1")
    assert excinfo.value.status_code == 429


# -----------------------------------------------------
# Requests on the wire
# -----------------------------------------------------


@respx.mock
async def test_post_message_sends_a_json_body_with_bearer_auth():
    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "channel": "C1", "ts": "1.1"})
    )

    result = await slack.chat_post_message.ainvoke(
        channel="C123ABC456", text="Deploy finished", thread_ts="1700000000.000100"
    )

    assert result["ts"] == "1.1"
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer xoxb-test"
    body = json.loads(request.content)
    # snake_case preserved — camelCase would be rejected by Slack
    assert body == {
        "channel": "C123ABC456",
        "text": "Deploy finished",
        "thread_ts": "1700000000.000100",
    }


@respx.mock
async def test_unset_optional_fields_are_omitted_not_nulled():
    """Slack rejects unexpected nulls on several methods."""
    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await slack.chat_post_message.ainvoke(channel="C1", text="hi")
    assert set(json.loads(route.calls.last.request.content)) == {"channel", "text"}


@respx.mock
async def test_nested_metadata_keeps_snake_case_keys():
    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await slack.chat_post_message.ainvoke(
        channel="C1",
        text="hi",
        metadata={"event_type": "deploy", "event_payload": {"build_id": 7}},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["metadata"] == {"event_type": "deploy", "event_payload": {"build_id": 7}}


@respx.mock
async def test_get_methods_send_query_parameters():
    route = respx.get(f"{API}conversations.history").mock(
        return_value=httpx.Response(200, json={"ok": True, "messages": []})
    )
    await slack.conversations_history.ainvoke(channel="C1", limit=50, inclusive=True)

    params = dict(route.calls.last.request.url.params)
    assert params == {"channel": "C1", "limit": "50", "inclusive": "true"}


@respx.mock
async def test_dotted_method_names_survive_url_construction():
    """Slack method names contain dots; they are path, not format placeholders."""
    route = respx.get(f"{API}conversations.list").mock(
        return_value=httpx.Response(200, json={"ok": True, "channels": []})
    )
    await slack.conversations_list.ainvoke()
    assert str(route.calls.last.request.url).startswith(f"{API}conversations.list")


# -----------------------------------------------------
# Response trimming
# -----------------------------------------------------


@respx.mock
async def test_history_trimming_drops_the_noise_and_keeps_the_cursor():
    raw = {
        "ok": True,
        "has_more": True,
        "messages": [
            {
                "type": "message",
                "user": "U123",
                "text": "shipping now",
                "ts": "1700000000.000100",
                "thread_ts": "1700000000.000100",
                "reply_count": 2,
                "blocks": [{"type": "rich_text", "elements": [{"x": "y"} for _ in range(50)]}],
                "reactions": [
                    {"name": "tada", "users": ["U1", "U2", "U3"], "count": 3},
                ],
                "edited": {"user": "U123", "ts": "1700000001.000000"},
                "team": "T1",
                "client_msg_id": "abc-def",
            }
        ],
        "response_metadata": {"next_cursor": "dXNlcjpVMDYxTkZUVDI="},
    }
    respx.get(f"{API}conversations.history").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.conversations_history.ainvoke(channel="C1")

    message = result["messages"][0]
    assert message["text"] == "shipping now"
    assert message["user"] == "U123"
    assert message["reply_count"] == 2
    assert message["reactions"] == [{"name": "tada", "count": 3}]
    assert message["has_blocks"] is True

    # the block tree, edit record and per-reaction user list are gone
    assert "blocks" not in message
    assert "edited" not in message
    assert "client_msg_id" not in message
    assert "users" not in message["reactions"][0]

    # paging still works
    assert result["has_more"] is True
    assert result["next_cursor"] == "dXNlcjpVMDYxTkZUVDI="


@respx.mock
async def test_trimming_is_a_large_reduction():
    """The point of the handler is context economy — measure it on real shape."""
    big_block = [{"type": "rich_text", "elements": [{"t": "x" * 40} for _ in range(30)]}]
    raw = {
        "ok": True,
        "messages": [
            {
                "user": f"U{i}",
                "text": "ok",
                "ts": f"170000000{i}.0001",
                "blocks": big_block,
                "client_msg_id": "x" * 36,
                "team": "T1",
            }
            for i in range(20)
        ],
    }
    respx.get(f"{API}conversations.history").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.conversations_history.ainvoke(channel="C1")
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 5


@respx.mock
async def test_bot_messages_are_attributed_by_bot_id():
    respx.get(f"{API}conversations.history").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "messages": [{"bot_id": "B1", "text": "built", "ts": "1.0"}]},
        )
    )
    result = await slack.conversations_history.ainvoke(channel="C1")
    assert result["messages"][0]["user"] == "B1"


@respx.mock
async def test_channel_trimming():
    raw = {
        "ok": True,
        "channels": [
            {
                "id": "C1",
                "name": "engineering",
                "is_private": False,
                "is_archived": False,
                "num_members": 42,
                "topic": {"value": "ship it", "creator": "U1", "last_set": 1},
                "purpose": {"value": "eng chat", "creator": "U1", "last_set": 1},
                "previous_names": ["eng"],
                "shared_team_ids": ["T1"],
            }
        ],
        "response_metadata": {"next_cursor": ""},
    }
    respx.get(f"{API}conversations.list").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.conversations_list.ainvoke()
    channel = result["channels"][0]

    assert channel["id"] == "C1"
    assert channel["name"] == "engineering"
    assert channel["topic"] == "ship it"       # flattened from the object
    assert channel["purpose"] == "eng chat"
    assert channel["num_members"] == 42
    assert "previous_names" not in channel
    # an empty cursor means no further page — do not advertise one
    assert "next_cursor" not in result


@respx.mock
async def test_user_trimming_drops_avatar_urls_and_keeps_identity():
    raw = {
        "ok": True,
        "members": [
            {
                "id": "U1",
                "name": "ada",
                "real_name": "Ada Lovelace",
                "is_bot": False,
                "is_admin": True,
                "tz": "Europe/London",
                "profile": {
                    "email": "ada@example.com",
                    "title": "Engineer",
                    "image_24": "https://x/24.png",
                    "image_32": "https://x/32.png",
                    "image_512": "https://x/512.png",
                },
            }
        ],
    }
    respx.get(f"{API}users.list").mock(return_value=httpx.Response(200, json=raw))

    member = (await slack.users_list.ainvoke())["members"][0]
    assert member == {
        "id": "U1",
        "name": "ada",
        "real_name": "Ada Lovelace",
        "email": "ada@example.com",
        "title": "Engineer",
        "is_admin": True,
        "tz": "Europe/London",
    }


@respx.mock
async def test_email_is_absent_when_the_scope_is_not_granted():
    """users:read.email is a separate scope; the handler must not invent the field."""
    respx.get(f"{API}users.list").mock(
        return_value=httpx.Response(
            200, json={"ok": True, "members": [{"id": "U1", "name": "ada", "profile": {}}]}
        )
    )
    assert "email" not in (await slack.users_list.ainvoke())["members"][0]


# -----------------------------------------------------
# Validation and configuration
# -----------------------------------------------------


async def test_missing_required_argument_is_a_validation_error():
    from charter import ToolValidationError

    with pytest.raises(ToolValidationError, match="channel"):
        await slack.chat_post_message.ainvoke(text="no channel")


async def test_unconfigured_pack_raises_credential_error(monkeypatch):
    monkeypatch.setattr(slack._credentials, "_provider", None)
    with pytest.raises(CredentialError, match="configure"):
        await slack.chat_post_message.ainvoke(channel="C1", text="hi")


@respx.mock
async def test_env_var_fallback(monkeypatch):
    monkeypatch.setattr(slack._credentials, "_provider", None)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-from-env")
    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await slack.chat_post_message.ainvoke(channel="C1", text="hi")
    assert route.calls.last.request.headers["authorization"] == "Bearer xoxb-from-env"


def test_search_sort_values_are_constrained():
    from pydantic import ValidationError

    schema = slack.search_messages.llm_schema()
    schema.model_validate({"query": "x", "sort": "timestamp", "sort_dir": "asc"})
    with pytest.raises(ValidationError):
        schema.model_validate({"query": "x", "sort": "relevance"})


# -----------------------------------------------------
# Reaching a person, and the shapes Slack answers with
# -----------------------------------------------------


@pytest.mark.asyncio
async def test_opening_a_conversation_must_name_somebody():
    """Slack marks both `users` and `channel` optional because they are
    alternatives, not because a request may name neither."""
    with pytest.raises(ToolValidationError):
        await slack.conversations_open.ainvoke({})


@pytest.mark.asyncio
@respx.mock
async def test_a_dm_round_trip_uses_the_nested_channel_id():
    """The id a following chat_post_message needs is at `channel.id`, not at the
    top level. This is the round trip: find a user, then message them."""
    respx.post(f"{API}conversations.open").mock(
        return_value=httpx.Response(200, json={"ok": True, "channel": {"id": "D069C7QFK"}})
    )
    opened = await slack.conversations_open.ainvoke({"users": "U123"})
    assert opened["channel"]["id"] == "D069C7QFK"

    route = respx.post(f"{API}chat.postMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "ts": "1.2", "channel": "D069C7QFK"})
    )
    await slack.chat_post_message.ainvoke(
        {"channel": opened["channel"]["id"], "text": "hello"}
    )
    assert "D069C7QFK" in route.calls.last.request.content.decode()


def test_reactions_get_is_the_only_one_that_takes_a_query_string():
    """Slack is inconsistent about placement and mixing the two is refused."""
    assert slack.reactions_get.method == "GET"
    for name in (
        "reactions_remove", "conversations_open", "conversations_create",
        "conversations_invite", "conversations_join", "chat_post_ephemeral",
        "chat_schedule_message",
    ):
        assert getattr(slack, name).method == "POST", name


def test_a_reaction_can_now_be_taken_back():
    names = {t.name for t in slack.TOOLS}
    assert {"reactions_add", "reactions_remove"} <= names


# -----------------------------------------------------
# The handlers added to close the trim gap
# -----------------------------------------------------


def _profile_heavy_user(uid: str = "U1") -> dict:
    """A users.info payload with the fields Slack actually sends."""
    return {
        "id": uid,
        "name": "ada",
        "real_name": "Ada Lovelace",
        "color": "9f69e7",
        "team_id": "T1",
        "tz": "Europe/London",
        "tz_label": "British Summer Time",
        "tz_offset": 3600,
        "is_admin": True,
        "profile": {
            "real_name": "Ada Lovelace",
            "title": "Analyst",
            "email": "ada@example.com",
            "status_text_canonical": "",
            **{f"image_{n}": f"https://avatars.example/{uid}/{n}.png"
               for n in (24, 32, 48, 72, 192, 512, 1024, "original")},
        },
    }


@respx.mock
async def test_user_info_gets_the_same_projection_as_the_list():
    raw = {"ok": True, "user": _profile_heavy_user()}
    respx.get(f"{API}users.info").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.users_info.ainvoke(user="U1")

    assert result["user"]["id"] == "U1"
    assert result["user"]["real_name"] == "Ada Lovelace"
    assert result["user"]["email"] == "ada@example.com"
    assert result["user"]["is_admin"] is True
    assert "image_512" not in json.dumps(result)
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 3


@respx.mock
async def test_user_info_on_a_missing_user_does_not_invent_one():
    respx.get(f"{API}users.info").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert await slack.users_info.ainvoke(user="U1") == {"user": None}


@respx.mock
async def test_post_message_keeps_channel_and_ts_and_drops_the_echo():
    """The two values a following call needs survive; the block tree does not."""
    raw = {
        "ok": True,
        "channel": "C1",
        "ts": "1700000000.0001",
        "message": {
            "user": "U1",
            "text": "shipped",
            "ts": "1700000000.0001",
            "blocks": [{"type": "rich_text", "elements": [{"t": "x" * 200}]}],
            "team": "T1",
            "bot_profile": {"id": "B1", "icons": {"image_72": "https://x/y.png"}},
        },
    }
    respx.post(f"{API}chat.postMessage").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.chat_post_message.ainvoke(channel="C1", text="shipped")

    assert result["channel"] == "C1"
    assert result["ts"] == "1700000000.0001"
    assert result["message"]["has_blocks"] is True
    assert "bot_profile" not in json.dumps(result)
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 2


@respx.mock
async def test_a_partial_invite_failure_survives_the_projection():
    """conversations.invite with force reports the users it could not add
    alongside ok:true. A handler that dropped `errors` would report a partial
    failure as a clean success."""
    raw = {
        "ok": True,
        "channel": {
            "id": "C1",
            "name": "general",
            "is_private": False,
            "topic": {"value": "talk", "creator": "U1", "last_set": 1},
            "purpose": {"value": "", "creator": "", "last_set": 0},
            "previous_names": ["old-general"],
        },
        "errors": [{"user": "U9", "ok": False, "error": "cant_invite_self"}],
    }
    respx.post(f"{API}conversations.invite").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.conversations_invite.ainvoke(channel="C1", users="U9")

    assert result["errors"] == [{"user": "U9", "ok": False, "error": "cant_invite_self"}]
    assert result["channel"]["id"] == "C1"
    assert result["channel"]["topic"] == "talk"


@respx.mock
async def test_joining_a_channel_twice_keeps_the_warning():
    raw = {
        "ok": True,
        "channel": {"id": "C1", "name": "general"},
        "warning": "already_in_channel",
        "response_metadata": {"warnings": ["already_in_channel"]},
    }
    respx.post(f"{API}conversations.join").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.conversations_join.ainvoke(channel="C1")
    assert result["warning"] == "already_in_channel"


@respx.mock
async def test_search_drops_the_surrounding_messages_and_keeps_the_permalink():
    """Each search hit ships four neighbouring messages nobody asked for."""
    neighbour = {"user": "U2", "text": "y" * 300, "ts": "1699999999.0001"}
    raw = {
        "ok": True,
        "query": "shipped",
        "messages": {
            "total": 2,
            "pagination": {"total_count": 2, "page": 1, "per_page": 20, "page_count": 1},
            "paging": {"count": 20, "total": 2, "page": 1, "pages": 1},
            "matches": [
                {
                    "ts": f"170000000{i}.0001",
                    "user": "U1",
                    "text": "shipped",
                    "permalink": f"https://x.slack.com/archives/C1/p{i}",
                    "channel": {
                        "id": "C1",
                        "name": "general",
                        "is_private": False,
                        "topic": {"value": "talk"},
                        "purpose": {"value": "talking"},
                    },
                    "previous": neighbour,
                    "previous_2": neighbour,
                    "next": neighbour,
                    "next_2": neighbour,
                }
                for i in range(2)
            ],
        },
    }
    respx.get(f"{API}search.messages").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.search_messages.ainvoke(query="shipped")

    assert result["total"] == 2
    assert result["matches"][0]["permalink"].startswith("https://x.slack.com")
    assert result["matches"][0]["channel"] == {"id": "C1", "name": "general"}
    assert "previous_2" not in json.dumps(result)
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 3


@respx.mock
async def test_reactions_get_collapses_the_per_reaction_user_lists():
    raw = {
        "ok": True,
        "type": "message",
        "channel": "C1",
        "message": {
            "ts": "1700000000.0001",
            "user": "U1",
            "text": "ship it",
            "reactions": [
                {"name": "tada", "count": 30, "users": [f"U{i}" for i in range(30)]},
                {"name": "rocket", "count": 12, "users": [f"V{i}" for i in range(12)]},
            ],
        },
    }
    respx.get(f"{API}reactions.get").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.reactions_get.ainvoke(channel="C1", timestamp="1700000000.0001")

    assert result["message"]["reactions"] == [
        {"name": "tada", "count": 30},
        {"name": "rocket", "count": 12},
    ]
    assert "U29" not in json.dumps(result)


@respx.mock
async def test_scheduling_keeps_the_id_that_cancels_it():
    raw = {
        "ok": True,
        "channel": "C1",
        "scheduled_message_id": "Q1234ABCD",
        "post_at": 1799999999,
        "message": {
            "text": "later",
            "user": "U1",
            "blocks": [{"type": "rich_text", "elements": [{"t": "x" * 200}]}],
        },
    }
    respx.post(f"{API}chat.scheduleMessage").mock(return_value=httpx.Response(200, json=raw))

    result = await slack.chat_schedule_message.ainvoke(
        channel="C1", text="later", post_at=1799999999
    )

    assert result["scheduled_message_id"] == "Q1234ABCD"
    assert result["post_at"] == 1799999999
    assert "rich_text" not in json.dumps(result)


def test_every_timestamp_in_the_pack_tells_the_model_it_is_seconds():
    """Slack takes epoch seconds, and a ts carries a fraction.

    `oldest`/`latest` are strings, so milliseconds are accepted and silently
    select an empty window rather than failing. `post_at` is an integer that
    accepts them just as happily, and Slack answers `time_too_far` only once
    the value is past 120 days, which milliseconds always are.
    """
    from pydantic import BaseModel

    from charter.types import Gloss

    def timestamps(model, seen=frozenset()):
        if model in seen:
            return
        for name, field in model.model_fields.items():
            if "unix timestamp" in (field.description or "").lower():
                yield model, name, field
            for candidate in (field.annotation, *getattr(field.annotation, "__args__", ())):
                for item in (candidate, *getattr(candidate, "__args__", ())):
                    if isinstance(item, type) and issubclass(item, BaseModel):
                        yield from timestamps(item, seen | {model})

    naked = set()
    for tool in slack.TOOLS:
        for model, name, field in timestamps(tool.args_schema):
            if not any(isinstance(m, Gloss) for m in getattr(field, "metadata", [])):
                naked.add(f"{model.__name__}.{name}")

    assert not naked, (
        f"Slack timestamp fields with no Gloss telling the model they are seconds: {sorted(naked)}"
    )
