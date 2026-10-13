# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Routes — one operation an API serves at more than one path.

Microsoft Graph lists a user's messages at ``/me/messages`` and a folder's at
``/me/mailFolders/{id}/messages``: one operation, one set of parameters, one
response, and the extra segment only narrows the collection. GitLab does the
same with ``/issues``, ``/projects/:id/issues`` and ``/groups/:id/issues``.
Declared as two tools, the model has to choose between near-identical
functions, which is choosing a URL; declared as one with an optional
``folder_id``, it makes the decision it makes for any filter, and the runtime
chooses the URL.

So a tool's ``url_template`` may be a sequence of templates, most specific
first, and a call goes to the first one whose placeholders all have values::

    url_template=("me/mailFolders/{folder_id}/messages", "me/messages")

Nothing about this reaches the model. The schema it is given has an optional
``folder_id`` like any optional parameter, and no adapter reads a URL.

A sequence is checked when the tool is built, so a declaration that cannot do
what it says fails at its own line: every placeholder is a ``Path`` field, the
last route can always be filled, and no route is shadowed by an earlier one
that would win every time it could.
"""

from __future__ import annotations

from string import Formatter
from typing import Any, Mapping, Sequence, Tuple, Type, Union

from pydantic import BaseModel

from charter.types.errors import DeclarationError
from charter.types.markers import Path, WireName

__all__ = ["UrlTemplate", "check_routes", "choose_route", "placeholders", "routes_of"]

UrlTemplate = Union[str, Sequence[str]]
"""One URL template, or several for one operation — see :mod:`charter.execution.routes`."""

_DOCS = "tools/wire-contract#routes"


def routes_of(url_template: UrlTemplate) -> Tuple[str, ...]:
    """``url_template`` as a tuple of templates, most specific first."""
    if isinstance(url_template, str):
        return (url_template,)
    routes = tuple(url_template)
    if not routes or not all(isinstance(route, str) for route in routes):
        raise DeclarationError(
            "url_template takes a template, or a non-empty sequence of templates "
            f"most specific first; got {url_template!r}.",
            docs=_DOCS,
        )
    return routes


def placeholders(template: str) -> Tuple[str, ...]:
    """The ``{names}`` a template interpolates, in order."""
    return tuple(field for _, field, _, _ in Formatter().parse(template) if field)


def choose_route(routes: Sequence[str], filled: Mapping[str, Any]) -> str:
    """The first route every placeholder of which ``filled`` has a value for.

    Falls back to the last route, whose missing placeholder then raises the
    ordinary "missing path parameter" error when it is formatted — which
    :func:`check_routes` makes unreachable for a declared sequence.
    """
    for route in routes:
        if all(name in filled for name in placeholders(route)):
            return route
    return routes[-1]


def check_routes(
    routes: Sequence[str],
    schema: Type[BaseModel],
    path_case: str,
    tool_name: str,
) -> None:
    """Refuse a sequence of routes that cannot do what it declares.

    A single template is the long-standing shape and is not checked here: it is
    the pack test suites' job, and existing tools built by hand rely on it.
    """
    if len(routes) < 2:
        return

    from charter.execution.casing import DictKeyParser

    path_fields = {}
    for name, field in schema.model_fields.items():
        if not any(isinstance(m, Path) for m in field.metadata):
            continue
        wire = next((m.name for m in field.metadata if isinstance(m, WireName)), None)
        always = field.is_required() or field.default is not None
        path_fields[wire or DictKeyParser.convert_key(name, path_case)] = (name, always)

    used = set()
    for route in routes:
        for placeholder in placeholders(route):
            if placeholder not in path_fields:
                raise DeclarationError(
                    f"Tool {tool_name!r}: route {route!r} names {{{placeholder}}}, which is "
                    f"not a Path() field of {schema.__name__}.",
                    docs=_DOCS,
                )
            used.add(placeholder)

    unused = sorted(set(path_fields) - used)
    if unused:
        raise DeclarationError(
            f"Tool {tool_name!r}: Path() fields {unused} appear in none of its routes.",
            docs=_DOCS,
        )

    for later, route in enumerate(routes):
        needed = set(placeholders(route))
        for earlier in routes[:later]:
            if set(placeholders(earlier)) <= needed:
                raise DeclarationError(
                    f"Tool {tool_name!r}: route {route!r} can never be chosen, because "
                    f"{earlier!r} comes first and is filled whenever it is. List routes "
                    "most specific first.",
                    docs=_DOCS,
                )

    last = routes[-1]
    optional = [p for p in placeholders(last) if not path_fields[p][1]]
    if optional:
        raise DeclarationError(
            f"Tool {tool_name!r}: its last route {last!r} needs {optional}, which a call "
            "may leave out, so some calls would have no route. End with a route every "
            "call can fill.",
            docs=_DOCS,
        )
