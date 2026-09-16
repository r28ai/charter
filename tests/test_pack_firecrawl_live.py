"""Firecrawl pack — live API tests with hardcoded arguments.

Reads ``FIRECRAWL_API_KEY`` from the environment or ``oss/.env``. Skip without
the key. Run with::

    cd oss
    .venv/bin/python -m pytest tests/test_pack_firecrawl_live.py -m live -v
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from charter.packs import firecrawl
from charter.types.errors import APIError

pytestmark = pytest.mark.live

EXAMPLE_URL = "https://example.com"


def _firecrawl_api_key() -> str | None:
    key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
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
        if name.strip() == "FIRECRAWL_API_KEY":
            return value.strip().strip('"').strip("'") or None
    return None


@pytest.fixture(scope="session", autouse=True)
def _configure_firecrawl() -> None:
    key = _firecrawl_api_key()
    if not key:
        pytest.skip("FIRECRAWL_API_KEY is not set (environment or oss/.env)")
    firecrawl.configure(api_key=key)


def _paid_only(exc: APIError) -> None:
    detail = str(getattr(exc, "body", "") or exc)
    if exc.status_code == 429:
        pytest.skip(f"rate limited: {detail[:200]}")
    if exc.status_code in (402, 403) or "plan" in detail.lower():
        pytest.skip(f"account tier does not include this endpoint: {detail[:200]}")


async def test_scrape_returns_markdown_from_a_known_url():
    result = await firecrawl.scrape.ainvoke(url=EXAMPLE_URL, formats=["markdown"])

    assert result["success"] is True
    markdown = result["data"]["markdown"]
    assert "Example Domain" in markdown
    metadata = result["data"]["metadata"]
    assert metadata["statusCode"] == 200
    assert "og:image" not in metadata


async def test_search_returns_web_hits_with_urls():
    result = await firecrawl.search.ainvoke(query="example domain IANA", limit=3)

    assert result["success"] is True
    web = result["data"]["web"]
    assert len(web) >= 1
    assert web[0]["url"]
    assert web[0].get("title") or web[0].get("description") or web[0].get("markdown")


async def test_map_lists_urls_on_a_site():
    result = await firecrawl.map.ainvoke(url=EXAMPLE_URL, limit=5)

    assert result["success"] is True
    assert len(result["links"]) >= 1
    assert result["links"][0]["url"]


async def test_credit_usage_returns_remaining_credits():
    result = await firecrawl.credit_usage.ainvoke()

    assert result["success"] is True
    remaining = result["data"]["remainingCredits"]
    assert remaining is not None


async def test_token_usage_returns_remaining_tokens():
    try:
        result = await firecrawl.token_usage.ainvoke()
    except APIError as exc:
        _paid_only(exc)
        raise

    assert result["success"] is True
    assert "remainingTokens" in result["data"]


async def test_queue_status_returns_metrics():
    result = await firecrawl.queue_status.ainvoke()

    assert result["success"] is True
    assert "jobsInQueue" in result


async def test_developer_search_returns_ranked_results():
    result = await firecrawl.developer_search.ainvoke(query="scrape a url", k=3)

    assert result["success"] is True
    assert result["results"]


async def test_research_papers_search_returns_papers():
    try:
        result = await firecrawl.research_papers_search.ainvoke(
            query="attention is all you need",
            k=3,
        )
    except APIError as exc:
        _paid_only(exc)
        raise

    assert result["success"] is True
    assert result["results"]


async def test_crawl_params_preview_returns_generated_options():
    result = await firecrawl.crawl_params_preview.ainvoke(
        url=EXAMPLE_URL,
        prompt="Only the homepage, skip blogs.",
    )

    assert result["success"] is True
    assert result["data"]["url"]


async def test_extract_starts_and_completes():
    try:
        created = await firecrawl.extract.ainvoke(
            urls=[EXAMPLE_URL],
            prompt="Extract the page heading as heading",
            schema_={
                "type": "object",
                "properties": {"heading": {"type": "string"}},
                "required": ["heading"],
            },
        )
    except APIError as exc:
        _paid_only(exc)
        raise

    job_id = created.get("id")
    assert job_id
    result = created
    for _ in range(30):
        result = await firecrawl.extract_status.ainvoke(id=job_id)
        if result.get("status") in {"completed", "failed", "cancelled"}:
            break
        await asyncio.sleep(2)

    assert result["status"] == "completed"
    assert result.get("data") is not None


async def test_interact_create_empty_body_is_accepted():
    session_id = None
    try:
        created = await firecrawl.interact_create.ainvoke()
    except APIError as exc:
        _paid_only(exc)
        raise

    session_id = created.get("id")
    assert session_id
    try:
        assert created["success"] is True
    finally:
        await firecrawl.interact_delete.ainvoke(session_id=session_id)


async def test_search_with_source_strings_returns_those_groups():
    result = await firecrawl.search.ainvoke(
        query="example domain",
        sources=["web", "news"],
        limit=2,
    )

    assert result["success"] is True
    assert "web" in result["data"]
    assert "news" in result["data"]
    assert result["data"]["web"][0]["url"]


async def test_scrape_question_format_returns_an_answer():
    result = await firecrawl.scrape.ainvoke(
        url=EXAMPLE_URL,
        formats=[{"type": "question", "question": "What is the heading of this page?"}],
    )

    assert result["success"] is True
    assert result["data"].get("answer")


async def test_activity_lists_recent_jobs():
    result = await firecrawl.activity.ainvoke(limit=5)

    assert result["success"] is True
    assert isinstance(result["data"], list)
    assert "has_more" in result


async def test_crawl_starts_then_cancels():
    try:
        created = await firecrawl.crawl.ainvoke(url=EXAMPLE_URL, limit=1)
    except APIError as exc:
        _paid_only(exc)
        raise
    job_id = created["id"]
    assert job_id
    try:
        status = await firecrawl.crawl_status.ainvoke(id=job_id)
        assert status.get("status") in {
            "scraping",
            "completed",
            "cancelled",
            "failed",
            "pending",
        }
    finally:
        await firecrawl.crawl_cancel.ainvoke(id=job_id)


async def test_scrape_markdown_and_links_together():
    result = await firecrawl.scrape.ainvoke(
        url=EXAMPLE_URL,
        formats=["markdown", "links"],
    )

    assert result["success"] is True
    assert "Example Domain" in result["data"]["markdown"]
    assert any("iana.org" in link for link in result["data"]["links"])


async def test_scrape_highlights_returns_selected_text():
    result = await firecrawl.scrape.ainvoke(
        url=EXAMPLE_URL,
        formats=[{"type": "highlights", "query": "example domain"}],
    )

    assert result["success"] is True
    assert result["data"].get("highlights")


async def test_scrape_html_survives_trimming():
    result = await firecrawl.scrape.ainvoke(url=EXAMPLE_URL, formats=["html"])

    assert result["success"] is True
    html = result["data"]["html"]
    assert "<" in html and "Example" in html
    assert "og:image" not in (result["data"].get("metadata") or {})


async def test_search_images_keeps_image_urls():
    result = await firecrawl.search.ainvoke(
        query="example.com iana logo",
        sources=["images"],
        limit=2,
    )

    assert result["success"] is True
    images = result["data"]["images"]
    assert images[0].get("imageUrl") or images[0].get("url")


async def test_search_include_domains_restricts_hosts():
    result = await firecrawl.search.ainvoke(
        query="example domain",
        include_domains=["example.com"],
        limit=3,
    )

    assert result["success"] is True
    for hit in result["data"]["web"]:
        assert "example.com" in hit["url"]


async def test_search_scraped_hits_keep_markdown_and_drop_noisy_metadata():
    result = await firecrawl.search.ainvoke(
        query="example domain IANA",
        limit=1,
        scrape_options={"formats": ["markdown"]},
    )

    assert result["success"] is True
    hit = result["data"]["web"][0]
    assert hit["url"]
    assert hit.get("markdown")
    metadata = hit.get("metadata") or {}
    assert "og:image" not in metadata
    assert "twitter:image" not in metadata


async def test_map_search_orders_matching_paths():
    result = await firecrawl.map.ainvoke(url="https://docs.firecrawl.dev", search="scrape", limit=10)

    assert result["success"] is True
    urls = [link["url"] if isinstance(link, dict) else link for link in result["links"]]
    assert urls
    assert any("scrape" in url.lower() for url in urls)


async def test_developer_search_can_restrict_to_docs():
    result = await firecrawl.developer_search.ainvoke(
        query="ignoreInvalidURLs",
        types=["doc"],
        k=3,
    )

    assert result["success"] is True
    assert result["results"]
    kinds = {hit.get("type") or hit.get("kind") for hit in result["results"]}
    assert kinds <= {"doc", None} or "doc" in kinds


async def test_research_get_and_similar_from_a_search_hit():
    found = await firecrawl.research_papers_search.ainvoke(
        query="attention is all you need",
        k=1,
    )
    paper = found["results"][0]
    paper_id = paper.get("paperId") or paper.get("id") or paper.get("paper_id")
    assert paper_id

    read = await firecrawl.research_paper_get.ainvoke(
        id=paper_id,
        query="what problem does this paper solve",
        k=2,
    )
    assert read["success"] is True

    similar = await firecrawl.research_similar_papers.ainvoke(
        id=paper_id,
        intent="follow-up transformer papers",
        k=3,
    )
    assert similar["success"] is True
    assert similar["results"]


async def test_batch_scrape_two_urls_then_status():
    try:
        created = await firecrawl.batch_scrape.ainvoke(
            urls=[EXAMPLE_URL, "https://www.iana.org/help/example-domains"],
            formats=["markdown"],
            ignore_invalid_urls=True,
        )
    except APIError as exc:
        _paid_only(exc)
        raise
    job_id = created["id"]
    try:
        result = created
        for _ in range(30):
            result = await firecrawl.batch_scrape_status.ainvoke(id=job_id)
            if result.get("status") in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)
        assert result["status"] == "completed"
        pages = result["data"]
        assert len(pages) >= 1
        assert pages[0].get("markdown")
        metadata = pages[0].get("metadata") or {}
        assert "og:image" not in metadata
    finally:
        if result.get("status") not in {"completed", "failed", "cancelled"}:
            await firecrawl.batch_scrape_cancel.ainvoke(id=job_id)


async def test_extract_accepts_a_glob_url():
    """Extract's documented URL shape is a glob, not a single page URL."""
    try:
        created = await firecrawl.extract.ainvoke(
            urls=["https://example.com/*"],
            prompt="Extract the heading",
            ignore_invalid_urls=True,
        )
    except APIError as exc:
        _paid_only(exc)
        raise

    assert created["success"] is True
    assert created.get("id")


async def test_scrape_json_format_is_the_extract_replacement():
    """v2 extract is deprecated in favour of scrape with a json format object."""
    result = await firecrawl.scrape.ainvoke(
        url=EXAMPLE_URL,
        formats=[{
            "type": "json",
            "prompt": "Extract the visible heading",
            "schema": {
                "type": "object",
                "properties": {"heading": {"type": "string"}},
                "required": ["heading"],
            },
        }],
    )

    assert result["success"] is True
    extracted = result["data"].get("json")
    assert extracted
    assert extracted.get("heading")


async def test_historical_usage_endpoints_accept_by_api_key():
    credits = await firecrawl.historical_credit_usage.ainvoke(by_api_key=False)
    assert credits["success"] is True
    tokens = await firecrawl.historical_token_usage.ainvoke(by_api_key=True)
    assert tokens["success"] is True


async def test_activity_can_filter_by_endpoint():
    result = await firecrawl.activity.ainvoke(endpoint="scrape", limit=5)

    assert result["success"] is True
    for row in result["data"]:
        assert row["endpoint"] == "scrape"


async def test_interact_can_execute_then_delete():
    created = await firecrawl.interact_create.ainvoke(ttl=30, stream_web_view=False)
    session_id = created["id"]
    try:
        executed = await firecrawl.interact_execute.ainvoke(
            session_id=session_id,
            code="console.log('charter-live')",
            language="node",
            timeout=15,
        )
        assert executed.get("success") is not False
    finally:
        await firecrawl.interact_delete.ainvoke(session_id=session_id)


async def test_crawl_status_trims_pages_after_completion():
    try:
        created = await firecrawl.crawl.ainvoke(
            url=EXAMPLE_URL,
            limit=1,
            scrape_options={"formats": ["markdown"]},
        )
    except APIError as exc:
        _paid_only(exc)
        raise
    job_id = created["id"]
    try:
        result = created
        for _ in range(30):
            result = await firecrawl.crawl_status.ainvoke(id=job_id)
            if result.get("status") in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)
        if result.get("status") != "completed":
            pytest.skip(f"crawl did not finish in time: {result.get('status')}")
        page = result["data"][0]
        assert page.get("markdown")
        assert "og:image" not in (page.get("metadata") or {})
        errors = await firecrawl.crawl_errors.ainvoke(id=job_id)
        assert "errors" in errors or errors.get("success") is not False
    finally:
        if result.get("status") not in {"completed", "failed", "cancelled"}:
            await firecrawl.crawl_cancel.ainvoke(id=job_id)


async def test_crawl_active_lists_jobs():
    result = await firecrawl.crawl_active.ainvoke()
    assert result.get("success") is not False
    assert "crawls" in result or "data" in result or isinstance(result.get("jobs"), list)


async def test_search_object_source_with_tbs_is_accepted():
    result = await firecrawl.search.ainvoke(
        query="IANA example domain",
        sources=[{"type": "web", "tbs": "qdr:y"}],
        limit=2,
        highlights=False,
        safe=True,
    )

    assert result["success"] is True
    assert result["data"]["web"][0]["url"]


async def test_map_can_skip_the_sitemap():
    result = await firecrawl.map.ainvoke(
        url=EXAMPLE_URL,
        sitemap="skip",
        ignore_query_parameters=True,
        limit=5,
    )

    assert result["success"] is True
    assert result["links"]


async def test_scrape_question_and_markdown_together():
    result = await firecrawl.scrape.ainvoke(
        url=EXAMPLE_URL,
        formats=["markdown", {"type": "question", "question": "What is this page for?"}],
    )

    assert result["success"] is True
    assert "Example Domain" in result["data"]["markdown"]
    assert result["data"].get("answer")


async def test_monitor_list_or_skip_if_unavailable():
    try:
        result = await firecrawl.monitor_list.ainvoke(limit=5)
    except APIError as exc:
        _paid_only(exc)
        raise

    assert result.get("success") is not False
