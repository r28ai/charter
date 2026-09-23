# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Firecrawl response trimming — context economy only.

A scrape returns the page's content and then every meta tag on it. On a
measured GitHub blob the split was 1,998 bytes of markdown against 4,624 bytes
of ``metadata`` across 71 keys: OpenGraph, Twitter cards, ``apple-itunes-app``,
``go-import``, a ``visitor-payload`` blob. Two thirds of the payload described
the page to crawlers rather than to the agent that asked for it.

These handlers keep the requested content verbatim — that is what the caller
came for and it is never trimmed — and reduce ``metadata`` to the handful of
fields an agent reads: what the page is called, what it says it is, where it
came from, and whether fetching it worked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

__all__ = [
    "extract_scrape",
    "extract_search",
    "extract_map",
]

# Document fields the OpenAPI scrape schema returns when the matching format
# (or parser option, or actions list) was requested. Trimming any of these
# would drop the thing the caller asked for.
_CONTENT: Tuple[str, ...] = (
    "markdown",
    "html",
    "rawHtml",
    "rawBase64",
    "links",
    "images",
    "summary",
    "json",
    "screenshot",
    "changeTracking",
    "branding",
    "product",
    "menu",
    "audio",
    "video",
    "answer",
    "highlights",
    "actions",
    "pages",
    "blocks",
)

# Search results that were not scraped still identify themselves with these
# keys. Dropping them left a search with no URLs.
_SEARCH_RESULT: Tuple[str, ...] = (
    "url",
    "title",
    "description",
    "snippet",
    "date",
    "position",
    "imageUrl",
    "imageWidth",
    "imageHeight",
)

# What an agent reads out of 71 meta tags.
_META = ("title", "description", "sourceURL", "url", "statusCode", "language", "error")


def _metadata(metadata: Any) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    return {k: metadata[k] for k in _META if metadata.get(k) is not None}


def _document(document: Dict[str, Any], *, extra: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """One page or search hit: its content, and the little of its metadata that reads."""
    keys = extra + _CONTENT
    out: Dict[str, Any] = {k: document[k] for k in keys if document.get(k) is not None}
    metadata = _metadata(document.get("metadata"))
    if metadata:
        out["metadata"] = metadata
    # A partial scrape says so here; dropping it would hide a failed fetch.
    if document.get("warning"):
        out["warning"] = document["warning"]
    return out


async def extract_scrape(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim scrape documents. The requested formats survive verbatim.

    Used by ``/scrape`` (one document in ``data``) and by crawl/batch status
    (an array of the same documents). The envelope stays where it is — callers
    read ``result["data"]``, and paging fields such as ``next`` must survive.
    """
    data = response.get("data")
    if isinstance(data, list):
        return {
            **response,
            "data": [_document(d) if isinstance(d, dict) else d for d in data],
        }
    if not isinstance(data, dict):
        return response
    return {**response, "data": _document(data)}


async def extract_search(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``/search``.

    Results arrive grouped by source (``web``, ``news``, ``images``). Hits that
    were not scraped still keep ``url`` / ``title`` / ``description``; scraped
    hits keep those plus the requested formats.
    """
    data = response.get("data")
    if isinstance(data, list):
        return {
            **response,
            "data": [
                _document(d, extra=_SEARCH_RESULT) if isinstance(d, dict) else d for d in data
            ],
        }
    if isinstance(data, dict):
        grouped: Dict[str, Any] = {}
        for source, results in data.items():
            grouped[source] = (
                [_document(d, extra=_SEARCH_RESULT) if isinstance(d, dict) else d for d in results]
                if isinstance(results, list)
                else results
            )
        return {**response, "data": grouped}
    return response


async def extract_map(response: Dict[str, Any]) -> Dict[str, Any]:
    """Trim ``/map``: the URLs it found, without each one's page metadata.

    The documented envelope is ``{"success", "links"}``, not ``data``.
    """
    links = response.get("links")
    if not isinstance(links, list):
        return response
    trimmed: List[Any] = []
    for entry in links:
        if isinstance(entry, dict):
            keep = {k: entry[k] for k in ("url", "title", "description") if entry.get(k)}
            trimmed.append(keep or entry)
        else:
            trimmed.append(entry)
    return {**response, "links": trimmed}
