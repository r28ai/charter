#!/usr/bin/env python
"""Several real processes, one user's Stripe grant, every refresh due at once.

Deliberately not a test, like ``live_oauth_check.py``: it calls Stripe. What it
proves is the multi-process path end to end, under true concurrency: workers
that each build their client the way the docs say, share one stored grant, and
find it due at the same moment, again and again.

Stripe is the harshest server for this. A refresh revokes the previous access
token within seconds, so a worker left holding it fails its next call, and
every failure is counted. Test mode costs nothing.

::

    # four processes on this machine, a SQLite store and a file lock
    uv run python scripts/live_oauth_stress.py run --store sqlite:///tmp/grant.db --workers 4

    # one worker per machine against Postgres, the lock the docs show
    uv run python scripts/live_oauth_stress.py seed   --store postgresql://...
    uv run python scripts/live_oauth_stress.py worker --store postgresql://... --name a ...
    uv run python scripts/live_oauth_stress.py report --store postgresql://... --run ...

``--mode`` picks the client each worker builds:

- ``documented``: a ``GrantLoader`` returning the whole grant, and a
  ``refresh_lock``. The setup the docs prescribe; it should lose no call.
- ``no-lock``: the loader without the lock. Workers due together refresh
  together, and Stripe revokes the tokens they finished with first.
- ``copy``: each worker holds its own copy of the refresh token, the way the
  guides used to show. The first refresh spends everyone else's.

The two broken modes exist so a clean run means something: a harness that
cannot see them fail cannot vouch for the one that passes.

The access token really lasts an hour. ``--lifetime`` declares it shorter, so
the workers renew every half lifetime instead of every 59 minutes. The grant
is read from and written back to ``$CHARTER_LIVE_DIR/stripe.json``, where
``live_oauth_check.py connect --provider stripe`` left it. Nothing writes to
the Stripe account, and nothing prints a token.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import fcntl
import hashlib
import json
import os
import random
import socket
import sqlite3
import stat
import subprocess
import sys
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path as FsPath
from typing import Any, AsyncIterator, Optional

from charter.auth import OAuth2Client, OAuth2Server, TokenGrant
from charter.auth.credentials import Credentials
from charter.types.errors import CharterError

STRIPE_APPS = OAuth2Server(
    issuer="https://marketplace.stripe.com",
    authorization_endpoint="https://marketplace.stripe.com/oauth/v2/authorize",
    token_endpoint="https://api.stripe.com/v1/oauth/token",
    token_endpoint_auth_method="secret_key_basic",
    uses_scopes=False,
    default_expires_in=3600,
)

READS = (("balance_retrieve", {}), ("customers_list", {"limit": 1}))
KEY = "stripe"

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS grants (key TEXT PRIMARY KEY, client_id TEXT,"
    " access_token TEXT, refresh_token TEXT, expires_at TEXT, version INTEGER,"
    " updated_by TEXT)",
    "CREATE TABLE IF NOT EXISTS events (run TEXT, worker TEXT, t DOUBLE PRECISION,"
    " kind TEXT, detail TEXT)",
)


def sha8(token: Optional[str]) -> Optional[str]:
    return hashlib.sha256(token.encode()).hexdigest()[:8] if token else None


# -----------------------------------------------------
# Stores. Each is the host's database, and each lock is the host's lock.
# -----------------------------------------------------


class SqliteStore:
    """A file on this machine, and ``flock`` on a file beside it."""

    def __init__(self, url: str) -> None:
        self.path = url.removeprefix("sqlite:///")
        self.lock_path = self.path + ".lock"

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    async def open(self) -> None:
        def create() -> None:
            with self._db() as db:
                for statement in SCHEMA:
                    db.execute(statement)

        await asyncio.to_thread(create)

    async def close(self) -> None:
        pass

    async def load(self) -> dict[str, Any]:
        def read() -> dict[str, Any]:
            db = self._db()
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM grants WHERE key = ?", (KEY,)).fetchone()
            db.close()
            return dict(row)

        return await asyncio.to_thread(read)

    async def save(self, row: dict[str, Any]) -> None:
        def write() -> None:
            db = self._db()
            db.execute(
                "INSERT INTO grants VALUES (:key, :client_id, :access_token, :refresh_token,"
                " :expires_at, :version, :updated_by) ON CONFLICT(key) DO UPDATE SET"
                " access_token = excluded.access_token, refresh_token = excluded.refresh_token,"
                " expires_at = excluded.expires_at, version = grants.version + 1,"
                " updated_by = excluded.updated_by",
                {"key": KEY, "client_id": None, "version": 1, **row},
            )
            db.close()

        await asyncio.to_thread(write)

    def lock(self) -> Any:
        @asynccontextmanager
        async def held() -> AsyncIterator[None]:
            fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, stat.S_IRUSR | stat.S_IWUSR)
            try:
                await asyncio.to_thread(fcntl.flock, fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

        return held

    async def event(self, run: str, worker: str, kind: str, detail: dict[str, Any]) -> None:
        def write() -> None:
            db = self._db()
            db.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                (run, worker, time.time(), kind, json.dumps(detail)),
            )
            db.close()

        await asyncio.to_thread(write)

    async def events(self, run: str) -> list[tuple[str, float, str, dict[str, Any]]]:
        def read() -> list[tuple[str, float, str, dict[str, Any]]]:
            db = self._db()
            rows = db.execute(
                "SELECT worker, t, kind, detail FROM events WHERE run = ? ORDER BY t", (run,)
            ).fetchall()
            db.close()
            return [(w, t, k, json.loads(d)) for w, t, k, d in rows]

        return await asyncio.to_thread(read)


class PostgresStore:
    """Postgres through asyncpg, locked exactly as docs/auth/oauth-flow.md shows."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pool: Any = None
        self.lock_pool: Any = None

    async def open(self) -> None:
        import asyncpg  # only the Postgres store needs it

        self.pool = await asyncpg.create_pool(self.url, min_size=1, max_size=4)
        # The lock's connections come from a pool of their own. The lock holds
        # one while the loader and on_refresh take others, so from one shared
        # pool, as many grants refreshing at once as it has connections would
        # each hold one and wait for another, forever.
        self.lock_pool = await asyncpg.create_pool(self.url, min_size=1, max_size=4)
        async with self.pool.acquire() as conn:
            for statement in SCHEMA:
                await conn.execute(statement)

    async def close(self) -> None:
        await self.pool.close()
        await self.lock_pool.close()

    async def load(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            return dict(await conn.fetchrow("SELECT * FROM grants WHERE key = $1", KEY))

    async def save(self, row: dict[str, Any]) -> None:
        full = {"client_id": None, **row}
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO grants VALUES ($1, $2, $3, $4, $5, 1, $6) ON CONFLICT (key) DO"
                " UPDATE SET access_token = $3, refresh_token = $4, expires_at = $5,"
                " version = grants.version + 1, updated_by = $6",
                KEY,
                full["client_id"],
                full["access_token"],
                full["refresh_token"],
                full["expires_at"],
                full["updated_by"],
            )

    def lock(self) -> Any:
        pool = self.lock_pool

        @asynccontextmanager
        async def held() -> AsyncIterator[None]:
            async with pool.acquire() as conn, conn.transaction():
                # Postgres: released when the transaction ends, whatever happens.
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"user-1:{KEY}")
                yield

        return held

    async def event(self, run: str, worker: str, kind: str, detail: dict[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO events VALUES ($1, $2, $3, $4, $5)",
                run,
                worker,
                time.time(),
                kind,
                json.dumps(detail),
            )

    async def events(self, run: str) -> list[tuple[str, float, str, dict[str, Any]]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT worker, t, kind, detail FROM events WHERE run = $1 ORDER BY t", run
            )
        return [(r["worker"], r["t"], r["kind"], json.loads(r["detail"])) for r in rows]


def open_store(url: str) -> Any:
    if url.startswith("sqlite:///"):
        return SqliteStore(url)
    if url.startswith(("postgres://", "postgresql://")):
        return PostgresStore(url)
    sys.exit(f"Unknown store {url!r}: sqlite:///path or postgresql://…")


# -----------------------------------------------------
# The grant on disk, where live_oauth_check.py keeps it
# -----------------------------------------------------


def live_file() -> FsPath:
    root = FsPath(os.environ.get("CHARTER_LIVE_DIR", FsPath.home() / ".charter/live"))
    return root / "stripe.json"


async def seed(store: Any) -> None:
    """Store the live grant, dated now, so the first call every worker makes is due."""
    row = json.loads(live_file().read_text())
    await store.open()
    await store.save(
        {
            "client_id": row["client_id"],
            "access_token": row.get("access_token"),
            "refresh_token": row["refresh_token"],
            "expires_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "seed",
        }
    )
    await store.close()


async def write_back(store: Any) -> None:
    """Return the newest grant to the live file, so the next live check holds a current one."""
    await store.open()
    row = await store.load()
    await store.close()
    path = live_file()
    data = {
        **json.loads(path.read_text()),
        "access_token": row["access_token"],
        "refresh_token": row["refresh_token"],
        "expires_at": row["expires_at"],
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(data))


# -----------------------------------------------------
# A worker: one process, built the way a server process builds its client
# -----------------------------------------------------


async def worker(args: argparse.Namespace) -> None:
    from charter.packs import stripe

    store = open_store(args.store)
    await store.open()
    secret = os.environ["STRIPE_SECRET_KEY"]
    server = dataclasses.replace(STRIPE_APPS, default_expires_in=args.lifetime)
    initial = await store.load()
    lock_waits: list[float] = []

    async def stored_grant() -> TokenGrant:
        row = await store.load()
        expires_at = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
        return TokenGrant(
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=expires_at,
        )

    async def on_refresh(credentials: Credentials, refresh_token: Optional[str]) -> None:
        expires_at = credentials.expires_at.isoformat() if credentials.expires_at else None
        await store.save(
            {
                "access_token": credentials.token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "updated_by": args.name,
            }
        )
        await store.event(args.run, args.name, "refresh", {"token": sha8(credentials.token)})

    def timed(factory: Any) -> Any:
        @asynccontextmanager
        async def held() -> AsyncIterator[None]:
            started = time.monotonic()
            async with factory():
                lock_waits.append(time.monotonic() - started)
                yield

        return held

    if args.mode == "copy":
        refresh_token: Any = initial["refresh_token"]
        lock = None
    else:
        refresh_token = stored_grant
        lock = timed(store.lock()) if args.mode == "documented" else None

    client = OAuth2Client(
        server,
        client_id=initial["client_id"],
        client_secret=secret,
        refresh_token=refresh_token,
        on_refresh=on_refresh,
        refresh_lock=lock,
    )
    stripe.configure(credential_provider=client)

    import charter.auth.oauth as oauth_module

    code = hashlib.sha256(FsPath(oauth_module.__file__).read_bytes()).hexdigest()[:12]
    await store.event(
        args.run,
        args.name,
        "start",
        {"host": socket.gethostname(), "region": os.environ.get("FLY_REGION"), "code": code},
    )

    while time.time() < args.start_at:
        await asyncio.sleep(0.05)

    ok = failed = 0
    tokens: set[str] = set()
    failures: Counter[str] = Counter()

    async def caller() -> None:
        nonlocal ok, failed
        while time.time() < args.until:
            name, call_args = random.choice(READS)
            try:
                await getattr(stripe, name).ainvoke(call_args)
                ok += 1
                cached = client._cached
                if cached is not None:
                    tokens.add(sha8(cached.token) or "")
            except CharterError as exc:
                failed += 1
                kind = type(exc).__name__
                status = getattr(exc, "status_code", None)
                failures[f"{kind} {status}"] += 1
                await store.event(
                    args.run,
                    args.name,
                    "fail",
                    {
                        "error": kind,
                        "status": status,
                        "reauthorize": getattr(exc, "reauthorize", False),
                        "message": str(exc)[:160],
                        "token": sha8(getattr(client, "_refused_token", None)),
                    },
                )
            await asyncio.sleep(random.uniform(0.5, 1.5) * args.interval)

    await asyncio.gather(*(caller() for _ in range(args.concurrency)))
    waits = sorted(lock_waits)
    await store.event(
        args.run,
        args.name,
        "summary",
        {
            "ok": ok,
            "failed": failed,
            "failures": dict(failures),
            "tokens": len(tokens),
            "lock_waits": len(waits),
            "lock_wait_p50": waits[len(waits) // 2] if waits else None,
            "lock_wait_max": waits[-1] if waits else None,
        },
    )
    await store.close()


# -----------------------------------------------------
# The report: what the run shows, and whether it passed
# -----------------------------------------------------


async def report(args: argparse.Namespace) -> bool:
    store = open_store(args.store)
    await store.open()
    events = await store.events(args.run)

    starts = [(w, d) for w, _, k, d in events if k == "start"]
    summaries = {w: d for w, _, k, d in events if k == "summary"}
    refreshes = [(t, w) for w, t, k, _ in events if k == "refresh"]
    fails = [(t, w, d) for w, t, k, d in events if k == "fail"]

    print(f"Run {args.run}, mode {args.mode}: {len(starts)} workers")
    for name, detail in starts:
        where = detail.get("region") or detail["host"]
        print(f"  {name}: {where}, charter/auth/oauth.py {detail['code']}")
    codes = {d["code"] for _, d in starts}

    ok = sum(s["ok"] for s in summaries.values())
    failed = sum(s["failed"] for s in summaries.values())
    print(f"Calls: {ok + failed}, failed {failed}")
    for name, s in sorted(summaries.items()):
        p50 = f"{s['lock_wait_p50'] * 1000:.0f}" if s["lock_wait_p50"] is not None else "-"
        top = f"{s['lock_wait_max'] * 1000:.0f}" if s["lock_wait_max"] is not None else "-"
        print(
            f"  {name}: ok {s['ok']}, failed {s['failed']} {s['failures'] or ''}"
            f" tokens {s['tokens']}, lock taken {s['lock_waits']}x (p50 {p50} ms, max {top} ms)"
        )

    # Every worker renews at half the declared lifetime (the leeway is capped
    # there), so one refresh per half lifetime is the floor and the target. Two
    # closer together than a quarter of it are a race nobody won.
    period = min(90, args.lifetime / 2)
    duplicates = sum(
        1 for a, b in zip(refreshes, refreshes[1:], strict=False) if b[0] - a[0] < period / 2
    )
    by = Counter(w for _, w in refreshes)
    print(
        f"Refreshes: {len(refreshes)} (one per {period:.0f}s window expected),"
        f" {duplicates} closer than {period / 2:.0f}s to the one before; by {dict(by)}"
    )
    lost = [d for _, _, d in fails if d.get("reauthorize")]
    for t, name, detail in fails[:12]:
        print(
            f"  fail {name} t={t - fails[0][0]:6.1f}s {detail['error']} {detail['status']}:"
            f" {detail['message'][:100]}"
        )
    if len(fails) > 12:
        print(f"  … {len(fails) - 12} more")

    alive = await _grant_alive(store)
    row = await store.load()
    await store.close()
    print(f"The grant afterwards: {'refreshes' if alive else 'DEAD'} (version {row['version']})")

    passed = (
        failed == 0 and duplicates == 0 and not lost and alive and len(codes) == 1 and summaries
    )
    print("PASSED" if passed else "FAILED")
    return bool(passed)


async def _grant_alive(store: Any) -> bool:
    """Refresh the stored grant once more and read with it, storing what comes back.

    A refresh rather than a read with the stored access token: the point is
    that the refresh token the workers left behind is the live one.
    """
    from charter.packs import stripe

    row = await store.load()

    async def keep(credentials: Credentials, refresh_token: Optional[str]) -> None:
        expires_at = credentials.expires_at.isoformat() if credentials.expires_at else None
        await store.save(
            {
                "access_token": credentials.token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "updated_by": "report",
            }
        )

    stripe.configure(
        credential_provider=OAuth2Client(
            STRIPE_APPS,
            client_id=row["client_id"],
            client_secret=os.environ["STRIPE_SECRET_KEY"],
            refresh_token=row["refresh_token"],
            on_refresh=keep,
        )
    )
    try:
        await stripe.balance_retrieve.ainvoke({})
        return True
    except CharterError:
        return False


# -----------------------------------------------------
# run: the local case, N processes on this machine
# -----------------------------------------------------


async def run_local(args: argparse.Namespace) -> bool:
    store = open_store(args.store)
    await seed(store)
    start_at = time.time() + 8  # every process imported and connected before the first call
    until = start_at + args.minutes * 60
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                __file__,
                "worker",
                "--store",
                args.store,
                "--run",
                args.run,
                "--name",
                f"w{i}",
                "--mode",
                args.mode,
                "--lifetime",
                str(args.lifetime),
                "--concurrency",
                str(args.concurrency),
                "--interval",
                str(args.interval),
                "--start-at",
                str(start_at),
                "--until",
                str(until),
            ]
        )
        for i in range(args.workers)
    ]
    for proc in procs:
        proc.wait()
    passed = await report(args)
    await write_back(open_store(args.store))
    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("run", "seed", "worker", "report", "write-back"))
    parser.add_argument("--store", required=True)
    parser.add_argument("--run", default=datetime.now(timezone.utc).strftime("%H%M%S"))
    parser.add_argument("--mode", choices=("documented", "no-lock", "copy"), default="documented")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--lifetime", type=int, default=60, help="declared seconds per token")
    parser.add_argument("--concurrency", type=int, default=3, help="callers per process")
    parser.add_argument("--interval", type=float, default=1.0, help="mean seconds between calls")
    parser.add_argument("--name", default=socket.gethostname())
    parser.add_argument("--start-at", type=float, default=0)
    parser.add_argument("--until", type=float, default=0)
    args = parser.parse_args()

    if args.command == "run":
        sys.exit(0 if asyncio.run(run_local(args)) else 1)
    if args.command == "seed":
        asyncio.run(seed(open_store(args.store)))
    elif args.command == "worker":
        asyncio.run(worker(args))
    elif args.command == "report":
        sys.exit(0 if asyncio.run(report(args)) else 1)
    elif args.command == "write-back":
        asyncio.run(write_back(open_store(args.store)))


if __name__ == "__main__":
    main()
