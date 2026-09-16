"""
Google Docs response trimming — context economy only.

A Docs document resource is mostly typography. An *empty* document comes back
at about 10KB, of which ``namedStyles`` is 4.2KB and ``tabs`` another 5.2KB;
add ``documentStyle`` and 94% of that payload describes fonts, margins and
heading definitions that no agent can act on. The text an agent came for is
buried under ``body.content[].paragraph.elements[].textRun.content``, wrapped
in a ``textStyle`` that is usually empty.

These handlers keep the identifiers, the title, and the text — and keep it
*addressable*. Docs edits are made by character index through
``documents.batchUpdate``, so every paragraph retains its ``startIndex`` and
``endIndex``. Flattening to one string would read well and make the document
uneditable, which is the wrong trade for a tool pack.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "extract_document",
]


def _text_of(elements: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, str]]]:
    """The visible text of a paragraph, and any links it carries.

    A link is content, not styling: it is the one thing inside ``textStyle``
    an agent can act on, so it survives while the rest of the style does not.
    """
    parts: List[str] = []
    links: List[Dict[str, str]] = []
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        run = element.get("textRun")
        if isinstance(run, dict):
            content = run.get("content", "")
            parts.append(content)
            url = ((run.get("textStyle") or {}).get("link") or {}).get("url")
            if url:
                links.append({"text": content.strip(), "url": url})
            continue
        # Inline images and equations carry no text; say they are there.
        if element.get("inlineObjectElement"):
            parts.append("￼")  # object replacement character
        elif element.get("person"):
            parts.append((element["person"].get("personProperties") or {}).get("name", ""))
    return "".join(parts), links


def _paragraph(element: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    paragraph = element.get("paragraph") or {}
    text, links = _text_of(paragraph.get("elements") or [])
    out: Dict[str, Any] = {
        "startIndex": element.get("startIndex", 0),
        "endIndex": element.get("endIndex"),
        "text": text,
    }
    # NORMAL_TEXT is the default and would cost a line on every paragraph;
    # a heading is the case worth reporting because it carries structure.
    style = (paragraph.get("paragraphStyle") or {}).get("namedStyleType")
    if style and style != "NORMAL_TEXT":
        out["style"] = style
    if paragraph.get("bullet"):
        out["bullet"] = True
    if links:
        out["links"] = links
    return out


def _table(element: Dict[str, Any]) -> Dict[str, Any]:
    """A table as rows of cell text; the cell's own structure is styling."""
    rows: List[List[str]] = []
    for row in (element.get("table") or {}).get("tableRows") or []:
        cells: List[str] = []
        for cell in row.get("tableCells") or []:
            text, _ = _text_of(
                [e for c in cell.get("content") or [] for e in (c.get("paragraph") or {}).get("elements") or []]
            )
            cells.append(text.strip())
        rows.append(cells)
    return {
        "startIndex": element.get("startIndex", 0),
        "endIndex": element.get("endIndex"),
        "table": rows,
    }


def _content(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for element in (body or {}).get("content") or []:
        if not isinstance(element, dict):
            continue
        if "paragraph" in element:
            block = _paragraph(element)
            if block:
                out.append(block)
        elif "table" in element:
            out.append(_table(element))
        # sectionBreak and tableOfContents carry no text an agent acts on.
    return out


def _tab(tab: Dict[str, Any]) -> Dict[str, Any]:
    """One tab: what names it, and its text. Each tab repeats the document's
    own ``namedStyles`` and ``documentStyle``, so a multi-tab document pays the
    4KB typography block once per tab before this."""
    properties = tab.get("tabProperties") or {}
    out: Dict[str, Any] = {
        "tabId": properties.get("tabId"),
        "title": properties.get("title", ""),
        "content": _content((tab.get("documentTab") or {}).get("body") or {}),
    }
    children = [_tab(c) for c in tab.get("childTabs") or [] if isinstance(c, dict)]
    if children:
        out["childTabs"] = children
    return out


async def extract_document(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``documents.get`` and ``documents.create``.

    Drops ``namedStyles``, ``documentStyle`` and ``suggestionsViewMode`` —
    typography, on which most of the payload is spent. Keeps ``revisionId``
    because ``batchUpdate`` takes it as a write precondition: dropping a field
    the API's own write path consumes is the wrong kind of saving.

    ``tabs`` is trimmed rather than dropped. ``documents_get`` advertises
    ``include_tabs_content=true`` for a document with several tabs, so the tab
    text has to survive; what does not is the typography each tab repeats.
    """
    out: Dict[str, Any] = {
        "documentId": response.get("documentId"),
        "title": response.get("title", ""),
    }
    if response.get("revisionId"):
        out["revisionId"] = response["revisionId"]
    out["content"] = _content(response.get("body") or {})
    # The end of the document, so an append has somewhere to target without
    # the caller re-deriving it from the last block.
    if out["content"]:
        end = out["content"][-1].get("endIndex")
        if end is not None:
            out["endIndex"] = end
    tabs = [_tab(t) for t in response.get("tabs") or [] if isinstance(t, dict)]
    if tabs:
        out["tabs"] = tabs
    return out
