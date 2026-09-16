"""R3 — credential injection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from charter import CredentialError
from charter.auth import (
    CallbackProvider,
    CredentialProvider,
    Credentials,
    EnvTokenProvider,
    StaticTokenProvider,
)


def test_credentials_without_expiry_never_expire():
    assert Credentials(token="t").is_expired() is False


def test_expired_credentials_are_detected():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert Credentials(token="t", expires_at=past).is_expired() is True


def test_future_credentials_are_not_expired():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert Credentials(token="t", expires_at=future).is_expired() is False


def test_leeway_expires_a_token_early():
    soon = datetime.now(timezone.utc) + timedelta(seconds=30)
    creds = Credentials(token="t", expires_at=soon)
    assert creds.is_expired() is False
    assert creds.is_expired(leeway_seconds=60) is True


def test_naive_expiry_is_read_as_utc():
    """A naive timestamp must not be treated as far-future or far-past."""
    utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
    naive_past = utc_now - timedelta(hours=1)
    naive_future = utc_now + timedelta(hours=1)
    assert Credentials(token="t", expires_at=naive_past).is_expired() is True
    assert Credentials(token="t", expires_at=naive_future).is_expired() is False


# -----------------------------------------------------
# Providers
# -----------------------------------------------------


async def test_static_token_provider():
    provider = StaticTokenProvider("tok")
    creds = await provider.get_credentials("anything")
    assert creds.token == "tok"


def test_static_token_provider_rejects_an_empty_token():
    with pytest.raises(CredentialError):
        StaticTokenProvider("")


def test_static_token_provider_repr_hides_the_token():
    assert "secret" not in repr(StaticTokenProvider("secret"))


async def test_env_token_provider_reads_the_variable(monkeypatch):
    monkeypatch.setenv("CHARTER_TEST_TOKEN", "from-env")
    creds = await EnvTokenProvider("CHARTER_TEST_TOKEN").get_credentials("google")
    assert creds.token == "from-env"


async def test_env_token_provider_is_reread_per_call(monkeypatch):
    monkeypatch.setenv("CHARTER_TEST_TOKEN", "first")
    provider = EnvTokenProvider("CHARTER_TEST_TOKEN")
    assert (await provider.get_credentials("g")).token == "first"

    monkeypatch.setenv("CHARTER_TEST_TOKEN", "second")
    assert (await provider.get_credentials("g")).token == "second"


async def test_env_token_provider_raises_when_unset(monkeypatch):
    monkeypatch.delenv("CHARTER_TEST_TOKEN", raising=False)
    with pytest.raises(CredentialError) as excinfo:
        await EnvTokenProvider("CHARTER_TEST_TOKEN").get_credentials("google")
    assert excinfo.value.provider == "google"
    assert "CHARTER_TEST_TOKEN" in str(excinfo.value)


async def test_callback_provider_accepts_a_sync_function():
    provider = CallbackProvider(lambda name: Credentials(token=f"tok-{name}"))
    assert (await provider.get_credentials("google")).token == "tok-google"


async def test_callback_provider_accepts_an_async_function():
    async def fetch(name):
        return Credentials(token=f"async-{name}")

    assert (await CallbackProvider(fetch).get_credentials("gh")).token == "async-gh"


def test_callback_provider_rejects_a_non_callable():
    with pytest.raises(CredentialError):
        CallbackProvider("not callable")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "provider",
    [
        StaticTokenProvider("t"),
        EnvTokenProvider("X"),
        CallbackProvider(lambda n: Credentials(token="t")),
    ],
)
def test_shipped_providers_satisfy_the_protocol(provider):
    assert isinstance(provider, CredentialProvider)


def test_an_arbitrary_object_satisfies_the_protocol():
    """The protocol is the contract — no inheritance required."""

    class Mine:
        async def get_credentials(self, provider: str) -> Credentials:
            return Credentials(token="x")

    assert isinstance(Mine(), CredentialProvider)
