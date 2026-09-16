"""
Transform registry for converting between semantic types and wire formats.

A ``Format("name")`` marker on a schema field names one of these transforms. At
request time the runtime looks the name up here and runs it, so the LLM fills in
``EmailContent`` while the API receives the base64url RFC822 blob it asked for.
"""

from charter.transforms.registry import (
    TransformRegistry,
    TransformSpec,
    apply_transform,
    get_transform,
    register_transform,
)

__all__ = [
    "TransformRegistry",
    "TransformSpec",
    "register_transform",
    "get_transform",
    "apply_transform",
]
