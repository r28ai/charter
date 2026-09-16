"""R3 — the key-case cascade.

Ported from charter-runtime-lib's test_key_case.py and tests/test_case_cascade.py,
converted from assert-scripts to pytest.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from charter import Body, Case, Path, Query, WireName
from charter.execution.casing import DictKeyParser

# -----------------------------------------------------
# Single-key conversion
# -----------------------------------------------------


@pytest.mark.parametrize(
    ("key", "case", "expected"),
    [
        ("date_time", "camel", "dateTime"),
        ("user_id", "camel", "userId"),
        ("date_time", "pascal", "DateTime"),
        ("user_id", "pascal", "UserId"),
        ("date_time", "kebab", "date-time"),
        ("user_id", "kebab", "user-id"),
        ("date_time", "snake", "date_time"),
        ("single", "camel", "single"),
        ("single", "pascal", "Single"),
    ],
)
def test_convert_key(key, case, expected):
    assert DictKeyParser.convert_key(key, case) == expected


def test_unknown_case_raises():
    with pytest.raises(ValueError, match="Unknown case"):
        DictKeyParser.convert_key("user_id", "screaming")


# -----------------------------------------------------
# Recursive conversion
# -----------------------------------------------------

NESTED = {
    "user_id": 1,
    "localized_name": {"display_name": "hi"},
    "items": [{"item_name": "x"}],
}


def test_snake_is_identity_and_returns_the_same_object():
    result = DictKeyParser.convert_keys_recursive(dict(NESTED), "snake")
    assert result["user_id"] == 1
    assert result["localized_name"]["display_name"] == "hi"
    assert result["items"][0]["item_name"] == "x"

    same = dict(NESTED)
    assert DictKeyParser.convert_keys_recursive(same, "snake") is same


def test_camel_converts_at_every_depth():
    camel = DictKeyParser.convert_keys_recursive(NESTED, "camel")
    assert "userId" in camel
    assert "localizedName" in camel
    assert camel["localizedName"]["displayName"] == "hi"
    assert camel["items"][0]["itemName"] == "x"


def test_pascal_converts_at_every_depth():
    pascal = DictKeyParser.convert_keys_recursive(NESTED, "pascal")
    assert "UserId" in pascal
    assert "LocalizedName" in pascal
    assert pascal["LocalizedName"]["DisplayName"] == "hi"
    assert pascal["Items"][0]["ItemName"] == "x"


def test_kebab_converts_at_every_depth():
    data = {"first_name": "Alice", "address": {"street_name": "Main St"}}
    kebab = DictKeyParser.convert_keys_recursive(data, "kebab")
    assert "first-name" in kebab
    assert "street-name" in kebab["address"]


def test_values_are_never_converted():
    data = {"user_id": "keep_me_snake"}
    assert DictKeyParser.convert_keys_recursive(data, "camel")["userId"] == "keep_me_snake"


def test_list_of_dicts_body():
    list_body = [{"first_name": "Alice"}, {"first_name": "Bob"}]
    camel = [DictKeyParser.convert_keys_recursive(i, "camel") for i in list_body]
    assert camel[0]["firstName"] == "Alice"
    assert camel[1]["firstName"] == "Bob"

    pascal = [DictKeyParser.convert_keys_recursive(i, "pascal") for i in list_body]
    assert pascal[0]["FirstName"] == "Alice"


# -----------------------------------------------------
# The cascade: Field > Schema > Default
# -----------------------------------------------------


def test_field_level_override_beats_the_default():
    data = {"display_name": "Bob", "user_id": "123", "email_address": "bob@example.com"}
    result = DictKeyParser.convert_keys_recursive(
        data, "camel", field_cases={"display_name": "pascal"}
    )
    assert "DisplayName" in result  # field-level pascal
    assert "userId" in result  # camel default
    assert "emailAddress" in result  # camel default


def test_field_level_override_to_kebab():
    data = {"user_id": "123", "email_address": "bob@example.com"}
    result = DictKeyParser.convert_keys_recursive(
        data, "camel", field_cases={"email_address": "kebab"}
    )
    assert "email-address" in result
    assert "userId" in result


def test_schema_level_override_beats_the_default():
    data = {"first_name": "Alice", "last_name": "Smith"}
    result = DictKeyParser.convert_keys_recursive(data, "camel", schema_case="pascal")
    assert "FirstName" in result
    assert "LastName" in result


def test_full_cascade_field_beats_schema_beats_default():
    data = {"display_name": "Charlie", "user_id": "456", "email_address": "c@ex.com"}
    result = DictKeyParser.convert_keys_recursive(
        data, "camel", schema_case="kebab", field_cases={"display_name": "pascal"}
    )
    assert "DisplayName" in result  # field-level pascal wins
    assert "user-id" in result  # schema-level kebab beats camel default
    assert "email-address" in result  # schema-level kebab


def test_field_and_schema_cases_apply_at_the_top_level_only():
    """Nested objects recurse with the plain case — a field marker names a field
    on *this* schema, so it would be meaningless against a nested object's keys."""
    data = {"display_name": "Bob", "nested": {"display_name": "inner"}}
    result = DictKeyParser.convert_keys_recursive(
        data, "camel", field_cases={"display_name": "pascal"}
    )
    assert "DisplayName" in result
    assert "displayName" in result["nested"]  # nested uses the plain default


# -----------------------------------------------------
# Case markers on models
# -----------------------------------------------------


class MixedCaseInput(BaseModel):
    user_id: Annotated[str, Path()]
    display_name: Annotated[str, Case("pascal"), Body()]
    search_query: Annotated[str, Query()]
    regular_field: Annotated[str, Body()]


def test_case_markers_are_extractable_from_field_metadata():
    field_cases = {}
    for name, field in MixedCaseInput.model_fields.items():
        for m in field.metadata:
            if isinstance(m, Case):
                field_cases[name] = m.case
                break

    assert field_cases.get("display_name") == "pascal"
    assert "user_id" not in field_cases
    assert "search_query" not in field_cases
    assert "regular_field" not in field_cases


class PascalSchemaInput(BaseModel):
    __case__ = "pascal"
    first_name: Annotated[str, Body()]
    last_name: Annotated[str, Body()]


class NoCaseInput(BaseModel):
    first_name: Annotated[str, Body()]


class ChildSchema(PascalSchemaInput):
    middle_name: Annotated[Optional[str], Body()] = None


def test_schema_case_dunder():
    assert getattr(PascalSchemaInput, "__case__", None) == "pascal"
    assert getattr(NoCaseInput, "__case__", None) is None
    assert getattr(ChildSchema, "__case__", None) == "pascal"


# -----------------------------------------------------
# WireName — the key the API documents
# -----------------------------------------------------


def _tool(args_schema, **kwargs):
    from charter import api_key_tool_factory

    factory = api_key_tool_factory(
        base_url="https://x.test/", pack="t", api_key_headers={"k": "v"}, **kwargs
    )
    return factory(
        name="t", args_schema=args_schema, method="POST", url_template="go", description="d"
    )


class _WireArgs(BaseModel):
    i_cal_uid: Annotated[Optional[str], Field(None), Query(), WireName("iCalUID")]
    max_results: Annotated[Optional[int], Field(None), Query()]


@respx.mock
async def test_a_wire_name_survives_the_default_snake_casing():
    """No convention reaches `iCalUID` from a snake field, so the marker has to
    win at every casing — including the default, where the conversion branch used
    to be skipped entirely."""
    route = respx.post(url__regex=r"https://x\.test/go.*").mock(
        return_value=httpx.Response(200, json={})
    )
    await _tool(_WireArgs).ainvoke({"iCalUid": "a", "maxResults": 2})
    params = dict(route.calls[0].request.url.params)
    assert params == {"iCalUID": "a", "max_results": "2"}


@respx.mock
async def test_a_wire_name_beats_every_convention_in_the_cascade():
    route = respx.post(url__regex=r"https://x\.test/go.*").mock(
        return_value=httpx.Response(200, json={})
    )
    await _tool(_WireArgs, query_case="camel").ainvoke({"iCalUid": "a", "maxResults": 2})
    params = dict(route.calls[0].request.url.params)
    assert params == {"iCalUID": "a", "maxResults": "2"}, "camel casing overrode the marker"


@respx.mock
async def test_a_wire_name_reaches_an_unwrapped_body():
    """A single Body() field is unwrapped to the JSON root, so the keys sent are
    the *nested* model's field names. Looked up against the request schema, the
    marker would work on a query parameter and silently not on the body field
    beside it."""

    class Nested(BaseModel):
        i_cal_uid: Annotated[Optional[str], Field(None), WireName("iCalUID")]
        summary: Annotated[Optional[str], Field(None)]

    class Args(BaseModel):
        payload: Annotated[Nested, Field(...), Body()]

    route = respx.post(url__regex=r"https://x\.test/go.*").mock(
        return_value=httpx.Response(200, json={})
    )
    await _tool(Args).ainvoke({"payload": {"iCalUid": "a", "summary": "s"}})
    assert json.loads(route.calls[0].request.content) == {"iCalUID": "a", "summary": "s"}


def test_a_wire_name_must_actually_name_something():
    from charter.types.errors import DeclarationError

    with pytest.raises(DeclarationError, match="WireName needs the key"):
        WireName("   ")


@respx.mock
async def test_a_field_case_is_honoured_on_a_query_at_default_casing():
    """`Case` is documented as the highest priority in the cascade and was
    silently the lowest on query parameters: the conversion was gated on the
    factory's query_case alone, so at the snake default the field override was
    dropped. Six of the eleven shipped packs sit at that default. The body path
    beside it always honoured the same marker."""

    class Args(BaseModel):
        display_name: Annotated[Optional[str], Field(None), Query(), Case("pascal")]
        plain: Annotated[Optional[str], Field(None), Query()]

    route = respx.post(url__regex=r"https://x\.test/go.*").mock(
        return_value=httpx.Response(200, json={})
    )
    await _tool(Args).ainvoke({"displayName": "a", "plain": "b"})
    assert dict(route.calls[0].request.url.params) == {"DisplayName": "a", "plain": "b"}
