"""End-to-end invariants: what actually leaves the process.

Every test here drives the *public* surface — a factory, a Tool, a projection, a
session — through the whole stack and asserts on the bytes respx received. None
of them reaches into `_extract_http_params`, `_create_auto_transformer` or a
generated `_LLM` class, so a refactor underneath moves nothing here: the only
way to break one of these is to change the request a declaration produces, which
is the thing the library promises not to do by accident.

Most of these were written as failing tests against defects found by driving
the library rather than by reading it, and each one is the shortest declaration
that reached its defect. They are kept at that size on purpose: a regression
here should point at one rule, not at a scenario.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Dict, List, Optional, Union

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    Body,
    Case,
    Mode,
    Path,
    Query,
    ToolSession,
    WireName,
    api_key_tool_factory,
    oauth_tool_factory,
)
from charter.auth import StaticTokenProvider
from charter.types.errors import CharterError

BASE = "https://api.example.test/"


# -----------------------------------------------------
# Harness
# -----------------------------------------------------


class Sent:
    """The request the runtime actually put on the wire."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "nothing was sent"
        return self.requests[-1]

    @property
    def url(self) -> str:
        return str(self.last.url)

    @property
    def query(self) -> str:
        return self.last.url.query.decode()

    @property
    def body(self) -> bytes:
        return self.last.content

    @property
    def json_body(self) -> Any:
        return json.loads(self.body)

    @property
    def headers(self) -> httpx.Headers:
        return self.last.headers


@pytest.fixture
def sent():
    """respx answering every request 200, recording what it was handed."""
    record = Sent()
    with respx.mock(assert_all_called=False) as router:

        def responder(request: httpx.Request) -> httpx.Response:
            record.requests.append(request)
            return httpx.Response(200, json={"ok": True})

        router.route().mock(side_effect=responder)
        yield record


def api(**factory_kwargs: Any):
    """An api-key factory pointed at the recorder."""
    factory_kwargs.setdefault("base_url", BASE)
    factory_kwargs.setdefault("api_key_headers", {"x-api-key": "SECRET"})
    factory_kwargs.setdefault("pack", "e2e")
    return api_key_tool_factory(**factory_kwargs)


# -----------------------------------------------------
# The body shape is a property of the schema
# -----------------------------------------------------
#
# `_extract_http_params` takes the unwrap decision from the *schema* and not
# from which fields a call populated, so that the wire shape cannot depend on
# the arguments. It takes it from the executed view, though, and `derived()`
# and `Mode` both change that view — so the shape moves anyway, one level up.


class _Inner(BaseModel):
    text: str


class TwoBodyFields(BaseModel):
    payload: Annotated[_Inner, Body()]
    note: Annotated[Optional[str], Body()] = None


class BodyFieldPlusWithheld(BaseModel):
    payload: Annotated[_Inner, Body()]
    note: Annotated[Optional[str], Body(), Mode("response_only")] = None


def test_two_body_fields_keep_their_names(sent):
    tool = api()(name="t", args_schema=TwoBodyFields, method="POST", url_template="e")
    tool.invoke({"payload": {"text": "hi"}})
    assert sent.json_body == {"payload": {"text": "hi"}}


def test_dropping_a_sibling_does_not_reshape_the_body(sent):
    tool = api()(name="t", args_schema=TwoBodyFields, method="POST", url_template="e")
    narrowed = tool.derived(name="t_narrow", drop={"note"})
    narrowed.invoke({"payload": {"text": "hi"}})
    assert sent.json_body == {"payload": {"text": "hi"}}


def test_a_withheld_sibling_does_not_reshape_the_body(sent):
    tool = api()(name="t", args_schema=BodyFieldPlusWithheld, method="POST", url_template="e")
    tool.invoke({"payload": {"text": "hi"}})
    assert sent.json_body == {"payload": {"text": "hi"}}


def test_shipped_github_projection_keeps_its_body_object(sent):
    from charter.auth import StaticTokenProvider
    from charter.packs import github

    # Configured rather than pointed at $GITHUB_TOKEN: a pack's credential is
    # process-global, so an env var set here is whatever the last test to touch
    # it left behind.
    github.configure(StaticTokenProvider("ghp_test"))

    tool = next(t for t in github.TOOLS if t.name == "pulls_request_reviewers")
    narrowed = tool.derived(name="request_user_reviewers", drop={"team_reviewers"})
    args = {"owner": "o", "repo": "r", "pull_number": 1, "reviewers": ["alice"]}
    narrowed.invoke(args)
    assert sent.json_body == {"reviewers": ["alice"]}


def test_shipped_stripe_projection_keeps_its_bracket_prefix(sent):
    from charter.packs import stripe

    stripe.configure(api_key="sk_test")

    tool = next(t for t in stripe.TOOLS if t.name == "disputes_update")
    narrowed = tool.derived(name="submit_evidence", drop={"metadata", "submit"})
    narrowed.invoke({"dispute": "dp_1", "evidence": {"uncategorized_text": "x"}})
    assert b"evidence%5Buncategorized_text%5D=x" in sent.body


# -----------------------------------------------------
# The key-case cascade, at every level it documents
# -----------------------------------------------------


class _CamelNested(BaseModel):
    __case__ = "camel"
    date_time: str
    time_zone: str


class SnakeToolWithCamelNested(BaseModel):
    summary: Annotated[str, Body()]
    start: Annotated[Optional[_CamelNested], Body()] = None


class _SnakeNested(BaseModel):
    __case__ = "snake"
    keep_me: str


class CamelToolWithSnakeNested(BaseModel):
    summary: Annotated[str, Body()]
    nested: Annotated[Optional[_SnakeNested], Body()] = None


class _MarkedBody(BaseModel):
    display_name: Annotated[str, Case("pascal")]
    i_cal_uid: Annotated[str, WireName("iCalUID")]
    other_key: str


class UnwrappedMarkedBody(BaseModel):
    payload: Annotated[_MarkedBody, Body()]


def test_field_case_marker_on_a_top_level_field(sent):
    class Top(BaseModel):
        display_name: Annotated[str, Case("pascal"), Body()]
        user_id: Annotated[str, Body()]

    tool = api(body_case="camel")(name="t", args_schema=Top, method="POST", url_template="e")
    tool.invoke({"display_name": "x", "user_id": "u"})
    assert sent.json_body == {"DisplayName": "x", "userId": "u"}


def test_wire_name_wins_on_an_unwrapped_body_model(sent):
    tool = api(body_case="camel")(
        name="t", args_schema=UnwrappedMarkedBody, method="POST", url_template="e"
    )
    tool.invoke({"payload": {"display_name": "x", "i_cal_uid": "u", "other_key": "o"}})
    assert sent.json_body["iCalUID"] == "u"


def test_case_marker_on_an_unwrapped_body_model(sent):
    tool = api(body_case="camel")(
        name="t", args_schema=UnwrappedMarkedBody, method="POST", url_template="e"
    )
    tool.invoke({"payload": {"display_name": "x", "i_cal_uid": "u", "other_key": "o"}})
    assert "DisplayName" in sent.json_body


def test_nested_schema_case_widens_the_factory_default(sent):
    tool = api(body_case="snake")(
        name="t", args_schema=SnakeToolWithCamelNested, method="POST", url_template="e"
    )
    tool.invoke({"summary": "s", "start": {"date_time": "2026-01-01", "time_zone": "UTC"}})
    assert sent.json_body["start"] == {"dateTime": "2026-01-01", "timeZone": "UTC"}


def test_nested_schema_case_narrows_the_factory_default(sent):
    tool = api(body_case="camel")(
        name="t", args_schema=CamelToolWithSnakeNested, method="POST", url_template="e"
    )
    tool.invoke({"summary": "s", "nested": {"keep_me": "v"}})
    assert sent.json_body["nested"] == {"keep_me": "v"}


class _ArrayItem(BaseModel):
    user_name: str
    node_id: Annotated[str, Case("pascal")]


class ArrayBody(BaseModel):
    user_name: Annotated[Optional[str], Query()] = None
    items: Annotated[List[_ArrayItem], Body()] = []


def test_an_array_body_is_keyed_off_its_item_model(sent):
    """A list body unwraps to a bare array, so its keys are the item model's —
    not the request model's, which happens to declare `user_name` as a query
    parameter and must not rename anything inside the array."""
    tool = api(body_case="camel")(name="t", args_schema=ArrayBody, method="POST", url_template="e")
    tool.invoke({"user_name": "q", "items": [{"user_name": "a", "node_id": "n"}]})
    assert sent.json_body == [{"userName": "a", "NodeId": "n"}]
    assert sent.last.url.params["user_name"] == "q"


class _Leaf(BaseModel):
    __case__ = "kebab"
    leaf_key: str


class _Branch(BaseModel):
    branch_key: str
    leaf: Optional[_Leaf] = None


class ThreeDeep(BaseModel):
    branch: Annotated[_Branch, Body(envelop=True)]


def test_the_cascade_reaches_every_depth_and_case_does_not_inherit(sent):
    """A model's `__case__` governs its own keys. The model below it falls back
    to the endpoint default rather than to its parent's override."""
    tool = api(body_case="camel")(name="t", args_schema=ThreeDeep, method="POST", url_template="e")
    tool.invoke({"branch": {"branch_key": "b", "leaf": {"leaf_key": "l"}}})
    assert sent.json_body == {"branch": {"branchKey": "b", "leaf": {"leaf-key": "l"}}}


class _SelfRef(BaseModel):
    node_name: str
    child_node: Optional[_SelfRef] = None


_SelfRef.model_rebuild()


class Recursive(BaseModel):
    root: Annotated[_SelfRef, Body(envelop=True)]


def test_a_self_referential_schema_is_converted_at_every_level(sent):
    tool = api(body_case="camel")(name="t", args_schema=Recursive, method="POST", url_template="e")
    tool.invoke({"root": {"node_name": "a", "child_node": {"node_name": "b"}}})
    assert sent.json_body == {"root": {"nodeName": "a", "childNode": {"nodeName": "b"}}}


# -----------------------------------------------------
# Headers: HTTP is case-insensitive, the cascade is not
# -----------------------------------------------------


class NoArgs(BaseModel):
    x: Annotated[Optional[str], Query()] = None


def test_per_call_header_is_the_final_word(sent):
    tool = api(static_headers={"Idempotency-Key": "from-static"})(
        name="t", args_schema=NoArgs, method="GET", url_template="e"
    )
    tool.invoke({}, headers={"Idempotency-Key": "from-caller"})
    assert sent.headers["idempotency-key"] == "from-caller"


def test_per_call_header_wins_whatever_its_spelling(sent):
    tool = api(static_headers={"Idempotency-Key": "from-static"})(
        name="t", args_schema=NoArgs, method="GET", url_template="e"
    )
    tool.invoke({}, headers={"idempotency-key": "from-caller"})
    assert sent.headers["idempotency-key"] == "from-caller"


def test_the_api_key_is_sent_once(sent):
    tool = api(
        api_key_headers={"x-api-key": "SECRET"},
        static_headers={"X-Api-Key": "STALE"},
    )(name="t", args_schema=NoArgs, method="GET", url_template="e")
    tool.invoke({})
    assert sent.headers["x-api-key"] == "SECRET"


def test_a_none_header_is_dropped(sent):
    tool = api()(name="t", args_schema=NoArgs, method="GET", url_template="e")
    tool.invoke({}, headers={"X-Optional": None})  # type: ignore[dict-item]
    assert "x-optional" not in sent.headers


# -----------------------------------------------------
# A credential does not leave the origin it was issued for
# -----------------------------------------------------


def _redirecting_router(record: List[httpx.Request]):
    def responder(request: httpx.Request) -> httpx.Response:
        record.append(request)
        if request.url.host == "elsewhere.test":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(302, headers={"Location": "https://elsewhere.test/asset"})

    return responder


def test_a_bearer_token_does_not_follow_a_redirect_off_origin():
    hops: List[httpx.Request] = []
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=_redirecting_router(hops))
        tool = oauth_tool_factory(
            pack="e2e",
            base_url=BASE,
            provider="v",
            credential_provider=StaticTokenProvider("TOKEN"),
            follow_redirects=True,
        )(name="t", args_schema=NoArgs, method="GET", url_template="download")
        tool.invoke({})
    assert hops[-1].url.host == "elsewhere.test"
    assert "authorization" not in hops[-1].headers


def test_an_api_key_does_not_follow_a_redirect_off_origin():
    hops: List[httpx.Request] = []
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=_redirecting_router(hops))
        tool = api(api_key_headers={"X-Api-Key": "SECRET"}, follow_redirects=True)(
            name="t", args_schema=NoArgs, method="GET", url_template="download"
        )
        tool.invoke({})
    assert hops[-1].url.host == "elsewhere.test"
    assert "x-api-key" not in hops[-1].headers


# -----------------------------------------------------
# Following a redirect changes nothing else about the call
# -----------------------------------------------------


def _redirect_chain(hops: int, seen: List[httpx.Request]):
    """A responder that redirects `hops` times, on-origin, then answers 200."""

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        n = len(seen)
        if n > hops:
            return httpx.Response(200, json={"hops": n})
        return httpx.Response(302, headers={"Location": f"{BASE}hop{n}"})

    return responder


@pytest.mark.parametrize("hops", [1, 20])
def test_a_chain_within_the_budget_returns_its_answer(hops):
    """The budget is redirects *followed*, so the answer to the last one counts.
    Returning only from inside the loop made the limit one lower than it reads,
    and refused a 200 that had already arrived."""
    seen: List[httpx.Request] = []
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=_redirect_chain(hops, seen))
        tool = api(follow_redirects=True)(
            name="t", args_schema=NoArgs, method="GET", url_template="start"
        )
        assert tool.invoke({}) == {"hops": hops + 1}


def test_a_chain_past_the_budget_raises_a_charter_error():
    """And not `httpx.TooManyRedirects`, which every adapter would let through —
    they catch CharterError and nothing else."""
    seen: List[httpx.Request] = []
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=_redirect_chain(21, seen))
        tool = api(follow_redirects=True)(
            name="t", args_schema=NoArgs, method="GET", url_template="start"
        )
        with pytest.raises(CharterError):
            tool.invoke({})


class _Thing(BaseModel):
    thing: Annotated[str, Body()]


@pytest.mark.parametrize(
    ("status", "method", "body"),
    [(303, "GET", b""), (307, "POST", b'{"thing":"v"}')],
)
def test_redirect_method_semantics_are_httpxs_own(status, method, body):
    """The walk is Charter's, the rules are httpx's: 303 downgrades to GET and
    drops the body, 307 preserves both. Reimplementing those was the risk in
    taking the walk over, so they are pinned."""
    seen: List[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/next"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(status, headers={"Location": f"{BASE}next"})

    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=responder)
        tool = api(follow_redirects=True)(
            name="t", args_schema=_Thing, method="POST", url_template="start"
        )
        tool.invoke({"thing": "v"})

    assert (seen[-1].method, seen[-1].content) == (method, body)


def test_a_relative_location_resolves_against_the_hop_it_came_from():
    seen: List[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "moved" in str(request.url):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(302, headers={"Location": "/v2/moved"})

    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=responder)
        tool = api(follow_redirects=True)(
            name="t", args_schema=NoArgs, method="GET", url_template="start"
        )
        tool.invoke({})

    assert str(seen[-1].url) == f"{BASE}v2/moved"


def test_measuring_a_redirected_call_cannot_fail_it():
    """A hop's request carries a stream that was never read, so `.content`
    raises on it. Sizing the payload is measurement, and measurement must never
    turn a good response into an exception — the rule `Tool._report` follows."""
    calls = []

    def responder(request: httpx.Request) -> httpx.Response:
        if "final" in str(request.url):
            return httpx.Response(200, json={"payload": "x" * 100})
        return httpx.Response(302, headers={"Location": f"{BASE}final"})

    with respx.mock(assert_all_called=False) as router:
        router.route().mock(side_effect=responder)
        tool = api(follow_redirects=True, on_call=calls.append)(
            name="t", args_schema=NoArgs, method="GET", url_template="start"
        )
        tool.invoke({})

    assert calls[0].status_code == 200
    assert calls[0].payload_bytes > 100


def test_a_caller_owned_client_survives_a_redirecting_call():
    import asyncio

    async def go():
        def responder(request: httpx.Request) -> httpx.Response:
            if "final" in str(request.url):
                return httpx.Response(200, json={"n": 1})
            return httpx.Response(302, headers={"Location": f"{BASE}final"})

        with respx.mock(assert_all_called=False) as router:
            router.route().mock(side_effect=responder)
            tool = api(follow_redirects=True)(
                name="t", args_schema=NoArgs, method="GET", url_template="start"
            )
            async with httpx.AsyncClient() as client:
                assert await tool.ainvoke({}, client=client) == {"n": 1}
                assert await tool.ainvoke({}, client=client) == {"n": 1}
                assert not client.is_closed

    asyncio.run(go())


# -----------------------------------------------------
# Containers reach the wire, whatever they nest
# -----------------------------------------------------


class _Leafy(BaseModel):
    leaf_key: Annotated[str, Case("pascal")]


class Containers(BaseModel):
    deep: Annotated[Optional[List[List[_Leafy]]], Body()] = None
    mapped: Annotated[Optional[Dict[str, List[_Leafy]]], Body()] = None
    unioned: Annotated[Optional[Union[_Leafy, str]], Body()] = None


def test_models_nested_in_containers_are_serialised_and_keyed(sent):
    """A container of models had one level of unwrapping, so anything deeper
    reached `json.dumps` still holding model instances and raised a bare
    TypeError out of the encoder. Mappings had no branch at all."""
    tool = api(body_case="camel")(name="t", args_schema=Containers, method="POST", url_template="e")
    tool.invoke(
        {
            "deep": [[{"leaf_key": "d"}]],
            "mapped": {"some_key": [{"leaf_key": "m"}]},
            "unioned": {"leaf_key": "u"},
        }
    )
    assert sent.json_body == {
        "deep": [[{"LeafKey": "d"}]],
        "mapped": {"someKey": [{"LeafKey": "m"}]},
        "unioned": {"LeafKey": "u"},
    }


class _Keyed(BaseModel):
    user_name: str
    node_id: Annotated[str, Case("pascal")]


class MapBody(BaseModel):
    entries: Annotated[Dict[str, _Keyed], Body(envelop=True)]


def test_a_mappings_own_keys_are_data_not_field_names(sent):
    """`user_name` here is a key somebody chose, and happens to collide with a
    field of the value model. It takes the plain conversion; only the values
    below it take the model's cascade."""
    tool = api(body_case="camel")(name="t", args_schema=MapBody, method="POST", url_template="e")
    tool.invoke({"entries": {"user_name": {"user_name": "a", "node_id": "n"}}})
    assert sent.json_body == {"entries": {"userName": {"userName": "a", "NodeId": "n"}}}


# -----------------------------------------------------
# A path parameter is not an edit to the endpoint
# -----------------------------------------------------


class OneSegment(BaseModel):
    seg: Annotated[str, Path()]


def _path_tool():
    return api()(name="t", args_schema=OneSegment, method="GET", url_template="resource/{seg}/sub")


@pytest.mark.parametrize("value", ["a/b", "100%", "?x=1", "#frag"])
def test_structural_punctuation_stays_inside_its_segment(sent, value):
    _path_tool().invoke({"seg": value})
    assert sent.last.url.path.startswith("/resource/")
    assert sent.last.url.path.endswith("/sub")
    assert sent.last.url.query == b""


def test_a_dotdot_segment_is_refused(sent):
    with pytest.raises(CharterError):
        _path_tool().invoke({"seg": "../../other"})


def test_a_dot_segment_is_refused(sent):
    """A lone '.' is normalised away by the URL layer, so the parameter would
    delete its own segment — a weaker '..' rather than a different thing."""
    with pytest.raises(CharterError):
        _path_tool().invoke({"seg": "."})


# -----------------------------------------------------
# A model's mistake comes back as something the model can read
# -----------------------------------------------------


def test_a_bad_toolsearch_argument_is_a_charter_error(sent):
    import asyncio

    tool = api(pack="p")(name="alpha_list", args_schema=NoArgs, method="GET", url_template="e")
    session = ToolSession([tool])
    with pytest.raises(CharterError):
        asyncio.run(session.dispatch("ToolSearch", {"query": "alpha", "max_results": "many"}))


def test_an_unknown_tool_is_a_charter_error(sent):
    import asyncio

    tool = api(pack="p")(name="alpha_list", args_schema=NoArgs, method="GET", url_template="e")
    session = ToolSession([tool])
    with pytest.raises(CharterError):
        asyncio.run(session.dispatch("p__nope", {}))


# -----------------------------------------------------
# Things that do hold, pinned so they keep holding
# -----------------------------------------------------


def test_static_query_is_wire_literal_and_unoverridable(sent):
    class Q(BaseModel):
        page_size: Annotated[Optional[int], Query()] = None

    tool = api(static_query={"api-version": "2024-01"}, query_case="camel")(
        name="t", args_schema=Q, method="GET", url_template="e"
    )
    tool.invoke({"page_size": 3})
    assert "api-version=2024-01" in sent.query
    assert "pageSize=3" in sent.query


def test_a_list_query_repeats_its_key(sent):
    class Q(BaseModel):
        label_ids: Annotated[Optional[List[str]], Query()] = None

    api()(name="t", args_schema=Q, method="GET", url_template="e").invoke({"label_ids": ["A", "B"]})
    assert sent.query == "label_ids=A&label_ids=B"


def test_bracket_query_format_indexes_a_list(sent):
    class Q(BaseModel):
        expand: Annotated[Optional[List[str]], Query()] = None

    api(query_format="bracket")(name="t", args_schema=Q, method="GET", url_template="e").invoke(
        {"expand": ["a", "b"]}
    )
    assert sent.last.url.params["expand[0]"] == "a"


def test_a_pinned_value_travels_the_path_a_supplied_one_travels(sent):
    class Q(BaseModel):
        q: Annotated[Optional[str], Query()] = None
        page_size: Annotated[Optional[int], Query()] = None

    tool = api(query_case="camel")(name="t", args_schema=Q, method="GET", url_template="e")
    tool.derived(name="t_pinned", pin={"q": "mimeType='x'"}).invoke({"page_size": 5})
    assert sent.last.url.params["q"] == "mimeType='x'"
    assert sent.last.url.params["pageSize"] == "5"


def test_a_binary_response_keeps_its_bytes():
    with respx.mock as router:
        router.route().mock(
            return_value=httpx.Response(
                200, content=b"\x89PNG\r\n\x1a\n", headers={"content-type": "image/png"}
            )
        )
        out = api()(name="t", args_schema=NoArgs, method="GET", url_template="e").invoke({})
    assert out["content_type"] == "image/png"
    assert out["size_bytes"] == 8


def test_static_body_cannot_be_rewritten_by_tool_input(sent):
    class B(BaseModel):
        query: Annotated[Optional[str], Body()] = None
        doc_id: Annotated[Optional[str], Body()] = None

    tool = api()(
        name="t",
        args_schema=B,
        method="POST",
        url_template="graphql",
        static_body={"query": "{ me }"},
    )
    tool.invoke({"query": "{ everything }", "doc_id": "d"})
    assert sent.json_body["query"] == "{ me }"
