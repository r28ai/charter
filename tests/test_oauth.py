"""OAuth 2.0 without a vendor SDK — the declaration, the refresh, and the cache.

The cases that matter are the ones a hand-rolled refresh gets wrong: a stampede
of concurrent calls, a server that rotates its refresh token, and a revoked
grant that has to stop the call rather than be retried.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    CredentialError,
    Path,
    oauth_tool_factory,
)
from charter.auth import (
    Credentials,
    OAuth2Client,
    OAuth2Server,
    SubjectProvider,
    TokenGrant,
    current_subject,
    use_subject,
)

TOKEN_URL = "https://oauth2.example.com/token"
API = "https://api.example.com/"

SERVER = OAuth2Server(issuer="https://example.com", token_endpoint=TOKEN_URL)


def _client(**kw) -> OAuth2Client:
    base = dict(client_id="cid", client_secret="csec", refresh_token="rt-1")
    base.update(kw)
    return OAuth2Client(SERVER, **base)


def _token_response(**kw) -> httpx.Response:
    body = {"access_token": "at-1", "token_type": "Bearer", "expires_in": 3600}
    body.update(kw)
    return httpx.Response(200, json=body)


# -----------------------------------------------------
# The declaration
# -----------------------------------------------------


def test_a_server_needs_a_token_endpoint():
    with pytest.raises(ValueError):
        OAuth2Server(token_endpoint="")


def test_an_unknown_auth_method_is_refused_at_declaration_time():
    with pytest.raises(ValueError):
        OAuth2Server(token_endpoint=TOKEN_URL, token_endpoint_auth_method="private_key_jwt")


def test_a_server_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        SERVER.token_endpoint = "https://elsewhere.example.com/token"  # type: ignore[misc]


# -----------------------------------------------------
# Discovery
# -----------------------------------------------------


@respx.mock
async def test_discovery_reads_openid_configuration():
    respx.get("https://login.acme.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": "https://login.acme.test",
                "token_endpoint": "https://login.acme.test/oauth2/v1/token",
                "token_endpoint_auth_methods_supported": [
                    "client_secret_basic",
                    "client_secret_post",
                ],
            },
        )
    )

    server = await OAuth2Server.discover("https://login.acme.test")
    assert server.token_endpoint == "https://login.acme.test/oauth2/v1/token"
    assert server.issuer == "https://login.acme.test"
    # Both offered — take the form-body method, which more servers actually accept.
    assert server.token_endpoint_auth_method == "client_secret_post"


@respx.mock
async def test_discovery_falls_back_to_rfc_8414():
    respx.get("https://login.acme.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(404)
    )
    respx.get("https://login.acme.test/.well-known/oauth-authorization-server").mock(
        return_value=httpx.Response(
            200,
            json={
                "token_endpoint": "https://login.acme.test/token",
                "token_endpoint_auth_methods_supported": ["client_secret_basic"],
            },
        )
    )

    server = await OAuth2Server.discover("https://login.acme.test/")
    assert server.token_endpoint == "https://login.acme.test/token"
    assert server.token_endpoint_auth_method == "client_secret_basic"


@respx.mock
async def test_discovery_says_what_it_tried_when_nothing_is_published():
    respx.get(url__startswith="https://nothing.test/.well-known/").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(CredentialError) as excinfo:
        await OAuth2Server.discover("https://nothing.test")

    message = str(excinfo.value)
    assert "openid-configuration" in message
    assert "oauth-authorization-server" in message
    # The page to read next is carried as a slug and rendered into the message,
    # rather than named as a repo path nobody who installed from PyPI has.
    assert excinfo.value.docs == "auth/authorization-servers"
    assert excinfo.value.docs_url in message


@respx.mock
async def test_discovery_refuses_a_server_that_cannot_be_used():
    respx.get("https://idp.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json={"issuer": "https://idp.test"})
    )
    respx.get("https://idp.test/.well-known/oauth-authorization-server").mock(
        return_value=httpx.Response(404)
    )

    with pytest.raises(CredentialError, match="no token_endpoint"):
        await OAuth2Server.discover("https://idp.test")


# -----------------------------------------------------
# Construction guards
# -----------------------------------------------------


def test_the_refresh_grant_requires_a_grant_to_refresh():
    with pytest.raises(CredentialError, match="refreshes a grant you already hold"):
        OAuth2Client(SERVER, client_id="cid", client_secret="csec")


def test_client_credentials_needs_no_refresh_token():
    client = OAuth2Client(SERVER, client_id="cid", client_secret="csec", grant="client_credentials")
    assert client.grant == "client_credentials"


def test_a_secret_never_appears_in_the_repr():
    assert "csec" not in repr(_client())


# -----------------------------------------------------
# The refresh
# -----------------------------------------------------


@respx.mock
async def test_a_refresh_sends_the_credentials_in_the_body():
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())

    credentials = await _client().get_credentials("example")

    assert credentials.token == "at-1"
    assert credentials.expires_at is not None
    sent = dict(pair.split("=", 1) for pair in route.calls[0].request.content.decode().split("&"))
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "rt-1"
    assert sent["client_id"] == "cid"
    assert sent["client_secret"] == "csec"
    assert "Authorization" not in route.calls[0].request.headers


@respx.mock
async def test_basic_auth_moves_the_credentials_out_of_the_body():
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())
    basic = OAuth2Server(token_endpoint=TOKEN_URL, token_endpoint_auth_method="client_secret_basic")

    await OAuth2Client(
        basic, client_id="cid", client_secret="csec", refresh_token="rt-1"
    ).get_credentials("example")

    request = route.calls[0].request
    assert request.headers["Authorization"].startswith("Basic ")
    assert b"client_secret" not in request.content


@respx.mock
async def test_client_credentials_sends_no_refresh_token():
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())

    await OAuth2Client(
        SERVER,
        client_id="cid",
        client_secret="csec",
        grant="client_credentials",
        scope="read:all",
    ).get_credentials("example")

    body = route.calls[0].request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "refresh_token" not in body
    assert "scope=read" in body


@respx.mock
async def test_a_token_with_no_expiry_is_held_rather_than_treated_as_dead():
    """Notion and GitHub's classic OAuth apps issue tokens that never expire."""
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-forever"})
    )

    client = _client()
    first = await client.get_credentials("example")
    second = await client.get_credentials("example")

    assert first.expires_at is None
    assert second.token == "at-forever"
    assert route.call_count == 1


# -----------------------------------------------------
# Rotation — detected, never declared
# -----------------------------------------------------


@respx.mock
async def test_a_rotated_refresh_token_is_adopted_without_being_configured():
    respx.post(TOKEN_URL).mock(
        side_effect=[
            _token_response(refresh_token="rt-2", expires_in=-1),
            _token_response(access_token="at-2", refresh_token="rt-3"),
        ]
    )

    client = _client()
    await client.get_credentials("example")
    assert client.refresh_token == "rt-2"

    await client.get_credentials("example")
    assert client.refresh_token == "rt-3"


@respx.mock
async def test_a_server_that_does_not_rotate_keeps_the_original():
    respx.post(TOKEN_URL).mock(return_value=_token_response())

    client = _client()
    await client.get_credentials("example")
    assert client.refresh_token == "rt-1"


@respx.mock
async def test_on_refresh_receives_the_token_to_store_next_time():
    respx.post(TOKEN_URL).mock(return_value=_token_response(refresh_token="rt-2"))

    saved = []

    async def save(credentials, refresh_token):
        saved.append((credentials.token, refresh_token))

    await _client(on_refresh=save).get_credentials("example")
    assert saved == [("at-1", "rt-2")]


@respx.mock
async def test_a_failing_on_refresh_does_not_fail_the_call():
    respx.post(TOKEN_URL).mock(return_value=_token_response())

    def broken(credentials, refresh_token):
        raise RuntimeError("the database is on fire")

    credentials = await _client(on_refresh=broken).get_credentials("example")
    assert credentials.token == "at-1"


# -----------------------------------------------------
# The cache
# -----------------------------------------------------


@respx.mock
async def test_a_live_token_is_reused():
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())

    client = _client()
    for _ in range(5):
        await client.get_credentials("example")

    assert route.call_count == 1


@respx.mock
async def test_a_token_inside_the_leeway_is_renewed_early():
    """Aged, not freshly issued.

    A token is never inside its own renewal window at birth — the leeway is
    capped at half the granted lifetime precisely so that a short-lived token
    does not refresh on every call. See the hardening suite.
    """
    route = respx.post(TOKEN_URL).mock(
        side_effect=[_token_response(expires_in=600), _token_response(access_token="at-2")]
    )

    client = _client(leeway_seconds=90)
    first = await client.get_credentials("example")
    assert first.token == "at-1"

    # 590 seconds later: 10 left, inside the 90-second window.
    client._cached = first.model_copy(
        update={"expires_at": first.expires_at - timedelta(seconds=590)}
    )
    assert (await client.get_credentials("example")).token == "at-2"
    assert route.call_count == 2


@respx.mock
async def test_concurrent_calls_share_one_refresh():
    """The bug that poisons rotating grants: twelve calls, twelve refreshes."""
    calls = {"n": 0}

    async def slow(request):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return _token_response()

    respx.post(TOKEN_URL).mock(side_effect=slow)

    client = _client()
    results = await asyncio.gather(*(client.get_credentials("example") for _ in range(12)))

    assert calls["n"] == 1
    assert {c.token for c in results} == {"at-1"}


def test_the_lock_survives_successive_event_loops():
    """``Tool.invoke()`` runs asyncio.run() per call, so each call is a new loop."""
    client = _client()

    with respx.mock:
        respx.post(TOKEN_URL).mock(return_value=_token_response(expires_in=-1))
        asyncio.run(client.get_credentials("example"))
        asyncio.run(client.get_credentials("example"))  # raises on a loop-bound lock


# -----------------------------------------------------
# Failure
# -----------------------------------------------------


@respx.mock
async def test_a_revoked_grant_says_so_and_does_not_retry():
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "Token revoked."}
        )
    )

    with pytest.raises(CredentialError) as excinfo:
        await _client().get_credentials("example")

    assert "invalid_grant" in str(excinfo.value)
    assert "authorize again" in str(excinfo.value)
    assert route.call_count == 1


@respx.mock
async def test_an_error_in_a_200_body_is_still_an_error():
    """Some servers answer 200 with an OAuth error — the same trick Envelope exists for."""
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"error": "invalid_client"}))

    with pytest.raises(CredentialError, match="invalid_client"):
        await _client().get_credentials("example")


@respx.mock
async def test_a_200_with_no_access_token_is_an_error():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"token_type": "Bearer"}))

    with pytest.raises(CredentialError, match="no access_token"):
        await _client().get_credentials("example")


@respx.mock
async def test_a_non_json_body_is_reported_rather_than_parsed():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(502, text="<html>bad gateway"))

    with pytest.raises(CredentialError, match="non-JSON"):
        await _client().get_credentials("example")


# -----------------------------------------------------
# End to end, through a tool
# -----------------------------------------------------


class Args(BaseModel):
    thing_id: Annotated[str, Path()]


@respx.mock
async def test_a_tool_refreshes_and_sends_the_bearer_token():
    respx.post(TOKEN_URL).mock(return_value=_token_response())
    route = respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    factory = oauth_tool_factory(
        pack="oauth", base_url=API, provider="example", credential_provider=_client()
    )
    tool = factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )
    await tool.ainvoke(thing_id="t1")

    assert route.calls[0].request.headers["Authorization"] == "Bearer at-1"


@respx.mock
async def test_an_expired_token_from_a_provider_is_refused_before_the_request():
    """The runtime's leeway is a guard, not a refresh policy."""
    from charter.auth import StaticTokenProvider

    route = respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))
    factory = oauth_tool_factory(
        pack="oauth",
        base_url=API,
        provider="example",
        credential_provider=StaticTokenProvider(
            "stale", expires_at=datetime.now(timezone.utc) + timedelta(seconds=2)
        ),
        expiry_leeway_seconds=10,
    )
    tool = factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )

    with pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")
    assert not route.called


# -----------------------------------------------------
# A token the API refuses before it expires
# -----------------------------------------------------


def _tool(credential_provider, **factory_kw):
    factory = oauth_tool_factory(
        pack="oauth",
        base_url=API,
        provider="example",
        credential_provider=credential_provider,
        **factory_kw,
    )
    return factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )


@respx.mock
async def test_a_token_refused_before_its_expiry_is_replaced_on_the_next_call():
    """A token revoked early (an app reinstalled, a secret rotated) was sent on
    every call until the expiry it was issued with: up to a day of 401s."""
    minted = respx.post(TOKEN_URL).mock(
        side_effect=[_token_response(access_token="at-1"), _token_response(access_token="at-2")]
    )
    api = respx.get(f"{API}v1/things/t1").mock(
        side_effect=[httpx.Response(401, json={}), httpx.Response(200, json={})]
    )
    tool = _tool(_client())

    with pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")
    await tool.ainvoke(thing_id="t1")

    assert minted.call_count == 2
    sent = [call.request.headers["Authorization"] for call in api.calls]
    assert sent == ["Bearer at-1", "Bearer at-2"]


@respx.mock
async def test_an_envelope_credential_error_replaces_the_token_too():
    from charter import Envelope

    minted = respx.post(TOKEN_URL).mock(
        side_effect=[_token_response(access_token="at-1"), _token_response(access_token="at-2")]
    )
    respx.get(f"{API}v1/things/t1").mock(
        side_effect=[
            httpx.Response(200, json={"ok": False, "error": "token_revoked"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    envelope = Envelope(ok_field="ok", error_field="error", credential_errors={"token_revoked"})
    tool = _tool(_client(), envelope=envelope)

    with pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")
    await tool.ainvoke(thing_id="t1")

    assert minted.call_count == 2


@respx.mock
async def test_a_failure_that_is_not_the_tokens_keeps_it():
    from charter import APIError

    minted = respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(f"{API}v1/things/t1").mock(
        side_effect=[httpx.Response(500, json={}), httpx.Response(200, json={})]
    )
    tool = _tool(_client())

    with pytest.raises(APIError):
        await tool.ainvoke(thing_id="t1")
    await tool.ainvoke(thing_id="t1")

    assert minted.call_count == 1


@respx.mock
async def test_a_local_credential_error_keeps_the_token():
    """No store configured, say: raised before the request, so it says nothing
    about the token and must not cost a refresh."""
    minted = respx.post(TOKEN_URL).mock(return_value=_token_response())
    route = respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(200, json={}))
    configured = {"host": None}

    def base_url() -> str:
        if configured["host"] is None:
            raise CredentialError("no host yet")
        return configured["host"]

    factory = oauth_tool_factory(
        pack="oauth", base_url=base_url, provider="example", credential_provider=_client()
    )
    tool = factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )
    with pytest.raises(CredentialError, match="no host"):
        await tool.ainvoke(thing_id="t1")
    configured["host"] = API
    await tool.ainvoke(thing_id="t1")

    assert minted.call_count == 1
    assert route.called


@respx.mock
async def test_a_late_rejection_does_not_drop_the_token_that_replaced_it():
    """Two calls in flight on the old token: the first 401 replaces it, and the
    second must not throw the replacement away."""
    from charter.auth import Credentials

    respx.post(TOKEN_URL).mock(
        side_effect=[_token_response(access_token="at-1"), _token_response(access_token="at-2")]
    )
    client = _client()
    old = await client.get_credentials("example")
    client.invalidate(old)
    new = await client.get_credentials("example")

    client.invalidate(Credentials(token="at-1"))

    assert (await client.get_credentials("example")) is new


@respx.mock
async def test_a_rejection_reaches_only_the_subject_it_was_for():
    issued: dict = {}

    def mint(request: httpx.Request) -> httpx.Response:
        subject = dict(pair.split("=") for pair in request.content.decode().split("&"))[
            "refresh_token"
        ]
        issued[subject] = issued.get(subject, 0) + 1
        return _token_response(access_token=f"{subject}-{issued[subject]}")

    respx.post(TOKEN_URL).mock(side_effect=mint)
    api = respx.get(f"{API}v1/things/t1").mock(
        side_effect=[
            httpx.Response(200, json={}),
            httpx.Response(401, json={}),
            httpx.Response(200, json={}),
            httpx.Response(200, json={}),
        ]
    )
    tool = _tool(SubjectProvider(lambda subject: _client(refresh_token=subject)))

    with use_subject("bob"):
        await tool.ainvoke(thing_id="t1")
    with use_subject("alice"), pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")
    with use_subject("alice"):
        await tool.ainvoke(thing_id="t1")
    with use_subject("bob"):
        await tool.ainvoke(thing_id="t1")

    sent = [call.request.headers["Authorization"] for call in api.calls]
    assert sent == ["Bearer bob-1", "Bearer alice-1", "Bearer alice-2", "Bearer bob-1"]


@respx.mock
async def test_a_provider_whose_invalidate_raises_does_not_hide_the_401(caplog):
    from charter.auth import Credentials

    class Broken:
        async def get_credentials(self, provider):
            return Credentials(token="t")

        def invalidate(self, credentials):
            raise RuntimeError("store unreachable")

    respx.get(f"{API}v1/things/t1").mock(return_value=httpx.Response(401, json={}))

    with pytest.raises(CredentialError):
        await _tool(Broken()).ainvoke(thing_id="t1")
    assert "invalidate() raised" in caplog.text


# -----------------------------------------------------
# Many end users
# -----------------------------------------------------


def test_an_unset_subject_is_loud():
    provider = SubjectProvider(lambda subject: _client())

    with pytest.raises(CredentialError, match="No subject is set"):
        provider.current()


async def test_a_subject_never_leaks_past_its_block():
    provider = SubjectProvider(lambda subject: _client())

    with use_subject("u1"):
        assert provider.current() == "u1"

    with pytest.raises(CredentialError):
        provider.current()


async def test_a_subject_is_reset_even_when_the_block_raises():
    with pytest.raises(ValueError):
        with use_subject("u1"):
            raise ValueError("boom")

    with pytest.raises(LookupError):
        current_subject.get()


@respx.mock
async def test_each_subject_gets_its_own_provider_and_its_own_token():
    respx.post(TOKEN_URL).mock(
        side_effect=lambda request: _token_response(
            access_token="at-"
            + dict(pair.split("=", 1) for pair in request.content.decode().split("&"))[
                "refresh_token"
            ]
        )
    )

    built = []

    def for_user(subject: str):
        built.append(subject)
        return _client(refresh_token=f"rt-{subject}")

    provider = SubjectProvider(for_user)

    with use_subject("alice"):
        assert (await provider.get_credentials("example")).token == "at-rt-alice"
    with use_subject("bob"):
        assert (await provider.get_credentials("example")).token == "at-rt-bob"
    with use_subject("alice"):
        await provider.get_credentials("example")

    assert built == ["alice", "bob"]  # alice's provider was reused, not rebuilt


async def test_an_async_factory_is_supported():
    async def for_user(subject: str):
        await asyncio.sleep(0)
        return _client()

    provider = SubjectProvider(for_user)
    with use_subject("u1"):
        assert await provider._provider_for("u1") is await provider._provider_for("u1")


async def test_providers_are_capped_and_evicted_least_recently_used():
    provider = SubjectProvider(lambda subject: _client(), max_subjects=2)

    a = await provider._provider_for("a")
    await provider._provider_for("b")
    await provider._provider_for("a")  # touch a, so b is now coldest
    await provider._provider_for("c")  # evicts b

    assert len(provider) == 2
    assert await provider._provider_for("a") is a
    assert await provider._provider_for("b") is not a  # rebuilt


async def test_a_subject_can_be_forgotten():
    provider = SubjectProvider(lambda subject: _client())
    first = await provider._provider_for("u1")
    provider.forget("u1")
    assert await provider._provider_for("u1") is not first


async def test_concurrent_first_calls_for_one_subject_share_a_provider():
    async def slow(subject: str):
        await asyncio.sleep(0.02)
        return _client()

    provider = SubjectProvider(slow)
    results = await asyncio.gather(*(provider._provider_for("u1") for _ in range(5)))

    assert len({id(p) for p in results}) == 1
    assert len(provider) == 1


@respx.mock
async def test_a_permission_error_keeps_the_token():
    """A missing scope is not a bad token: dropping it cost a refresh per failing
    call, on a token no refresh could widen."""
    from charter import Envelope

    minted = respx.post(TOKEN_URL).mock(return_value=_token_response())
    respx.get(f"{API}v1/things/t1").mock(
        side_effect=[
            httpx.Response(200, json={"ok": False, "error": "missing_scope"}),
            httpx.Response(200, json={"ok": False, "error": "missing_scope"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    envelope = Envelope(ok_field="ok", error_field="error", permission_errors={"missing_scope"})
    tool = _tool(_client(), envelope=envelope)

    for _ in range(2):
        with pytest.raises(CredentialError):
            await tool.ainvoke(thing_id="t1")
    await tool.ainvoke(thing_id="t1")

    assert minted.call_count == 1


# -----------------------------------------------------
# A lifetime the server documents but does not send
# -----------------------------------------------------

# Stripe's tokens last an hour; its token response never carries expires_in.
DATED = dataclasses.replace(SERVER, default_expires_in=3600)


def _undated_response(access_token: str = "at-1") -> httpx.Response:
    return httpx.Response(200, json={"access_token": access_token, "token_type": "bearer"})


@respx.mock
async def test_a_declared_lifetime_dates_a_token_the_response_left_undated():
    respx.post(TOKEN_URL).mock(return_value=_undated_response())
    before = datetime.now(timezone.utc)

    credentials = await OAuth2Client(
        DATED, client_id="cid", client_secret="csec", refresh_token="rt-1"
    ).get_credentials("example")

    assert credentials.expires_at is not None
    assert before + timedelta(seconds=3599) <= credentials.expires_at
    assert credentials.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=3600)


@respx.mock
async def test_a_dated_token_is_renewed_before_the_hour_rather_than_refused_after_it():
    """Undated, the cache keeps a token until the API refuses it, and that call fails."""
    minted = respx.post(TOKEN_URL).mock(
        side_effect=[_undated_response("at-1"), _undated_response("at-2")]
    )
    client = OAuth2Client(DATED, client_id="cid", client_secret="csec", refresh_token="rt-1")
    await client.get_credentials("example")

    # Fifty-nine minutes on: inside the 90-second leeway, so renewed unprompted.
    cached = client._cached
    assert cached is not None and cached.expires_at is not None
    client._cached = cached.model_copy(
        update={"expires_at": datetime.now(timezone.utc) + timedelta(seconds=60)}
    )
    credentials = await client.get_credentials("example")

    assert credentials.token == "at-2"
    assert minted.call_count == 2


@respx.mock
async def test_an_expires_in_the_server_does_send_beats_the_declared_lifetime():
    respx.post(TOKEN_URL).mock(return_value=_token_response(expires_in=600))

    credentials = await OAuth2Client(
        DATED, client_id="cid", client_secret="csec", refresh_token="rt-1"
    ).get_credentials("example")

    assert credentials.expires_at is not None
    assert credentials.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=600)


@pytest.mark.parametrize("lifetime", [0, -1, True, 3600.0, "3600"])
def test_a_declared_lifetime_is_a_positive_whole_number_of_seconds(lifetime):
    with pytest.raises(ValueError, match="default_expires_in"):
        dataclasses.replace(SERVER, default_expires_in=lifetime)


# -----------------------------------------------------
# More than one process
# -----------------------------------------------------


class _RotatingServer:
    """A token endpoint that spends each refresh token on use, as Stripe's does."""

    def __init__(self, live: str = "rt-0") -> None:
        self.live = {live}
        self.issued = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sent = dict(httpx.QueryParams(request.content.decode()))["refresh_token"]
        if sent not in self.live:
            return httpx.Response(
                400,
                json={"error": "invalid_grant", "error_description": "Refresh token is spent."},
            )
        self.live.discard(sent)
        self.issued += 1
        successor = f"rt-{self.issued}"
        self.live.add(successor)
        return httpx.Response(
            200,
            json={"access_token": f"at-{self.issued}", "refresh_token": successor},
        )


class _Store:
    """The host's grants table, shared by every process."""

    def __init__(self, refresh_token: str = "rt-0") -> None:
        self.refresh_token = refresh_token
        self.reads = 0

    async def load(self) -> str:
        self.reads += 1
        return self.refresh_token

    def save(self, credentials, refresh_token) -> None:
        self.refresh_token = refresh_token


def _worker(refresh_token, store: _Store) -> OAuth2Client:
    return OAuth2Client(
        SERVER,
        client_id="cid",
        client_secret="csec",
        refresh_token=refresh_token,
        on_refresh=store.save,
    )


@respx.mock
async def test_a_second_process_holding_its_own_copy_is_refused_once_the_first_rotates():
    """Why the loader exists: the grant is fine, and this process calls it dead."""
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _Store()
    first, second = _worker("rt-0", store), _worker("rt-0", store)

    await first.get_credentials("example")
    with pytest.raises(CredentialError, match="invalid_grant"):
        await second.get_credentials("example")


@respx.mock
async def test_processes_reading_the_stored_token_take_turns_on_one_rotating_grant():
    server = _RotatingServer()
    route = respx.post(TOKEN_URL).mock(side_effect=server)
    store = _Store()
    first, second = _worker(store.load, store), _worker(store.load, store)

    tokens = []
    for worker in (first, second, first, second):
        worker.reset()  # the hour is up in that process
        tokens.append((await worker.get_credentials("example")).token)

    assert tokens == ["at-1", "at-2", "at-3", "at-4"]
    assert store.refresh_token == "rt-4"
    # Read before each refresh, not recovered after a refusal: no wasted requests.
    assert route.call_count == 4


@respx.mock
async def test_a_token_spent_between_the_read_and_the_refresh_is_read_again():
    """Another process refreshed and stored its successor in that gap."""
    server = _RotatingServer(live="rt-stored-elsewhere")
    route = respx.post(TOKEN_URL).mock(side_effect=server)
    store = _Store("rt-0")

    def read_then_lose_the_race() -> str:
        spent, store.refresh_token = store.refresh_token, "rt-stored-elsewhere"
        return spent

    reads = iter([read_then_lose_the_race, lambda: store.refresh_token])
    client = _worker(lambda: next(reads)(), store)

    credentials = await client.get_credentials("example")

    assert credentials.token == "at-1"
    assert route.call_count == 2
    assert store.refresh_token == "rt-1"


@respx.mock
async def test_a_refused_token_the_store_still_holds_is_dead_without_a_second_try():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-other"))
    store = _Store("rt-0")

    with pytest.raises(CredentialError, match="invalid_grant"):
        await _worker(store.load, store).get_credentials("example")

    assert route.call_count == 1
    assert store.reads == 2


@pytest.mark.parametrize("returned", [42, TokenGrant(access_token="at-1")])
@respx.mock
async def test_a_loader_that_returns_no_token_says_so(returned):
    respx.post(TOKEN_URL).mock(return_value=_token_response())

    with pytest.raises(CredentialError, match="loader returned no refresh token") as caught:
        await _client(refresh_token=lambda: returned).get_credentials("example")
    assert caught.value.reauthorize is False  # a bug in the loader, not a user to reconnect


@pytest.mark.parametrize("returned", [None, ""])
@respx.mock
async def test_a_store_holding_no_grant_asks_the_user_to_connect_again(returned):
    """The row is gone: the user disconnected in another process, or never connected.

    That is the reconnect button's case, not a loader failure, and nothing is
    asked of the token endpoint, which cannot bring a deleted grant back.
    """
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())

    with pytest.raises(CredentialError, match="No grant is stored") as caught:
        await _client(refresh_token=lambda: returned).get_credentials("example")
    assert caught.value.reauthorize is True
    assert caught.value.provider == "example"
    assert route.call_count == 0


@respx.mock
async def test_a_loader_that_raises_is_a_credential_error():
    respx.post(TOKEN_URL).mock(return_value=_token_response())

    def unreachable_database() -> str:
        raise ConnectionError("db down")

    with pytest.raises(CredentialError, match="ConnectionError: db down"):
        await _client(refresh_token=unreachable_database).get_credentials("example")


# -----------------------------------------------------
# Sharing the access token, not just the refresh token
# -----------------------------------------------------
#
# Stripe revokes the previous access token a few seconds after a refresh. Two
# workers that each refresh would refuse each other's next call, so a worker
# takes the token another already stored instead of refreshing again.


class _GrantStore:
    """The host's row for one grant: what on_refresh writes and the loader reads."""

    def __init__(self, refresh_token: str = "rt-0", access_token=None, expires_at=None) -> None:
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.expires_at = expires_at

    async def load(self):
        if self.access_token is None:
            return self.refresh_token
        return TokenGrant(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
        )

    def save(self, credentials, refresh_token) -> None:
        self.access_token = credentials.token
        self.expires_at = credentials.expires_at
        self.refresh_token = refresh_token


def _sharing_worker(store: _GrantStore) -> OAuth2Client:
    return OAuth2Client(
        SERVER,
        client_id="cid",
        client_secret="csec",
        refresh_token=store.load,
        on_refresh=store.save,
    )


def _in(seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


@respx.mock
async def test_a_second_worker_takes_the_stored_access_token_instead_of_refreshing():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()
    first, second = _sharing_worker(store), _sharing_worker(store)

    a = await first.get_credentials("example")
    b = await second.get_credentials("example")

    assert a.token == b.token == "at-1"
    assert route.call_count == 1


@respx.mock
async def test_a_stored_token_inside_the_leeway_is_refreshed_rather_than_taken():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore("rt-0", access_token="at-old", expires_at=_in(30))

    credentials = await _sharing_worker(store).get_credentials("example")

    assert credentials.token == "at-1"
    assert route.call_count == 1
    assert store.access_token == "at-1"


@respx.mock
async def test_a_token_the_api_refused_is_not_read_back_from_the_store():
    """The store still holds the token until a refresh replaces it."""
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore("rt-0", access_token="at-revoked", expires_at=_in(3000))
    client = _sharing_worker(store)

    refused = await client.get_credentials("example")
    assert refused.token == "at-revoked" and route.call_count == 0
    client.invalidate(refused)
    renewed = await client.get_credentials("example")

    assert renewed.token == "at-1"
    assert route.call_count == 1


@respx.mock
async def test_after_invalid_grant_the_winner_s_stored_token_is_taken_without_a_retry():
    """Another worker refreshed first: its token is in the store, so use it."""
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-1"))
    reads = 0

    async def read_then_lose_the_race():
        nonlocal reads
        reads += 1
        if reads == 1:
            return "rt-0"
        return TokenGrant(access_token="at-winner", refresh_token="rt-1", expires_at=_in(3000))

    client = OAuth2Client(
        SERVER, client_id="cid", client_secret="csec", refresh_token=read_then_lose_the_race
    )
    credentials = await client.get_credentials("example")

    assert credentials.token == "at-winner"
    assert route.call_count == 1


# -----------------------------------------------------
# A lock around the refresh
# -----------------------------------------------------
#
# RFC 9700 §4.14: when a spent refresh token comes back, a server with reuse
# detection "will revoke the active refresh token". Two workers that each read
# the store before either has written it present the same token twice, and the
# second presentation disconnects the user. Rereading after invalid_grant cannot
# help: the grant is already gone.


class _ReuseDetectingServer(_RotatingServer):
    def __init__(self, live: str = "rt-0") -> None:
        super().__init__(live)
        self.spent: set = set()
        self.revoked = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        sent = dict(httpx.QueryParams(request.content.decode()))["refresh_token"]
        if self.revoked or sent in self.spent:
            self.revoked = True
            self.live.clear()
            return httpx.Response(
                400, json={"error": "invalid_grant", "error_description": "Token reuse detected."}
            )
        response = super().__call__(request)
        if response.status_code == 200:
            self.spent.add(sent)
        return response


class _SlowStore(_GrantStore):
    """A store read whose answer can be stale by the time it arrives, as a
    database round trip's can: the read happens, then the caller waits."""

    async def load(self):
        value = await super().load()
        await asyncio.sleep(0)
        return value


def _locked_worker(store: _GrantStore, lock) -> OAuth2Client:
    return OAuth2Client(
        SERVER,
        client_id="cid",
        client_secret="csec",
        refresh_token=store.load,
        on_refresh=store.save,
        refresh_lock=lock,
    )


@respx.mock
async def test_without_a_lock_two_workers_present_one_token_and_the_server_revokes_the_grant():
    """Why the lock is mandatory against reuse detection, and why it is quiet:
    the loser takes the winner's stored access token, so both calls succeed,
    and the user is disconnected an hour later when no refresh token is left."""
    server = _ReuseDetectingServer()
    respx.post(TOKEN_URL).mock(side_effect=server)
    store = _SlowStore()

    await asyncio.gather(
        _sharing_worker(store).get_credentials("example"),
        _sharing_worker(store).get_credentials("example"),
    )

    assert server.revoked
    assert not server.live


@respx.mock
async def test_with_a_lock_the_second_worker_reads_what_the_first_stored():
    server = _ReuseDetectingServer()
    route = respx.post(TOKEN_URL).mock(side_effect=server)
    store = _SlowStore()
    across_processes = asyncio.Lock()  # stands in for a database or Redis lock

    first, second = await asyncio.gather(
        _locked_worker(store, lambda: across_processes).get_credentials("example"),
        _locked_worker(store, lambda: across_processes).get_credentials("example"),
    )

    assert first.token == second.token == "at-1"
    assert route.call_count == 1
    assert not server.revoked


@respx.mock
async def test_the_lock_is_held_until_on_refresh_has_stored_the_result():
    order: list = []
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()

    class Lock:
        async def __aenter__(self):
            order.append("lock")

        async def __aexit__(self, *exc):
            order.append("unlock")

    def save(credentials, refresh_token):
        order.append("store")
        store.save(credentials, refresh_token)

    client = OAuth2Client(
        SERVER,
        client_id="cid",
        client_secret="csec",
        refresh_token=store.load,
        on_refresh=save,
        refresh_lock=Lock,
    )
    await client.get_credentials("example")

    assert order == ["lock", "store", "unlock"]


def test_a_lock_without_a_loader_is_refused():
    """Under the lock the client must read the store; a string is a stale copy."""
    with pytest.raises(ValueError, match="refresh_lock needs refresh_token to be a GrantLoader"):
        _client(refresh_lock=asyncio.Lock)


@respx.mock
async def test_a_lock_that_cannot_be_taken_is_a_credential_error():
    route = respx.post(TOKEN_URL).mock(return_value=_token_response())

    class Unreachable:
        async def __aenter__(self):
            raise ConnectionError("redis down")

        async def __aexit__(self, *exc):
            return False

    store = _GrantStore()
    with pytest.raises(CredentialError, match="refresh lock failed: ConnectionError: redis down"):
        await _locked_worker(store, Unreachable).get_credentials("example")
    assert route.call_count == 0


# -----------------------------------------------------
# From review: the edges of the loader and the lock
# -----------------------------------------------------


@respx.mock
async def test_a_lock_that_fails_to_release_does_not_undo_a_refresh_that_worked(caplog):
    """A Redis lock whose timeout ran out mid-refresh raises on release."""
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()

    class Expired:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            raise RuntimeError("lock not owned")

    credentials = await _locked_worker(store, Expired).get_credentials("example")

    assert credentials.token == "at-1"
    assert store.refresh_token == "rt-1"
    assert "releasing the refresh lock raised" in caplog.text


@respx.mock
async def test_a_lock_that_fails_to_release_does_not_hide_the_refresh_s_own_error():
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-other"))
    store = _GrantStore()

    class Expired:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            raise RuntimeError("lock not owned")

    with pytest.raises(CredentialError, match="invalid_grant"):
        await _locked_worker(store, Expired).get_credentials("example")


@respx.mock
async def test_a_store_that_fails_after_invalid_grant_leaves_the_grant_dead_and_cooling():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-other"))
    reads = 0

    async def flaky():
        nonlocal reads
        reads += 1
        if reads > 1:
            raise ConnectionError("db down")
        return "rt-0"

    client = OAuth2Client(SERVER, client_id="cid", client_secret="csec", refresh_token=flaky)
    with pytest.raises(CredentialError, match="invalid_grant"):
        await client.get_credentials("example")
    with pytest.raises(CredentialError, match="invalid_grant"):
        await client.get_credentials("example")

    assert route.call_count == 1


@respx.mock
async def test_a_reconnected_grant_in_the_store_ends_the_cool_down_at_once():
    """The user connected again through another process; this one notices now."""
    server = _RotatingServer(live="rt-new")
    route = respx.post(TOKEN_URL).mock(side_effect=server)
    store = _GrantStore("rt-dead")
    client = _sharing_worker(store)

    with pytest.raises(CredentialError, match="invalid_grant"):
        await client.get_credentials("example")
    store.refresh_token = "rt-new"  # what the other process's exchange stored
    credentials = await client.get_credentials("example")

    assert credentials.token == "at-1"
    assert route.call_count == 2


@respx.mock
async def test_the_cool_down_holds_while_the_store_still_has_the_dead_grant():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-other"))
    store = _GrantStore("rt-dead")
    client = _sharing_worker(store)

    for _ in range(3):
        with pytest.raises(CredentialError, match="invalid_grant"):
            await client.get_credentials("example")

    assert route.call_count == 1


@respx.mock
async def test_from_grant_takes_a_loader_and_a_lock():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer(live="rt-1"))
    store = _GrantStore("rt-1", access_token="at-0", expires_at=_in(3000))
    grant = TokenGrant(access_token="at-0", refresh_token="rt-1", expires_at=_in(3000))

    client = OAuth2Client.from_grant(
        SERVER,
        grant,
        client_id="cid",
        client_secret="csec",
        refresh_token=store.load,
        on_refresh=store.save,
        refresh_lock=asyncio.Lock,
    )
    assert (await client.get_credentials("example")).token == "at-0"
    client.invalidate(Credentials(token="at-0"))
    assert (await client.get_credentials("example")).token == "at-1"
    assert route.call_count == 1


@respx.mock
async def test_a_declared_short_lifetime_lets_a_worker_take_a_stored_token_inside_ninety_seconds():
    """The leeway is capped at half the lifetime from the first call, not after a refresh."""
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    short = dataclasses.replace(SERVER, default_expires_in=120)
    store = _GrantStore("rt-0", access_token="at-stored", expires_at=_in(80))

    client = OAuth2Client(
        short,
        client_id="cid",
        client_secret="csec",
        refresh_token=store.load,
        on_refresh=store.save,
    )

    assert (await client.get_credentials("example")).token == "at-stored"
    assert route.call_count == 0


def test_a_loader_with_the_client_credentials_grant_is_refused():
    with pytest.raises(ValueError, match="client_credentials grant has none to read"):
        OAuth2Client(
            SERVER,
            client_id="cid",
            client_secret="csec",
            grant="client_credentials",
            refresh_token=lambda: "rt",
        )


# -----------------------------------------------------
# When on_refresh fails to store a refresh
# -----------------------------------------------------
#
# The server has spent the refresh token the store still holds, and the one
# that works exists only in this client. Read back before the next refresh, the
# store's copy replaced it: one failed write, and against a server that refuses
# a spent token (Stripe, GitHub, Notion) the user had to connect again.


def _failing_writes(store: _GrantStore, failures: int):
    """An on_refresh whose first ``failures`` writes raise, as a database blip would."""
    attempts: list = []

    def save(credentials, refresh_token) -> None:
        attempts.append(refresh_token)
        if len(attempts) <= failures:
            raise ConnectionError("database unavailable")
        store.save(credentials, refresh_token)

    return save, attempts


async def _stored_again(client: OAuth2Client) -> None:
    """Wait for the background try at storing a lost refresh again, if one is running."""
    task = client._restoring
    if task is not None:
        await asyncio.wait([task])


def _writing_client(store: _GrantStore, save) -> OAuth2Client:
    return OAuth2Client(
        SERVER, client_id="cid", client_secret="csec", refresh_token=store.load, on_refresh=save
    )


@respx.mock
async def test_a_store_on_refresh_failed_to_write_is_not_read_back_over_the_newer_token():
    route = respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()
    save, attempts = _failing_writes(store, failures=2)  # the write, and the try again
    client = _writing_client(store, save)

    first = await client.get_credentials("example")
    await _stored_again(client)
    assert store.refresh_token == "rt-0"  # both lost
    client.invalidate(first)  # or the hour is up

    assert (await client.get_credentials("example")).token == "at-2"
    assert route.call_count == 2
    assert store.refresh_token == "rt-2"  # and that refresh's write caught the store up


@respx.mock
async def test_a_refresh_on_refresh_failed_to_store_is_stored_again_at_once():
    """Until it is, every other process reads a spent refresh token from the store."""
    server = _RotatingServer()
    respx.post(TOKEN_URL).mock(side_effect=server)
    store = _GrantStore()
    save, attempts = _failing_writes(store, failures=1)
    client = _writing_client(store, save)

    assert (await client.get_credentials("example")).token == "at-1"
    await _stored_again(client)

    assert attempts == ["rt-1", "rt-1"]
    assert (store.refresh_token, store.access_token) == ("rt-1", "at-1")
    assert client._unstored is None
    # Another process now takes the grant from the store rather than presenting rt-0.
    assert (await _sharing_worker(store).get_credentials("example")).token == "at-1"
    assert server.issued == 1


@respx.mock
async def test_a_store_still_down_is_tried_again_after_the_back_off_and_never_holds_up_a_call(
    caplog,
):
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()
    save, attempts = _failing_writes(store, failures=2)
    client = _writing_client(store, save)

    with caplog.at_level("WARNING", logger="charter"):
        await client.get_credentials("example")
        await _stored_again(client)
    assert attempts == ["rt-1", "rt-1"]  # the write, and the try at once
    assert "trying again" in caplog.text

    for _ in range(3):  # within the back-off: the cached token, and no write
        assert (await client.get_credentials("example")).token == "at-1"
    await _stored_again(client)
    assert attempts == ["rt-1", "rt-1"]

    client._restore_after = 0.0  # the back-off has passed
    assert (await client.get_credentials("example")).token == "at-1"
    await _stored_again(client)
    assert attempts == ["rt-1", "rt-1", "rt-1"]
    assert (store.refresh_token, client._unstored) == ("rt-1", None)


@respx.mock
async def test_a_store_that_hangs_does_not_hold_up_a_call_with_a_token_in_hand():
    """Storing again needs the store; the call that finds it due does not."""
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()
    hanging = asyncio.Event()
    writes: list = []

    async def save(credentials, refresh_token):
        writes.append(refresh_token)
        if len(writes) == 1:
            raise ConnectionError("database unavailable")
        await hanging.wait()  # the database stopped answering

    client = _writing_client(store, save)
    await client.get_credentials("example")

    client._restore_after = 0.0
    token = await asyncio.wait_for(client.get_credentials("example"), timeout=1)
    assert token.token == "at-1"
    hanging.set()
    await _stored_again(client)


@pytest.mark.parametrize(
    "now_stored", ["rt-reconnected", None], ids=["user connected again", "user disconnected"]
)
@respx.mock
async def test_a_store_that_has_moved_on_is_not_written_over_with_the_lost_refresh(now_stored):
    respx.post(TOKEN_URL).mock(side_effect=_RotatingServer())
    store = _GrantStore()
    save, attempts = _failing_writes(store, failures=99)
    client = _writing_client(store, save)
    await client.get_credentials("example")
    await _stored_again(client)
    assert attempts == ["rt-1", "rt-1"]
    store.refresh_token = now_stored  # written by another process meanwhile

    client._restore_after = 0.0
    assert (await client.get_credentials("example")).token == "at-1"
    await _stored_again(client)
    assert attempts == ["rt-1", "rt-1"]  # not written over the store
    assert store.refresh_token == now_stored
    assert client._unstored is None
