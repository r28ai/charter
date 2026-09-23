# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Validation errors an LLM can act on.

A raw Pydantic ``ValidationError`` is written for a developer reading a stack
trace. Handed back to a model as a tool result it is mostly noise, and the model
often retries with the same mistake. This module renders it as compact markdown
that names the field path, the problem, and what was actually sent.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Type

from pydantic import BaseModel, ValidationError

from charter.types.errors import ToolValidationError, strip_docs_links

__all__ = ["format_validation_error", "validate_input"]

_INPUT_EXCERPT = 80


def format_validation_error(error: ValidationError) -> str:
    """Render a ``ValidationError`` as compact markdown for LLM consumption.

    Pydantic's structured output already carries the field path, the message and
    the offending input; the input is truncated so a large payload the model
    already knows it sent does not flood the context.

    Documentation links are stripped from each message. A validator on a schema
    type the model fills in can raise a linked error, and pydantic quotes it
    verbatim — but the reader here is a model, which pays for the URL in context
    and cannot follow it. Stripping at the formatter covers the LangChain
    adapter too, which wires this in as ``handle_validation_error`` and never
    goes through :class:`~charter.types.errors.ToolValidationError`.
    """
    lines = []
    for err in error.errors():
        loc = ".".join(str(p) for p in err["loc"])
        msg = strip_docs_links(err["msg"])
        inp = err.get("input")
        # Skip showing input for model-level errors (loc is empty, input is the
        # whole kwargs dict — noisy and unhelpful for the LLM).
        if loc and not isinstance(inp, dict):
            raw = repr(inp)
            val = raw[:_INPUT_EXCERPT] + "..." if len(raw) > _INPUT_EXCERPT else raw
            suffix = f" (got {val})"
        else:
            suffix = ""
        label = loc if loc else "(input)"
        lines.append(f"- **{label}**: {msg}{suffix}")
    return "Validation error:\n" + "\n".join(lines)


def validate_input(
    schema: Type[BaseModel],
    args: Dict[str, Any],
    *,
    tool_name: Optional[str] = None,
) -> BaseModel:
    """Validate ``args`` against ``schema``.

    Raises:
        ToolValidationError: carrying the LLM-facing message and the structured
            per-field errors, so a host app can either hand the text straight
            back to the model or render its own.
    """
    try:
        return schema.model_validate(args)
    except ValidationError as exc:
        raise ToolValidationError(
            format_validation_error(exc),
            tool_name=tool_name,
            errors=[dict(e) for e in exc.errors()],
        ) from exc
