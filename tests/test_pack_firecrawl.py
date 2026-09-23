"""Firecrawl pack — response trimming around content that must survive intact.

On a measured GitHub blob a scrape was 1,998 bytes of markdown against 4,624
bytes of ``metadata`` across 71 keys: OpenGraph, Twitter cards,
``apple-itunes-app``, ``go-import``, a ``visitor-payload`` blob. Two thirds of
the payload described the page to crawlers.

The content the caller asked for is never trimmed, and the ``{"success",
"data"}`` envelope stays where callers expect it.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from charter import APIError, CredentialError
from charter.packs import firecrawl

API = "https://api.firecrawl.dev/v2/"

NOISY_METADATA = {
    "title": "harness-sandbox/README.md at main",
    "description": "Sandbox for the Charter scenario harness.",
    "sourceURL": "https://github.com/harness-owner/harness-sandbox",
    "statusCode": 200,
    "language": "en",
    **{
        k: "x" * 60
        for k in (
            "og:image",
            "ogImage",
            "twitter:image",
            "og:description",
            "ogDescription",
            "twitter:description",
            "og:image:alt",
            "apple-itunes-app",
            "go-import",
            "visitor-payload",
            "octolytics-dimension-user_id",
            "hovercard-subject-tag",
            "request-id",
            "html-safe-nonce",
            "theme-color",
            "browser-stats-url",
        )
    },
}


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    firecrawl.configure(api_key="fc-test")


@respx.mock
async def test_the_markdown_is_never_touched():
    """It is the thing the caller asked for; trimming it would be a bug."""
    markdown = "# Deployment Runbook\n\n" + "Freeze merges. " * 200
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"markdown": markdown, "metadata": NOISY_METADATA}}
        )
    )

    result = await firecrawl.scrape.ainvoke(url="https://example.com")
    assert result["data"]["markdown"] == markdown


@respx.mock
async def test_the_envelope_stays_where_callers_read_it():
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"markdown": "# Hi", "metadata": NOISY_METADATA}}
        )
    )

    result = await firecrawl.scrape.ainvoke(url="https://example.com")
    assert result["success"] is True
    assert result["data"]["markdown"] == "# Hi"


@respx.mock
async def test_metadata_is_reduced_to_what_an_agent_reads():
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"markdown": "# Hi", "metadata": NOISY_METADATA}}
        )
    )

    metadata = (await firecrawl.scrape.ainvoke(url="https://example.com"))["data"]["metadata"]
    assert metadata == {
        "title": "harness-sandbox/README.md at main",
        "description": "Sandbox for the Charter scenario harness.",
        "sourceURL": "https://github.com/harness-owner/harness-sandbox",
        "statusCode": 200,
        "language": "en",
    }


@respx.mock
async def test_a_partial_scrape_still_says_so():
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {"markdown": "# Hi", "metadata": NOISY_METADATA, "warning": "timed out"},
            },
        )
    )

    assert (await firecrawl.scrape.ainvoke(url="https://x.com"))["data"]["warning"] == "timed out"


@respx.mock
async def test_every_requested_format_survives():
    formats = {
        "markdown": "# Hi",
        "html": "<h1>Hi</h1>",
        "rawHtml": "<html>",
        "links": ["https://a.example"],
        "summary": "a page",
        "json": {"owner": "sam"},
    }
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {**formats, "metadata": NOISY_METADATA}}
        )
    )

    data = (await firecrawl.scrape.ainvoke(url="https://example.com"))["data"]
    for key, value in formats.items():
        assert data[key] == value, key


@respx.mock
async def test_trimming_is_a_large_reduction():
    payload = {"success": True, "data": {"markdown": "# Hi", "metadata": NOISY_METADATA}}
    respx.post(f"{API}scrape").mock(return_value=httpx.Response(200, json=payload))

    result = await firecrawl.scrape.ainvoke(url="https://example.com")
    before, after = len(json.dumps(payload)), len(json.dumps(result))
    assert after < before * 0.5, f"only trimmed {(1 - after / before) * 100:.0f}%"


@respx.mock
async def test_search_keeps_its_grouped_shape():
    respx.post(f"{API}search").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [{"markdown": "a", "metadata": NOISY_METADATA}],
                    "news": [{"markdown": "b", "metadata": NOISY_METADATA}],
                },
            },
        )
    )

    data = (await firecrawl.search.ainvoke(query="billing"))["data"]
    assert set(data) == {"web", "news"}
    assert data["web"][0]["markdown"] == "a"
    assert "og:image" not in json.dumps(data)


@respx.mock
async def test_map_returns_the_urls_it_found():
    respx.post(f"{API}map").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "links": [
                    {
                        "url": "https://a.example",
                        "title": "A",
                        "description": "d",
                        "og:image": "x" * 100,
                    }
                ],
            },
        )
    )

    links = (await firecrawl.map.ainvoke(url="https://a.example"))["links"]
    assert links == [{"url": "https://a.example", "title": "A", "description": "d"}]


@respx.mock
async def test_crawl_posts_camel_case_json_on_the_wire():
    route = respx.post(f"{API}crawl").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "job-1"})
    )

    await firecrawl.crawl.ainvoke(url="https://example.com", limit=10, allow_subdomains=True)

    assert route.calls[0].request.headers["Authorization"] == "Bearer fc-test"
    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "limit": 10,
        "allowSubdomains": True,
    }


@respx.mock
async def test_developer_search_sends_camel_case_query_parameters():
    route = respx.get(f"{API}search/developer").mock(
        return_value=httpx.Response(200, json={"success": True, "results": []})
    )

    await firecrawl.developer_search.ainvoke(query="webhooks", k=5, min_stars=100)

    assert dict(route.calls[0].request.url.params) == {
        "query": "webhooks",
        "k": "5",
        "min_stars": "100",
    }


@respx.mock
async def test_a_success_false_body_raises_instead_of_returning():
    respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": False, "error": "bad query"})
    )

    with pytest.raises(APIError, match="bad query"):
        await firecrawl.search.ainvoke(query="test")


async def test_unconfigured_pack_raises_before_a_request(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    firecrawl._headers._api_key = None  # noqa: SLF001 — test the guard directly

    with pytest.raises(CredentialError, match="no API key"):
        await firecrawl.search.ainvoke(query="test")


def test_every_tool_llm_schema_builds():
    for tool in firecrawl.TOOLS:
        schema = tool.llm_schema()
        assert schema.model_json_schema()["type"] == "object"


@respx.mock
async def test_search_with_only_query_sends_no_copied_defaults():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": []}})
    )

    await firecrawl.search.ainvoke(query="billing")

    assert json.loads(route.calls[0].request.content) == {"query": "billing"}


@respx.mock
async def test_ignore_invalid_urls_keeps_its_documented_acronym():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": []}})
    )

    await firecrawl.search.ainvoke(query="billing", ignore_invalid_urls=True)

    assert json.loads(route.calls[0].request.content) == {
        "query": "billing",
        "ignoreInvalidURLs": True,
    }


@respx.mock
async def test_regex_on_full_url_keeps_its_documented_acronym():
    route = respx.post(f"{API}crawl").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "job-1"})
    )

    await firecrawl.crawl.ainvoke(url="https://example.com", regex_on_full_url=True)

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "regexOnFullURL": True,
    }


@respx.mock
async def test_developer_star_filters_stay_snake_on_the_wire():
    route = respx.get(f"{API}search/developer").mock(
        return_value=httpx.Response(200, json={"success": True, "results": []})
    )

    await firecrawl.developer_search.ainvoke(query="webhooks", min_stars=100, max_stars=500)

    assert dict(route.calls[0].request.url.params) == {
        "query": "webhooks",
        "min_stars": "100",
        "max_stars": "500",
    }


@respx.mock
async def test_map_with_only_url_sends_no_copied_defaults():
    route = respx.post(f"{API}map").mock(
        return_value=httpx.Response(200, json={"success": True, "links": []})
    )

    await firecrawl.map.ainvoke(url="https://a.example")

    assert json.loads(route.calls[0].request.content) == {"url": "https://a.example"}


@respx.mock
async def test_nested_type_reaches_the_wire_as_type():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(
        url="https://example.com",
        formats=[{"type": "audio"}, {"type": "question", "question": "What is this?"}],
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "formats": [
            {"type": "audio"},
            {"type": "question", "question": "What is this?"},
        ],
    }


@respx.mock
async def test_extract_posts_camel_case_json_on_the_wire():
    route = respx.post(f"{API}extract").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "ext-1"})
    )

    await firecrawl.extract.ainvoke(
        urls=["https://example.com/*"],
        prompt="company name",
        schema_={"type": "object"},
        enable_web_search=True,
        ignore_invalid_urls=False,
    )

    assert json.loads(route.calls[0].request.content) == {
        "urls": ["https://example.com/*"],
        "prompt": "company name",
        "schema": {"type": "object"},
        "enableWebSearch": True,
        "ignoreInvalidURLs": False,
    }


@respx.mock
async def test_extract_with_only_urls_sends_no_copied_defaults():
    route = respx.post(f"{API}extract").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "ext-1"})
    )

    await firecrawl.extract.ainvoke(urls=["https://example.com"])

    assert json.loads(route.calls[0].request.content) == {"urls": ["https://example.com"]}


@respx.mock
async def test_historical_token_usage_sends_camel_case_query():
    route = respx.get(f"{API}team/token-usage/historical").mock(
        return_value=httpx.Response(200, json={"success": True, "periods": []})
    )

    await firecrawl.historical_token_usage.ainvoke(by_api_key=True)

    assert dict(route.calls[0].request.url.params) == {"byApiKey": "true"}


def test_search_rejects_include_and_exclude_domains_together():
    with pytest.raises(ValueError, match="excludeDomains"):
        firecrawl.search.llm_schema()(
            query="x",
            include_domains=["a.com"],
            exclude_domains=["b.com"],
        )


@respx.mock
async def test_redact_pii_keeps_its_documented_acronym():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(url="https://example.com", redact_pii=True)

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "redactPII": True,
    }


@respx.mock
async def test_nested_redact_pii_keeps_its_documented_acronym():
    route = respx.post(f"{API}crawl").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "job-1"})
    )

    await firecrawl.crawl.ainvoke(
        url="https://example.com",
        scrape_options={"redact_pii": True},
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "scrapeOptions": {"redactPII": True},
    }


@respx.mock
async def test_search_accepts_source_and_category_strings():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": []}})
    )

    await firecrawl.search.ainvoke(
        query="billing",
        sources=["web", "news"],
        categories=["developer"],
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "billing",
        "sources": ["web", "news"],
        "categories": ["developer"],
    }


@respx.mock
async def test_search_keeps_titles_and_urls_when_pages_were_not_scraped():
    respx.post(f"{API}search").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://example.com",
                            "title": "Example",
                            "description": "An example page",
                            "metadata": NOISY_METADATA,
                        }
                    ],
                    "images": [
                        {
                            "url": "https://example.com",
                            "title": "Example",
                            "imageUrl": "https://example.com/og.png",
                            "imageWidth": 1200,
                            "position": 1,
                        }
                    ],
                },
            },
        )
    )

    data = (await firecrawl.search.ainvoke(query="example"))["data"]
    assert data["web"][0] == {
        "url": "https://example.com",
        "title": "Example",
        "description": "An example page",
        "metadata": {
            "title": "harness-sandbox/README.md at main",
            "description": "Sandbox for the Charter scenario harness.",
            "sourceURL": "https://github.com/harness-owner/harness-sandbox",
            "statusCode": 200,
            "language": "en",
        },
    }
    assert data["images"][0] == {
        "url": "https://example.com",
        "title": "Example",
        "imageUrl": "https://example.com/og.png",
        "imageWidth": 1200,
        "position": 1,
    }


@respx.mock
async def test_scrape_keeps_every_documented_content_field():
    payload = {
        "markdown": "# Hi",
        "answer": "It is a page",
        "highlights": "Hi",
        "branding": {"logo": "https://example.com/logo.png"},
        "rawBase64": "aGVsbG8=",
        "audio": "https://cdn.example/a.mp3",
        "video": "https://cdn.example/v.mp4",
        "pages": [{"pageNumber": 1, "markdown": "# Hi"}],
        "actions": {"screenshots": ["https://cdn.example/s.png"]},
        "metadata": NOISY_METADATA,
        "warning": "partial",
    }
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": payload})
    )

    data = (await firecrawl.scrape.ainvoke(url="https://example.com"))["data"]
    for key in (
        "markdown",
        "answer",
        "highlights",
        "branding",
        "rawBase64",
        "audio",
        "video",
        "pages",
        "actions",
        "warning",
    ):
        assert data[key] == payload[key], key
    assert "og:image" not in json.dumps(data["metadata"])


@respx.mock
async def test_interact_create_with_no_args_sends_an_empty_object():
    route = respx.post(f"{API}interact").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "sess-1"})
    )

    await firecrawl.interact_create.ainvoke()

    assert json.loads(route.calls[0].request.content) == {}


@respx.mock
async def test_scrape_status_interpolates_the_job_id():
    route = respx.get(f"{API}scrape/job-1").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape_status.ainvoke(job_id="job-1")

    assert str(route.calls[0].request.url) == f"{API}scrape/job-1"


@respx.mock
async def test_batch_scrape_cancel_is_a_delete():
    route = respx.delete(f"{API}batch/scrape/job-1").mock(
        return_value=httpx.Response(200, json={"status": "cancelled"})
    )

    result = await firecrawl.batch_scrape_cancel.ainvoke(id="job-1")

    assert result == {"status": "cancelled"}
    assert route.calls[0].request.method == "DELETE"


@respx.mock
async def test_parsers_accept_the_bare_pdf_string():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(url="https://example.com", parsers=["pdf"], formats=["markdown"])

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "parsers": ["pdf"],
        "formats": ["markdown"],
    }


@respx.mock
async def test_monitor_create_sends_target_type_as_type():
    route = respx.post(f"{API}monitor").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "mon-1"})
    )

    await firecrawl.monitor_create.ainvoke(
        name="docs",
        schedule={"text": "every 30 minutes"},
        targets=[{"type": "scrape", "urls": ["https://example.com"]}],
    )

    assert json.loads(route.calls[0].request.content) == {
        "name": "docs",
        "schedule": {"text": "every 30 minutes"},
        "targets": [{"type": "scrape", "urls": ["https://example.com"]}],
    }


def test_monitor_schedule_rejects_cron_and_text_together():
    with pytest.raises(ValueError, match="either cron or text"):
        firecrawl.monitor_create.llm_schema()(
            name="docs",
            schedule={"cron": "*/30 * * * *", "text": "every 30 minutes"},
            targets=[{"type": "scrape", "urls": ["https://example.com"]}],
        )


@respx.mock
async def test_threat_protection_update_is_a_put():
    route = respx.put(f"{API}team/threat-protection").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    await firecrawl.threat_protection_update.ainvoke(mode="normal", blocked_tlds=["xyz"])

    assert route.calls[0].request.method == "PUT"
    assert json.loads(route.calls[0].request.content) == {
        "mode": "normal",
        "blockedTlds": ["xyz"],
    }


@respx.mock
async def test_research_from_stays_from_on_the_query_string():
    route = respx.get(f"{API}search/research/papers").mock(
        return_value=httpx.Response(200, json={"success": True, "results": []})
    )

    await firecrawl.research_papers_search.ainvoke(query="transformers", from_="2020-01-01")

    assert dict(route.calls[0].request.url.params) == {
        "query": "transformers",
        "from": "2020-01-01",
    }


@respx.mock
async def test_mixed_source_strings_and_objects_reach_the_wire():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": [], "news": []}})
    )

    await firecrawl.search.ainvoke(
        query="billing",
        sources=["web", {"type": "news"}, {"type": "web", "tbs": "qdr:w", "location": "US"}],
        categories=[{"type": "pdf"}, "developer"],
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "billing",
        "sources": [
            "web",
            {"type": "news"},
            {"type": "web", "tbs": "qdr:w", "location": "US"},
        ],
        "categories": [{"type": "pdf"}, "developer"],
    }


@respx.mock
async def test_redact_pii_object_camel_cases_its_nested_keys():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(
        url="https://example.com",
        redact_pii={"mode": "fast", "replace_style": "mask", "entities": ["EMAIL", "PHONE"]},
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "redactPII": {"mode": "fast", "replaceStyle": "mask", "entities": ["EMAIL", "PHONE"]},
    }


@respx.mock
async def test_nested_scrape_options_on_search_keep_acronyms_and_camel_case():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": []}})
    )

    await firecrawl.search.ainvoke(
        query="billing",
        scrape_options={
            "only_main_content": False,
            "skip_tls_verification": True,
            "redact_pii": True,
            "formats": [
                "markdown",
                {"type": "json", "prompt": "name", "check_prompt_injection": True},
            ],
        },
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "billing",
        "scrapeOptions": {
            "onlyMainContent": False,
            "skipTlsVerification": True,
            "redactPII": True,
            "formats": [
                "markdown",
                {"type": "json", "prompt": "name", "checkPromptInjection": True},
            ],
        },
    }


@respx.mock
async def test_pdf_parser_object_camel_cases_page_fields():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(
        url="https://example.com/doc.pdf",
        parsers=[
            {"type": "pdf", "mode": "ocr", "max_pages": 3, "page_markers": True, "pages": True}
        ],
        actions=[
            {"type": "wait", "milliseconds": 250},
            {"type": "executeJavascript", "script": "document.title"},
        ],
        location={"country": "DE", "languages": ["de-DE"]},
        profile={"name": "checkout", "save_changes": False},
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com/doc.pdf",
        "parsers": [
            {"type": "pdf", "mode": "ocr", "maxPages": 3, "pageMarkers": True, "pages": True},
        ],
        "actions": [
            {"type": "wait", "milliseconds": 250},
            {"type": "executeJavascript", "script": "document.title"},
        ],
        "location": {"country": "DE", "languages": ["de-DE"]},
        "profile": {"name": "checkout", "saveChanges": False},
    }


@respx.mock
async def test_search_keeps_envelope_fields_and_falsey_result_values():
    respx.post(f"{API}search").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "id": "search-1",
                "creditsUsed": 2,
                "warning": "one source timed out",
                "data": {
                    "news": [
                        {
                            "url": "https://news.example",
                            "title": "Example",
                            "snippet": "A snippet",
                            "date": "2024-01-01",
                            "position": 0,
                            "imageUrl": "https://news.example/a.png",
                            "metadata": NOISY_METADATA,
                        }
                    ],
                },
            },
        )
    )

    result = await firecrawl.search.ainvoke(query="example")
    assert result["id"] == "search-1"
    assert result["creditsUsed"] == 2
    assert result["warning"] == "one source timed out"
    assert result["data"]["news"][0]["position"] == 0
    assert result["data"]["news"][0]["snippet"] == "A snippet"
    assert result["data"]["news"][0]["date"] == "2024-01-01"
    assert "og:image" not in json.dumps(result["data"])


@respx.mock
async def test_search_legacy_flat_list_is_still_trimmed():
    respx.post(f"{API}search").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {
                        "url": "https://a.example",
                        "title": "A",
                        "markdown": "# A",
                        "metadata": NOISY_METADATA,
                    }
                ],
            },
        )
    )

    data = (await firecrawl.search.ainvoke(query="a"))["data"]
    assert data[0]["url"] == "https://a.example"
    assert data[0]["markdown"] == "# A"
    assert "og:image" not in json.dumps(data)


@respx.mock
async def test_map_keeps_bare_url_strings():
    respx.post(f"{API}map").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "links": ["https://a.example", "https://b.example"],
            },
        )
    )

    assert (await firecrawl.map.ainvoke(url="https://a.example"))["links"] == [
        "https://a.example",
        "https://b.example",
    ]


@respx.mock
async def test_scrape_status_trims_the_same_way_as_scrape():
    respx.get(f"{API}scrape/job-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {"markdown": "# Hi", "json": {}, "links": [], "metadata": NOISY_METADATA},
            },
        )
    )

    data = (await firecrawl.scrape_status.ainvoke(job_id="job-1"))["data"]
    assert data["markdown"] == "# Hi"
    assert data["json"] == {}
    assert data["links"] == []
    assert "og:image" not in data["metadata"]


@respx.mock
async def test_crawl_status_trims_each_page_and_keeps_paging():
    respx.get(f"{API}crawl/job-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "completed",
                "total": 2,
                "completed": 2,
                "next": "https://api.firecrawl.dev/v2/crawl/job-1?skip=1",
                "creditsUsed": 2,
                "data": [
                    {"markdown": "# A", "metadata": NOISY_METADATA},
                    {"markdown": "# B", "metadata": NOISY_METADATA},
                ],
            },
        )
    )

    result = await firecrawl.crawl_status.ainvoke(id="job-1")
    assert result["status"] == "completed"
    assert result["next"].endswith("skip=1")
    assert result["creditsUsed"] == 2
    assert [page["markdown"] for page in result["data"]] == ["# A", "# B"]
    assert "og:image" not in json.dumps(result["data"])


@respx.mock
async def test_batch_scrape_status_trims_each_page():
    respx.get(f"{API}batch/scrape/job-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "completed",
                "data": [{"markdown": "# A", "metadata": NOISY_METADATA}],
            },
        )
    )

    data = (await firecrawl.batch_scrape_status.ainvoke(id="job-1"))["data"]
    assert data[0]["markdown"] == "# A"
    assert "og:image" not in json.dumps(data)


@respx.mock
async def test_extract_accepts_the_documented_schema_name():
    route = respx.post(f"{API}extract").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "ext-1"})
    )

    await firecrawl.extract.ainvoke(
        urls=["https://example.com"],
        schema={"type": "object", "properties": {"heading": {"type": "string"}}},
    )

    body = json.loads(route.calls[0].request.content)
    assert body["schema"] == {"type": "object", "properties": {"heading": {"type": "string"}}}
    assert "schema_" not in body


@respx.mock
async def test_developer_types_repeat_on_the_query_string():
    route = respx.get(f"{API}search/developer").mock(
        return_value=httpx.Response(200, json={"success": True, "results": []})
    )

    await firecrawl.developer_search.ainvoke(query="webhook", types=["doc", "issue"], k=2)

    params = route.calls[0].request.url.params
    assert params["query"] == "webhook"
    assert params["k"] == "2"
    assert params.get_list("types") == ["doc", "issue"]


@respx.mock
async def test_false_query_booleans_are_still_sent():
    route = respx.get(f"{API}team/credit-usage/historical").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )

    await firecrawl.historical_credit_usage.ainvoke(by_api_key=False)

    assert dict(route.calls[0].request.url.params) == {"byApiKey": "false"}


@respx.mock
async def test_no_arg_gets_do_not_invent_a_query_string():
    route = respx.get(f"{API}team/credit-usage").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"remainingCredits": 1}})
    )

    await firecrawl.credit_usage.ainvoke()

    assert route.calls[0].request.url.params == httpx.QueryParams()


@respx.mock
async def test_interact_create_merges_ttl_onto_the_empty_body():
    route = respx.post(f"{API}interact").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "sess-1"})
    )

    await firecrawl.interact_create.ainvoke(ttl=30)

    assert json.loads(route.calls[0].request.content) == {"ttl": 30}


@respx.mock
async def test_cancel_without_a_success_flag_is_not_treated_as_failure():
    respx.delete(f"{API}crawl/job-1").mock(
        return_value=httpx.Response(200, json={"status": "cancelled"})
    )

    assert (await firecrawl.crawl_cancel.ainvoke(id="job-1")) == {"status": "cancelled"}


@respx.mock
async def test_http_error_becomes_an_api_error():
    respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            402, json={"error": "Payment required to access this resource."}
        )
    )

    with pytest.raises(APIError, match="Payment required"):
        await firecrawl.scrape.ainvoke(url="https://example.com")


@respx.mock
async def test_batch_scrape_keeps_ignore_invalid_urls_acronym():
    route = respx.post(f"{API}batch/scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "batch-1"})
    )

    await firecrawl.batch_scrape.ainvoke(
        urls=["https://example.com", "not-a-url"],
        ignore_invalid_urls=True,
        max_concurrency=2,
        webhook={"url": "https://hooks.example/firecrawl", "events": ["completed", "failed"]},
    )

    assert json.loads(route.calls[0].request.content) == {
        "urls": ["https://example.com", "not-a-url"],
        "ignoreInvalidURLs": True,
        "maxConcurrency": 2,
        "webhook": {"url": "https://hooks.example/firecrawl", "events": ["completed", "failed"]},
    }


@respx.mock
async def test_search_feedback_interpolates_job_id_and_camels_the_body():
    route = respx.post(f"{API}search/job-1/feedback").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    await firecrawl.search_feedback.ainvoke(
        job_id="job-1",
        rating="partial",
        valuable_sources=[{"url": "https://example.com", "reason": "canonical"}],
        missing_content=[{"topic": "pricing"}],
        query_suggestions="try IANA example domain",
    )

    assert str(route.calls[0].request.url) == f"{API}search/job-1/feedback"
    assert json.loads(route.calls[0].request.content) == {
        "rating": "partial",
        "valuableSources": [{"url": "https://example.com", "reason": "canonical"}],
        "missingContent": [{"topic": "pricing"}],
        "querySuggestions": "try IANA example domain",
    }


@respx.mock
async def test_monitor_update_sends_a_partial_patch():
    route = respx.patch(f"{API}monitor/mon-1").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    await firecrawl.monitor_update.ainvoke(monitor_id="mon-1", status="paused")

    assert route.calls[0].request.method == "PATCH"
    assert json.loads(route.calls[0].request.content) == {"status": "paused"}


def test_monitor_update_without_fields_is_rejected():
    with pytest.raises(ValueError, match="at least one field"):
        firecrawl.monitor_update.llm_schema()(monitor_id="mon-1")


def test_monitor_schedule_rejects_timezone_without_cron_or_text():
    with pytest.raises(ValueError, match="either cron or text"):
        firecrawl.monitor_create.llm_schema()(
            name="docs",
            schedule={"timezone": "UTC"},
            targets=[{"type": "search", "queries": ["firecrawl changelog"]}],
        )


@respx.mock
async def test_monitor_search_target_camels_its_filters():
    route = respx.post(f"{API}monitor").mock(
        return_value=httpx.Response(200, json={"success": True, "id": "mon-1"})
    )

    await firecrawl.monitor_create.ainvoke(
        name="changelog",
        schedule={"cron": "*/30 * * * *", "timezone": "America/New_York"},
        targets=[
            {
                "type": "search",
                "queries": ["firecrawl changelog"],
                "search_window": "24h",
                "max_results": 5,
                "include_domains": ["docs.firecrawl.dev"],
            }
        ],
        judge_enabled=True,
        retention_days=7,
    )

    assert json.loads(route.calls[0].request.content) == {
        "name": "changelog",
        "schedule": {"cron": "*/30 * * * *", "timezone": "America/New_York"},
        "targets": [
            {
                "type": "search",
                "queries": ["firecrawl changelog"],
                "searchWindow": "24h",
                "maxResults": 5,
                "includeDomains": ["docs.firecrawl.dev"],
            }
        ],
        "judgeEnabled": True,
        "retentionDays": 7,
    }


@respx.mock
async def test_threat_protection_override_on_scrape():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# Hi"}})
    )

    await firecrawl.scrape.ainvoke(
        url="https://example.com",
        threat_protection={
            "mode": "normal",
            "risk_score_threshold": 80,
            "blocked_tlds": ["xyz"],
            "failure_policy": "closed",
        },
        audit_metadata={"username": "qa"},
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://example.com",
        "threatProtection": {
            "mode": "normal",
            "riskScoreThreshold": 80,
            "blockedTlds": ["xyz"],
            "failurePolicy": "closed",
        },
        "auditMetadata": {"username": "qa"},
    }


@respx.mock
async def test_research_similar_papers_path_and_query():
    route = respx.get(f"{API}search/research/papers/arxiv:1706.03762/similar").mock(
        return_value=httpx.Response(200, json={"success": True, "results": []})
    )

    await firecrawl.research_similar_papers.ainvoke(
        id="arxiv:1706.03762",
        intent="follow-up work on attention",
        mode="citers",
        rerank=True,
        anchor="arxiv:1810.04805",
    )

    assert "/search/research/papers/arxiv:1706.03762/similar" in str(route.calls[0].request.url)
    assert dict(route.calls[0].request.url.params) == {
        "intent": "follow-up work on attention",
        "mode": "citers",
        "rerank": "true",
        "anchor": "arxiv:1810.04805",
    }


@respx.mock
async def test_activity_sends_endpoint_and_cursor():
    route = respx.get(f"{API}team/activity").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [], "has_more": False})
    )

    await firecrawl.activity.ainvoke(endpoint="scrape", limit=5, cursor="abc")

    assert dict(route.calls[0].request.url.params) == {
        "endpoint": "scrape",
        "limit": "5",
        "cursor": "abc",
    }


@respx.mock
async def test_scrape_interact_and_stop_share_a_job_path():
    execute = respx.post(f"{API}scrape/job-1/interact").mock(
        return_value=httpx.Response(200, json={"success": True, "result": "ok"})
    )
    stop = respx.delete(f"{API}scrape/job-1/interact").mock(
        return_value=httpx.Response(200, json={"success": True})
    )

    await firecrawl.scrape_interact.ainvoke(job_id="job-1", code="document.title", language="node")
    await firecrawl.scrape_interact_stop.ainvoke(job_id="job-1")

    assert json.loads(execute.calls[0].request.content) == {
        "code": "document.title",
        "language": "node",
    }
    assert stop.calls[0].request.method == "DELETE"


@respx.mock
async def test_include_domains_alone_is_sent():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"success": True, "data": {"web": []}})
    )

    await firecrawl.search.ainvoke(query="example", include_domains=["example.com"])

    assert json.loads(route.calls[0].request.content) == {
        "query": "example",
        "includeDomains": ["example.com"],
    }


@respx.mock
async def test_screenshot_format_keeps_viewport_shape():
    route = respx.post(f"{API}scrape").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"screenshot": "https://cdn.example/s.png"}}
        )
    )

    await firecrawl.scrape.ainvoke(
        url="https://example.com",
        formats=[
            {
                "type": "screenshot",
                "full_page": True,
                "quality": 80,
                "viewport": {"width": 1280, "height": 720},
            }
        ],
    )

    assert json.loads(route.calls[0].request.content)["formats"] == [
        {
            "type": "screenshot",
            "fullPage": True,
            "quality": 80,
            "viewport": {"width": 1280, "height": 720},
        }
    ]


@respx.mock
async def test_extract_status_is_not_trimmed_as_a_scrape_document():
    """Extract data is the LLM object, not a Firecrawl document — do not strip it."""
    respx.get(f"{API}extract/ext-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "status": "completed",
                "data": {"heading": "Example Domain", "og:image": "keep-me"},
            },
        )
    )

    result = await firecrawl.extract_status.ainvoke(id="ext-1")
    assert result["data"] == {"heading": "Example Domain", "og:image": "keep-me"}
