"""One pooled HTTP client per event loop, shared by every arm.

Both arms built a fresh ``httpx.AsyncClient`` for every tool call - Charter's
executor does it whenever ``ainvoke`` is not handed one, and the raw arm wrapped
each request in ``async with httpx.AsyncClient(...)``. That costs a TLS
handshake per call, and it puts the close inside a ``finally`` (or an
``__aexit__``) that cancellation can interrupt. A campaign cancels often - the
message limit, the sample time limit, a killed batch - and each interrupted
close can leave its socket in CLOSE_WAIT. They accumulate until the process
stops making progress, which is the stall that has been costing whole batches.

Sharing one pooled client removes both halves: connections are reused instead of
renegotiated, and there is no per-call close for a cancellation to orphan.

The client is keyed by event loop because an ``AsyncClient`` binds to the loop
that created it; a client cached across loops raises on first use.

**Both arms must use this.** Pooling one arm and not the other would hand it a
latency advantage and quietly corrupt the comparison.
"""

from __future__ import annotations

import asyncio

import httpx

__all__ = ["shared_client", "aclose_all"]

_CLIENTS: dict[int, httpx.AsyncClient] = {}

# Matches the per-call timeout both arms used before, with connect split out so a
# dead host fails fast instead of eating the whole budget.
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# keepalive_expiry is the load-bearing one: a pooled connection the peer has
# already closed is reaped rather than handed to the next request.
LIMITS = httpx.Limits(max_connections=64, max_keepalive_connections=16, keepalive_expiry=30.0)


def shared_client() -> httpx.AsyncClient:
    """The pooled client for the running loop, created on first use."""
    key = id(asyncio.get_running_loop())
    client = _CLIENTS.get(key)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(timeout=TIMEOUT, limits=LIMITS)
        _CLIENTS[key] = client
    return client


async def aclose_all() -> None:
    """Close the client for the running loop. Safe to call more than once."""
    client = _CLIENTS.pop(id(asyncio.get_running_loop()), None)
    if client is not None and not client.is_closed:
        await client.aclose()
