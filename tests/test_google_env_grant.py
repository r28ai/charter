"""The Google packs renew a grant they find in the environment.

``$GOOGLE_ACCESS_TOKEN`` lasts about an hour, so a server started from it dies an
hour in. ``$GOOGLE_TOKEN_FILE``, or ``$GOOGLE_REFRESH_TOKEN`` with the client id
and secret, is a grant the packs renew for themselves — which is what lets
``python -m charter.mcp`` stay up.
"""

from __future__ import annotations

import json
import os
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from charter.packs import gcalendar, gmail
from charter.packs._google import ENV_GRANT
from charter.types.errors import CredentialError

TOKEN_URL = "https://oauth2.googleapis.com/token"
LABELS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


@pytest.fixture(autouse=True)
def _unconfigured(monkeypatch):
    for pack in (gmail, gcalendar):
        monkeypatch.setattr(pack._credentials, "_provider", None)
    for var in ("GOOGLE_ACCESS_TOKEN", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
        monkeypatch.delenv(var, raising=False)


def _token_route(*tokens: str):
    return respx.post(TOKEN_URL).mock(
        side_effect=[
            httpx.Response(
                200, json={"access_token": t, "expires_in": 3599, "token_type": "Bearer"}
            )
            for t in tokens
        ]
    )


def _form(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def _trio(monkeypatch, refresh_token="1//refresh"):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "shh")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", refresh_token)


async def test_the_three_variables_are_a_grant_the_pack_renews(monkeypatch):
    _trio(monkeypatch)
    with respx.mock:
        token = _token_route("at-1")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert labels.calls.last.request.headers["authorization"] == "Bearer at-1"
    assert _form(token.calls.last.request) == {
        "grant_type": "refresh_token",
        "refresh_token": "1//refresh",
        "client_id": "client.apps.googleusercontent.com",
        "client_secret": "shh",
    }


async def test_a_grant_wins_over_a_raw_access_token(monkeypatch):
    """A raw token left in the environment is usually stale; a grant never is."""
    _trio(monkeypatch)
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "ya29.stale")
    with respx.mock:
        _token_route("at-fresh")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert labels.calls.last.request.headers["authorization"] == "Bearer at-fresh"


async def test_the_raw_token_still_works_alone(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "ya29.alone")
    with respx.mock:
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert labels.calls.last.request.headers["authorization"] == "Bearer ya29.alone"


async def test_one_refresh_serves_every_google_pack(monkeypatch):
    _trio(monkeypatch)
    with respx.mock:
        token = _token_route("at-shared")
        respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        events = respx.get(EVENTS_URL).mock(return_value=httpx.Response(200, json={}))
        await gmail.labels_list.ainvoke(userId="me")
        await gcalendar.events_list.ainvoke(calendar_id="primary")

    assert token.call_count == 1
    assert events.calls.last.request.headers["authorization"] == "Bearer at-shared"


@pytest.mark.parametrize(
    "contents",
    [
        # google-auth's Credentials.to_json(): Hermes Agent's google_token.json,
        # the token.json of Google's quickstarts
        {
            "token": "ya29.cached",
            "refresh_token": "1//from-file",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client.apps.googleusercontent.com",
            "client_secret": "shh",
            "scopes": ["https://www.googleapis.com/auth/gmail.modify"],
            "universe_domain": "googleapis.com",
            "account": "",
            "expiry": "2026-10-02T09:00:00Z",
        },
        # gcloud auth application-default login
        {
            "account": "",
            "client_id": "client.apps.googleusercontent.com",
            "client_secret": "shh",
            "quota_project_id": "my-project",
            "refresh_token": "1//from-file",
            "type": "authorized_user",
            "universe_domain": "googleapis.com",
        },
    ],
    ids=["google-auth-to-json", "gcloud-adc"],
)
async def test_an_authorized_user_file_is_a_grant(monkeypatch, tmp_path, contents):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(contents))
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(path))
    with respx.mock:
        token = _token_route("at-from-file")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert _form(token.calls.last.request)["refresh_token"] == "1//from-file"
    assert labels.calls.last.request.headers["authorization"] == "Bearer at-from-file"


async def test_the_file_path_may_start_with_a_tilde(monkeypatch, tmp_path):
    """A client config passes the value through verbatim, with no shell to expand it."""
    (tmp_path / "token.json").write_text(
        json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "1//t"})
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", "~/token.json")
    with respx.mock:
        _token_route("at-tilde")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert labels.calls.last.request.headers["authorization"] == "Bearer at-tilde"


async def test_reauthorizing_needs_no_restart(monkeypatch, tmp_path):
    """The file is read per call; a different grant in it builds a new client."""
    path = tmp_path / "token.json"
    path.write_text(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "1//old"}))
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(path))
    with respx.mock:
        token = _token_route("at-old", "at-new")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")
        await gmail.labels_list.ainvoke(userId="me")
        assert token.call_count == 1  # cached between calls

        path.write_text(
            json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "1//new"})
        )
        await gmail.labels_list.ainvoke(userId="me")

    assert _form(token.calls.last.request)["refresh_token"] == "1//new"
    assert labels.calls.last.request.headers["authorization"] == "Bearer at-new"


@pytest.mark.parametrize(
    "contents, says",
    [
        ({"installed": {"client_id": "c", "client_secret": "s"}}, "OAuth client file"),
        ({"web": {"client_id": "c", "client_secret": "s"}}, "OAuth client file"),
        ({"type": "service_account", "private_key": "k"}, "service account key"),
        ({"client_id": "c", "client_secret": "s"}, "has no refresh_token"),
        (["not", "an", "object"], "not a JSON object"),
    ],
)
async def test_a_file_that_is_not_a_grant_says_what_it_is(monkeypatch, tmp_path, contents, says):
    path = tmp_path / "token.json"
    path.write_text(json.dumps(contents))
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(path))
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "ya29.would-hide-the-mistake")
    with respx.mock, pytest.raises(CredentialError, match=says):
        await gmail.labels_list.ainvoke(userId="me")


async def test_a_missing_or_garbled_file_is_an_error_not_a_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "ya29.would-hide-the-mistake")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "absent.json"))
    with pytest.raises(CredentialError, match="cannot be read"):
        await gmail.labels_list.ainvoke(userId="me")

    (tmp_path / "garbled.json").write_text("{not json")
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(tmp_path / "garbled.json"))
    with pytest.raises(CredentialError, match="not JSON"):
        await gmail.labels_list.ainvoke(userId="me")


async def test_a_refresh_token_without_its_client_names_what_is_missing(monkeypatch):
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "1//orphan")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "c")
    with pytest.raises(CredentialError, match=r"\$GOOGLE_CLIENT_SECRET is not"):
        await gmail.labels_list.ainvoke(userId="me")


async def test_with_nothing_set_the_error_names_every_way_in():
    assert not gmail._credentials.is_configured
    with pytest.raises(CredentialError) as excinfo:
        await gmail.labels_list.ainvoke(userId="me")
    message = str(excinfo.value)
    for var in ("GOOGLE_TOKEN_FILE", "GOOGLE_REFRESH_TOKEN", "GOOGLE_ACCESS_TOKEN"):
        assert f"${var}" in message


def test_a_grant_counts_as_configured(monkeypatch):
    _trio(monkeypatch)
    assert gmail._credentials.is_configured
    assert gmail._credentials.env_grant is ENV_GRANT


def _grant_file(tmp_path, mode):
    path = tmp_path / "token.json"
    path.write_text(json.dumps({"client_id": "c", "client_secret": "s", "refresh_token": "1//t"}))
    path.chmod(mode)
    return path


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
async def test_a_file_others_can_read_warns_once(monkeypatch, tmp_path, caplog):
    """Like kubectl with a group-readable kubeconfig: a warning, never a refusal.

    The file is read on every call, so the warning has to be once per path or a
    busy server would print it with every tool call.
    """
    path = _grant_file(tmp_path, 0o644)
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(path))
    with caplog.at_level("WARNING", logger="charter"), respx.mock:
        _token_route("at-1")
        labels = respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")
        await gmail.labels_list.ainvoke(userId="me")

    assert labels.call_count == 2  # warned, and still served
    warnings = [r.getMessage() for r in caplog.records if "refresh token" in r.getMessage()]
    assert len(warnings) == 1
    assert f"chmod 600 {path}" in warnings[0] and "644" in warnings[0]
    assert oct(path.stat().st_mode & 0o777) == oct(0o644)  # never changed for the user


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission bits")
async def test_an_owner_only_file_is_silent(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("GOOGLE_TOKEN_FILE", str(_grant_file(tmp_path, 0o600)))
    with caplog.at_level("WARNING", logger="charter"), respx.mock:
        _token_route("at-1")
        respx.get(LABELS_URL).mock(return_value=httpx.Response(200, json={"labels": []}))
        await gmail.labels_list.ainvoke(userId="me")

    assert not [r for r in caplog.records if "refresh token" in r.getMessage()]
