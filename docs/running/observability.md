---
title: "What a call cost"
description: "Timings split by owner, payload versus context, measured locally and kept locally."
---

Two of this library's claims are, until someone measures them, only claims:

- a pack hands the model a fraction of what the API actually sent
- the boundary adds no meaningful latency of its own

[`ToolCall`](/reference/observability#toolcall) is those two claims as numbers,
recorded on every invocation — including the ones that fail, and the ones that
never leave the process.

All of it is local. A record goes to the `on_call` sink you name and to the `charter`
logger; there is no default sink, no phone-home, and no history. Comparing this
week's numbers against last week's needs storage, and this library deliberately
has none.

## A line per call

The runtime emits one INFO record per call, whose message is the rendered line:

```python enable_call_log.py
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
```

```
stripe.list_charges    GET  v1/charges                 200     18ms  ↑     12 B  ↓    38.4 KB →     412 B  (99%)
stripe.get_charge      GET  v1/charges/{charge_id}     200     11ms  ↑     20 B  ↓      159 B →     159 B   (0%)
stripe.list_charges    GET  v1/charges                 ✗ invalid_input — not sent, 1ms
```

Sizes, never values. The arguments and the response body appear only on the DEBUG
path, which a host has to ask for explicitly.

That third line is the one worth staring at: the model produced a call that did not
satisfy the schema, so it was rejected here, in your process, before anything was
sent. No request, no rate-limit budget, no charge.

## A summary at the end of a run

[`CallCollector`](/reference/observability#callcollector) is a sink that keeps
the records; [`format_call_summary`](/reference/observability#format_call_summary)
renders them:

```python call_summary.py
from charter import CallCollector, format_call_summary

calls = CallCollector()
stripe = api_key_tool_factory(base_url=..., api_key_headers=..., on_call=calls)

...

print(format_call_summary(calls))
```

```
Charter — 47 calls · 3 providers

  ok 44 · invalid_input 2 · envelope_error 1
  2 of 47 never reached the network — no request, no quota, no charge

  context       1.81 MB → 43.2 KB  (97.7% trimmed)
  upstream      18.44s summed · p50 291ms · p95 812ms
  Charter overhead  0.14s summed · 3.0ms/call · 0.8% of the time in calls

  tool                       calls  upstream p50   payload → context
  stripe.list_charges           18         288ms   38.4 KB → 412 B
  gmail.messages_get            14         233ms   41.2 KB → 1.1 KB
```

The times are sums, not wall clock — concurrent calls are each counted once, so the
totals exceed elapsed time.

## Forwarding to something that keeps history

`on_call` takes any callable — the [`CallSink`](/reference/observability#callsink)
protocol. [`ToolCall.to_dict()`](/reference/observability#toolcall-to_dict) uses
OpenTelemetry's attribute names where a convention exists, so forwarding needs no
translation table:

```python otel_sink.py
def to_otel(call):
    span.add_event("charter.call", attributes=call.to_dict())

gmail = oauth_tool_factory(..., on_call=to_otel)
```

```json
{
  "http.request.method": "GET",
  "http.route": "v1/charges",
  "http.response.status_code": 200,
  "charter.tool": "stripe.list_charges",
  "charter.outcome": "ok",
  "charter.reached_network": true,
  "charter.duration.total_ms": 18.42,
  "charter.duration.upstream_ms": 16.4,
  "charter.duration.overhead_ms": 2.02,
  "charter.size.payload_bytes": 39321,
  "charter.size.context_bytes": 412,
  "charter.size.saved_bytes": 38909
}
```

A sink is called synchronously, once per invocation, after the call finishes and
before any exception propagates. One that raises is caught and logged at DEBUG: a
broken sink must never turn a working tool call into a failing one.

## What is measured, and why that decomposition

### Outcome, not just status code

| outcome | reached the network |
|---|---|
| `invalid_input` — arguments failed the schema | no |
| `transform_failed` — a [`Format`](/reference/markers#format) transform raised | no |
| `credential_unavailable` — none resolved, or a refresh failed | no |
| `ok` | yes |
| `envelope_error` — HTTP 200, failure in the body | yes |
| `http_error` — a non-success status | yes |
| `credential_rejected` — a declared credential status, 401 by default | yes |
| `transport_error` — timeout, connection failure | yes |

Two of these have no equivalent anywhere else in a normal stack. The three
`reached_network: false` outcomes are calls that cost nothing at the API — a
number no HTTP-level metric can produce, because nothing HTTP happened.
`envelope_error` is the opposite surprise: an API that answers 200 and puts the
failure in the body, which every generic HTTP metric records as a success. See
[envelopes](/tools/envelopes).

The split between `credential_unavailable` and `credential_rejected` is drawn on
`reached_network`, not on the status code the exception carries. A failed OAuth
refresh raises a [`CredentialError`](/reference/errors#credentialerror) carrying a 400 from the *authorization
server*; filing that as "rejected" would report that the API turned you away when
the API was never contacted. (One nuance worth knowing: a failed refresh did make
a network call, just not to the tool's API. `reached_network` is about the tool's
own request.)

Validation is why the record is minted in
[`Tool.ainvoke`](/reference/tool#tool-ainvoke) rather than in the executor:
`validate_input` runs before the executor is reached, so a record minted any
deeper would miss every rejected call.

### Timings, split by owner

These fields exist to be acted on. [Optimization](/optimization/overview) is the
other side of this page: which lever moves which number.

| field | whose time it is |
|---|---|
| `validate_ms` | Charter — checking the model's arguments against the schema |
| `transform_ms` | Charter — `Format` transforms and `build_request` |
| `credential_ms` | **yours** — your [`CredentialProvider`](/reference/credentials#credentialprovider), which may hit a vault |
| `upstream_ms` | **the provider's** — around the HTTP request, and nothing else |
| `handler_ms` | **yours** — your `response_handler` |
| `total_ms` | everything |
| `overhead_ms` | `total_ms - upstream_ms` |

A single duration would conflate four things with different owners; a slow
credential provider and a slow API are the same number to anyone who only measured
the total. `overhead_ms` is the one that answers *is this layer in my way?* — and a
boundary layer should be able to answer that from the user's own logs, on demand.

### Sizes on both sides

| field | what it counts |
|---|---|
| `args_bytes` | the arguments the model emitted |
| `request_bytes` | body plus query string actually sent |
| `payload_bytes` | the response body, as read |
| `context_bytes` | what the model receives, after the response handler |

`saved_bytes` and `saved_ratio` are derived. A negative saving is not hidden: a
response handler that adds more than it removes is worth seeing.

Three things this deliberately does not do:

- **It does not report tokens.** Tokens need a tokeniser this library does not
  have, and a bytes-per-token constant would turn a measurement into a guess with a
  decimal point in it.
- **It does not claim bandwidth saved.** `payload_bytes` is read after
  decompression. The currency here is the model's context window, not egress.
- **It does not re-serialise the payload to make the ratio prettier.**
  `payload_bytes` is the response as the server formatted it and `context_bytes` is
  compact JSON, so against an API that pretty-prints, part of the difference is that
  API's whitespace.

## Cost

Timings are a handful of `perf_counter` reads and are always taken. Sizes cost a
serialisation of the arguments and of the result, so they are only computed when
something is listening — a sink is attached, or the `charter` logger is enabled for
INFO. With neither, the size fields are `None` and nothing extra is paid.

## Where this stops

Everything above is derivable from one process's own run. The moment a number needs
*yesterday* — a baseline, "p95 doubled", "this response grew three fields" — it
needs storage, and storing your traffic is not something a library that promises it
cannot see your data gets to do. That line is the same one drawn in the package
docstring, and it is structural rather than commercial.

## Related

- [`ToolCall`](/reference/observability#toolcall) — every field, grouped by identity, outcome, timings and sizes
- [`CallSink`](/reference/observability#callsink) and [`CallCollector`](/reference/observability#callcollector) — what `on_call` accepts
- [`format_call_line`](/reference/observability#format_call_line) and [`format_call_summary`](/reference/observability#format_call_summary) — the renderers
- [Logging](/reference/configuration#logging) — the `charter` logger and its levels
