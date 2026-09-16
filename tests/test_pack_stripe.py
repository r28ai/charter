"""Stripe pack — the form-encoded, bracket-notation, derived-cursor case."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import APIError, CredentialError, Tool, ToolValidationError
from charter.packs import stripe

API = "https://api.stripe.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    stripe.configure(api_key="sk_test_123")


def _form(request: httpx.Request) -> Dict[str, str]:
    return dict(parse_qsl(request.content.decode()))


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_fifty_nine_tools():
    assert len(stripe.TOOLS) == 59
    assert all(isinstance(t, Tool) for t in stripe.TOOLS)


def test_every_tool_builds_its_schemas():
    for tool in stripe.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_the_whole_pack_is_form_encoded_in_both_directions():
    """Stripe speaks form encoding with bracket notation for query and body."""
    for tool in stripe.TOOLS:
        assert tool.body_format == "form"
        assert tool.query_format == "bracket"
        assert tool.body_case == "snake"
        assert tool.query_case == "snake"


def test_no_envelope_is_declared():
    """Stripe uses real HTTP status codes — the right amount of config is none."""
    for tool in stripe.TOOLS:
        assert tool.envelope is None


def test_the_list_tools_declare_the_derived_cursor():
    """Pagination belongs to a list endpoint, not to the API.

    On the factory it labelled `balance_retrieve` and every create with a
    `starting_after` they do not accept.
    """
    paging = {t.name for t in stripe.TOOLS if t.pagination is not None}
    assert paging == {
        "customers_list",
        "payment_intents_list",
        "charges_list",
        "products_list",
        "prices_list",
        "subscriptions_list",
        "refunds_list",
        "invoices_list",
        "payment_methods_list",
        "customer_payment_methods_list",
        "disputes_list",
        "accounts_list",
        "transfers_list",
        "payouts_list",
        "application_fees_list",
        "balance_transactions_list",
        "invoice_items_list",
        "checkout_sessions_list",
        "checkout_sessions_line_items",
    }
    assert all(t.pagination is stripe.STRIPE_PAGINATION for t in stripe.TOOLS if t.pagination)
    assert stripe.STRIPE_PAGINATION.cursor_field == "data[-1].id"
    assert stripe.STRIPE_PAGINATION.cursor_param == "starting_after"


def test_headers_resolve_per_request():
    for tool in stripe.TOOLS:
        assert callable(tool.api_key_headers)


# -----------------------------------------------------
# The flagship: nested form bodies
# -----------------------------------------------------


@respx.mock
async def test_checkout_session_line_items_use_bracket_notation():
    """The exact shape Stripe's own curl example shows."""
    route = respx.post(f"{API}v1/checkout/sessions").mock(
        return_value=httpx.Response(
            200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/pay/cs_test_1"}
        )
    )

    result = await stripe.checkout_sessions_create.ainvoke(
        mode="payment",
        success_url="https://example.com/success",
        line_items=[
            {"price": "price_1MotwR", "quantity": 2},
            {"price": "price_2Xyz", "quantity": 1},
        ],
        metadata={"order_id": "6735"},
    )

    assert result["url"].startswith("https://checkout.stripe.com/")
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert request.headers["authorization"] == "Bearer sk_test_123"

    assert _form(request) == {
        "mode": "payment",
        "success_url": "https://example.com/success",
        "line_items[0][price]": "price_1MotwR",
        "line_items[0][quantity]": "2",
        "line_items[1][price]": "price_2Xyz",
        "line_items[1][quantity]": "1",
        "metadata[order_id]": "6735",
    }


@respx.mock
async def test_nested_address_object_is_bracketed():
    route = respx.post(f"{API}v1/customers").mock(
        return_value=httpx.Response(200, json={"id": "cus_1", "object": "customer"})
    )

    await stripe.customers_create.ainvoke(
        email="ada@example.com",
        name="Ada Lovelace",
        address={"line1": "1 Main St", "city": "London", "country": "GB"},
    )

    assert _form(route.calls.last.request) == {
        "email": "ada@example.com",
        "name": "Ada Lovelace",
        "address[line1]": "1 Main St",
        "address[city]": "London",
        "address[country]": "GB",
    }


@respx.mock
async def test_a_list_of_strings_is_indexed():
    route = respx.post(f"{API}v1/customers").mock(
        return_value=httpx.Response(200, json={"id": "cus_1", "object": "customer"})
    )
    await stripe.customers_create.ainvoke(email="a@b.com", preferred_locales=["en", "fr"])

    form = _form(route.calls.last.request)
    assert form["preferred_locales[0]"] == "en"
    assert form["preferred_locales[1]"] == "fr"


@respx.mock
async def test_snake_case_keys_are_not_camelised():
    """The default is camel; Stripe would reject successUrl."""
    route = respx.post(f"{API}v1/checkout/sessions").mock(
        return_value=httpx.Response(200, json={"id": "cs_1"})
    )
    await stripe.checkout_sessions_create.ainvoke(
        mode="payment",
        line_items=[{"price": "price_1", "quantity": 1}],
        success_url="https://x",
        client_reference_id="cart_9",
    )
    form = _form(route.calls.last.request)
    assert "success_url" in form and "successUrl" not in form
    assert "client_reference_id" in form


@respx.mock
async def test_unset_fields_are_omitted_entirely():
    route = respx.post(f"{API}v1/refunds").mock(
        return_value=httpx.Response(200, json={"id": "re_1", "object": "refund"})
    )
    await stripe.refunds_create.ainvoke(charge="ch_1")
    assert _form(route.calls.last.request) == {"charge": "ch_1"}


# -----------------------------------------------------
# GET requests
# -----------------------------------------------------


@respx.mock
async def test_path_parameters_are_substituted():
    route = respx.get(f"{API}v1/customers/cus_NffrFeUfNV2Hib").mock(
        return_value=httpx.Response(200, json={"id": "cus_NffrFeUfNV2Hib", "object": "customer"})
    )
    result = await stripe.customers_retrieve.ainvoke(customer="cus_NffrFeUfNV2Hib")
    assert result["id"] == "cus_NffrFeUfNV2Hib"
    assert route.called


@respx.mock
async def test_list_filters_go_in_the_query_string():
    route = respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [], "has_more": False})
    )
    await stripe.subscriptions_list.ainvoke(customer="cus_1", status="active", limit=25)

    assert dict(route.calls.last.request.url.params) == {
        "limit": "25",
        "customer": "cus_1",
        "status": "active",
    }


@respx.mock
async def test_a_tool_with_no_parameters_still_works():
    route = respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(200, json={"object": "balance", "available": []})
    )
    result = await stripe.balance_retrieve.ainvoke()
    # `object` is dropped with the rest of the infrastructural fields; the
    # buckets are what the call is for.
    assert result == {"available": []}
    assert route.called


# -----------------------------------------------------
# Pagination — the derived cursor
# -----------------------------------------------------


@respx.mock
async def test_paging_uses_the_last_object_id_as_the_cursor():
    """Stripe's starting_after is an object id, not a token it hands back."""
    pages = [
        {
            "object": "list",
            "has_more": True,
            "data": [{"id": "cus_1", "email": "a@x.com"}, {"id": "cus_2", "email": "b@x.com"}],
        },
        {"object": "list", "has_more": False, "data": [{"id": "cus_3", "email": "c@x.com"}]},
    ]
    route = respx.get(f"{API}v1/customers").mock(
        side_effect=[httpx.Response(200, json=p) for p in pages]
    )

    tool = stripe.customers_list
    args: Optional[Dict[str, Any]] = {"limit": 2}
    seen = []
    while args is not None:
        page = await tool.ainvoke(args)
        seen.extend(c["id"] for c in page["data"])
        args = tool.pagination.next_page_args(page, args)

    assert seen == ["cus_1", "cus_2", "cus_3"]
    assert dict(route.calls[-1].request.url.params)["starting_after"] == "cus_2"


@respx.mock
async def test_trimming_preserves_the_id_the_cursor_depends_on():
    """A handler that dropped `id` would silently break paging."""
    respx.get(f"{API}v1/customers").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": True,
                "data": [{"id": "cus_9", "email": "a@x.com", "livemode": False}],
            },
        )
    )
    page = await stripe.customers_list.ainvoke(limit=1)
    assert stripe.STRIPE_PAGINATION.next_cursor(page) == "cus_9"


# -----------------------------------------------------
# Response trimming
# -----------------------------------------------------


@respx.mock
async def test_customer_objects_are_trimmed_but_keep_what_matters():
    raw = {
        "object": "list",
        "url": "/v1/customers",
        "has_more": False,
        "data": [
            {
                "id": "cus_1",
                "object": "customer",
                "email": "ada@example.com",
                "name": "Ada",
                "balance": 0,
                "created": 1680893993,
                "livemode": False,
                "address": None,
                "default_source": None,
                "invoice_settings": {"custom_fields": None, "footer": None},
                "next_invoice_sequence": 25,
                "preferred_locales": [],
                "tax_exempt": "none",
            }
        ],
    }
    respx.get(f"{API}v1/customers").mock(return_value=httpx.Response(200, json=raw))

    result = await stripe.customers_list.ainvoke()
    customer = result["data"][0]

    assert customer["id"] == "cus_1"
    assert customer["email"] == "ada@example.com"
    assert customer["balance"] == 0  # a real zero survives
    for noise in ("object", "livemode", "invoice_settings", "next_invoice_sequence"):
        assert noise not in customer
    assert "url" not in result
    assert len(json.dumps(result)) < len(json.dumps(raw)) / 2


@respx.mock
async def test_a_retrieve_returns_a_bare_object_not_a_list():
    respx.get(f"{API}v1/customers/cus_1").mock(
        return_value=httpx.Response(
            200,
            json={"id": "cus_1", "object": "customer", "email": "a@x.com", "livemode": False},
        )
    )
    result = await stripe.customers_retrieve.ainvoke(customer="cus_1")
    assert result == {"id": "cus_1", "email": "a@x.com"}


# -----------------------------------------------------
# Errors
# -----------------------------------------------------


@respx.mock
async def test_a_card_error_surfaces_stripes_own_message():
    respx.post(f"{API}v1/refunds").mock(
        return_value=httpx.Response(
            402,
            json={
                "error": {
                    "type": "card_error",
                    "code": "charge_already_refunded",
                    "message": "Charge ch_1 has already been refunded.",
                }
            },
        )
    )
    with pytest.raises(APIError) as excinfo:
        await stripe.refunds_create.ainvoke(charge="ch_1")

    assert excinfo.value.status_code == 402
    assert "already been refunded" in str(excinfo.value)


@respx.mock
async def test_a_bad_key_is_a_credential_error():
    respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(
            401, json={"error": {"type": "invalid_request_error", "message": "Invalid API Key"}}
        )
    )
    with pytest.raises(CredentialError, match="Invalid API Key"):
        await stripe.balance_retrieve.ainvoke()


@respx.mock
async def test_rate_limiting_surfaces_retry_after():
    respx.get(f"{API}v1/charges").mock(
        return_value=httpx.Response(
            429,
            headers={"Retry-After": "2"},
            json={"error": {"type": "api_error", "message": "Too many requests"}},
        )
    )
    with pytest.raises(APIError) as excinfo:
        await stripe.charges_list.ainvoke()
    assert excinfo.value.retry_after == 2


async def test_missing_required_argument_is_a_validation_error():
    with pytest.raises(ToolValidationError, match="mode"):
        await stripe.checkout_sessions_create.ainvoke(success_url="https://x")


async def test_an_invalid_enum_is_rejected_locally():
    with pytest.raises(ToolValidationError, match="mode"):
        await stripe.checkout_sessions_create.ainvoke(mode="instalments", success_url="https://x")


async def test_unconfigured_pack_fails_before_any_request(monkeypatch):
    monkeypatch.setattr(stripe._headers, "_api_key", None)
    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="configure"):
            await stripe.balance_retrieve.ainvoke()
        assert not route.called


@respx.mock
async def test_env_var_fallback(monkeypatch):
    monkeypatch.setattr(stripe._headers, "_api_key", None)
    monkeypatch.setenv("STRIPE_API_KEY", "sk_from_env")
    stripe.configure(api_key="sk_from_env")
    route = respx.get(f"{API}v1/balance").mock(return_value=httpx.Response(200, json={}))
    await stripe.balance_retrieve.ainvoke()
    assert route.calls.last.request.headers["authorization"] == "Bearer sk_from_env"


@respx.mock
async def test_trimming_preserves_a_false_has_more_so_paging_terminates():
    """Stripe's cursor is always present, so a dropped `has_more: false` would
    leave the loop with nothing to stop on."""
    respx.get(f"{API}v1/customers").mock(
        return_value=httpx.Response(
            200, json={"object": "list", "has_more": False, "data": [{"id": "cus_9"}]}
        )
    )
    page = await stripe.customers_list.ainvoke()
    assert page["has_more"] is False
    assert stripe.STRIPE_PAGINATION.next_page_args(page, {}) is None


# -----------------------------------------------------
# Idempotency and Connect — the host's channel
# -----------------------------------------------------


@respx.mock
async def test_a_write_can_carry_a_caller_owned_idempotency_key():
    """Stripe deduplicates writes by Idempotency-Key. The key is the caller's, so
    a retry of the same logical refund can send the same one."""
    route = respx.post(f"{API}v1/refunds").mock(
        return_value=httpx.Response(200, json={"id": "re_1", "object": "refund"})
    )
    key = "refund-order-6735"

    await stripe.refunds_create.ainvoke({"charge": "ch_1"}, headers={"Idempotency-Key": key})
    await stripe.refunds_create.ainvoke({"charge": "ch_1"}, headers={"Idempotency-Key": key})

    assert [c.request.headers["idempotency-key"] for c in route.calls] == [key, key]


@respx.mock
async def test_charter_never_mints_an_idempotency_key_itself():
    """A key generated per call would defeat the point — the retry must reuse it."""
    route = respx.post(f"{API}v1/refunds").mock(
        return_value=httpx.Response(200, json={"id": "re_1"})
    )
    await stripe.refunds_create.ainvoke(charge="ch_1")
    assert "idempotency-key" not in route.calls.last.request.headers


@respx.mock
async def test_connect_acts_on_behalf_of_a_connected_account():
    route = respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(200, json={"object": "balance"})
    )
    await stripe.balance_retrieve.ainvoke(headers={"Stripe-Account": "acct_1032D82eZvKYlo2C"})

    request = route.calls.last.request
    assert request.headers["stripe-account"] == "acct_1032D82eZvKYlo2C"
    assert request.headers["authorization"] == "Bearer sk_test_123"


@respx.mock
async def test_one_key_can_serve_many_connected_accounts():
    """The platform key is fixed; which account it acts as is per call."""
    route = respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(200, json={"object": "balance"})
    )
    for account in ("acct_1", "acct_2"):
        await stripe.balance_retrieve.ainvoke(headers={"Stripe-Account": account})

    assert [c.request.headers["stripe-account"] for c in route.calls] == ["acct_1", "acct_2"]


@respx.mock
async def test_the_model_cannot_choose_the_connected_account():
    """Which account a call acts as is the host's decision, structurally.

    `Stripe-Account` is not a field on any schema here, and an argument the
    schema does not declare is refused — so the attempt fails locally rather
    than travelling as a silently ignored key.
    """
    route = respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(200, json={"object": "balance"})
    )
    with pytest.raises(ToolValidationError, match="not permitted"):
        await stripe.balance_retrieve.ainvoke({"Stripe-Account": "acct_attacker"})
    assert not route.calls


# -----------------------------------------------------
# Create-only parameters, and the pinned version
# -----------------------------------------------------


def test_update_does_not_inherit_the_create_only_payment_method():
    """`payment_method` is a create parameter; update answers 400 to it.

    The two schemas are nearly the same, and deriving update from create was the
    convenient way to say so. It also handed the model a parameter Stripe
    rejects, on the one endpoint where the model is most likely to reach for it.
    """
    fields = stripe.customers_update.args_schema.model_fields
    assert "payment_method" not in fields
    assert "payment_method" not in stripe.customers_update.llm_schema().model_fields
    # The shared attributes are still shared.
    assert {"email", "name", "address", "metadata", "tax_exempt"} <= set(fields)


def test_create_still_takes_payment_method():
    assert "payment_method" in stripe.customers_create.args_schema.model_fields


@respx.mock
async def test_every_request_pins_the_api_version():
    """Unpinned, Stripe serves whichever version the account defaults to.

    That makes the response shape a property of the caller's dashboard rather
    than of this pack — which is how a handler can be written against fields
    that a different account never returns.
    """
    route = respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(200, json={"object": "balance"})
    )

    await stripe.balance_retrieve.ainvoke()

    assert route.calls.last.request.headers["stripe-version"] == stripe.API_VERSION


def test_the_pinned_version_is_never_visible_to_the_model():
    for tool in stripe.TOOLS:
        assert "stripe_version" not in tool.llm_schema().model_fields
        assert "Stripe-Version" not in json.dumps(tool.to_json_schema())


# -----------------------------------------------------
# A subscription's billing period
# -----------------------------------------------------


def _subscription(*items: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": "sub_1",
        "object": "subscription",
        "status": "active",
        "customer": "cus_1",
        "currency": "usd",
        "livemode": False,
        "items": {"object": "list", "data": list(items), "has_more": False},
    }


def _item(price: str, start: int, end: int, quantity: int = 1) -> Dict[str, Any]:
    return {
        "id": f"si_{price}",
        "object": "subscription_item",
        "current_period_start": start,
        "current_period_end": end,
        "quantity": quantity,
        "price": {"id": price, "object": "price", "unit_amount": 1000},
    }


@respx.mock
async def test_the_billing_period_survives_its_move_onto_the_items():
    """Stripe moved `current_period_*` off the Subscription and onto its items.

    A projection that keeps asking the subscription for them finds nothing and
    drops both — leaving the model an active subscription with no renewal date
    and nothing saying one was expected.
    """
    respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [_subscription(_item("price_a", 1679609767, 1682288167))],
            },
        )
    )

    page = await stripe.subscriptions_list.ainvoke({})
    sub = page["data"][0]

    assert sub["current_period_start"] == 1679609767
    assert sub["current_period_end"] == 1682288167
    assert sub["items"] == [{"price": "price_a", "unit_amount": 1000, "quantity": 1}]
    # The invariants the cursor and the walk depend on are untouched.
    assert sub["id"] == "sub_1"
    assert page["has_more"] is False


@respx.mock
async def test_a_truncated_items_list_says_so():
    """Stripe caps a subscription's nested `items` at 20 and sets `has_more`.

    Flattening `items` to a bare list drops that flag, and an agent totalling a
    subscription then reads a short list as the whole one. Verified against the
    live API: 25 items come back as 20 with `has_more: true`.
    """
    respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [
                    {
                        **_subscription(_item("price_a", 100, 200)),
                        "items": {
                            "object": "list",
                            "has_more": True,
                            "data": [_item("price_a", 100, 200)],
                        },
                    }
                ],
            },
        )
    )

    sub = (await stripe.subscriptions_list.ainvoke({}))["data"][0]
    assert sub["items_has_more"] is True


@respx.mock
async def test_a_complete_items_list_is_not_flagged():
    """`has_more: false` says nothing actionable — no tool here pages items."""
    respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [_subscription(_item("price_a", 100, 200))],
            },
        )
    )

    sub = (await stripe.subscriptions_list.ainvoke({}))["data"][0]
    assert "items_has_more" not in sub


@respx.mock
async def test_a_failed_payment_intent_keeps_the_reason_it_failed():
    """`status` says the payment did not happen; only this says why.

    The difference between `try_again_later` and a hard decline is the
    difference between retrying and telling the customer to use another card.
    """
    respx.get(f"{API}v1/payment_intents/pi_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pi_1",
                "object": "payment_intent",
                "amount": 3300,
                "currency": "usd",
                "status": "requires_payment_method",
                "latest_charge": "ch_1",
                "last_payment_error": {
                    "type": "card_error",
                    "code": "card_declined",
                    "decline_code": "generic_decline",
                    "advice_code": "try_again_later",
                    "message": "Your card was declined.",
                    "doc_url": "https://stripe.com/docs/error-codes/card-declined",
                    "charge": "ch_1",
                    "payment_method": {"id": "pm_1", "object": "payment_method"},
                },
            },
        )
    )

    intent = await stripe.payment_intents_retrieve.ainvoke(payment_intent="pi_1")
    error = intent["last_payment_error"]

    assert error["code"] == "card_declined"
    assert error["decline_code"] == "generic_decline"
    assert error["advice_code"] == "try_again_later"
    assert error["message"] == "Your card was declined."
    # Projected, not copied: the nested payment_method is envelope, and the
    # charge is already on the intent as `latest_charge`.
    assert "payment_method" not in error
    assert "charge" not in error


@respx.mock
async def test_a_succeeded_payment_intent_carries_no_error_key():
    respx.get(f"{API}v1/payment_intents/pi_2").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pi_2",
                "object": "payment_intent",
                "amount": 3300,
                "currency": "usd",
                "status": "succeeded",
                "last_payment_error": None,
            },
        )
    )

    intent = await stripe.payment_intents_retrieve.ainvoke(payment_intent="pi_2")
    assert "last_payment_error" not in intent


@respx.mock
async def test_items_on_different_schedules_are_reported_per_item():
    """Two schedules have no single answer, so none is invented."""
    respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [
                    _subscription(
                        _item("price_a", 100, 200),
                        _item("price_b", 150, 250),
                    )
                ],
            },
        )
    )

    sub = (await stripe.subscriptions_list.ainvoke({}))["data"][0]

    assert "current_period_start" not in sub
    assert "current_period_end" not in sub
    assert sub["items"][0]["current_period_start"] == 100
    assert sub["items"][1]["current_period_end"] == 250


@respx.mock
async def test_a_retrieved_subscription_without_items_still_trims():
    respx.get(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "has_more": False,
                  "data": [{"id": "sub_2", "object": "subscription", "status": "canceled"}]},
        )
    )

    sub = (await stripe.subscriptions_list.ainvoke({}))["data"][0]
    assert sub == {"id": "sub_2", "status": "canceled"}


# -----------------------------------------------------
# Rules Stripe documents, checked before the round trip
# -----------------------------------------------------


async def test_a_refund_names_exactly_one_thing_to_refund():
    """Neither is "which charge?"; both is "these conflict". Both are 400s.

    Refunds are the one write in this pack that moves money, so the argument
    deciding what gets refunded is worth checking locally.
    """
    with pytest.raises(ToolValidationError, match="Exactly one"):
        await stripe.refunds_create.ainvoke({})
    with pytest.raises(ToolValidationError, match="Exactly one"):
        await stripe.refunds_create.ainvoke(charge="ch_1", payment_intent="pi_1")


def test_every_amount_in_the_pack_tells_the_model_it_is_cents():
    """The gloss is a property of the phrase, not of refunds.

    "smallest currency unit" is what Stripe writes on every money field, and it
    is correct on every one of them. A model holding a dollar figure has to
    multiply by 100 each time, and nothing rejects it when it does not: the
    request is valid and the API answers 200. `refunds_create` was found by a
    3B model in the harness; the other eight were found by grepping for the
    phrase, which is the only reason they are glossed too.
    """
    from pydantic import BaseModel

    from charter.types import Gloss

    def money(model, seen=frozenset()):
        """(model, field) for every field whose description names the unit."""
        if model in seen:
            return
        for name, field in model.model_fields.items():
            if "currency unit" in (field.description or ""):
                yield model, name, field
            for candidate in (field.annotation, *getattr(field.annotation, "__args__", ())):
                for item in (candidate, *getattr(candidate, "__args__", ())):
                    if isinstance(item, type) and issubclass(item, BaseModel):
                        yield from money(item, seen | {model})

    naked = set()
    for tool in stripe.TOOLS:
        for model, name, field in money(tool.args_schema):
            if not any(isinstance(m, Gloss) for m in getattr(field, "metadata", [])):
                naked.add(f"{model.__name__}.{name}")

    assert not naked, (
        "Stripe money fields with no Gloss telling the model they are cents: "
        f"{sorted(naked)}"
    )


def test_every_timestamp_in_the_pack_tells_the_model_it_is_seconds():
    """The same shape as the money fields, with a louder failure.

    Stripe takes epoch *seconds*. A model reaching for the JavaScript clock
    sends milliseconds, the field is an integer either way, and 1700000000000
    seconds lands in the year 55000. On a `created` filter that is an empty
    result set that reads as "no matches"; on `cancel_at` it is a cancellation
    that never happens.
    """
    from pydantic import BaseModel

    from charter.types import Gloss

    def timestamps(model, seen=frozenset()):
        if model in seen:
            return
        for name, field in model.model_fields.items():
            text = (field.description or "").lower()
            if "unix timestamp" in text or "epoch time" in text:
                yield model, name, field
            for candidate in (field.annotation, *getattr(field.annotation, "__args__", ())):
                for item in (candidate, *getattr(candidate, "__args__", ())):
                    if isinstance(item, type) and issubclass(item, BaseModel):
                        yield from timestamps(item, seen | {model})

    naked = set()
    for tool in stripe.TOOLS:
        for model, name, field in timestamps(tool.args_schema):
            if not any(isinstance(m, Gloss) for m in getattr(field, "metadata", [])):
                naked.add(f"{model.__name__}.{name}")

    assert not naked, (
        "Stripe timestamp fields with no Gloss telling the model they are seconds: "
        f"{sorted(naked)}"
    )


def test_the_refund_amount_tells_the_model_it_is_cents():
    """Stripe's phrase is correct and was not enough for a small model.

    "A positive integer in the smallest currency unit" is what the reference
    page says. A 3B model reading `15.00` off a spreadsheet sent `amount=15`,
    which is a valid request for fifteen cents: nothing rejects it, and Stripe
    answers 200. The unit goes in a `Gloss` rather than in the description so
    that the description stays the text the reference page can be diffed
    against.
    """
    from charter.packs.stripe.types.payments import RefundsCreateRequest

    documented = RefundsCreateRequest.model_fields["amount"].description or ""
    assert documented == (
        "A positive integer in the smallest currency unit representing how much "
        "to refund. Defaults to the entire charge."
    )

    told = stripe.refunds_create.to_json_schema()["parameters"]["properties"]["amount"]
    assert told["description"].startswith(documented)
    assert "$15.00 is 1500" in told["description"]


async def test_a_paid_checkout_session_needs_line_items():
    with pytest.raises(ToolValidationError, match="line_items"):
        await stripe.checkout_sessions_create.ainvoke(
            mode="payment", success_url="https://x"
        )


async def test_a_setup_session_needs_a_currency():
    with pytest.raises(ToolValidationError, match="currency"):
        await stripe.checkout_sessions_create.ainvoke(
            mode="setup", success_url="https://x"
        )


async def test_the_in_page_ui_modes_refuse_the_redirect_urls():
    """There is no redirect: the customer never leaves your page."""
    for ui_mode in ("embedded_page", "elements"):
        with pytest.raises(ToolValidationError, match="success_url"):
            await stripe.checkout_sessions_create.ainvoke(
                mode="payment",
                ui_mode=ui_mode,
                line_items=[{"price": "price_1", "quantity": 1}],
                success_url="https://x",
            )


@respx.mock
async def test_an_embedded_session_with_a_return_url_is_accepted():
    route = respx.post(f"{API}v1/checkout/sessions").mock(
        return_value=httpx.Response(200, json={"id": "cs_1"})
    )

    await stripe.checkout_sessions_create.ainvoke(
        mode="payment",
        ui_mode="embedded_page",
        line_items=[{"price": "price_1", "quantity": 1}],
        return_url="https://example.com/done",
    )

    form = _form(route.calls.last.request)
    assert form["ui_mode"] == "embedded_page"
    assert form["return_url"] == "https://example.com/done"


@respx.mock
async def test_the_form_ui_mode_is_accepted():
    """A closed Literal that omits a documented value rejects a valid call.

    `form` renders inside your page, so it takes `return_url` and refuses the
    redirect URLs — live Stripe answers 400 for `success_url` here. This guards
    the Literal; `_IN_PAGE_UI_MODES` guards the URL rule.
    """
    route = respx.post(f"{API}v1/checkout/sessions").mock(
        return_value=httpx.Response(200, json={"id": "cs_1"})
    )

    await stripe.checkout_sessions_create.ainvoke(
        mode="payment",
        ui_mode="form",
        line_items=[{"price": "price_1", "quantity": 1}],
        return_url="https://example.com/done",
    )

    assert _form(route.calls.last.request)["ui_mode"] == "form"


@pytest.mark.parametrize("url_field", ["success_url", "cancel_url"])
async def test_the_form_ui_mode_refuses_the_redirect_urls(url_field):
    """`form` renders in your page, so there is nowhere to redirect.

    Live Stripe answers 400 "The following parameters are not supported with
    `ui_mode: form`" for either URL — in front of a waiting customer, which is
    the round trip this validator exists to save.
    """
    with pytest.raises(ToolValidationError, match="nowhere to redirect"):
        await stripe.checkout_sessions_create.ainvoke(
            mode="payment",
            ui_mode="form",
            line_items=[{"price": "price_1", "quantity": 1}],
            **{url_field: "https://example.com/done"},
        )


async def test_both_cursor_directions_at_once_is_refused():
    with pytest.raises(ToolValidationError, match="mutually exclusive"):
        await stripe.customers_list.ainvoke(starting_after="cus_1", ending_before="cus_2")


# -----------------------------------------------------
# Subscription lifecycle
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_create_nests_items_and_discounts_in_brackets():
    route = respx.post(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(200, json={"id": "sub_1", "object": "subscription"})
    )
    await stripe.subscriptions_create.ainvoke(
        {
            "customer": "cus_1",
            "items": [{"price": "price_1", "quantity": 2}],
            "discounts": [{"promotion_code": "promo_1"}],
        }
    )
    form = _form(route.calls.last.request)
    assert form["items[0][price]"] == "price_1"
    assert form["items[0][quantity]"] == "2"
    assert form["discounts[0][promotion_code]"] == "promo_1"


@pytest.mark.asyncio
@respx.mock
async def test_create_sends_only_what_was_given():
    """A documented default is what the server does when the field is absent.

    Copying `cancel_at_period_end: false` onto the schema would send it on every
    call, which is a different request from the one the reference describes.
    """
    route = respx.post(f"{API}v1/subscriptions").mock(
        return_value=httpx.Response(200, json={"id": "sub_1", "object": "subscription"})
    )
    await stripe.subscriptions_create.ainvoke(
        {"customer": "cus_1", "items": [{"price": "price_1"}]}
    )
    form = _form(route.calls.last.request)
    assert set(form) == {"customer", "items[0][price]"}


def test_create_and_update_do_not_share_an_enum():
    """Stripe documents the same values with different validity per endpoint.

    `always_invoice` is unsupported on creation and `pending_if_incomplete` is
    update-only, so a shared Literal would offer the model a value the endpoint
    refuses — which it cannot tell from the call being wrong.
    """
    def choices(tool, prop):
        """The values the model may actually select, not the prose around them.

        The descriptions name the excluded value on purpose, so a substring search
        over the schema finds it on both endpoints and proves nothing.
        """
        schema = tool.to_json_schema()["parameters"]["properties"][prop]
        for branch in schema["anyOf"]:
            if "enum" in branch:
                return set(branch["enum"])
        raise AssertionError(f"{prop} carries no enum")

    create, update = stripe.subscriptions_create, stripe.subscriptions_update

    assert choices(create, "prorationBehavior") == {"create_prorations", "none"}
    assert choices(update, "prorationBehavior") == {
        "always_invoice",
        "create_prorations",
        "none",
    }
    assert choices(create, "paymentBehavior") == {
        "allow_incomplete",
        "default_incomplete",
        "error_if_incomplete",
    }
    assert choices(update, "paymentBehavior") == {
        "allow_incomplete",
        "default_incomplete",
        "error_if_incomplete",
        "pending_if_incomplete",
    }


def test_update_withholds_the_three_fields_stripe_rejects_there():
    """A customer cannot be changed after creation, and update has no trial days.

    The model's view is camelCased, so these are asserted under the names the model
    actually reads — `trial_period_days` would be absent either way and prove nothing.
    """
    update = stripe.subscriptions_update.to_json_schema()["parameters"]["properties"]
    create = stripe.subscriptions_create.to_json_schema()["parameters"]["properties"]
    for absent in ("customer", "currency", "trialPeriodDays"):
        assert absent not in update, absent
        assert absent in create, absent


@pytest.mark.asyncio
async def test_days_until_due_needs_send_invoice():
    """Stripe answers 400 for the combination; the schema answers first."""
    with pytest.raises(ToolValidationError):
        await stripe.subscriptions_create.ainvoke(
            {"customer": "cus_1", "items": [{"price": "p_1"}], "days_until_due": 30}
        )


@pytest.mark.asyncio
async def test_an_updated_item_needs_a_price_unless_it_is_being_deleted():
    with pytest.raises(ToolValidationError):
        await stripe.subscriptions_update.ainvoke(
            {"subscription": "sub_1", "items": [{"id": "si_1", "quantity": 3}]}
        )


@pytest.mark.asyncio
@respx.mock
async def test_deleting_an_item_needs_no_price():
    route = respx.post(f"{API}v1/subscriptions/sub_1").mock(
        return_value=httpx.Response(200, json={"id": "sub_1", "object": "subscription"})
    )
    await stripe.subscriptions_update.ainvoke(
        {"subscription": "sub_1", "items": [{"id": "si_1", "deleted": True}]}
    )
    form = _form(route.calls.last.request)
    assert form == {"items[0][id]": "si_1", "items[0][deleted]": "true"}


@pytest.mark.asyncio
@respx.mock
async def test_cancel_is_a_delete_that_still_carries_a_form_body():
    """Stripe cancels with DELETE, and takes cancellation_details on it."""
    route = respx.delete(f"{API}v1/subscriptions/sub_1").mock(
        return_value=httpx.Response(
            200, json={"id": "sub_1", "object": "subscription", "status": "canceled"}
        )
    )
    await stripe.subscriptions_cancel.ainvoke(
        {
            "subscription": "sub_1",
            "prorate": True,
            "cancellation_details": {"feedback": "too_expensive"},
        }
    )
    request = route.calls.last.request
    assert request.method == "DELETE"
    form = _form(request)
    assert form["prorate"] == "true"
    assert form["cancellation_details[feedback]"] == "too_expensive"


@pytest.mark.asyncio
async def test_cancellation_feedback_is_a_closed_set():
    with pytest.raises(ToolValidationError):
        await stripe.subscriptions_cancel.ainvoke(
            {"subscription": "sub_1", "cancellation_details": {"feedback": "too_pricey"}}
        )


# -----------------------------------------------------
# Refunds: list and retrieve
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_refunds_list_brackets_the_created_window():
    route = respx.get(f"{API}v1/refunds").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [], "has_more": False})
    )
    await stripe.refunds_list.ainvoke({"charge": "ch_1", "created": {"gte": 1700000000}})
    query = dict(route.calls.last.request.url.params)
    assert query["charge"] == "ch_1"
    assert query["created[gte]"] == "1700000000"


def test_refunds_list_declares_no_status_filter():
    """Stripe documents none. A filter the API ignores is worse than its absence,
    because the model reads an unfiltered page as a filtered one."""
    props = stripe.refunds_list.to_json_schema()["parameters"]["properties"]
    assert "status" not in props


@pytest.mark.asyncio
@respx.mock
async def test_refunds_retrieve_takes_only_the_id():
    route = respx.get(f"{API}v1/refunds/re_1").mock(
        return_value=httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
    )
    await stripe.refunds_retrieve.ainvoke({"refund": "re_1"})
    assert not dict(route.calls.last.request.url.params)
    props = stripe.refunds_retrieve.to_json_schema()["parameters"]["properties"]
    assert set(props) == {"refund"}


# -----------------------------------------------------
# Invoices
# -----------------------------------------------------


@pytest.mark.asyncio
async def test_due_terms_require_send_invoice():
    """Stripe defaults collection_method to charge_automatically.

    So omitting it while setting a due term is the same rejected request as
    setting it to charge_automatically outright, and both are caught here.
    """
    for extra in ({"days_until_due": 30}, {"due_date": 1700000000}):
        with pytest.raises(ToolValidationError):
            await stripe.invoices_create.ainvoke({"customer": "cus_1", **extra})

    with pytest.raises(ToolValidationError):
        await stripe.invoices_create.ainvoke(
            {"customer": "cus_1", "collection_method": "charge_automatically", "days_until_due": 30}
        )


@pytest.mark.asyncio
@respx.mock
async def test_due_terms_are_fine_with_send_invoice():
    route = respx.post(f"{API}v1/invoices").mock(
        return_value=httpx.Response(200, json={"id": "in_1", "status": "draft"})
    )
    await stripe.invoices_create.ainvoke(
        {"customer": "cus_1", "collection_method": "send_invoice", "days_until_due": 30}
    )
    assert _form(route.calls.last.request)["days_until_due"] == "30"


def test_invoice_create_requires_a_customer():
    """Stripe marks it optional only because `from_invoice` is the alternative.

    That revises an existing invoice and is not modelled here, so every call this
    tool can make needs a customer.
    """
    assert "customer" in stripe.invoices_create.to_json_schema()["parameters"]["required"]


def test_invoice_update_drops_the_create_only_fields():
    update = stripe.invoices_update.to_json_schema()["parameters"]["properties"]
    for absent in ("customer", "currency", "subscription", "pendingInvoiceItemsBehavior"):
        assert absent not in update, absent


def test_pending_invoice_items_behavior_has_two_values():
    """`include_and_require` is gone from the current reference."""
    schema = stripe.invoices_create.to_json_schema()["parameters"]["properties"]
    branch = next(
        b for b in schema["pendingInvoiceItemsBehavior"]["anyOf"] if "enum" in b
    )
    assert set(branch["enum"]) == {"exclude", "include"}


@pytest.mark.asyncio
@respx.mock
async def test_the_three_bare_actions_send_no_body():
    for name, path in (
        ("invoices_send", "send"),
        ("invoices_void", "void"),
        ("invoices_mark_uncollectible", "mark_uncollectible"),
    ):
        with respx.mock:
            route = respx.post(f"{API}v1/invoices/in_1/{path}").mock(
                return_value=httpx.Response(200, json={"id": "in_1"})
            )
            await getattr(stripe, name).ainvoke({"invoice": "in_1"})
            assert not route.calls.last.request.content


def test_finalize_takes_exactly_one_parameter_besides_the_id():
    props = stripe.invoices_finalize.to_json_schema()["parameters"]["properties"]
    assert set(props) == {"invoice", "autoAdvance"}


# -----------------------------------------------------
# Payment methods
# -----------------------------------------------------


def test_payment_method_type_is_not_a_closed_enum():
    """Stripe marks it x-stripeBypassValidation and documents 55, 57 and 58 values
    in three places. A Literal would reject calls Stripe accepts."""
    schema = stripe.payment_methods_list.to_json_schema()["parameters"]["properties"]["type"]
    assert not any("enum" in branch for branch in schema["anyOf"])
    assert "us_bank_account" in schema["description"]


@pytest.mark.asyncio
@respx.mock
async def test_an_unknown_payment_method_type_is_sent_not_rejected():
    route = respx.get(f"{API}v1/payment_methods").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [], "has_more": False})
    )
    await stripe.payment_methods_list.ainvoke({"type": "some_future_method"})
    assert dict(route.calls.last.request.url.params)["type"] == "some_future_method"


def test_attach_requires_a_customer_even_though_stripe_marks_it_optional():
    assert "customer" in stripe.payment_methods_attach.to_json_schema()["parameters"]["required"]


@pytest.mark.asyncio
@respx.mock
async def test_a_payment_method_keeps_only_its_own_detail_hash():
    """A PaymentMethod carries one of ~57 type-named hashes. The type names it."""
    respx.get(f"{API}v1/payment_methods/pm_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pm_1", "type": "card", "customer": "cus_1",
                "card": {"brand": "visa", "last4": "4242"},
                "us_bank_account": None,
                "radar_options": {"session": "rsess_1"},
            },
        )
    )
    result = await stripe.payment_methods_retrieve.ainvoke({"payment_method": "pm_1"})
    assert result["card"] == {"brand": "visa", "last4": "4242"}
    assert "radar_options" not in result


# -----------------------------------------------------
# Disputes
# -----------------------------------------------------


def test_dispute_evidence_offers_no_file_upload_fields():
    """Nine evidence fields take a file_... id from a multipart upload, which
    nothing here can produce. Offering them would be offering a dead end.

    Asserted against exact property names rather than a substring search, because
    four of the nine are prefixes of the text field they pair with: `refundPolicy`
    is a file and `refundPolicyDisclosure` is not.
    """
    params = stripe.disputes_update.to_json_schema()["parameters"]
    evidence = params["$defs"]["DisputeEvidence_LLM"]["properties"]

    for file_field in (
        "customerSignature", "customerCommunication", "receipt", "refundPolicy",
        "cancellationPolicy", "serviceDocumentation", "shippingDocumentation",
        "duplicateChargeDocumentation", "uncategorizedFile", "enhancedEvidence",
    ):
        assert file_field not in evidence, file_field

    for text_field in (
        "refundPolicyDisclosure", "cancellationPolicyDisclosure", "uncategorizedText",
        "duplicateChargeExplanation", "duplicateChargeId",
    ):
        assert text_field in evidence, text_field


def test_submit_carries_no_default_so_the_caller_always_chooses():
    """Stripe submits when it is absent, and submission is irreversible."""
    props = stripe.disputes_update.to_json_schema()["parameters"]["properties"]
    assert props["submit"].get("default") is None


def test_dispute_dates_are_strings_not_timestamps():
    """Stripe asks for a human-readable date here, unlike every other date in the
    pack. An integer would be silently wrong."""
    schema = json.dumps(stripe.disputes_update.to_json_schema()["parameters"])
    assert '"serviceDate"' in schema
    props = stripe.disputes_update.to_json_schema()["parameters"]
    evidence = props["$defs"]["DisputeEvidence_LLM"] if "$defs" in props else None
    if evidence is not None:
        for field in ("serviceDate", "shippingDate"):
            branches = evidence["properties"][field]["anyOf"]
            assert {"type": "string"} in branches, field


def test_disputes_close_takes_only_the_id_and_says_what_it_costs():
    props = stripe.disputes_close.to_json_schema()["parameters"]["properties"]
    assert set(props) == {"dispute"}
    assert "cannot be undone" in stripe.disputes_close.action_label


def test_disputes_list_declares_no_status_filter():
    props = stripe.disputes_list.to_json_schema()["parameters"]["properties"]
    assert "status" not in props


# -----------------------------------------------------
# Connect
# -----------------------------------------------------


def test_no_connect_tool_lets_the_model_choose_the_account():
    """Acting as a connected account is the Stripe-Account header, which the host
    sets at the call site. Only the retrieve names an account, in its own URL."""
    for name in (
        "accounts_list", "transfers_list", "transfers_retrieve", "payouts_list",
        "payouts_retrieve", "application_fees_list", "balance_transactions_list",
    ):
        props = getattr(stripe, name).to_json_schema()["parameters"]["properties"]
        assert "stripeAccount" not in props and "account" not in props, name
    assert "account" in stripe.accounts_retrieve.to_json_schema()["parameters"]["required"]


def test_connect_is_read_only():
    for tool in stripe.TOOLS:
        if tool.url_template.startswith(("v1/accounts", "v1/transfers", "v1/payouts",
                                         "v1/application_fees", "v1/balance_transactions")):
            assert tool.method == "GET", tool.name


def test_payout_status_filter_offers_only_the_documented_four():
    """The Payout object also reports `in_transit`, but the filter does not
    document it and Stripe's schema puts no enum on the query parameter."""
    schema = stripe.payouts_list.to_json_schema()["parameters"]["properties"]["status"]
    branch = next(b for b in schema["anyOf"] if "enum" in b)
    assert set(branch["enum"]) == {"pending", "paid", "failed", "canceled"}


@pytest.mark.asyncio
@respx.mock
async def test_arrival_date_brackets_like_created():
    route = respx.get(f"{API}v1/payouts").mock(
        return_value=httpx.Response(200, json={"object": "list", "data": [], "has_more": False})
    )
    await stripe.payouts_list.ainvoke({"arrival_date": {"gte": 1700000000}})
    assert dict(route.calls.last.request.url.params)["arrival_date[gte]"] == "1700000000"


def test_balance_transaction_type_is_closed_and_complete():
    """Stripe declares a formal enum here, unlike payment method `type`."""
    schema = stripe.balance_transactions_list.to_json_schema()["parameters"]["properties"]["type"]
    branch = next(b for b in schema["anyOf"] if "enum" in b)
    assert len(branch["enum"]) == 50
    for tricky in ("reserve_hold", "reserve_transaction", "reserved_funds",
                   "stripe_fee", "stripe_fx_fee", "tax_fee", "tax_fund"):
        assert tricky in branch["enum"], tricky


# -----------------------------------------------------
# Invoice items: what makes an invoice billable
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_price_goes_under_pricing_not_at_the_top_level():
    """Stripe moved `price` under `pricing` on invoice items. A top-level `price`
    is not a parameter, so it would be ignored and the line would bill nothing."""
    route = respx.post(f"{API}v1/invoiceitems").mock(
        return_value=httpx.Response(200, json={"id": "ii_1", "amount": 500})
    )
    await stripe.invoice_items_create.ainvoke(
        {"customer": "cus_1", "invoice": "in_1", "pricing": {"price": "price_1"}}
    )
    form = _form(route.calls.last.request)
    assert form["pricing[price]"] == "price_1"
    assert "price" not in form

    props = stripe.invoice_items_create.to_json_schema()["parameters"]["properties"]
    assert "price" not in props


@pytest.mark.asyncio
async def test_an_invoice_item_period_cannot_end_before_it_starts():
    with pytest.raises(ToolValidationError):
        await stripe.invoice_items_create.ainvoke(
            {"customer": "cus_1", "period": {"start": 200, "end": 100}}
        )


def test_an_invoice_item_cannot_be_moved_between_invoices():
    """customer, currency, invoice and subscription are create-only."""
    update = stripe.invoice_items_update.to_json_schema()["parameters"]["properties"]
    for absent in ("customer", "currency", "invoice", "subscription"):
        assert absent not in update, absent


def test_an_invoice_can_now_be_given_a_line():
    """The round trip this batch existed to close: create an invoice, put a line
    on it, finalise it."""
    names = {t.name for t in stripe.TOOLS}
    assert {"invoices_create", "invoice_items_create", "invoices_finalize"} <= names


# -----------------------------------------------------
# Checkout, catalog, payments
# -----------------------------------------------------


def test_checkout_list_filters_on_status_but_not_payment_status():
    """`complete` does not imply paid, and only one of the two is a filter."""
    props = stripe.checkout_sessions_list.to_json_schema()["parameters"]["properties"]
    assert "paymentStatus" not in props and "payment_status" not in props
    branch = next(b for b in props["status"]["anyOf"] if "enum" in b)
    assert set(branch["enum"]) == {"open", "complete", "expired"}


def test_products_and_prices_keep_stripes_inconsistent_path_names():
    """Stripe spells one /v1/products/{id} and the other /v1/prices/{price}."""
    assert stripe.products_update.url_template == "v1/products/{id}"
    assert stripe.prices_update.url_template == "v1/prices/{price}"


def test_a_price_cannot_be_repriced():
    """Everything about what a price costs is fixed once it exists."""
    props = stripe.prices_update.to_json_schema()["parameters"]["properties"]
    for absent in ("unitAmount", "unitAmountDecimal", "currency", "recurring", "product"):
        assert absent not in props, absent
    assert "active" in props


def test_capture_method_offers_the_manual_hold():
    branch = next(
        b
        for b in stripe.payment_intents_create.to_json_schema()["parameters"]["properties"][
            "captureMethod"
        ]["anyOf"]
        if "enum" in b
    )
    assert set(branch["enum"]) == {"automatic_async", "automatic", "manual"}


@pytest.mark.asyncio
async def test_off_session_needs_confirm():
    with pytest.raises(ToolValidationError):
        await stripe.payment_intents_create.ainvoke(
            {"amount": 1000, "currency": "usd", "off_session": True}
        )


def test_cancellation_reason_offers_only_what_may_be_sent():
    """The object reports four more that Stripe generates: failed_invoice,
    void_invoice, automatic and expired. Typing the request against the object's
    set would offer the model values the API refuses."""
    branch = next(
        b
        for b in stripe.payment_intents_cancel.to_json_schema()["parameters"]["properties"][
            "cancellationReason"
        ]["anyOf"]
        if "enum" in b
    )
    assert set(branch["enum"]) == {
        "duplicate", "fraudulent", "requested_by_customer", "abandoned"
    }


def test_a_confirmed_payment_can_say_it_takes_no_redirects():
    """Stripe offers an intent the payment methods the dashboard has enabled, and
    some of those redirect, so a server-side `confirm` is a 400 unless the call
    either supplies a `return_url` or turns redirects off. The schema used to
    declare `confirm` and neither of its two remedies, which made every confirmed
    payment fail and left `payment_intents_capture` unreachable."""
    fields = stripe.payment_intents_create.llm_schema().model_fields
    assert "automatic_payment_methods" in fields
    assert "return_url" in fields


@pytest.mark.asyncio
@respx.mock
async def test_automatic_payment_methods_is_form_encoded_with_brackets():
    route = respx.post("https://api.stripe.com/v1/payment_intents").mock(
        return_value=httpx.Response(200, json={"id": "pi_1", "status": "succeeded"})
    )
    await stripe.payment_intents_create.ainvoke(
        {
            "amount": 1000,
            "currency": "usd",
            "confirm": True,
            "payment_method": "pm_card_visa",
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        }
    )
    sent = dict(parse_qsl(route.calls.last.request.content.decode()))
    assert sent["automatic_payment_methods[enabled]"] == "true"
    assert sent["automatic_payment_methods[allow_redirects]"] == "never"


@pytest.mark.asyncio
@respx.mock
async def test_a_partly_captured_charge_reports_what_was_taken():
    """`amount` on a charge is the authorisation and does not move when less than
    all of it is captured. Without `amount_captured` beside it the trimmed charge
    says 5000 for a payment that collected 4000."""
    respx.get("https://api.stripe.com/v1/charges/ch_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "ch_1", "object": "charge", "amount": 5000,
                "amount_captured": 4000, "amount_refunded": 0, "captured": True,
                "currency": "usd", "paid": True, "status": "succeeded",
            },
        )
    )
    charge = await stripe.charges_retrieve.ainvoke(charge="ch_1")
    assert charge["amount"] == 5000
    assert charge["amount_captured"] == 4000
    assert charge["captured"] is True


@respx.mock
async def test_clearing_a_scheduled_cancellation_puts_an_empty_value_on_the_wire():
    """`cancel_at=""` is how Stripe unschedules a cancellation, verified live.

    `cancel_at_period_end=false` clears the flag and leaves a `cancel_at`
    timestamp in place, so without this the schedule is a one-way door: an agent
    can set a cancellation date and has no way to take it back.

    Asserted on the bytes with ``keep_blank_values=True``, because the module's
    ``_form`` helper uses ``parse_qsl`` at its default, which drops blank values
    — the one byte this test exists to see. A wire assertion that cannot
    represent the value it checks would pass whether or not the field was sent.
    """
    route = respx.post(f"{API}v1/subscriptions/sub_1").mock(
        return_value=httpx.Response(200, json={"id": "sub_1", "cancel_at": None})
    )

    await stripe.subscriptions_update.ainvoke(
        {"subscription": "sub_1", "cancel_at": ""}
    )

    body = route.calls.last.request.content.decode()
    sent = dict(parse_qsl(body, keep_blank_values=True))
    assert sent["cancel_at"] == ""
    assert "cancel_at=" in body


def test_a_subscription_cannot_be_created_with_an_empty_cancel_at():
    """Creation has nothing to clear, and Stripe does not offer the value there.

    The unset lives on the update schema alone rather than on the base both
    schemas share, for the same reason the proration and payment behaviours do.
    """
    from charter.packs.stripe.types import SubscriptionsCreateRequest

    with pytest.raises(ValidationError):
        SubscriptionsCreateRequest(
            customer="cus_1", items=[{"price": "price_1"}], cancel_at=""
        )


def test_an_update_still_takes_a_timestamp_and_a_sentinel():
    """Widening the union must not cost it the two forms it already carried."""
    from charter.packs.stripe.types import SubscriptionsUpdateRequest

    assert SubscriptionsUpdateRequest(subscription="sub_1", cancel_at=1791838726).cancel_at
    assert (
        SubscriptionsUpdateRequest(subscription="sub_1", cancel_at="max_period_end").cancel_at
        == "max_period_end"
    )
    with pytest.raises(ValidationError):
        SubscriptionsUpdateRequest(subscription="sub_1", cancel_at="whenever")


# -----------------------------------------------------
# Refunds and balance — the handlers that closed the trim gap
# -----------------------------------------------------


@respx.mock
async def test_a_failed_refund_keeps_the_reason_it_failed():
    """A refund can fail days after creation. Keeping `amount` and dropping
    `failure_reason` would report money back that never arrived."""
    respx.get(f"{API}v1/refunds/re_1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "re_1",
                "object": "refund",
                "amount": 2000,
                "currency": "usd",
                "status": "failed",
                "failure_reason": "expired_or_canceled_card",
                "failure_balance_transaction": "txn_9",
                "charge": "ch_1",
                "created": 1700000000,
                "livemode": False,
                "destination_details": {
                    "card": {"reference_status": "pending", "type": "refund"},
                    "type": "card",
                },
            },
        )
    )

    result = await stripe.refunds_retrieve.ainvoke(refund="re_1")

    assert result["status"] == "failed"
    assert result["failure_reason"] == "expired_or_canceled_card"
    assert result["id"] == "re_1"
    assert "destination_details" not in result
    assert "livemode" not in result


@respx.mock
async def test_refund_list_keeps_the_cursor_fields():
    respx.get(f"{API}v1/refunds").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "has_more": False,
                "data": [
                    {"id": "re_1", "object": "refund", "amount": 100, "currency": "usd",
                     "status": "succeeded", "livemode": False}
                ],
            },
        )
    )
    result = await stripe.refunds_list.ainvoke()
    # id survives: Stripe's cursor is the last object's id.
    assert result["data"][0]["id"] == "re_1"
    assert result["has_more"] is False


@respx.mock
async def test_balance_keeps_every_bucket_and_drops_the_source_split():
    """Reading `available` alone on an account with funds in reserve reads the
    wrong number, so every bucket survives."""
    respx.get(f"{API}v1/balance").mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "balance",
                "livemode": False,
                "available": [
                    {"amount": 4200, "currency": "usd",
                     "source_types": {"card": 4200, "bank_account": 0, "fpx": 0}}
                ],
                "pending": [
                    {"amount": 800, "currency": "usd",
                     "source_types": {"card": 800, "bank_account": 0, "fpx": 0}}
                ],
                "connect_reserved": [
                    {"amount": 1000, "currency": "usd", "source_types": {"card": 1000}}
                ],
            },
        )
    )

    result = await stripe.balance_retrieve.ainvoke()

    assert result == {
        "available": [{"amount": 4200, "currency": "usd"}],
        "pending": [{"amount": 800, "currency": "usd"}],
        "connect_reserved": [{"amount": 1000, "currency": "usd"}],
    }


@respx.mock
async def test_checkout_create_is_trimmed_like_checkout_retrieve():
    """The two were inconsistent: retrieve trimmed, create did not."""
    respx.post(f"{API}v1/checkout/sessions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "cs_1",
                "object": "checkout.session",
                "url": "https://checkout.stripe.com/c/pay/cs_1",
                "status": "open",
                "payment_status": "unpaid",
                "mode": "payment",
                "amount_total": 5000,
                "currency": "usd",
                "livemode": False,
                "automatic_tax": {"enabled": False, "liability": None, "status": None},
                "custom_text": {"after_submit": None, "shipping_address": None,
                                "submit": None, "terms_of_service_acceptance": None},
                "phone_number_collection": {"enabled": False},
            },
        )
    )

    result = await stripe.checkout_sessions_create.ainvoke(
        mode="payment",
        success_url="https://example.com/ok",
        line_items=[{"price": "price_1", "quantity": 1}],
    )

    assert result["url"] == "https://checkout.stripe.com/c/pay/cs_1"
    assert result["payment_status"] == "unpaid"
    assert "custom_text" not in result
    assert "automatic_tax" not in result
