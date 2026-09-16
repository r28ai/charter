"""
Firecrawl — search, scrape, crawl, map, monitor, and interact with the web.

An API-key pack: authentication is a static bearer header, so there is no
credential provider, just a key.

    from charter.packs import firecrawl

    firecrawl.configure(api_key="fc-...")
    await firecrawl.scrape.ainvoke(url="https://example.com")

``configure()`` is optional if ``$FIRECRAWL_API_KEY`` is set. Headers are
resolved per request, so configuring after the tools are built works, and an
unconfigured call raises ``CredentialError`` before anything is sent.

The wire uses camelCase for JSON bodies and query parameters.

Failure is usually an HTTP status code with ``{"error": "..."}``, but many
endpoints also answer HTTP 200 with ``{"success": false, "error": "..."}``.
That second shape is declared once as :data:`FIRECRAWL_ENVELOPE` on the
factory.

``parse`` is not exposed: it requires ``multipart/form-data`` file upload,
which Charter's wire contract does not encode today (same constraint as
Notion file uploads).
"""

from __future__ import annotations

from charter.factories import api_key_tool_factory
from charter.packs._config import DeferredApiKeyHeaders, api_key_headers
from charter.packs.firecrawl.response_handlers import (
    extract_map,
    extract_scrape,
    extract_search,
)
from charter.packs.firecrawl.types.account import (
    ActivityListRequest,
    CreditUsageGetRequest,
    HistoricalCreditUsageGetRequest,
    HistoricalTokenUsageGetRequest,
    QueueStatusGetRequest,
    ThreatProtectionGetRequest,
    ThreatProtectionUpdateRequest,
    TokenUsageGetRequest,
)
from charter.packs.firecrawl.types.batch import (
    BatchScrapeCancelRequest,
    BatchScrapeErrorsRequest,
    BatchScrapeRequest,
    BatchScrapeStatusRequest,
)
from charter.packs.firecrawl.types.crawl import (
    CrawlActiveRequest,
    CrawlCancelRequest,
    CrawlErrorsRequest,
    CrawlParamsPreviewRequest,
    CrawlRequest,
    CrawlStatusRequest,
)
from charter.packs.firecrawl.types.developer import DeveloperSearchRequest
from charter.packs.firecrawl.types.extract import ExtractRequest, ExtractStatusRequest
from charter.packs.firecrawl.types.interact import (
    InteractCreateRequest,
    InteractDeleteRequest,
    InteractExecuteRequest,
    InteractListRequest,
)
from charter.packs.firecrawl.types.map.actions import MapRequest
from charter.packs.firecrawl.types.monitor import (
    MonitorCheckGetRequest,
    MonitorChecksListRequest,
    MonitorCreateRequest,
    MonitorDeleteRequest,
    MonitorGetRequest,
    MonitorListRequest,
    MonitorRunRequest,
    MonitorUpdateRequest,
)
from charter.packs.firecrawl.types.research import (
    ResearchPaperGetRequest,
    ResearchPapersSearchRequest,
    ResearchSimilarPapersRequest,
)
from charter.packs.firecrawl.types.scrape.actions import ScrapeRequest, ScrapeStatusRequest
from charter.packs.firecrawl.types.scrape.interact_actions import (
    ScrapeInteractRequest,
    ScrapeInteractStopRequest,
)
from charter.packs.firecrawl.types.search.actions import (
    SearchFeedbackRequest,
    SearchRequest,
)
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.pagination import Pagination

BASE_URL = "https://api.firecrawl.dev/v2/"
QUOTA_DOC_URL = "https://docs.firecrawl.dev/rate-limits"

_headers: DeferredApiKeyHeaders = api_key_headers(
    "firecrawl",
    {"Authorization": "Bearer CHARTER_UNCONFIGURED"},
    "Authorization",
    "FIRECRAWL_API_KEY",
)

FIRECRAWL_ENVELOPE = Envelope(ok_field="success", error_field="error")

ACTIVITY_PAGINATION = Pagination(
    cursor_field="cursor",
    cursor_param="cursor",
    more_field="has_more",
)


def configure(api_key: str) -> None:
    """Supply the Firecrawl API key for this pack's tools."""
    _headers.configure(api_key)


_firecrawl = api_key_tool_factory(
    pack="firecrawl",
    base_url=BASE_URL,
    api_key_headers=_headers,
    body_case="camel",
    query_case="camel",
    envelope=FIRECRAWL_ENVELOPE,
)

search = _firecrawl(
    name="search",
    args_schema=SearchRequest,
    method="POST",
    url_template="search",
    description=(
        "Search and optionally scrape web results. Use for current events, factual "
        "lookups, news, and any question that benefits from real-time web results. "
        "Supports web, image, and news sources. Include scrapeOptions with formats "
        "to get full page content."
    ),
    action_label="Searches the web for information.",
    response_handler=extract_search,
)

search_feedback = _firecrawl(
    name="search_feedback",
    args_schema=SearchFeedbackRequest,
    method="POST",
    url_template="search/{job_id}/feedback",
    description="Submit feedback for a prior search job to improve future results.",
    action_label="Submits search feedback.",
)

map = _firecrawl(  # noqa: A001 — the API's own name for this endpoint
    name="map",
    args_schema=MapRequest,
    method="POST",
    url_template="map",
    description=(
        "Discover and list all URLs of a website starting from a base URL. "
        "Use when the user wants to explore a site's structure or find specific pages."
    ),
    action_label="Maps all URLs on a website.",
    response_handler=extract_map,
)

scrape = _firecrawl(
    name="scrape",
    args_schema=ScrapeRequest,
    method="POST",
    url_template="scrape",
    description=(
        "Scrape a single URL and optionally extract information. Use when the user "
        "wants to read or summarize a specific webpage. Supports markdown, HTML, "
        "screenshots, and structured JSON extraction."
    ),
    action_label="Scrapes a URL and returns its content.",
    response_handler=extract_scrape,
)

scrape_status = _firecrawl(
    name="scrape_status",
    args_schema=ScrapeStatusRequest,
    method="GET",
    url_template="scrape/{job_id}",
    description="Get the status of a scrape job by job ID.",
    action_label="Gets scrape job status.",
    response_handler=extract_scrape,
)

batch_scrape = _firecrawl(
    name="batch_scrape",
    args_schema=BatchScrapeRequest,
    method="POST",
    url_template="batch/scrape",
    description="Scrape multiple URLs in one batch job. Poll status with batch_scrape_status.",
    action_label="Starts a batch scrape job.",
)

batch_scrape_status = _firecrawl(
    name="batch_scrape_status",
    args_schema=BatchScrapeStatusRequest,
    method="GET",
    url_template="batch/scrape/{id}",
    description="Get the status and results of a batch scrape job.",
    action_label="Gets batch scrape status.",
    response_handler=extract_scrape,
)

batch_scrape_cancel = _firecrawl(
    name="batch_scrape_cancel",
    args_schema=BatchScrapeCancelRequest,
    method="DELETE",
    url_template="batch/scrape/{id}",
    description="Cancel a running batch scrape job.",
    action_label="Cancels a batch scrape job.",
)

batch_scrape_errors = _firecrawl(
    name="batch_scrape_errors",
    args_schema=BatchScrapeErrorsRequest,
    method="GET",
    url_template="batch/scrape/{id}/errors",
    description="Get per-URL errors from a batch scrape job.",
    action_label="Gets batch scrape errors.",
)

scrape_interact = _firecrawl(
    name="scrape_interact",
    args_schema=ScrapeInteractRequest,
    method="POST",
    url_template="scrape/{job_id}/interact",
    description="Execute code in the browser sandbox associated with a scrape job.",
    action_label="Interacts with a scraped page.",
)

scrape_interact_stop = _firecrawl(
    name="scrape_interact_stop",
    args_schema=ScrapeInteractStopRequest,
    method="DELETE",
    url_template="scrape/{job_id}/interact",
    description="Stop the interactive browser session associated with a scrape job.",
    action_label="Stops interacting with a scraped page.",
)

interact_create = _firecrawl(
    name="interact_create",
    args_schema=InteractCreateRequest,
    method="POST",
    url_template="interact",
    description="Create a browser sandbox interact session for code execution.",
    action_label="Creates an interact session.",
    # The body is required and every field is optional; Charter otherwise sends
    # no body and the API rejects the request.
    static_body={},
)

interact_execute = _firecrawl(
    name="interact_execute",
    args_schema=InteractExecuteRequest,
    method="POST",
    url_template="interact/{session_id}/execute",
    description="Execute Python, Node, or bash code in an interact session.",
    action_label="Executes code in an interact session.",
)

interact_list = _firecrawl(
    name="interact_list",
    args_schema=InteractListRequest,
    method="GET",
    url_template="interact",
    description="List browser sandbox interact sessions for the authenticated team.",
    action_label="Lists interact sessions.",
)

interact_delete = _firecrawl(
    name="interact_delete",
    args_schema=InteractDeleteRequest,
    method="DELETE",
    url_template="interact/{session_id}",
    description="Delete an interact session and stop billing for it.",
    action_label="Deletes an interact session.",
)

research_papers_search = _firecrawl(
    name="research_papers_search",
    args_schema=ResearchPapersSearchRequest,
    method="GET",
    url_template="search/research/papers",
    description="Search the research paper index with natural-language queries.",
    action_label="Searches research papers.",
)

research_paper_get = _firecrawl(
    name="research_paper_get",
    args_schema=ResearchPaperGetRequest,
    method="GET",
    url_template="search/research/papers/{id}",
    description="Inspect metadata or read passages from a research paper.",
    action_label="Reads a research paper.",
)

research_similar_papers = _firecrawl(
    name="research_similar_papers",
    args_schema=ResearchSimilarPapersRequest,
    method="GET",
    url_template="search/research/papers/{id}/similar",
    description="Find related papers by semantic intent and structural mode.",
    action_label="Finds related research papers.",
)

developer_search = _firecrawl(
    name="developer_search",
    args_schema=DeveloperSearchRequest,
    method="GET",
    url_template="search/developer",
    description="Search Firecrawl docs, issues, pull requests, and repository readmes.",
    action_label="Searches the developer index.",
)

crawl = _firecrawl(
    name="crawl",
    args_schema=CrawlRequest,
    method="POST",
    url_template="crawl",
    description="Recursively crawl a website and scrape each discovered page.",
    action_label="Starts a crawl job.",
)

crawl_status = _firecrawl(
    name="crawl_status",
    args_schema=CrawlStatusRequest,
    method="GET",
    url_template="crawl/{id}",
    description="Get the status and results of a crawl job.",
    action_label="Gets crawl status.",
    response_handler=extract_scrape,
)

crawl_params_preview = _firecrawl(
    name="crawl_params_preview",
    args_schema=CrawlParamsPreviewRequest,
    method="POST",
    url_template="crawl/params-preview",
    description="Preview crawl parameters generated from a natural language prompt.",
    action_label="Previews crawl parameters.",
)

crawl_cancel = _firecrawl(
    name="crawl_cancel",
    args_schema=CrawlCancelRequest,
    method="DELETE",
    url_template="crawl/{id}",
    description="Cancel a running crawl job.",
    action_label="Cancels a crawl job.",
)

crawl_errors = _firecrawl(
    name="crawl_errors",
    args_schema=CrawlErrorsRequest,
    method="GET",
    url_template="crawl/{id}/errors",
    description="Get per-URL errors from a crawl job.",
    action_label="Gets crawl errors.",
)

crawl_active = _firecrawl(
    name="crawl_active",
    args_schema=CrawlActiveRequest,
    method="GET",
    url_template="crawl/active",
    description="List all active crawl jobs for the authenticated team.",
    action_label="Lists active crawls.",
)

extract = _firecrawl(
    name="extract",
    args_schema=ExtractRequest,
    method="POST",
    url_template="extract",
    description=(
        "Extract structured data from one or more URLs using an LLM. "
        "Poll results with extract_status."
    ),
    action_label="Starts an extract job.",
)

extract_status = _firecrawl(
    name="extract_status",
    args_schema=ExtractStatusRequest,
    method="GET",
    url_template="extract/{id}",
    description="Get the status and results of an extract job.",
    action_label="Gets extract job status.",
)

monitor_create = _firecrawl(
    name="monitor_create",
    args_schema=MonitorCreateRequest,
    method="POST",
    url_template="monitor",
    description="Create a scheduled monitor for scrape, crawl, or search targets.",
    action_label="Creates a monitor.",
)

monitor_list = _firecrawl(
    name="monitor_list",
    args_schema=MonitorListRequest,
    method="GET",
    url_template="monitor",
    description="List monitors for the authenticated team.",
    action_label="Lists monitors.",
)

monitor_get = _firecrawl(
    name="monitor_get",
    args_schema=MonitorGetRequest,
    method="GET",
    url_template="monitor/{monitor_id}",
    description="Get a monitor by ID.",
    action_label="Gets a monitor.",
)

monitor_update = _firecrawl(
    name="monitor_update",
    args_schema=MonitorUpdateRequest,
    method="PATCH",
    url_template="monitor/{monitor_id}",
    description="Update a monitor's schedule, targets, or status.",
    action_label="Updates a monitor.",
)

monitor_delete = _firecrawl(
    name="monitor_delete",
    args_schema=MonitorDeleteRequest,
    method="DELETE",
    url_template="monitor/{monitor_id}",
    description="Delete a monitor.",
    action_label="Deletes a monitor.",
)

monitor_run = _firecrawl(
    name="monitor_run",
    args_schema=MonitorRunRequest,
    method="POST",
    url_template="monitor/{monitor_id}/run",
    description="Queue an immediate monitor check outside the schedule.",
    action_label="Runs a monitor.",
)

monitor_checks_list = _firecrawl(
    name="monitor_checks_list",
    args_schema=MonitorChecksListRequest,
    method="GET",
    url_template="monitor/{monitor_id}/checks",
    description="List checks for a monitor.",
    action_label="Lists monitor checks.",
)

monitor_check_get = _firecrawl(
    name="monitor_check_get",
    args_schema=MonitorCheckGetRequest,
    method="GET",
    url_template="monitor/{monitor_id}/checks/{check_id}",
    description="Get a monitor check with optional page-level results.",
    action_label="Gets a monitor check.",
)

activity = _firecrawl(
    name="activity",
    args_schema=ActivityListRequest,
    method="GET",
    url_template="team/activity",
    description="List recent API activity for the authenticated team.",
    action_label="Lists API activity.",
    pagination_override=ACTIVITY_PAGINATION,
)

credit_usage = _firecrawl(
    name="credit_usage",
    args_schema=CreditUsageGetRequest,
    method="GET",
    url_template="team/credit-usage",
    description="Get remaining credits and billing period for the authenticated team.",
    action_label="Shows credit usage.",
)

historical_credit_usage = _firecrawl(
    name="historical_credit_usage",
    args_schema=HistoricalCreditUsageGetRequest,
    method="GET",
    url_template="team/credit-usage/historical",
    description="Get historical credit usage by billing period.",
    action_label="Shows historical credit usage.",
)

token_usage = _firecrawl(
    name="token_usage",
    args_schema=TokenUsageGetRequest,
    method="GET",
    url_template="team/token-usage",
    description="Get remaining extract tokens for the authenticated team.",
    action_label="Shows extract token usage.",
)

historical_token_usage = _firecrawl(
    name="historical_token_usage",
    args_schema=HistoricalTokenUsageGetRequest,
    method="GET",
    url_template="team/token-usage/historical",
    description="Get historical extract token usage by billing period.",
    action_label="Shows historical extract token usage.",
)

queue_status = _firecrawl(
    name="queue_status",
    args_schema=QueueStatusGetRequest,
    method="GET",
    url_template="team/queue-status",
    description="Get metrics about the team's scrape queue.",
    action_label="Shows queue status.",
)

threat_protection_get = _firecrawl(
    name="threat_protection_get",
    args_schema=ThreatProtectionGetRequest,
    method="GET",
    url_template="team/threat-protection",
    description="Get the team's threat protection policy.",
    action_label="Gets threat protection policy.",
)

threat_protection_update = _firecrawl(
    name="threat_protection_update",
    args_schema=ThreatProtectionUpdateRequest,
    method="PUT",
    url_template="team/threat-protection",
    description="Update the team's threat protection policy. Enterprise feature.",
    action_label="Updates threat protection policy.",
)

TOOLS: list[Tool] = [
    search,
    search_feedback,
    map,
    scrape,
    scrape_status,
    batch_scrape,
    batch_scrape_status,
    batch_scrape_cancel,
    batch_scrape_errors,
    scrape_interact,
    scrape_interact_stop,
    interact_create,
    interact_execute,
    interact_list,
    interact_delete,
    research_papers_search,
    research_paper_get,
    research_similar_papers,
    developer_search,
    crawl,
    crawl_status,
    crawl_params_preview,
    crawl_cancel,
    crawl_errors,
    crawl_active,
    extract,
    extract_status,
    monitor_create,
    monitor_list,
    monitor_get,
    monitor_update,
    monitor_delete,
    monitor_run,
    monitor_checks_list,
    monitor_check_get,
    activity,
    credit_usage,
    historical_credit_usage,
    token_usage,
    historical_token_usage,
    queue_status,
    threat_protection_get,
    threat_protection_update,
]

__all__ = [
    "TOOLS",
    "configure",
    "BASE_URL",
    "QUOTA_DOC_URL",
    "FIRECRAWL_ENVELOPE",
    "ACTIVITY_PAGINATION",
    "search",
    "search_feedback",
    "map",
    "scrape",
    "scrape_status",
    "batch_scrape",
    "batch_scrape_status",
    "batch_scrape_cancel",
    "batch_scrape_errors",
    "scrape_interact",
    "scrape_interact_stop",
    "interact_create",
    "interact_execute",
    "interact_list",
    "interact_delete",
    "research_papers_search",
    "research_paper_get",
    "research_similar_papers",
    "developer_search",
    "crawl",
    "crawl_status",
    "crawl_params_preview",
    "crawl_cancel",
    "crawl_errors",
    "crawl_active",
    "extract",
    "extract_status",
    "monitor_create",
    "monitor_list",
    "monitor_get",
    "monitor_update",
    "monitor_delete",
    "monitor_run",
    "monitor_checks_list",
    "monitor_check_get",
    "activity",
    "credit_usage",
    "historical_credit_usage",
    "token_usage",
    "historical_token_usage",
    "queue_status",
    "threat_protection_get",
    "threat_protection_update",
]
