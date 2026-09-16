"""Response models for the Firecrawl /search endpoint.

All fields use Mode("response_only") — they are populated by the API response
and never sent in requests. The LLM reads these rich typed models; the framework
handles wire-format conversion transparently.

API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
"""
from __future__ import annotations

from typing import Annotated, List, Optional

from pydantic import BaseModel, Field

from charter.types import Mode

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

class SearchResultMetadata(BaseModel):
    """Metadata associated with a scraped search result page.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    title: Annotated[Optional[str], Field(None, description="Title of the page"), Mode("response_only")]
    description: Annotated[Optional[str], Field(None, description="Description of the page"), Mode("response_only")]
    source_url: Annotated[Optional[str], Field(None, description="The original URL that was requested. May differ from the page's final URL if redirects occurred."), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="The final URL of the page after all redirects have been followed."), Mode("response_only")]
    status_code: Annotated[Optional[int], Field(None, description="HTTP status code of the response"), Mode("response_only")]
    error: Annotated[Optional[str], Field(None, description="Error message if the page could not be scraped"), Mode("response_only")]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class WebResult(BaseModel):
    """A single web search result, optionally with scraped content.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    title: Annotated[Optional[str], Field(None, description="Title from search result"), Mode("response_only")]
    description: Annotated[Optional[str], Field(None, description="Description from search result"), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="URL of the search result"), Mode("response_only")]
    markdown: Annotated[Optional[str], Field(None, description="Markdown content if scraping was requested"), Mode("response_only")]
    html: Annotated[Optional[str], Field(None, description="HTML content if requested in formats"), Mode("response_only")]
    raw_html: Annotated[Optional[str], Field(None, description="Raw HTML content if requested in formats"), Mode("response_only")]
    links: Annotated[Optional[List[str]], Field(None, description="Links found if requested in formats"), Mode("response_only")]
    screenshot: Annotated[Optional[str], Field(None, description="Screenshot URL if requested in formats. Screenshots expire after 24 hours and can no longer be downloaded."), Mode("response_only")]
    metadata: Annotated[Optional[SearchResultMetadata], Field(None, description="Metadata about the scraped page"), Mode("response_only")]


class ImageResult(BaseModel):
    """A single image search result.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    title: Annotated[Optional[str], Field(None, description="Title from search result"), Mode("response_only")]
    image_url: Annotated[Optional[str], Field(None, description="URL of the image"), Mode("response_only")]
    image_width: Annotated[Optional[int], Field(None, description="Width of the image"), Mode("response_only")]
    image_height: Annotated[Optional[int], Field(None, description="Height of the image"), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="URL of the search result"), Mode("response_only")]
    position: Annotated[Optional[int], Field(None, description="Position of the search result"), Mode("response_only")]


class NewsResult(BaseModel):
    """A single news search result, optionally with scraped content.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    title: Annotated[Optional[str], Field(None, description="Title of the article"), Mode("response_only")]
    snippet: Annotated[Optional[str], Field(None, description="Snippet from the article"), Mode("response_only")]
    url: Annotated[Optional[str], Field(None, description="URL of the article"), Mode("response_only")]
    date: Annotated[Optional[str], Field(None, description="Date of the article"), Mode("response_only")]
    image_url: Annotated[Optional[str], Field(None, description="Image URL of the article"), Mode("response_only")]
    position: Annotated[Optional[int], Field(None, description="Position of the article"), Mode("response_only")]
    markdown: Annotated[Optional[str], Field(None, description="Markdown content if scraping was requested"), Mode("response_only")]
    html: Annotated[Optional[str], Field(None, description="HTML content if requested in formats"), Mode("response_only")]
    raw_html: Annotated[Optional[str], Field(None, description="Raw HTML content if requested in formats"), Mode("response_only")]
    links: Annotated[Optional[List[str]], Field(None, description="Links found if requested in formats"), Mode("response_only")]
    screenshot: Annotated[Optional[str], Field(None, description="Screenshot URL if requested in formats. Screenshots expire after 24 hours and can no longer be downloaded."), Mode("response_only")]
    metadata: Annotated[Optional[SearchResultMetadata], Field(None, description="Metadata about the scraped page"), Mode("response_only")]


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class SearchData(BaseModel):
    """Container for all search result arrays, keyed by source type.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    web: Annotated[Optional[List[WebResult]], Field(None, description="The search results. The arrays available will depend on the sources you specified in the request. By default, the `web` array will be returned."), Mode("response_only")]
    images: Annotated[Optional[List[ImageResult]], Field(None, description="Image search results. Only present when 'images' is included in sources."), Mode("response_only")]
    news: Annotated[Optional[List[NewsResult]], Field(None, description="News search results. Only present when 'news' is included in sources."), Mode("response_only")]


class SearchResponse(BaseModel):
    """Root response from the Firecrawl POST /search endpoint.

    API Reference: https://docs.firecrawl.dev/api-reference/endpoint/search
    """
    success: Annotated[Optional[bool], Field(None, description="Whether the search was successful"), Mode("response_only")]
    data: Annotated[Optional[SearchData], Field(None, description="The search results."), Mode("response_only")]
    warning: Annotated[Optional[str], Field(None, description="Warning message if any issues occurred"), Mode("response_only")]
    id: Annotated[Optional[str], Field(None, description="The ID of the search job"), Mode("response_only")]
    credits_used: Annotated[Optional[int], Field(None, description="The number of credits used for the search"), Mode("response_only")]
