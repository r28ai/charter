"""R1 — the type system: markers, semantic types, protobuf models, errors."""

from __future__ import annotations

from typing import Annotated, List, Optional, get_args, get_type_hints

import pytest
from pydantic import BaseModel, Field, ValidationError

import charter
from charter.types import (
    APIError,
    Body,
    Case,
    CharterError,
    CredentialError,
    DocumentContent,
    EmailContent,
    FieldMask,
    FileContent,
    Format,
    ListValue,
    Mode,
    Path,
    Query,
    Struct,
    ToolValidationError,
    TransformError,
    Value,
)

# -----------------------------------------------------
# Markers as Annotated metadata
# -----------------------------------------------------


class SendMessageSchema(BaseModel):
    """The R1 acceptance schema: a Body field carrying a Format transform."""

    user_id: Annotated[str, Path()] = "me"
    raw: Annotated[str, Body(), Format("rfc822_base64")]
    pretty_print: Annotated[Optional[bool], Query()] = None
    thread_id: Annotated[Optional[str], Body(), Mode("response_only")] = None
    display_name: Annotated[Optional[str], Body(), Case("pascal")] = None


def _metadata_for(schema: type[BaseModel], field: str) -> list:
    return list(schema.model_fields[field].metadata)


def test_body_and_format_metadata_round_trips():
    """Accept (R1): construct Annotated[str, Body(), Format(...)] and read it back."""
    metadata = _metadata_for(SendMessageSchema, "raw")

    body = next(m for m in metadata if isinstance(m, Body))
    fmt = next(m for m in metadata if isinstance(m, Format))

    assert body.envelop is False
    assert fmt.transform == "rfc822_base64"


def test_markers_survive_get_type_hints():
    """Annotated metadata must be recoverable from the raw annotation too."""
    hints = get_type_hints(SendMessageSchema, include_extras=True)
    args = get_args(hints["raw"])

    assert args[0] is str
    assert any(isinstance(a, Body) for a in args)
    assert any(isinstance(a, Format) and a.transform == "rfc822_base64" for a in args)


def test_each_location_marker_is_distinguishable():
    assert isinstance(_metadata_for(SendMessageSchema, "user_id")[0], Path)
    assert any(isinstance(m, Query) for m in _metadata_for(SendMessageSchema, "pretty_print"))
    assert any(isinstance(m, Body) for m in _metadata_for(SendMessageSchema, "raw"))


def test_body_envelop_flag():
    assert Body().envelop is False
    assert Body(envelop=True).envelop is True


def test_case_marker_carries_key_case():
    case = next(m for m in _metadata_for(SendMessageSchema, "display_name") if isinstance(m, Case))
    assert case.case == "pascal"


# -----------------------------------------------------
# Mode parsing
# -----------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("response_only", {"response_only"}),
        ("request_only", {"request_only"}),
        ("disabled", {"disabled"}),
        ("create,update", {"create", "update"}),
        ("create , update ", {"create", "update"}),
        ("", set()),
    ],
)
def test_mode_parses_comma_separated_modes(spec, expected):
    assert Mode(spec).modes == expected


def test_mode_on_field_is_readable():
    mode = next(m for m in _metadata_for(SendMessageSchema, "thread_id") if isinstance(m, Mode))
    assert mode.modes == {"response_only"}


# -----------------------------------------------------
# Semantic types
# -----------------------------------------------------


def test_email_content_accepts_from_alias_and_field_name():
    by_alias = EmailContent(to="a@b.com", subject="s", body="b", **{"from": "me@x.com"})
    by_name = EmailContent(to="a@b.com", subject="s", body="b", from_="me@x.com")

    assert by_alias.from_ == "me@x.com"
    assert by_name.from_ == "me@x.com"


def test_email_content_dumps_alias():
    email = EmailContent(to="a@b.com", subject="s", body="b", from_="me@x.com")
    dumped = email.model_dump(exclude_none=True, by_alias=True)

    assert dumped["from"] == "me@x.com"
    assert "from_" not in dumped


def test_email_content_accepts_list_recipients():
    email = EmailContent(to=["a@b.com", "c@d.com"], subject="s", body="b")
    assert email.to == ["a@b.com", "c@d.com"]


def test_email_content_requires_core_fields():
    with pytest.raises(ValidationError):
        EmailContent(subject="s", body="b")  # type: ignore[call-arg]


def test_document_and_file_content():
    doc = DocumentContent(title="T", content="# hi")
    assert doc.metadata is None

    f = FileContent(filename="a.txt", content="hello")
    assert f.mime_type is None


# -----------------------------------------------------
# Protobuf models
# -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "attr", "expected"),
    [
        ("hello", "string_value", "hello"),
        (42, "number_value", 42.0),
        (3.5, "number_value", 3.5),
        (True, "bool_value", True),
        (False, "bool_value", False),
        (None, "null_value", "NULL_VALUE"),
    ],
)
def test_value_coerces_plain_json_primitives(raw, attr, expected):
    """Accept (R2/R1): the LLM sends a primitive, not {"string_value": ...}."""
    value = Value.model_validate(raw)
    assert getattr(value, attr) == expected


def test_value_bool_is_not_coerced_to_number():
    """bool is a subclass of int — the bool branch must win."""
    value = Value.model_validate(True)
    assert value.bool_value is True
    assert value.number_value is None


def test_value_accepts_explicit_variant_dict():
    value = Value.model_validate({"string_value": "explicit"})
    assert value.string_value == "explicit"


def test_value_rejects_multiple_variants():
    with pytest.raises(ValidationError):
        Value.model_validate({"string_value": "a", "number_value": 1.0})


def test_value_rejects_empty_variant_set():
    with pytest.raises(ValidationError):
        Value.model_validate({})


def test_nested_struct_and_list_value():
    struct = Struct.model_validate({"fields": {"name": "Ada", "age": 36}})
    assert struct.fields is not None
    assert struct.fields["name"].string_value == "Ada"
    assert struct.fields["age"].number_value == 36.0

    lv = ListValue.model_validate({"values": ["a", 1, True]})
    assert [v.string_value for v in lv.values] == ["a", None, None]
    assert lv.values[1].number_value == 1.0
    assert lv.values[2].bool_value is True


def test_field_mask_shorthands():
    assert FieldMask.model_validate({"paths": ["a", "b"]}).paths == ["a", "b"]
    assert FieldMask.model_validate(["a", "b"]).paths == ["a", "b"]
    assert FieldMask.model_validate("a, b ,c").paths == ["a", "b", "c"]
    assert FieldMask.model_validate("a,,b").paths == ["a", "b"]


def test_protobuf_models_generate_json_schema():
    """These must be usable in LLM tool schema generation."""

    class Sheet(BaseModel):
        values: Annotated[Optional[List[List[Value]]], Format("proto_json")] = Field(default=None)

    schema = Sheet.model_json_schema()
    assert "properties" in schema
    assert "values" in schema["properties"]


# -----------------------------------------------------
# Errors
# -----------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        CredentialError("nope"),
        ToolValidationError("nope"),
        TransformError("nope"),
        APIError("nope", status_code=500),
    ],
)
def test_every_error_derives_from_charter_error(exc):
    assert isinstance(exc, CharterError)
    assert isinstance(exc, Exception)


def test_credential_error_carries_provider():
    err = CredentialError("token expired", provider="google", status_code=401)
    assert err.provider == "google"
    assert err.status_code == 401
    assert "google" in str(err)
    assert "token expired" in str(err)


def test_credential_error_without_provider_reads_plainly():
    assert str(CredentialError("no token configured")) == "no token configured"


def test_tool_validation_error_carries_structured_errors():
    err = ToolValidationError(
        "field 'to' is required", tool_name="gmail_send", errors=[{"loc": ["to"]}]
    )
    assert err.tool_name == "gmail_send"
    assert err.errors == [{"loc": ["to"]}]
    assert str(err) == "field 'to' is required"


def test_transform_error_names_the_field():
    err = TransformError("boom", transform="rfc822_base64", field="raw")
    assert err.transform == "rfc822_base64"
    assert "raw" in str(err)


def test_api_error_truncates_body_excerpt():
    err = APIError("upstream failed", status_code=502, body="x" * 5000, url="https://api/x")
    assert len(err.body) == 500
    assert err.status_code == 502
    assert "502" in str(err)
    assert "https://api/x" in str(err)


# -----------------------------------------------------
# Public surface
# -----------------------------------------------------


def test_top_level_package_reexports_the_type_system():
    for name in (
        "Path",
        "Query",
        "Body",
        "Format",
        "Mode",
        "Case",
        "EmailContent",
        "DocumentContent",
        "FileContent",
        "Value",
        "ListValue",
        "Struct",
        "FieldMask",
        "CharterError",
        "CredentialError",
        "ToolValidationError",
        "TransformError",
        "APIError",
    ):
        assert hasattr(charter, name), f"charter.{name} missing"
        assert name in charter.__all__


def test_package_has_a_version():
    assert charter.__version__ == "0.1.0"
