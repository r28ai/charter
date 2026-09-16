"""Measurement — what a call cost, and the guarantees around recording it.

The interesting cases are the ones a naive implementation gets wrong: a call
that never reached the network, a 200 that was really a failure, and a sink that
raises.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    Body,
    CallCollector,
    CredentialError,
    Envelope,
    Format,
    Path,
    Query,
    ToolCall,
    ToolValidationError,
    TransformError,
    api_key_tool_factory,
    collecting,
    format_call_line,
    format_call_summary,
    oauth_tool_factory,
)
from charter.auth import CredentialProvider, Credentials

BASE = "https://api.example.com/"


def _compact(value) -> bytes:
    """The encoding httpx uses for a mocked JSON body — and the one Charter measures."""
    return json.dumps(value, separators=(",", ":")).encode()


class Args(BaseModel):
    thing_id: Annotated[str, Path()]
    limit: Annotated[Optional[int], Query()] = None
    note: Annotated[Optional[str], Body()] = None


def _tool(*, on_call=None, **kw):
    factory = api_key_tool_factory(
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
        on_call=on_call,
        **{k: v for k, v in kw.items() if k in {"envelope"}},
    )
    return factory(
        name="things_get",
        args_schema=Args,
        method="GET",
        url_template="v1/things/{thing_id}",
        **{k: v for k, v in kw.items() if k not in {"envelope"}},
    )


# -----------------------------------------------------
# The record
# -----------------------------------------------------


@respx.mock
async def test_a_successful_call_is_recorded_with_both_sizes():
    payload = {"id": "t1", "envelope": "x" * 4000, "useful": "yes"}
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json=payload))

    calls = CallCollector()
    tool = _tool(on_call=calls)
    await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.tool == "things_get"
    assert call.outcome == "ok"
    assert call.reached_network is True
    assert call.status_code == 200
    assert call.error_type is None

    assert call.payload_bytes == len(_compact(payload))
    assert call.context_bytes == call.payload_bytes  # no handler: nothing trimmed
    assert call.saved_bytes == 0
    assert call.args_bytes is not None and call.args_bytes > 0
    assert call.request_bytes is not None


@respx.mock
async def test_the_record_carries_the_template_not_the_resolved_url():
    """Identifiers in the path stay out of the record, and out of a metrics label."""
    respx.get(f"{BASE}v1/things/cus_secret_42").mock(
        return_value=httpx.Response(200, json={})
    )

    calls = CallCollector()
    await _tool(on_call=calls).ainvoke(thing_id="cus_secret_42")

    (call,) = calls.records
    assert call.url_template == "v1/things/{thing_id}"
    assert "cus_secret_42" not in json.dumps(call.to_dict())


@respx.mock
async def test_a_response_handler_shows_up_as_trimming():
    payload = {"items": [{"id": i, "junk": "x" * 200} for i in range(20)]}
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json=payload))

    async def keep_ids(response):
        return [item["id"] for item in response["items"]]

    calls = CallCollector()
    tool = _tool(on_call=calls, response_handler=keep_ids)
    await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.context_bytes < call.payload_bytes
    assert call.saved_bytes == call.payload_bytes - call.context_bytes
    assert call.saved_ratio > 0.9
    assert call.handler_ms >= 0.0


@respx.mock
async def test_both_sides_of_the_saving_are_measured_the_same_way():
    """A pass-through handler must show zero saved, not a whitespace artifact."""
    payload = {"a": 1, "b": [1, 2, 3], "c": {"d": "e"}}
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json=payload))

    async def identity(response):
        return response

    calls = CallCollector()
    await _tool(on_call=calls, response_handler=identity).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.saved_bytes == 0


# -----------------------------------------------------
# Calls that never reached the network
# -----------------------------------------------------


@respx.mock
async def test_invalid_input_is_recorded_and_never_sent():
    route = respx.get(f"{BASE}v1/things/t1").mock(
        return_value=httpx.Response(200, json={})
    )

    calls = CallCollector()
    tool = _tool(on_call=calls)

    with pytest.raises(ToolValidationError):
        await tool.ainvoke(thing_id="t1", limit="not-a-number")

    (call,) = calls.records
    assert call.outcome == "invalid_input"
    assert call.reached_network is False
    assert call.status_code is None
    assert call.error_type == "ToolValidationError"
    assert call.payload_bytes is None
    assert not route.called


async def test_a_missing_credential_is_recorded_without_a_status_code():
    calls = CallCollector()
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers=lambda: {"x-api-key": ""}, on_call=calls
    )
    tool = factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )

    with pytest.raises(CredentialError):
        await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "credential_unavailable"
    assert call.reached_network is False
    assert call.status_code is None


@respx.mock
async def test_a_failed_transform_is_recorded_without_a_request():
    class Body_(BaseModel):
        blob: Annotated[str, Body(), Format("base64url_decode")]

    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    calls = CallCollector()
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers={"x-api-key": "k"}, on_call=calls
    )
    tool = factory(name="t", args_schema=Body_, method="POST", url_template="v1/x")

    with pytest.raises(TransformError):
        await tool.ainvoke(blob="!!!not base64!!!")

    (call,) = calls.records
    assert call.outcome == "transform_failed"
    assert call.reached_network is False
    assert not route.called


# -----------------------------------------------------
# Failures that did reach the network
# -----------------------------------------------------


@respx.mock
async def test_an_http_error_is_recorded_with_its_status():
    respx.get(f"{BASE}v1/things/t1").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    calls = CallCollector()
    with pytest.raises(APIError):
        await _tool(on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "http_error"
    assert call.reached_network is True
    assert call.status_code == 500
    assert call.payload_bytes is not None  # the error body was still read


@respx.mock
async def test_a_401_is_a_rejected_credential_not_a_missing_one():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(401, json={}))

    calls = CallCollector()
    with pytest.raises(CredentialError):
        await _tool(on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "credential_rejected"
    assert call.status_code == 401


@respx.mock
async def test_an_envelope_failure_is_not_filed_as_a_200_http_error():
    """The whole point of an envelope: a 200 that was really a failure.

    Recorded as `envelope_error`, because `http_error 200` reads like a bug in
    the record rather than a fact about the API.
    """
    respx.get(f"{BASE}v1/things/t1").mock(
        return_value=httpx.Response(200, json={"ok": False, "error": "not_in_channel"})
    )

    calls = CallCollector()
    tool = _tool(on_call=calls, envelope=Envelope(ok_field="ok", error_field="error"))

    with pytest.raises(APIError):
        await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "envelope_error"
    assert call.status_code == 200
    assert call.reached_network is True


@respx.mock
async def test_a_transport_failure_is_recorded():
    respx.get(f"{BASE}v1/things/t1").mock(side_effect=httpx.ConnectTimeout("nope"))

    calls = CallCollector()
    with pytest.raises(httpx.ConnectTimeout):
        await _tool(on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.outcome == "transport_error"
    assert call.error_type == "ConnectTimeout"
    assert call.reached_network is True
    assert call.status_code is None


# -----------------------------------------------------
# Timing decomposition
# -----------------------------------------------------


@respx.mock
async def test_the_credential_providers_time_is_not_billed_to_the_api():
    import asyncio

    class SlowProvider(CredentialProvider):
        async def get_credentials(self, provider: str) -> Credentials:
            await asyncio.sleep(0.05)
            return Credentials(token="t")

    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    factory = oauth_tool_factory(
        base_url=BASE,
        provider="example",
        credential_provider=SlowProvider(),
        on_call=calls,
    )
    tool = factory(
        name="things_get", args_schema=Args, method="GET", url_template="v1/things/{thing_id}"
    )
    await tool.ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.credential_ms >= 45
    assert call.upstream_ms < call.credential_ms
    assert call.total_ms >= call.credential_ms
    # The provider's slowness lands in Charter's column, not the API's — which is
    # the point of separating them.
    assert call.overhead_ms >= call.credential_ms


@respx.mock
async def test_overhead_excludes_upstream_time():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={}))

    calls = CallCollector()
    await _tool(on_call=calls).ainvoke(thing_id="t1")

    (call,) = calls.records
    assert call.upstream_ms > 0
    assert call.overhead_ms == pytest.approx(call.total_ms - call.upstream_ms, abs=1e-6)


async def test_an_unsent_call_has_no_upstream_time():
    calls = CallCollector()
    with pytest.raises(ToolValidationError):
        await _tool(on_call=calls).ainvoke(thing_id="t1", limit="nope")

    (call,) = calls.records
    assert call.upstream_ms == 0.0
    assert call.overhead_ms == call.total_ms


# -----------------------------------------------------
# The sink contract
# -----------------------------------------------------


@respx.mock
async def test_a_raising_sink_never_breaks_the_call():
    respx.get(f"{BASE}v1/things/t1").mock(
        return_value=httpx.Response(200, json={"ok": 1})
    )

    def broken(call):
        raise RuntimeError("the sink is on fire")

    result = await _tool(on_call=broken).ainvoke(thing_id="t1")
    assert result == {"ok": 1}


def test_sizing_is_skipped_when_nothing_is_listening():
    """Sizing costs a serialisation; nobody pays for it unless someone is reading."""
    charter_logger = logging.getLogger("charter")
    previous = charter_logger.level
    charter_logger.setLevel(logging.WARNING)
    try:
        tool = _tool()
        assert tool._observed() is False

        tool.on_call = lambda call: None
        assert tool._observed() is True
    finally:
        charter_logger.setLevel(previous)


@respx.mock
async def test_the_info_log_line_carries_the_record(caplog):
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))

    with caplog.at_level(logging.INFO, logger="charter"):
        await _tool().ainvoke(thing_id="t1")

    records = [r for r in caplog.records if hasattr(r, "charter_call")]
    assert len(records) == 1
    assert isinstance(records[0].charter_call, ToolCall)
    assert "things_get" in records[0].getMessage()


@respx.mock
async def test_debug_logging_shows_values_but_info_shows_only_sizes(caplog):
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))

    with caplog.at_level(logging.INFO, logger="charter"):
        await _tool().ainvoke(thing_id="t1", note="a-secret-note")

    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "a-secret-note" not in text


# -----------------------------------------------------
# Export shape
# -----------------------------------------------------


@respx.mock
async def test_to_dict_uses_otel_names_and_drops_empties():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))

    calls = CallCollector()
    await _tool(on_call=calls).ainvoke(thing_id="t1")

    attrs = calls.records[0].to_dict()
    assert attrs["http.request.method"] == "GET"
    assert attrs["http.route"] == "v1/things/{thing_id}"
    assert attrs["http.response.status_code"] == 200
    assert attrs["charter.outcome"] == "ok"
    assert "error.type" not in attrs  # None keys are dropped
    json.dumps(attrs)  # must be serialisable as-is


# -----------------------------------------------------
# Collector and formatting
# -----------------------------------------------------


def _record(**kw) -> ToolCall:
    base = dict(
        tool="things_get",
        provider="example",
        method="GET",
        url_template="v1/things/{thing_id}",
        outcome="ok",
        reached_network=True,
        status_code=200,
        total_ms=100.0,
        upstream_ms=90.0,
        payload_bytes=40000,
        context_bytes=400,
    )
    base.update(kw)
    return ToolCall(**base)


def test_the_collector_keeps_exact_counters_past_its_record_cap():
    calls = CallCollector(max_records=3)
    for _ in range(10):
        calls(_record())

    assert calls.count == 10
    assert len(calls.records) == 3
    assert calls.dropped == 7
    assert calls.by_outcome["ok"] == 10
    assert calls.payload_bytes == 400000


def test_the_collector_resets_cleanly():
    calls = CallCollector()
    calls(_record())
    calls.reset()
    assert calls.count == 0
    assert calls.records == []


def test_a_line_for_an_unsent_call_says_so():
    line = format_call_line(
        _record(
            outcome="invalid_input",
            reached_network=False,
            status_code=None,
            payload_bytes=None,
            context_bytes=None,
            upstream_ms=0.0,
            total_ms=0.4,
        )
    )
    assert "invalid_input" in line
    assert "not sent" in line


def test_a_line_for_a_successful_call_shows_the_trimming():
    line = format_call_line(_record())
    assert "things_get" in line
    assert "39.1 KB" in line
    assert "400 B" in line
    assert "(99%)" in line


def test_the_summary_totals_a_run():
    calls = CallCollector()
    for _ in range(4):
        calls(_record())
    calls(
        _record(
            tool="things_create",
            outcome="invalid_input",
            reached_network=False,
            status_code=None,
            payload_bytes=None,
            context_bytes=None,
            upstream_ms=0.0,
            total_ms=1.0,
        )
    )

    summary = format_call_summary(calls)
    assert "5 calls" in summary
    assert "ok 4" in summary
    assert "invalid_input 1" in summary
    assert "never reached the network" in summary
    assert "trimmed" in summary
    assert "charter overhead" in summary
    assert "things_get" in summary


def test_the_summary_separates_a_first_use_build_from_the_steady_state():
    """The overhead line is the claim the library makes about itself.

    A tool's view is derived on the first call that needs it, and that time is
    genuinely Charter's, so it stays in the total. But it is paid once per tool
    per process, and dividing it across calls that will never pay it again
    describes a steady state that does not exist: ten calls to a cold Linear tool
    report 190ms/call of overhead where the real figure is 10ms. Said, not
    subtracted.
    """
    cold = _record(total_ms=1900.0, schema_ms=1800.0)
    warm = [_record(total_ms=100.0) for _ in range(9)]

    summary = format_call_summary([cold, *warm])
    assert "190.0ms/call" in summary, "the raw per-call figure is still reported"
    assert "1 first-use schema build" in summary
    assert "10.0ms/call without them" in summary

    # And a run with nothing cold says nothing about it.
    assert "first-use schema build" not in format_call_summary(warm)


def test_the_summary_handles_an_empty_run():
    assert format_call_summary(CallCollector()) == "charter — no calls recorded"


def test_the_summary_accepts_a_plain_list():
    assert "1 call " in format_call_summary([_record()])


# -----------------------------------------------------
# Listening to a tool you did not build
# -----------------------------------------------------


@respx.mock
async def test_a_shipped_pack_records_without_being_mutated():
    """`on_call` is a constructor argument, and a shipped pack calls the
    constructor at import. `collecting` is the only way to hear one without
    assigning to an object every other user of that pack shares."""
    from charter.auth import StaticTokenProvider
    from charter.packs import gmail

    gmail.configure(StaticTokenProvider("t"))
    respx.get(url__regex=r".*labels.*").mock(
        return_value=httpx.Response(200, json={"labels": []})
    )

    calls = CallCollector()
    with collecting(calls):
        await gmail.labels_list.ainvoke({"userId": "me"})
        await gmail.labels_list.ainvoke({"userId": "me"})
    await gmail.labels_list.ainvoke({"userId": "me"})

    assert calls.count == 2, "the call outside the block was recorded"
    assert gmail.labels_list.on_call is None, "the shared tool was mutated"


@respx.mock
async def test_concurrent_work_keeps_its_records_apart():
    """The case a shared `on_call` cannot serve: two requests in one process."""
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))
    tool = _tool()

    async def caller(sink, times):
        with collecting(sink):
            for _ in range(times):
                await tool.ainvoke({"thing_id": "t1"})

    first, second = CallCollector(), CallCollector()
    await asyncio.gather(caller(first, 3), caller(second, 1))
    assert (first.count, second.count) == (3, 1)


@respx.mock
async def test_nesting_adds_rather_than_replaces():
    """An outer collector that stopped receiving because something inside opened
    its own would be a silent hole in a measurement."""
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))
    tool = _tool()

    outer, inner = CallCollector(), CallCollector()
    with collecting(outer):
        await tool.ainvoke({"thing_id": "t1"})
        with collecting(inner):
            await tool.ainvoke({"thing_id": "t1"})
        await tool.ainvoke({"thing_id": "t1"})

    assert outer.count == 3
    assert inner.count == 1


@respx.mock
async def test_the_block_is_left_even_when_the_call_raises():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(500, json={}))
    tool = _tool()
    calls = CallCollector()

    with pytest.raises(APIError), collecting(calls):
        await tool.ainvoke({"thing_id": "t1"})

    assert calls.count == 1, "a failed call is still a call"
    from charter.observability import current_sinks

    assert current_sinks() == (), "the sink outlived its block"


@respx.mock
async def test_a_tools_own_sink_fires_alongside_the_context_one():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))
    own, scoped = CallCollector(), CallCollector()
    tool = _tool()
    tool.on_call = own

    with collecting(scoped):
        await tool.ainvoke({"thing_id": "t1"})

    assert own.count == 1
    assert scoped.count == 1


@respx.mock
async def test_one_sink_named_twice_records_once():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))
    calls = CallCollector()
    tool = _tool()
    tool.on_call = calls

    with collecting(calls):
        await tool.ainvoke({"thing_id": "t1"})

    assert calls.count == 1


@respx.mock
async def test_a_broken_sink_silences_neither_the_others_nor_the_call():
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))

    def broken(call):
        raise RuntimeError("this sink is broken")

    calls = CallCollector()
    tool = _tool()
    with collecting(broken, calls):
        result = await tool.ainvoke({"thing_id": "t1"})

    assert result == {"a": 1}
    assert calls.count == 1


@respx.mock
async def test_a_context_sink_turns_sizing_on():
    """`_observed` gates payload sizing on someone reading. A context sink is
    someone reading."""
    respx.get(f"{BASE}v1/things/t1").mock(return_value=httpx.Response(200, json={"a": 1}))
    charter_logger = logging.getLogger("charter")
    previous = charter_logger.level
    charter_logger.setLevel(logging.WARNING)
    try:
        tool = _tool()
        assert tool._observed() is False
        calls = CallCollector()
        with collecting(calls):
            assert tool._observed() is True
            await tool.ainvoke({"thing_id": "t1"})
        assert calls.context_bytes > 0
    finally:
        charter_logger.setLevel(previous)


async def test_where_the_context_sink_does_and_does_not_follow_the_work():
    """The reference page states this as a table, so it is pinned as one.

    `asyncio.to_thread` copies the context and `run_in_executor` does not, which
    is the opposite of what this docstring first claimed.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from charter.observability import current_sinks

    async def in_task():
        return current_sinks()

    with collecting(CallCollector()):
        loop = asyncio.get_running_loop()
        box: list = []
        thread = threading.Thread(target=lambda: box.append(current_sinks()))
        thread.start()
        thread.join()
        with ThreadPoolExecutor() as pool:
            in_executor = await loop.run_in_executor(pool, current_sinks)

        assert len(await asyncio.create_task(in_task())) == 1
        assert len(await asyncio.to_thread(current_sinks)) == 1
        assert in_executor == ()
        assert box[0] == ()


def test_a_sink_that_could_never_be_called_is_rejected_at_the_block():
    """A sink that raises is caught and logged: a transient failure must not fail
    the call. One that is not callable is a mistake here, and swallowing it means
    recording nothing for the life of the block with nothing above DEBUG to say
    so."""
    with pytest.raises(TypeError, match="takes callables"):
        with collecting("not a function"):
            pass

    from charter.observability import current_sinks

    assert current_sinks() == (), "a rejected sink left the context dirty"
