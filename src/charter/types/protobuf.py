# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Pydantic models for Google's protobuf well-known types.

These mirror the standard ``google.protobuf`` well-known types (``Value``,
``ListValue``, ``Struct``, ``FieldMask``) as Pydantic ``BaseModel``s so they can
participate in:

  - LLM tool schema generation (``model_json_schema()``)
  - Runtime validation (``model_validator``)
  - The ``Format("proto_json")`` transform for wire-format conversion

The ``coerce_primitive`` validator on ``Value`` lets LLMs send plain JSON
primitives (``"hello"``, ``42``, ``true``, ``null``) which are automatically
promoted to the correct variant — no need to spell out
``{"string_value": "hello"}``.

API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from charter.types.errors import DeclarationError

__all__ = [
    "NullValue",
    "Struct",
    "ListValue",
    "Value",
    "FieldMask",
]


NullValue = Literal["NULL_VALUE"]


class Struct(BaseModel):
    """``Struct`` represents structured data: fields mapping to dynamically typed values.

    The JSON representation for ``Struct`` is a JSON object.

    API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/#struct
    """

    fields: Optional[Dict[str, Value]] = Field(
        default=None, description="Unordered map of dynamically typed values."
    )


class ListValue(BaseModel):
    """``ListValue`` is a wrapper around a repeated field of values.

    The JSON representation for ``ListValue`` is a JSON array.

    API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/#list-value
    """

    values: List[Value] = Field(..., description="Repeated field of dynamically typed values.")


class Value(BaseModel):
    """``Value`` represents a dynamically typed value.

    It can be either null, a number, a string, a boolean, a recursive struct value,
    or a list of values. A producer of value is expected to set one of these variants;
    absence of any variant indicates an error.

    The ``coerce_primitive`` validator accepts plain JSON primitives so the LLM can
    send ``"hello"`` instead of ``{"string_value": "hello"}``.

    API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/#value
    """

    null_value: Optional[NullValue] = Field(default=None, description="Represents a null value.")
    number_value: Optional[float] = Field(default=None, description="Represents a double value.")
    string_value: Optional[str] = Field(default=None, description="Represents a string value.")
    bool_value: Optional[bool] = Field(default=None, description="Represents a boolean value.")
    struct_value: Optional[Struct] = Field(
        default=None, description="Represents a structured value."
    )
    list_value: Optional[ListValue] = Field(
        default=None, description="Represents a repeated `Value`."
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_primitive(cls, v: Any) -> Any:
        """Allow plain JSON primitives in addition to the explicit variant struct."""
        if isinstance(v, bool):
            return {"bool_value": v}
        if isinstance(v, (int, float)):
            return {"number_value": float(v)}
        if isinstance(v, str):
            return {"string_value": v}
        if v is None:
            return {"null_value": "NULL_VALUE"}
        return v  # dict or Value instance — Pydantic handles normally

    @model_validator(mode="after")
    def check_one_variant(self) -> Value:
        variants = [
            self.null_value,
            self.number_value,
            self.string_value,
            self.bool_value,
            self.struct_value,
            self.list_value,
        ]
        if sum(v is not None for v in variants) != 1:
            # No `docs`, despite this being a declaration-shaped complaint: a
            # model fills a Value in, so this validator's message travels back
            # to the model inside a ToolValidationError. `Value` is the one
            # protobuf type that is model-facing rather than author-facing.
            raise DeclarationError("Value must have exactly one variant set.")
        return self


class FieldMask(BaseModel):
    """``FieldMask`` represents a set of symbolic field paths.

    The LLM provides a list of dot-separated field paths (``paths``). The
    ``Format("field_mask")`` transform serialises them to the JSON wire encoding:
    a single comma-separated camelCase string, e.g. ``"user.displayName,photo"``.

    The ``coerce_shorthand`` validator also accepts the compact wire-format string
    directly, splitting it back into paths.

    API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/#field-mask
    """

    paths: List[str] = Field(
        ...,
        description=(
            "The set of field mask paths. Each path is a dot-separated sequence "
            "of camelCase field names, e.g. 'userEnteredValue' or "
            "'userEnteredFormat.horizontalAlignment'."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_shorthand(cls, v: Any) -> Any:
        """Accept shorthand forms in addition to the canonical ``{"paths": [...]}`` dict.

        - list -> ``{"paths": v}``        e.g. ``["userEnteredValue", "name"]``
        - str  -> ``{"paths": [p, ...]}`` e.g. ``"userEnteredValue,name"``
        """
        if isinstance(v, list):
            return {"paths": v}
        if isinstance(v, str):
            return {"paths": [p.strip() for p in v.split(",") if p.strip()]}
        return v


Struct.model_rebuild()
ListValue.model_rebuild()
Value.model_rebuild()
