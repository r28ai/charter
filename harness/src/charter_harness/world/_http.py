"""
The one HTTP helper every world client is built on.

Deliberately not Charter. The world layer seeds fixtures and reads the state
back to grade a run; if it went through the packs, a bug in a pack's read path
could grade that same pack as correct. So this is httpx with three things
added: a retry on 429/5xx and on a rate-limit 403 with a jittered backoff
(fixtures should not fail on a rate-limit blip), a uniform :class:`WorldError`
carrying status and body, and :func:`eventually` for reads against
eventually-consistent APIs.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, TypeVar

import httpx

__all__ = ["Http", "WorldError", "eventually"]

T = TypeVar("T")

_RETRY_STATUSES = {429, 500, 502, 503, 504}

# Google answers a burst quota with 403 and a usageLimits reason, not 429. That
# has to be retried or a seed dies the moment several calendar scenarios run at
# once. A plain 403 (an API not enabled, a scope the token lacks) must still
# fail immediately with its own message, so the reason decides, not the status.
_RATE_LIMIT_REASONS = {"ratelimitexceeded", "userratelimitexceeded", "quotaexceeded"}


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    try:
        errors = response.json()["error"]["errors"]
    except Exception:  # a 403 that is not Google-shaped is not a rate limit
        return False
    return any(
        str(e.get("reason", "")).lower() in _RATE_LIMIT_REASONS or e.get("domain") == "usageLimits"
        for e in errors
    )


class WorldError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body[:2000]

    def __str__(self) -> str:
        base = super().__str__()
        if self.status is not None:
            base = f"HTTP {self.status} — {base}"
        return f"{base}\n{self.body}" if self.body else base


HeaderFactory = Callable[[], Awaitable[dict[str, str]]]


class Http:
    """A thin async client bound to one base URL and one way of authenticating."""

    def __init__(self, base_url: str, headers: HeaderFactory, *, timeout: float = 30.0, retries: int = 4) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self._headers = headers
        self._timeout = timeout
        self._retries = retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        ok: Callable[[httpx.Response], bool] | None = None,
    ) -> httpx.Response:
        url = path if path.startswith("http") else self.base_url + path.lstrip("/")
        client = await self._get_client()
        attempt = 0
        while True:
            merged = {**(await self._headers()), **(headers or {})}
            try:
                response = await client.request(method, url, params=params, json=json, data=data, headers=merged)
            except httpx.TimeoutException:
                if attempt >= self._retries:
                    raise
                attempt += 1
                await asyncio.sleep(min(2**attempt, 20))
                continue
            if (response.status_code in _RETRY_STATUSES or _is_rate_limited(response)) and attempt < self._retries:
                attempt += 1
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 20)
                # Jitter: the samples in flight hit the quota together, so they
                # would otherwise retry in lockstep and rebuild the same burst.
                await asyncio.sleep(delay + random.uniform(0, delay / 2))
                continue
            good = ok(response) if ok else response.is_success
            if not good:
                raise WorldError(
                    f"{method} {url} failed", status=response.status_code, body=response.text
                )
            return response

    async def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.request(method, path, **kwargs)
        if not response.content:
            return None
        return response.json()


async def eventually(
    read: Callable[[], Awaitable[T]],
    until: Callable[[T], bool],
    *,
    timeout: float = 45.0,
    interval: float = 3.0,
) -> T:
    """Call ``read`` until ``until`` accepts the value or ``timeout`` passes.

    Returns the last value either way: the judge decides what a still-unsettled
    read means, this only bounds how long the harness waits for the API.
    """
    deadline = time.monotonic() + timeout
    value = await read()
    while not until(value) and time.monotonic() < deadline:
        await asyncio.sleep(interval)
        value = await read()
    return value
