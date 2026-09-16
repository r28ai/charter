"""Adversarial cases for the credential path — one test per bug actually found.

Everything here failed at least once against a real implementation. A hostile or
merely sloppy authorization server, a stampede, a revoked grant, and the places
where a secret could escape.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Annotated

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    CallCollector,
    CharterError,
    CredentialError,
    Path,
    format_call_summary,
    oauth_tool_factory,
)
from charter.auth import (
    OAuth2Client,
    OAuth2Server,
    SubjectProvider,
    use_subject,
)
from charter.auth.oauth import _DEAD_GRANT_COOLDOWN_SECONDS

TOKEN_URL = "https://oauth2.example.com/token"
API = "https://api.example.com/"
SERVER = OAuth2Server(token_endpoint=TOKEN_URL)


def _client(**kw) -> OAuth2Client:
    base = dict(client_id="cid", client_secret="s3cr3t-client", refresh_token="rt-1")
    base.update(kw)
    return OAuth2Client(SERVER, **base)


def _ok(**kw) -> httpx.Response:
    body = {"access_token": "at-1", "expires_in": 3600}
    body.update(kw)
    return httpx.Response(200, json=body)


class Args(BaseModel):
    thing_id: Annotated[str, Path()]


def _tool(provider, **kw):
    factory = oauth_tool_factory(
        base_url=API, provider="example", credential_provider=provider, **kw
    )
    return factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )


# -----------------------------------------------------
# A server that answers with nonsense
# -----------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    "expires_in",
    [10**20, -(10**20), "9" * 40, 1e308],
    ids=["huge", "hugely_negative", "huge_string", "float_inf_ish"],
)
async def test_an_absurd_expires_in_does_not_escape_as_an_arbitrary_exception(expires_in):
    """A raw OverflowError would sail past every `except CharterError` a host wrote."""
    respx.post(TOKEN_URL).mock(return_value=_ok(expires_in=expires_in))

    try:
        credentials = await _client().get_credentials("example")
    except CharterError:
        pass  # a typed failure is acceptable; an untyped one is not
    else:
        assert credentials.token == "at-1"


@respx.mock
@pytest.mark.parametrize(
    "expires_in", [None, "soon", {}, [], True], ids=["null", "text", "dict", "list", "bool"]
)
async def test_a_junk_expires_in_is_treated_as_no_expiry(expires_in):
    respx.post(TOKEN_URL).mock(return_value=_ok(expires_in=expires_in))
    assert (await _client().get_credentials("example")).expires_at is None


@pytest.mark.parametrize(
    "body",
    [
        b"null",
        b"[]",
        b"[1]",
        b"{}",
        b'{"access_token":null}',
        b'{"access_token":[]}',
        b'{"error":null}',
        b'{"error":[]}',
        b'{"error":{"code":1}}',
        b'{"error":"x","error_description":{"a":1}}',
        # Python's json parses these bare literals, so a server can send them.
        b'{"access_token":"a","expires_in":NaN}',
        b'{"access_token":"a","expires_in":Infinity}',
        b'{"access_token":"a","expires_in":-Infinity}',
        b'{"access_token":"a","refresh_token":0}',
        b'{"access_token":"a","expires_in":"1e309"}',
        b'{"access_token":"a","expires_in":"0x10"}',
        b'{"access_token":"a","expires_in":' + b"9" * 400 + b"}",
        b'"a string"',
        b"42",
        b"true",
        b"not json at all",
        b"",
    ],
    ids=range(22),
)
@respx.mock
async def test_only_typed_errors_escape_a_hostile_token_response(body):
    """Whatever the server sends, a host's `except CharterError` must be enough.

    `Infinity` reached `int()` and raised OverflowError past every handler —
    the same class of escape as an absurd integer, through a different door.
    """
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, content=body, headers={"content-type": "application/json"}
        )
    )
    try:
        await _client().get_credentials("example")
    except CharterError:
        pass


@respx.mock
@pytest.mark.parametrize(
    "secret, expected",
    [("a b", "a+b"), ("a+b", "a%2Bb"), ("a/b=", "a%2Fb%3D"), ("pä:ss", "p%C3%A4%3Ass")],
)
async def test_basic_auth_uses_form_encoding_not_percent_encoding(secret, expected):
    """RFC 6749 §2.3.1 encodes each half with application/x-www-form-urlencoded.

    A space is therefore "+", not "%20". Most servers decode either, which is
    exactly why this would have failed once, mysteriously, against the one that
    does not.
    """
    import base64

    basic = OAuth2Server(
        token_endpoint=TOKEN_URL, token_endpoint_auth_method="client_secret_basic"
    )
    route = respx.post(TOKEN_URL).mock(return_value=_ok())

    await OAuth2Client(
        basic, client_id="cid", client_secret=secret, refresh_token="rt-1"
    ).get_credentials("example")

    header = route.calls[0].request.headers["Authorization"].split(" ", 1)[1]
    assert base64.b64decode(header).decode() == f"cid:{expected}"


@respx.mock
async def test_the_token_request_is_form_encoded():
    route = respx.post(TOKEN_URL).mock(return_value=_ok())
    await _client().get_credentials("example")
    content_type = route.calls[0].request.headers["content-type"]
    assert content_type.startswith("application/x-www-form-urlencoded")


@respx.mock
async def test_a_token_response_that_is_a_list_is_refused_cleanly():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=["not", "an", "object"]))
    with pytest.raises(CredentialError):
        await _client().get_credentials("example")


@respx.mock
async def test_a_non_string_access_token_is_refused():
    respx.post(TOKEN_URL).mock(return_value=_ok(access_token=12345))
    with pytest.raises(CredentialError, match="no access_token"):
        await _client().get_credentials("example")


@respx.mock
async def test_a_non_string_rotated_refresh_token_is_ignored_not_adopted():
    respx.post(TOKEN_URL).mock(return_value=_ok(refresh_token={"oops": 1}))
    client = _client()
    await client.get_credentials("example")
    assert client.refresh_token == "rt-1"


@respx.mock
async def test_an_empty_rotated_refresh_token_does_not_erase_the_working_one():
    respx.post(TOKEN_URL).mock(return_value=_ok(refresh_token=""))
    client = _client()
    await client.get_credentials("example")
    assert client.refresh_token == "rt-1"


# -----------------------------------------------------
# A revoked grant must not become a stampede
# -----------------------------------------------------


@respx.mock
async def test_a_revoked_grant_is_asked_about_once_not_once_per_tool_call():
    """Token endpoints rate-limit per client, so one dead user can degrade every
    other user of the same app."""
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = _client()

    for _ in range(25):
        with pytest.raises(CredentialError, match="invalid_grant"):
            await client.get_credentials("example")

    assert route.call_count == 1


@respx.mock
async def test_the_cool_down_does_not_grow_a_traceback_on_every_raise():
    """Caching an exception *instance* and re-raising it is a slow leak.

    Each raise appends a frame to the same object's traceback, and each frame
    pins its locals. Five thousand raises grew one to fifteen thousand frames,
    so the cool-down remembers the reason and builds a fresh error each time.
    """

    def frames(exc: BaseException) -> int:
        count, tb = 0, exc.__traceback__
        while tb:
            count, tb = count + 1, tb.tb_next
        return count

    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = _client()

    depths = []
    for _ in range(200):
        try:
            await client.get_credentials("example")
        except CredentialError as exc:
            depths.append(frames(exc))

    assert max(depths[1:]) == min(depths[1:])  # every cool-down raise is identical
    assert max(depths) < 10


@respx.mock
async def test_the_cool_down_error_still_names_the_provider():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = _client()

    with pytest.raises(CredentialError):
        await client.get_credentials("example")
    with pytest.raises(CredentialError) as second:
        await client.get_credentials("acme")

    assert second.value.provider == "acme"
    assert second.value.status_code == 400
    assert "invalid_grant" in str(second.value)


@respx.mock
async def test_the_cool_down_expires_so_a_transient_invalid_grant_recovers():
    route = respx.post(TOKEN_URL).mock(
        side_effect=[httpx.Response(400, json={"error": "invalid_grant"}), _ok()]
    )
    client = _client()

    with pytest.raises(CredentialError):
        await client.get_credentials("example")
    client._dead_until -= _DEAD_GRANT_COOLDOWN_SECONDS + 1  # pretend a minute passed

    assert (await client.get_credentials("example")).token == "at-1"
    assert route.call_count == 2


@respx.mock
async def test_reset_clears_the_cool_down_after_reauthorization():
    respx.post(TOKEN_URL).mock(
        side_effect=[httpx.Response(400, json={"error": "invalid_grant"}), _ok()]
    )
    client = _client()

    with pytest.raises(CredentialError):
        await client.get_credentials("example")
    client.reset()
    assert (await client.get_credentials("example")).token == "at-1"


@respx.mock
async def test_other_failures_are_retried_because_they_may_be_transient():
    route = respx.post(TOKEN_URL).mock(
        side_effect=[httpx.Response(503, json={"error": "temporarily_unavailable"}), _ok()]
    )
    client = _client()

    with pytest.raises(CredentialError):
        await client.get_credentials("example")
    assert (await client.get_credentials("example")).token == "at-1"
    assert route.call_count == 2


@respx.mock
async def test_concurrent_callers_do_not_queue_up_behind_a_dead_grant():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    client = _client()

    results = await asyncio.gather(
        *(client.get_credentials("example") for _ in range(10)), return_exceptions=True
    )

    assert all(isinstance(r, CredentialError) for r in results)
    assert route.call_count == 1


@respx.mock
async def test_a_transport_failure_leaves_no_poisoned_state():
    route = respx.post(TOKEN_URL).mock(
        side_effect=[httpx.ConnectTimeout("down"), _ok()]
    )
    client = _client()

    with pytest.raises(httpx.ConnectTimeout):
        await client.get_credentials("example")
    assert (await client.get_credentials("example")).token == "at-1"
    assert route.call_count == 2


# -----------------------------------------------------
# The cache must not defeat itself
# -----------------------------------------------------


@respx.mock
async def test_a_token_shorter_lived_than_the_leeway_is_not_refreshed_every_call():
    """Born inside its own renewal window: the cache would turn one call into two.

    Worse against a rotating server, which would mint a new refresh token per
    tool call — the exact stampede the cache exists to prevent, and invisible
    except as latency.
    """
    route = respx.post(TOKEN_URL).mock(return_value=_ok(expires_in=60))
    client = _client(leeway_seconds=90)

    for _ in range(10):
        await client.get_credentials("example")

    assert route.call_count == 1


@respx.mock
async def test_early_renewal_still_happens_for_a_normal_lifetime():
    route = respx.post(TOKEN_URL).mock(
        side_effect=[_ok(expires_in=3600), _ok(access_token="at-2", expires_in=3600)]
    )
    client = _client(leeway_seconds=90)

    await client.get_credentials("example")
    # 3600s granted, so the 90s leeway is kept in full rather than halved.
    assert client._effective_leeway() == 90

    client._cached = client._cached.model_copy(
        update={"expires_at": client._cached.expires_at - timedelta(seconds=3560)}
    )
    assert (await client.get_credentials("example")).token == "at-2"
    assert route.call_count == 2


@respx.mock
async def test_a_token_with_no_stated_lifetime_keeps_the_configured_leeway():
    respx.post(TOKEN_URL).mock(return_value=_ok(expires_in=None))
    client = _client(leeway_seconds=90)
    await client.get_credentials("example")
    assert client._effective_leeway() == 90


@respx.mock
async def test_reset_forgets_the_lifetime_as_well_as_the_token():
    respx.post(TOKEN_URL).mock(return_value=_ok(expires_in=60))
    client = _client(leeway_seconds=90)
    await client.get_credentials("example")
    assert client._effective_leeway() == 30

    client.reset()
    assert client._effective_leeway() == 90


# -----------------------------------------------------
# Cancellation is not a transport failure
# -----------------------------------------------------


@respx.mock
async def test_a_cancelled_call_is_recorded_as_cancelled():
    """Someone else's timeout must not land in the provider's latency column."""
    respx.post(TOKEN_URL).mock(return_value=_ok())

    async def hang(request):
        await asyncio.sleep(5)
        return httpx.Response(200, json={})

    respx.get(f"{API}v1/things/t1").mock(side_effect=hang)

    calls = CallCollector()
    tool = _tool(_client(), on_call=calls)
    task = asyncio.create_task(tool.ainvoke(thing_id="t1"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    (call,) = calls.records
    assert call.outcome == "cancelled"
    assert call.error_type == "CancelledError"


# -----------------------------------------------------
# Nothing leaks
# -----------------------------------------------------


@respx.mock
async def test_no_secret_reaches_the_call_record_or_the_log_line(caplog):
    respx.post(TOKEN_URL).mock(return_value=_ok(access_token="at-very-secret"))
    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={"ok": 1}))

    calls = CallCollector()
    with caplog.at_level(logging.INFO, logger="charter"):
        await _tool(_client(), on_call=calls).ainvoke(thing_id="t1")

    blob = json.dumps(calls.records[0].to_dict()) + format_call_summary(calls)
    blob += "\n".join(r.getMessage() for r in caplog.records)

    for secret in ("at-very-secret", "s3cr3t-client", "rt-1"):
        assert secret not in blob


@respx.mock
async def test_a_failing_on_refresh_does_not_log_the_token(caplog):
    respx.post(TOKEN_URL).mock(return_value=_ok(access_token="at-very-secret"))

    def broken(credentials, refresh_token):
        raise RuntimeError("db down")

    with caplog.at_level(logging.DEBUG, logger="charter"):
        await _client(on_refresh=broken).get_credentials("example")

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "at-very-secret" not in text
    assert "s3cr3t-client" not in text


def test_the_server_declaration_carries_no_secret():
    assert "s3cr3t-client" not in repr(SERVER)
    assert "s3cr3t-client" not in repr(_client())
    assert "rt-1" not in repr(_client())


# -----------------------------------------------------
# Bounded growth
# -----------------------------------------------------


async def test_the_in_flight_map_empties_after_a_cold_start():
    """The classic leak: bound the cache, then grow a second map beside it."""
    provider = SubjectProvider(lambda subject: _client(), max_subjects=5)

    for i in range(50):
        await provider._provider_for(f"u{i}")

    assert len(provider) == 5
    assert provider._pending == {}


async def test_the_in_flight_map_empties_when_the_factory_raises():
    def explode(subject: str):
        raise RuntimeError("token store is down")

    provider = SubjectProvider(explode)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await provider._provider_for("u1")

    assert provider._pending == {}
    assert len(provider) == 0


async def test_waiters_see_the_factory_failure_rather_than_hanging():
    started = asyncio.Event()

    async def slow_explode(subject: str):
        started.set()
        await asyncio.sleep(0.02)
        raise RuntimeError("token store is down")

    provider = SubjectProvider(slow_explode)
    results = await asyncio.gather(
        *(provider._provider_for("u1") for _ in range(5)), return_exceptions=True
    )

    assert all(isinstance(r, RuntimeError) for r in results)
    assert provider._pending == {}


async def test_a_cancelled_cold_start_does_not_wedge_the_subject():
    release = asyncio.Event()

    async def slow(subject: str):
        await release.wait()
        return _client()

    provider = SubjectProvider(slow)
    task = asyncio.create_task(provider._provider_for("u1"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert provider._pending == {}
    release.set()
    assert await provider._provider_for("u1") is not None


async def test_eviction_under_churn_stays_at_the_cap():
    provider = SubjectProvider(lambda subject: _client(), max_subjects=3)
    for i in range(1000):
        await provider._provider_for(f"u{i % 40}")
    assert len(provider) == 3


def test_the_subject_survives_the_sync_invoke_path():
    """``Tool.invoke()`` runs asyncio.run(), which copies the current context.

    If it did not, `with use_subject(...)` would silently do nothing on the sync
    path and the lookup would fail — or worse, fall through to another user.
    """
    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=_ok())
        respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={"ok": 1}))

        provider = SubjectProvider(lambda subject: _client(refresh_token=f"rt-{subject}"))
        tool = _tool(provider)

        with use_subject("u1"):
            assert tool.invoke(thing_id="t1") == {"ok": 1}
            assert tool.invoke(thing_id="t1") == {"ok": 1}

        with pytest.raises(CredentialError, match="No subject is set"):
            tool.invoke(thing_id="t1")


async def test_nested_subjects_restore_the_outer_one():
    from charter.auth import current_subject

    with use_subject("outer"):
        with use_subject("inner"):
            assert current_subject.get() == "inner"
        assert current_subject.get() == "outer"


@respx.mock
async def test_one_clients_cache_is_never_handed_to_another_subject():
    """The security-critical one: A's token must never reach B."""
    respx.post(TOKEN_URL).mock(
        side_effect=lambda request: _ok(
            access_token="at-"
            + dict(p.split("=", 1) for p in request.content.decode().split("&"))[
                "refresh_token"
            ]
        )
    )

    provider = SubjectProvider(lambda subject: _client(refresh_token=f"rt-{subject}"))

    async def token_for(subject: str) -> str:
        with use_subject(subject):
            return (await provider.get_credentials("example")).token

    tokens = await asyncio.gather(*(token_for(f"u{i}") for i in range(20)))
    assert tokens == [f"at-rt-u{i}" for i in range(20)]


# -----------------------------------------------------
# Interaction with the call record
# -----------------------------------------------------


@respx.mock
async def test_a_failed_refresh_is_not_reported_as_the_api_rejecting_us():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    route = respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    with pytest.raises(CredentialError):
        await _tool(_client(), on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "credential_unavailable"
    assert call.reached_network is False
    assert not route.called


@respx.mock
async def test_the_summary_counts_unsent_calls_from_the_flag_not_a_name_list():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    tool = _tool(_client(), on_call=calls)
    for _ in range(3):
        with pytest.raises(CredentialError):
            await tool.ainvoke(thing_id="t1")

    summary = format_call_summary(calls)
    assert "3 of 3 never reached the network" in summary


@respx.mock
async def test_a_403_does_not_send_a_host_into_a_pointless_oauth_flow():
    """Observed live: Google answers 403 PERMISSION_DENIED for an IAM refusal.

    Re-consenting cannot grant it, so a host honouring `CredentialError` would
    loop: refresh, retry, 403, refresh. It has to be an APIError.
    """
    respx.post(TOKEN_URL).mock(return_value=_ok())
    respx.get(f"{API}v1/things/t1").mock(
        return_value=httpx.Response(
            403, json={"error": {"status": "PERMISSION_DENIED", "message": "Denied"}}
        )
    )

    calls = CallCollector()
    with pytest.raises(APIError):
        await _tool(_client(), on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "http_error"
    assert call.status_code == 403


@respx.mock
async def test_an_api_that_means_credentials_by_403_can_say_so():
    respx.post(TOKEN_URL).mock(return_value=_ok())
    respx.get(f"{API}v1/things/t1").mock(
        return_value=httpx.Response(403, json={"message": "Insufficient scope"})
    )

    calls = CallCollector()
    tool = _tool(_client(), on_call=calls, credential_statuses={401, 403})

    with pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "credential_rejected"
    assert call.reached_network is True


@respx.mock
async def test_the_credential_time_is_billed_to_charter_not_to_the_api():
    async def slow(request):
        await asyncio.sleep(0.05)
        return _ok()

    respx.post(TOKEN_URL).mock(side_effect=slow)
    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    await _tool(_client(), on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.credential_ms >= 45
    assert call.upstream_ms < call.credential_ms
    assert call.overhead_ms >= call.credential_ms


@respx.mock
async def test_an_unserialisable_result_does_not_break_the_call():
    """A response handler may return anything; measuring it must never be fatal."""
    respx.post(TOKEN_URL).mock(return_value=_ok())
    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))

    async def cyclic(response):
        node: dict = {}
        node["self"] = node
        return node

    calls = CallCollector()
    factory = oauth_tool_factory(
        base_url=API, provider="example", credential_provider=_client(), on_call=calls
    )
    tool = factory(
        name="things_get",
        args_schema=Args,
        method="GET",
        url_template="v1/things/{thing_id}",
        response_handler=cyclic,
    )
    returned = await tool.ainvoke(thing_id="t1")

    assert returned["self"] is returned
    (call,) = calls.records
    assert call.outcome == "ok"
    assert call.payload_bytes is not None
    assert call.context_bytes is None  # unmeasurable, not a crash
    assert call.saved_bytes is None


@respx.mock
async def test_a_cached_token_costs_nothing_on_the_second_call():
    respx.post(TOKEN_URL).mock(return_value=_ok())
    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    tool = _tool(_client(), on_call=calls)
    await tool.ainvoke(thing_id="t1")
    await tool.ainvoke(thing_id="t1")

    first, second = calls.records
    assert second.credential_ms < first.credential_ms
    assert second.credential_ms < 5


# -----------------------------------------------------
# Discovery against an unhelpful server
# -----------------------------------------------------


@respx.mock
async def test_a_useless_first_document_does_not_skip_the_second_url():
    respx.get("https://idp.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={"issuer": "https://idp.test"})
    )
    respx.get("https://idp.test/.well-known/oauth-authorization-server").mock(
        return_value=httpx.Response(200, json={"token_endpoint": "https://idp.test/token"})
    )

    server = await OAuth2Server.discover("https://idp.test")
    assert server.token_endpoint == "https://idp.test/token"


@respx.mock
async def test_a_server_offering_only_unsupported_auth_is_refused_by_name():
    respx.get(url__startswith="https://idp.test/.well-known/").mock(
        return_value=httpx.Response(
            200,
            json={
                "token_endpoint": "https://idp.test/token",
                "token_endpoint_auth_methods_supported": ["private_key_jwt"],
            },
        )
    )

    with pytest.raises(CredentialError, match="private_key_jwt"):
        await OAuth2Server.discover("https://idp.test")


@respx.mock
async def test_discovery_does_not_close_a_client_it_was_lent():
    respx.get("https://idp.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={"token_endpoint": "https://idp.test/token"})
    )

    async with httpx.AsyncClient() as client:
        await OAuth2Server.discover("https://idp.test", client=client)
        assert not client.is_closed


@respx.mock
async def test_a_refresh_does_not_close_a_client_it_was_lent():
    respx.post(TOKEN_URL).mock(return_value=_ok())

    async with httpx.AsyncClient() as client:
        await _client(client=client).get_credentials("example")
        assert not client.is_closed
