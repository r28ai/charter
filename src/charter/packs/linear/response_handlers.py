# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Linear response unwrapping.

A GraphQL response is two layers of envelope before anything useful: the
``data`` key the spec mandates, then the name of the operation you asked for.
``{"data": {"issues": {"nodes": [...], "pageInfo": {...}}}}`` is three levels of
indirection around a list.

These handlers strip the two layers that carry no information and stop there.
What they must *not* strip is ``pageInfo``: it is the cursor, and the pagination
this pack declares reads it back out of the trimmed payload.

Failure detection is deliberately **not** here. Linear reports a declined
mutation as ``{"success": false}`` inside a valid ``data``, with no ``errors``
array — but that is a fact about the API, not about any one tool, so it is
declared once as :data:`~charter.packs.linear.LINEAR_ENVELOPE` and enforced by the
runtime on every call. Writing it into each mutation's handler instead would put
it back where it was: opt-in per tool, and wrong the first time somebody adds a
mutation without remembering.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["unwrap", "unwrap_mutation"]


def _strip(operation: str, response: Any) -> Any:
    """``{"data": {"<operation>": X}}`` -> ``X``."""
    if not isinstance(response, dict):
        return response
    data = response.get("data")
    if not isinstance(data, dict):
        return response
    if operation not in data:
        return data
    return data[operation]


def unwrap(operation: str) -> Callable[[Any], Any]:
    """Strip ``data`` and the operation name from a GraphQL response.

    ``pageInfo`` is deliberately preserved: it is where the cursor lives.
    """

    async def handler(response: Any) -> Any:
        return _strip(operation, response)

    return handler


def unwrap_mutation(operation: str) -> Callable[[Any], Any]:
    """Unwrap a mutation payload.

    The envelope has already raised if ``success`` was false, so anything
    reaching here succeeded — which means the flag has said all it has to say and
    is noise in the model's context.
    """

    async def handler(response: Any) -> Any:
        payload = _strip(operation, response)
        if not isinstance(payload, dict):
            return payload
        return {k: v for k, v in payload.items() if k != "success"}

    return handler
