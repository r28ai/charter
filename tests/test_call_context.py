"""Per-call context: what the host knows, read by the rules on the schema.

A rule like "only this customer's orders" needs a fact the model's arguments
cannot supply: whom the agent is acting for. The host passes it as
``ainvoke(args, context=...)``, Pydantic hands it to the schema's validators as
``info.context``, and the rule stays on the field it guards. These pin that it
reaches every validator that checks a call, that a model cannot supply it, and
that a refused call never reaches the network.
"""

from __future__ import annotations

import json
import types
from typing import Annotated, Any, Dict, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from charter import Body, Mode, Path, Tool, ToolSession, ToolValidationError, api_key_tool_factory
from charter.adapters.openai import run

BASE = "https://shop.example.com/"
OWNERS = {"ord_1": "cus_a", "ord_2": "cus_b"}
WRITES_NEED_CONFIRMATION = "This changes the customer's order. Confirm it with them first."


def _customer(info: ValidationInfo) -> Optional[str]:
    return (info.context or {}).get("customer_id")


class OrderRef(BaseModel):
    order_id: Annotated[str, Path()] = Field(description="The order.")

    @field_validator("order_id")
    @classmethod
    def _own_order(cls, value: str, info: ValidationInfo) -> str:
        customer = _customer(info)
        if customer is None:
            raise ValueError("No customer has been verified in this conversation.")
        if OWNERS.get(value) != customer:
            raise ValueError("That order belongs to another customer.")
        return value


class CancelOrder(OrderRef):
    reason: Annotated[Optional[str], Body()] = Field(None, description="Why.")
    # Withheld from the model, so the model's view is a generated model rather
    # than this class: the rules have to survive being carried onto it.
    cancelled_at: Annotated[Optional[str], Body(), Mode("response_only")] = None

    @model_validator(mode="after")
    def _confirmed(self, info: ValidationInfo) -> CancelOrder:
        if not (info.context or {}).get("confirmed"):
            raise ValueError(WRITES_NEED_CONFIRMATION)
        return self


shop = api_key_tool_factory(pack="shop", base_url=BASE, api_key_headers={"X-Key": "k"})
get_order = shop(
    name="orders_get",
    description="Get an order.",
    method="GET",
    url_template="v1/orders/{order_id}",
    args_schema=OrderRef,
)
cancel_order = shop(
    name="orders_cancel",
    description="Cancel an order.",
    method="POST",
    url_template="v1/orders/{order_id}/cancel",
    args_schema=CancelOrder,
)


def _ok(route: Any) -> Any:
    return route.mock(return_value=httpx.Response(200, json={"ok": True}))


# -----------------------------------------------------
# The rule reads the context
# -----------------------------------------------------


@respx.mock
async def test_a_field_rule_reads_whom_the_agent_acts_for():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})

    assert route.called


@respx.mock
async def test_the_same_call_for_another_customer_is_refused_before_the_network():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await get_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_b"})

    assert not route.called


def test_a_rule_always_reads_a_mapping():
    """Empty when the host passed nothing, so a rule has no `None` case to forget."""
    seen: list = []

    class Probe(BaseModel):
        x: Annotated[str, Body()]

        @field_validator("x")
        @classmethod
        def _read(cls, value: str, info: ValidationInfo) -> str:
            seen.append(info.context)
            return value

    probe = shop(
        name="probe", description="d", method="POST", url_template="v1/p", args_schema=Probe
    )
    probe.llm_schema()  # built, so the validator above is the view's
    with respx.mock:
        respx.post(f"{BASE}v1/p").mock(return_value=httpx.Response(200, json={}))
        probe.invoke({"x": "a"})
        probe.invoke({"x": "a"}, context={"customer_id": "cus_a"})

    assert seen == [{}, {"customer_id": "cus_a"}]


@respx.mock
async def test_without_a_context_the_rule_decides_and_this_one_fails_closed():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    with pytest.raises(ToolValidationError, match="No customer has been verified"):
        await get_order.ainvoke({"order_id": "ord_1"})

    assert not route.called


@respx.mock
async def test_a_model_level_rule_on_a_generated_view_reads_it_too():
    """`CancelOrder` withholds a field, so the model's view is a generated
    model, and its validators are carried onto it. Both rules still see the
    context: the field rule on `order_id` and the model rule on the whole call."""
    route = _ok(respx.post(f"{BASE}v1/orders/ord_1/cancel"))
    assert cancel_order.llm_schema() is not CancelOrder

    with pytest.raises(ToolValidationError, match="Confirm it with them first"):
        await cancel_order.ainvoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})
    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await cancel_order.ainvoke(
            {"order_id": "ord_2"}, context={"customer_id": "cus_a", "confirmed": True}
        )
    assert not route.called

    await cancel_order.ainvoke(
        {"order_id": "ord_1"}, context={"customer_id": "cus_a", "confirmed": True}
    )
    assert route.call_count == 1


@respx.mock
async def test_a_pinned_tool_hands_the_context_to_its_second_validation():
    """A pin re-validates the call with the pinned values merged in. That pass
    reads the context as well, or a rule on a pinned field would see none."""
    route = _ok(respx.get(f"{BASE}v1/orders/ord_2"))
    their_order = get_order.derived(name="their_order", pin={"order_id": "ord_2"})

    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await their_order.ainvoke({}, context={"customer_id": "cus_a"})
    assert not route.called

    await their_order.ainvoke({}, context={"customer_id": "cus_b"})
    assert route.called


class Line(BaseModel):
    order_id: str

    @field_validator("order_id")
    @classmethod
    def _own_order(cls, value: str, info: ValidationInfo) -> str:
        if OWNERS.get(value) != _customer(info):
            raise ValueError("That order belongs to another customer.")
        return value


class Bulk(BaseModel):
    lines: Annotated[list[Line], Body()] = Field(description="Orders to act on.")


@respx.mock
async def test_a_rule_on_a_nested_model_reads_it_too():
    route = _ok(respx.post(f"{BASE}v1/bulk"))
    bulk = shop(
        name="bulk",
        description="Act on orders.",
        method="POST",
        url_template="v1/bulk",
        args_schema=Bulk,
    )

    with pytest.raises(ToolValidationError, match=r"lines\.1\.order_id"):
        await bulk.ainvoke(
            {"lines": [{"order_id": "ord_1"}, {"order_id": "ord_2"}]},
            context={"customer_id": "cus_a"},
        )
    assert not route.called


@respx.mock
def test_invoke_passes_the_context_through():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    get_order.invoke({"order_id": "ord_1"}, context={"customer_id": "cus_a"})
    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        get_order.invoke({"order_id": "ord_1"}, context={"customer_id": "cus_b"})

    assert route.call_count == 1


# -----------------------------------------------------
# The model cannot reach it
# -----------------------------------------------------


def test_the_context_is_not_part_of_the_schema_the_model_reads():
    assert "context" not in get_order.llm_schema().model_fields
    assert "context" not in get_order.to_json_schema()["parameters"]["properties"]


@respx.mock
async def test_a_model_cannot_supply_the_context_as_an_argument():
    """The shape a prompt-injected model might try: claim to be the customer.
    `context` is not a declared field, so the argument itself is refused."""
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))

    with pytest.raises(ToolValidationError):
        await get_order.ainvoke({"order_id": "ord_1", "context": {"customer_id": "cus_a"}})

    assert not route.called


# -----------------------------------------------------
# What a host drives the tools through
# -----------------------------------------------------


@respx.mock
async def test_a_session_dispatch_passes_the_context_through():
    route = _ok(respx.get(f"{BASE}v1/orders/ord_1"))
    session = ToolSession([get_order], progressive=False)
    (name,) = session.visible()

    await session.dispatch(name, {"order_id": "ord_1"}, context={"customer_id": "cus_a"})
    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        await session.dispatch(name, {"order_id": "ord_1"}, context={"customer_id": "cus_b"})

    assert route.call_count == 1


class _ScriptedClient:
    def __init__(self, *messages: Any) -> None:
        self.script = list(messages)

    @property
    def chat(self) -> Any:
        return types.SimpleNamespace(completions=types.SimpleNamespace(create=self._create))

    async def _create(self, **_: Any) -> Any:
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=self.script.pop(0))])


def _call(name: str, arguments: Dict[str, Any]) -> Any:
    function = types.SimpleNamespace(name=name, arguments=json.dumps(arguments))
    return types.SimpleNamespace(id="1", function=function)


@respx.mock
async def test_the_openai_loop_gives_every_call_the_runs_context():
    """The refusal is the tool's result, so the model reads why and the run goes on."""
    route = _ok(respx.get(f"{BASE}v1/orders/ord_2"))
    session = ToolSession([get_order], progressive=False)
    (name,) = session.visible()
    client = _ScriptedClient(
        types.SimpleNamespace(content=None, tool_calls=[_call(name, {"order_id": "ord_2"})]),
        types.SimpleNamespace(content="done", tool_calls=None),
    )

    result = await run(
        client,
        model="m",
        messages=[{"role": "user", "content": "cancel my order"}],
        session=session,
        context={"customer_id": "cus_a"},
    )

    assert not route.called
    assert "belongs to another customer" in result.messages[2]["content"]


def test_a_tool_built_directly_takes_a_context_too():
    """No factory, no session: the plain `Tool` is where the argument lives."""
    tool = Tool(
        name="orders_get",
        method="GET",
        url_template="v1/orders/{order_id}",
        args_schema=OrderRef,
        base_url=BASE,
        api_key_headers={"X-Key": "k"},
    )
    with pytest.raises(ToolValidationError, match="belongs to another customer"):
        tool.invoke({"order_id": "ord_1"}, context={"customer_id": "cus_b"})
