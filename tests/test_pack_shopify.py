"""Shopify pack — the per-installation host, and userErrors inside a 200."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import APIError, CredentialError, Tool, ToolValidationError
from charter.packs import shopify

SHOP = "my-store"
API = f"https://{SHOP}.myshopify.com/admin/api/{shopify.API_VERSION}/graphql.json"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    shopify.configure(shop=SHOP, access_token="shpat_test123")


def _sent() -> Dict[str, Any]:
    return json.loads(respx.calls.last.request.content)


def _validate(tool: Tool, args: Dict[str, Any]):
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


def _orders_page(*names: str, cursor: str = "c1", more: bool = True) -> Dict[str, Any]:
    return {
        "data": {
            "orders": {
                "nodes": [
                    {
                        "id": f"gid://shopify/Order/{i}",
                        "name": name,
                        "totalPriceSet": {
                            "shopMoney": {"amount": "42.00", "currencyCode": "USD"}
                        },
                    }
                    for i, name in enumerate(names, start=1)
                ],
                "pageInfo": {"hasNextPage": more, "endCursor": cursor},
            }
        }
    }


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_twenty_two_tools():
    assert len(shopify.TOOLS) == 22
    assert all(isinstance(t, Tool) for t in shopify.TOOLS)


def test_every_tool_builds_its_schemas():
    for tool in shopify.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_every_tool_carries_its_document_as_a_constant():
    for tool in shopify.TOOLS:
        assert tool.static_body is not None, tool.name
        assert tool.static_body["query"].strip(), tool.name
        assert set(tool.llm_schema().model_fields) <= {"variables"}, tool.name


def test_every_tool_declares_the_envelope():
    for tool in shopify.TOOLS:
        assert tool.envelope is shopify.SHOPIFY_ENVELOPE, tool.name


def test_the_envelope_covers_every_place_shopify_reports_failure():
    """Three paths, because `orderCancel` does not use `userErrors`.

    Its own `userErrors` field exists and is deprecated; the live one is
    `orderCancelUserErrors`. A refusal that is not read is a write the model
    reports as a success.
    """
    assert shopify.SHOPIFY_ENVELOPE.errors_field == (
        "errors",
        "data.*.userErrors",
        "data.*.orderCancelUserErrors",
    )


@respx.mock
async def test_a_mutation_added_without_ceremony_is_still_guarded():
    """The reason this is a declaration and not a response handler."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "productDelete": {
                        "userErrors": [{"field": ["id"], "message": "Product not found"}]
                    }
                }
            },
        )
    )

    added_later = shopify._shopify(
        name="product_delete",
        args_schema=shopify.types.ShopGetRequest,
        method="POST",
        url_template=shopify.GRAPHQL_PATH,
        static_body={"query": "mutation { productDelete { userErrors { field message } } }"},
    )

    with pytest.raises(APIError, match="id: Product not found"):
        await added_later.ainvoke()


@respx.mock
async def test_a_query_has_no_user_errors_and_must_not_trip_the_envelope():
    respx.post(API).mock(return_value=httpx.Response(200, json=_orders_page("#1001")))

    out = await shopify.orders_list.ainvoke(variables={"first": 1})

    assert out["nodes"][0]["name"] == "#1001"


def test_the_api_version_is_pinned_in_the_path():
    """Shopify ships quarterly; an unpinned integration changes under you."""
    assert shopify.API_VERSION in shopify.GRAPHQL_PATH
    for tool in shopify.TOOLS:
        assert tool.url_template == shopify.GRAPHQL_PATH, tool.name


# -----------------------------------------------------
# The per-installation host
# -----------------------------------------------------


@respx.mock
async def test_the_configured_store_becomes_the_host():
    route = respx.post(API).mock(
        return_value=httpx.Response(200, json={"data": {"shop": {"name": "My Store"}}})
    )

    await shopify.shop_get.ainvoke()

    assert route.called
    assert str(respx.calls.last.request.url) == API


@pytest.mark.parametrize(
    "given",
    ["my-store", "my-store.myshopify.com", "https://my-store.myshopify.com", "my-store/"],
)
def test_every_spelling_of_the_store_that_shopifys_own_ui_shows_is_accepted(given):
    shopify.configure(shop=given, access_token="shpat_x")
    assert shopify.base_url() == "https://my-store.myshopify.com/"


@respx.mock
async def test_the_access_token_goes_in_its_own_header_not_authorization():
    respx.post(API).mock(return_value=httpx.Response(200, json={"data": {"shop": {}}}))

    await shopify.shop_get.ainvoke()

    headers = respx.calls.last.request.headers
    assert headers["x-shopify-access-token"] == "shpat_test123"
    assert "authorization" not in headers


@respx.mock
async def test_an_unconfigured_store_fails_before_it_reaches_the_network(monkeypatch):
    monkeypatch.setattr(shopify._base_url, "_shop", None)
    route = respx.route().mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(CredentialError, match="no store"):
        await shopify.shop_get.ainvoke()

    assert not route.called


def test_the_store_is_never_a_schema_field():
    """The host must not be model-controlled: that is choosing the server."""
    for tool in shopify.TOOLS:
        fields = set(tool.llm_schema().model_fields)
        assert not fields & {"shop", "store", "base_url", "host", "domain"}, tool.name


# -----------------------------------------------------
# Variables and casing
# -----------------------------------------------------


@respx.mock
async def test_snake_case_variables_arrive_camel_cased():
    respx.post(API).mock(return_value=httpx.Response(200, json=_orders_page("#1001")))

    await shopify.orders_list.ainvoke(
        variables={"query": "financial_status:paid", "sort_key": "TOTAL_PRICE", "first": 5}
    )

    assert _sent()["variables"] == {
        "first": 5,
        "query": "financial_status:paid",
        "sortKey": "TOTAL_PRICE",
    }


@respx.mock
async def test_a_product_mutation_uses_the_product_argument_not_input():
    """Shopify renamed productCreate's argument; `input` is deprecated."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "productCreate": {
                        "product": {"id": "gid://shopify/Product/1", "title": "Widget"},
                        "userErrors": [],
                    }
                }
            },
        )
    )

    await shopify.product_create.ainvoke(
        variables={
            "product": {
                "title": "Widget",
                "description_html": "<p>A widget.</p>",
                "product_type": "Gadgets",
                "status": "DRAFT",
            }
        }
    )

    variables = _sent()["variables"]
    assert set(variables) == {"product"}
    assert variables["product"] == {
        "title": "Widget",
        "descriptionHtml": "<p>A widget.</p>",
        "productType": "Gadgets",
        "status": "DRAFT",
    }


# -----------------------------------------------------
# Failure
# -----------------------------------------------------


@respx.mock
async def test_user_errors_raise_even_though_the_status_is_200():
    """The trap GraphQL's own errors array does not carry.

    SHOPIFY_ENVELOPE reaches it with a path, so the runtime raises before any
    handler runs — there is no per-tool step to forget.
    """
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "productCreate": {
                        "product": None,
                        "userErrors": [
                            {"field": ["handle"], "message": "Handle has already been taken"}
                        ],
                    }
                }
            },
        )
    )

    with pytest.raises(APIError, match="handle: Handle has already been taken"):
        await shopify.product_create.ainvoke(variables={"product": {"title": "Widget"}})


@respx.mock
async def test_a_document_level_error_still_raises_through_the_envelope():
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"errors": [{"message": "Field 'bogus' doesn't exist"}]}
        )
    )

    with pytest.raises(APIError, match="doesn't exist"):
        await shopify.products_list.ainvoke(variables={"first": 5})


@respx.mock
async def test_an_empty_user_errors_list_is_not_a_failure():
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "customerCreate": {
                        "customer": {"id": "gid://shopify/Customer/1", "displayName": "Ada"},
                        "userErrors": [],
                    }
                }
            },
        )
    )

    out = await shopify.customer_create.ainvoke(
        variables={"input": {"email": "ada@example.com", "first_name": "Ada"}}
    )

    assert out == {"id": "gid://shopify/Customer/1", "displayName": "Ada"}


@respx.mock
async def test_a_401_becomes_a_credential_error():
    respx.post(API).mock(return_value=httpx.Response(401, json={"errors": "Invalid API key"}))

    with pytest.raises(CredentialError):
        await shopify.shop_get.ainvoke()


# -----------------------------------------------------
# Money flattening
# -----------------------------------------------------


@respx.mock
async def test_money_bags_flatten_to_a_readable_amount():
    respx.post(API).mock(return_value=httpx.Response(200, json=_orders_page("#1001")))

    out = await shopify.orders_list.ainvoke(variables={"first": 1})

    assert out["nodes"][0]["totalPriceSet"] == "42.00 USD"


@respx.mock
async def test_money_is_flattened_at_every_depth_it_appears():
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "order": {
                        "id": "gid://shopify/Order/1",
                        "totalPriceSet": {
                            "shopMoney": {"amount": "42.00", "currencyCode": "USD"}
                        },
                        "lineItems": {
                            "nodes": [
                                {
                                    "title": "Widget",
                                    "quantity": 2,
                                    "originalTotalSet": {
                                        "shopMoney": {
                                            "amount": "21.00",
                                            "currencyCode": "USD",
                                        }
                                    },
                                }
                            ]
                        },
                    }
                }
            },
        )
    )

    out = await shopify.order_get.ainvoke(variables={"id": "gid://shopify/Order/1"})

    assert out["totalPriceSet"] == "42.00 USD"
    assert out["lineItems"]["nodes"][0]["originalTotalSet"] == "21.00 USD"


def test_flattening_leaves_ordinary_objects_alone():
    from charter.packs.shopify.response_handlers import flatten_wrappers

    payload = {"id": "1", "address": {"city": "Kyoto", "zip": "600"}, "tags": ["a", "b"]}
    assert flatten_wrappers(payload) == payload


def test_contact_wrappers_collapse_back_to_scalars():
    """`Customer.email`/`phone` are deprecated; their replacements are objects.

    `defaultEmailAddress { emailAddress }` is an object wrapping one string, for
    the two fields most likely to be read on a customer. Shopify's deprecation
    does not have to become the model's extra nesting.
    """
    from charter.packs.shopify.response_handlers import flatten_wrappers

    out = flatten_wrappers(
        {
            "id": "gid://shopify/Customer/1",
            "displayName": "Ada Lovelace",
            "defaultEmailAddress": {"emailAddress": "ada@example.com"},
            "defaultPhoneNumber": {"phoneNumber": "+15551234567"},
        }
    )

    assert out["email"] == "ada@example.com"
    assert out["phone"] == "+15551234567"
    assert "defaultEmailAddress" not in out
    assert "defaultPhoneNumber" not in out


def test_a_customer_with_no_contact_details_keeps_the_keys():
    """Null is what the deprecated scalars reported, and it is a fact."""
    from charter.packs.shopify.response_handlers import flatten_wrappers

    out = flatten_wrappers({"id": "1", "defaultEmailAddress": None})
    assert out["email"] is None


def test_no_document_selects_a_deprecated_field():
    """Checked against the published 2026-07 Admin schema.

    `Customer.email`, `Customer.phone` and `ShopPlan.displayName` are all
    deprecated at this version; Shopify removes deprecated fields in a later
    release, so selecting one is a scheduled break.
    """
    from charter.packs.shopify import queries

    documents = "\n".join(
        value for name, value in vars(queries).items()
        if isinstance(value, str) and not name.startswith("__")
    )

    # `Customer.displayName` is fine; it is `ShopPlan.displayName` that is gone.
    assert "plan { displayName }" not in documents
    assert "plan { publicDisplayName }" in documents
    assert "defaultEmailAddress" in documents
    assert "defaultPhoneNumber" in documents


# -----------------------------------------------------
# Pagination
# -----------------------------------------------------


def test_relay_pagination_stops_on_has_next_page():
    """Shopify sends an endCursor on the last page too."""
    last = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": "c9"}}
    assert shopify.SHOPIFY_PAGINATION.next_page_args(last, {"variables": {}}) is None


@respx.mock
async def test_a_two_page_walk_against_the_wire():
    respx.post(API).mock(
        side_effect=[
            httpx.Response(200, json=_orders_page("#1001", "#1002", cursor="c1", more=True)),
            httpx.Response(200, json=_orders_page("#1003", cursor="c2", more=False)),
        ]
    )

    args: Dict[str, Any] = {"variables": {"first": 2}}
    collected = []
    page = await shopify.orders_list.ainvoke(args)
    collected += page["nodes"]
    while (args := shopify.orders_list.pagination.next_page_args(page, args)) is not None:
        page = await shopify.orders_list.ainvoke(args)
        collected += page["nodes"]

    assert [o["name"] for o in collected] == ["#1001", "#1002", "#1003"]
    assert json.loads(respx.calls[1].request.content)["variables"]["after"] == "c1"


def test_only_the_connections_declare_pagination():
    paging = {t.name for t in shopify.TOOLS if t.pagination is not None}
    assert paging == {"products_list", "orders_list", "customers_list", "locations_list"}


# -----------------------------------------------------
# Schema constraints
# -----------------------------------------------------


def test_a_customer_with_neither_email_nor_phone_is_rejected_locally():
    with pytest.raises(ToolValidationError):
        _validate(shopify.customer_create, {"variables": {"input": {"first_name": "Ada"}}})

    _validate(shopify.customer_create, {"variables": {"input": {"email": "a@x.com"}}})
    _validate(shopify.customer_create, {"variables": {"input": {"phone": "+15551234567"}}})


def test_a_product_update_with_only_an_id_is_rejected():
    with pytest.raises(ToolValidationError):
        _validate(
            shopify.product_update,
            {"variables": {"product": {"id": "gid://shopify/Product/1"}}},
        )

    _validate(
        shopify.product_update,
        {"variables": {"product": {"id": "gid://shopify/Product/1", "title": "New"}}},
    )


def test_page_size_is_bounded_at_shopifys_maximum():
    with pytest.raises(ToolValidationError):
        _validate(shopify.products_list, {"variables": {"first": 500}})


def test_product_status_is_constrained_to_the_documented_enum():
    with pytest.raises(ToolValidationError):
        _validate(
            shopify.product_create,
            {"variables": {"product": {"title": "x", "status": "PUBLISHED"}}},
        )


# -----------------------------------------------------
# Enums modelled whole, and the window nobody sees
# -----------------------------------------------------


def _literal_values(model, field: str):
    from typing import get_args

    annotation = model.model_fields[field].annotation
    # Optional[Literal[...]] -> Literal[...] -> its values
    for arg in get_args(annotation):
        values = get_args(arg)
        if values:
            return set(values)
    return set()


def test_the_sort_key_enums_are_the_documented_sets_not_a_subset():
    """A closed Literal missing a value rejects a call the API would accept.

    And it does so invisibly: the model cannot tell "Shopify will not sort by
    this" from "this pack left it out", so it has no way to recover.
    """
    from charter.packs.shopify.types import (
        CustomersListVariables,
        OrdersListVariables,
        ProductsListVariables,
    )

    assert _literal_values(OrdersListVariables, "sort_key") == {
        "CREATED_AT", "CURRENT_TOTAL_PRICE", "CUSTOMER_NAME", "DESTINATION",
        "FINANCIAL_STATUS", "FULFILLMENT_STATUS", "ID", "ORDER_NUMBER",
        "PO_NUMBER", "PROCESSED_AT", "RELEVANCE", "TOTAL_ITEMS_QUANTITY",
        "TOTAL_PRICE", "UPDATED_AT",
    }
    assert _literal_values(ProductsListVariables, "sort_key") == {
        "CREATED_AT", "ID", "INVENTORY_TOTAL", "PRODUCT_TYPE", "PUBLISHED_AT",
        "RELEVANCE", "TITLE", "UPDATED_AT", "VENDOR",
    }
    assert _literal_values(CustomersListVariables, "sort_key") == {
        "CREATED_AT", "ID", "LOCATION", "NAME", "RELEVANCE", "UPDATED_AT",
    }


@respx.mock
async def test_a_sort_key_that_used_to_be_missing_reaches_the_wire():
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"orders": {"nodes": [], "pageInfo": {"hasNextPage": False,
                                                                "endCursor": None}}}},
        )
    )

    await shopify.orders_list.ainvoke(
        variables={"query": "financial_status:paid", "sort_key": "FULFILLMENT_STATUS"}
    )

    assert _sent()["variables"]["sortKey"] == "FULFILLMENT_STATUS"


def test_the_sixty_day_order_window_is_named_where_the_model_reads_it():
    """Shopify truncates order history silently — no error, no marker on the page.

    An agent asked for last quarter's orders gets a short answer that looks
    complete, so the limit has to be in the text the model actually reads: the
    tool description and the `query` field, not only in a comment.
    """
    assert "60 days" in shopify.orders_list.description
    assert "read_all_orders" in shopify.orders_list.description

    from charter.packs.shopify.types import OrdersListVariables

    assert "60 days" in (OrdersListVariables.model_fields["query"].description or "")


def test_the_window_is_named_for_orders_only():
    """Products and customers have no such limit; saying so there would be noise."""
    for tool in shopify.TOOLS:
        if tool.name != "orders_list":
            assert "read_all_orders" not in tool.description


def test_a_throttled_call_says_how_long_to_wait():
    """Shopify's limit is a cost budget, and it refuses inside a 200.

    No `Retry-After` anywhere, and the bucket is not a request count — but the
    refusing response carries the cost that did not fit, what is left, and the
    refill rate, which is the whole of the arithmetic. Without it an agent that
    trips the one budget-based limit here has nothing to back off on.
    """
    from charter.packs.shopify import SHOPIFY_ENVELOPE

    throttled = {
        "errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
        "extensions": {
            "cost": {
                "requestedQueryCost": 1002,
                "throttleStatus": {
                    "maximumAvailable": 4000.0,
                    "currentlyAvailable": 2,
                    "restoreRate": 200.0,
                },
            }
        },
    }

    with pytest.raises(APIError) as caught:
        SHOPIFY_ENVELOPE.raise_for_payload(throttled, url="https://x", provider="shopify")
    # 1002 wanted, 2 in hand, 200 restored per second.
    assert caught.value.retry_after == 5


def test_an_ordinary_refusal_does_not_invent_a_wait():
    """`userErrors` is a rejected write, not a rate limit."""
    from charter.packs.shopify import SHOPIFY_ENVELOPE

    refused = {
        "data": {"productUpdate": {"userErrors": [{"field": ["id"], "message": "gone"}]}},
        "extensions": {
            "cost": {
                "requestedQueryCost": 10,
                "throttleStatus": {
                    "maximumAvailable": 4000.0,
                    "currentlyAvailable": 3990,
                    "restoreRate": 200.0,
                },
            }
        },
    }

    with pytest.raises(APIError) as caught:
        SHOPIFY_ENVELOPE.raise_for_payload(refused, url="https://x", provider="shopify")
    assert caught.value.retry_after is None


# -----------------------------------------------------
# Fulfilment, inventory, order state
# -----------------------------------------------------


def test_the_idempotency_key_is_a_variable_and_never_a_literal():
    """Shopify caches a key's response for 24 hours. A key baked into the constant
    document would make every adjustment after the first a silent no-op that still
    answers 200 — the worst possible shape for a stock mutation."""
    from charter.packs.shopify import queries

    document = queries.INVENTORY_ADJUST_QUANTITIES
    assert "@idempotent(key: $idempotencyKey)" in document
    assert "$idempotencyKey: String!" in document


def test_each_adjustment_mints_its_own_key():
    from charter.packs.shopify.types import InventoryAdjustVariables

    change = {"delta": 1, "inventory_item_id": "gid://shopify/InventoryItem/1",
              "location_id": "gid://shopify/Location/1", "change_from_quantity": 7}
    payload = {"name": "available", "reason": "correction", "changes": [change]}
    first = InventoryAdjustVariables(input=payload)
    second = InventoryAdjustVariables(input=payload)
    assert first.idempotency_key != second.idempotency_key
    assert first.idempotency_key


@pytest.mark.asyncio
@respx.mock
async def test_the_idempotency_key_reaches_the_wire():
    route = respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"inventoryAdjustQuantities": {
                "inventoryAdjustmentGroup": {"id": "gid://shopify/x/1"}, "userErrors": []}}},
        )
    )
    await shopify.inventory_adjust_quantities.ainvoke(
        {"variables": {"input": {
            "name": "available", "reason": "correction",
            "changes": [{"delta": -2,
                         "inventory_item_id": "gid://shopify/InventoryItem/1",
                         "location_id": "gid://shopify/Location/1",
                         "change_from_quantity": 7}]}}}
    )
    sent = json.loads(route.calls.last.request.content)
    assert sent["variables"]["idempotencyKey"]


def test_stock_states_exclude_the_ones_this_mutation_cannot_write():
    """`on_hand` needs a different mutation and `committed` is Shopify's own."""
    from charter.packs.shopify.types import InventoryAdjustInput

    allowed = InventoryAdjustInput.model_fields["name"].annotation
    import typing
    values = set(typing.get_args(allowed))
    assert values == {"available", "damaged", "quality_control", "reserved", "safety_stock"}
    assert "on_hand" not in values and "committed" not in values


@pytest.mark.asyncio
@respx.mock
async def test_an_order_cancel_refusal_is_not_reported_as_success():
    """orderCancel is the one mutation whose errors are not at `userErrors`."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={"data": {"orderCancel": {
                "job": None,
                "orderCancelUserErrors": [
                    {"field": ["orderId"], "message": "Order cannot be cancelled",
                     "code": "NO_REFUND_METHOD"}
                ],
            }}},
        )
    )
    with pytest.raises(APIError):
        await shopify.order_cancel.ainvoke(
            {"variables": {"order_id": "gid://shopify/Order/1", "reason": "CUSTOMER",
                           "restock": True}}
        )


def test_cancelling_must_say_what_happens_to_the_stock():
    """`restock` is non-null in Shopify's schema, so it is never a silent default."""
    required = shopify.order_cancel.to_json_schema()["parameters"]["$defs"][
        "OrderCancelVariables_LLM"
    ]["required"]
    assert {"orderId", "reason", "restock"} <= set(required)


def test_fulfilment_is_two_tools_because_shopify_makes_the_first_half():
    """Fulfillment orders are created by Shopify and cannot be made by a caller,
    so an order id has to be resolved before anything can be fulfilled."""
    names = {t.name for t in shopify.TOOLS}
    assert {"order_fulfillment_orders", "fulfillment_create"} <= names


def test_a_variant_sku_lives_on_the_inventory_item():
    """Shopify moved it there, and it is the most common porting mistake."""
    from charter.packs.shopify.types import ProductVariantBulkInput

    assert "sku" not in ProductVariantBulkInput.model_fields
    assert "inventory_item" in ProductVariantBulkInput.model_fields


def test_an_adjustment_must_say_what_it_expects_to_overwrite():
    """`changeFromQuantity` is required by Shopify's schema, not by its business
    rules, so a change without it is rejected at the GraphQL layer and the
    mutation never runs. Refusing it here says so in the caller's own terms."""
    from charter.packs.shopify.types import InventoryAdjustVariables

    with pytest.raises(ValidationError):
        InventoryAdjustVariables(
            input={
                "name": "available",
                "reason": "correction",
                "changes": [
                    {
                        "delta": 1,
                        "inventory_item_id": "gid://shopify/InventoryItem/1",
                        "location_id": "gid://shopify/Location/1",
                    }
                ],
            }
        )


def test_a_customer_update_names_the_customer():
    """`customer_update` used to share `CustomerInput` with create, which has no
    `id` — so the tool could not say who to update, and its own docstring asked
    for a field the schema forbade."""
    from charter.packs.shopify.types import CustomerUpdateVariables

    variables = CustomerUpdateVariables(
        input={"id": "gid://shopify/Customer/1", "note": "seen at the trade show"}
    )
    assert variables.input.id == "gid://shopify/Customer/1"

    # And an edit does not have to restate the contact details create insists on.
    assert variables.input.email is None

    with pytest.raises(ValidationError):
        CustomerUpdateVariables(input={"note": "nobody in particular"})


def _declared_variables(document: str) -> set:
    """The ``$name`` variables a GraphQL operation declares.

    Read off the signature — everything before the first selection brace — so a
    ``$variable`` *used* deeper in the document is not mistaken for one declared.
    """
    return set(re.findall(r"\$(\w+)", document.split("{", 1)[0]))


def _offered_variables(tool: Tool) -> set:
    """The variable names a tool's schema lets the caller fill in, spelled the
    way the document spells them."""
    field = tool.args_schema.model_fields.get("variables")
    if field is None:
        return set()
    model = field.annotation
    names = getattr(model, "model_fields", {})
    return {n.split("_")[0] + "".join(w.capitalize() for w in n.split("_")[1:]) for n in names}


@pytest.mark.parametrize("tool", [t for t in shopify.TOOLS], ids=lambda t: t.name)
def test_every_variable_the_schema_offers_is_one_the_document_declares(tool):
    """A variable the document does not declare is dropped in silence.

    `locations_list` inherited `reverse` from `ConnectionVariables` and its
    document never declared it, so the model could ask for the reverse sort
    order, Shopify would answer 200 with the list in the original order, and
    nothing anywhere reported a problem. That is the same failure as a
    misspelled query parameter: the argument is accepted, ignored, and the call
    succeeds.

    Asserted for every tool rather than for `locations` alone, because the
    inheritance that caused it applies to every connection in the pack.
    """
    document = (tool.static_body or {}).get("query")
    if document is None:
        return
    orphans = _offered_variables(tool) - _declared_variables(document)
    assert not orphans, (
        f"{tool.name} offers {sorted(orphans)}, which its document never declares — "
        "the value would be dropped on the way to Shopify"
    )
