# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Outlook response handlers — what a model is handed back from Microsoft Graph.

A Graph message is mostly envelope: ``@odata.context`` and ``@odata.etag`` on
every object, a ``changeKey``, a base64 ``conversationIndex``, and each
recipient wrapped twice (``{"emailAddress": {"name": ..., "address": ...}}``).
A page of ten messages without ``$select`` also carries ten full HTML bodies.
These handlers keep the content and drop the machinery:

* OData annotations go, except an object's ``@odata.type``, which becomes
  ``type``;
* recipients become ``"Name <address>"`` strings;
* a list of messages leaves the full ``body`` out — ``bodyPreview`` is the first
  255 characters, ``uniqueBody`` stays when it was selected, and
  ``messages_get`` returns the rest;
* ``@odata.nextLink`` and ``@odata.deltaLink`` become ``next_link`` and
  ``delta_link``, the names the paging tools take them back under. A dotted
  key cannot be named by a :class:`~charter.Pagination` path, and a trim that
  dropped the link would leave the walk with nothing to stop or continue on;
* an attachment's bytes are decoded only when they are text, strictly — a
  binary file is reported, not turned into replacement characters.

Every handler takes the payload of a successful call. Failures — an HTTP
error from Graph — have raised before any of this runs.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, Optional

__all__ = [
    "mime_text",
    "raw_attachment",
    "read_attachment",
    "trim_attachments",
    "trim_entity",
    "trim_message",
    "trim_message_delta",
    "trim_messages",
    "trim_page",
    "upload_session",
]

# Present on almost every Graph object and useful to none of the callers here.
#
# `lCID` is on every localeInfo Graph returns, mailbox settings' `language`
# among them, and on none it documents. The update refuses it as an unknown
# field, so a model that read the settings and wrote the language back as it
# found it was refused for a value it never chose.
_NOISE = frozenset(
    {
        "@odata.context",
        "@odata.etag",
        "@odata.id",
        "@odata.editLink",
        "@microsoft.graph.tips",
        "changeKey",
        "conversationIndex",
        "lCID",
    }
)
# OData annotations on a property, rather than on the object: an attachment's
# `@odata.mediaContentType`, an expanded item's `item@odata.navigationLink`, the
# `count@odata.type` an open extension stamps on each of its values. `@odata.type`
# itself is kept, as `type`; every other annotation is machinery.
_ANNOTATION = "@odata."
_RECIPIENT_FIELDS = ("from", "sender", "toRecipients", "ccRecipients", "bccRecipients", "replyTo")
_GRAPH_TYPE_PREFIX = "#microsoft.graph."

# Content types whose bytes are text, beyond text/*.
_TEXTUAL = frozenset(
    {
        "application/json",
        "application/xml",
        "application/javascript",
        "application/x-yaml",
        "application/yaml",
        "application/csv",
        "message/rfc822",
    }
)


def _clean(value: Any) -> Any:
    """``value`` without Graph's envelope keys, nulls or empty containers."""
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if key in _NOISE or (_ANNOTATION in key and key != "@odata.type"):
                continue
            item = _clean(item)
            if item is None or item == [] or item == {}:
                continue
            if key == "@odata.type" and isinstance(item, str):
                cleaned["type"] = item.removeprefix(_GRAPH_TYPE_PREFIX).removeprefix(
                    "microsoft.graph."
                )
                continue
            cleaned[key] = item
        return cleaned
    if isinstance(value, list):
        return [_clean(item) for item in value]
    return value


def _address(recipient: Any) -> Any:
    """``{"emailAddress": {"name": "Ada", "address": "ada@x"}}`` -> ``"Ada <ada@x>"``."""
    if not isinstance(recipient, dict):
        return recipient
    email = recipient.get("emailAddress")
    if not isinstance(email, dict):
        return recipient
    address, name = email.get("address"), email.get("name")
    if address and name and name != address:
        return f"{name} <{address}>"
    return address or name or recipient


def _message(raw: Any, *, keep_body: bool) -> Any:
    """A message without the envelope, its recipients as ``Name <address>``.

    ``keep_body=False`` drops ``body`` but keeps ``uniqueBody``: Graph returns
    the second only when it was selected, so its presence is the caller asking.
    """
    if not isinstance(raw, dict):
        return raw
    message = _clean(raw)
    for field in _RECIPIENT_FIELDS:
        value = message.get(field)
        if isinstance(value, list):
            message[field] = [_address(r) for r in value]
        elif value is not None:
            message[field] = _address(value)
    if not keep_body:
        message.pop("body", None)
    if "@removed" in message:
        message["removed"] = message.pop("@removed")
    return message


def _page(raw: Any, item: Any) -> Dict[str, Any]:
    """A collection page: its items, and whatever says where the next one is."""
    if not isinstance(raw, dict):
        return {"value": []}
    page: Dict[str, Any] = {"value": [item(v) for v in raw.get("value") or []]}
    if raw.get("@odata.nextLink"):
        page["next_link"] = raw["@odata.nextLink"]
    if raw.get("@odata.deltaLink"):
        page["delta_link"] = raw["@odata.deltaLink"]
    if raw.get("@odata.count") is not None:
        page["count"] = raw["@odata.count"]
    return page


async def trim_message(response: Any) -> Any:
    """One message, with its body and recipients readable."""
    return _message(response, keep_body=True)


async def trim_messages(response: Any) -> Dict[str, Any]:
    """A page of messages without their full bodies; ``bodyPreview`` stays."""
    return _page(response, lambda m: _message(m, keep_body=False))


async def trim_message_delta(response: Any) -> Dict[str, Any]:
    """A delta page: changed messages without bodies, removals as ``removed``."""
    return _page(response, lambda m: _message(m, keep_body=False))


async def trim_page(response: Any) -> Dict[str, Any]:
    """Any other collection: folders, categories, rules, overrides, locales."""
    return _page(response, _clean)


async def trim_entity(response: Any) -> Any:
    """One object, without Graph's envelope keys."""
    return _clean(response)


def _attachment_summary(raw: Any) -> Any:
    attachment = _clean(raw)
    if isinstance(attachment, dict):
        attachment.pop("contentBytes", None)
    return attachment


async def trim_attachments(response: Any) -> Dict[str, Any]:
    """A message's attachments as metadata: names, types, sizes and IDs, no bytes."""
    return _page(response, _attachment_summary)


def _is_text(content_type: Optional[str]) -> bool:
    base = (content_type or "").split(";", 1)[0].strip().lower()
    return base.startswith("text/") or base in _TEXTUAL or base.endswith(("+json", "+xml"))


async def read_attachment(response: Any) -> Any:
    """One attachment: a text file's content as text, anything else described.

    A file attachment's ``contentBytes`` is base64. A text file is decoded
    strictly, and comes back as ``content``. A binary one — or a "text" one
    whose bytes are not UTF-8 — is reported by name, type and size, and the
    bytes are left out: decoded loosely they read as content and are not, and
    ``attachments_get_content`` is the tool that hands them over as bytes. An
    item attachment keeps its expanded item, projected like any message.
    """
    attachment = _clean(response)
    if not isinstance(attachment, dict):
        return attachment
    encoded = attachment.pop("contentBytes", None)
    if isinstance(encoded, str):
        content_type = attachment.get("contentType")
        decoded: Optional[str] = None
        if _is_text(content_type):
            try:
                decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (binascii.Error, ValueError):
                decoded = None
        if decoded is not None:
            attachment["content"] = decoded
        else:
            attachment["content_omitted"] = (
                f"{content_type or 'binary'} content is not text; use "
                "attachments_get_content for the bytes."
            )
    item = attachment.get("item")
    if isinstance(item, dict):
        attachment["item"] = _message(item, keep_body=True)
    return attachment


def _bytes_of(response: Any) -> Optional[bytes]:
    """The body of a ``$value`` response, as bytes, whichever way the runtime held it."""
    if not isinstance(response, dict):
        return None
    if isinstance(response.get("raw"), str):
        return response["raw"].encode("utf-8")
    if isinstance(response.get("raw_base64"), str):
        try:
            return base64.b64decode(response["raw_base64"], validate=True)
        except (binascii.Error, ValueError):
            return None
    return None


async def mime_text(response: Any) -> Dict[str, Any]:
    """A message's MIME content, as the text it is.

    MIME is 7-bit text by construction, so it is decoded strictly; content that
    is not UTF-8 is handed back base64-encoded and labelled, never with its bad
    bytes replaced.
    """
    data = _bytes_of(response)
    if data is None:
        return {"mime": None}
    try:
        return {"mime": data.decode("utf-8")}
    except UnicodeDecodeError:
        return {
            "mime_base64": base64.b64encode(data).decode("ascii"),
            "note": "The MIME content is not UTF-8 text, so it is returned base64-encoded.",
        }


async def raw_attachment(response: Any) -> Dict[str, Any]:
    """An attachment's raw contents: text when they are text, base64 bytes otherwise."""
    if isinstance(response, dict) and isinstance(response.get("raw"), str):
        return {"content": response["raw"]}
    if isinstance(response, dict) and "raw_base64" in response:
        return {
            "content_base64": response.get("raw_base64"),
            "content_type": response.get("content_type"),
            "size_bytes": response.get("size_bytes"),
        }
    return _clean(response) if isinstance(response, dict) else {"content": response}


async def upload_session(response: Any) -> Any:
    """Where to send the file's bytes, and by when."""
    if not isinstance(response, dict):
        return response
    keep = ("uploadUrl", "expirationDateTime", "nextExpectedRanges")
    return {key: response[key] for key in keep if key in response}
