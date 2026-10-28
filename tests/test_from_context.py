"""`FromContext`: a field the host fills in for each call, which the model never sees.

Requiring the host's value and reading it are one declaration: a field with no
default is required, so a call whose context lacks it is refused before any rule
runs, and a rule reads it as `self.customer_id`, typed. These pin that the model
cannot see or set it, that a missing or mistyped value is the host's error and
not the model's, that a rule refusing because of it is the model's to read, where
it goes on the wire, and what the egress map says about it.
"""

from __future__ import annotations

import json
import types
from typing import Annotated, Any, List, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field, field_validator, model_validator

from charter import (
    Body,
    ContextError,
    DeclarationError,
    FromContext,
    Header,
    Mode,
    Path,
    Query,
    ToolSession,
    ToolValidationError,
    api_key_tool_factory,
    egress_map,
    format_egress_map,
)
from charter.adapters.openai import run

BASE = "https://shop.example.com/"
OWNERS = {"ord_1": "cus_a", "ord_2": "cus_b"}

shop = api_key_tool_factory(pack="shop", base_url=BASE, api_key_headers={"X-Key": "k"})


class GetOrder(BaseModel):
    order_id: Annotated[str, Path()] = Field(description="The order.")
    customer_id: Annotated[str, FromContext()]

    @model_validator(mode="after")
    def _own_order(self) -> GetOrder:
        if OWNERS.get(self.order_id) != self.customer_id:
            raise ValueError("That order belongs to another customer.")
        return self


class ListOrders(BaseModel):
    customer_id: Annotated[str, Query(), FromContext()]
    status: Annotated[Optional[str], Query()] = None


get_order = shop(
    name="orders_get",
    description="Get an order.",
    method="GET",
    url_template="v1/orders/{order_id}",
    args_schema=GetOrder,
)
list_orders = shop(
    name="orders_list",
    description="List orders.",
    method="GET",
    url_template="v1/orders",
    args_schema=ListOrders,
)


def _ok(route: Any) -> Any:
    return route.mock(return_value=httpx.Response(200, json={"ok": True}))


# -----------------------------------------------------
# The model never sees it
# -----------------------------------------------------


def test_the_field_is_not_in_the_schema_the_model_reads():
    for tool in (get_order, list_orders):
        assert "customer_id" not in tool.llm_schema().model_fields
        assert "customer_id" not in tool.to_json_schema()["parameters"]["properties"]


@respx.mock
async def test_a_model_cannot_set_it_by_filling_in_an_argument():
    route = _ok(respx.get(f"{BASE}v1/orders"))

    with pytest.raises(ToolValidationError):
        await list_orders.ainvoke({"customer_id": "cus_b"}, context={"customer_id": "cus_a"})

    assert not route.called


# -----------------------------------------------------
# The rule reads it as a field
# -----------------------------------------------------


@respx.mock
async def test_a_rule_reads_the_hosts_value_as_a_field():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})
    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_b"})

    assert route.call_count == 1


@respx.mock
async def test_without_a_location_marker_it_never_reaches_the_wire():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})

    request = route.calls.last.request
    assert "cus_a" not in str(request.url)
    assert b"cus_a" not in request.content
    assert "cus_a" not in " ".join(request.headers.values())


@respx.mock
async def test_with_a_location_marker_it_is_sent_there():
    """A pin whose value arrives per call: the list is scoped to the customer the
    host verified, and the model can neither see nor change the filter."""
    route = _ok(respx.get(f"{BASE}v1/orders"))

    await list_orders.ainvoke({"status": "open"}, context={"customer_id": "cus_a"})
    await list_orders.ainvoke({}, context={"customer_id": "cus_b"})

    assert dict(route.calls[0].request.url.params) == {"customer_id": "cus_a", "status": "open"}
    assert dict(route.calls[1].request.url.params) == {"customer_id": "cus_b"}


class AsAccount(BaseModel):
    account: Annotated[str, Header("Stripe-Account"), FromContext("connected_account")]
    amount: Annotated[int, Body()]


@respx.mock
async def test_the_context_key_can_differ_from_the_field_name():
    route = _ok(respx.post(f"{BASE}v1/charges"))
    charge = shop(
        name="charge",
        description="Charge.",
        method="POST",
        url_template="v1/charges",
        args_schema=AsAccount,
    )

    await charge.ainvoke({"amount": 100}, context={"connected_account": "acct_1"})

    assert route.calls.last.request.headers["stripe-account"] == "acct_1"


class OptionalTier(BaseModel):
    order_id: Annotated[str, Path()]
    tier: Annotated[str, FromContext()] = "free"

    @model_validator(mode="after")
    def _pro_only(self) -> OptionalTier:
        if self.order_id.startswith("pro_") and self.tier != "pro":
            raise ValueError("Pro orders need a pro plan.")
        return self


@respx.mock
async def test_an_optional_one_the_host_leaves_out_takes_its_default():
    route = _ok(respx.get(url__startswith=f"{BASE}v1/orders/"))
    tiered = shop(
        name="tiered",
        description="d",
        method="GET",
        url_template="v1/orders/{order_id}",
        args_schema=OptionalTier,
    )

    with pytest.raises(ToolValidationError, match="need a pro plan"):
        await tiered.ainvoke({"order_id": "pro_1"})
    await tiered.ainvoke({"order_id": "pro_1"}, context={"tier": "pro"})

    assert route.call_count == 1


# -----------------------------------------------------
# A missing or mistyped value is the host's error, not the model's
# -----------------------------------------------------


@respx.mock
async def test_a_missing_value_is_refused_before_anything_runs():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    with pytest.raises(ContextError) as missing:
        await get_order.ainvoke({"order_id": "ord_1"}, context={})

    assert (missing.value.tool_name, missing.value.field, missing.value.key) == (
        "orders_get",
        "customer_id",
        "customer_id",
    )
    assert "application's to fix" in str(missing.value)
    assert not route.called


@respx.mock
async def test_the_hosts_error_comes_before_the_models():
    """Two mistakes, one call: the host's is reported, because the model cannot
    do anything useful until the host has said whom it is acting for."""
    route = _ok(respx.get(url__startswith=f"{BASE}v1/orders"))

    with pytest.raises(ContextError):
        await get_order.ainvoke({"order_id": "ord_1", "unknown": 1})

    assert not route.called


@respx.mock
async def test_a_mistyped_value_is_the_hosts_error_too():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    with pytest.raises(ContextError, match="does not fit 'customer_id'"):
        await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": 42})

    assert not route.called


class Verified(BaseModel):
    order_id: Annotated[str, Path()]
    verified: Annotated[bool, FromContext()]

    @field_validator("verified")
    @classmethod
    def _must_be_verified(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Verify the customer's identity before looking up an order.")
        return value


@respx.mock
async def test_a_rule_on_the_hosts_field_is_the_models_to_read():
    """A rule that refuses *because of* the host's value is a refusal like any
    other: the model reads it and can act, here by asking the customer to verify."""
    route = _ok(respx.get(url__startswith=f"{BASE}v1/orders/"))
    lookup = shop(
        name="lookup",
        description="d",
        method="GET",
        url_template="v1/orders/{order_id}",
        args_schema=Verified,
    )

    with pytest.raises(ToolValidationError, match="Verify the customer's identity"):
        await lookup.ainvoke({"order_id": "ord_1"}, context={"verified": False})
    await lookup.ainvoke({"order_id": "ord_1"}, context={"verified": True})

    assert route.call_count == 1


# -----------------------------------------------------
# With pins and projections
# -----------------------------------------------------


class Refund(BaseModel):
    order_id: Annotated[str, Body()]
    currency: Annotated[str, Body()]
    customer_id: Annotated[str, FromContext()]
    note: Annotated[Optional[str], Body()] = None

    @model_validator(mode="after")
    def _own_and_in_dollars(self) -> Refund:
        if OWNERS.get(self.order_id) != self.customer_id:
            raise ValueError("That order belongs to another customer.")
        if self.currency != "usd":
            raise ValueError("Refunds are in dollars.")
        return self


refund = shop(
    name="refund",
    description="Refund an order.",
    method="POST",
    url_template="v1/refunds",
    args_schema=Refund,
)


@respx.mock
async def test_a_pin_and_the_hosts_value_both_reach_the_rule():
    route = _ok(respx.post(f"{BASE}v1/refunds"))
    in_dollars = refund.derived(name="refund_usd", pin={"currency": "usd"})

    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await in_dollars.ainvoke({"order_id": "ord_2"}, context={"customer_id": "cus_a"})
    await in_dollars.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})

    assert json.loads(route.calls.last.request.content) == {"orderId": "ord_1", "currency": "usd"}


def test_keep_leaves_the_hosts_field_alone():
    """`keep` narrows the model's view, and the host's field is not in it."""
    kept = refund.derived(name="refund_kept", keep={"order_id"}, pin={"currency": "usd"})
    assert set(kept.llm_schema().model_fields) == {"order_id"}
    assert "customer_id" in kept._exec_schema.model_fields


def test_it_cannot_be_pinned():
    with pytest.raises(DeclarationError, match="the host fills in with FromContext"):
        refund.derived(name="pinned", pin={"customer_id": "cus_a"})


def test_it_cannot_be_dropped():
    with pytest.raises(DeclarationError, match="comes from the host with FromContext"):
        refund.derived(name="dropped", drop={"customer_id"})


class Withheld(BaseModel):
    order_id: Annotated[str, Path()]
    customer_id: Annotated[Optional[str], FromContext(), Mode("response_only")] = None


def test_it_cannot_be_withheld_by_mode():
    with pytest.raises(DeclarationError, match="cannot also be withheld by Mode"):
        shop(
            name="w",
            description="d",
            method="GET",
            url_template="v1/orders/{order_id}",
            args_schema=Withheld,
        )


class Line(BaseModel):
    order_id: str
    customer_id: Annotated[str, FromContext()]


class Bulk(BaseModel):
    lines: Annotated[List[Line], Body()]


def test_it_is_refused_below_the_top_level():
    """Nested, it would be an ordinary field the model fills in."""
    bulk = shop(
        name="bulk",
        description="d",
        method="POST",
        url_template="v1/bulk",
        args_schema=Bulk,
    )
    with pytest.raises(DeclarationError, match="is nested"):
        bulk.prepare()
    with pytest.raises(DeclarationError, match="is nested"):
        egress_map([bulk])


# -----------------------------------------------------
# What a reviewer reads
# -----------------------------------------------------


def test_the_egress_map_lists_it_as_the_hosts():
    entry = egress_map([list_orders])["shop_orders_list"]

    assert entry["visible"] == ["status"]
    assert {"field": "customer_id", "reason": "context", "key": "customer_id"} in entry["withheld"]
    assert "- customer_id  [context] <- context['customer_id']" in format_egress_map([list_orders])


# -----------------------------------------------------
# Through the loops a host drives
# -----------------------------------------------------


@respx.mock
async def test_a_session_and_the_openai_loop_fill_it_in():
    route = _ok(respx.get(f"{BASE}v1/orders"))
    session = ToolSession([list_orders], progressive=False)
    (name,) = session.visible()

    await session.dispatch(name, {}, context={"customer_id": "cus_a"})

    call = types.SimpleNamespace(id="1", function=types.SimpleNamespace(name=name, arguments="{}"))
    script = [
        types.SimpleNamespace(content=None, tool_calls=[call]),
        types.SimpleNamespace(content="done", tool_calls=None),
    ]

    async def create(**_: Any) -> Any:
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=script.pop(0))])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    await run(client, model="m", messages=[], session=session, context={"customer_id": "cus_b"})

    assert [dict(c.request.url.params) for c in route.calls] == [
        {"customer_id": "cus_a"},
        {"customer_id": "cus_b"},
    ]


async def test_the_openai_loop_hands_a_missing_value_back_as_the_tools_result():
    """A `ContextError` is a `CharterError`, so the model reads it, and the message
    tells it a different call will not help."""
    session = ToolSession([list_orders], progressive=False)
    (name,) = session.visible()
    call = types.SimpleNamespace(id="1", function=types.SimpleNamespace(name=name, arguments="{}"))
    script = [
        types.SimpleNamespace(content=None, tool_calls=[call]),
        types.SimpleNamespace(content="done", tool_calls=None),
    ]

    async def create(**_: Any) -> Any:
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=script.pop(0))])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))
    )
    result = await run(client, model="m", messages=[], session=session)

    assert "changing the call will not help" in result.messages[1]["content"]


# -----------------------------------------------------
# Found by stress-testing the change
# -----------------------------------------------------


def test_paths_neither_lists_nor_prices_the_hosts_field():
    """It is not in the model's view: naming it in a projection is refused, and
    its tokens are never in the prompt to save."""
    assert list_orders.paths() == ["status"]
    assert [cost.path for cost in list_orders.paths(by_cost=True)] == ["status"]


async def test_a_context_that_is_not_a_mapping_is_refused_by_name():
    with pytest.raises(TypeError, match="context is a mapping"):
        await list_orders.ainvoke({}, context=["customer_id"])  # type: ignore[arg-type]


@respx.mock
async def test_concurrent_calls_each_carry_their_own_customer():
    route = _ok(respx.get(f"{BASE}v1/orders"))
    import asyncio

    await asyncio.gather(
        *(list_orders.ainvoke({}, context={"customer_id": f"cus_{i}"}) for i in range(100))
    )

    sent = sorted(c.request.url.params["customer_id"] for c in route.calls)
    assert sent == sorted(f"cus_{i}" for i in range(100))
