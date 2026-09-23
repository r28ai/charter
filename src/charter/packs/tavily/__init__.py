# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""
Tavily — real-time web search, extraction, crawling, mapping, and research.

An API-key pack: authentication is a bearer token, so there is no credential
provider, just a key.

    from charter.packs import tavily

    tavily.configure(api_key="tvly-...")
    results = await tavily.search.ainvoke(query="latest AI news")

``configure()`` is optional if ``$TAVILY_API_KEY`` is set. Headers are resolved
per request, so configuring after the tools are built works, and an unconfigured
call raises ``CredentialError`` before anything is sent.

The wire is snake_case throughout — parameters, bodies and query strings. Failure
is always an HTTP status code with ``{"detail": {"error": "..."}}``; there is no
success envelope to declare.

Research streaming via ``stream=true`` is not exposed here: the response is SSE,
not JSON, and does not fit the tool contract. Create a task with
``research_create`` and poll with ``research_get`` instead.

``logs`` requires a paid plan or pay-as-you-go. ``org_usage`` is enterprise-only
and must authenticate with the organization owner's personal API key.

**Project scoping and tracking go through the per-call header channel.** Tavily
accepts ``X-Project-ID`` on ``usage`` (and optional ``X-Session-Id`` /
``X-Human-Id`` on any endpoint). These are host-application values, not tool
arguments.
"""

from __future__ import annotations

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.tavily.types import (
    CrawlRequest,
    ExtractRequest,
    LogsRequest,
    MapRequest,
    OrgUsageRequest,
    ResearchCreateRequest,
    ResearchGetRequest,
    SearchRequest,
    UsageGetRequest,
)
from charter.tool import Tool

BASE_URL = "https://api.tavily.com/"
QUOTA_DOC_URL = "https://docs.tavily.com/documentation/rate-limits"

_headers: DeferredApiKeyHeaders = api_key_headers(
    "tavily",
    {"Authorization": "Bearer CHARTER_UNCONFIGURED"},
    "Authorization",
    "TAVILY_API_KEY",
)


def configure(api_key: str) -> None:
    """Supply the Tavily API key for this pack's tools."""
    _headers.configure(api_key)


_tavily = api_key_tool_factory(
    pack="tavily",
    base_url=BASE_URL,
    api_key_headers=_headers,
    body_case="snake",
    query_case="snake",
    quota_doc_url=QUOTA_DOC_URL,
)

search = _tavily(
    name="search",
    args_schema=SearchRequest,
    method="POST",
    url_template="search",
    description=(
        "Execute a real-time web search optimized for AI agents. Use when sources "
        "are unknown or current web context is needed. Prefer search_depth "
        "advanced with chunks_per_source 3 for stronger evidence per source."
    ),
    action_label="Searches the web.",
)

extract = _tavily(
    name="extract",
    args_schema=ExtractRequest,
    method="POST",
    url_template="extract",
    description=(
        "Extract clean markdown or text from one or more known URLs. Use after "
        "search when the URL is already selected."
    ),
    action_label="Extracts content from URLs.",
    # Documented extract timeout is 1–60s; the factory default of 20s would
    # abort an `advanced` extraction before Tavily does.
    timeout_override=65,
)

crawl = _tavily(
    name="crawl",
    args_schema=CrawlRequest,
    method="POST",
    url_template="crawl",
    description=(
        "Graph-based website traversal with built-in extraction. Use when many "
        "pages on a site need to be read."
    ),
    action_label="Crawls a website and extracts pages.",
    # Documented crawl timeout is 10–150s (server default 150).
    timeout_override=160,
)

map = _tavily(  # noqa: A001 — the API's own name for this endpoint
    name="map",
    args_schema=MapRequest,
    method="POST",
    url_template="map",
    description=(
        "Discover URLs on a site without extracting content. Use before crawl "
        "to understand site structure."
    ),
    action_label="Maps URLs on a website.",
    timeout_override=160,
)

research_create = _tavily(
    name="research_create",
    args_schema=ResearchCreateRequest,
    method="POST",
    url_template="research",
    description=(
        "Create an async research task that searches, analyzes sources, and "
        "generates a cited report. Poll results with research_get."
    ),
    action_label="Starts a research task.",
)

research_get = _tavily(
    name="research_get",
    args_schema=ResearchGetRequest,
    method="GET",
    url_template="research/{request_id}",
    description=(
        "Retrieve the status and results of a research task by request_id. "
        "HTTP 202 means still running; poll until HTTP 200."
    ),
    action_label="Gets research task results.",
)

usage = _tavily(
    name="usage",
    args_schema=UsageGetRequest,
    method="GET",
    url_template="usage",
    description=(
        "Get API key and account usage for the current billing cycle, broken down by endpoint type."
    ),
    action_label="Shows API usage.",
)

logs = _tavily(
    name="logs",
    args_schema=LogsRequest,
    method="POST",
    url_template="logs",
    description=(
        "Retrieve per-request usage logs for API keys under your account. "
        "Requires a paid plan or pay-as-you-go. Logs never include request "
        "input or output."
    ),
    action_label="Lists API usage logs.",
    # Tavily requires a JSON body even when every field is omitted; Charter
    # otherwise sends nothing and the API answers 422.
    static_body={},
)

org_usage = _tavily(
    name="org_usage",
    args_schema=OrgUsageRequest,
    method="POST",
    url_template="org-usage",
    description=(
        "Retrieve organization-wide usage, PayGo USD cost, and request counts "
        "across all API keys. Enterprise-only; authenticate with the org "
        "owner's personal API key."
    ),
    action_label="Shows organization usage.",
)

TOOLS: list[Tool] = [
    search,
    extract,
    crawl,
    map,
    research_create,
    research_get,
    usage,
    logs,
    org_usage,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "QUOTA_DOC_URL",
    "search",
    "extract",
    "crawl",
    "map",
    "research_create",
    "research_get",
    "usage",
    "logs",
    "org_usage",
]
