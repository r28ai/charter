# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
What a call cost — measured in your process, kept in your process.

Two of this library's claims are, until someone measures them, only claims: that
a pack hands the model a fraction of what the API actually sent, and that the
boundary adds no meaningful latency of its own. :class:`ToolCall` is those two
claims as numbers, recorded on every invocation — successful or not.

Nothing here leaves the machine. A record goes to the ``on_call`` sink you
supply and to the ``charter`` logger at INFO level. There is no default sink, no
phone-home, and no aggregation across runs: comparing today's numbers against
last week's needs storage, and this library deliberately has none.

A line per call while developing::

    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

A summary at the end of a run::

    from charter import CallCollector, format_call_summary

    calls = CallCollector()
    gmail = oauth_tool_factory(..., on_call=calls)

    await messages_list.ainvoke(user_id="me")
    print(format_call_summary(calls))

Or forward each record to whatever you already run::

    def to_otel(call):
        span.add_event("charter.call", attributes=call.to_dict())

    gmail = oauth_tool_factory(..., on_call=to_otel)

``on_call`` is set when a tool is built, which a shipped pack does at import.
:func:`collecting` is how you listen to one that already exists::

    from charter import CallCollector, collecting
    from charter.packs import gmail

    calls = CallCollector()
    with collecting(calls):
        await run(client, model="gpt-4o", messages=..., session=session)

    print(format_call_summary(calls))

Sizes are reported in bytes, and named bytes. Bytes are not tokens; a
tokens-saved figure derived from a bytes-per-token constant would be a guess
with a decimal point in it, so this module does not print one.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from charter.types.errors import (
    APIError,
    CharterError,
    CredentialError,
    ToolValidationError,
    TransformError,
)

__all__ = [
    "ToolCall",
    "CallSink",
    "CallCollector",
    "collecting",
    "current_sinks",
    "format_call_line",
    "format_call_summary",
]

logger = logging.getLogger("charter")


# -----------------------------------------------------
# The probe — internal, mutable, one per call in flight
# -----------------------------------------------------


@dataclass
class CallProbe:
    """Scratch space the runtime fills in as one call proceeds.

    Internal. The executor and the wire layer write to it, :meth:`ToolCall.from_probe`
    freezes it, and nothing outside the library should hold one.

    ``observed`` is the cost switch: the timings are free (a handful of
    ``perf_counter`` reads), but measuring a payload means serialising it, so the
    size fields are only filled in when something is actually listening.

    ``schema_ms`` is filled in only on a call that had to derive the tool's view
    first — see :attr:`ToolCall.schema_ms`.
    """

    observed: bool = False

    schema_ms: float = 0.0
    validate_ms: float = 0.0
    transform_ms: float = 0.0
    credential_ms: float = 0.0
    upstream_ms: float = 0.0
    handler_ms: float = 0.0

    request_bytes: Optional[int] = None
    payload_bytes: Optional[int] = None

    status_code: Optional[int] = None
    reached_network: bool = False
    envelope_failed: bool = False


# -----------------------------------------------------
# The record
# -----------------------------------------------------

# Outcomes, in the order a summary lists them. The first four never reached the
# network: the model got the call wrong and it cost no request, no rate-limit
# budget, and no money.
OUTCOMES = (
    "invalid_input",
    "transform_failed",
    "credential_unavailable",
    "ok",
    "envelope_error",
    "http_error",
    "credential_rejected",
    "transport_error",
    "cancelled",
    "error",
)


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation, measured.

    The identity fields carry ``url_template`` rather than the resolved URL, on
    purpose twice over: the resolved path contains customer identifiers, and it
    would make every call its own label in a metrics backend.

    ``outcome`` is finer-grained than a status code because two of its values
    have no status code to report. ``invalid_input`` and ``transform_failed``
    happened before anything was sent — the model produced a bad call and it
    cost nothing. ``envelope_error`` is the opposite surprise: HTTP 200 with the
    failure inside the body, which every generic HTTP metric records as success.

    The timings are decomposed by owner. ``upstream_ms`` is the provider's;
    everything else is yours, and :attr:`overhead_ms` is the difference — the
    number that answers "is this layer in my way?".

    ``schema_ms`` is the odd one and is reported separately for that reason: it
    is zero on every call but the first one made against a tool, where it is
    whatever deriving that tool's view cost — seconds, on a schema whose types
    refer to each other. It was charged to ``validate_ms`` until it had a field
    of its own, which put a one-off build in the number a host watches to see
    whether the model is sending malformed arguments.
    :meth:`Tool.prepare <charter.Tool.prepare>` moves it to startup, where a
    non-zero ``schema_ms`` in production then means a tool nobody prepared.
    """

    tool: str
    provider: Optional[str]
    method: str
    url_template: str

    outcome: str
    reached_network: bool
    status_code: Optional[int] = None
    error_type: Optional[str] = None

    total_ms: float = 0.0
    schema_ms: float = 0.0
    validate_ms: float = 0.0
    transform_ms: float = 0.0
    credential_ms: float = 0.0
    upstream_ms: float = 0.0
    handler_ms: float = 0.0

    args_bytes: Optional[int] = None
    request_bytes: Optional[int] = None
    payload_bytes: Optional[int] = None
    context_bytes: Optional[int] = None

    # -- derived ----------------------------------------

    @property
    def overhead_ms(self) -> float:
        """Wall time minus the provider's share: what Charter itself cost."""
        return max(0.0, self.total_ms - self.upstream_ms)

    @property
    def saved_bytes(self) -> Optional[int]:
        """Bytes the API sent that the model never had to read.

        ``None`` when the call was not observed. Negative is possible and is not
        hidden: a response handler that adds more than it removes is worth
        seeing.

        Exactly two byte counts, no estimation: what came back off the wire, and
        what the result serialises to. It is not a token count — tokens depend on
        a tokeniser this library does not have, and a bytes-per-token constant
        would turn a measurement into a guess with a decimal point in it.

        One caveat worth knowing: :attr:`payload_bytes` is the response as the
        server formatted it, while :attr:`context_bytes` is compact JSON. Against
        an API that pretty-prints, some of the difference is that API's
        whitespace rather than anything a handler removed.
        """
        if self.payload_bytes is None or self.context_bytes is None:
            return None
        return self.payload_bytes - self.context_bytes

    @property
    def saved_ratio(self) -> Optional[float]:
        """:attr:`saved_bytes` as a fraction of what the API sent."""
        if self.payload_bytes is None or self.context_bytes is None:
            return None
        if self.payload_bytes == 0:
            return None
        return (self.payload_bytes - self.context_bytes) / self.payload_bytes

    # -- construction -----------------------------------

    @classmethod
    def from_probe(
        cls,
        *,
        tool: str,
        provider: Optional[str],
        method: str,
        url_template: str,
        probe: CallProbe,
        error: Optional[BaseException],
        total_ms: float,
        args_bytes: Optional[int] = None,
        context_bytes: Optional[int] = None,
    ) -> ToolCall:
        """Freeze a finished call into a record."""
        outcome, error_type = _classify(error, probe)
        return cls(
            tool=tool,
            provider=provider,
            method=method,
            url_template=url_template,
            outcome=outcome,
            reached_network=probe.reached_network,
            status_code=probe.status_code,
            error_type=error_type,
            total_ms=total_ms,
            schema_ms=probe.schema_ms,
            validate_ms=probe.validate_ms,
            transform_ms=probe.transform_ms,
            credential_ms=probe.credential_ms,
            upstream_ms=probe.upstream_ms,
            handler_ms=probe.handler_ms,
            args_bytes=args_bytes,
            request_bytes=probe.request_bytes,
            payload_bytes=probe.payload_bytes,
            context_bytes=context_bytes,
        )

    # -- export -----------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Flat attributes, using OpenTelemetry's names where one exists.

        Aligning the shared keys means forwarding a record to an OTel span, a
        Datadog event, or a log pipeline needs no translation table — which
        matters more for this layer than for most, since being easy to point at
        someone else's observability stack is part of being neutral.
        """
        attrs: Dict[str, Any] = {
            "http.request.method": self.method,
            "http.route": self.url_template,
            "http.response.status_code": self.status_code,
            "peer.service": self.provider,
            "error.type": self.error_type,
            "charter.tool": self.tool,
            "charter.outcome": self.outcome,
            "charter.reached_network": self.reached_network,
            "charter.duration.total_ms": round(self.total_ms, 3),
            "charter.duration.schema_ms": round(self.schema_ms, 3),
            "charter.duration.validate_ms": round(self.validate_ms, 3),
            "charter.duration.transform_ms": round(self.transform_ms, 3),
            "charter.duration.credential_ms": round(self.credential_ms, 3),
            "charter.duration.upstream_ms": round(self.upstream_ms, 3),
            "charter.duration.handler_ms": round(self.handler_ms, 3),
            "charter.duration.overhead_ms": round(self.overhead_ms, 3),
            "charter.size.args_bytes": self.args_bytes,
            "charter.size.request_bytes": self.request_bytes,
            "charter.size.payload_bytes": self.payload_bytes,
            "charter.size.context_bytes": self.context_bytes,
            "charter.size.saved_bytes": self.saved_bytes,
        }
        return {k: v for k, v in attrs.items() if v is not None}


CallSink = Callable[[ToolCall], None]
"""Something to hand each finished :class:`ToolCall` to.

Called synchronously, once per invocation, after the call has finished and
before any exception propagates. It must not be slow, and it must not raise —
one that does is caught and logged at DEBUG, never allowed to fail the tool
call it was only supposed to describe.
"""


_SINKS: ContextVar[Tuple[CallSink, ...]] = ContextVar("charter_call_sinks", default=())


def current_sinks() -> Tuple[CallSink, ...]:
    """The sinks :func:`collecting` has active in this context."""
    return _SINKS.get()


@contextmanager
def collecting(*sinks: CallSink) -> Iterator[None]:
    """Send every call made inside the block to ``sinks`` as well.

    ``on_call`` is a constructor argument, so a tool built by a shipped pack at
    import time has no sink and no way to be given one — assigning to it would
    reach every user of that pack in the process, because ``charter.packs.gmail``
    exports one set of tool objects rather than one per caller. This attaches a
    sink to a *scope* instead of to an object::

        calls = CallCollector()
        with collecting(calls):
            await run(client, model="gpt-4o", messages=messages, session=session)

        print(format_call_summary(calls))

    The scope is a context, not a process. A context is copied whenever a task is
    created, so a sink set before ``gather`` reaches every branch, and two
    requests served concurrently keep their records apart without knowing about
    each other.

    It follows work off the event loop only where the copy is made for you.
    ``asyncio.to_thread`` copies the context, so a sink set around it is seen
    inside. ``loop.run_in_executor`` and a bare ``threading.Thread`` do not, so a
    call made there records nothing: open the block inside that thread, or hand
    the sink over and use it directly.

    Nesting adds rather than replaces, and a tool's own ``on_call`` fires too.
    An outer collector that stopped receiving because something inside opened its
    own would be a silent hole in a measurement, which is the one thing a
    measurement may not have. A sink named twice is called once.

    Raises:
        TypeError: if a sink is not callable. A sink that raises is caught and
            logged, because a transient failure must not fail the call it was
            describing — but one that can never be called is a mistake at this
            line, and swallowing it would mean recording nothing for the life of
            the block with nothing above DEBUG to say so.
    """
    for sink in sinks:
        if not callable(sink):
            raise TypeError(
                f"collecting() takes callables; got {type(sink).__name__}. "
                f"A sink receives one ToolCall and returns None."
            )
    token = _SINKS.set(_SINKS.get() + tuple(sinks))
    try:
        yield
    finally:
        _SINKS.reset(token)


def _classify(error: Optional[BaseException], probe: CallProbe) -> tuple[str, Optional[str]]:
    """What happened, and which exception said so."""
    if error is None:
        return "ok", None

    name = type(error).__name__

    # A caller's timeout or a dropped client is not the API failing, and filing
    # it as a transport error would put someone else's latency budget in your
    # provider's column.
    if isinstance(error, asyncio.CancelledError):
        return "cancelled", name

    if isinstance(error, ToolValidationError):
        return "invalid_input", name
    if isinstance(error, TransformError):
        return "transform_failed", name
    # An envelope failure arrives as APIError or CredentialError — the envelope
    # is the only thing that knows the 200 was really a failure, so it flags it.
    if probe.envelope_failed:
        return "envelope_error", name
    if isinstance(error, CredentialError):
        # Split on whether the tool's own request went out, not on the status
        # code the exception happens to carry. A failed token refresh carries a
        # 400 from the *authorization server*, and calling that "rejected" would
        # say the API turned us away when the API was never contacted.
        if not probe.reached_network:
            return "credential_unavailable", name
        return "credential_rejected", name
    if isinstance(error, APIError):
        return "http_error", name
    if isinstance(error, CharterError):
        return "error", name
    # httpx timeouts, connection failures, anything else that escaped the wire.
    return "transport_error", name


# -----------------------------------------------------
# Collecting
# -----------------------------------------------------


@dataclass
class _ToolStats:
    calls: int = 0
    upstream_ms: List[float] = field(default_factory=list)
    payload_bytes: int = 0
    context_bytes: int = 0
    sized_calls: int = 0


class CallCollector:
    """A :data:`CallSink` that keeps what it is given, for a summary at the end.

    Pass it straight to a factory's ``on_call``. Counters and totals are exact
    for the life of the process; individual records are capped at ``max_records``
    so that a long-running service does not accumulate one per request forever.
    Percentiles are computed over what was retained.

    Not a metrics backend and not trying to be — it holds one process's own run
    in memory and forgets it on exit.
    """

    def __init__(self, max_records: int = 1000) -> None:
        self.max_records = max_records
        self._lock = threading.Lock()
        self._records: List[ToolCall] = []
        self.count = 0
        self.dropped = 0
        self.by_outcome: Dict[str, int] = {}
        self._by_tool: Dict[str, _ToolStats] = {}
        self.total_ms = 0.0
        self.upstream_ms = 0.0
        self.overhead_ms = 0.0
        self.payload_bytes = 0
        self.context_bytes = 0

    def __call__(self, call: ToolCall) -> None:
        with self._lock:
            self.count += 1
            self.by_outcome[call.outcome] = self.by_outcome.get(call.outcome, 0) + 1
            self.total_ms += call.total_ms
            self.upstream_ms += call.upstream_ms
            self.overhead_ms += call.overhead_ms

            stats = self._by_tool.setdefault(call.tool, _ToolStats())
            stats.calls += 1
            if call.reached_network:
                stats.upstream_ms.append(call.upstream_ms)
            if call.payload_bytes is not None and call.context_bytes is not None:
                self.payload_bytes += call.payload_bytes
                self.context_bytes += call.context_bytes
                stats.payload_bytes += call.payload_bytes
                stats.context_bytes += call.context_bytes
                stats.sized_calls += 1

            if len(self._records) < self.max_records:
                self._records.append(call)
            else:
                self.dropped += 1

    def __iter__(self):
        with self._lock:
            return iter(list(self._records))

    def __len__(self) -> int:
        return self.count

    @property
    def records(self) -> List[ToolCall]:
        """The retained records, oldest first."""
        with self._lock:
            return list(self._records)

    def reset(self) -> None:
        """Forget everything, keeping the collector usable."""
        with self._lock:
            self._records.clear()
            self._by_tool.clear()
            self.by_outcome.clear()
            self.count = 0
            self.dropped = 0
            self.total_ms = 0.0
            self.upstream_ms = 0.0
            self.overhead_ms = 0.0
            self.payload_bytes = 0
            self.context_bytes = 0


# -----------------------------------------------------
# Formatting
# -----------------------------------------------------


def _fmt_bytes(value: Optional[int]) -> str:
    if value is None:
        return "—"
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n < 1024:
        return f"{sign}{int(n)} B"
    if n < 1024 * 1024:
        return f"{sign}{n / 1024:.1f} KB"
    return f"{sign}{n / (1024 * 1024):.2f} MB"


def _fmt_ms(value: float) -> str:
    if value < 1000:
        return f"{value:.0f}ms"
    return f"{value / 1000:.2f}s"


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _percentile(values: List[float], q: float) -> float:
    """Nearest-rank percentile. Good enough for a run summary, and honest about it."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((len(ordered) - 1) * q))
    return ordered[idx]


def format_call_line(call: ToolCall) -> str:
    """One :class:`ToolCall` as a single scannable line.

    This is the message of the INFO log record the runtime emits, so turning on
    ``logging`` at INFO gives a call log for free::

        stripe.list_charges  GET  v1/charges            200    412ms  ↑ 118 B  ↓ 38.4 KB → 412 B  (99%)
        stripe.create_charge POST v1/charges            ✗ invalid_input — not sent, 0ms

    Sizes, never values: the arguments and the response body are logged only on
    the DEBUG path, which a host has to ask for.

    A call that had to derive the tool's view first says so, because otherwise
    the line reports a slow call and points at the API for it.
    """
    head = f"{_clip(call.tool, 22).ljust(22)} {call.method.ljust(4)} {_clip(call.url_template, 26).ljust(26)}"

    # Only ever on the first call against a tool, and then it is most of the
    # line's duration. Left unexplained it reads as the API being slow — or, on a
    # call that never reached the network, as nothing at all.
    build = f"  (+{_fmt_ms(call.schema_ms)} first-use schema build)" if call.schema_ms else ""

    if call.outcome != "ok":
        detail = call.outcome
        if call.status_code is not None:
            detail = f"{detail} {call.status_code}"
        if not call.reached_network:
            return f"{head} ✗ {detail} — not sent, {_fmt_ms(call.total_ms)}{build}"
        return f"{head} ✗ {detail}  {_fmt_ms(call.total_ms)}{build}"

    status = str(call.status_code) if call.status_code is not None else "—"
    line = f"{head} {status:>3}  {_fmt_ms(call.total_ms):>7}"

    if call.args_bytes is not None:
        line += f"  ↑ {_fmt_bytes(call.args_bytes):>8}"
    if call.payload_bytes is not None and call.context_bytes is not None:
        ratio = call.saved_ratio
        pct = f"  ({ratio * 100:.0f}%)" if ratio is not None else ""
        line += (
            f"  ↓ {_fmt_bytes(call.payload_bytes):>9} → {_fmt_bytes(call.context_bytes):>9}{pct}"
        )
    return line + build


def format_call_summary(calls: Iterable[ToolCall]) -> str:
    """A run's calls, totalled — for a human, at the end of a script or a test.

    Accepts a :class:`CallCollector` or any iterable of records.

    The times are sums, not wall clock: calls that ran concurrently are counted
    once each, so the totals exceed elapsed time and are labelled as sums.

    Where any call derived a tool's view, the overhead line says how much of
    itself that was. It is genuinely Charter's time and is not subtracted, but it
    is paid once per tool per process, and dividing it across calls that will
    never pay it again describes a steady state that does not exist.
    """
    collector = calls if isinstance(calls, CallCollector) else None
    records = list(calls)

    if not records:
        return "charter — no calls recorded"

    providers = {c.provider for c in records if c.provider}
    total_ms = sum(c.total_ms for c in records)
    upstream_ms = sum(c.upstream_ms for c in records)
    overhead_ms = sum(c.overhead_ms for c in records)
    upstream_samples = [c.upstream_ms for c in records if c.reached_network]

    sized = [c for c in records if c.payload_bytes is not None and c.context_bytes is not None]
    payload_total = sum(c.payload_bytes or 0 for c in sized)
    context_total = sum(c.context_bytes or 0 for c in sized)

    outcomes: Dict[str, int] = {}
    for call in records:
        outcomes[call.outcome] = outcomes.get(call.outcome, 0) + 1
    # Counted from the flag the runtime actually set, not from a list of outcome
    # names kept in step by hand — the list drifts, the flag cannot.
    local = sum(1 for call in records if not call.reached_network)

    lines: List[str] = []
    plural = "" if len(records) == 1 else "s"
    header = f"charter — {len(records)} call{plural}"
    if providers:
        # Only tools built by an OAuth factory carry one, so say nothing rather
        # than reporting a provider count of zero as one.
        header += f" · {len(providers)} provider" + ("" if len(providers) == 1 else "s")
    lines.append(header)
    if collector is not None and collector.dropped:
        lines.append(
            f"  (showing the first {len(records)} of {collector.count}; "
            f"{collector.dropped} not retained)"
        )
    lines.append("")

    ordered = [name for name in OUTCOMES if name in outcomes]
    lines.append("  " + " · ".join(f"{name} {outcomes[name]}" for name in ordered))
    if local:
        lines.append(
            f"  {local} of {len(records)} never reached the network — "
            "no request, no quota, no charge"
        )
    lines.append("")

    if sized:
        ratio = (payload_total - context_total) / payload_total if payload_total else 0.0
        lines.append(
            f"  context       {_fmt_bytes(payload_total)} → {_fmt_bytes(context_total)}"
            f"  ({ratio * 100:.1f}% trimmed)"
        )
    if upstream_samples:
        lines.append(
            f"  upstream      {_fmt_ms(upstream_ms)} summed"
            f" · p50 {_fmt_ms(_percentile(upstream_samples, 0.50))}"
            f" · p95 {_fmt_ms(_percentile(upstream_samples, 0.95))}"
        )
    share = (overhead_ms / total_ms * 100) if total_ms else 0.0
    per_call = overhead_ms / len(records)
    lines.append(
        f"  charter overhead  {_fmt_ms(overhead_ms)} summed"
        f" · {per_call:.1f}ms/call · {share:.1f}% of the time in calls"
    )
    # A first-use schema build is real overhead and stays in the total, but it
    # happens once per tool per process and the per-call figure above divides it
    # across calls that will never pay it again. Ten calls to a cold Linear tool
    # read as 190ms/call of overhead where the steady state is 10ms. Said rather
    # than subtracted: the time was spent, and `Tool.prepare()` is what moves it.
    schema_ms = sum(c.schema_ms for c in records)
    if schema_ms:
        cold = sum(1 for c in records if c.schema_ms)
        steady = (overhead_ms - schema_ms) / len(records)
        lines.append(
            f"  {_fmt_ms(schema_ms)} of that was {cold} first-use schema "
            f"build{'' if cold == 1 else 's'}, paid once per tool per process"
            f" · {steady:.1f}ms/call without them"
        )
    lines.append("")

    by_tool: Dict[str, List[ToolCall]] = {}
    for call in records:
        by_tool.setdefault(call.tool, []).append(call)

    lines.append(f"  {'tool'.ljust(26)} {'calls':>5}  {'upstream p50':>12}   payload → context")
    for name, tool_calls in sorted(by_tool.items(), key=lambda kv: -len(kv[1])):
        samples = [c.upstream_ms for c in tool_calls if c.reached_network]
        tool_sized = [
            c for c in tool_calls if c.payload_bytes is not None and c.context_bytes is not None
        ]
        p50 = _fmt_ms(_percentile(samples, 0.50)) if samples else "—"
        if tool_sized:
            raw = sum(c.payload_bytes or 0 for c in tool_sized) // len(tool_sized)
            ctx = sum(c.context_bytes or 0 for c in tool_sized) // len(tool_sized)
            sizes = f"{_fmt_bytes(raw)} → {_fmt_bytes(ctx)}"
        else:
            sizes = "—"
        lines.append(f"  {_clip(name, 26).ljust(26)} {len(tool_calls):>5}  {p50:>12}   {sizes}")

    return "\n".join(lines)
