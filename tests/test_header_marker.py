"""Header(): an argument the model decides that the API takes as a request header.

Microsoft Graph sizes a delta page with `Prefer: odata.maxpagesize`, and nothing
in its query or body does the same job. Before the marker, the Outlook pack sent
it through a `Query()` field that `build_request` deleted and re-sent as a
header, and the generated docs listed it as a query parameter.

The value comes from a model, so these pin what it cannot do as well as what it
does: replace the credential or a static header, or break the header with a
line break.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from charter import Body, DeclarationError, Format, Header, Path, Query, Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.types.markers import declared_body_fields

BASE = "https://api.example.com/"


class Delta(BaseModel):
    folder_id: Annotated[str, Path()]
    select: Annotated[Optional[str], Query()] = None
    max_page_size: Annotated[
        Optional[int],
        Field(None, ge=1, description="The maximum number of items in each page."),
        Header("Prefer", template="odata.maxpagesize={}"),
    ] = None


def _tool(schema=Delta, **overrides) -> Tool:
    kwargs = dict(
        name="delta",
        description="Track changes.",
        method="GET",
        url_template="v1/folders/{folder_id}/delta",
        args_schema=schema,
        base_url=BASE,
        api_key_headers={"x-api-key": "k"},
    )
    kwargs.update(overrides)
    return Tool(**kwargs)


def _route():
    return respx.get(f"{BASE}v1/folders/inbox/delta").mock(
        return_value=httpx.Response(200, json={})
    )


# -----------------------------------------------------
# On the wire
# -----------------------------------------------------


@respx.mock
async def test_the_value_is_written_into_its_header_and_nowhere_else():
    route = _route()
    await _tool().ainvoke(folder_id="inbox", max_page_size=5, select="subject")

    request = route.calls[0].request
    assert request.headers["prefer"] == "odata.maxpagesize=5"
    assert dict(request.url.params) == {"select": "subject"}
    assert request.content == b""


@respx.mock
async def test_an_unset_header_argument_sends_no_header():
    route = _route()
    await _tool().ainvoke(folder_id="inbox")
    assert "prefer" not in route.calls[0].request.headers


def test_the_model_sees_it_as_an_argument():
    fields = _tool().llm_schema().model_fields
    assert "max_page_size" in fields
    assert "maximum number of items" in (fields["max_page_size"].description or "")


class Priority(Enum):
    HIGH = "high"


class Flags(BaseModel):
    folder_id: Annotated[str, Path()]
    urgent: Annotated[Optional[bool], Header("X-Urgent")] = None
    priority: Annotated[Optional[Priority], Header("X-Priority")] = None
    tier: Annotated[Optional[Literal["gold", "silver"]], Header("X-Tier")] = None


@respx.mock
async def test_a_boolean_an_enum_and_a_literal_are_sent_as_their_values():
    route = _route()
    await _tool(Flags).ainvoke(folder_id="inbox", urgent=True, priority="high", tier="gold")

    headers = route.calls[0].request.headers
    assert headers["x-urgent"] == "true"
    assert headers["x-priority"] == "high"
    assert headers["x-tier"] == "gold"


class Free(BaseModel):
    folder_id: Annotated[str, Path()]
    note: Annotated[Optional[str], Header("X-Note")] = None


@pytest.mark.parametrize("value", ["a\r\nX-Injected: yes", "a\nb", "a\rb", "a\0b"])
@respx.mock
async def test_a_line_break_is_refused_before_any_request(value):
    """A header value is one line. One that broke it would be a second header."""
    route = _route()
    with pytest.raises(ToolValidationError, match="'note' is sent as the X-Note header"):
        await _tool(Free).ainvoke(folder_id="inbox", note=value)
    assert not route.called


@respx.mock
async def test_a_build_request_override_and_the_host_are_more_specific():
    route = _route()
    tool = _tool(build_request=lambda _: {"headers": {"Prefer": "odata.maxpagesize=7"}})
    await tool.ainvoke(folder_id="inbox", max_page_size=5)
    assert route.calls[0].request.headers["prefer"] == "odata.maxpagesize=7"

    await _tool().ainvoke(
        {"folder_id": "inbox", "max_page_size": 5}, headers={"Prefer": "odata.maxpagesize=9"}
    )
    assert route.calls[1].request.headers["prefer"] == "odata.maxpagesize=9"


@respx.mock
async def test_a_pinned_header_argument_is_sent():
    route = _route()
    await _tool().derived(name="delta_small", pin={"max_page_size": 2}).ainvoke(folder_id="inbox")
    assert route.calls[0].request.headers["prefer"] == "odata.maxpagesize=2"


class Encoded(BaseModel):
    folder_id: Annotated[str, Path()]
    note: Annotated[Optional[str], Header("X-Note"), Format("base64")] = None


@respx.mock
async def test_a_transformed_header_argument_sends_the_transformed_value():
    route = _route()
    await _tool(Encoded).ainvoke(folder_id="inbox", note="hi")
    assert route.calls[0].request.headers["x-note"] == "aGk="


# -----------------------------------------------------
# The body does not count it
# -----------------------------------------------------


class Send(BaseModel):
    message: Annotated[dict, Body()]
    priority: Annotated[Optional[str], Header("X-Priority")] = None


def test_a_header_argument_is_not_a_body_field():
    """One Body() field unwraps; a header beside it must not make it two."""
    assert declared_body_fields(Send) == 1


@respx.mock
async def test_the_lone_body_field_still_unwraps_beside_a_header():
    route = respx.post(f"{BASE}v1/send").mock(return_value=httpx.Response(200, json={}))
    tool = _tool(Send, method="POST", url_template="v1/send")
    await tool.ainvoke(message={"subject": "hi"}, priority="high")

    request = route.calls[0].request
    assert request.content == b'{"subject":"hi"}'
    assert request.headers["x-priority"] == "high"


# -----------------------------------------------------
# What a declaration cannot say
# -----------------------------------------------------


@pytest.mark.parametrize("name", ["", "Two Words", "X-Bad:", "Prefer\r\n"])
def test_a_header_name_must_be_one_token(name):
    with pytest.raises(DeclarationError, match="is not a header name"):
        Header(name)


@pytest.mark.parametrize(
    "name", ["Authorization", "proxy-authorization", "Cookie", "Host", "Content-Type"]
)
def test_a_credential_or_a_derived_header_cannot_be_named(name):
    with pytest.raises(DeclarationError, match="may not set"):
        Header(name)


@pytest.mark.parametrize("template", ["odata.maxpagesize=", "{}-{}", "{0}"])
def test_a_template_has_exactly_one_slot(template):
    with pytest.raises(DeclarationError, match="exactly one"):
        Header("Prefer", template=template)


def test_a_static_header_cannot_also_be_an_argument():
    """Graph's `Prefer: outlook.body-content-type` beside a page size would lose one."""
    with pytest.raises(DeclarationError, match="static_headers already sets"):
        _tool(static_headers={"prefer": 'outlook.body-content-type="text"'})


def test_the_credential_header_cannot_be_an_argument():
    class Keyed(BaseModel):
        folder_id: Annotated[str, Path()]
        key: Annotated[Optional[str], Header("X-API-Key")] = None

    with pytest.raises(DeclarationError, match="the credential already sets"):
        _tool(Keyed)


def test_a_token_header_cannot_be_an_argument():
    class Shop(BaseModel):
        folder_id: Annotated[str, Path()]
        token: Annotated[Optional[str], Header("X-Shopify-Access-Token")] = None

    with pytest.raises(DeclarationError, match="the credential already sets"):
        _tool(
            Shop,
            api_key_headers=None,
            credential_provider=StaticTokenProvider("t"),
            token_header="X-Shopify-Access-Token",
        )


def test_two_arguments_cannot_name_one_header():
    class Twice(BaseModel):
        folder_id: Annotated[str, Path()]
        a: Annotated[Optional[str], Header("X-Note")] = None
        b: Annotated[Optional[str], Header("x-note")] = None

    with pytest.raises(DeclarationError, match="are both sent as the x-note header"):
        _tool(Twice)
