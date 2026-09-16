"""R2 — the transform registry and its built-ins."""

from __future__ import annotations

import base64
import email
import json
from typing import Annotated, List, Optional

import httpx
import pytest
import respx
from pydantic import BaseModel, Field

from charter.transforms import (
    TransformRegistry,
    TransformSpec,
    apply_transform,
    get_transform,
    register_transform,
)
from charter.types import (
    DocumentContent,
    EmailContent,
    FieldMask,
    FileContent,
    Format,
    ListValue,
    Struct,
    TransformError,
    Value,
)

BUILTINS = {
    "rfc822_base64",
    "email_json",
    "base64",
    "base64url",
    "bytes",
    "json_base64",
    "file_base64",
    "document_json",
    "field_mask",
    "proto_json",
}


def _decode_b64url(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8")


# -----------------------------------------------------
# Registry behaviour
# -----------------------------------------------------


def test_every_builtin_transform_is_registered():
    assert BUILTINS <= set(TransformRegistry.names())


@pytest.mark.parametrize("name", sorted(BUILTINS))
def test_get_transform_returns_a_spec(name):
    spec = get_transform(name)
    assert isinstance(spec, TransformSpec)
    assert spec.name == name
    assert spec.llm_description


def test_unknown_transform_name_raises_transform_error():
    """Accept (R2): an unregistered name is a TransformError, not a bare ValueError."""
    with pytest.raises(TransformError) as excinfo:
        apply_transform("does_not_exist", "x")

    err = excinfo.value
    assert err.transform == "does_not_exist"
    assert "does_not_exist" in str(err)
    # The message lists what *is* available, so the failure is self-diagnosing.
    assert "rfc822_base64" in str(err)


def test_get_transform_returns_none_for_unknown_name():
    assert get_transform("does_not_exist") is None


def test_transform_failure_is_wrapped_in_transform_error():
    def explode(value):
        raise RuntimeError("kaboom")

    register_transform("test_explode", str, explode)
    try:
        with pytest.raises(TransformError) as excinfo:
            apply_transform("test_explode", "x")
        assert "kaboom" in str(excinfo.value)
        assert excinfo.value.transform == "test_explode"
    finally:
        TransformRegistry._transforms.pop("test_explode", None)


def test_bad_semantic_payload_raises_transform_error():
    """A dict that will not validate as the semantic type fails loudly."""
    with pytest.raises(TransformError) as excinfo:
        apply_transform("rfc822_base64", {"subject": "no recipient"})

    assert "EmailContent" in str(excinfo.value)


def test_register_transform_programmatically():
    register_transform("test_shout", str, lambda v: v.upper(), "Shouty text")
    try:
        assert apply_transform("test_shout", "hi") == "HI"
        spec = get_transform("test_shout")
        assert spec is not None and spec.llm_description == "Shouty text"
    finally:
        TransformRegistry._transforms.pop("test_shout", None)


def test_decorator_registration():
    @TransformRegistry.register("test_decorated", str)
    def _t(value: str) -> str:
        return value[::-1]

    try:
        assert apply_transform("test_decorated", "abc") == "cba"
        # The decorator returns the original function unwrapped.
        assert _t("abc") == "cba"
    finally:
        TransformRegistry._transforms.pop("test_decorated", None)


# -----------------------------------------------------
# rfc822_base64 — the flagship path
# -----------------------------------------------------


def test_rfc822_base64_round_trip_shape():
    """Accept (R2): EmailContent -> rfc822_base64 decodes back to a real RFC822 message."""
    content = EmailContent(
        to="ada@example.com",
        subject="Hello",
        body="Plain body",
        cc=["cc1@example.com", "cc2@example.com"],
        bcc="bcc@example.com",
        from_="me@example.com",
        reply_to="reply@example.com",
        in_reply_to="<parent@example.com>",
        references="<root@example.com> <parent@example.com>",
    )

    encoded = apply_transform("rfc822_base64", content)

    # base64url, unpadded — Gmail's requirement.
    assert isinstance(encoded, str)
    assert "=" not in encoded
    assert "+" not in encoded and "/" not in encoded

    msg = email.message_from_string(_decode_b64url(encoded))
    assert msg["To"] == "ada@example.com"
    assert msg["Subject"] == "Hello"
    assert msg["Cc"] == "cc1@example.com, cc2@example.com"
    assert msg["Bcc"] == "bcc@example.com"
    assert msg["From"] == "me@example.com"
    assert msg["Reply-To"] == "reply@example.com"
    assert msg["In-Reply-To"] == "<parent@example.com>"
    assert msg["References"] == "<root@example.com> <parent@example.com>"
    assert msg.get_content_type() == "text/plain"
    assert "Plain body" in msg.get_payload(decode=True).decode()


def test_rfc822_base64_accepts_a_plain_dict():
    """The executor dumps models to dicts — apply() must coerce them back."""
    encoded = apply_transform(
        "rfc822_base64", {"to": "a@b.com", "subject": "S", "body": "B"}
    )
    msg = email.message_from_string(_decode_b64url(encoded))
    assert msg["To"] == "a@b.com"


def test_rfc822_base64_joins_list_recipients():
    encoded = apply_transform(
        "rfc822_base64",
        EmailContent(to=["a@b.com", "c@d.com"], subject="S", body="B"),
    )
    msg = email.message_from_string(_decode_b64url(encoded))
    assert msg["To"] == "a@b.com, c@d.com"


def test_rfc822_base64_html_only():
    encoded = apply_transform(
        "rfc822_base64",
        EmailContent(to="a@b.com", subject="S", body="<b>hi</b>", mimeType="text/html"),
    )
    msg = email.message_from_string(_decode_b64url(encoded))
    assert msg.get_content_type() == "text/html"
    assert not msg.is_multipart()


def test_rfc822_base64_multipart_alternative():
    encoded = apply_transform(
        "rfc822_base64",
        EmailContent(to="a@b.com", subject="S", body="plain", bodyHtml="<b>rich</b>"),
    )
    msg = email.message_from_string(_decode_b64url(encoded))

    assert msg.is_multipart()
    assert msg.get_content_type() == "multipart/alternative"
    parts = msg.get_payload()
    assert [p.get_content_type() for p in parts] == ["text/plain", "text/html"]
    assert "plain" in parts[0].get_payload(decode=True).decode()
    assert "<b>rich</b>" in parts[1].get_payload(decode=True).decode()


def test_rfc822_base64_omits_absent_optional_headers():
    encoded = apply_transform(
        "rfc822_base64", EmailContent(to="a@b.com", subject="S", body="B")
    )
    msg = email.message_from_string(_decode_b64url(encoded))
    assert msg["Cc"] is None
    assert msg["Bcc"] is None
    assert msg["From"] is None
    assert msg["In-Reply-To"] is None


def test_rfc822_base64_survives_unicode():
    encoded = apply_transform(
        "rfc822_base64", EmailContent(to="a@b.com", subject="S", body="héllo — 🌍")
    )
    msg = email.message_from_string(_decode_b64url(encoded))
    assert "héllo — 🌍" in msg.get_payload(decode=True).decode("utf-8")


def test_email_json_uses_wire_aliases():
    out = apply_transform(
        "email_json",
        EmailContent(to="a@b.com", subject="S", body="B", from_="me@x.com"),
    )
    assert out["from"] == "me@x.com"
    assert "from_" not in out
    # exclude_none drops the unset optionals.
    assert "cc" not in out


# -----------------------------------------------------
# Encoding transforms
# -----------------------------------------------------


def test_base64_is_padded_standard_alphabet():
    assert apply_transform("base64", "hello") == base64.b64encode(b"hello").decode()


def test_base64url_is_unpadded_url_safe():
    raw = "??>>??"  # encodes to bytes containing + and / in the standard alphabet
    out = apply_transform("base64url", raw)
    assert "=" not in out
    assert _decode_b64url(out) == raw


def test_bytes_matches_base64url():
    """'bytes' exists for semantic clarity; encoding must stay identical."""
    for sample in ("hello", "??>>??", "héllo"):
        assert apply_transform("bytes", sample) == apply_transform("base64url", sample)


def test_json_base64_is_compact():
    out = apply_transform("json_base64", {"a": 1, "b": [1, 2]})
    decoded = base64.b64decode(out).decode()
    assert decoded == '{"a":1,"b":[1,2]}'  # no whitespace
    assert json.loads(decoded) == {"a": 1, "b": [1, 2]}


def test_file_base64():
    out = apply_transform("file_base64", FileContent(filename="a.txt", content="hello"))
    assert base64.b64decode(out).decode() == "hello"


def test_file_base64_accepts_dict():
    out = apply_transform("file_base64", {"filename": "a.txt", "content": "hello"})
    assert base64.b64decode(out).decode() == "hello"


def test_document_json_drops_none_fields():
    out = apply_transform("document_json", DocumentContent(title="T", content="C"))
    assert out == {"title": "T", "content": "C"}


# -----------------------------------------------------
# Protobuf transforms
# -----------------------------------------------------


@pytest.mark.parametrize(
    ("primitive", "expected"),
    [("hello", "hello"), (42, 42.0), (True, True), (False, False), (None, None)],
)
def test_proto_json_unwraps_a_value_to_a_json_primitive(primitive, expected):
    """Accept (R2): plain JSON -> protobuf Value coercion -> plain JSON again."""
    value = Value.model_validate(primitive)
    dumped = value.model_dump(exclude_none=True, mode="json")
    assert apply_transform("proto_json", dumped) == expected


def test_proto_json_handles_a_matrix_of_values():
    """The Sheets shape: List[List[Value]] -> a plain 2-D JSON array."""
    rows = [["Name", "Score"], ["Ada", 99]]
    dumped = [
        [Value.model_validate(cell).model_dump(exclude_none=True, mode="json") for cell in row]
        for row in rows
    ]
    assert apply_transform("proto_json", dumped) == [["Name", "Score"], ["Ada", 99.0]]


def test_proto_json_unwraps_list_value():
    lv = ListValue.model_validate({"values": ["a", 1]})
    dumped = {"list_value": lv.model_dump(exclude_none=True, mode="json")}
    assert apply_transform("proto_json", dumped) == ["a", 1.0]


def test_proto_json_unwraps_struct_value():
    struct = Struct.model_validate({"fields": {"name": "Ada", "ok": True}})
    dumped = {"struct_value": struct.model_dump(exclude_none=True, mode="json")}
    assert apply_transform("proto_json", dumped) == {"name": "Ada", "ok": True}


def test_proto_json_recurses_through_nested_structs():
    struct = Struct.model_validate({"fields": {"outer": {"struct_value": {"fields": {"inner": 1}}}}})
    dumped = {"struct_value": struct.model_dump(exclude_none=True, mode="json")}
    assert apply_transform("proto_json", dumped) == {"outer": {"inner": 1.0}}


def test_proto_json_passes_bare_primitives_through():
    assert apply_transform("proto_json", "already plain") == "already plain"
    assert apply_transform("proto_json", 7) == 7


def test_proto_json_maps_null_value_to_none():
    dumped = Value.model_validate(None).model_dump(exclude_none=True, mode="json")
    assert apply_transform("proto_json", dumped) is None


def test_field_mask_serialises_to_a_comma_joined_string():
    assert apply_transform("field_mask", FieldMask(paths=["user.displayName", "photo"])) == (
        "user.displayName,photo"
    )


def test_field_mask_accepts_shorthand_dict():
    assert apply_transform("field_mask", {"paths": ["a", "b"]}) == "a,b"


# -----------------------------------------------------
# Transforms declared on a schema
# -----------------------------------------------------


def test_format_marker_names_a_registered_transform():
    """Every Format marker in a schema must resolve against the registry."""

    class GmailSendSchema(BaseModel):
        raw: Annotated[EmailContent, Format("rfc822_base64")]
        values: Annotated[Optional[List[List[Value]]], Format("proto_json")] = Field(default=None)

    for field in GmailSendSchema.model_fields.values():
        for meta in field.metadata:
            if isinstance(meta, Format):
                assert get_transform(meta.transform) is not None, meta.transform


# -----------------------------------------------------
# Where a transformed field goes when it is not alone
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_transformed_body_field_does_not_swallow_its_siblings():
    """A single Body() field *is* the body, so its transformed value replaces the
    body outright — that is how Gmail's `raw` becomes the whole request. With
    several Body() fields the body is a mapping, and replacing it with one
    field's value drops the rest.

    Nothing caught this for twelve packs because every Format in every pack sat
    on a nested model field, where the transform mutates in place. The first
    top-level Format beside other Body() fields sent the API one base64 string
    and no commit message.
    """

    from pydantic import BaseModel

    from charter import Body, Path, api_key_tool_factory

    class WriteFile(BaseModel):
        path: Annotated[str, Field(...), Path()]
        message: Annotated[str, Field(...), Body()]
        content: Annotated[str, Field(...), Format("base64"), Body()]
        branch: Annotated[Optional[str], Field(None), Body()] = None

    factory = api_key_tool_factory(
        base_url="https://api.example.com/", api_key_headers={"x-api-key": "k"}
    )
    write = factory(
        name="write_file", args_schema=WriteFile, method="PUT",
        url_template="contents/{path}",
    )

    route = respx.put("https://api.example.com/contents/a.txt").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await write.ainvoke({"path": "a.txt", "message": "commit", "content": "hello"})

    body = json.loads(route.calls.last.request.content)
    assert body == {"message": "commit", "content": base64.b64encode(b"hello").decode()}


@pytest.mark.asyncio
@respx.mock
async def test_a_lone_transformed_scalar_body_field_keeps_its_name():
    """A lone Body() field unwraps only when its value is a structure.

    This used to send the bare base64 string as the whole JSON document, on the
    reading that "a single Body field *is* the body". A scalar has no fields to
    promote, and no API asks for one: Gmail — the case that reading was written
    for — wants ``{"raw": "..."}``, and its pack declares `raw` inside a nested
    Message model rather than at the top level, so it never took this path. Five
    tools in three packs did, and none of them could run.
    """

    from pydantic import BaseModel

    from charter import Body, api_key_tool_factory

    class SendRaw(BaseModel):
        raw: Annotated[str, Field(...), Format("base64"), Body()]

    factory = api_key_tool_factory(
        base_url="https://api.example.com/", api_key_headers={"x-api-key": "k"}
    )
    send = factory(name="send", args_schema=SendRaw, method="POST", url_template="send")

    route = respx.post("https://api.example.com/send").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await send.ainvoke({"raw": "hello"})

    assert json.loads(route.calls.last.request.content) == {
        "raw": base64.b64encode(b"hello").decode()
    }
