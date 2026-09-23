# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Transform registry for managing format transformations.

This module provides a centralized registry for all transformations between
semantic types (what LLMs see) and wire formats (what APIs expect).
"""

from __future__ import annotations

import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Callable, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from charter.types.errors import TransformError
from charter.types.protobuf import FieldMask
from charter.types.semantic import DocumentContent, EmailContent, FileContent

__all__ = [
    "TransformSpec",
    "TransformRegistry",
    "register_transform",
    "get_transform",
    "apply_transform",
]


# -----------------------------------------------------
# Transform Specification
# -----------------------------------------------------


class TransformSpec:
    """Specification for a transform between semantic and wire formats."""

    def __init__(
        self,
        name: str,
        semantic_type: type,
        transform_fn: Callable[[Any], Any],
        llm_description: Optional[str] = None,
    ) -> None:
        self.name = name
        self.semantic_type = semantic_type
        self.transform_fn = transform_fn
        self.llm_description = llm_description or f"{semantic_type.__name__} data"

    def __repr__(self) -> str:
        return f"TransformSpec({self.name!r} -> {self.semantic_type.__name__})"


# -----------------------------------------------------
# Transform Registry
# -----------------------------------------------------


class TransformRegistry:
    """Central registry for all format transformations."""

    _transforms: Dict[str, TransformSpec] = {}

    @classmethod
    def register(
        cls,
        name: str,
        semantic_type: type,
        llm_description: Optional[str] = None,
    ) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        """Decorator to register a transform function.

        Args:
            name: Unique name for the transform (e.g. ``"rfc822_base64"``).
            semantic_type: The type that LLMs will see for this field.
            llm_description: Optional description for LLM context.

        Example:
            >>> @TransformRegistry.register("rfc822_base64", EmailContent)
            ... def transform_email_to_rfc822(email: EmailContent) -> str:
            ...     ...
        """

        def decorator(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
            cls._transforms[name] = TransformSpec(
                name=name,
                semantic_type=semantic_type,
                transform_fn=func,
                llm_description=llm_description,
            )
            return func

        return decorator

    @classmethod
    def get(cls, name: str) -> Optional[TransformSpec]:
        """Get a transform spec by name, or ``None`` when it is not registered."""
        return cls._transforms.get(name)

    @classmethod
    def names(cls) -> list[str]:
        """Every registered transform name, sorted."""
        return sorted(cls._transforms)

    @classmethod
    def apply(cls, name: str, value: Any) -> Any:
        """Apply a named transform to a value.

        When the value is a dict and the registered semantic type is a ``BaseModel``,
        the dict is automatically coerced into the model instance before the transform
        function runs. This is needed because the auto-transformer calls
        ``model_dump()`` on the LLM input, so complex semantic types (e.g.
        ``EmailContent``) arrive as plain dicts rather than model instances.

        Raises:
            TransformError: if ``name`` is not registered, if the value cannot be
                coerced into the transform's semantic type, or if the transform
                function itself raises.
        """
        spec = cls.get(name)
        if spec is None:
            known = ", ".join(cls.names()) or "<none registered>"
            raise TransformError(
                f"Unknown transform: {name!r}. Registered transforms: {known}",
                transform=name,
                docs="tools/transforms#registering-your-own",
            )

        # Auto-coerce dict -> semantic model (from model_dump output).
        #
        # `spec.semantic_type is not BaseModel` matters: a transform registered
        # against bare BaseModel (proto_json) accepts *any* protobuf shape, and
        # BaseModel has no fields, so coercing would silently discard the payload.
        if (
            isinstance(value, dict)
            and isinstance(spec.semantic_type, type)
            and issubclass(spec.semantic_type, BaseModel)
            and spec.semantic_type is not BaseModel
        ):
            try:
                value = spec.semantic_type(**value)
            except ValidationError as exc:
                raise TransformError(
                    f"Transform {name!r} expects {spec.semantic_type.__name__}, but the "
                    f"value did not validate: {exc}",
                    transform=name,
                    docs="reference/semantic-types",
                ) from exc

        try:
            return spec.transform_fn(value)
        except TransformError:
            raise
        except Exception as exc:
            raise TransformError(f"Transform {name!r} failed: {exc}", transform=name) from exc


# -----------------------------------------------------
# Email Transforms
# -----------------------------------------------------


@TransformRegistry.register("rfc822_base64", EmailContent, "Email message content")
def transform_email_to_rfc822_base64(email: EmailContent) -> str:
    """Transform ``EmailContent`` to RFC822 format, base64url encoded.

    This is used for the Gmail API and other email services that expect RFC822
    formatted messages. Supports plain text, HTML, and multipart/alternative.
    """
    # Build message body: multipart/alternative if both body and bodyHtml, else single part
    msg: MIMEText | MIMEMultipart
    if email.bodyHtml:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(email.body, "plain", "utf-8"))
        msg.attach(MIMEText(email.bodyHtml, "html", "utf-8"))
    elif email.mimeType == "text/html":
        msg = MIMEText(email.body, "html", "utf-8")
    else:
        msg = MIMEText(email.body, "plain", "utf-8")

    # Set headers
    if isinstance(email.to, list):
        msg["To"] = ", ".join(email.to)
    else:
        msg["To"] = email.to

    msg["Subject"] = email.subject

    # Optional headers
    if email.from_:
        msg["From"] = email.from_

    if email.cc:
        if isinstance(email.cc, list):
            msg["Cc"] = ", ".join(email.cc)
        else:
            msg["Cc"] = email.cc

    if email.bcc:
        if isinstance(email.bcc, list):
            msg["Bcc"] = ", ".join(email.bcc)
        else:
            msg["Bcc"] = email.bcc

    if email.reply_to:
        msg["Reply-To"] = email.reply_to

    # Threading headers (RFC 2822 standard)
    if email.in_reply_to:
        msg["In-Reply-To"] = email.in_reply_to

    if email.references:
        msg["References"] = email.references

    # Convert to RFC822 string
    rfc822_string = msg.as_string()

    # Encode to base64url (Gmail requirement)
    encoded = base64.urlsafe_b64encode(rfc822_string.encode("utf-8")).decode("utf-8")
    # Remove padding for URL safety
    return encoded.rstrip("=")


@TransformRegistry.register("email_json", EmailContent, "Email message as JSON")
def transform_email_to_json(email: EmailContent) -> dict:
    """Transform ``EmailContent`` to JSON format.

    Used for modern email APIs that accept JSON payloads (e.g. SendGrid).
    """
    return email.model_dump(exclude_none=True, by_alias=True)


# -----------------------------------------------------
# Basic Encoding Transforms
# -----------------------------------------------------
#
# Transform naming conventions:
#   - "base64":    Standard base64 encoding (with padding)
#   - "base64url": URL-safe base64 encoding (no padding)
#   - "bytes":     Google API "bytes" format (same as base64url)
#
# Note: "bytes" and "base64url" use identical encoding. The separate transform
# exists for semantic clarity when working with Google APIs that use the "bytes"
# type annotation in their schemas.
# -----------------------------------------------------


@TransformRegistry.register("base64", str, "Plain text content")
def transform_to_base64(value: str) -> str:
    """Transform string to base64 encoding."""
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


@TransformRegistry.register("base64url", str, "Plain text content")
def transform_to_base64url(value: str) -> str:
    """Transform string to base64url encoding (URL-safe)."""
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


@TransformRegistry.register("bytes", str, "Binary data as text")
def transform_to_bytes(value: str) -> str:
    """Transform string to bytes format (base64url encoded).

    This is used for Google API fields that have the "bytes" type in their schemas,
    such as Gmail's raw message field. Functionally identical to base64url encoding,
    but provides semantic clarity when working with Google API specifications.

    Examples:
        - Gmail ``message.raw`` field (RFC822 message as bytes)
        - File attachment data in various Google APIs
    """
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("utf-8").rstrip("=")


@TransformRegistry.register("json_base64", dict, "JSON data")
def transform_json_to_base64(value: dict) -> str:
    """Transform JSON to a base64 encoded string."""
    json_str = json.dumps(value, separators=(",", ":"))
    return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")


# -----------------------------------------------------
# File Transforms
# -----------------------------------------------------


@TransformRegistry.register("file_base64", FileContent, "File content")
def transform_file_to_base64(file: FileContent) -> str:
    """Transform ``FileContent`` to a base64 encoded string."""
    return base64.b64encode(file.content.encode("utf-8")).decode("utf-8")


# -----------------------------------------------------
# Document Transforms
# -----------------------------------------------------


@TransformRegistry.register("document_json", DocumentContent, "Document content")
def transform_document_to_json(doc: DocumentContent) -> dict:
    """Transform ``DocumentContent`` to JSON."""
    return doc.model_dump(exclude_none=True)


# -----------------------------------------------------
# Protobuf JSON Transforms
# -----------------------------------------------------


def _proto_value_to_json(value: Any) -> Any:
    """Recursively convert a dumped protobuf ``Value`` struct to its JSON wire form.

    Protobuf's JSON encoding spec maps ``google.protobuf.Value`` to a plain JSON
    primitive — not the ``{"string_value": "..."}`` struct representation. This
    transform bridges the two so that the LLM can use strict Pydantic types
    (``Value``, ``ListValue``, ``Struct``) while the wire format is correct JSON.

    Handles:
      - list / nested list -> recurses into each element
      - ``Value`` dict     -> extracts the active variant as a JSON primitive
      - ``ListValue`` dict -> converts to a JSON array
      - ``Struct`` dict    -> converts to a JSON object
      - bare primitive     -> passes through unchanged
    """
    if isinstance(value, list):
        return [_proto_value_to_json(v) for v in value]
    if isinstance(value, dict):
        if "string_value" in value:
            return value["string_value"]
        if "number_value" in value:
            return value["number_value"]
        if "bool_value" in value:
            return value["bool_value"]
        if "null_value" in value:
            return None
        if "list_value" in value:
            inner = value["list_value"] or {}
            return [_proto_value_to_json(v) for v in inner.get("values", [])]
        if "struct_value" in value:
            inner = value["struct_value"] or {}
            return {k: _proto_value_to_json(v) for k, v in inner.get("fields", {}).items()}
    return value


@TransformRegistry.register("field_mask", FieldMask, "Field mask paths")
def transform_field_mask(mask: FieldMask) -> str:
    """Transform a ``FieldMask`` to its JSON wire encoding.

    Per the protobuf JSON spec, ``FieldMask { paths: ["user.displayName", "photo"] }``
    encodes as the string ``"user.displayName,photo"``.

    API Reference: https://protobuf.dev/reference/protobuf/google.protobuf/#field-mask
    """
    return ",".join(mask.paths)


@TransformRegistry.register("proto_json", BaseModel, "Protobuf value encoded as JSON primitive")
def transform_proto_json(value: Any) -> Any:
    """Transform any protobuf ``Value``/``ListValue``/``Struct`` to its JSON wire format.

    Register this on fields typed as ``Value``, ``List[Value]``, ``List[List[Value]]``,
    etc. The LLM provides data using strict Pydantic types; this transform converts
    them to plain JSON primitives before the HTTP request is sent.

    Example:
        >>> values: Annotated[
        ...     Optional[List[List[Value]]],
        ...     Format("proto_json"),
        ...     Field(default=None, description="..."),
        ... ]
    """
    return _proto_value_to_json(value)


# -----------------------------------------------------
# Helper Functions
# -----------------------------------------------------


def register_transform(
    name: str,
    semantic_type: Type[Any],
    transform_fn: Callable[[Any], Any],
    llm_description: Optional[str] = None,
) -> None:
    """Register a transform programmatically (non-decorator).

    Args:
        name: Unique name for the transform.
        semantic_type: The semantic type LLMs see for this field.
        transform_fn: The transformation function.
        llm_description: Optional description for LLMs.
    """
    TransformRegistry._transforms[name] = TransformSpec(
        name=name,
        semantic_type=semantic_type,
        transform_fn=transform_fn,
        llm_description=llm_description,
    )


def get_transform(name: str) -> Optional[TransformSpec]:
    """Get a transform spec by name."""
    return TransformRegistry.get(name)


def apply_transform(name: str, value: Any) -> Any:
    """Apply a named transform to a value."""
    return TransformRegistry.apply(name, value)
