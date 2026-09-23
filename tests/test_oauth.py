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
    OAuth2Client,
    OAuth2Server,
    SubjectProvider,
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
