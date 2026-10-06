"""Revocation — the disconnect button, declared.

Deleting a stored refresh token does not disconnect anybody: the grant stays
live at the server, with every scope it was given, and the app stays listed on
the user's account. These pin the request each shape of revocation sends, what
counts as "already gone" rather than a failure, and what a client does with a
grant once it has revoked it. What each documented server is sent is pinned in
test_docs_oauth.py, against the constants on the pages.
"""

from __future__ import annotations

import asyncio
import base64
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from charter import CredentialError, DeclarationError
from charter.auth import (
    OAuth2Client,
    OAuth2Server,
    Revocation,
    StaticTokenProvider,
    SubjectProvider,
    TokenGrant,
    revoke_token,
)

TOKEN_URL = "https://oauth2.example.com/token"
REVOKE_URL = "https://oauth2.example.com/revoke"

SERVER = OAuth2Server(token_endpoint=TOKEN_URL, revocation=Revocation(REVOKE_URL))

# A server that ends a grant given a live access token, sent as Bearer.
BEARER = OAuth2Server(
    token_endpoint=TOKEN_URL,
    revocation=Revocation(REVOKE_URL, token_type="access_token", token_header="Authorization"),
)


def _client(server: OAuth2Server = SERVER, **kw) -> OAuth2Client:
    base = dict(client_id="cid", client_secret="csec-secret", refresh_token="rt-1")
    base.update(kw)
    return OAuth2Client(server, **base)


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def _basic(request: httpx.Request) -> str:
    scheme, _, encoded = request.headers["Authorization"].partition(" ")
    assert scheme == "Basic"
    return base64.b64decode(encoded).decode()


# -----------------------------------------------------
# The declaration
# -----------------------------------------------------


def test_the_defaults_are_rfc_7009():
    revocation = Revocation(REVOKE_URL)
    assert revocation.token_type == "refresh_token"
    assert revocation.http_method == "POST"
    assert revocation.auth_method is None  # as the token endpoint
    assert revocation.token_field is None and revocation.token_header is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"endpoint": ""},
        {"endpoint": REVOKE_URL, "token_type": "id_token"},
        {"endpoint": REVOKE_URL, "auth_method": "private_key_jwt"},
        {"endpoint": REVOKE_URL, "http_method": "PUT"},
        {"endpoint": REVOKE_URL, "request_format": "xml"},
        {"endpoint": REVOKE_URL, "token_field": ""},
        {"endpoint": REVOKE_URL, "token_type": "access_token", "token_header": ""},
        # A bare string iterates as letters; each would match nothing, silently.
        {"endpoint": REVOKE_URL, "gone_errors": "invalid_auth"},
        {"endpoint": REVOKE_URL, "gone_errors": ("",)},
        {"endpoint": REVOKE_URL, "gone_statuses": (500,)},
        {"endpoint": REVOKE_URL, "gone_statuses": 422},
        {"endpoint": REVOKE_URL, "gone_statuses": (True,)},
    ],
)
def test_a_malformed_revocation_is_refused_where_it_is_written(kwargs):
    with pytest.raises(DeclarationError):
        Revocation(**kwargs)


def test_the_token_goes_in_one_place():
    with pytest.raises(DeclarationError, match="not both"):
        Revocation(
            REVOKE_URL,
            token_type="access_token",
            token_field="access_token",
            token_header="Authorization",
        )


def test_only_an_access_token_can_be_a_request_s_credential():
    with pytest.raises(DeclarationError, match="token_type='access_token'"):
        Revocation(REVOKE_URL, token_header="Authorization")


def test_a_bare_url_is_not_a_revocation():
    with pytest.raises(DeclarationError, match="Revocation"):
        OAuth2Server(token_endpoint=TOKEN_URL, revocation=REVOKE_URL)  # type: ignore[arg-type]


def test_a_bearer_token_and_basic_client_auth_cannot_share_a_header():
    with pytest.raises(DeclarationError, match="Authorization header"):
        OAuth2Server(
            token_endpoint=TOKEN_URL,
            token_endpoint_auth_method="client_secret_basic",
            revocation=Revocation(
                REVOKE_URL, token_type="access_token", token_header="Authorization"
            ),
        )
    # Declared on the revocation itself, the clash goes away.
    OAuth2Server(
        token_endpoint=TOKEN_URL,
        token_endpoint_auth_method="client_secret_basic",
        revocation=Revocation(
            REVOKE_URL,
            token_type="access_token",
            token_header="Authorization",
            auth_method="client_secret_post",
        ),
    )


# -----------------------------------------------------
# Discovery
# -----------------------------------------------------


def _metadata(**extra) -> dict:
    return {"issuer": "https://idp.example.com", "token_endpoint": TOKEN_URL, **extra}


def test_discovery_reads_the_revocation_endpoint():
    server = OAuth2Server._from_metadata(_metadata(revocation_endpoint=REVOKE_URL), "u")
    assert server.revocation == Revocation(REVOKE_URL)


def test_discovery_without_one_declares_none():
    assert OAuth2Server._from_metadata(_metadata(), "u").revocation is None


@pytest.mark.parametrize(
    ("supported", "expected"),
    [
        (["client_secret_post", "client_secret_basic"], None),  # the token endpoint's own
        (["client_secret_basic"], "client_secret_basic"),
        (["none"], "none"),
    ],
)
def test_discovery_picks_an_auth_method_the_endpoint_accepts(supported, expected):
    document = _metadata(
        revocation_endpoint=REVOKE_URL, revocation_endpoint_auth_methods_supported=supported
    )
    revocation = OAuth2Server._from_metadata(document, "u").revocation
    assert revocation == Revocation(REVOKE_URL, auth_method=expected)


def test_discovery_leaves_out_an_endpoint_it_cannot_authenticate_to():
    document = _metadata(
        revocation_endpoint=REVOKE_URL,
        revocation_endpoint_auth_methods_supported=["private_key_jwt"],
    )
    server = OAuth2Server._from_metadata(document, "u")
    assert server.revocation is None  # and the declaration still refreshes
    assert server.token_endpoint == TOKEN_URL


# -----------------------------------------------------
# revoke_token: the request, and its answer
# -----------------------------------------------------


@respx.mock
async def test_rfc_7009_sends_the_refresh_token_with_the_client_s_credentials():
    route = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    assert await revoke_token(
        SERVER, refresh_token="rt-1", access_token="at-1", client_id="cid", client_secret="csec"
    )
    request = route.calls.last.request
    # The refresh token, because revoking it ends the whole grant.
    assert _form(request) == {"token": "rt-1", "client_id": "cid", "client_secret": "csec"}


@respx.mock
async def test_an_access_token_is_revoked_when_it_is_all_there_is():
    route = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    assert await revoke_token(SERVER, access_token="at-1", client_id="cid", client_secret="csec")
    assert _form(route.calls.last.request)["token"] == "at-1"


@respx.mock
async def test_auth_none_sends_the_token_alone_and_needs_no_client():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL, revocation=Revocation(REVOKE_URL, auth_method="none")
    )
    route = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    assert await revoke_token(server, refresh_token="rt-1")
    request = route.calls.last.request
    assert _form(request) == {"token": "rt-1"}
    assert "Authorization" not in request.headers


@respx.mock
async def test_a_json_server_is_sent_json_with_basic_auth():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL,
        token_endpoint_auth_method="client_secret_basic",
        token_request_format="json",
        revocation=Revocation(REVOKE_URL),
    )
    route = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200, json={}))
    assert await revoke_token(server, refresh_token="rt-1", client_id="cid", client_secret="csec")
    request = route.calls.last.request
    assert json.loads(request.content) == {"token": "rt-1"}
    assert _basic(request) == "cid:csec"


@respx.mock
async def test_a_bearer_revocation_authenticates_with_the_token():
    route = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    assert await revoke_token(BEARER, access_token="at-1", client_id="cid", client_secret="csec")
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer at-1"
    assert _form(request) == {"client_id": "cid", "client_secret": "csec"}


@respx.mock
async def test_a_custom_header_carries_the_bare_token_and_no_body():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL,
        revocation=Revocation(
            REVOKE_URL,
            token_type="access_token",
            token_header="X-Access-Token",
            auth_method="none",
            http_method="DELETE",
        ),
    )
    route = respx.delete(REVOKE_URL).mock(return_value=httpx.Response(200, json={}))
    assert await revoke_token(server, access_token="at-1")
    request = route.calls.last.request
    assert request.headers["X-Access-Token"] == "at-1"
    assert request.content == b""


@respx.mock
async def test_the_client_id_is_filled_into_the_endpoint():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL,
        revocation=Revocation(
            "https://api.example.com/applications/{client_id}/grant",
            token_type="access_token",
            token_field="access_token",
            http_method="DELETE",
            request_format="json",
            auth_method="client_secret_basic",
        ),
    )
    route = respx.delete("https://api.example.com/applications/Iv1.abc/grant").mock(
        return_value=httpx.Response(204)
    )
    assert await revoke_token(
        server, access_token="at-1", client_id="Iv1.abc", client_secret="csec"
    )
    request = route.calls.last.request
    assert json.loads(request.content) == {"access_token": "at-1"}
    assert _basic(request) == "Iv1.abc:csec"


@pytest.mark.parametrize(
    "response",
    [
        # RFC 7009 §2.2.1, and Google's answer for a token already revoked
        httpx.Response(
            400, json={"error": "invalid_token", "error_description": "Token expired or revoked"}
        ),
        httpx.Response(400, json={"error": "invalid_grant"}),
    ],
)
@respx.mock
async def test_a_token_already_dead_is_not_a_failure(response):
    respx.post(REVOKE_URL).mock(return_value=response)
    assert (
        await revoke_token(SERVER, refresh_token="rt-1", client_id="c", client_secret="s") is False
    )


@respx.mock
async def test_the_server_s_own_dead_grant_codes_count_as_gone():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL,
        dead_grant_errors=("token_revoked",),
        revocation=Revocation(
            REVOKE_URL,
            token_type="access_token",
            token_header="Authorization",
            gone_errors=("invalid_auth",),
        ),
    )
    for code in ("token_revoked", "invalid_auth"):
        # Slack's shape: a failure inside an HTTP 200.
        respx.post(REVOKE_URL).mock(
            return_value=httpx.Response(200, json={"ok": False, "error": code})
        )
        assert (
            await revoke_token(server, access_token="at", client_id="c", client_secret="s") is False
        )


@respx.mock
async def test_a_declared_status_counts_as_gone():
    server = OAuth2Server(
        token_endpoint=TOKEN_URL, revocation=Revocation(REVOKE_URL, gone_statuses=(422,))
    )
    respx.post(REVOKE_URL).mock(
        return_value=httpx.Response(422, json={"message": "Validation Failed"})
    )
    assert await revoke_token(server, refresh_token="rt", client_id="c", client_secret="s") is False


@respx.mock
async def test_a_401_means_the_token_is_dead_when_the_token_was_the_credential():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(401))
    assert await revoke_token(BEARER, access_token="at", client_id="c", client_secret="s") is False


@respx.mock
async def test_a_401_is_a_failure_when_the_client_was_the_credential():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
    with pytest.raises(CredentialError, match="invalid_client") as caught:
        await revoke_token(SERVER, refresh_token="rt-1", client_id="c", client_secret="s")
    assert caught.value.status_code == 401
    assert caught.value.reauthorize is False
    assert caught.value.token_refused is False


@respx.mock
async def test_any_other_refusal_raises_and_redacts_what_was_sent():
    respx.post(REVOKE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": False,
                "error": "bad_client_secret",
                "error_description": "no csec-secret here",
            },
        )
    )
    with pytest.raises(CredentialError, match="bad_client_secret") as caught:
        await revoke_token(
            BEARER, access_token="at-live-token", client_id="c", client_secret="csec-secret"
        )
    assert "csec-secret" not in str(caught.value)


@respx.mock
async def test_a_server_error_raises_with_its_status():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(503, text="unavailable"))
    with pytest.raises(CredentialError, match="HTTP 503") as caught:
        await revoke_token(SERVER, refresh_token="rt", client_id="c", client_secret="s")
    assert caught.value.status_code == 503


@respx.mock
async def test_notion_s_error_shape_is_read():
    respx.post(REVOKE_URL).mock(
        return_value=httpx.Response(
            400,
            json={"object": "error", "status": 400, "code": "validation_error", "message": "bad"},
        )
    )
    with pytest.raises(CredentialError, match="validation_error — bad"):
        await revoke_token(SERVER, refresh_token="rt", client_id="c", client_secret="s")


async def test_a_server_with_no_revocation_says_what_to_do_instead():
    server = OAuth2Server(token_endpoint=TOKEN_URL)
    with pytest.raises(DeclarationError, match="deleting the stored grant"):
        await revoke_token(server, refresh_token="rt", client_id="c", client_secret="s")


async def test_an_access_token_server_will_not_take_a_refresh_token():
    with pytest.raises(CredentialError, match="access token"):
        await revoke_token(BEARER, refresh_token="rt", client_id="c", client_secret="s")


async def test_a_token_is_required():
    with pytest.raises(CredentialError, match="refresh_token or the access_token"):
        await revoke_token(SERVER, client_id="c", client_secret="s")


async def test_client_credentials_are_required_where_the_client_authenticates():
    with pytest.raises(CredentialError, match="client_id and client_secret"):
        await revoke_token(SERVER, refresh_token="rt")


# -----------------------------------------------------
# OAuth2Client.revoke
# -----------------------------------------------------


@respx.mock
async def test_a_client_revokes_its_current_refresh_token_then_will_not_refresh():
    token = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "at-1", "expires_in": 3600, "refresh_token": "rt-2"}
        )
    )
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    client = _client()
    await client.get_credentials("google")  # rotates rt-1 to rt-2

    assert await client.revoke() is True
    assert _form(revoke.calls.last.request)["token"] == "rt-2"

    with pytest.raises(CredentialError, match="revoked with revoke") as caught:
        await client.get_credentials("google")
    assert caught.value.reauthorize is True
    assert token.call_count == 1  # the token endpoint is not asked about a revoked grant


@respx.mock
async def test_a_revoked_client_stays_revoked_past_the_dead_grant_cool_down(monkeypatch):
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    client = _client()
    await client.revoke()

    import charter.auth.oauth as oauth

    monkeypatch.setattr(oauth, "monotonic", lambda: 10.0**12)
    with pytest.raises(CredentialError, match="revoked with revoke"):
        await client.get_credentials("google")


@respx.mock
async def test_reset_lifts_a_revocation():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-new", "expires_in": 3600})
    )
    client = _client()
    await client.revoke()
    client.reset()
    assert (await client.get_credentials("google")).token == "at-new"


@respx.mock
async def test_a_failed_revocation_leaves_the_client_working():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(503))
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600})
    )
    client = _client()
    with pytest.raises(CredentialError):
        await client.revoke()
    assert (await client.get_credentials("google")).token == "at-1"


@respx.mock
async def test_a_grant_already_gone_reports_false_and_still_stops_the_client():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_token"}))
    client = _client()
    assert await client.revoke() is False
    with pytest.raises(CredentialError, match="revoked with revoke"):
        await client.get_credentials("google")


async def test_a_client_for_a_server_without_revocation_raises_before_any_request():
    client = _client(OAuth2Server(token_endpoint=TOKEN_URL))
    with respx.mock(assert_all_called=False) as mock:
        with pytest.raises(DeclarationError, match="declares no revocation"):
            await client.revoke()
        assert not mock.calls


@respx.mock
async def test_an_access_token_server_is_sent_the_cached_token_without_a_refresh():
    token = respx.post(TOKEN_URL)
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    grant = TokenGrant(
        access_token="at-cached",
        refresh_token="rt-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    client = OAuth2Client.from_grant(BEARER, grant, client_id="cid", client_secret="csec")
    assert await client.revoke() is True
    assert revoke.calls.last.request.headers["Authorization"] == "Bearer at-cached"
    assert token.call_count == 0


@respx.mock
async def test_an_access_token_server_gets_a_live_token_when_the_cached_one_lapsed():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-fresh", "expires_in": 3600})
    )
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    grant = TokenGrant(
        access_token="at-stale",
        refresh_token="rt-1",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    client = OAuth2Client.from_grant(BEARER, grant, client_id="cid", client_secret="csec")
    assert await client.revoke() is True
    assert revoke.calls.last.request.headers["Authorization"] == "Bearer at-fresh"


@respx.mock
async def test_an_access_token_server_with_a_dead_grant_has_nothing_to_revoke():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    revoke = respx.post(REVOKE_URL)
    client = _client(BEARER)
    assert await client.revoke() is False
    assert revoke.call_count == 0


@respx.mock
async def test_a_loader_is_read_so_the_stored_grant_is_the_one_revoked():
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    stored = {"refresh_token": "rt-stored-by-another-process"}
    client = _client(refresh_token=lambda: stored["refresh_token"])

    assert await client.revoke() is True
    assert _form(revoke.calls.last.request)["token"] == "rt-stored-by-another-process"


@respx.mock
async def test_a_loader_holding_a_new_grant_lifts_the_revocation():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "at-again", "expires_in": 3600})
    )
    stored = {"refresh_token": "rt-1"}
    client = _client(refresh_token=lambda: stored["refresh_token"])
    await client.revoke()

    with pytest.raises(CredentialError, match="revoked with revoke"):
        await client.get_credentials("google")  # the store still holds the revoked one

    stored["refresh_token"] = "rt-reconnected"  # the user connected again
    assert (await client.get_credentials("google")).token == "at-again"


@respx.mock
async def test_the_refresh_lock_is_held_around_the_revocation():
    events: list[str] = []

    @asynccontextmanager
    async def lock():
        events.append("take")
        yield
        events.append("release")

    def revoked(request):
        events.append("revoke")
        return httpx.Response(200)

    respx.post(REVOKE_URL).mock(side_effect=revoked)
    client = _client(refresh_token=lambda: "rt-1", refresh_lock=lock)
    await client.revoke()
    assert events == ["take", "revoke", "release"]


@respx.mock
async def test_a_revocation_waits_for_a_refresh_in_flight():
    """Against a server that rotates, revoking the token a refresh is spending
    would end a grant the refresh has already moved past."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_refresh(request):
        started.set()
        await release.wait()
        return httpx.Response(
            200, json={"access_token": "at-1", "expires_in": 3600, "refresh_token": "rt-2"}
        )

    respx.post(TOKEN_URL).mock(side_effect=slow_refresh)
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    client = _client()

    refreshing = asyncio.create_task(client.get_credentials("google"))
    await started.wait()
    revoking = asyncio.create_task(client.revoke())
    await asyncio.sleep(0)
    release.set()
    await refreshing
    await revoking
    assert _form(revoke.calls.last.request)["token"] == "rt-2"


@respx.mock
async def test_a_client_credentials_client_revokes_its_token_and_can_mint_another():
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600}),
            httpx.Response(200, json={"access_token": "at-2", "expires_in": 3600}),
        ]
    )
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    client = OAuth2Client(SERVER, client_id="cid", client_secret="csec", grant="client_credentials")
    await client.get_credentials("api")

    assert await client.revoke() is True
    assert _form(revoke.calls.last.request)["token"] == "at-1"
    assert (await client.get_credentials("api")).token == "at-2"


async def test_a_client_credentials_client_with_no_token_has_nothing_to_revoke():
    client = OAuth2Client(SERVER, client_id="cid", client_secret="csec", grant="client_credentials")
    with respx.mock(assert_all_called=False) as mock:
        assert await client.revoke() is False
        assert not mock.calls


# -----------------------------------------------------
# SubjectProvider.revoke — one user, disconnected
# -----------------------------------------------------


@respx.mock
async def test_a_subject_is_built_revoked_and_forgotten():
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    built: list[str] = []

    async def for_user(subject: str):
        built.append(subject)
        return _client(refresh_token=f"rt-{subject}")

    users = SubjectProvider(for_user)
    assert await users.revoke("u1") is True
    assert _form(revoke.calls.last.request)["token"] == "rt-u1"
    assert built == ["u1"]
    assert len(users) == 0


@respx.mock
async def test_a_subject_is_forgotten_even_when_the_revocation_fails():
    respx.post(REVOKE_URL).mock(return_value=httpx.Response(503))
    users = SubjectProvider(lambda subject: _client())
    with pytest.raises(CredentialError):
        await users.revoke("u1")
    assert len(users) == 0


async def test_a_provider_without_revoke_says_how_to_revoke_instead():
    users = SubjectProvider(lambda subject: StaticTokenProvider("xoxb-1"))
    with pytest.raises(CredentialError, match="revoke_token"):
        await users.revoke("u1")
    assert len(users) == 0


async def test_a_subject_must_be_named():
    with pytest.raises(CredentialError):
        await SubjectProvider(lambda subject: _client()).revoke("")
