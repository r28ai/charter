"""A rule on the whole call reads the call as it will be sent.

A `model_validator(mode="after")` is written against the author's model and reads
fields by name. The model is handed a view, and a view can lack fields: cut by a
projection, withheld by `Mode`, pinned, or filled in by the host. Reading one of
those raised `AttributeError` on every call, which made a tool the docs tell you
to build unusable (`gcalendar.events_list` with `time_max` cut, below).

A field the view lacks now reads as its default, at any depth, which is what the
API receives. On a view that lacks a pin or a host value the rule does not run at
all, and runs once on the view the runtime executes, where those are set. These
pin both, on the shipped Calendar pack and on schemas written for the purpose.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field, model_validator

from charter import Body, Mode, ToolValidationError, api_key_tool_factory
from charter.auth import StaticTokenProvider
from charter.packs import gcalendar

EVENTS = r".*calendar/v3/calendars/primary/events.*"
BASE = "https://api.example.com/"


@pytest.fixture
def calendar(monkeypatch):
    monkeypatch.delenv("GOOGLE_ACCESS_TOKEN", raising=False)
    gcalendar.configure(StaticTokenProvider("t"))
    return gcalendar


@respx.mock
async def test_a_rule_reading_a_field_the_projection_cut_reads_its_default(calendar):
    """`_the_window_must_be_a_window` reads `time_max`. Cut it, and the window has
    no end, which is the default the API sees: the rule passes rather than raising."""
    route = respx.get(url__regex=EVENTS).mock(return_value=httpx.Response(200, json={"items": []}))
    upcoming = calendar.events_list.derived(name="upcoming", drop={"time_max"})

    await upcoming.ainvoke({"calendar_id": "primary", "time_min": "2026-11-01T00:00:00Z"})

    assert route.called


@respx.mock
async def test_a_rule_reading_a_pinned_field_reads_the_pin(calendar):
    """Pin `order_by="startTime"` for a tool that lists upcoming events in order.
    The pack's rule then needs `single_events`, and the model still decides that."""
    route = respx.get(url__regex=EVENTS).mock(return_value=httpx.Response(200, json={"items": []}))
    in_order = calendar.events_list.derived(name="in_order", pin={"order_by": "startTime"})

    with pytest.raises(ToolValidationError, match="only available when singleEvents is True"):
        await in_order.ainvoke({"calendar_id": "primary"})
    assert not route.called

    await in_order.ainvoke({"calendar_id": "primary", "single_events": True})
    assert route.called
    assert dict(route.calls.last.request.url.params)["orderBy"] == "startTime"


# -----------------------------------------------------
# On a schema written for it
# -----------------------------------------------------

READS: list[dict] = []


class Transfer(BaseModel):
    amount: Annotated[int, Body()]
    currency: Annotated[Optional[str], Body()] = None
    memo: Annotated[Optional[str], Body()] = None
    status: Annotated[Optional[str], Body(), Mode("response_only")] = None

    @model_validator(mode="after")
    def _limits(self) -> Transfer:
        READS.append({"currency": self.currency, "memo": self.memo, "status": self.status})
        if self.currency == "eur" and self.amount > 100:
            raise ValueError("Transfers in euros are capped at 100.")
        return self


bank = api_key_tool_factory(pack="bank", base_url=BASE, api_key_headers={"X-Key": "k"})
transfer = bank(
    name="transfer",
    description="Move money.",
    method="POST",
    url_template="v1/transfers",
    args_schema=Transfer,
)


@pytest.fixture(autouse=True)
def _reads():
    READS.clear()


@respx.mock
async def test_a_withheld_field_reads_as_its_default_and_the_rule_still_runs():
    route = respx.post(f"{BASE}v1/transfers").mock(return_value=httpx.Response(200, json={}))
    assert "status" not in transfer.llm_schema().model_fields

    with pytest.raises(ToolValidationError, match="capped at 100"):
        await transfer.ainvoke({"amount": 500, "currency": "eur"})
    await transfer.ainvoke({"amount": 50, "currency": "eur"})

    assert READS[-1]["status"] is None
    assert route.call_count == 1


@respx.mock
async def test_a_cut_field_reads_as_its_default():
    respx.post(f"{BASE}v1/transfers").mock(return_value=httpx.Response(200, json={}))
    no_memo = transfer.derived(name="no_memo", drop={"memo"})

    await no_memo.ainvoke({"amount": 50})

    assert READS[-1]["memo"] is None


@respx.mock
async def test_a_pinned_tool_runs_the_rule_once_on_the_call_with_the_pin():
    """The model's view lacks the pin, so the rule waits for the second pass,
    which holds it. It runs there once, not once per pass."""
    route = respx.post(f"{BASE}v1/transfers").mock(return_value=httpx.Response(200, json={}))
    in_euros = transfer.derived(name="in_euros", pin={"currency": "eur"})

    with pytest.raises(ToolValidationError, match="capped at 100"):
        await in_euros.ainvoke({"amount": 500})
    assert READS == [{"currency": "eur", "memo": None, "status": None}]

    READS.clear()
    await in_euros.ainvoke({"amount": 50})
    assert READS == [{"currency": "eur", "memo": None, "status": None}]
    assert route.call_count == 1


def test_a_view_with_every_field_carries_the_rule_unchanged():
    """No hidden field, no stand-in: the rule runs on the view instance itself, as
    it always has, so a tool with nothing cut sees no difference at all."""
    plain = bank(
        name="plain",
        description="d",
        method="POST",
        url_template="v1/x",
        args_schema=_Plain,
    )
    plain.llm_schema().model_validate({"amount": 1})
    assert type(_SEEN[-1]).__name__ == "_Plain_LLM"


_SEEN: list[object] = []


class _Plain(BaseModel):
    amount: Annotated[int, Body()]

    @model_validator(mode="after")
    def _record(self) -> _Plain:
        _SEEN.append(self)
        return self


# -----------------------------------------------------
# Found by stress-testing the change
# -----------------------------------------------------


class _Secretive(BaseModel):
    a: Optional[str] = None
    secret: Annotated[Optional[str], Mode("response_only")] = None


class _Wrapper(BaseModel):
    inner: Annotated[Optional[_Secretive], Body()] = None

    @model_validator(mode="after")
    def _reads_nested(self) -> _Wrapper:
        if self.inner is not None and self.inner.secret == "x":
            raise ValueError("unreachable")
        return self


@respx.mock
async def test_a_rule_reading_a_field_hidden_one_level_down_reads_its_default():
    """The top-level view has every field, so nothing is cut there; the nested
    one withholds `secret`. A rule reaching into it used to raise AttributeError."""
    route = respx.post(f"{BASE}v1/w").mock(return_value=httpx.Response(200, json={}))
    wrapper = bank(
        name="wrapper", description="d", method="POST", url_template="v1/w", args_schema=_Wrapper
    )

    await wrapper.ainvoke({"inner": {"a": "1"}})

    assert route.called


def test_a_hidden_field_reads_as_its_default_and_an_unknown_one_still_raises():
    view = transfer.llm_schema().model_validate({"amount": 1})
    assert view.status is None
    with pytest.raises(AttributeError):
        _ = view.not_a_field


class _Normalises(BaseModel):
    code: Annotated[str, Body()]
    status: Annotated[Optional[str], Body(), Mode("response_only")] = None

    @model_validator(mode="after")
    def _upper(self) -> _Normalises:
        return self.model_copy(update={"code": self.code.upper()})


@respx.mock
async def test_a_rule_that_returns_a_normalised_copy_is_kept_on_a_view_with_hidden_fields():
    route = respx.post(f"{BASE}v1/n").mock(return_value=httpx.Response(200, json={}))
    normalise = bank(
        name="normalise",
        description="d",
        method="POST",
        url_template="v1/n",
        args_schema=_Normalises,
    )

    await normalise.ainvoke({"code": "abc"})

    assert json.loads(route.calls.last.request.content) == {"code": "ABC"}


class _Derives(BaseModel):
    n: Annotated[int, Body()]
    doubled: Annotated[Optional[int], Body(), Mode("response_only")] = Field(
        default_factory=lambda data: data["n"] * 2
    )

    @model_validator(mode="after")
    def _reads_doubled(self) -> _Derives:
        if self.doubled != self.n * 2:
            raise ValueError("doubled is not double")
        return self


@respx.mock
async def test_a_hidden_field_whose_default_needs_the_data_gets_it():
    """A `default_factory` taking the validated data, on a field the view lacks.
    Computed without it, the default raised, and the model was told the call
    was wrong."""
    route = respx.post(f"{BASE}v1/d").mock(return_value=httpx.Response(200, json={}))
    derives = bank(
        name="derives", description="d", method="POST", url_template="v1/d", args_schema=_Derives
    )

    await derives.ainvoke({"n": 2})

    assert route.called


class _Refund(BaseModel):
    order_id: Annotated[str, Body()]
    currency: Annotated[str, Body()]

    @model_validator(mode="after")
    def _in_dollars(self) -> _Refund:
        if self.currency != "usd":
            raise ValueError("Refunds are in dollars.")
        return self


@respx.mock
async def test_langchain_validating_the_view_itself_respects_the_pin():
    """LangChain validates the model's view as the tool's `args_schema`, before
    Charter sees the call and with no context. Run there, the rule read the pin's
    default and refused a call the pin made valid."""
    pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
    from charter.adapters import langchain

    route = respx.post(f"{BASE}v1/r").mock(return_value=httpx.Response(200, json={"ok": True}))
    refund = bank(
        name="refund", description="d", method="POST", url_template="v1/r", args_schema=_Refund
    )

    in_dollars = langchain.to_langchain(refund.derived(name="usd", pin={"currency": "usd"}))
    assert await in_dollars.ainvoke({"order_id": "o1"}) == {"ok": True}

    in_euros = langchain.to_langchain(refund.derived(name="eur", pin={"currency": "eur"}))
    assert "Refunds are in dollars" in await in_euros.ainvoke({"order_id": "o1"})
    assert route.call_count == 1
