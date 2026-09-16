"""
The deterministic runtime: schema in, HTTP out.

- :mod:`~charter.execution.casing` — the key-case cascade
- :mod:`~charter.execution.http` — marker routing, the request, typed errors
- :mod:`~charter.execution.schema` — the mode-filtered, semantically-typed LLM view
- :mod:`~charter.execution.validation` — validation errors an LLM can act on
- :mod:`~charter.execution.executor` — the pipeline that ties them together
"""

from charter.execution.casing import DictKeyParser
from charter.execution.executor import ResponseHandler, ToolExecutor
from charter.execution.http import call_api
from charter.execution.schema import (
    LLMBase,
    SchemaStore,
    create_llm_schema,
    should_include_field,
)
from charter.execution.validation import format_validation_error, validate_input

__all__ = [
    "DictKeyParser",
    "ToolExecutor",
    "ResponseHandler",
    "call_api",
    "LLMBase",
    "SchemaStore",
    "create_llm_schema",
    "should_include_field",
    "format_validation_error",
    "validate_input",
]
