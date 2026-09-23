# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Gmail response handlers — the context-economy layer.

A raw ``threads.get`` response is mostly machinery: a nested MIME tree, base64url
blobs, dozens of headers, and the binary body of every attachment. Handed to a
model verbatim it costs thousands of tokens to say "Ada replied, here is what
she wrote".

:func:`extract_thread_text`, :func:`extract_message_text` and
:func:`extract_draft_text` walk that tree and return text only — decoded bodies,
the headers worth keeping, and attachment *metadata* without the bytes. All three
project a message the same way, so a thread, a single message and a draft read
alike.

Decoding primitives come from :mod:`charter.text`; what is left here is the part
that is genuinely Gmail-shaped — walking the MIME part tree, in both of the
representations Gmail offers it in.
"""

from __future__ import annotations

import email
import email.policy
from typing import Any, Dict, List, Optional, Set, Tuple

from charter.text import decode_base64url, html_to_text

__all__ = [
    "extract_thread_text",
    "extract_message_text",
    "extract_draft_text",
    "extract_labels",
    "extract_label",
    "extract_thread_list",
]


def _extract_text_parts(part: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Recursively walk the MIME part tree and extract text-only content.

    Rules:
      ``text/plain``    -> base64-decode, include as-is
      ``text/html``     -> base64-decode, convert to plain text
      ``text/calendar`` -> base64-decode, include as-is (iCalendar is readable)
      ``multipart/*``   -> traverse children only
      ``message/rfc822``, ``image/*``, ``audio/*``, ``video/*``,
      ``application/*`` -> skip
    """
    mime = (part.get("mimeType") or "").lower()

    # Container: recurse into children
    if mime.startswith("multipart/"):
        collected: List[Dict[str, Any]] = []
        for child in part.get("parts") or []:
            collected.extend(_extract_text_parts(child))
        return collected

    # Skip non-text types
    if mime.startswith(("image/", "audio/", "video/", "application/", "message/")):
        return []

    # Leaf text parts
    body = part.get("body") or {}
    data = body.get("data")
    if not data:
        return []

    decoded = decode_base64url(data)

    if mime == "text/html":
        decoded = html_to_text(decoded)

    return [{"mimeType": part.get("mimeType", mime), "text": decoded}]


def _extract_attachment_metadata(part: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Attachment metadata from a MessagePart, when ``body.attachmentId`` is present.

    Returns filename, mimeType, size and attachmentId — never the binary data.
    """
    body = part.get("body") or {}
    attachment_id = body.get("attachmentId")
    if not attachment_id:
        return None

    # filename: from part.filename or the Content-Disposition header
    filename = part.get("filename") or ""
    if not filename:
        for h in part.get("headers") or []:
            if h.get("name", "").lower() == "content-disposition":
                # Parse 'attachment; filename="doc.pdf"' or 'attachment; filename=doc.pdf'
                val = h.get("value", "")
                if "filename=" in val:
                    fn = val.split("filename=", 1)[-1].strip().strip("\"'")
                    if fn:
                        filename = fn
                break

    return {
        "attachmentId": attachment_id,
        "filename": filename or "(unnamed)",
        "mimeType": part.get("mimeType", "application/octet-stream"),
        "size": body.get("size", 0),
    }


def _collect_attachment_metadata(part: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Recursively collect attachment metadata from all parts."""
    collected: List[Dict[str, Any]] = []

    meta = _extract_attachment_metadata(part)
    if meta:
        collected.append(meta)

    for child in part.get("parts") or []:
        collected.extend(_collect_attachment_metadata(child))

    return collected


_KEEP_HEADERS: Set[str] = {
    "from",
    "to",
    "cc",
    "bcc",
    "subject",
    "date",
    "list-unsubscribe",
    "received",
    "message-id",
    "reply-to",
    "in-reply-to",
    "references",
    "precedence",
    "x-priority",
    "delivered-to",
}


def _extract_headers(headers: Optional[List[Dict[str, str]]], keep: Set[str]) -> Dict[str, str]:
    """Pick only the desired headers from the headers list."""
    if not headers:
        return {}
    return {h["name"]: h["value"] for h in headers if h.get("name", "").lower() in keep}


_RAW_ATTACHMENT_MAINTYPES = ("image", "audio", "video", "application", "message")


def _from_raw(
    raw: str,
) -> Tuple[Dict[str, str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Headers, text parts and attachment metadata from the ``RAW`` representation.

    ``format=raw`` answers with the entire RFC-822 message in one base64url field
    and no ``payload`` at all, so the tree walk above has nothing to walk. Parsing
    it here rather than handing it back is the whole point of the handler: that
    one blob carries every attachment, base64 encoded a second time.

    Each part's charset is read off the part, which is right whenever the part is
    transfer-encoded — as anything non-ASCII normally is. A part sent as bare
    8-bit in a non-UTF-8 charset has already lost bytes in ``decode_base64url``,
    and degrades there exactly as the payload walk does.
    """
    # policy.default decodes RFC 2047 encoded-words in headers and filenames.
    # Without it a non-ASCII subject comes back as `=?utf-8?b?Q2Fmw6k=?=`, while
    # the payload walk above gets the same subject already decoded by Gmail —
    # so the two representations would disagree about the same message.
    parsed = email.message_from_string(decode_base64url(raw), policy=email.policy.default)
    headers = {name: str(value) for name, value in parsed.items() if name.lower() in _KEEP_HEADERS}

    texts: List[Dict[str, Any]] = []
    attachments: List[Dict[str, Any]] = []
    for part in parsed.walk():
        if part.get_content_maintype() == "multipart":
            continue
        # decode=True hands back the transfer-decoded bytes for a leaf part and
        # None for a part that holds other parts, which an embedded
        # message/rfc822 does. Serialising that one keeps its reported size from
        # being a confident zero.
        decoded = part.get_payload(decode=True)
        content = decoded if isinstance(decoded, bytes) else part.as_bytes()
        filename = part.get_filename()
        if filename or part.get_content_maintype() in _RAW_ATTACHMENT_MAINTYPES:
            # Metadata only, and deliberately no attachmentId: the raw
            # representation does not carry one, so re-reading the message with
            # format=full is what gets a handle on the bytes.
            attachments.append(
                {
                    "filename": filename or "(unnamed)",
                    "mimeType": part.get_content_type(),
                    "size": len(content),
                }
            )
            continue
        text = content.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/html":
            text = html_to_text(text)
        texts.append({"mimeType": part.get_content_type(), "text": text})

    return headers, texts, attachments


def _body_text(text_parts: List[Dict[str, Any]]) -> str:
    """The one body to show: text/plain wins where a message carries both."""
    plain = [p for p in text_parts if p["mimeType"] == "text/plain"]
    if plain:
        return plain[0]["text"]
    return text_parts[0]["text"] if text_parts else ""


def _transform_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a single Gmail Message dict into an LLM-friendly representation.

    Which of the two representations arrives is decided by the ``format`` the
    call asked for: ``full`` and ``metadata`` fill ``payload``, ``raw`` fills
    ``raw`` instead, and ``minimal`` fills neither. Nothing is invented for the
    one that is absent — a ``bodyText`` of ``""`` on a ``minimal`` read would say
    the message is empty, which is a different fact from not having asked for it.
    """
    result: Dict[str, Any] = {"id": msg.get("id"), "threadId": msg.get("threadId")}
    if "labelIds" in msg:
        result["labelIds"] = msg["labelIds"]

    payload = msg.get("payload")
    raw = msg.get("raw")
    text_parts: Optional[List[Dict[str, Any]]] = None
    headers: Dict[str, str] = {}
    attachments: List[Dict[str, Any]] = []
    if payload is not None:
        headers = _extract_headers(payload.get("headers"), _KEEP_HEADERS)
        text_parts = _extract_text_parts(payload)
        # Attachment metadata for a follow-up messages.attachments.get
        attachments = _collect_attachment_metadata(payload)
    elif raw:
        headers, text_parts, attachments = _from_raw(raw)

    if headers:
        result["headers"] = headers
    if text_parts is not None:
        result["bodyText"] = _body_text(text_parts)
        # Surface calendar parts separately so the agent can reason about them
        calendar = [p for p in text_parts if p["mimeType"] == "text/calendar"]
        if calendar:
            result["calendar"] = calendar[0]["text"]
    if msg.get("snippet"):
        result["snippet"] = msg["snippet"]
    if attachments:
        result["attachments"] = attachments

    return result


async def extract_thread_text(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for ``threads_get``.

    Turns the raw Gmail thread payload into a compact, text-only representation
    the LLM can read without base64 blobs or binary content.
    """
    messages = response.get("messages") or []
    result: Dict[str, Any] = {
        "id": response.get("id"),
        "messages": [_transform_message(m) for m in messages],
    }
    if "historyId" in response:
        result["historyId"] = response["historyId"]
    return result


async def extract_message_text(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for ``messages_get``.

    The projection :func:`extract_thread_text` applies to every message in a
    thread, applied to the one message ``messages.get`` returns — so a message
    read on its own and the same message read inside its thread come back the
    same shape.
    """
    return _transform_message(response)


async def extract_draft_text(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for ``drafts_get``.

    A draft is an id and a message, and that message is an ordinary Gmail
    Message — MIME tree, attachment bytes and all. The id is what
    ``drafts_update``, ``drafts_send`` and ``drafts_delete`` take next, so it is
    kept beside the projected message rather than folded into it.
    """
    result: Dict[str, Any] = {"id": response.get("id")}
    message = response.get("message")
    if message is not None:
        result["message"] = _transform_message(message)
    return result


# A Gmail Label carries four counters the API recomputes on every read —
# messagesTotal, messagesUnread, threadsTotal, threadsUnread — plus a colour
# object and the visibility flags that decide where it renders in the web UI.
# None of it identifies the label or says what applying it would do.
_LABEL_KEEP = ("id", "name", "type")


def _trim_label(label: Dict[str, Any]) -> Dict[str, Any]:
    return {k: label[k] for k in _LABEL_KEEP if label.get(k) is not None}


async def extract_labels(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for ``labels_list``.

    The list is what an agent reads to turn a label *name* into the id every
    other call takes, so the names and ids stay and the render hints go.
    """
    return {"labels": [_trim_label(x) for x in response.get("labels") or [] if isinstance(x, dict)]}


async def extract_label(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for the single-label reads and writes.

    ``labels_get``, ``labels_create``, ``labels_update`` and ``labels_patch`` all
    answer with one Label, so they are all projected the same way — a created
    label reads back exactly as a fetched one.
    """
    return _trim_label(response)


async def extract_thread_list(response: Dict[str, Any]) -> Dict[str, Any]:
    """Response handler for ``threads_list``.

    The snippet is what an agent reads to pick a thread, so it stays; the
    per-thread ``historyId`` is a sync cursor for a mailbox watcher and means
    nothing to a caller listing threads.

    ``messages_list`` and ``drafts_list`` deliberately have no handler: those
    endpoints return ids and nothing else, so there is nothing to drop and a
    handler would only add a way to be wrong.
    """
    out: Dict[str, Any] = {
        "threads": [
            {k: v for k, v in t.items() if k != "historyId"}
            for t in response.get("threads") or []
            if isinstance(t, dict)
        ]
    }
    if response.get("nextPageToken"):
        out["nextPageToken"] = response["nextPageToken"]
    return out
