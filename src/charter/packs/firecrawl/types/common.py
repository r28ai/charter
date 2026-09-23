# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""Shared request types for Firecrawl scrape, crawl, batch, search, and monitor.

API Reference: https://docs.firecrawl.dev/api-reference/v2-openapi.json
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_serializer

from charter.types import Body, WireName

__all__ = [
    "Viewport",
    "Format",
    "PdfParser",
    "Action",
    "ScrapeLocation",
    "Webhook",
    "WebhookEvent",
    "AuditMetadata",
    "ThreatProtectionOverride",
    "RedactPIIOptions",
    "BrowserProfile",
    "ScrapeOptionsNested",
    "ScrapeOptionsMixin",
    "CrawlTargetOptions",
    "FormatType",
    "ParserItem",
    "RedactPII",
]


FormatType = Literal[
    "markdown",
    "summary",
    "html",
    "rawHtml",
    "rawBase64",
    "links",
    "images",
    "screenshot",
    "json",
    "changeTracking",
    "branding",
    "product",
    "menu",
    "audio",
    "video",
    "question",
    "highlights",
]


class Viewport(BaseModel):
    """Viewport dimensions for screenshot actions or formats."""

    width: int = Field(..., description="The width of the viewport in pixels")
    height: int = Field(..., description="The height of the viewport in pixels")


class Format(BaseModel):
    """An output format. The API also accepts a bare type string in the formats list."""

    type_: Annotated[FormatType, Field(..., alias="type", description="The format type.")]
    full_page: Optional[bool] = Field(
        None,
        description="Whether to capture a full-page screenshot. Only applicable to 'screenshot'.",
    )
    quality: Optional[int] = Field(
        None,
        description="The quality of the screenshot, from 1 to 100. Only applicable to 'screenshot'.",
    )
    viewport: Optional[Viewport] = Field(
        None,
        description="Viewport settings for the screenshot. Only applicable to 'screenshot'.",
    )
    schema_: Optional[dict] = Field(
        None,
        alias="schema",
        description="JSON schema for structured extraction. Only applicable to 'json' and 'changeTracking'.",
    )
    prompt: Optional[str] = Field(
        None,
        description="Prompt for AI-based extraction. Only applicable to 'json', 'summary', and 'changeTracking'.",
    )
    check_prompt_injection: Optional[bool] = Field(
        None,
        description=(
            "Scan page content for prompt injection before JSON extraction. "
            "Fails with 403 / SCRAPE_PROMPT_INJECTION_DETECTED when an injection is detected. "
            "Adds 4 credits when the check runs."
        ),
    )
    modes: Optional[List[Literal["git-diff", "json"]]] = Field(
        None,
        description="Change tracking modes. Only applicable to 'changeTracking'.",
    )
    tag: Optional[str] = Field(
        None,
        description="Tag for change tracking. Only applicable to 'changeTracking'.",
    )
    question: Optional[str] = Field(
        None,
        max_length=10000,
        description="The question to answer about the page. Required when type is 'question'.",
    )
    query: Optional[str] = Field(
        None,
        max_length=10000,
        description="The text-selection query. Required when type is 'highlights'.",
    )


class PdfParser(BaseModel):
    """PDF parser configuration. The parsers list also accepts the bare string 'pdf'."""

    type_: Annotated[
        Literal["pdf"],
        Field(..., alias="type", description="The parser type. Currently only 'pdf' is supported."),
    ]
    mode: Optional[Literal["fast", "auto", "ocr"]] = Field(
        None,
        description=(
            "PDF parsing mode. 'fast': text-based extraction only. "
            "'auto': fast first, OCR fallback. 'ocr': OCR on every page. "
            "The server applies 'auto' when this is absent."
        ),
    )
    max_pages: Optional[int] = Field(
        None,
        ge=1,
        le=10000,
        description="Maximum number of pages to parse from the PDF.",
    )
    pages: Optional[bool] = Field(
        None,
        description="Include physical per-page markdown alongside the document markdown.",
    )
    blocks: Optional[bool] = Field(
        None,
        description="Include per-page typed layout blocks alongside the document markdown.",
    )
    page_markers: Optional[bool] = Field(
        None,
        description="Annotate page breaks in the document markdown.",
    )


ParserItem = Union[Literal["pdf"], PdfParser]


class Action(BaseModel):
    """A browser action to perform on the page before grabbing the content."""

    type_: Annotated[
        Literal[
            "wait",
            "screenshot",
            "click",
            "write",
            "press",
            "scroll",
            "scrape",
            "executeJavascript",
            "pdf",
        ],
        Field(..., alias="type", description="The action type."),
    ]
    milliseconds: Optional[int] = Field(
        None, ge=1, description="Number of milliseconds to wait. Only applicable to 'wait'."
    )
    selector: Optional[str] = Field(None, description="CSS selector for the target element.")
    full_page: Optional[bool] = Field(
        None, description="Whether to capture a full-page screenshot."
    )
    quality: Optional[int] = Field(
        None, description="The quality of the screenshot, from 1 to 100."
    )
    viewport: Optional[Viewport] = Field(None, description="Viewport settings for the screenshot.")
    all: Optional[bool] = Field(None, description="Clicks all elements matched by the selector.")
    text: Optional[str] = Field(None, description="Text to type into the element.")
    key: Optional[str] = Field(None, description="Key to press (e.g. 'Enter', 'Tab').")
    direction: Optional[Literal["up", "down"]] = Field(None, description="Direction to scroll.")
    script: Optional[str] = Field(None, description="JavaScript code to execute on the page.")
    format: Optional[
        Literal["A0", "A1", "A2", "A3", "A4", "A5", "A6", "Letter", "Legal", "Tabloid", "Ledger"]
    ] = Field(
        None,
        description="The page size of the resulting PDF. The server applies 'Letter' when this is absent.",
    )
    landscape: Optional[bool] = Field(
        None, description="Whether to generate the PDF in landscape orientation."
    )
    scale: Optional[float] = Field(None, description="The scale multiplier of the resulting PDF.")


class ScrapeLocation(BaseModel):
    """Geographic location settings for the scrape request."""

    country: Optional[str] = Field(
        None,
        pattern=r"^[A-Z]{2}$",
        description="ISO 3166-1 alpha-2 country code (e.g., 'US', 'AU', 'DE', 'JP'). The server applies 'US' when this is absent.",
    )
    languages: Optional[List[str]] = Field(
        None,
        description="Preferred languages and locales for the request in order of priority.",
    )


class AuditMetadata(BaseModel):
    """User attribution included with SIEM logging events when SIEM is enabled."""

    username: str = Field(
        ..., max_length=1024, description="The username associated with the request."
    )


class ThreatProtectionOverride(BaseModel):
    """Per-request threat protection override. Enterprise feature."""

    mode: Optional[Literal["off", "normal"]] = Field(
        None,
        description="URL scanning mode for this request. If Threat Protection is enforced, mode may not be 'off'.",
    )
    risk_score_threshold: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Normalized risk score (0-100) at or above which a classifier verdict blocks the URL.",
    )
    blacklist: Optional[List[str]] = Field(
        None,
        max_length=1000,
        description="Domains to always block, as plain domains or wildcard globs.",
    )
    whitelist: Optional[List[str]] = Field(
        None,
        max_length=1000,
        description="Domains to always allow. Wins over every other rule.",
    )
    blocked_tlds: Optional[List[str]] = Field(
        None,
        max_length=1000,
        description="Top-level domains to block outright, lowercase without the leading dot.",
    )
    failure_policy: Optional[Literal["open", "closed"]] = Field(
        None,
        description="What to do when the classifier cannot be reached.",
    )


class RedactPIIOptions(BaseModel):
    """Tuning options for PII redaction."""

    mode: Optional[Literal["accurate", "aggressive", "fast"]] = Field(
        None,
        description="Redaction strategy. The server applies 'accurate' when this is absent.",
    )
    entities: Optional[
        List[Literal["PERSON", "EMAIL", "PHONE", "LOCATION", "FINANCIAL", "SECRET"]]
    ] = Field(
        None,
        description="Restrict redaction to these entity buckets. If omitted, all supported entities are redacted.",
    )
    replace_style: Optional[Literal["tag", "mask", "remove"]] = Field(
        None,
        description="Replacement style. The server applies 'tag' when this is absent.",
    )


RedactPII = Union[bool, RedactPIIOptions]


class BrowserProfile(BaseModel):
    """Persistent browser storage across scrape and interact sessions."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="A name for the profile. Sessions with the same name share storage.",
    )
    save_changes: Optional[bool] = Field(
        None,
        description="When true, browser state is saved back to the profile on close. The server applies true when this is absent.",
    )


WebhookEvent = Literal["completed", "page", "failed", "started"]


class Webhook(BaseModel):
    """Webhook specification for crawl or batch scrape jobs."""

    url: str = Field(..., description="The URL to send the webhook to.")
    headers: Optional[Dict[str, str]] = Field(
        None, description="Headers to send to the webhook URL."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom metadata that will be included in all webhook payloads.",
    )
    events: Optional[List[WebhookEvent]] = Field(
        None,
        description="Type of events that should be sent to the webhook URL. The server sends all events when this is absent.",
    )


class ScrapeOptionsNested(BaseModel):
    """Nested scrape options used by search, crawl, and monitor targets."""

    formats: Optional[List[Union[FormatType, Format]]] = Field(
        None,
        description="Output formats to include in the response. Strings or objects. The server applies markdown when this is absent.",
    )
    only_main_content: Optional[bool] = Field(
        None,
        description="Only return the main content of the page excluding headers, navs, footers, etc. The server applies true when this is absent.",
    )
    only_clean_content: Optional[bool] = Field(
        None,
        description="Beta. LLM pass over markdown to remove residual boilerplate that onlyMainContent can miss.",
    )
    include_tags: Optional[List[str]] = Field(None, description="Tags to include in the output.")
    exclude_tags: Optional[List[str]] = Field(None, description="Tags to exclude from the output.")
    max_age: Optional[int] = Field(
        None,
        description="Returns a cached version of the page if it is younger than this age in milliseconds. The server applies 172800000 (2 days) when this is absent.",
    )
    min_age: Optional[int] = Field(
        None,
        description="When set, the request only checks the cache and never triggers a fresh scrape.",
    )
    headers: Optional[Dict[str, str]] = Field(None, description="Headers to send with the request.")
    wait_for: Optional[int] = Field(
        None,
        description="Specify a delay in milliseconds before fetching the content. The server applies 0 when this is absent.",
    )
    mobile: Optional[bool] = Field(None, description="Emulate scraping from a mobile device.")
    skip_tls_verification: Optional[bool] = Field(
        None, description="Skip TLS certificate verification when making requests."
    )
    timeout: Optional[int] = Field(
        None,
        ge=1000,
        le=300000,
        description="Timeout in milliseconds. The server applies 60000 when this is absent.",
    )
    parsers: Optional[List[ParserItem]] = Field(
        None, description="Controls how files are processed during scraping."
    )
    actions: Optional[List[Action]] = Field(
        None, description="Actions to perform on the page before grabbing the content."
    )
    location: Optional[ScrapeLocation] = Field(
        None, description="Location settings for the request."
    )
    remove_base64_images: Optional[bool] = Field(
        None, description="Removes all base64 images from the markdown output."
    )
    block_ads: Optional[bool] = Field(
        None, description="Enables ad-blocking and cookie popup blocking."
    )
    proxy: Optional[Literal["basic", "enhanced", "auto"]] = Field(
        None, description="Specifies the type of proxy to use."
    )
    store_in_cache: Optional[bool] = Field(
        None, description="If true, the page will be stored in the Firecrawl index and cache."
    )
    lockdown: Optional[bool] = Field(
        None,
        description="Serve from cache only and never make an outbound request. On miss, returns 404 SCRAPE_LOCKDOWN_CACHE_MISS.",
    )
    redact_pii: Annotated[
        Optional[RedactPII],
        Field(
            None,
            description="Redact personally identifiable information from returned markdown. Pass true for defaults, or an object to tune it.",
        ),
        WireName("redactPII"),
    ]
    profile: Optional[BrowserProfile] = Field(
        None,
        description="Persistent browser storage across scrape and interact sessions.",
    )
    threat_protection: Optional[ThreatProtectionOverride] = Field(
        None,
        description="Per-request threat protection override. Enterprise feature.",
    )
    audit_metadata: Optional[AuditMetadata] = Field(
        None,
        description="User attribution included with SIEM logging events when SIEM is enabled.",
    )

    @model_serializer(mode="wrap")
    def _redact_pii_on_the_wire(self, handler):
        """``redact_pii`` camelCases to ``redactPii``; the API documents ``redactPII``.

        Nested scrape options are converted with the factory camelCase only —
        ``WireName`` is applied at the top-level request schema — so the dump
        has to spell the key before conversion runs.
        """
        data = handler(self)
        if isinstance(data, dict) and "redact_pii" in data:
            data["redactPII"] = data.pop("redact_pii")
        return data


class ScrapeOptionsMixin(BaseModel):
    """Scrape option fields merged at the top level of scrape and batch scrape bodies."""

    formats: Annotated[
        Optional[List[Union[FormatType, Format]]],
        Field(
            None,
            description="Output formats to include in the response. Strings or objects. The server applies markdown when this is absent.",
        ),
        Body(),
    ]
    only_main_content: Annotated[
        Optional[bool],
        Field(
            None,
            description="Only return the main content of the page excluding headers, navs, footers, etc. The server applies true when this is absent.",
        ),
        Body(),
    ]
    only_clean_content: Annotated[
        Optional[bool],
        Field(
            None,
            description="Beta. LLM pass over markdown to remove residual boilerplate that onlyMainContent can miss.",
        ),
        Body(),
    ]
    include_tags: Annotated[
        Optional[List[str]], Field(None, description="Tags to include in the output."), Body()
    ]
    exclude_tags: Annotated[
        Optional[List[str]], Field(None, description="Tags to exclude from the output."), Body()
    ]
    max_age: Annotated[
        Optional[int],
        Field(
            None,
            description="Returns a cached version of the page if it is younger than this age in milliseconds. The server applies 172800000 (2 days) when this is absent.",
        ),
        Body(),
    ]
    min_age: Annotated[
        Optional[int],
        Field(
            None,
            description="When set, the request only checks the cache and never triggers a fresh scrape.",
        ),
        Body(),
    ]
    headers: Annotated[
        Optional[Dict[str, str]],
        Field(None, description="Headers to send with the request."),
        Body(),
    ]
    wait_for: Annotated[
        Optional[int],
        Field(
            None,
            description="Specify a delay in milliseconds before fetching the content. The server applies 0 when this is absent.",
        ),
        Body(),
    ]
    mobile: Annotated[
        Optional[bool],
        Field(None, description="Emulate scraping from a mobile device."),
        Body(),
    ]
    skip_tls_verification: Annotated[
        Optional[bool],
        Field(None, description="Skip TLS certificate verification when making requests."),
        Body(),
    ]
    timeout: Annotated[
        Optional[int],
        Field(
            None,
            ge=1000,
            le=300000,
            description="Timeout in milliseconds. The server applies 60000 when this is absent.",
        ),
        Body(),
    ]
    parsers: Annotated[
        Optional[List[ParserItem]],
        Field(None, description="Controls how files are processed during scraping."),
        Body(),
    ]
    actions: Annotated[
        Optional[List[Action]],
        Field(None, description="Actions to perform on the page before grabbing the content."),
        Body(),
    ]
    location: Annotated[
        Optional[ScrapeLocation],
        Field(None, description="Location settings for the request."),
        Body(),
    ]
    remove_base64_images: Annotated[
        Optional[bool],
        Field(None, description="Removes all base64 images from the markdown output."),
        Body(),
    ]
    block_ads: Annotated[
        Optional[bool],
        Field(None, description="Enables ad-blocking and cookie popup blocking."),
        Body(),
    ]
    proxy: Annotated[
        Optional[Literal["basic", "enhanced", "auto"]],
        Field(None, description="Specifies the type of proxy to use."),
        Body(),
    ]
    store_in_cache: Annotated[
        Optional[bool],
        Field(
            None, description="If true, the page will be stored in the Firecrawl index and cache."
        ),
        Body(),
    ]
    lockdown: Annotated[
        Optional[bool],
        Field(
            None,
            description="Serve from cache only and never make an outbound request. On miss, returns 404 SCRAPE_LOCKDOWN_CACHE_MISS.",
        ),
        Body(),
    ]
    redact_pii: Annotated[
        Optional[RedactPII],
        Field(
            None,
            description="Redact personally identifiable information from returned markdown. Pass true for defaults, or an object to tune it.",
        ),
        Body(),
        WireName("redactPII"),
    ]
    profile: Annotated[
        Optional[BrowserProfile],
        Field(None, description="Persistent browser storage across scrape and interact sessions."),
        Body(),
    ]
    threat_protection: Annotated[
        Optional[ThreatProtectionOverride],
        Field(None, description="Per-request threat protection override. Enterprise feature."),
        Body(),
    ]
    audit_metadata: Annotated[
        Optional[AuditMetadata],
        Field(
            None,
            description="User attribution included with SIEM logging events when SIEM is enabled.",
        ),
        Body(),
    ]


class CrawlTargetOptions(BaseModel):
    """Crawl options attached to a monitor crawl target."""

    limit: Optional[int] = Field(None, description="Maximum number of pages to crawl.")
    max_depth: Optional[int] = Field(None, description="Maximum crawl depth.")
    include_paths: Optional[List[str]] = Field(
        None, description="URL pathname regex patterns to include."
    )
    exclude_paths: Optional[List[str]] = Field(
        None, description="URL pathname regex patterns to exclude."
    )
