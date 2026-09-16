"""R10 — getting the grant: the authorization URL, the code exchange, the bridge.

The cases that matter are the ones a hand-rolled consent flow gets wrong: the
vendor parameter that fails silently when omitted (Google's missing refresh
token), PKCE constructed not-quite-per-RFC, a `state` compare that leaks
timing, and identity smuggled in through a params map.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from charter import (
    CharterError,
    CredentialError,
)
from charter.auth import (
    AuthorizationRequest,
    OAuth2Client,
    OAuth2Flow,
    OAuth2Server,
    TokenGrant,
    scopes_for,
    states_match,
)
from charter.auth.flow import _pkce_challenge

AUTH_URL = "https://accounts.example.com/authorize"
TOKEN_URL = "https://oauth2.example.com/token"

SERVER = OAuth2Server(
    issuer="https://example.com",
    token_endpoint=TOKEN_URL,
    authorization_endpoint=AUTH_URL,
)

GOOGLE = OAuth2Server(
    issuer="https://accounts.google.com",
    authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
    token_endpoint="https://oauth2.googleapis.com/token",
    authorization_params={"access_type": "offline", "prompt": "consent"},
)


def _flow(server: OAuth2Server = SERVER, **kw) -> OAuth2Flow:
    base = dict(
        client_id="cid",
        client_secret="csec",
        redirect_uri="https://app.example.com/oauth/callback",
    )
    base.update(kw)
    return OAuth2Flow(server, **base)


def _exchange_response(**kw) -> httpx.Response:
    body = {
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    body.update(kw)
    return httpx.Response(200, json=body)


# -----------------------------------------------------
# The server declaration (R10.1)
# -----------------------------------------------------


def test_servers_compare_equal_with_params_in_either_order():
    a = OAuth2Server(
        token_endpoint=TOKEN_URL,
        authorization_params={"access_type": "offline", "prompt": "consent"},
    )
    b = OAuth2Server(
        token_endpoint=TOKEN_URL,
        authorization_params={"prompt": "consent", "access_type": "offline"},
    )
    assert a == b


def test_authorization_params_are_read_only():
    with pytest.raises(TypeError):
        GOOGLE.authorization_params["prompt"] = "none"  # type: ignore[index]


@respx.mock
async def test_discovery_captures_the_authorization_endpoint():
    respx.get("https://login.acme.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": "https://login.acme.test",
                "token_endpoint": "https://login.acme.test/token",
                "authorization_endpoint": "https://login.acme.test/authorize",
            },
        )
    )

    server = await OAuth2Server.discover("https://login.acme.test")
    assert server.authorization_endpoint == "https://login.acme.test/authorize"


@respx.mock
async def test_a_server_discovered_without_an_authorization_endpoint_still_refreshes():
    respx.get("https://idp.test/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200, json={"token_endpoint": "https://idp.test/token"}
        )
    )
    respx.post("https://idp.test/token").mock(return_value=_exchange_response())

    server = await OAuth2Server.discover("https://idp.test")
    assert server.authorization_endpoint is None

    client = OAuth2Client(
        server, client_id="cid", client_secret="csec", refresh_token="rt-1"
    )
    assert (await client.get_credentials("example")).token == "at-1"


def test_authorize_on_a_refresh_only_server_says_what_to_declare():
    refresh_only = OAuth2Server(token_endpoint=TOKEN_URL)

    with pytest.raises(CredentialError, match="authorization_endpoint"):
        _flow(refresh_only).authorize(["scope-a"])


# -----------------------------------------------------
# authorize() (R10.2)
# -----------------------------------------------------


def test_the_authorization_url_matches_a_hand_built_google_url():
    """Golden URL: every character hand-verified against RFC 6749 §4.1.1."""
    flow = OAuth2Flow(
        GOOGLE,
        client_id="client-1.apps.googleusercontent.com",
        client_secret="csec",
        redirect_uri="https://app.example.com/oauth/google/callback",
    )

    request = flow.authorize(
        ["https://www.googleapis.com/auth/gmail.modify"],
        state="fixed-state",
        login_hint="ada@example.com",
        pkce=False,
    )

    assert request.url == (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?response_type=code"
        "&client_id=client-1.apps.googleusercontent.com"
        "&redirect_uri=https%3A%2F%2Fapp.example.com%2Foauth%2Fgoogle%2Fcallback"
        "&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify"
        "&state=fixed-state"
        "&login_hint=ada%40example.com"
        "&access_type=offline"
        "&prompt=consent"
    )
    assert request.state == "fixed-state"
    assert request.code_verifier is None


def test_the_s256_step_matches_the_rfc_7636_appendix_b_vector():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert _pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_a_fixed_entropy_source_yields_a_known_verifier_and_challenge(monkeypatch):
    monkeypatch.setattr(os, "urandom", lambda n: bytes(range(n)))

    request = _flow().authorize(["scope-a"])

    expected_verifier = (
        base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")
    )
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(expected_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    assert request.code_verifier == expected_verifier
    assert f"code_challenge={expected_challenge}" in request.url
    assert "code_challenge_method=S256" in request.url


def test_two_calls_yield_distinct_state_and_verifier():
    flow = _flow()
    first = flow.authorize(["scope-a"])
    second = flow.authorize(["scope-a"])

    assert first.state != second.state
    assert first.code_verifier != second.code_verifier


def test_the_servers_authorization_params_appear_in_the_url():
    request = _flow(GOOGLE, client_id="cid").authorize(["scope-a"])
    assert "access_type=offline" in request.url
    assert "prompt=consent" in request.url


def test_extra_params_win_over_the_servers_lore():
    request = _flow(GOOGLE, client_id="cid").authorize(
        ["scope-a"], extra_params={"prompt": "select_account"}
    )
    assert "prompt=select_account" in request.url
    assert "prompt=consent" not in request.url


@pytest.mark.parametrize(
    "key", ["client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method"]
)
def test_identity_cannot_be_smuggled_through_extra_params(key):
    with pytest.raises(ValueError, match=key):
        _flow().authorize(["scope-a"], extra_params={key: "evil"})


def test_identity_cannot_be_smuggled_through_authorization_params_either():
    server = dataclasses.replace(SERVER, authorization_params={"client_id": "evil"})
    with pytest.raises(ValueError, match="client_id"):
        _flow(server).authorize(["scope-a"])


def test_an_authorization_request_for_nothing_is_refused():
    with pytest.raises(CredentialError, match="no scopes"):
        _flow().authorize([])


def test_the_request_is_frozen():
    request = _flow().authorize(["scope-a"])
    assert isinstance(request, AuthorizationRequest)
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.url = "https://elsewhere"  # type: ignore[misc]


# -----------------------------------------------------
# states_match
# -----------------------------------------------------


def test_states_match_agrees_with_equality():
    assert states_match("abc123", "abc123") is True
    assert states_match("abc123", "abc124") is False
    assert states_match("abc123", "") is False
    assert states_match("", "") is True


def test_states_match_handles_non_ascii_input_from_the_wire():
    # The received value is attacker-controlled; a surprise TypeError from the
    # comparison would turn a failed CSRF check into a 500.
    assert states_match("abc123", "ünexpected") is False


# -----------------------------------------------------
# scopes_for
# -----------------------------------------------------


def test_scopes_for_dedupes_across_packs_preserving_first_seen_order():
    from charter.packs import gcalendar, gmail

    scopes = scopes_for([*gmail.TOOLS, *gcalendar.TOOLS])

    assert scopes == [
        "https://www.googleapis.com/auth/gmail.modify",
        # threads_delete alone; Google covers no other Gmail endpoint here with
        # anything narrower, and the consent screen widens only because that
        # tool is in the list.
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
    ]


def test_scopes_for_asks_for_full_access_only_when_a_tool_needs_it():
    """The reason a broader scope is declared per tool and not per pack."""
    from charter.packs import gmail

    everything_else = [t for t in gmail.TOOLS if t is not gmail.threads_delete]

    assert scopes_for(everything_else) == ["https://www.googleapis.com/auth/gmail.modify"]
    assert "https://mail.google.com/" in scopes_for(gmail.TOOLS)


def test_scopes_for_of_nothing_is_empty():
    assert scopes_for([]) == []


# -----------------------------------------------------
# exchange() (R10.3)
# -----------------------------------------------------


@respx.mock
async def test_the_happy_path_returns_a_grant_with_parsed_scopes():
    route = respx.post(TOKEN_URL).mock(
        return_value=_exchange_response(scope="scope-a scope-b")
    )

    grant = await _flow().exchange("code-1", code_verifier="verifier-1")

    assert isinstance(grant, TokenGrant)
    assert grant.access_token == "at-1"
    assert grant.refresh_token == "rt-1"
    assert grant.scopes == ["scope-a", "scope-b"]
    assert grant.expires_at is not None
    assert grant.raw["token_type"] == "Bearer"

    sent = dict(
        pair.split("=", 1)
        for pair in route.calls[0].request.content.decode().split("&")
    )
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "code-1"
    assert sent["code_verifier"] == "verifier-1"
    assert sent["redirect_uri"] == "https%3A%2F%2Fapp.example.com%2Foauth%2Fcallback"
    assert sent["client_id"] == "cid"
    assert sent["client_secret"] == "csec"


@respx.mock
async def test_an_absent_scope_field_parses_to_an_empty_list():
    respx.post(TOKEN_URL).mock(return_value=_exchange_response())
    grant = await _flow().exchange("code-1")
    assert grant.scopes == []


@respx.mock
async def test_client_secret_basic_puts_the_credentials_in_the_header_not_the_body():
    route = respx.post(TOKEN_URL).mock(return_value=_exchange_response())
    basic = OAuth2Server(
        token_endpoint=TOKEN_URL,
        authorization_endpoint=AUTH_URL,
        token_endpoint_auth_method="client_secret_basic",
    )

    await _flow(basic).exchange("code-1")

    request = route.calls[0].request
    assert request.headers["Authorization"].startswith("Basic ")
    assert b"client_secret" not in request.content


@respx.mock
async def test_an_oauth_error_at_400_raises():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(CredentialError, match="invalid_grant"):
        await _flow().exchange("code-used-twice")


@respx.mock
async def test_an_oauth_error_in_a_200_body_raises_too():
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"error": "invalid_client"})
    )
    with pytest.raises(CredentialError, match="invalid_client"):
        await _flow().exchange("code-1")


@respx.mock
async def test_a_failed_exchange_leaves_no_cooldown_behind():
    """Codes are single-use; a failed exchange is the host's flow to restart."""
    respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(400, json={"error": "invalid_grant"}),
            _exchange_response(),
        ]
    )

    flow = _flow()
    with pytest.raises(CredentialError):
        await flow.exchange("stale-code")
    grant = await flow.exchange("fresh-code")
    assert grant.access_token == "at-1"


@respx.mock
async def test_a_missing_refresh_token_names_the_likely_vendor_cause():
    """The highest-value error message in the module: the silent Google failure."""
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(refresh_token=None))

    with pytest.raises(CredentialError) as excinfo:
        await _flow().exchange("code-1")

    message = str(excinfo.value)
    assert "access_type" in message and "offline" in message
    assert "prompt" in message and "consent" in message


@respx.mock
async def test_expect_refresh_token_false_returns_the_grant_anyway():
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(refresh_token=None))

    grant = await _flow().exchange("code-1", expect_refresh_token=False)
    assert grant.access_token == "at-1"
    assert grant.refresh_token is None


@respx.mock
async def test_an_exchange_with_no_access_token_is_an_error():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"scope": "a"}))

    with pytest.raises(CredentialError, match="no access_token"):
        await _flow().exchange("code-1")


def test_no_secret_appears_in_the_flow_repr():
    assert "csec" not in repr(_flow())


@pytest.mark.parametrize("render", [repr, str, "{}".format], ids=["repr", "str", "format"])
def test_no_token_appears_when_a_grant_is_printed(render):
    """An f-string in a log line is where a leaked secret is hardest to recall."""
    printed = render(TokenGrant(access_token="at-secret", refresh_token="rt-secret"))
    assert "at-secret" not in printed
    assert "rt-secret" not in printed


# -----------------------------------------------------
# from_grant — the bridge to injection (R10.3)
# -----------------------------------------------------


def _grant(**kw) -> TokenGrant:
    base = dict(
        access_token="at-1",
        refresh_token="rt-1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        raw={"expires_in": 3600},
    )
    base.update(kw)
    return TokenGrant(**base)


@respx.mock
async def test_the_first_call_after_connecting_makes_zero_http_calls():
    client = OAuth2Client.from_grant(
        SERVER, _grant(), client_id="cid", client_secret="csec"
    )

    credentials = await client.get_credentials("example")

    assert credentials.token == "at-1"
    assert respx.calls.call_count == 0  # no route mocked; a request would raise


@respx.mock
async def test_after_expiry_the_seeded_client_refreshes_normally():
    route = respx.post(TOKEN_URL).mock(
        return_value=_exchange_response(access_token="at-2")
    )
    expired = _grant(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

    client = OAuth2Client.from_grant(
        SERVER, expired, client_id="cid", client_secret="csec"
    )
    credentials = await client.get_credentials("example")

    assert credentials.token == "at-2"
    sent = route.calls[0].request.content.decode()
    assert "grant_type=refresh_token" in sent
    assert "refresh_token=rt-1" in sent


async def test_a_grant_without_a_refresh_token_is_refused():
    with pytest.raises(CredentialError, match="refresh"):
        OAuth2Client.from_grant(
            SERVER, _grant(refresh_token=None), client_id="cid", client_secret="csec"
        )


@respx.mock
async def test_on_refresh_still_fires_when_the_seeded_client_refreshes():
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(refresh_token="rt-2"))
    expired = _grant(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    saved = []

    client = OAuth2Client.from_grant(
        SERVER,
        expired,
        client_id="cid",
        client_secret="csec",
        on_refresh=lambda credentials, refresh_token: saved.append(refresh_token),
    )
    await client.get_credentials("example")

    assert saved == ["rt-2"]


# -----------------------------------------------------
# Hardening — the hostile server, the careless caller
# -----------------------------------------------------


def test_the_verifier_satisfies_rfc_7636_section_4_1():
    """43–128 characters, all from the unreserved set. A server will check."""
    unreserved = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    )
    for _ in range(20):
        verifier = _flow().authorize(["scope-a"]).code_verifier
        assert verifier is not None
        assert 43 <= len(verifier) <= 128
        assert set(verifier) <= unreserved


def test_an_authorization_endpoint_that_already_has_a_query_keeps_it():
    """Entra puts a tenant in the path; other servers ship a query of their own."""
    server = dataclasses.replace(
        SERVER, authorization_endpoint="https://idp.test/authorize?realm=employees"
    )
    url = _flow(server).authorize(["scope-a"]).url

    assert url.startswith("https://idp.test/authorize?realm=employees&")
    assert "response_type=code" in url


def test_the_client_secret_never_reaches_the_authorization_url():
    """It is a redirect the user's browser sees; only the id belongs in it."""
    url = _flow().authorize(["scope-a"], state="s", login_hint="ada@example.com").url
    assert "csec" not in url


def test_scopes_may_be_any_iterable_including_a_generator():
    request = _flow().authorize(scope for scope in ("scope-a", "scope-b"))
    assert "scope=scope-a%20scope-b" in request.url


def test_a_scope_is_space_joined_and_percent_encoded_not_plus_encoded():
    """A "+" in a query string means a literal plus to a strict server."""
    request = _flow().authorize(["a b", "c"], state="s", pkce=False)
    assert "scope=a%20b%20c" in request.url
    assert "+" not in request.url


@respx.mock
async def test_a_non_json_exchange_body_is_reported_rather_than_parsed():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(502, text="<html>nope"))

    with pytest.raises(CredentialError, match="non-JSON"):
        await _flow().exchange("code-1")


@respx.mock
async def test_an_exchange_response_that_is_a_list_is_refused_cleanly():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=["at-1"]))

    with pytest.raises(CredentialError, match="non-JSON"):
        await _flow().exchange("code-1")


@respx.mock
@pytest.mark.parametrize("refresh_token", [42, {"token": "rt"}, [], ""])
async def test_a_non_string_refresh_token_is_not_mistaken_for_one(refresh_token):
    """A server sending junk must trip the missing-refresh-token guard, not pass it."""
    respx.post(TOKEN_URL).mock(
        return_value=_exchange_response(refresh_token=refresh_token)
    )

    with pytest.raises(CredentialError, match="access_type"):
        await _flow().exchange("code-1")


@respx.mock
@pytest.mark.parametrize("scope", [42, ["a", "b"], None])
async def test_a_non_string_scope_field_degrades_to_no_scopes(scope):
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(scope=scope))

    grant = await _flow().exchange("code-1")
    assert grant.scopes == []


@respx.mock
@pytest.mark.parametrize(
    "expires_in", [None, "soon", {}, [], True], ids=["null", "text", "dict", "list", "bool"]
)
async def test_a_junk_expires_in_leaves_the_grant_without_an_expiry(expires_in):
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(expires_in=expires_in))

    grant = await _flow().exchange("code-1")
    assert grant.expires_at is None


@respx.mock
@pytest.mark.parametrize(
    "expires_in",
    [10**20, -(10**20), "9" * 40, 1e308],
    ids=["huge", "hugely_negative", "huge_string", "float_inf_ish"],
)
async def test_an_absurd_expires_in_does_not_escape_as_an_arbitrary_exception(expires_in):
    """A raw OverflowError would sail past every `except CharterError` a host wrote.

    And the grant has to stay usable end to end: `from_grant` reads the same
    `expires_in` back out of `raw` to seed the leeway cap.
    """
    respx.post(TOKEN_URL).mock(return_value=_exchange_response(expires_in=expires_in))

    try:
        grant = await _flow().exchange("code-1")
        client = OAuth2Client.from_grant(
            SERVER, grant, client_id="cid", client_secret="csec"
        )
        assert (await client.get_credentials("example")).token == "at-1"
    except CharterError:
        pass  # a typed failure is acceptable; an untyped one is not


@respx.mock
async def test_an_empty_code_is_refused_before_a_request_is_made():
    route = respx.post(TOKEN_URL).mock(return_value=_exchange_response())

    with pytest.raises(CredentialError, match="authorization code"):
        await _flow().exchange("")
    assert not route.called


@respx.mock
async def test_the_exchange_never_logs_a_secret(caplog):
    respx.post(TOKEN_URL).mock(return_value=_exchange_response())

    with caplog.at_level("DEBUG", logger="charter"):
        await _flow().exchange("code-1")

    printed = "\n".join(record.getMessage() for record in caplog.records)
    for secret in ("csec", "code-1", "at-1", "rt-1"):
        assert secret not in printed


@respx.mock
async def test_a_flow_is_reusable_across_users_because_it_holds_nothing():
    """The covenant, as a test: two consecutive flows never see each other."""
    respx.post(TOKEN_URL).mock(
        side_effect=[
            _exchange_response(access_token="at-alice", refresh_token="rt-alice"),
            _exchange_response(access_token="at-bob", refresh_token="rt-bob"),
        ]
    )
    flow = _flow()

    alice_request = flow.authorize(["scope-a"], login_hint="alice@example.com")
    bob_request = flow.authorize(["scope-a"], login_hint="bob@example.com")
    alice = await flow.exchange("code-alice", code_verifier=alice_request.code_verifier)
    bob = await flow.exchange("code-bob", code_verifier=bob_request.code_verifier)

    assert alice.refresh_token == "rt-alice"
    assert bob.refresh_token == "rt-bob"
    assert alice_request.state != bob_request.state
