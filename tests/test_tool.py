"""R4 — Tool and the factories."""

from __future__ import annotations

import base64
import email
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel

from charter import (
    APIError,
    Body,
    CredentialError,
    EmailContent,
    Format,
    Mode,
    Path,
    Query,
    Tool,
    ToolValidationError,
    api_key_tool_factory,
    oauth_tool_factory,
)
from charter.auth import StaticTokenProvider

BASE = "https://api.example.com/"


def _decode_b64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8")


class GetWeather(BaseModel):
    city: Annotated[str, Path()]
    units: Annotated[Optional[str], Query()] = "metric"


def _weather_tool(**overrides) -> Tool:
    kwargs = dict(
        name="get_current_weather",
        description="Get current weather for a city.",
        method="GET",
        url_template="data/2.5/weather/{city}",
        args_schema=GetWeather,
        base_url=BASE,
        api_key_headers={"x-api-key": "test-key"},
    )
    kwargs.update(overrides)
    return Tool(**kwargs)


# -----------------------------------------------------
# Construction
# -----------------------------------------------------


def test_tool_exposes_its_configuration():
    tool = _weather_tool(action_label="Check the weather")
    assert tool.name == "get_current_weather"
    assert tool.method == "GET"
    assert tool.action_label == "Check the weather"
    assert tool.base_url == BASE


def test_tool_requires_an_auth_method():
    with pytest.raises(ValueError, match="Must provide either"):
        Tool(
            name="t",
            method="GET",
            url_template="v1/{city}",
            args_schema=GetWeather,
            base_url=BASE,
        )


def test_repr_is_informative():
    assert "get_current_weather" in repr(_weather_tool())


def test_unit_cost_is_not_part_of_the_surface():
    """Dropped by the plan — a billing concept, not a boundary concept."""
    tool = _weather_tool()
    assert not hasattr(tool, "unit_cost")
    with pytest.raises(TypeError):
        _weather_tool(unit_cost=5)


# -----------------------------------------------------
# Schema views
# -----------------------------------------------------


class SendMessage(BaseModel):
    user_id: Annotated[str, Path()] = "me"
    raw: Annotated[EmailContent, Body(), Format("rfc822_base64")]
    thread_id: Annotated[Optional[str], Body(), Mode("response_only")] = None


def _gmail_tool(**overrides) -> Tool:
    kwargs = dict(
        name="messages_send",
        description="Send an email.",
        method="POST",
        url_template="gmail/v1/users/{user_id}/messages/send",
        args_schema=SendMessage,
        base_url=BASE,
        credential_provider=StaticTokenProvider("tok"),
        provider="google",
    )
    kwargs.update(overrides)
    return Tool(**kwargs)


def test_llm_schema_hides_response_only_fields():
    assert "thread_id" not in _gmail_tool().llm_schema().model_fields


def test_args_schema_keeps_the_full_wire_contract():
    assert "thread_id" in _gmail_tool().args_schema.model_fields


def test_llm_schema_is_built_once():
    tool = _gmail_tool()
    assert tool.llm_schema() is tool.llm_schema()


def test_to_json_schema_is_a_valid_openai_function_def():
    tool = _weather_tool()
    fn = tool.to_json_schema()

    assert set(fn) == {"name", "description", "parameters"}
    assert fn["name"] == "get_current_weather"
    assert fn["description"] == "Get current weather for a city."

    params = fn["parameters"]
    assert params["type"] == "object"
    assert "city" in params["properties"]
    assert "units" in params["properties"]
    # 'city' is required, 'units' has a default
    assert params["required"] == ["city"]


def test_to_json_schema_hands_out_a_copy():
    """The generated schema is cached, so what a caller gets must not be it.

    Adapters pass ``parameters`` straight out by reference, and tightening a
    returned schema — ``additionalProperties``, a trimmed ``required`` — is an
    ordinary thing to do with one.
    """
    tool = _weather_tool()
    first = tool.to_json_schema()
    first["name"] = "renamed"
    first["parameters"]["strict"] = True
    first["parameters"]["properties"].pop("city")
    first["parameters"]["properties"]["units"]["description"] = "rewritten"

    second = tool.to_json_schema()
    assert second["name"] == "get_current_weather"
    assert "strict" not in second["parameters"]
    assert "city" in second["parameters"]["properties"]
    assert second["parameters"]["properties"]["units"].get("description") != "rewritten"


def test_to_json_schema_exposes_the_semantic_type_not_the_wire_type():
    params = _gmail_tool().to_json_schema()["parameters"]
    assert "thread_id" not in params["properties"]
    # raw is an EmailContent object, not a base64 string
    raw = params["properties"]["raw"]
    ref = raw.get("$ref") or raw.get("allOf", [{}])[0].get("$ref", "")
    assert "EmailContent" in ref


# -----------------------------------------------------
# Invocation
# -----------------------------------------------------


@respx.mock
async def test_ainvoke_with_kwargs():
    route = respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={"temp": 21})
    )
    assert await _weather_tool().ainvoke(city="Tokyo") == {"temp": 21}
    assert dict(route.calls.last.request.url.params) == {"units": "metric"}


@respx.mock
async def test_ainvoke_with_a_positional_dict():
    respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={"temp": 21})
    )
    assert await _weather_tool().ainvoke({"city": "Tokyo", "units": "imperial"}) == {"temp": 21}


@respx.mock
async def test_ainvoke_merges_dict_and_kwargs():
    route = respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={})
    )
    await _weather_tool().ainvoke({"city": "Tokyo"}, units="imperial")
    assert dict(route.calls.last.request.url.params) == {"units": "imperial"}


@respx.mock
async def test_kwargs_win_over_the_positional_dict():
    route = respx.get(f"{BASE}data/2.5/weather/Kyoto").mock(
        return_value=httpx.Response(200, json={})
    )
    await _weather_tool().ainvoke({"city": "Tokyo"}, city="Kyoto")
    assert route.called


@respx.mock
def test_sync_invoke_wraps_ainvoke():
    respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={"temp": 21})
    )
    assert _weather_tool().invoke(city="Tokyo") == {"temp": 21}


async def test_sync_invoke_refuses_to_run_inside_a_loop():
    """asyncio.run() cannot nest — say so plainly rather than dying in asyncio."""
    with pytest.raises(RuntimeError, match=r"await tool\.ainvoke"):
        _weather_tool().invoke(city="Tokyo")


@respx.mock
async def test_the_flagship_path_email_to_base64url_raw():
    route = respx.post(f"{BASE}gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )

    result = await _gmail_tool().ainvoke(
        raw={"to": "ada@example.com", "subject": "Hi", "body": "Hello"}
    )

    assert result == {"id": "m1"}
    import json as _json

    # Two Body() fields means the body is a mapping, so the transformed `raw`
    # is keyed rather than becoming the body outright. That is also what Gmail
    # wants: {"raw": "<base64url>"}. Before the transform routing was made to
    # agree with `call_api`'s own single-body rule, this sent the bare string
    # and dropped `thread_id` with it.
    body = _json.loads(route.calls.last.request.content)
    msg = email.message_from_string(_decode_b64url(body["raw"]))
    assert msg["To"] == "ada@example.com"
    assert msg["Subject"] == "Hi"
    assert route.calls.last.request.headers["authorization"] == "Bearer tok"


# -----------------------------------------------------
# Errors
# -----------------------------------------------------


async def test_missing_required_argument_raises_tool_validation_error():
    with pytest.raises(ToolValidationError) as excinfo:
        await _weather_tool().ainvoke(units="metric")

    err = excinfo.value
    assert err.tool_name == "get_current_weather"
    assert "city" in str(err)
    assert "Validation error" in str(err)
    assert err.errors  # structured errors preserved for the host app


async def test_validation_message_names_the_offending_value():
    class Typed(BaseModel):
        count: Annotated[int, Query()]

    tool = _weather_tool(args_schema=Typed, url_template="v1/x")
    with pytest.raises(ToolValidationError) as excinfo:
        await tool.ainvoke(count="not a number")
    assert "count" in str(excinfo.value)


@respx.mock
async def test_api_error_propagates_from_ainvoke():
    respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(APIError, match="boom"):
        await _weather_tool().ainvoke(city="Tokyo")


@respx.mock
async def test_401_propagates_as_credential_error_from_ainvoke():
    respx.post(f"{BASE}gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Invalid Credentials"}})
    )
    with pytest.raises(CredentialError) as excinfo:
        await _gmail_tool().ainvoke(
            raw={"to": "a@b.com", "subject": "S", "body": "B"}
        )
    assert excinfo.value.provider == "google"


# -----------------------------------------------------
# api_key_tool_factory
# -----------------------------------------------------


def test_api_key_factory_returns_a_builder():
    factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "k"})
    assert callable(factory)

    tool = factory(
        name="t", args_schema=GetWeather, method="GET", url_template="v1/{city}"
    )
    assert isinstance(tool, Tool)
    assert tool.base_url == BASE
    assert tool.api_key_headers == {"x-api-key": "k"}


def test_api_key_factory_rejects_an_empty_header_value():
    with pytest.raises(ValueError, match="empty value"):
        api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": ""})


def test_api_key_factory_requires_headers_somewhere():
    factory = api_key_tool_factory(base_url=BASE)
    with pytest.raises(ValueError, match="must be provided"):
        factory(name="t", args_schema=GetWeather, method="GET", url_template="v1/{city}")


def test_api_key_factory_per_tool_header_override():
    factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "default"})
    tool = factory(
        name="t",
        args_schema=GetWeather,
        method="GET",
        url_template="v1/{city}",
        api_key_headers_override={"x-api-key": "special"},
    )
    assert tool.api_key_headers == {"x-api-key": "special"}


def test_factory_case_defaults_and_overrides():
    factory = api_key_tool_factory(
        base_url=BASE, api_key_headers={"x-api-key": "k"}, body_case="pascal"
    )
    default = factory(name="a", args_schema=GetWeather, method="GET", url_template="v1/{city}")
    overridden = factory(
        name="b",
        args_schema=GetWeather,
        method="GET",
        url_template="v1/{city}",
        body_case_override="kebab",
    )
    assert default.body_case == "pascal"
    assert overridden.body_case == "kebab"


def test_factory_keeps_action_label():
    factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "k"})
    tool = factory(
        name="t",
        args_schema=GetWeather,
        method="GET",
        url_template="v1/{city}",
        action_label="Check the weather",
    )
    assert tool.action_label == "Check the weather"


def test_factory_rejects_unit_cost():
    """Dropped from the surface — passing it should fail loudly, not silently."""
    factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "k"})
    with pytest.raises(TypeError):
        factory(
            name="t",
            args_schema=GetWeather,
            method="GET",
            url_template="v1/{city}",
            unit_cost=5,
        )


@respx.mock
async def test_factory_built_tool_executes():
    route = respx.get(f"{BASE}v1/Tokyo").mock(return_value=httpx.Response(200, json={"ok": 1}))
    factory = api_key_tool_factory(base_url=BASE, api_key_headers={"x-api-key": "k"})
    tool = factory(name="t", args_schema=GetWeather, method="GET", url_template="v1/{city}")

    assert await tool.ainvoke(city="Tokyo") == {"ok": 1}
    assert route.calls.last.request.headers["x-api-key"] == "k"


# -----------------------------------------------------
# oauth_tool_factory
# -----------------------------------------------------


def test_oauth_factory_builds_tools_carrying_provider_and_scopes():
    factory = oauth_tool_factory(
        base_url=BASE,
        provider="google",
        credential_provider=StaticTokenProvider("tok"),
        scopes=["https://www.googleapis.com/auth/gmail.modify"],
    )
    tool = factory(
        name="messages_send",
        args_schema=SendMessage,
        method="POST",
        url_template="gmail/v1/users/{user_id}/messages/send",
        action_label="Send an email",
    )

    assert tool.provider == "google"
    assert tool.scopes == ["https://www.googleapis.com/auth/gmail.modify"]
    assert tool.action_label == "Send an email"
    assert tool.api_key_headers is None


@respx.mock
async def test_oauth_factory_built_tool_sends_the_bearer_token():
    route = respx.post(f"{BASE}gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    factory = oauth_tool_factory(
        base_url=BASE, provider="google", credential_provider=StaticTokenProvider("tok")
    )
    tool = factory(
        name="messages_send",
        args_schema=SendMessage,
        method="POST",
        url_template="gmail/v1/users/{user_id}/messages/send",
    )

    await tool.ainvoke(raw={"to": "a@b.com", "subject": "S", "body": "B"})
    assert route.calls.last.request.headers["authorization"] == "Bearer tok"


async def test_oauth_factory_tools_share_the_credential_provider():
    """One provider, refreshed centrally, serves every tool built from it."""
    seen = []

    class Counting:
        async def get_credentials(self, provider):
            from charter.auth import Credentials

            seen.append(provider)
            return Credentials(token="tok")

    factory = oauth_tool_factory(
        base_url=BASE, provider="google", credential_provider=Counting()
    )
    a = factory(name="a", args_schema=GetWeather, method="GET", url_template="v1/{city}")
    b = factory(name="b", args_schema=GetWeather, method="GET", url_template="v2/{city}")

    with respx.mock:
        respx.get(f"{BASE}v1/Tokyo").mock(return_value=httpx.Response(200, json={}))
        respx.get(f"{BASE}v2/Tokyo").mock(return_value=httpx.Response(200, json={}))
        await a.ainvoke(city="Tokyo")
        await b.ainvoke(city="Tokyo")

    assert seen == ["google", "google"]


# -----------------------------------------------------
# API-key headers resolved at request time
# -----------------------------------------------------


@respx.mock
async def test_api_key_headers_may_be_a_callable_resolved_per_request():
    """Lets a credential arrive after the tools are built — and makes the check
    the runtime's job rather than something a tool author must remember."""
    calls = []

    def resolve():
        calls.append(1)
        return {"x-api-key": f"key-{len(calls)}"}

    route = respx.get(f"{BASE}data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={})
    )
    tool = _weather_tool(api_key_headers=resolve)

    await tool.ainvoke(city="Tokyo")
    await tool.ainvoke(city="Tokyo")

    assert len(calls) == 2  # resolved per call, not cached at construction
    assert route.calls[-1].request.headers["x-api-key"] == "key-2"


@respx.mock
async def test_a_resolver_raising_prevents_the_request():
    def resolve():
        raise CredentialError("not configured yet")

    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="not configured"):
            await _weather_tool(api_key_headers=resolve).ainvoke(city="Tokyo")
        assert not route.called


@respx.mock
async def test_empty_resolved_headers_raise_before_sending():
    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="No API key headers"):
            await _weather_tool(api_key_headers=dict).ainvoke(city="Tokyo")
        assert not route.called


@respx.mock
async def test_a_header_resolving_to_an_empty_value_raises():
    with respx.mock:
        route = respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CredentialError, match="x-api-key"):
            await _weather_tool(api_key_headers=lambda: {"x-api-key": ""}).ainvoke(city="Tokyo")
        assert not route.called


def test_a_callable_satisfies_the_auth_requirement_at_construction():
    """It cannot be inspected up front, so it counts as configured auth."""
    assert _weather_tool(api_key_headers=lambda: {"x-api-key": "k"}) is not None


def test_an_empty_dict_still_fails_construction():
    with pytest.raises(ValueError, match="Must provide either"):
        _weather_tool(api_key_headers={})


def test_factory_accepts_a_resolver_and_skips_build_time_validation():
    factory = api_key_tool_factory(base_url=BASE, api_key_headers=lambda: {"x-api-key": "k"})
    tool = factory(name="t", args_schema=GetWeather, method="GET", url_template="v1/{city}")
    assert callable(tool.api_key_headers)


def test_a_factory_builds_a_shared_type_once_for_every_tool_it_makes():
    """Tools from one factory reach the same types, and used to rebuild each one.

    Linear's 128 tools reference the same filter graph, so constructing the pack
    called `create_llm_schema` 16,149 times and spent 28 seconds of import doing
    it - the factory now owns one cache, and a type no prune reaches is generated
    once. Identity is the assertion, because equal shape would pass while every
    tool still paid to build its own copy.
    """
    from pydantic import Field

    from charter.factories import api_key_tool_factory

    class Shared(BaseModel):
        label: str = Field(description="A label.")

    class First(BaseModel):
        item: Shared = Field(description="The shared type.")

    class Second(BaseModel):
        other: Shared = Field(description="The same shared type, elsewhere.")

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    one = factory("one", First, "GET", "one", description="One.")
    two = factory("two", Second, "GET", "two", description="Two.")

    generated_one = one._llm_schema.model_fields["item"].annotation
    generated_two = two._llm_schema.model_fields["other"].annotation
    assert generated_one is generated_two, "the shared type was generated twice"

    # A second factory is a second store: nothing accumulates across packs.
    elsewhere = api_key_tool_factory(
        "https://api.other.com", {"X-Key": "{api_key}"}, pack="other"
    )
    three = elsewhere("three", First, "GET", "three", description="Three.")
    assert three._llm_schema.model_fields["item"].annotation is not generated_one


def test_a_view_is_not_built_until_something_asks_for_it():
    """Constructing a tool costs nothing beyond what can fail.

    Importing the Linear pack built 128 views eagerly and spent most of its
    import doing it, for tools a session never exposes. What must stay eager is
    everything that can raise: `derived()` resolves its paths before a Tool
    exists, and a pinned tool still builds its exec view at construction so a bad
    pin is still a construction-time error.
    """
    from pydantic import Field

    from charter.factories import api_key_tool_factory

    class Args(BaseModel):
        label: str = Field(description="A label.")

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "t", description="T.")

    assert tool._llm_schema_built is None, "the view was built at construction"
    assert tool.llm_schema() is not None
    assert tool._llm_schema_built is not None, "the view was not memoised"

    # The second call hands back the same object, not an equal one.
    assert tool.llm_schema() is tool._llm_schema_built


def test_a_keep_path_that_names_nothing_still_fails_at_declaration():
    """The error that laziness must not defer.

    A projection is checked when it is declared, not when a model first asks for
    the tool — otherwise a typo in a pack ships and surfaces in someone's agent
    run instead of in the pack author's test suite.
    """
    from pydantic import Field

    from charter.factories import api_key_tool_factory
    from charter.types.errors import DeclarationError

    class Inner(BaseModel):
        label: str = Field(description="A label.")

    class Args(BaseModel):
        item: Inner = Field(description="The item.")

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "t", description="T.")

    with pytest.raises(DeclarationError, match="is not a field of"):
        tool.derived(name="bad", keep={"item.nope"})


# -----------------------------------------------------
# The view is derived lazily, from a store several tools share
# -----------------------------------------------------
#
# Both halves of 4620cacc are only safe under an invariant the commit did not
# state: nothing leaves a caller-owned store until it can validate. Deriving on
# first use moved the build from import - one thread, holding the import lock -
# onto whichever caller gets there first, and a `Tool` is a process-wide object
# that several of them reach at once.


def _recursive_pack_shapes():
    """A filter graph shaped like Linear's: mutually recursive, widely shared."""
    from typing import List

    from pydantic import Field

    class Filter(BaseModel):
        name: Optional[str] = Field(None, description="Match on name.")
        # Mutually recursive through Group, so the cycle closes outside any one
        # model's own build - which is the shape that needs `_rebuild_generated`
        # and therefore the shape that is unusable until the walk finishes.
        any_of: Optional[List[Group]] = Field(None, description="Any of these.")

    class Group(BaseModel):
        members: Optional[List[Filter]] = Field(None, description="Members.")
        nested: Optional[Group] = Field(None, description="Nested group.")

    Filter.model_rebuild()
    Group.model_rebuild()

    class Args(BaseModel):
        term: str = Field(..., description="The search term.")
        filter: Optional[Filter] = Field(None, description="Narrow the search.")

    return Args, Filter


def test_a_store_never_holds_a_view_that_cannot_validate():
    """Nothing is published until the walk has resolved its forward references.

    A generated model with an unresolved ref raises `not fully defined` on every
    validation, and most of a recursive graph is in that state for most of the
    walk. Publishing each model as it was built put those in a store the caller
    keeps, where anyone reading it - another thread, or a later call after this
    one raised - took one for finished.
    """
    from charter.execution.schema import create_llm_schema

    Args, _ = _recursive_pack_shapes()

    class Probe(dict):
        def __init__(self) -> None:
            super().__init__()
            self.published_incomplete: list = []

        def __setitem__(self, key, value):  # pragma: no cover - dict.update path
            self._check(value)
            super().__setitem__(key, value)

        def update(self, other=(), **kw):
            for value in dict(other, **kw).values():
                self._check(value)
            super().update(other, **kw)

        def _check(self, value):
            _source, model = value
            if not getattr(model, "__pydantic_complete__", True):
                self.published_incomplete.append(model.__name__)

    store = Probe()
    create_llm_schema(Args, cache=store)

    assert store, "nothing was shared at all, so the store is not being used"
    assert store.published_incomplete == [], (
        "a model was published before its forward references resolved"
    )
    assert all(
        model.__pydantic_complete__ for _source, model in store.values()
    ), "the store holds a model that cannot validate"


def test_a_walk_that_raises_leaves_the_store_as_it_found_it():
    """The store is one commit, not a trail of partial work.

    A store outlives the call that filled it. Publishing during the walk meant a
    failure part way through left every model built so far behind - complete or
    not - for the next tool off the same factory to pick up, with nothing to say
    they came from a call that never finished.
    """
    from pydantic import Field

    from charter.execution.schema import create_llm_schema
    from charter.transforms import registry

    class Boom(Exception):
        pass

    class Inner(BaseModel):
        label: str = Field(..., description="A label.")

    class Args(BaseModel):
        # Walked first, so it is built and would have been published before the
        # field below fails. Without that ordering the test proves nothing.
        item: Inner = Field(..., description="The item.")
        payload: Annotated[str, Field(..., description="Encoded."), Format("base64")]

    def explode(_name):
        raise Boom("the walk failed")

    store: dict = {}
    original = registry.TransformRegistry.get
    registry.TransformRegistry.get = staticmethod(explode)  # type: ignore[assignment]
    try:
        with pytest.raises(Boom):
            create_llm_schema(Args, cache=store)
    finally:
        registry.TransformRegistry.get = original  # type: ignore[assignment]

    assert store == {}, (
        f"a failed walk left {len(store)} model(s) in the caller's store"
    )

    # The proof that the ordering above holds: the same walk, allowed to finish,
    # does publish `Inner`.
    finished: dict = {}
    create_llm_schema(Args, cache=finished)
    assert finished, "the walk publishes nothing at all, so the check above is vacuous"


def test_a_thread_reading_the_store_mid_build_never_sees_a_broken_view():
    """The build moved off the import thread, so it has to be safe on any other.

    `Tool.invoke` is synchronous, so a WSGI worker pool, a sync LangChain agent
    on an executor and `to_openai_tools` inside the turn loop all reach a cold
    tool from several threads at once, and they reach it through one store. A
    reader is asserted against directly rather than through a second builder,
    because the damage is not the race being lost - it is what the loser then
    keeps. It memoises whatever the store handed it, so a model read mid-walk
    becomes that tool's view for the life of the process: a schema it advertises
    to the model and rejects every call against with `not fully defined`.
    """
    import threading

    from charter.execution.validation import validate_input
    from charter.factories import api_key_tool_factory

    Args, _ = _recursive_pack_shapes()

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "t", description="T.")
    store = tool._llm_cache
    assert store is not None and store == {}, "the tool built its view eagerly"

    seen_broken: list = []
    seen_any = threading.Event()
    stop = threading.Event()

    def watch() -> None:
        while not stop.is_set():
            for _source, model in list(store.values()):
                seen_any.set()
                if not getattr(model, "__pydantic_complete__", True):
                    seen_broken.append(model.__name__)

    reader = threading.Thread(target=watch, daemon=True)
    reader.start()
    try:
        view = tool._llm_schema
        # The reader is left running until it has actually read the filled
        # store. Stopping it the instant the build returns would let it finish
        # having seen nothing, and "saw nothing broken" would then be true of a
        # thread that never looked.
        seen_any.wait(timeout=5)
    finally:
        stop.set()
        reader.join(timeout=5)

    assert seen_any.is_set(), "the reader never saw the store fill, so it proves nothing"
    assert seen_broken == [], (
        f"a reader saw {len(seen_broken)} model(s) that cannot validate: "
        f"{sorted(set(seen_broken))[:5]}"
    )
    assert view.__pydantic_complete__
    validate_input(view, {"term": "x"}, tool_name=tool.name)


def test_two_threads_first_touching_one_tool_agree_on_its_view():
    """One view, however many callers arrive together.

    Two threads that both build hand out two different classes for the same
    tool, and the second overwrites the first after callers are already holding
    it - so a `parameters` block generated from one and an argument validated
    against the other come from different objects, and the tool's own
    `_json_schema` describes a class it no longer uses.

    The store is instrumented to hold the first walk open until the second
    caller has arrived, because the window is otherwise too narrow to land on
    and a test that cannot lose the race is not testing for it.
    """
    import threading
    import time

    Args, _ = _recursive_pack_shapes()

    class SlowStore(dict):
        """A store that stalls the first walk to read it."""

        def __init__(self) -> None:
            super().__init__()
            self.entered = threading.Event()
            self._stalled = False

        def __contains__(self, key: object) -> bool:
            # The answer is taken before the stall, not after. Read afterwards,
            # the stalled walk would see the *other* thread's finished work and
            # adopt it - which is luck, not a guarantee, and would leave this
            # test unable to fail.
            present = super().__contains__(key)
            if not self._stalled:
                self._stalled = True
                self.entered.set()
                time.sleep(0.2)
            return present

    store = SlowStore()
    tool = Tool(
        name="t",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        pack="example",
        api_key_headers={"X-Key": "k"},
        llm_cache=store,
    )

    views: list = []
    first = threading.Thread(target=lambda: views.append(tool._llm_schema))
    first.start()
    assert store.entered.wait(timeout=5), "the first walk never reached the store"
    second = threading.Thread(target=lambda: views.append(tool._llm_schema))
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert len(views) == 2
    assert views[0] is views[1], "the tool built and handed out two views"
    assert tool.to_json_schema()["parameters"] is not None


def test_a_projection_shares_the_store_of_the_tool_it_narrows():
    """`derived` is the deployer's lever, and it was the one path with no store.

    Only subtrees no prune path reaches are ever shared, which is exactly the set
    an added prune cannot change - the same condition `path_costs` relies on to
    price a level against one store. Without this, every projection rebuilt the
    whole graph alone: eight projections of a Linear list tool cost 12s of first
    use rather than 2s, and the pack's own curated list tools are projections.
    """
    from charter.factories import api_key_tool_factory

    Args, _ = _recursive_pack_shapes()

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "t", description="T.")
    narrowed = tool.derived(name="narrowed", drop={"filter.name"})

    assert narrowed._llm_cache is tool._llm_cache is not None

    # Shared means shared by identity: the subtree the extra prune cannot reach
    # is the same class object, not an equal one.
    parent_group = tool._llm_schema.model_fields["filter"].annotation
    child_group = narrowed._llm_schema.model_fields["filter"].annotation
    assert parent_group is not child_group, "the pruned model was reused"
    assert narrowed._llm_schema.__pydantic_complete__


def test_a_projection_carries_every_argument_the_constructor_takes():
    """The mechanical guard on the bug that let `llm_cache` go missing.

    `derived` rebuilds a `Tool` by listing its arguments, so a parameter added to
    `__init__` and forgotten here is silently dropped from every projection. That
    is how projections lost the factory's schema store: nothing failed, they just
    paid for the graph again. A test that reads the signature notices the next
    one.
    """
    import inspect

    constructor = set(inspect.signature(Tool.__init__).parameters) - {"self"}
    source = inspect.getsource(Tool.derived)
    passed = {name for name in constructor if f"{name}=" in source}

    missing = constructor - passed
    assert not missing, f"derived() does not carry: {sorted(missing)}"


def test_a_tool_can_still_be_copied():
    """A lock is not state, and holding one must not make a tool uncopyable.

    `copy.deepcopy(tool)` worked before the view was derived on first use, and a
    `threading.RLock` cannot be copied or pickled - so guarding the build with
    one would have turned a working call into `cannot pickle '_thread.RLock'
    object` for anyone fanning tools out across processes.
    """
    import copy as _copy

    from charter.factories import api_key_tool_factory

    Args, _ = _recursive_pack_shapes()

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "t", description="T.")

    clone = _copy.deepcopy(tool)
    assert clone.name == tool.name
    # The copy guards its own build rather than sharing the original's lock.
    assert clone._schema_lock is not tool._schema_lock
    assert clone._llm_schema.__pydantic_complete__


def test_every_recursive_walk_carries_the_whole_walk_state():
    """The guard on how `_pending` was dropped from one branch out of four.

    The walk recurses from four places - a nested model, a list item, a
    forward-referenced list item, and a model reached as a dict *value* - and
    each has to hand the whole walk down. An internal argument missing from one
    of them fails silently: the subtree below it simply stops being cached, and
    nothing about the schema it produces is wrong. `_pending` went missing from
    the dict branch exactly that way, and took a quarter of Notion's type graph
    out of the store with it - the branch Notion's page `properties` is.

    Read off the source rather than asserted per branch, so a fifth call site is
    covered the day it is written.
    """
    import ast
    import inspect
    import textwrap

    from charter.execution import schema as schema_module

    tree = ast.parse(textwrap.dedent(inspect.getsource(schema_module._create_llm_schema)))
    walk_state = {"prune", "cache", "_seen_types", "_root_mode", "_path", "_pending"}

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_create_llm_schema"
    ]
    assert len(calls) >= 4, f"expected the four recursive calls, found {len(calls)}"

    for call in calls:
        passed = {kw.arg for kw in call.keywords if kw.arg is not None}
        missing = walk_state - passed
        assert not missing, (
            f"the recursive call on line {call.lineno} of create_llm_schema "
            f"does not pass {sorted(missing)}"
        )


def test_a_bad_pin_still_fails_where_it_is_declared():
    """The other error laziness must not defer, and the one nothing covered.

    Deriving the view on first use is only safe because everything that can fail
    stays eager, and a pinned tool is half of that argument: `_check_pin_values`
    runs against the *exec* view, so the view has to be built at construction
    rather than when a model first reaches for the tool. That was asserted in the
    commit message and by no test - `_check_pin_values` had no coverage at all,
    so making the exec view lazy too would have gone green.
    """
    from pydantic import Field

    from charter.factories import api_key_tool_factory
    from charter.types.errors import DeclarationError

    class Args(BaseModel):
        q: Annotated[Optional[str], Field(None, description="Search."), Query()]
        limit: Annotated[Optional[int], Field(None, description="How many."), Query()]

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    tool = factory("t", Args, "GET", "search", description="T.")

    with pytest.raises(DeclarationError, match="does not satisfy that field"):
        tool.derived(name="bad", pin={"limit": "not-an-int"})

    # A good pin builds, and only the exec view is eager: the model-facing one
    # is still deferred, which is the half the performance work depends on.
    pinned = tool.derived(name="ok", pin={"limit": 5})
    assert pinned._exec_schema_built is not None, "the exec view was not built eagerly"
    assert pinned._llm_schema_built is None, "the model-facing view was built eagerly"


def test_a_type_reached_as_a_dict_value_is_shared_like_any_other():
    """The branch that lost its walk state, asserted on behaviour as well.

    A model reached as a `Dict[str, Model]` *value* is walked like any other -
    Notion's page `properties` is that shape, a map of column name to value - and
    it has to reach the store by the same route. The AST guard above catches the
    argument going missing; this catches the sharing stopping for any other
    reason.
    """
    from typing import Dict as TypingDict

    from pydantic import Field

    from charter.factories import api_key_tool_factory

    class Value(BaseModel):
        kind: str = Field(..., description="The value's type.")

    class First(BaseModel):
        properties: TypingDict[str, Value] = Field(..., description="Columns.")

    class Second(BaseModel):
        other: TypingDict[str, Value] = Field(..., description="The same map.")

    factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    one = factory("one", First, "GET", "one", description="One.")
    two = factory("two", Second, "GET", "two", description="Two.")

    def value_model(view, field):
        import typing

        return typing.get_args(view.model_fields[field].annotation)[1]

    shared = value_model(one._llm_schema, "properties")
    assert shared is value_model(two._llm_schema, "other"), (
        "a type reached as a dict value was generated twice"
    )


# -----------------------------------------------------
# One store, several threads
# -----------------------------------------------------
#
# Holding models back until they can validate stops a reader seeing a half-built
# one. It does not stop two walks of the same graph running at once, and that is
# a second failure with the same cause: each builds its own copy of a shared
# subtree, then reads the other's, and the graph that comes out is spliced
# together from two generations of the same models.


def test_two_walks_sharing_a_store_do_not_splice_two_graphs_together():
    """One type is one class in one view, however many walks share the store.

    The hazard the publish-at-end fix does not cover. Two walks each build their
    own copy of a shared subtree; the one that finishes second adopts, for a
    branch it has not reached yet, a model the first published — and that model
    references the *first* walk's copies of children the second already built.
    The view that comes out is spliced from two generations of one graph.

    Asserted as identity, because identity is the guarantee: ``_seen_types``
    exists to make a type reached twice in one view one class, and a store shared
    across threads is the one way around it. What it costs depends on how far the
    two generations have diverged — where they are identical pydantic quietly
    folds them back into one ``$defs`` entry, and where they are not it emits
    both. On ``linear.custom_view_create`` it emitted both: 80 definitions became
    136 and a 193KB schema became 382KB, on a pack whose tools Fireworks already
    refuses past a depth of 50, where one refusal takes every other tool in the
    request with it.

    The interleaving is arranged rather than waited for. ``Args.left`` and
    ``Args.right`` both reach ``Shared``, ``left`` is walked first, and the slow
    walk is stopped between them — so it has built its own ``Shared`` and has not
    yet seen ``Wrapper``, which is exactly the window.
    """
    import threading

    from pydantic import Field

    from charter.execution import schema as schema_module
    from charter.execution.schema import SchemaStore, create_llm_schema

    class Shared(BaseModel):
        label: str = Field(..., description="A label.")

    class Wrapper(BaseModel):
        shared: Optional[Shared] = Field(None, description="The shared type.")

    class Args(BaseModel):
        left: Optional[Shared] = Field(None, description="Reached first.")
        right: Optional[Wrapper] = Field(None, description="Reached second.")

    class StallingStore(SchemaStore):
        """Stops one nominated walk on its way into ``Wrapper``."""

        def __init__(self) -> None:
            super().__init__()
            self.at_wrapper = threading.Event()
            self.may_continue = threading.Event()
            self.slow: Optional[threading.Thread] = None
            self._stalled = False

        def __contains__(self, key: object) -> bool:
            if (
                not self._stalled
                and isinstance(key, tuple)
                and key[0] == id(Wrapper)
                and threading.current_thread() is self.slow
            ):
                self._stalled = True
                self.at_wrapper.set()
                self.may_continue.wait(timeout=10)
            return super().__contains__(key)

    store = StallingStore()
    built: dict = {}

    slow = threading.Thread(target=lambda: built.__setitem__("slow", create_llm_schema(Args, cache=store)))
    store.slow = slow
    slow.start()
    assert store.at_wrapper.wait(timeout=10), "the slow walk never reached Wrapper"

    fast = threading.Thread(target=lambda: built.__setitem__("fast", create_llm_schema(Args, cache=store)))
    fast.start()
    # Long enough for the second walk to finish and publish if nothing stops it,
    # and harmless if something does: the guard makes it wait here instead.
    fast.join(timeout=1.0)
    store.may_continue.set()
    slow.join(timeout=20)
    fast.join(timeout=20)

    assert store._stalled, "the stall never fired, so nothing was interleaved"
    assert set(built) == {"slow", "fast"}

    def model_of(annotation):
        from typing import get_args

        rest = [a for a in get_args(annotation) if a is not type(None)]
        return rest[0] if rest else annotation

    for which, view in built.items():
        assert view.__pydantic_complete__
        direct = model_of(view.model_fields["left"].annotation)
        through = model_of(
            model_of(view.model_fields["right"].annotation).model_fields["shared"].annotation
        )
        assert direct is through, (
            f"the {which} view reaches one source type through two generated "
            f"classes ({direct} and {through}): two walks were spliced together"
        )

    del schema_module


def test_a_store_two_threads_share_is_guarded_and_a_plain_dict_still_works():
    """The lock lives on the store, because the store is what is shared.

    A per-tool guard is not enough and never was: one store is read by every tool
    in a pack, so two threads building two *different* tools interleave inside
    the same type graph. ``SchemaStore`` carries the lock; a plain dict is still
    accepted — it is a documented, caller-owned argument — and falls back to one
    process-wide lock rather than to no guard at all.
    """
    import threading

    from pydantic import Field

    from charter.execution.schema import SchemaStore, _store_guard, create_llm_schema

    Args, _ = _recursive_pack_shapes()

    store = SchemaStore()
    assert _store_guard(store) is store.lock
    assert _store_guard({}) is _store_guard({}), "a plain dict has no guard of its own"
    assert _store_guard(None) is not store.lock

    # Two stores are two locks, so unrelated packs do not queue behind each other.
    assert SchemaStore().lock is not SchemaStore().lock

    # A plain dict is still a working cache.
    plain: dict = {}
    view = create_llm_schema(Args, cache=plain)
    assert view.__pydantic_complete__ and plain

    # And the guard is reentrant, because a nested build reaches it on the same
    # thread through `Tool._exec_schema` -> `_llm_schema`.
    with store.lock:
        with store.lock:
            assert create_llm_schema(Args, cache=store).__pydantic_complete__

    # Held for the *duration* of a root walk, not around each read and write.
    # Asserted from another thread, because that is the only place the
    # difference is visible: a lock taken and released per access is free the
    # instant it is asked for.
    held: list = []
    fresh = SchemaStore()

    class Watched(BaseModel):
        term: str = Field(..., description="Watched.")

    def probe() -> None:
        held.append(fresh.lock.acquire(blocking=False))
        if held[-1]:
            fresh.lock.release()

    # Inside the walk: a `__contains__` on the store is reached once the root's
    # cache key is looked up, and that is already inside the guard.
    class Probing(SchemaStore):
        def __contains__(self, key: object) -> bool:
            watcher = threading.Thread(target=probe)
            watcher.start()
            watcher.join(timeout=5)
            return super().__contains__(key)

    fresh = Probing()
    create_llm_schema(Watched, cache=fresh)
    assert held and not any(held), (
        "another thread could take the store's lock while a root walk was "
        "running: the guard is not held across the walk"
    )


def test_a_factory_hands_its_tools_a_guarded_store():
    """The packs' own stores are the ones with threads on them."""
    from charter.auth import StaticTokenProvider
    from charter.execution.schema import SchemaStore
    from charter.factories import api_key_tool_factory, oauth_tool_factory

    Args, _ = _recursive_pack_shapes()

    key_factory = api_key_tool_factory(
        "https://api.example.com", {"X-Key": "{api_key}"}, pack="example"
    )
    oauth_factory = oauth_tool_factory(
        "https://api.example.com",
        "example",
        StaticTokenProvider("t"),
        pack="example",
    )
    one = key_factory("one", Args, "GET", "one", description="One.")
    two = oauth_factory("two", Args, "GET", "two", description="Two.")

    assert isinstance(one._llm_cache, SchemaStore)
    assert isinstance(two._llm_cache, SchemaStore)
    assert one._llm_cache is not two._llm_cache, "two factories share one store"


def test_a_tool_with_no_store_still_builds_its_view_once():
    """Where the per-tool guard is the only guard there is.

    A ``Tool`` built outside a factory has no ``llm_cache``, so nothing below it
    coordinates anything: two threads that first-touch it together each run a
    whole build and each publish the result, and the second overwrites the view
    the first already handed out. A ``parameters`` block generated from one and
    an argument validated against the other are then two different classes, and
    the tool's own ``_json_schema`` describes one it no longer uses.

    The store hides this when there is one — the second walk finds the root in it
    and gets the first walk's class back — which is why it is asserted here,
    where there is not.
    """
    import threading
    import time

    from pydantic import Field

    import charter.tool as tool_module

    class Args(BaseModel):
        term: Annotated[str, Field(..., description="The search term."), Query()]

    tool = Tool(
        name="unstored",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        api_key_headers={"X-Key": "k"},
    )
    assert tool._llm_cache is None, "this tool is supposed to have no store"

    real = tool_module.create_llm_schema
    entered = threading.Event()

    def slow_build(*args, **kwargs):
        # Wide enough for the second caller to arrive mid-build, which is the
        # window. Without it the race is real and essentially never lost.
        entered.set()
        time.sleep(0.2)
        return real(*args, **kwargs)

    tool_module.create_llm_schema = slow_build
    try:
        views: list = []
        first = threading.Thread(target=lambda: views.append(tool._llm_schema))
        first.start()
        assert entered.wait(timeout=5), "the first build never started"
        second = threading.Thread(target=lambda: views.append(tool._llm_schema))
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)
    finally:
        tool_module.create_llm_schema = real

    assert len(views) == 2
    assert views[0] is views[1], "the tool built and handed out two different views"
    assert tool._llm_schema is views[0], "the memo is not the view that was handed out"


# -----------------------------------------------------
# What deriving on first use costs the first caller
# -----------------------------------------------------
#
# The build did not get cheaper, it moved — out of import and into whichever call
# arrives first. Two things follow that are not about correctness of the schema:
# the call that pays must not be charged for it in the wrong place, and it must
# not pay on the event loop's thread.


def _slow_schema(monkeypatch, seconds: float = 0.2):
    """Make the view take measurable time to derive, and say when it starts."""
    import threading
    import time

    import charter.tool as tool_module

    real = tool_module.create_llm_schema
    started = threading.Event()

    def slow(*args, **kwargs):
        started.set()
        time.sleep(seconds)
        return real(*args, **kwargs)

    monkeypatch.setattr(tool_module, "create_llm_schema", slow)
    return started


def test_the_first_call_does_not_charge_the_build_to_validation(monkeypatch):
    """``validate_ms`` means validating this call, and nothing else.

    The build ran inside the validation timer, so the first call against a Linear
    list tool reported 1.86 *seconds* of input validation. That is the number a
    host watches to find out whether the model is sending malformed arguments,
    and a one-off schema build sitting in its p99 makes it useless for that. It
    has its own field now, zero on every call but the first.
    """
    import asyncio

    from pydantic import Field

    calls: list = []

    class Args(BaseModel):
        term: Annotated[str, Field(..., description="The search term."), Query()]

    tool = Tool(
        name="t",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        api_key_headers={"X-Key": "k"},
        on_call=calls.append,
    )

    _slow_schema(monkeypatch, 0.25)

    with respx.mock(base_url=BASE) as mock:
        mock.get("t").mock(return_value=httpx.Response(200, json={"ok": True}))
        asyncio.run(tool.ainvoke({"term": "x"}))
        asyncio.run(tool.ainvoke({"term": "y"}))

    first, second = calls
    assert first.schema_ms > 200, f"the build was not measured: {first.schema_ms}ms"
    assert first.validate_ms < 100, (
        f"the build is still being charged to validation: {first.validate_ms}ms"
    )
    assert second.schema_ms == 0, "a warm call reported a schema build"
    assert first.to_dict()["charter.duration.schema_ms"] == round(first.schema_ms, 3)

    # And the log line says so, because otherwise it reports a slow call and
    # leaves the API holding the blame.
    from charter.observability import format_call_line

    assert "first-use schema build" in format_call_line(first)
    assert "first-use schema build" not in format_call_line(second)


def test_the_first_call_does_not_block_the_event_loop(monkeypatch):
    """A build on the loop's thread stops every other call in the process.

    ``ainvoke`` is a coroutine and the build is seconds of pure Python, so
    deriving it inline froze the loop for all of it — on a cold Linear tool, 2.4
    seconds during which nothing else ran, including requests already in flight.
    Measured as the worst gap between ticks of a task that is supposed to run
    every 5ms.
    """
    import asyncio

    from pydantic import Field

    class Args(BaseModel):
        term: Annotated[str, Field(..., description="The search term."), Query()]

    tool = Tool(
        name="t",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        api_key_headers={"X-Key": "k"},
    )

    _slow_schema(monkeypatch, 0.5)

    async def main() -> float:
        worst = 0.0
        stop = asyncio.Event()

        async def ticker() -> None:
            nonlocal worst
            from time import perf_counter

            last = perf_counter()
            while not stop.is_set():
                await asyncio.sleep(0.005)
                now = perf_counter()
                worst = max(worst, now - last)
                last = now

        beat = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)
        with respx.mock(base_url=BASE) as mock:
            mock.get("t").mock(return_value=httpx.Response(200, json={"ok": True}))
            await tool.ainvoke({"term": "x"})
        stop.set()
        await beat
        return worst

    worst = asyncio.run(main())
    assert worst < 0.3, (
        f"the event loop was blocked for {worst * 1000:.0f}ms while the view was "
        f"derived; the build belongs off the loop's thread"
    )


def test_prepare_pays_the_build_up_front_and_is_idempotent():
    """The way a host stops paying for it inside a request at all."""
    import asyncio

    from pydantic import Field

    calls: list = []

    class Args(BaseModel):
        term: Annotated[str, Field(..., description="The search term."), Query()]
        limit: Annotated[Optional[int], Field(None, description="How many."), Query()]

    tool = Tool(
        name="t",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        api_key_headers={"X-Key": "k"},
        on_call=calls.append,
    )
    assert tool._llm_schema_built is None and tool._json_schema is None

    assert tool.prepare() is tool, "prepare() does not return the tool"
    assert tool._llm_schema_built is not None, "prepare() left the view underived"
    assert tool._json_schema is not None, "prepare() left the JSON schema ungenerated"

    view = tool._llm_schema_built
    tool.prepare()
    assert tool._llm_schema_built is view, "prepare() rebuilt an already-built view"

    with respx.mock(base_url=BASE) as mock:
        mock.get("t").mock(return_value=httpx.Response(200, json={"ok": True}))
        asyncio.run(tool.ainvoke({"term": "x"}))

    assert calls[0].schema_ms == 0, (
        "a prepared tool still charged a schema build to its first call"
    )


def test_prepare_builds_the_executed_view_of_a_pinned_tool():
    """A pinned tool has two views, and a call needs both."""
    from pydantic import Field

    class Args(BaseModel):
        q: Annotated[Optional[str], Field(None, description="Search."), Query()]
        limit: Annotated[Optional[int], Field(None, description="How many."), Query()]

    tool = Tool(
        name="t",
        method="GET",
        url_template="t",
        args_schema=Args,
        base_url=BASE,
        description="T.",
        api_key_headers={"X-Key": "k"},
    )
    pinned = tool.derived(name="p", pin={"limit": 5})
    # The exec view is eager, because `_check_pin_values` runs against it.
    assert pinned._exec_schema_built is not None
    assert pinned._llm_schema_built is None
    assert not pinned._views_ready

    pinned.prepare()
    assert pinned._views_ready
    assert "limit" not in pinned._llm_schema.model_fields
    assert "limit" in pinned._exec_schema.model_fields


def test_a_schema_that_cannot_resolve_its_own_names_fails_at_declaration():
    """"Nothing is deferred that can fail" has to be true, not nearly true.

    Deriving on first use was argued safe on the grounds that everything which
    can fail stays eager, and two things were kept eager for it: ``derived()``
    resolves its selectors before a ``Tool`` exists, and a pinned tool builds its
    exec view at construction. What neither covers is the walk itself. A schema
    whose annotations do not resolve declared a tool without complaint and raised
    a bare ``PydanticUndefinedAnnotation`` out of the first agent run that
    touched it — which is the shape that once left 17 Linear tools unable to emit
    a schema at all, and the packs are only covered against it because the
    conformance suite touches every tool. A pack someone else writes is not.
    """
    from typing import List

    from pydantic import Field

    from charter.types.errors import DeclarationError

    class Leaf(BaseModel):
        # Names a class that is not there: pydantic leaves the model incomplete
        # rather than raising, and it stays usable enough to declare a tool with.
        kids: Optional[List[Missing]] = Field(None, description="Children.")  # noqa: F821

    class Args(BaseModel):
        leaf: Annotated[Optional[Leaf], Field(None, description="A leaf."), Body()]

    assert not Leaf.__pydantic_complete__, "pydantic resolved it after all"

    with pytest.raises(DeclarationError, match="cannot resolve its own annotations"):
        Tool(
            name="broken",
            method="POST",
            url_template="t",
            args_schema=Args,
            base_url=BASE,
            description="T.",
            api_key_headers={"X-Key": "k"},
        )


def test_the_resolvability_check_does_not_refuse_a_working_schema():
    """Including the two shapes it would be easiest to refuse by accident.

    A self-referential model is complete and must build, and a model reached only
    as a ``Dict`` value or a list item has to be reached by the walk at all —
    a check that cannot see it would pass every schema and mean nothing.
    """
    from typing import Dict as TypingDict
    from typing import List

    from pydantic import Field

    from charter.tool import _check_schema_resolvable, _models_in

    class Node(BaseModel):
        name: str = Field(..., description="The name.")
        children: Optional[List[Node]] = Field(None, description="Children.")

    Node.model_rebuild()

    class Cell(BaseModel):
        value: str = Field(..., description="The value.")

    class Args(BaseModel):
        tree: Annotated[Optional[Node], Field(None, description="A tree."), Body()]
        cells: Annotated[
            Optional[TypingDict[str, Cell]], Field(None, description="Cells."), Body()
        ]

    _check_schema_resolvable(Args, "ok")  # does not raise

    # The walk reaches through each container, which is what makes it a check.
    assert list(_models_in(Optional[List[Node]])) == [Node]
    assert list(_models_in(Optional[TypingDict[str, Cell]])) == [Cell]
    assert list(_models_in(Optional[str])) == []
    assert list(_models_in(TypingDict[str, str])) == []

    # Every member of a union, not the first. A model the check cannot see is a
    # model nobody checked, which is the one thing a guard may not be.
    from typing import Union as TypingUnion

    assert set(_models_in(TypingUnion[Cell, Node])) == {Cell, Node}
    assert set(_models_in(Optional[List[TypingUnion[Cell, Node]]])) == {Cell, Node}

    # And no depth bound: an annotation nested past one would be skipped in
    # silence, which is the failure this check exists to prevent.
    deep = Optional[List[Optional[List[Optional[List[Optional[
        List[Optional[List[Optional[List[Optional[List[Cell]]]]]]]]]]]]]]
    assert list(_models_in(deep)) == [Cell]


def test_the_resolvability_memo_records_only_a_walk_that_finished():
    """A factory checks a shared graph once, and never records a failed walk.

    Linear's 145 tools reach the same filter graph, so checking each tool alone
    costs 208ms against 6.5ms shared. The memo is keyed by id and holds the
    class, which is what keeps the key meaning what it meant; it never needs
    invalidating because ``__pydantic_complete__`` only goes False to True. What
    it must not do is record models from a walk that raised — they were reached,
    not cleared, and the next tool off the same factory would skip them.
    """
    from typing import List

    from pydantic import Field

    from charter.execution.schema import SchemaStore
    from charter.tool import _check_schema_resolvable
    from charter.types.errors import DeclarationError

    class Fine(BaseModel):
        label: str = Field(..., description="A label.")

    class Broken(BaseModel):
        kids: Optional[List[AlsoMissing]] = Field(None, description="Kids.")  # noqa: F821

    class Args(BaseModel):
        # `Fine` is reached and cleared; `Broken` then stops the walk.
        fine: Optional[Fine] = Field(None, description="Fine.")
        broken: Optional[Broken] = Field(None, description="Broken.")

    store = SchemaStore()
    with pytest.raises(DeclarationError):
        _check_schema_resolvable(Args, "t", store.verified)
    assert store.verified == {}, (
        "a walk that raised recorded models as checked; the next tool off this "
        "factory would skip them"
    )

    # A walk that finishes records what it cleared, and holds the classes so the
    # ids it keyed them by cannot be handed to something else.
    ok_store = SchemaStore()
    _check_schema_resolvable(Fine, "t", ok_store.verified)
    assert set(ok_store.verified) == {id(Fine)}
    assert ok_store.verified[id(Fine)] is Fine

    # Second pass is a lookup, not a walk.
    _check_schema_resolvable(Fine, "t", ok_store.verified)
    assert set(ok_store.verified) == {id(Fine)}


def test_the_resolvability_check_sees_every_model_the_walk_builds():
    """A model the check cannot reach is a model it certifies without looking.

    The check walks source annotations; ``create_llm_schema`` walks them its own
    way, through four branches including a model reached as a ``Dict`` value.
    If the two disagree about what is reachable, the guard passes schemas whose
    failing model it never visited — which is worse than having no guard, because
    it reads as one.

    The walk itself is the authority, so it is instrumented rather than
    described: every source class it generates a view for has to be one the check
    would have visited. Run against the packs that carry the awkward shapes —
    Linear's cycle, Notion's dict-valued properties, Sheets' protobuf ``Value``.
    """
    import importlib

    from charter.execution import schema as schema_module
    from charter.tool import _models_in

    def reachable(root) -> set:
        found, stack, seen = set(), [root], set()
        while stack:
            model = stack.pop()
            if id(model) in seen:
                continue
            seen.add(id(model))
            found.add(model)
            for field in model.model_fields.values():
                stack.extend(_models_in(field.annotation))
        return found

    real = schema_module._create_llm_schema
    walked: list = []

    def spy(original_schema, **kwargs):
        walked.append(original_schema)
        return real(original_schema, **kwargs)

    # Built from the schema rather than through the tool, and with no store.
    # A tool memoises its view, so going through one would compare nothing at all
    # in a run where something earlier had already built it — which is every full
    # run of this suite, and exactly how this test first passed while asserting
    # nothing.
    subjects: list = []
    for pack in ("linear", "notion", "gsheets"):
        module = importlib.import_module(f"charter.packs.{pack}")
        by_schema: dict = {}
        for attr, tool in vars(module).items():
            if isinstance(tool, Tool):
                by_schema.setdefault(id(tool.args_schema), (pack, attr, tool))
        subjects.extend(list(by_schema.values())[:8])

    schema_module._create_llm_schema = spy
    try:
        missed: list = []
        checked = 0
        for pack, attr, tool in subjects:
            walked.clear()
            schema_module.create_llm_schema(
                tool.args_schema, mode=tool.mode, prune=tool._prune or None, cache=None
            )
            assert walked, f"{pack}.{attr}: the walk was not observed"
            checked += 1
            seen_by_check = reachable(tool.args_schema)
            for source in walked:
                if source not in seen_by_check:
                    missed.append((pack, attr, source.__name__))
    finally:
        schema_module._create_llm_schema = real

    assert checked == len(subjects) and checked >= 20, f"only {checked} compared"
    assert missed == [], (
        f"the walk built a view for {len(missed)} model(s) the check never "
        f"visits: {missed[:5]}"
    )


def test_every_shipped_tool_passes_the_resolvability_check():
    """The check is only worth having if it is not refusing the packs."""
    import importlib

    from charter.mcp import PACKS
    from charter.tool import _check_schema_resolvable

    checked = 0
    for pack in PACKS:
        module = importlib.import_module(f"charter.packs.{pack}")
        for tool in vars(module).values():
            if isinstance(tool, Tool):
                _check_schema_resolvable(tool.args_schema, tool.name)
                checked += 1
    assert checked > 100, f"only {checked} tools were checked"
