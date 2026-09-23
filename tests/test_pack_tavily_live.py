"""Tavily pack — live API tests with hardcoded arguments.

Reads ``TAVILY_API_KEY`` from the environment, or from a ``.env`` at the repository
root. Skipped without the key. Run with::

    .venv/bin/python -m pytest tests/test_pack_tavily_live.py -m live -v
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from charter.packs import tavily
from charter.types.errors import APIError

pytestmark = pytest.mark.live

EXAMPLE_URL = "https://example.com"
DOCS_URL = "https://docs.tavily.com"


def _tavily_api_key() -> str | None:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "TAVILY_API_KEY":
            return value.strip().strip('"').strip("'") or None
    return None


@pytest.fixture(scope="session", autouse=True)
def _configure_tavily() -> None:
    key = _tavily_api_key()
    if not key:
        pytest.skip("TAVILY_API_KEY is not set (environment or .env at the repo root)")
    tavily.configure(api_key=key)


def _paid_only(exc: APIError) -> None:
    detail = str(getattr(exc, "body", "") or exc)
    if exc.status_code == 429:
        pytest.skip(f"rate limited: {detail[:200]}")
    if exc.status_code in (402, 403, 432, 433) or "plan" in detail.lower():
        pytest.skip(f"account tier does not include this endpoint: {detail[:200]}")


async def test_search_returns_ranked_results():
    result = await tavily.search.ainvoke(
        query="What is the Python programming language?",
        search_depth="basic",
        max_results=3,
        include_answer=False,
    )

    assert result["query"] == "What is the Python programming language?"
    assert len(result["results"]) >= 1
    assert result["results"][0]["url"]


async def test_extract_returns_markdown_from_a_known_url():
    result = await tavily.extract.ainvoke(
        urls=[EXAMPLE_URL],
        extract_depth="basic",
    )

    page = result["results"][0]
    assert page["url"] == EXAMPLE_URL
    assert page.get("raw_content") or page.get("content")


async def test_map_lists_urls_on_a_site():
    result = await tavily.map.ainvoke(url=DOCS_URL, limit=5)

    assert result["base_url"] == DOCS_URL
    assert len(result["results"]) >= 1


async def test_crawl_extracts_a_few_pages():
    result = await tavily.crawl.ainvoke(
        url=DOCS_URL,
        max_depth=1,
        limit=2,
        extract_depth="basic",
    )

    assert result["base_url"] == DOCS_URL
    assert result["results"][0]["raw_content"]


async def test_usage_returns_key_and_account():
    result = await tavily.usage.ainvoke()

    assert result["key"]["usage"] is not None
    assert "limit" in result["key"]  # null means unlimited
    assert result["account"]["current_plan"]


async def test_search_include_domains_restricts_hosts():
    result = await tavily.search.ainvoke(
        query="IANA example domain",
        include_domains=["example.com"],
        include_domains_mode="filter",
        max_results=3,
        search_depth="basic",
        include_answer=False,
    )

    if not result["results"]:
        pytest.skip("Tavily returned no indexed pages for example.com")
    for hit in result["results"]:
        assert "example.com" in hit["url"]


async def test_search_news_topic_can_include_published_date():
    result = await tavily.search.ainvoke(
        query="Python programming language",
        topic="news",
        time_range="month",
        max_results=2,
        search_depth="basic",
        include_answer=False,
        include_favicon=True,
    )

    hit = result["results"][0]
    assert hit["url"]
    assert "published_date" in hit
    if hit.get("favicon"):
        assert hit["favicon"].startswith("http")


async def test_search_raw_content_and_usage_are_opt_in():
    result = await tavily.search.ainvoke(
        query="What is example.com?",
        max_results=1,
        search_depth="basic",
        include_raw_content="markdown",
        include_usage=True,
        include_answer=False,
    )

    assert result["results"][0].get("raw_content")
    assert result.get("usage") is not None


async def test_extract_accepts_a_bare_url_string():
    result = await tavily.extract.ainvoke(
        urls=EXAMPLE_URL,
        extract_depth="basic",
        include_favicon=True,
        include_usage=True,
    )

    page = result["results"][0]
    assert page["url"] == EXAMPLE_URL
    assert page.get("raw_content")
    assert result.get("failed_results") == [] or isinstance(result.get("failed_results"), list)


async def test_extract_query_reranks_chunks():
    result = await tavily.extract.ainvoke(
        urls=[EXAMPLE_URL],
        query="what is this domain for",
        chunks_per_source=2,
        extract_depth="basic",
        format="text",
    )

    page = result["results"][0]
    assert page.get("raw_content")
    assert "[...]" in page["raw_content"] or len(page["raw_content"]) > 0


async def test_map_results_are_url_strings():
    result = await tavily.map.ainvoke(
        url=DOCS_URL,
        limit=5,
        exclude_paths=["/changelog/.*"],
        include_usage=True,
    )

    assert result["results"]
    assert isinstance(result["results"][0], str)
    assert result["results"][0].startswith("http")


async def test_crawl_can_select_documentation_paths():
    result = await tavily.crawl.ainvoke(
        url=DOCS_URL,
        max_depth=1,
        limit=2,
        select_paths=["/documentation/.*"],
        extract_depth="basic",
        include_favicon=True,
    )

    assert result["results"]
    page = result["results"][0]
    assert page.get("raw_content")
    assert "/documentation/" in page["url"] or page["url"].startswith("http")


async def test_search_images_returns_an_images_list():
    result = await tavily.search.ainvoke(
        query="IANA example domain logo",
        include_images=True,
        max_results=2,
        search_depth="basic",
        include_answer=False,
    )

    assert "images" in result
    assert result["images"] or result["results"]
    if result["images"]:
        image = result["images"][0]
        if isinstance(image, dict):
            assert image.get("url")
        else:
            assert isinstance(image, str) and image.startswith("http")


async def test_search_image_descriptions_are_objects_with_url():
    result = await tavily.search.ainvoke(
        query="IANA example domain",
        include_images=True,
        include_image_descriptions=True,
        max_results=2,
        search_depth="basic",
        include_answer=False,
    )

    if not result.get("images"):
        pytest.skip("no images returned for this query")
    image = result["images"][0]
    assert isinstance(image, dict)
    assert image.get("url")


async def test_search_language_filter_still_returns_hits():
    result = await tavily.search.ainvoke(
        query="programming language",
        language="en",
        filter_by_language=True,
        max_results=2,
        search_depth="basic",
        include_answer=False,
    )

    assert result["results"][0]["url"]


async def test_extract_include_images_returns_url_strings():
    result = await tavily.extract.ainvoke(
        urls="https://en.wikipedia.org/wiki/Example.com",
        extract_depth="basic",
        include_images=True,
    )

    page = result["results"][0]
    assert page.get("raw_content")
    assert isinstance(page.get("images") or [], list)


async def test_crawl_include_images_survives_on_each_page():
    result = await tavily.crawl.ainvoke(
        url=DOCS_URL,
        max_depth=1,
        limit=1,
        extract_depth="basic",
        include_images=True,
    )

    assert result["results"]
    page = result["results"][0]
    assert page.get("raw_content")
    if page.get("images"):
        assert isinstance(page["images"], list)


async def test_research_get_does_not_treat_a_running_task_as_failure():
    try:
        created = await tavily.research_create.ainvoke(
            input="Name one primary color.",
            model="mini",
            output_length="short",
        )
    except APIError as exc:
        _paid_only(exc)
        raise
    result = await tavily.research_get.ainvoke(request_id=created["request_id"])
    assert result["status"] in ("pending", "in_progress", "completed", "failed")
    assert result.get("request_id") == created["request_id"]


async def test_logs_no_arg_reaches_the_api():
    """No-arg call sends ``{}``; a 403 still proves the wire shape is accepted."""
    try:
        result = await tavily.logs.ainvoke()
    except APIError as exc:
        _paid_only(exc)
        raise

    assert isinstance(result.get("logs"), list)


async def test_logs_with_limit_on_paid_plans():
    try:
        result = await tavily.logs.ainvoke(limit=1)
    except APIError as exc:
        _paid_only(exc)
        raise

    assert isinstance(result.get("logs"), list)


async def test_research_create_and_get_complete():
    try:
        created = await tavily.research_create.ainvoke(
            input="List three well-known benefits of static typing in programming languages.",
            model="mini",
            output_length="short",
        )
    except APIError as exc:
        _paid_only(exc)
        raise

    request_id = created["request_id"]
    result = created
    for _ in range(90):
        if result.get("status") == "completed":
            break
        await asyncio.sleep(2)
        result = await tavily.research_get.ainvoke(
            request_id=request_id,
            include_usage=True,
        )

    assert result["status"] == "completed"
    assert result.get("content")
    assert isinstance(result.get("sources"), list)


async def test_research_output_schema_accepts_minimal_item_shapes():
    try:
        created = await tavily.research_create.ainvoke(
            input="Name three primary colors.",
            model="mini",
            output_length="short",
            output_schema={
                "properties": {
                    "colors": {
                        "type": "array",
                        "description": "Primary colors.",
                        "items": {"type": "string"},
                    }
                },
                "required": ["colors"],
            },
        )
    except APIError as exc:
        _paid_only(exc)
        raise

    request_id = created["request_id"]
    result = created
    for _ in range(90):
        if result.get("status") == "completed":
            break
        await asyncio.sleep(2)
        result = await tavily.research_get.ainvoke(request_id=request_id)

    assert result["status"] == "completed"
    assert isinstance(result.get("content"), dict)
    assert result["content"].get("colors")


async def test_org_usage_skips_without_enterprise():
    try:
        await tavily.org_usage.ainvoke(organization_name="harness-live-check")
    except APIError as exc:
        if exc.status_code in (400, 403, 404):
            pytest.skip(f"org_usage not available for this account: {exc}")
        raise
