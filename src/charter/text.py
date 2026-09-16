"""
Content-decoding primitives for response handlers.

A response handler's job is to turn an API's raw payload into something a model
can read. Two decodings come up over and over while doing that — base64url
bodies and HTML content — so they live here rather than being rewritten in every
pack.

Both are stdlib-only, on purpose: the core dependency budget is pydantic and
httpx, and an HTML-to-text pass this shallow does not justify a parser
dependency.

    from charter import decode_base64url, html_to_text

Used by the Gmail pack; needed by anything carrying user-authored content —
Notion blocks, Zendesk tickets, Intercom conversations, Outlook messages.
"""

from __future__ import annotations

import base64
import re
from html.parser import HTMLParser
from typing import Any, List

__all__ = ["decode_base64url", "html_to_text"]


def decode_base64url(data: str, *, errors: str = "replace") -> str:
    """Decode a base64url string to UTF-8 text, padding it first.

    APIs that hand back base64url almost never pad it (Gmail, JWT segments,
    Microsoft Graph attachments), and :func:`base64.urlsafe_b64decode` requires
    padding, so this adds it back.

    ``errors`` is passed to ``bytes.decode`` and defaults to ``"replace"``: a
    response handler should degrade rather than raise on one malformed part.
    """
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode()).decode("utf-8", errors=errors)


class _TextExtractor(HTMLParser):
    """Collect readable text, dropping script/style/head content."""

    _SKIP = {"script", "style", "head", "title"}
    # Tags whose boundaries should read as a line break in the flattened text.
    _BREAK = {
        "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "blockquote", "section", "article", "header", "footer",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BREAK:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        joined = "".join(self._parts)
        # Trim trailing spaces on each line, then collapse runs of blank lines.
        joined = "\n".join(line.strip() for line in joined.split("\n"))
        return re.sub(r"\n{3,}", "\n\n", joined).strip()


def html_to_text(html: str) -> str:
    """Flatten HTML to readable plain text.

    Drops ``script``/``style``/``head`` content, turns block-level tags into line
    breaks, decodes character entities, and collapses runs of blank lines.

    Malformed input degrades to the raw markup rather than raising — a handler
    should never fail a whole call over one badly formed message part.
    """
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return html.strip()
    return parser.text()
