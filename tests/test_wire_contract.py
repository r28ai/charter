"""Contract-layer additions: body format, static params, Retry-After, pagination.

Each of these was previously either impossible to express or pushed into a
pack-local escape hatch.
"""

from __future__ import annotations

import base64
import json
from typing import Annotated, Any, Dict, List, Optional
from urllib.parse import parse_qsl

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    Body,
    Pagination,
    Path,
    Query,
    Tool,
    ToolValidationError,
    api_key_tool_factory,
    oauth_tool_factory,
)
from charter.auth import StaticTokenProvider
from charter.types.errors import DeclarationError

BASE = "https://api.example.com/"


class ChargeCreate(BaseModel):
    """A Stripe-shaped request: nested objects, a list, a bool."""

    amount: Annotated[int, Body()]
    currency: Annotated[str, Body()]
    metadata: Annotated[Optional[Dict[str, Any]], Body()] = None
    capture: Annotated[Optional[bool], Body()] = None


def _tool(**kw) -> Tool:
    base: Dict[str, Any] = dict(
        name="t",
        method="POST",
        url_template="v1/charges",
        args_schema=ChargeCreate,
        base_url=BASE,
        api_key_headers={"Authorization": "Bearer sk_test"},
    )
    base.update(kw)
    return Tool(**base)


def _form(request: httpx.Request) -> Dict[str, str]:
    return dict(parse_qsl(request.content.decode()))


# -----------------------------------------------------
# Body format — form-encoded APIs
# -----------------------------------------------------


@respx.mock
async def test_json_remains_the_default():
    route = respx.post(f"{BASE}v1/charges").mock(return_value=httpx.Response(200, json={}))
    await _tool().ainvoke(amount=2000, currency="usd")

    request = route.calls.last.request
    assert request.headers["content-type"] == "application/json"
    assert b'"amount"' in request.content


@respx.mock
async def test_form_encoding_uses_bracket_notation():
    """The Stripe/Rack convention, which Twilio and OAuth2 token endpoints share."""
    route = respx.post(f"{BASE}v1/charges").mock(return_value=httpx.Response(200, json={}))

    await _tool(body_format="form", body_case="snake").ainvoke(
        amount=2000, currency="usd", metadata={"order_id": "x1"}, capture=False
    )

    request = route.calls.last.request
    assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert _form(request) == {
        "amount": "2000",
        "currency": "usd",
        "metadata[order_id]": "x1",
        "capture": "false",
    }


@respx.mock
async def test_form_encoding_indexes_lists():
    class WithList(BaseModel):
        items: Annotated[list, Body(envelop=True)]

    route = respx.post(f"{BASE}v1/charges").mock(return_value=httpx.Response(200, json={}))
    await _tool(args_schema=WithList, body_format="form").ainvoke(
        items=[{"price": "p1", "qty": 2}, {"price": "p2", "qty": 1}]
    )

    assert _form(route.calls.last.request) == {
        "items[0][price]": "p1",
        "items[0][qty]": "2",
        "items[1][price]": "p2",
        "items[1][qty]": "1",
    }


@respx.mock
async def test_form_encoding_still_honours_key_casing():
    class Cased(BaseModel):
        order_id: Annotated[str, Body()]
        shop_id: Annotated[str, Body()]

    route = respx.post(f"{BASE}v1/charges").mock(return_value=httpx.Response(200, json={}))
    await _tool(args_schema=Cased, body_format="form", body_case="camel").ainvoke(
        order_id="x", shop_id="y"
    )
    assert _form(route.calls.last.request) == {"orderId": "x", "shopId": "y"}


@respx.mock
async def test_a_form_body_that_unwraps_to_a_bare_value_is_a_clear_error():
    """Form encoding cannot express a top-level array or scalar. Emitting
    `[0][price]=` or `=x` would be a silent wire bug, so this raises instead."""

    class Unwrapped(BaseModel):
        items: Annotated[list, Body()]

    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(ValueError, match="must be a mapping of named fields"):
            await _tool(args_schema=Unwrapped, body_format="form").ainvoke(items=[1, 2])
        assert not route.called


@respx.mock
async def test_form_encoding_omits_none_rather_than_sending_empty():
    route = respx.post(f"{BASE}v1/charges").mock(return_value=httpx.Response(200, json={}))
    await _tool(body_format="form").ainvoke(amount=1, currency="usd")
    assert set(_form(route.calls.last.request)) == {"amount", "currency"}


def test_factory_declares_body_format_once():
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers={"Authorization": "Bearer k"}, body_format="form"
    )
    tools = [
        factory(name=f"t{i}", args_schema=ChargeCreate, method="POST", url_template="v1/charges")
        for i in range(2)
    ]
    assert all(t.body_format == "form" for t in tools)


def test_a_single_endpoint_can_override_the_body_format():
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers={"Authorization": "Bearer k"}, body_format="form"
    )
    odd = factory(
        name="odd",
        args_schema=ChargeCreate,
        method="POST",
        url_template="v1/odd",
        body_format_override="json",
    )
    assert odd.body_format == "json"


# -----------------------------------------------------
# Static query and headers
# -----------------------------------------------------


class Simple(BaseModel):
    id: Annotated[str, Path()]
    q: Annotated[Optional[str], Query()] = None
    # cursor_param must name a real schema field — the declaration says where the
    # cursor goes, it does not invent a parameter.
    cursor: Annotated[Optional[str], Query()] = None


@respx.mock
async def test_static_query_is_sent_on_every_request():
    """Azure requires api-version on every call; it must not be a schema field."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        static_query={"api-version": "2024-01-01"},
    )
    await tool.ainvoke(id="x")
    assert dict(route.calls.last.request.url.params)["api-version"] == "2024-01-01"


@respx.mock
async def test_static_query_keys_are_never_case_converted():
    """`api-version` must stay `api-version`, not become `apiVersion`."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        query_case="camel",
        static_query={"api-version": "2024-01-01", "prettyPrint": "false"},
    )
    await tool.ainvoke(id="x", q="hello")

    params = dict(route.calls.last.request.url.params)
    assert "api-version" in params  # untouched
    assert params["q"] == "hello"   # schema fields still cased normally


@respx.mock
async def test_static_query_does_not_appear_in_the_llm_schema():
    """The whole point: infrastructure the model never sees or sets."""
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        static_query={"api-version": "2024-01-01"},
    )
    assert "api-version" not in tool.llm_schema().model_fields
    assert "api_version" not in tool.llm_schema().model_fields


@respx.mock
async def test_static_headers_are_sent_on_every_request():
    """Notion rejects any request without Notion-Version."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        static_headers={"Notion-Version": "2022-06-28"},
    )
    await tool.ainvoke(id="x")
    assert route.calls.last.request.headers["notion-version"] == "2022-06-28"


@respx.mock
async def test_oauth_packs_can_now_set_a_constant_header():
    """Previously impossible — oauth_tool_factory took no headers at all, so an
    OAuth API requiring a version header could not be expressed."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    factory = oauth_tool_factory(
        base_url=BASE,
        provider="notion",
        credential_provider=StaticTokenProvider("tok"),
        static_headers={"Notion-Version": "2022-06-28"},
    )
    tool = factory(name="t", args_schema=Simple, method="GET", url_template="v1/{id}")
    await tool.ainvoke(id="x")

    request = route.calls.last.request
    assert request.headers["notion-version"] == "2022-06-28"
    assert request.headers["authorization"] == "Bearer tok"


@respx.mock
async def test_a_transport_override_still_beats_a_static_header():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        static_headers={"X-Thing": "static"},
        build_request=lambda _: {"headers": {"X-Thing": "override"}},
    )
    await tool.ainvoke(id="x")
    assert route.calls.last.request.headers["x-thing"] == "override"


# -----------------------------------------------------
# Retry-After
# -----------------------------------------------------


@respx.mock
async def test_retry_after_is_surfaced_on_429():
    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "30"}, json={})
    )
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    with pytest.raises(APIError) as excinfo:
        await tool.ainvoke(id="x")

    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 30
    assert "retry after 30s" in str(excinfo.value)


@respx.mock
async def test_retry_after_is_surfaced_on_503_too():
    respx.get(f"{BASE}v1/x").mock(
        return_value=httpx.Response(503, headers={"Retry-After": "5"}, text="down")
    )
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    with pytest.raises(APIError) as excinfo:
        await tool.ainvoke(id="x")
    assert excinfo.value.retry_after == 5


@respx.mock
@pytest.mark.parametrize("header", [None, "", "Wed, 21 Oct 2026 07:28:00 GMT", "junk", "-5"])
async def test_absent_or_unparseable_retry_after_is_none(header):
    """An HTTP-date is legal but rare in JSON APIs; guessing at clock skew is
    worse than reporting nothing."""
    headers = {"Retry-After": header} if header is not None else {}
    respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(429, headers=headers, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    with pytest.raises(APIError) as excinfo:
        await tool.ainvoke(id="x")
    assert excinfo.value.retry_after is None


# -----------------------------------------------------
# Pagination
# -----------------------------------------------------

SLACKISH = Pagination(
    cursor_field="response_metadata.next_cursor", cursor_param="cursor", more_field="has_more"
)
GOOGLEISH = Pagination(cursor_field="nextPageToken", cursor_param="pageToken")


def test_dotted_cursor_paths_are_walked():
    assert SLACKISH.next_cursor({"response_metadata": {"next_cursor": "abc"}}) == "abc"


def test_a_flat_cursor_field_works():
    assert GOOGLEISH.next_cursor({"nextPageToken": "t2"}) == "t2"


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"response_metadata": {}},
        {"response_metadata": {"next_cursor": ""}},
        {"response_metadata": None},
        "not a dict",
    ],
)
def test_absent_or_empty_cursor_means_no_further_page(response):
    """Slack sends "" on the last page — treating that as a cursor loops forever."""
    assert SLACKISH.next_cursor(response) is None
    assert SLACKISH.next_page_args(response) is None


def test_more_field_wins_over_a_stale_cursor():
    stale = {"has_more": False, "response_metadata": {"next_cursor": "abc"}}
    assert SLACKISH.has_more(stale) is False
    assert SLACKISH.next_page_args(stale) is None


def test_next_page_args_carries_the_previous_arguments_forward():
    response = {"has_more": True, "response_metadata": {"next_cursor": "abc"}}
    assert SLACKISH.next_page_args(response, {"channel": "C1", "limit": 50}) == {
        "channel": "C1",
        "limit": 50,
        "cursor": "abc",
    }


def test_next_page_args_replaces_a_previous_cursor():
    response = {"has_more": True, "response_metadata": {"next_cursor": "page2"}}
    assert SLACKISH.next_page_args(response, {"cursor": "page1"})["cursor"] == "page2"


def test_pagination_is_declarative_data():
    assert Pagination(cursor_field="a", cursor_param="b") == Pagination(
        cursor_field="a", cursor_param="b"
    )


@respx.mock
async def test_a_caller_can_page_without_knowing_the_convention():
    """The point of declaring it: the loop is the caller's, the convention is not."""
    pages = [
        {"messages": [1], "has_more": True, "response_metadata": {"next_cursor": "c2"}},
        {"messages": [2], "has_more": False, "response_metadata": {"next_cursor": ""}},
    ]
    route = respx.get(f"{BASE}v1/x").mock(side_effect=[httpx.Response(200, json=p) for p in pages])

    tool = _tool(
        args_schema=Simple, method="GET", url_template="v1/{id}", pagination=SLACKISH
    )

    args: Optional[Dict[str, Any]] = {"id": "x"}
    collected = []
    while args is not None:
        page = await tool.ainvoke(args)
        collected.extend(page["messages"])
        args = tool.pagination.next_page_args(page, args)

    assert collected == [1, 2]
    assert dict(route.calls[-1].request.url.params)["cursor"] == "c2"


def test_factory_declares_pagination_once():
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers={"Authorization": "Bearer k"}, pagination=GOOGLEISH
    )
    tool = factory(name="t", args_schema=Simple, method="GET", url_template="v1/{id}")
    assert tool.pagination is GOOGLEISH


# -----------------------------------------------------
# Per-invocation headers — the host's channel, not the model's
# -----------------------------------------------------


@respx.mock
async def test_per_call_headers_reach_the_wire():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "x"}, headers={"Idempotency-Key": "key-1"})
    assert route.calls.last.request.headers["idempotency-key"] == "key-1"


@respx.mock
async def test_the_same_tool_can_send_a_different_value_per_call():
    """The whole point: these vary per invocation, unlike static_headers."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "x"}, headers={"Stripe-Account": "acct_1"})
    await tool.ainvoke({"id": "x"}, headers={"Stripe-Account": "acct_2"})

    assert route.calls[0].request.headers["stripe-account"] == "acct_1"
    assert route.calls[1].request.headers["stripe-account"] == "acct_2"


@respx.mock
async def test_no_header_is_sent_when_none_is_given():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    await tool.ainvoke(id="x")
    assert "idempotency-key" not in route.calls.last.request.headers


@respx.mock
async def test_a_model_cannot_set_a_header_through_tool_arguments():
    """`headers` is keyword-only and never merged into args. A model filling in
    tool arguments has no path to the header dict.

    The attempt is now *refused* rather than quietly dropped: `headers` is not a
    declared field, and an undeclared argument is a validation error. So the
    injected header never reaches the request, and no request is made at all.
    """
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    # The shape a prompt-injected model might try.
    with pytest.raises(ToolValidationError, match="not permitted"):
        await tool.ainvoke({"id": "x", "headers": {"Stripe-Account": "acct_attacker"}})

    assert not route.calls


@respx.mock
async def test_per_call_headers_are_not_part_of_the_llm_schema():
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    assert "headers" not in tool.llm_schema().model_fields
    assert "headers" not in tool.to_json_schema()["parameters"]["properties"]


@respx.mock
async def test_per_call_headers_beat_static_headers():
    """The call site is the most specific authority."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        static_headers={"X-Thing": "static"},
    )
    await tool.ainvoke({"id": "x"}, headers={"X-Thing": "per-call"})
    assert route.calls.last.request.headers["x-thing"] == "per-call"


@respx.mock
async def test_per_call_headers_beat_a_build_request_override():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(
        args_schema=Simple,
        method="GET",
        url_template="v1/{id}",
        build_request=lambda _: {"headers": {"X-Thing": "from-hook"}},
    )
    await tool.ainvoke({"id": "x"}, headers={"X-Thing": "per-call"})
    assert route.calls.last.request.headers["x-thing"] == "per-call"


@respx.mock
async def test_per_call_headers_do_not_clobber_auth():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    await tool.ainvoke({"id": "x"}, headers={"Idempotency-Key": "k"})
    assert route.calls.last.request.headers["authorization"] == "Bearer sk_test"


@respx.mock
async def test_per_call_headers_work_on_the_bearer_path_too():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    factory = oauth_tool_factory(
        base_url=BASE, provider="p", credential_provider=StaticTokenProvider("tok")
    )
    tool = factory(name="t", args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "x"}, headers={"X-Tenant": "t1"})
    request = route.calls.last.request
    assert request.headers["x-tenant"] == "t1"
    assert request.headers["authorization"] == "Bearer tok"


@respx.mock
async def test_a_none_valued_header_is_dropped_not_sent_empty():
    """Lets a caller pass an optional header unconditionally."""
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    await tool.ainvoke({"id": "x"}, headers={"X-Opt": None, "X-Set": "yes"})

    request = route.calls.last.request
    assert "x-opt" not in request.headers
    assert request.headers["x-set"] == "yes"


def test_sync_invoke_accepts_headers_too():
    import respx as _respx

    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")
    with _respx.mock:
        route = _respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
        tool.invoke({"id": "x"}, headers={"X-Thing": "sync"})
        assert route.calls.last.request.headers["x-thing"] == "sync"


# -----------------------------------------------------
# static_body — a constant that belongs in the body
#
# The GraphQL case: the query document is what the tool *is*, not something the
# model chooses. static_query and static_headers already covered constants in
# the other two places a request has; this is the third.
# -----------------------------------------------------


class GqlVariables(BaseModel):
    first: Optional[int] = None
    after: Optional[str] = None


class GqlRequest(BaseModel):
    variables: Annotated[GqlVariables, Body(envelop=True)]


DOCUMENT = "query Issues($first: Int) { issues(first: $first) { nodes { id } } }"


class NoVars(BaseModel):
    variables: Annotated[Optional[GqlVariables], Body(envelop=True)] = None


class Sneaky(BaseModel):
    """Two Body() fields, so the body is an object with a `query` key in it —
    the only shape in which tool input could collide with the document."""

    variables: Annotated[Optional[GqlVariables], Body()] = None
    query: Annotated[Optional[str], Body()] = None


class ScalarBody(BaseModel):
    value: Annotated[List[str], Body()]


class Ping(BaseModel):
    note: Annotated[Optional[str], Body()] = None


def _gql_tool(**kwargs):
    return Tool(
        name="issues",
        method="POST",
        url_template="graphql",
        args_schema=GqlRequest,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
        static_body={"query": DOCUMENT},
        **kwargs,
    )


@respx.mock
async def test_static_body_puts_the_document_beside_the_variables():
    route = respx.post("https://api.example.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    await _gql_tool().ainvoke(variables={"first": 10})

    assert json.loads(route.calls.last.request.content) == {
        "query": DOCUMENT,
        "variables": {"first": 10},
    }


@respx.mock
async def test_static_body_is_the_whole_body_when_there_are_no_variables():
    route = respx.post("https://api.example.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    tool = Tool(
        name="viewer",
        method="POST",
        url_template="graphql",
        args_schema=NoVars,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
        static_body={"query": DOCUMENT},
    )
    await tool.ainvoke()

    request = route.calls.last.request
    assert json.loads(request.content) == {"query": DOCUMENT}
    # A body appeared, so the JSON content type must appear with it.
    assert request.headers["content-type"] == "application/json"


@respx.mock
async def test_static_body_is_wire_literal_and_not_case_converted():
    """`query` is the key GraphQL wants; camelising it would break the request."""
    route = respx.post("https://api.example.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    tool = Tool(
        name="issues",
        method="POST",
        url_template="graphql",
        args_schema=GqlRequest,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
        static_body={"query": DOCUMENT, "operation_name": "Issues"},
        body_case="camel",
    )
    await tool.ainvoke(variables={"first": 1})

    sent = json.loads(route.calls.last.request.content)
    assert "query" in sent and "operation_name" in sent
    assert "operationName" not in sent


@respx.mock
async def test_tool_input_cannot_overwrite_a_static_body_key():
    """Infrastructure wins: the model must not be able to rewrite the document."""
    route = respx.post("https://api.example.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {}})
    )

    tool = Tool(
        name="sneaky",
        method="POST",
        url_template="graphql",
        args_schema=Sneaky,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
        static_body={"query": DOCUMENT},
    )
    await tool.ainvoke(query="mutation { deleteEverything }", variables={"first": 1})

    sent = json.loads(route.calls.last.request.content)
    assert sent["query"] == DOCUMENT
    assert sent["variables"] == {"first": 1}


async def test_static_body_refuses_to_merge_into_a_non_object_body():
    tool = Tool(
        name="scalar",
        method="POST",
        url_template="graphql",
        args_schema=ScalarBody,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
        static_body={"query": DOCUMENT},
    )

    with pytest.raises(ValueError, match="object body"):
        await tool.ainvoke(value=["a"])


def test_static_body_is_absent_unless_declared():
    tool = Tool(
        name="plain",
        method="POST",
        url_template="x",
        args_schema=GqlRequest,
        base_url="https://api.example.com/",
        api_key_headers={"Authorization": "key"},
    )
    assert tool.static_body is None


# -----------------------------------------------------
# A base URL that is a property of the installation
# -----------------------------------------------------


@respx.mock
async def test_a_callable_base_url_is_resolved_per_request():
    """Shopify's host is only known once someone installs the app."""
    respx.post("https://store-a.example.com/v1/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    respx.post("https://store-b.example.com/v1/ping").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    host = {"value": "https://store-a.example.com/"}

    tool = Tool(
        name="ping",
        method="POST",
        url_template="v1/ping",
        args_schema=Ping,
        base_url=lambda: host["value"],
        api_key_headers={"Authorization": "key"},
    )

    await tool.ainvoke(note="a")
    assert respx.calls.last.request.url.host == "store-a.example.com"

    host["value"] = "https://store-b.example.com/"
    await tool.ainvoke(note="b")
    assert respx.calls.last.request.url.host == "store-b.example.com"


@respx.mock
async def test_an_unresolved_base_url_fails_before_anything_is_sent():
    route = respx.route().mock(return_value=httpx.Response(200, json={}))

    tool = Tool(
        name="ping",
        method="POST",
        url_template="v1/ping",
        args_schema=Ping,
        base_url=lambda: "",
        api_key_headers={"Authorization": "key"},
    )

    with pytest.raises(ValueError, match="No base URL"):
        await tool.ainvoke(note="a")
    assert not route.called


# -----------------------------------------------------
# Page-number pagination, and a `more_field` that is a path
# -----------------------------------------------------


GITHUBISH = Pagination(page_param="page", per_page_param="per_page")
SEARCHISH = Pagination(page_param="page", per_page_param="per_page", items_field="items")
RELAYISH = Pagination(
    cursor_field="pageInfo.endCursor",
    cursor_param="variables.after",
    more_field="pageInfo.hasNextPage",
)


def test_a_pagination_declares_one_style_and_says_which():
    assert GITHUBISH.style == "page"
    assert RELAYISH.style == "cursor"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "either cursor_field"),
        ({"cursor_field": "a"}, "Cursor pagination needs both"),
        ({"page_param": "page"}, "Page-number pagination needs both"),
        ({"cursor_field": "a", "cursor_param": "b", "page_param": "p"}, "one style"),
    ],
)
def test_a_half_declared_pagination_is_refused_at_build_time(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Pagination(**kwargs)


def test_page_numbers_advance_while_pages_come_back_full():
    previous = {"owner": "o", "per_page": 2, "page": 1}
    assert GITHUBISH.next_page_args([1, 2], previous) == {**previous, "page": 2}


def test_a_short_page_is_the_end_because_there_is_no_other_signal():
    previous = {"per_page": 2, "page": 3}
    assert GITHUBISH.next_page_args([1], previous) is None
    assert GITHUBISH.next_page_args([], previous) is None


def test_the_first_page_is_assumed_when_no_page_number_was_given():
    assert GITHUBISH.next_page_args([1, 2], {"per_page": 2}) == {"per_page": 2, "page": 2}


def test_without_a_page_size_only_an_empty_page_ends_the_walk():
    """Reporting 'maybe' is not an option; an extra empty call beats stopping early."""
    assert GITHUBISH.has_more([1, 2, 3], None) is True
    assert GITHUBISH.has_more([], None) is False


def test_a_search_style_body_is_read_through_items_field():
    previous = {"q": "x", "per_page": 2, "page": 1}
    assert SEARCHISH.next_page_args({"total_count": 9, "items": [1, 2]}, previous) == {
        **previous,
        "page": 2,
    }
    assert SEARCHISH.next_page_args({"total_count": 3, "items": [1]}, previous) is None


def test_a_page_style_pagination_reports_no_cursor():
    assert GITHUBISH.next_cursor([1, 2]) is None


def test_more_field_is_a_path_so_a_relay_connection_can_terminate():
    """A Relay API sends an endCursor on its last page too.

    Before more_field accepted a path, `pageInfo.hasNextPage` was unreachable and
    the cursor fallback said 'another page' forever.
    """
    last = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": "c9"}}
    more = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c9"}}

    assert RELAYISH.has_more(last) is False
    assert RELAYISH.has_more(more) is True
    assert RELAYISH.next_page_args(last, {"variables": {}}) is None


def test_a_cursor_param_may_be_a_path_into_a_nested_argument():
    page = {"pageInfo": {"hasNextPage": True, "endCursor": "c2"}}
    assert RELAYISH.next_page_args(page, {"variables": {"first": 50}}) == {
        "variables": {"first": 50, "after": "c2"}
    }


def test_setting_a_nested_cursor_leaves_the_previous_arguments_untouched():
    previous = {"variables": {"first": 50}}
    RELAYISH.next_page_args({"pageInfo": {"hasNextPage": True, "endCursor": "c2"}}, previous)
    assert previous == {"variables": {"first": 50}}


def test_a_missing_more_field_falls_back_to_the_cursor():
    """An API that omits the flag entirely still has to be walkable."""
    partial = Pagination(cursor_field="next", cursor_param="cursor", more_field="has_more")
    assert partial.has_more({"next": "c1"}) is True
    assert partial.has_more({"next": ""}) is False
    # And when the flag is present it wins, even against a live cursor.
    assert partial.has_more({"next": "c1", "has_more": False}) is False


# -----------------------------------------------------
# Path parameters cannot rewrite the URL
# -----------------------------------------------------


@respx.mock
async def test_a_path_parameter_cannot_walk_up_the_template():
    """`..` in a path value would change which endpoint is called.

    Reproduced against the live GitHub API before this was refused:
    `repos_get_content(owner=o, repo=r, path="../../other/contents/README.md")`
    returned 200 with a *different repository's* file, and
    `path="../../../../user"` left the repository API altogether. The value
    comes from a model, so this is a boundary, not a typo.
    """
    respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    with pytest.raises(ToolValidationError, match=r"'\.\.' segment"):
        await tool.ainvoke({"id": "../../elsewhere"})


@respx.mock
async def test_a_path_parameter_cannot_start_a_query_string_or_fragment():
    """`?` and `#` are structural: unescaped, a value adds parameters of its own."""
    route = respx.get(url__regex=rf"{BASE}v1/.*").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "file.md?ref=secret"})
    url = str(route.calls.last.request.url)
    assert "%3F" in url
    assert not route.calls.last.request.url.params

    await tool.ainvoke({"id": "file.md#frag"})
    assert "%23" in str(route.calls.last.request.url)


@respx.mock
async def test_a_path_parameter_stays_inside_its_own_segment():
    """`/` is encoded unless the field declares itself multi-segment."""
    route = respx.get(url__regex=rf"{BASE}v1/.*").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "a/b"})
    assert "v1/a%2Fb" in str(route.calls.last.request.url)


@respx.mock
async def test_allow_slash_keeps_a_genuinely_multi_segment_value():
    """GitHub's file path is one value that legitimately spans segments."""

    class FilePath(BaseModel):
        path: Annotated[str, Path(allow_slash=True)]

    route = respx.get(url__regex=rf"{BASE}v1/.*").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=FilePath, method="GET", url_template="v1/{path}")

    await tool.ainvoke({"path": "src/charter/tool.py"})
    assert "v1/src/charter/tool.py" in str(route.calls.last.request.url)
    # ...and the opt-in does not also buy an escape hatch.
    with pytest.raises(ToolValidationError, match=r"'\.\.' segment"):
        await tool.ainvoke({"path": "src/../../other"})


@respx.mock
async def test_a_path_parameter_keeps_characters_that_are_legal_in_a_segment():
    """A Calendar id is an email; a Sheets range is `Sheet1!A1:B2`."""
    route = respx.get(url__regex=rf"{BASE}v1/.*").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(args_schema=Simple, method="GET", url_template="v1/{id}")

    await tool.ainvoke({"id": "Sheet1!A1:B2"})
    assert "v1/Sheet1!A1:B2" in str(route.calls.last.request.url)


# -----------------------------------------------------
# A lone Body() field: what unwraps, and what keeps its name
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_lone_scalar_body_field_keeps_its_name_in_json():
    """Slack's `conversations_join` and GitHub's `actions_rerun_workflow` shape.

    Unwrapping promotes a nested structure's fields to the root. A scalar has
    none, and taking the rule literally sent a bare JSON string as the whole
    document — which every one of these APIs rejects. Both tools were declared
    this way and neither could run.
    """

    class Join(BaseModel):
        channel: Annotated[str, Body()]

    route = respx.post(f"{BASE}join").mock(return_value=httpx.Response(200, json={"ok": True}))
    await _tool(args_schema=Join, method="POST", url_template="join").ainvoke(
        {"channel": "C0123"}
    )

    assert json.loads(route.calls.last.request.content) == {"channel": "C0123"}


@pytest.mark.asyncio
@respx.mock
async def test_a_lone_scalar_body_field_is_form_encodable():
    """Stripe's `payment_methods_attach` shape, and the sharper half of the same
    bug: a form body has no representation for a bare value at all, so this did
    not reach the network — it raised a DeclarationError locally, on a schema the
    author had declared correctly."""

    class Attach(BaseModel):
        payment_method: Annotated[str, Path()]
        customer: Annotated[str, Body()]

    route = respx.post(f"{BASE}v1/payment_methods/pm_1/attach").mock(
        return_value=httpx.Response(200, json={"id": "pm_1"})
    )
    tool = _tool(
        args_schema=Attach,
        method="POST",
        url_template="v1/payment_methods/{payment_method}/attach",
        body_format="form",
    )
    await tool.ainvoke({"payment_method": "pm_1", "customer": "cus_1"})

    assert dict(parse_qsl(route.calls.last.request.content.decode())) == {"customer": "cus_1"}


@pytest.mark.asyncio
@respx.mock
async def test_a_lone_model_body_field_still_unwraps():
    """The other 90%, unchanged: GitHub's `issues_create`, every Google pack."""

    class Issue(BaseModel):
        title: str
        body: Optional[str] = None

    class Create(BaseModel):
        issue: Annotated[Issue, Body()]

    route = respx.post(f"{BASE}issues").mock(return_value=httpx.Response(200, json={}))
    await _tool(args_schema=Create, method="POST", url_template="issues").ainvoke(
        {"issue": {"title": "Bug"}}
    )

    assert json.loads(route.calls.last.request.content) == {"title": "Bug"}


# -----------------------------------------------------
# Responses that are not JSON, and requests that are not documents
# -----------------------------------------------------


def _fetch_tool(**overrides: Any) -> Tool:
    """A minimal GET whose response shape is what each test below is about."""

    class Args(BaseModel):
        thing: Annotated[str, Path()]

    kwargs: Dict[str, Any] = dict(
        name="fetch",
        args_schema=Args,
        method="GET",
        url_template="things/{thing}",
        description="Fetch a thing.",
        action_label="Fetches.",
    )
    kwargs.update(overrides)
    factory = api_key_tool_factory(
        base_url="https://api.example.com/", api_key_headers={"x-api-key": "k"}
    )
    return factory(**kwargs)


@respx.mock
async def test_a_text_response_is_decoded_and_a_binary_one_keeps_its_bytes():
    """`resp.text` replaces what it cannot decode, which is how a ZIP becomes prose.

    A response body that is not text is kept as bytes — base64-encoded, with its
    type and size — because the alternative is handing a caller replacement
    characters that read like content. The failure is one layer below where a
    response handler could catch it, so it is decided here.
    """
    respx.get("https://api.example.com/things/log").mock(
        return_value=httpx.Response(
            200, text="line one\nline two", headers={"Content-Type": "text/plain; charset=utf-8"}
        )
    )
    assert await _fetch_tool().ainvoke(thing="log") == {"raw": "line one\nline two"}

    payload = b"PK\x03\x04\xff\xfe\x00binary"
    respx.get("https://api.example.com/things/zip").mock(
        return_value=httpx.Response(200, content=payload, headers={"Content-Type": "application/zip"})
    )
    out = await _fetch_tool().ainvoke(thing="zip")
    assert base64.b64decode(out["raw_base64"]) == payload
    assert out["content_type"] == "application/zip"
    assert out["size_bytes"] == len(payload)
    assert "raw" not in out, "a binary body must not also be offered as text"


@respx.mock
async def test_a_declared_charset_is_what_makes_a_vendor_type_text():
    """No list of media types can cover the vendor ones, and a charset can.

    `application/vnd.github.diff` is a diff and is text; nothing about the type
    string says so. The server saying how its bytes become characters is the one
    signal that generalises.
    """
    respx.get("https://api.example.com/things/diff").mock(
        return_value=httpx.Response(
            200,
            text="@@ -1 +1 @@\n-a\n+b",
            headers={"Content-Type": "application/vnd.example.diff; charset=utf-8"},
        )
    )
    assert await _fetch_tool().ainvoke(thing="diff") == {"raw": "@@ -1 +1 @@\n-a\n+b"}


@respx.mock
async def test_a_redirect_is_not_followed_unless_the_tool_asks():
    """Off by default, because on a JSON API a 3xx is usually a wrong URL.

    Following one silently would hide that. Where the redirect *is* the answer —
    an object store handing back a signed URL — the tool declares it.
    """
    respx.get("https://api.example.com/things/blob").mock(
        return_value=httpx.Response(302, headers={"Location": "https://cdn.example.com/blob"})
    )
    elsewhere = respx.get("https://cdn.example.com/blob").mock(
        return_value=httpx.Response(200, text="the payload", headers={"Content-Type": "text/plain"})
    )

    assert await _fetch_tool().ainvoke(thing="blob") == {}
    assert not elsewhere.called

    assert await _fetch_tool(follow_redirects_override=True).ainvoke(thing="blob") == {
        "raw": "the payload"
    }
    assert elsewhere.called


@respx.mock
async def test_the_credential_does_not_cross_an_origin_on_a_redirect():
    """A signed URL authenticates itself and has no business holding a token.

    httpx drops `Authorization` when a redirect leaves the origin, and following
    redirects is only safe because it does. Asserted rather than assumed: what
    would leak is a credential, and the leak would be silent.
    """
    factory = oauth_tool_factory(
        base_url="https://api.example.com/",
        provider="example",
        credential_provider=StaticTokenProvider("secret-token"),
        follow_redirects=True,
    )

    class Args(BaseModel):
        thing: Annotated[str, Path()]

    tool = factory(
        name="fetch", args_schema=Args, method="GET", url_template="things/{thing}",
        description="d", action_label="a",
    )

    respx.get("https://api.example.com/things/blob").mock(
        return_value=httpx.Response(302, headers={"Location": "https://cdn.example.com/blob"})
    )
    landed = respx.get("https://cdn.example.com/blob").mock(
        return_value=httpx.Response(200, text="ok", headers={"Content-Type": "text/plain"})
    )

    await tool.ainvoke(thing="blob")

    sent = {k.lower() for k in landed.calls.last.request.headers}
    assert "authorization" not in sent
    assert "secret-token" not in str(landed.calls.last.request.headers)


@respx.mock
async def test_a_raw_body_sends_the_bytes_and_nothing_around_them():
    """For the endpoints that take a *file* rather than a document.

    JSON and form encoding both wrap the value in something; an upload endpoint
    wants neither. The `Content-Type` is the declaration's to set, because there
    is no type that can be inferred from an arbitrary byte string.
    """

    class Upload(BaseModel):
        thing: Annotated[str, Path()]
        content: Annotated[str, Body()]

    factory = api_key_tool_factory(
        base_url="https://api.example.com/",
        api_key_headers={"x-api-key": "k"},
        body_format="raw",
        static_headers={"Content-Type": "application/octet-stream"},
    )
    tool = factory(
        name="upload", args_schema=Upload, method="POST", url_template="things/{thing}",
        description="d", action_label="a",
        # A lone scalar Body() keeps its name, which is right everywhere but here.
        build_request=lambda model: {"body": model.content},
    )
    route = respx.post("https://api.example.com/things/x").mock(
        return_value=httpx.Response(201, json={"ok": True})
    )

    await tool.ainvoke(thing="x", content="the whole file\n")

    assert route.calls.last.request.content == b"the whole file\n"
    assert route.calls.last.request.headers["Content-Type"] == "application/octet-stream"


async def test_a_raw_body_refuses_a_mapping_rather_than_serialising_one():
    """A dict here means the schema was not the shape the format needs, and
    quietly JSON-encoding it would send a document to an endpoint expecting a
    file."""

    class TwoFields(BaseModel):
        thing: Annotated[str, Path()]
        a: Annotated[str, Body()]
        b: Annotated[str, Body()]

    factory = api_key_tool_factory(
        base_url="https://api.example.com/", api_key_headers={"x-api-key": "k"},
        body_format="raw",
    )
    tool = factory(
        name="upload", args_schema=TwoFields, method="POST", url_template="things/{thing}",
        description="d", action_label="a",
    )
    with pytest.raises(DeclarationError, match="raw body must be a string or bytes"):
        await tool.ainvoke(thing="x", a="1", b="2")


async def test_a_static_body_cannot_be_merged_into_a_raw_one():
    """There is no object to add a key to. Refused rather than dropped."""

    class Args(BaseModel):
        thing: Annotated[str, Path()]
        content: Annotated[str, Body()]

    factory = api_key_tool_factory(
        base_url="https://api.example.com/", api_key_headers={"x-api-key": "k"},
        body_format="raw",
    )
    tool = factory(
        name="upload", args_schema=Args, method="POST", url_template="things/{thing}",
        description="d", action_label="a", static_body={"version": "1"},
    )
    with pytest.raises(DeclarationError, match="static_body cannot be merged into a raw body"):
        await tool.ainvoke(thing="x", content="bytes")
