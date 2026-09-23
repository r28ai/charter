# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Notion response trimming — context economy only.

Notion never reports failure in a 200, so nothing here decides whether a call
worked; these handlers only ever see a successful payload. What they deal with
is size, and Notion's is structural rather than incidental.

Every piece of text in Notion is an array of rich text runs, and each run
carries its own annotations, a ``plain_text`` copy, an ``href`` and a ``type``
discriminator. A one-line page title is about 200 bytes of JSON for roughly
twenty characters of title. A row of a database repeats that for every column,
and then adds ``created_by`` and ``last_edited_by`` user objects, two
timestamps, a parent, a URL and a public URL. A hundred-row query is a few
hundred kilobytes of which the readable part is a few kilobytes.

So these project. Text collapses to the string it spells, a property collapses
to its value, and the paging markers are kept so the caller can still walk. What
is dropped is the scaffolding, never a row: the handlers here never filter a
list, because a shorter page would corrupt the signal pagination depends on.

The ``id`` of everything is kept. It is what the next call needs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "trim_page",
    "trim_pages",
    "trim_blocks",
    "trim_block",
    "trim_users",
    "trim_comments",
    "trim_data_source",
    "trim_database",
]


def _plain_text(rich_text: Any) -> str:
    """The string an array of rich text runs spells.

    ``plain_text`` is Notion's own flattening and is present on every run it
    returns, so this is a join rather than a reconstruction. Falls back to the
    nested content for a run that somehow lacks it.
    """
    if not isinstance(rich_text, list):
        return ""
    parts: List[str] = []
    for run in rich_text:
        if not isinstance(run, dict):
            continue
        text = run.get("plain_text")
        if text is None:
            nested = run.get("text")
            text = nested.get("content") if isinstance(nested, dict) else None
        if text:
            parts.append(str(text))
    return "".join(parts)


def _paging(response: Dict[str, Any], out: Dict[str, Any]) -> Dict[str, Any]:
    """Carry the paging markers onto a trimmed list.

    ``has_more`` is kept even when false: it is the signal a walk terminates on,
    and a handler that drops it leaves the caller inferring the end from a
    cursor Notion does not always clear.
    """
    if "has_more" in response:
        out["has_more"] = bool(response["has_more"])
    if response.get("next_cursor") is not None:
        out["next_cursor"] = response["next_cursor"]
    return out


def _property_value(prop: Any) -> Any:
    """One page property, reduced to the value a reader would quote.

    Notion wraps every value in its type. A select becomes its name, a date
    becomes its start (or ``start → end`` for a range), a relation becomes the
    IDs it points at. The type tag itself is dropped: the property's name in
    the surrounding map already says what it is, and the shape of the value
    carries the rest.
    """
    if not isinstance(prop, dict):
        return prop
    kind = prop.get("type")
    value = prop.get(kind) if kind else None

    if kind in ("title", "rich_text"):
        return _plain_text(value)
    if kind in (
        "number",
        "checkbox",
        "url",
        "email",
        "phone_number",
        "created_time",
        "last_edited_time",
    ):
        return value
    if kind in ("select", "status"):
        return value.get("name") if isinstance(value, dict) else None
    if kind == "multi_select":
        return [o.get("name") for o in value or [] if isinstance(o, dict)]
    if kind == "date":
        if not isinstance(value, dict):
            return None
        start, end = value.get("start"), value.get("end")
        return f"{start} → {end}" if end else start
    if kind in ("people", "created_by", "last_edited_by"):
        people = value if isinstance(value, list) else [value]
        return [p.get("id") for p in people if isinstance(p, dict)]
    if kind == "relation":
        return [r.get("id") for r in value or [] if isinstance(r, dict)]
    if kind == "files":
        return [f.get("name") for f in value or [] if isinstance(f, dict)]
    if kind == "formula":
        return _unwrap_computed(value)
    if kind == "rollup":
        return _unwrap_computed(value)
    if kind == "unique_id":
        if not isinstance(value, dict):
            return None
        prefix, number = value.get("prefix"), value.get("number")
        return f"{prefix}-{number}" if prefix else number
    if kind == "verification":
        return value.get("state") if isinstance(value, dict) else None
    # A property type added after this pack was written. Returning the raw value
    # keeps the call useful rather than dropping a column the caller asked for.
    return value


def _unwrap_computed(value: Any) -> Any:
    """A formula or rollup result, reduced to what it computed to.

    Both wrap their answer in its own type a second time. ``unsupported`` is
    kept as a word rather than dropped: a silently missing value reads as an
    empty column, and this one means Notion could not evaluate it.
    """
    if not isinstance(value, dict):
        return value
    kind = value.get("type")
    if kind == "unsupported":
        return "unsupported"
    if kind == "date":
        inner = value.get("date")
        return inner.get("start") if isinstance(inner, dict) else None
    if kind == "array":
        return [_unwrap_computed(v) for v in value.get("array") or []]
    return value.get(kind) if kind else None


def _title_of(properties: Any) -> Optional[str]:
    """The page's title, wherever its column happens to be named.

    A database decides what its title column is called, so this is found by
    type rather than by name.
    """
    if not isinstance(properties, dict):
        return None
    for prop in properties.values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            return _plain_text(prop.get("title"))
    return None


def _icon(icon: Any) -> Optional[str]:
    """An icon, as the one string worth carrying."""
    if not isinstance(icon, dict):
        return None
    if icon.get("type") == "emoji":
        return icon.get("emoji")
    if icon.get("type") == "custom_emoji":
        custom = icon.get("custom_emoji")
        return custom.get("name") if isinstance(custom, dict) else None
    return None


def _parent_id(parent: Any) -> Optional[str]:
    """The ID out of a parent object, whichever kind it is."""
    if not isinstance(parent, dict):
        return None
    kind = parent.get("type")
    return parent.get(kind) if isinstance(parent.get(kind), str) else None


def _page(page: Dict[str, Any]) -> Dict[str, Any]:
    """One page, reduced to its identity and its property values."""
    out: Dict[str, Any] = {"id": page.get("id")}
    title = _title_of(page.get("properties"))
    if title:
        out["title"] = title
    if page.get("url"):
        out["url"] = page["url"]

    properties = page.get("properties")
    if isinstance(properties, dict):
        values = {
            name: _property_value(prop)
            for name, prop in properties.items()
            if not (isinstance(prop, dict) and prop.get("type") == "title")
        }
        # Emptiness is information here — a row with nothing filled in is a real
        # answer — so the key is kept even when every column is None.
        out["properties"] = values

    for key in ("in_trash", "is_locked"):
        if page.get(key):
            out[key] = page[key]
    if page.get("last_edited_time"):
        out["last_edited_time"] = page["last_edited_time"]
    icon = _icon(page.get("icon"))
    if icon:
        out["icon"] = icon
    parent = _parent_id(page.get("parent"))
    if parent:
        out["parent_id"] = parent
    return out


async def trim_page(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a single page object.

    Used by create, retrieve, update and move: all four answer with the page.
    """
    if not isinstance(response, dict):
        return response
    # A page created asynchronously answers with the task, not the page. Saying
    # so beats returning an object with every field missing.
    if response.get("object") == "async_task":
        return response
    return _page(response)


async def trim_pages(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a list of pages — a data source query, or a search.

    A search can return data sources beside pages, so an entry that is not a
    page is passed through with its title flattened rather than forced into a
    page's shape.
    """
    if not isinstance(response, dict):
        return response
    results: List[Dict[str, Any]] = []
    for item in response.get("results") or []:
        if not isinstance(item, dict):
            continue
        if item.get("object") == "page":
            results.append(_page(item))
        elif item.get("object") in ("data_source", "database"):
            results.append(
                {
                    "id": item.get("id"),
                    "object": item.get("object"),
                    "title": _plain_text(item.get("title")),
                    "url": item.get("url"),
                }
            )
        else:
            results.append(item)
    return _paging(response, {"results": results})


_TEXT_BLOCKS = (
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "heading_4",
    "bulleted_list_item",
    "numbered_list_item",
    "to_do",
    "toggle",
    "quote",
    "callout",
    "code",
    "template",
)


def _block(block: Dict[str, Any]) -> Dict[str, Any]:
    """One block, reduced to its type, its text and what a caller can act on."""
    kind = block.get("type")
    out: Dict[str, Any] = {"id": block.get("id"), "type": kind}
    content = block.get(kind) if kind else None

    if isinstance(content, dict):
        if kind in _TEXT_BLOCKS:
            out["text"] = _plain_text(content.get("rich_text"))
            if kind == "to_do":
                out["checked"] = bool(content.get("checked"))
            if kind == "code":
                out["language"] = content.get("language")
        elif kind == "equation":
            out["expression"] = content.get("expression")
        elif kind in ("child_page", "child_database"):
            out["title"] = content.get("title")
        elif kind in ("image", "video", "audio", "pdf", "file"):
            source = content.get(content.get("type") or "")
            if isinstance(source, dict) and source.get("url"):
                out["url"] = source["url"]
            caption = _plain_text(content.get("caption"))
            if caption:
                out["caption"] = caption
        elif kind in ("bookmark", "embed", "link_preview"):
            out["url"] = content.get("url")
        elif kind == "table_row":
            out["cells"] = [_plain_text(cell) for cell in content.get("cells") or []]
        elif kind == "table":
            out["table_width"] = content.get("table_width")

    if block.get("has_children"):
        out["has_children"] = True
    if block.get("in_trash"):
        out["in_trash"] = True
    return out


async def trim_block(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a single block object."""
    if not isinstance(response, dict):
        return response
    return _block(response)


async def trim_blocks(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a list of blocks — a children listing, or an append's result.

    ``has_children`` is kept wherever it is true, since it is the only signal
    that reading this list did not read everything.
    """
    if not isinstance(response, dict):
        return response
    results = [_block(b) for b in response.get("results") or [] if isinstance(b, dict)]
    return _paging(response, {"results": results})


def _user(user: Dict[str, Any]) -> Dict[str, Any]:
    """One user, without the avatar URL and the workspace limits object."""
    out: Dict[str, Any] = {"id": user.get("id"), "type": user.get("type")}
    if user.get("name"):
        out["name"] = user["name"]
    person = user.get("person")
    if isinstance(person, dict) and person.get("email"):
        out["email"] = person["email"]
    bot = user.get("bot")
    if isinstance(bot, dict):
        if bot.get("workspace_name"):
            out["workspace_name"] = bot["workspace_name"]
        owner = bot.get("owner")
        if isinstance(owner, dict) and owner.get("type"):
            out["owner_type"] = owner["type"]
    return out


async def trim_users(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a user listing, or a single user.

    Handles both shapes, since `users_retrieve` and `users_retrieve_me` answer
    with a bare user and `users_list` answers with a page of them.
    """
    if not isinstance(response, dict):
        return response
    if response.get("object") == "user":
        return _user(response)
    results = [_user(u) for u in response.get("results") or [] if isinstance(u, dict)]
    return _paging(response, {"results": results})


def _comment(comment: Dict[str, Any]) -> Dict[str, Any]:
    """One comment, as its text plus who said it and where."""
    out: Dict[str, Any] = {
        "id": comment.get("id"),
        "discussion_id": comment.get("discussion_id"),
        "text": _plain_text(comment.get("rich_text")),
    }
    author = comment.get("created_by")
    if isinstance(author, dict):
        out["created_by"] = author.get("id")
    if comment.get("created_time"):
        out["created_time"] = comment["created_time"]
    parent = _parent_id(comment.get("parent"))
    if parent:
        out["parent_id"] = parent
    attachments = comment.get("attachments")
    if attachments:
        out["attachments"] = [
            a.get("file", {}).get("url") if isinstance(a.get("file"), dict) else a.get("category")
            for a in attachments
            if isinstance(a, dict)
        ]
    return out


async def trim_comments(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a comment listing, or a single comment."""
    if not isinstance(response, dict):
        return response
    if response.get("object") == "comment":
        return _comment(response)
    results = [_comment(c) for c in response.get("results") or [] if isinstance(c, dict)]
    return _paging(response, {"results": results})


def _property_schema(name: str, config: Any) -> Dict[str, Any]:
    """One column of a data source, as its type and the options it allows.

    The options are what a caller needs before writing to the column, so they
    are kept — by name, without the IDs and colours.
    """
    if not isinstance(config, dict):
        return {"name": name}
    kind = config.get("type")
    out: Dict[str, Any] = {"id": config.get("id"), "type": kind}
    settings = config.get(kind) if kind else None
    if isinstance(settings, dict):
        options = settings.get("options")
        if isinstance(options, list):
            out["options"] = [o.get("name") for o in options if isinstance(o, dict)]
        if kind == "number" and settings.get("format"):
            out["format"] = settings["format"]
        if kind == "formula" and settings.get("expression"):
            out["expression"] = settings["expression"]
        if kind == "relation" and settings.get("data_source_id"):
            out["data_source_id"] = settings["data_source_id"]
    return out


async def trim_data_source(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a data source, keeping the column schema a caller has to write against.

    This is the one read where the schema *is* the payload, so the properties
    are kept in full rather than collapsed — what goes is the per-option IDs and
    colours, and the object's own scaffolding.
    """
    if not isinstance(response, dict):
        return response
    properties = response.get("properties")
    out: Dict[str, Any] = {
        "id": response.get("id"),
        "title": _plain_text(response.get("title")),
    }
    parent = _parent_id(response.get("parent"))
    if parent:
        out["database_id"] = parent
    if isinstance(properties, dict):
        out["properties"] = {
            name: _property_schema(name, config) for name, config in properties.items()
        }
    return out


async def trim_database(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a database, keeping the data sources it contains.

    Those IDs are the point of the call: a database holds no columns of its own,
    so reading one is how a caller finds the data source to query.
    """
    if not isinstance(response, dict):
        return response
    out: Dict[str, Any] = {
        "id": response.get("id"),
        "title": _plain_text(response.get("title")),
    }
    if response.get("url"):
        out["url"] = response["url"]
    sources = response.get("data_sources")
    if isinstance(sources, list):
        out["data_sources"] = [
            {"id": s.get("id"), "name": s.get("name")} for s in sources if isinstance(s, dict)
        ]
    if response.get("is_inline") is not None:
        out["is_inline"] = response["is_inline"]
    return out
