"""
Pagination — where an API keeps its place in a list.

Almost every list endpoint paginates, and almost every API puts the marker
somewhere different: Slack in ``response_metadata.next_cursor``, Google in
``nextPageToken``, Notion in ``next_cursor``, Stripe in ``has_more`` plus the last
object's id. The concept is universal; the location never is.

Two *styles* cover the field, and a ``Pagination`` declares exactly one:

- **Cursor** — the API hands back an opaque token (or, for Stripe, the last
  object's id) that you send on the next call. Declare ``cursor_field`` and
  ``cursor_param``.
- **Page number** — there is no token; you ask for page 1, 2, 3 and stop when a
  page comes back short. GitHub works this way. Declare ``page_param`` and
  ``per_page_param``, with ``items_field`` naming where the array lives
  (``None`` when the body *is* the array, as GitHub's list endpoints are).

Declaring it means a caller can page without knowing the convention, and a
response handler that trims a payload can keep the cursor without re-deriving
where it lives.

This declares *where the marker is*. It does not loop — following pages is
orchestration, and orchestration stays in your agent. See "What this can't
express" in the README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from charter.types.errors import DeclarationError

__all__ = ["Pagination"]


_SEGMENT = re.compile(r"^([^\[\]]+)((?:\[-?\d+\])*)$")


def _parse_path(path: str) -> List[tuple]:
    """``"data[-1].id"`` -> ``[("data", [-1]), ("id", [])]``."""
    parsed: List[tuple] = []
    for segment in path.split("."):
        match = _SEGMENT.match(segment)
        if not match:
            raise DeclarationError(f"Malformed cursor path segment: {segment!r}")
        key, brackets = match.groups()
        indices = [int(i) for i in re.findall(r"\[(-?\d+)\]", brackets)]
        parsed.append((key, indices))
    return parsed


def _set_path(args: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    """Set ``path`` on ``args``, creating and copying nested dicts as it goes.

    ``"after"`` sets a top-level argument; ``"variables.after"`` reaches into a
    nested one, which is where a GraphQL API keeps its cursor. Intermediate
    dicts are copied rather than mutated, so the caller's previous page
    arguments are left untouched.
    """
    head, _, rest = path.partition(".")
    if not rest:
        args[head] = value
        return args
    nested = args.get(head)
    args[head] = _set_path(dict(nested) if isinstance(nested, dict) else {}, rest, value)
    return args


@dataclass(frozen=True)
class Pagination:
    """How one API reports that there is another page.

    Declare either the cursor fields or the page-number fields, never both.

    Attributes
    ----------
    cursor_field:
        Path to the next cursor in the response. Dotted for nesting, with
        optional list indices: ``"response_metadata.next_cursor"``,
        ``"nextPageToken"``, or ``"data[-1].id"`` for APIs like Stripe whose
        cursor is the last returned object's id rather than a token they hand
        back.
    cursor_param:
        Name of the request field that carries the cursor back, e.g. ``"cursor"``
        or ``"pageToken"``. Must be a field on the tool's schema. May be dotted
        to reach into a nested argument — a GraphQL tool carries its cursor at
        ``"variables.after"``, because that is where the wire puts it.
    more_field:
        Optional boolean field that says another page exists, e.g. ``"has_more"``
        or, for a Relay connection, ``"pageInfo.hasNextPage"``. Dotted like
        ``cursor_field``. When absent, a non-empty cursor is the signal — which
        is wrong for any API that returns a cursor on its last page, so declare
        this whenever the API offers it.
    page_param:
        Page-number style: the request field holding the 1-based page number,
        e.g. ``"page"``. Must be a field on the tool's schema.
    per_page_param:
        Page-number style: the request field holding the page size, e.g.
        ``"per_page"``. Used to tell a full page from the last one.
    items_field:
        Page-number style: where the returned array lives, e.g. ``"items"`` for
        GitHub's search endpoints. ``None`` means the response body *is* the
        array, which is how GitHub's plain list endpoints answer.
    max_items:
        The most results the API will serve for one query, when it serves fewer
        than it will count. GitHub's search reports ``total_count: 24207`` and
        then refuses anything past the first 1,000 matches. Without this, the
        walk keeps saying "another page" right up to the wall and the *next*
        call is the one that fails — so the loop in :meth:`next_page_args` ends
        by raising rather than by finishing. Declared here, the wall is where
        the walk stops.
    """

    cursor_field: Optional[str] = None
    cursor_param: Optional[str] = None
    more_field: Optional[str] = None
    page_param: Optional[str] = None
    per_page_param: Optional[str] = None
    items_field: Optional[str] = None
    max_items: Optional[int] = None

    def __post_init__(self) -> None:
        is_cursor = bool(self.cursor_field or self.cursor_param)
        is_page = bool(self.page_param or self.per_page_param)

        if is_cursor and is_page:
            raise DeclarationError(
                "A Pagination declares one style, not both: cursor "
                "(cursor_field/cursor_param) or page number "
                "(page_param/per_page_param).",
                docs="reference/envelopes-and-pagination#pagination",
            )
        if not is_cursor and not is_page:
            raise DeclarationError(
                "A Pagination needs either cursor_field + cursor_param, or "
                "page_param + per_page_param — otherwise it names no marker.",
                docs="reference/envelopes-and-pagination#pagination",
            )
        if is_cursor and not (self.cursor_field and self.cursor_param):
            raise DeclarationError(
                "Cursor pagination needs both cursor_field (where the cursor is "
                "in the response) and cursor_param (the request field it goes back in).",
                docs="reference/envelopes-and-pagination#pagination",
            )
        if is_page and not (self.page_param and self.per_page_param):
            raise DeclarationError(
                "Page-number pagination needs both page_param and per_page_param — "
                "without the page size there is no way to tell a full page from the last.",
                docs="reference/envelopes-and-pagination#pagination",
            )

    @property
    def style(self) -> str:
        """``"cursor"`` or ``"page"``."""
        return "cursor" if self.cursor_field else "page"

    def _items(self, response: Any) -> Optional[list]:
        """The array of results in a page-number response."""
        if self.items_field is None:
            return response if isinstance(response, list) else None
        if not isinstance(response, dict):
            return None
        items = response.get(self.items_field)
        return items if isinstance(items, list) else None

    _MISSING = object()

    def _read(self, response: Any, path: str) -> Any:
        """Follow a dotted, optionally indexed path into a response body.

        Returns :attr:`_MISSING` when any step is absent, which is what lets a
        caller tell "the API said False" from "the API said nothing".
        """
        if not isinstance(response, dict):
            return self._MISSING

        value: Any = response
        for key, indices in _parse_path(path):
            if not isinstance(value, dict) or key not in value:
                return self._MISSING
            value = value[key]
            for index in indices:
                if not isinstance(value, (list, tuple)) or not value:
                    return self._MISSING
                try:
                    value = value[index]
                except IndexError:
                    return self._MISSING
            if value is None:
                return self._MISSING

        return value

    def next_cursor(self, response: Any) -> Optional[str]:
        """The cursor for the next page, or ``None`` when there is not one.

        An empty string counts as absent — Slack returns ``""`` on the last page,
        and advertising that as a cursor would produce an endless loop.

        Always ``None`` in page-number style, which has no cursor to report.
        """
        if self.cursor_field is None:
            return None

        value = self._read(response, self.cursor_field)
        if value is self._MISSING or not value:
            return None
        return str(value)

    def has_more(self, response: Any, previous: Optional[Dict[str, Any]] = None) -> bool:
        """Whether another page exists.

        In cursor style, uses ``more_field`` when the API provides one, since
        some APIs send a stale cursor on the final page; otherwise falls back to
        the cursor.

        In page-number style there is no marker at all, so a *short* page is the
        signal: fewer items than were asked for means this was the last one. Pass
        ``previous`` — the arguments that produced ``response`` — so the page size
        is known. Without it, only an empty page can be recognised as the end.
        """
        if self.style == "page":
            page_param, per_page_param = self.page_param, self.per_page_param
            assert page_param and per_page_param  # guaranteed by __post_init__
            items = self._items(response)
            if not items:
                return False
            requested = (previous or {}).get(per_page_param)
            if self.max_items is not None and isinstance(requested, int) and requested > 0:
                # The next page would begin past what the API will serve. The
                # count it reports is of matches, not of results it will hand
                # over, so this is the only place the difference is known.
                page = (previous or {}).get(page_param)
                page = page if isinstance(page, int) and page >= 1 else 1
                if page * requested >= self.max_items:
                    return False
            if isinstance(requested, int) and requested > 0:
                return len(items) >= requested
            # No page size in hand: a non-empty page might be the last one, and
            # saying "maybe" is not an option. Report more and let the next call
            # come back empty rather than stopping on a page that was full.
            return True

        if self.more_field:
            flag = self._read(response, self.more_field)
            if flag is not self._MISSING:
                return bool(flag)
        return self.next_cursor(response) is not None

    def next_page_args(self, response: Any, previous: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Arguments for the next call, or ``None`` when the last page is in hand.

            args = {"channel": "C1"}
            page = await tool.ainvoke(args)
            while (args := tool.pagination.next_page_args(page, args)) is not None:
                page = await tool.ainvoke(args)

        The same loop works in page-number style, which is the point of
        declaring the style rather than the mechanics.
        """
        if not self.has_more(response, previous):
            return None

        if self.style == "page":
            page_param = self.page_param
            assert page_param is not None  # guaranteed by __post_init__
            current = (previous or {}).get(page_param)
            current = current if isinstance(current, int) and current >= 1 else 1
            return {**(previous or {}), page_param: current + 1}

        cursor_param = self.cursor_param
        assert cursor_param is not None  # guaranteed by __post_init__
        cursor = self.next_cursor(response)
        if cursor is None:
            return None
        return _set_path(dict(previous or {}), cursor_param, cursor)
