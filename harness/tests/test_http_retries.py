"""
Which failures the world layer retries, and which it refuses to.

A seed that dies on a burst quota costs a whole scenario-epoch, so a rate limit
has to be retried. But the retry must be narrow: Google answers *both* "you are
going too fast" and "this API is not enabled for your project" with 403, and
only the first is worth waiting out. The second has an actionable message that
should reach the caller immediately rather than 30 seconds later.

Offline; every response is served by respx.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from charter_harness.world._http import Http, WorldError

BASE = "https://api.example.test/"


def rate_limited() -> httpx.Response:
    """Google's burst-quota shape: 403, usageLimits, rateLimitExceeded."""
    return httpx.Response(
        403,
        json={
            "error": {
                "code": 403,
                "message": "Rate Limit Exceeded",
                "errors": [
                    {
                        "domain": "usageLimits",
                        "reason": "rateLimitExceeded",
                        "message": "Rate Limit Exceeded",
                    }
                ],
            }
        },
    )


def api_disabled() -> httpx.Response:
    """The 403 that must NOT be retried: the project has the API switched off."""
    return httpx.Response(
        403,
        json={
            "error": {
                "code": 403,
                "message": "Google Drive API has not been used in project 1 before or it is disabled.",
                "errors": [{"domain": "global", "reason": "accessNotConfigured"}],
            }
        },
    )


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> Http:
    # The backoff is real time; the point under test is the decision, not the wait.
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("charter_harness.world._http.asyncio.sleep", no_sleep)
    return Http(BASE, lambda: _headers(), retries=4)


async def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer test"}


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_403_is_retried_then_succeeds(http: Http) -> None:
    route = respx.get(BASE + "thing").mock(
        side_effect=[rate_limited(), rate_limited(), httpx.Response(200, json={"ok": True})]
    )
    assert await http.json("GET", "thing") == {"ok": True}
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_disabled_api_403_fails_immediately(http: Http) -> None:
    route = respx.get(BASE + "thing").mock(return_value=api_disabled())
    with pytest.raises(WorldError) as exc:
        await http.json("GET", "thing")
    assert exc.value.status == 403
    assert "has not been used in project" in exc.value.body
    assert route.call_count == 1, "a non-rate-limit 403 must not be retried"


@pytest.mark.asyncio
@respx.mock
async def test_429_and_5xx_are_still_retried(http: Http) -> None:
    route = respx.get(BASE + "thing").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert await http.json("GET", "thing") == {"ok": True}
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_rate_limit_gives_up_after_the_retry_budget(http: Http) -> None:
    route = respx.get(BASE + "thing").mock(return_value=rate_limited())
    with pytest.raises(WorldError) as exc:
        await http.json("GET", "thing")
    assert exc.value.status == 403
    assert route.call_count == 5, "four retries after the first attempt"


@pytest.mark.asyncio
@respx.mock
async def test_a_403_that_is_not_json_is_not_a_rate_limit(http: Http) -> None:
    route = respx.get(BASE + "thing").mock(
        return_value=httpx.Response(403, text="<html>nope</html>")
    )
    with pytest.raises(WorldError):
        await http.json("GET", "thing")
    assert route.call_count == 1
