"""R3 — the execution pipeline, offline against respx.

Covers marker routing, the casing cascade on the wire, transforms, transport
overrides, credential injection, and error translation.
"""

from __future__ import annotations

import base64
import email
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from charter import (
    APIError,
    Body,
    Case,
    CharterError,
    CredentialError,
    EmailContent,
    Format,
    Mode,
    Path,
    Query,
    TransformError,
    Value,
    api_key_tool_factory,
)
from charter.auth import (
    Credentials,
    StaticTokenProvider,
)
from charter.execution.executor import (
    ToolExecutor,
    _create_auto_transformer,
    _dump_like_json,
)
from charter.execution.http import call_api

BASE = "https://api.example.com/"


def _decode_b64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8")


# -----------------------------------------------------
# _dump_like_json
# -----------------------------------------------------


class Inner(BaseModel):
    x: int = 1
    y: Optional[str] = None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("hello", "hello"),
        (42, 42),
        (Inner(x=5), {"x": 5}),
        ([Inner(x=1), Inner(x=2)], [{"x": 1}, {"x": 2}]),
        ({"a": Inner(x=3)}, {"a": {"x": 3}}),
        ([[Inner(x=7)]], [[{"x": 7}]]),
    ],
)
def test_dump_like_json(value, expected):
    assert _dump_like_json(value) == expected


# -----------------------------------------------------
# The auto-transformer
# -----------------------------------------------------


class PlainSchema(BaseModel):
    city: Annotated[str, Path()]
    units: Annotated[Optional[str], Query()] = "metric"


def test_auto_transformer_is_a_noop_without_format_markers():
    transformer = _create_auto_transformer(PlainSchema)
    assert transformer(PlainSchema(city="Tokyo")) == {}


class SendMessage(BaseModel):
    user_id: Annotated[str, Path()] = "me"
    raw: Annotated[EmailContent, Body(), Format("rfc822_base64")]


def test_auto_transformer_routes_a_transformed_body_field():
    """The transformed value is a base64 string — a scalar — so it is one key in
    the body rather than the whole of it. The routing here has to agree with
    `call_api`, which decides the same question through the same helper."""
    transformer = _create_auto_transformer(SendMessage)
    override = transformer(SendMessage(raw=EmailContent(to="a@b.com", subject="S", body="B")))
    assert set(override["body"]) == {"raw"}
    msg = email.message_from_string(_decode_b64url(override["body"]["raw"]))
    assert msg["To"] == "a@b.com"


def test_auto_transformer_envelops_when_asked():
    class Enveloped(BaseModel):
        message: Annotated[EmailContent, Body(envelop=True), Format("rfc822_base64")]

    transformer = _create_auto_transformer(Enveloped)
    override = transformer(Enveloped(message=EmailContent(to="a@b.com", subject="S", body="B")))
    assert set(override["body"]) == {"message"}


def test_transform_failure_names_the_field():
    class Bad(BaseModel):
        thing: Annotated[str, Body(), Format("no_such_transform")]

    transformer = _create_auto_transformer(Bad)
    with pytest.raises(TransformError) as excinfo:
        transformer(Bad(thing="x"))
    assert excinfo.value.field == "thing"


# -----------------------------------------------------
# ToolExecutor construction
# -----------------------------------------------------


class SimpleInput(BaseModel):
    id: Annotated[str, Path()]


def _executor(**overrides) -> ToolExecutor:
    kwargs: Dict[str, Any] = dict(
        method="GET",
        url_template="v1/{id}",
        base_url=BASE,
        original_schema=SimpleInput,
        api_key_headers={"x-api-key": "test-key"},
    )
    kwargs.update(overrides)
    return ToolExecutor(**kwargs)


def test_executor_requires_an_auth_method():
    with pytest.raises(ValueError, match="Must provide either"):
        ToolExecutor(
            method="GET", url_template="v1/{id}", base_url=BASE, original_schema=SimpleInput
        )


def test_executor_rejects_two_auth_methods():
    with pytest.raises(ValueError, match="Cannot use both"):
        _executor(credential_provider=StaticTokenProvider("t"))


def test_executor_rejects_a_sync_response_handler():
    def sync_handler(response):
        return response

    with pytest.raises(ValueError, match="async"):
        _executor(response_handler=sync_handler)


def test_executor_accepts_an_async_response_handler():
    async def handler(response):
        return response

    assert _executor(response_handler=handler)._response_handler is handler


def test_executor_uses_a_custom_build_request():
    def build(model):
        return {}

    assert _executor(build_request=build)._build_request is build


def test_executor_auto_generates_build_request():
    assert _executor()._build_request is not None


# -----------------------------------------------------
# Marker routing and casing, over the wire
# -----------------------------------------------------


class SearchInput(BaseModel):
    calendar_id: Annotated[str, Path()]
    max_results: Annotated[Optional[int], Query()] = None
    show_deleted: Annotated[Optional[bool], Query()] = None


@respx.mock
async def test_path_substitution_and_query_casing():
    route = respx.get(f"{BASE}calendar/v3/calendars/primary/events").mock(
        return_value=httpx.Response(200, json={"items": []})
    )

    result = await call_api(
        method="GET",
        url_template="calendar/v3/calendars/{calendar_id}/events",
        tool_input=SearchInput(calendar_id="primary", max_results=10, show_deleted=False),
        base_url=BASE,
        query_case="camel",
    )

    assert result == {"items": []}
    request = route.calls.last.request
    assert dict(request.url.params) == {"maxResults": "10", "showDeleted": "false"}


@respx.mock
async def test_none_valued_fields_are_omitted_entirely():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))

    await call_api(
        method="GET",
        url_template="v1/{calendar_id}",
        tool_input=SearchInput(calendar_id="x"),
        base_url=BASE,
        query_case="camel",
    )
    assert dict(route.calls.last.request.url.params) == {}


class BodyInput(BaseModel):
    doc_id: Annotated[str, Path()]
    display_name: Annotated[str, Case("pascal"), Body()]
    user_email: Annotated[str, Body()]


@respx.mock
async def test_body_casing_cascade_field_beats_endpoint():
    route = respx.post(f"{BASE}v1/docs/d1").mock(return_value=httpx.Response(200, json={}))

    await call_api(
        method="POST",
        url_template="v1/docs/{doc_id}",
        tool_input=BodyInput(doc_id="d1", display_name="Ada", user_email="a@b.com"),
        base_url=BASE,
        body_case="camel",
    )

    import json as _json

    body = _json.loads(route.calls.last.request.content)
    assert body == {"DisplayName": "Ada", "userEmail": "a@b.com"}


@respx.mock
async def test_schema_case_dunder_applies_to_the_body():
    class PascalBody(BaseModel):
        doc_id: Annotated[str, Path()]
        first_name: Annotated[str, Body()]
        last_name: Annotated[str, Body()]

    PascalBody.__case__ = "pascal"

    route = respx.post(f"{BASE}v1/d1").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="POST",
        url_template="v1/{doc_id}",
        tool_input=PascalBody(doc_id="d1", first_name="Ada", last_name="L"),
        base_url=BASE,
        body_case="camel",
    )

    import json as _json

    assert _json.loads(route.calls.last.request.content) == {
        "FirstName": "Ada",
        "LastName": "L",
    }


@respx.mock
async def test_path_case_conversion():
    class PathCase(BaseModel):
        user_id: Annotated[str, Path()]

    route = respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="GET",
        url_template="v1/{userId}",
        tool_input=PathCase(user_id="me"),
        base_url=BASE,
        path_case="camel",
    )
    assert route.called


@respx.mock
async def test_missing_path_parameter_is_a_clear_error():
    class Missing(BaseModel):
        other: Annotated[str, Query()] = "x"

    with pytest.raises(ValueError, match="Missing required path parameter 'calendar_id'"):
        await call_api(
            method="GET",
            url_template="v1/{calendar_id}",
            tool_input=Missing(),
            base_url=BASE,
        )


# -----------------------------------------------------
# Body modes
# -----------------------------------------------------


@respx.mock
async def test_single_body_field_is_unwrapped():
    class Unwrapped(BaseModel):
        payload: Annotated[dict, Body()]

    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="POST",
        url_template="v1/x",
        tool_input=Unwrapped(payload={"a": 1}),
        base_url=BASE,
    )
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {"a": 1}


@respx.mock
async def test_enveloped_body_keeps_the_field_name():
    class Enveloped(BaseModel):
        message: Annotated[dict, Body(envelop=True)]

    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="POST",
        url_template="v1/x",
        tool_input=Enveloped(message={"a": 1}),
        base_url=BASE,
    )
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {"message": {"a": 1}}


@respx.mock
async def test_multiple_body_fields_merge_under_their_names():
    class Composite(BaseModel):
        requests: Annotated[list, Body()]
        include_grid_data: Annotated[bool, Body()]

    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="POST",
        url_template="v1/x",
        tool_input=Composite(requests=[1], include_grid_data=True),
        base_url=BASE,
        body_case="camel",
    )
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {
        "requests": [1],
        "includeGridData": True,
    }


# -----------------------------------------------------
# Auth
# -----------------------------------------------------


@respx.mock
async def test_bearer_credentials_become_an_authorization_header():
    route = respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="GET",
        url_template="v1/{id}",
        tool_input=SimpleInput(id="me"),
        credentials=Credentials(token="tok123"),
        base_url=BASE,
    )
    assert route.calls.last.request.headers["authorization"] == "Bearer tok123"


@respx.mock
async def test_api_key_headers_are_injected_by_the_executor():
    route = respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={"ok": 1}))
    result = await _executor().execute(SimpleInput(id="me"))

    assert result == {"ok": 1}
    assert route.calls.last.request.headers["x-api-key"] == "test-key"
    assert "authorization" not in route.calls.last.request.headers


@respx.mock
async def test_credential_provider_is_consulted_per_call():
    calls = []

    class Counting:
        async def get_credentials(self, provider):
            calls.append(provider)
            return Credentials(token=f"tok{len(calls)}")

    route = respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={}))
    executor = ToolExecutor(
        method="GET",
        url_template="v1/{id}",
        base_url=BASE,
        original_schema=SimpleInput,
        credential_provider=Counting(),
        provider="google",
    )

    await executor.execute(SimpleInput(id="me"))
    await executor.execute(SimpleInput(id="me"))

    assert calls == ["google", "google"]
    assert route.calls[-1].request.headers["authorization"] == "Bearer tok2"


async def test_expired_credentials_raise_before_any_request():
    class Expired:
        async def get_credentials(self, provider):
            return Credentials(
                token="stale",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )

    executor = ToolExecutor(
        method="GET",
        url_template="v1/{id}",
        base_url=BASE,
        original_schema=SimpleInput,
        credential_provider=Expired(),
        provider="google",
    )

    with pytest.raises(CredentialError) as excinfo:
        await executor.execute(SimpleInput(id="me"))
    assert excinfo.value.provider == "google"


# -----------------------------------------------------
# Error translation
# -----------------------------------------------------


@respx.mock
async def test_401_becomes_a_credential_error():
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Invalid Credentials"}})
    )

    with pytest.raises(CredentialError) as excinfo:
        await call_api(
            method="GET",
            url_template="v1/{id}",
            tool_input=SimpleInput(id="me"),
            base_url=BASE,
            provider="google",
        )

    assert excinfo.value.status_code == 401
    assert excinfo.value.provider == "google"
    assert "Invalid Credentials" in str(excinfo.value)


@respx.mock
async def test_403_is_an_api_error_not_a_credential_error():
    """403 is not an instruction to re-authenticate.

    HTTP separates the two on purpose: 401 says the request was unauthenticated,
    403 says it was authenticated and still refused. Google answers 403 for an
    IAM permission that no amount of consenting will grant, and GitHub answers
    403 for a rate limit — reporting either as a credential failure sends a
    well-behaved host into an OAuth flow that cannot fix it.
    """
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(403, json={"error": {"message": "Permission denied"}})
    )

    with pytest.raises(APIError) as excinfo:
        await call_api(
            method="GET",
            url_template="v1/{id}",
            tool_input=SimpleInput(id="me"),
            base_url=BASE,
            provider="google",
        )

    assert excinfo.value.status_code == 403
    assert "Permission denied" in str(excinfo.value)


@respx.mock
async def test_an_api_can_declare_that_it_means_credentials_by_403():
    """Some APIs use 403 for a missing scope, which re-consent does fix."""
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(403, json={"error": {"message": "Insufficient scope"}})
    )

    with pytest.raises(CredentialError) as excinfo:
        await call_api(
            method="GET",
            url_template="v1/{id}",
            tool_input=SimpleInput(id="me"),
            base_url=BASE,
            provider="google",
            credential_statuses={401, 403},
        )

    assert excinfo.value.status_code == 403


@respx.mock
async def test_other_4xx_becomes_an_api_error_with_the_provider_message():
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "Invalid query", "status": "INVALID_ARGUMENT"}}
        )
    )

    with pytest.raises(APIError) as excinfo:
        await call_api(
            method="GET", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
        )

    assert excinfo.value.status_code == 400
    assert "Invalid query" in str(excinfo.value)


@respx.mock
@pytest.mark.parametrize(
    "payload",
    [
        {"detail": "nope"},
        {"message": "nope"},
        {"error_description": "nope"},
        # Firecrawl and Linear both answer like this. Without it the message is
        # the HTTP reason phrase and the provider's own sentence survives only
        # in the body excerpt.
        {"error": "nope"},
    ],
)
async def test_flat_error_shapes_are_understood(payload):
    respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(422, json=payload))
    with pytest.raises(APIError) as excinfo:
        await call_api(
            method="GET", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
        )
    assert excinfo.value.message == "nope"


@respx.mock
async def test_nested_detail_error_object_is_unwrapped():
    """FastAPI-style bodies put the message under ``detail.error``, not ``detail``."""
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(400, json={"detail": {"error": "Max 20 URLs are allowed."}})
    )
    with pytest.raises(APIError, match="Max 20 URLs are allowed"):
        await call_api(
            method="GET", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
        )


@respx.mock
async def test_non_json_error_body_still_raises_api_error():
    respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(500, text="upstream exploded"))
    with pytest.raises(APIError) as excinfo:
        await call_api(
            method="GET", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
        )
    assert excinfo.value.status_code == 500
    assert "upstream exploded" in excinfo.value.body


# -----------------------------------------------------
# Responses
# -----------------------------------------------------


@respx.mock
async def test_204_returns_an_empty_dict():
    respx.delete(f"{BASE}v1/me").mock(return_value=httpx.Response(204))
    result = await call_api(
        method="DELETE", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
    )
    assert result == {}


@respx.mock
async def test_non_json_success_is_wrapped_as_raw():
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(200, text="plain text", headers={"content-type": "text/plain"})
    )
    result = await call_api(
        method="GET", url_template="v1/{id}", tool_input=SimpleInput(id="me"), base_url=BASE
    )
    assert result == {"raw": "plain text"}


@respx.mock
async def test_response_handler_reshapes_the_result():
    respx.get(f"{BASE}v1/me").mock(
        return_value=httpx.Response(200, json={"messages": [{"id": 1}], "noise": "x" * 100})
    )

    async def keep_ids(response):
        return [m["id"] for m in response["messages"]]

    result = await _executor(response_handler=keep_ids).execute(SimpleInput(id="me"))
    assert result == [1]


# -----------------------------------------------------
# Transport override merging
# -----------------------------------------------------


@respx.mock
async def test_transport_override_merges_rather_than_replaces_query():
    route = respx.get(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="GET",
        url_template="v1/{calendar_id}",
        tool_input=SearchInput(calendar_id="x", max_results=5),
        base_url=BASE,
        query_case="snake",
        transport_override={"query": {"extra": "1"}},
    )
    params = dict(route.calls.last.request.url.params)
    assert params == {"max_results": "5", "extra": "1"}


@respx.mock
async def test_transport_override_headers_win():
    route = respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="GET",
        url_template="v1/{id}",
        tool_input=SimpleInput(id="me"),
        credentials=Credentials(token="tok"),
        base_url=BASE,
        transport_override={"headers": {"Authorization": "Bearer override"}},
    )
    assert route.calls.last.request.headers["authorization"] == "Bearer override"


# -----------------------------------------------------
# The full pipeline
# -----------------------------------------------------


class GmailSend(BaseModel):
    """Path + Query + Body + Format + Mode, all at once."""

    user_id: Annotated[str, Path()] = "me"
    pretty_print: Annotated[Optional[bool], Query()] = None
    raw: Annotated[EmailContent, Body(), Format("rfc822_base64")] = Field(
        ..., description="The message to send"
    )
    thread_id: Annotated[Optional[str], Body(), Mode("response_only")] = None


@respx.mock
async def test_full_pipeline_path_query_body_transform_and_mode():
    route = respx.post(f"{BASE}gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1", "threadId": "t1"})
    )

    executor = ToolExecutor(
        method="POST",
        url_template="gmail/v1/users/{user_id}/messages/send",
        base_url=BASE,
        original_schema=GmailSend,
        body_case="camel",
        query_case="camel",
        credential_provider=StaticTokenProvider("tok"),
        provider="google",
    )

    result = await executor.execute(
        GmailSend(
            pretty_print=True,
            raw=EmailContent(to="ada@example.com", subject="Hi", body="Hello"),
        )
    )

    request = route.calls.last.request

    # URL substitution
    assert str(request.url).startswith(f"{BASE}gmail/v1/users/me/messages/send")
    # Query casing
    assert dict(request.url.params) == {"prettyPrint": "true"}
    # Auth
    assert request.headers["authorization"] == "Bearer tok"

    # Transform applied: the body is the base64url RFC822 message
    import json as _json

    # Two Body() fields means the body is a mapping, so the transformed `raw`
    # is keyed rather than becoming the body outright. That is also what Gmail
    # wants: {"raw": "<base64url>"}. Before the transform routing was made to
    # agree with `call_api`'s own single-body rule, this sent the bare string
    # and dropped `thread_id` with it.
    body = _json.loads(request.content)
    msg = email.message_from_string(_decode_b64url(body["raw"]))
    assert msg["To"] == "ada@example.com"
    assert msg["Subject"] == "Hi"

    # response_only field is absent from the LLM view but present in the response
    from charter.execution.schema import create_llm_schema

    assert "thread_id" not in create_llm_schema(GmailSend).model_fields
    assert result["threadId"] == "t1"


@respx.mock
async def test_proto_json_matrix_reaches_the_wire_as_plain_json():
    class SheetsUpdate(BaseModel):
        spreadsheet_id: Annotated[str, Path()]
        values: Annotated[Optional[List[List[Value]]], Body(), Format("proto_json")] = None

    route = respx.post(f"{BASE}v4/spreadsheets/s1").mock(return_value=httpx.Response(200, json={}))

    await call_api(
        method="POST",
        url_template="v4/spreadsheets/{spreadsheet_id}",
        tool_input=SheetsUpdate.model_validate(
            {"spreadsheet_id": "s1", "values": [["Name", "Score"], ["Ada", 99]]}
        ),
        base_url=BASE,
        transport_override=_create_auto_transformer(SheetsUpdate)(
            SheetsUpdate.model_validate(
                {"spreadsheet_id": "s1", "values": [["Name", "Score"], ["Ada", 99]]}
            )
        ),
    )

    import json as _json

    assert _json.loads(route.calls.last.request.content) == [
        ["Name", "Score"],
        ["Ada", 99.0],
    ]


@respx.mock
async def test_a_supplied_client_is_reused_and_not_closed():
    respx.get(f"{BASE}v1/me").mock(return_value=httpx.Response(200, json={}))
    async with httpx.AsyncClient() as client:
        await call_api(
            method="GET",
            url_template="v1/{id}",
            tool_input=SimpleInput(id="me"),
            base_url=BASE,
            client=client,
        )
        assert not client.is_closed


# -----------------------------------------------------
# The body shape is a property of the schema, not the call
# -----------------------------------------------------


class OptionalBodies(BaseModel):
    """Several optional body fields — the shape that exposed the bug."""

    channel: Annotated[str, Body()]
    text: Annotated[Optional[str], Body()] = None
    thread_ts: Annotated[Optional[str], Body()] = None


@respx.mock
async def test_body_shape_does_not_depend_on_which_fields_are_populated():
    """Regression: unwrapping used to be decided by how many body fields happened
    to be non-None, so the same tool sent {"channel": ...} on one call and a bare
    "C1" on the next. The wire shape must follow the schema alone."""
    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))

    import json as _json

    await call_api(
        method="POST", url_template="v1/x", tool_input=OptionalBodies(channel="C1"), base_url=BASE
    )
    one = _json.loads(route.calls.last.request.content)

    await call_api(
        method="POST",
        url_template="v1/x",
        tool_input=OptionalBodies(channel="C1", text="hi"),
        base_url=BASE,
    )
    two = _json.loads(route.calls.last.request.content)

    assert one == {"channel": "C1"}
    assert two == {"channel": "C1", "text": "hi"}
    assert isinstance(one, dict) and isinstance(two, dict)


@respx.mock
async def test_a_schema_with_one_declared_body_field_still_unwraps():
    """The common case is unchanged: one declared Body() field is the body."""

    class OneBody(BaseModel):
        payload: Annotated[dict, Body()]

    route = respx.post(f"{BASE}v1/x").mock(return_value=httpx.Response(200, json={}))
    await call_api(
        method="POST",
        url_template="v1/x",
        tool_input=OneBody(payload={"a": 1}),
        base_url=BASE,
    )
    import json as _json

    assert _json.loads(route.calls.last.request.content) == {"a": 1}


async def test_an_unmarked_top_level_field_is_refused_rather_than_guessed():
    """The schema is the contract, so an unstated one is an error.

    This used to default to `Body()` and announce it through `warnings.warn` —
    the only diagnostic in the runtime that did not go through the `charter`
    logger, so a host that configured Charter's logging saw nothing, and a host
    under `-W ignore` saw nothing at all. The field went to the wire on a guess,
    announced where nobody was listening. An unmarked field is either an
    authoring slip or a response-only field somebody forgot to mark, and both
    send something the author did not intend.
    """

    class Unmarked(BaseModel):
        location: Annotated[str, Path()]
        mystery: Optional[str] = None

    tool = api_key_tool_factory(
        pack="execution",
        base_url="https://api.example.com/",
        api_key_headers={"x-api-key": "k"},
    )(
        name="unmarked",
        args_schema=Unmarked,
        method="POST",
        url_template="v1/things/{location}",
    )

    with respx.mock:
        route = respx.post("https://api.example.com/v1/things/here").mock(
            return_value=httpx.Response(200, json={})
        )
        with pytest.raises(CharterError, match="mystery"):
            await tool.ainvoke(location="here", mystery="sent on a guess")

    assert not route.called, "the request must not be built at all"


async def test_the_refusal_names_the_markers_and_the_way_out():
    class Unmarked(BaseModel):
        mystery: Optional[str] = None

    tool = api_key_tool_factory(
        pack="execution",
        base_url="https://api.example.com/",
        api_key_headers={"x-api-key": "k"},
    )(name="unmarked", args_schema=Unmarked, method="POST", url_template="v1/things")

    with respx.mock:
        respx.route().mock(return_value=httpx.Response(200, json={}))
        with pytest.raises(CharterError) as excinfo:
            await tool.ainvoke(mystery="x")

    message = str(excinfo.value)
    assert "Path()" in message and "Query()" in message and "Body()" in message
    assert "response_only" in message
