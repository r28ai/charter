"""Tavily pack — snake_case wire contract and credential guard."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from charter import APIError, CredentialError
from charter.packs import tavily

API = "https://api.tavily.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tavily.configure(api_key="tvly-test")


@respx.mock
async def test_search_posts_snake_case_json_on_the_wire():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(
            200,
            json={
                "query": "ai news",
                "results": [],
                "response_time": 0.5,
                "request_id": "req_1",
            },
        )
    )

    await tavily.search.ainvoke(
        query="ai news",
        search_depth="advanced",
        max_results=5,
        include_answer=True,
    )

    assert route.calls[0].request.headers["Authorization"] == "Bearer tvly-test"
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "query": "ai news",
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": True,
    }


@respx.mock
async def test_research_get_sends_snake_case_query_parameters():
    route = respx.get(f"{API}research/abc-123").mock(
        return_value=httpx.Response(
            200,
            json={"request_id": "abc-123", "status": "completed", "response_time": 1},
        )
    )

    await tavily.research_get.ainvoke(request_id="abc-123", include_usage=True)

    assert dict(route.calls[0].request.url.params) == {"include_usage": "true"}


@respx.mock
async def test_usage_get_has_no_body():
    route = respx.get(f"{API}usage").mock(
        return_value=httpx.Response(
            200,
            json={"key": {"usage": 10, "limit": 1000}, "account": {"current_plan": "free"}},
        )
    )

    await tavily.usage.ainvoke()

    assert route.calls[0].request.content in (b"", None)


@respx.mock
async def test_logs_no_arg_sends_an_empty_object():
    route = respx.post(f"{API}logs").mock(
        return_value=httpx.Response(200, json={"logs": [], "count": 0})
    )

    await tavily.logs.ainvoke()

    assert json.loads(route.calls[0].request.content) == {}


@respx.mock
async def test_org_usage_posts_required_organization_name():
    route = respx.post(f"{API}org-usage").mock(
        return_value=httpx.Response(
            200,
            json={"organization": {"name": "Acme"}, "totals": {"usage": 0}, "keys": []},
        )
    )

    await tavily.org_usage.ainvoke(organization_name="Acme")

    assert json.loads(route.calls[0].request.content) == {"organization_name": "Acme"}


async def test_unconfigured_pack_raises_before_a_request(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tavily._headers._api_key = None  # noqa: SLF001 — test the guard directly

    with pytest.raises(CredentialError, match="no API key"):
        await tavily.search.ainvoke(query="test")


def test_search_rejects_include_domains_mode_without_domains():
    from charter.packs.tavily.types.search.actions import SearchRequest

    with pytest.raises(ValueError, match="include_domains"):
        SearchRequest(query="test", include_domains_mode="filter")


def test_every_tool_llm_schema_builds():
    for tool in tavily.TOOLS:
        schema = tool.llm_schema()
        assert schema.model_json_schema()["type"] == "object"


def test_extract_accepts_a_single_url_string():
    from charter.packs.tavily.types.extract.actions import ExtractRequest

    ExtractRequest(urls="https://example.com")


def test_extract_rejects_more_than_twenty_urls():
    from charter.packs.tavily.types.extract.actions import ExtractRequest

    with pytest.raises(ValueError, match="at most 20"):
        ExtractRequest(urls=[f"https://example.com/{i}" for i in range(21)])


def test_research_file_rejects_an_unsupported_extension():
    from charter.packs.tavily.types.research.actions import ResearchFile

    with pytest.raises(ValueError, match="\\.txt, \\.md, or \\.json"):
        ResearchFile(name="notes.pdf", data="YWJj")


def test_output_schema_object_requires_properties():
    from charter.packs.tavily.types.research.actions import OutputSchemaProperty

    with pytest.raises(ValueError, match="require `properties`"):
        OutputSchemaProperty(type="object")


def test_output_schema_array_requires_items():
    from charter.packs.tavily.types.research.actions import OutputSchemaProperty

    with pytest.raises(ValueError, match="require `items`"):
        OutputSchemaProperty(type="array", description="A list.")


def test_research_output_schema_allows_items_without_description():
    from charter.packs.tavily.types.research.actions import ResearchCreateRequest

    ResearchCreateRequest(
        input="colors",
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


def test_search_rejects_an_undocumented_country():
    from charter.packs.tavily.types.search.actions import SearchRequest

    with pytest.raises(ValueError):
        SearchRequest(query="test", country="atlantis")


@respx.mock
async def test_usage_accepts_x_project_id_via_per_call_headers():
    route = respx.get(f"{API}usage").mock(
        return_value=httpx.Response(
            200,
            json={"key": {"usage": 1, "limit": 1000}, "account": {"current_plan": "free"}},
        )
    )

    await tavily.usage.ainvoke(headers={"X-Project-ID": "proj-123"})

    assert route.calls[0].request.headers["X-Project-ID"] == "proj-123"


@respx.mock
async def test_research_file_type_reaches_the_wire_as_type():
    route = respx.post(f"{API}research").mock(
        return_value=httpx.Response(
            201,
            json={
                "request_id": "req-1",
                "created_at": "2025-01-15T10:30:00Z",
                "status": "pending",
                "input": "summarize",
                "model": "mini",
                "response_time": 1,
            },
        )
    )

    await tavily.research_create.ainvoke(
        input="summarize",
        files=[{"name": "notes.md", "data": "YWJj", "type": "base64"}],
    )

    files = json.loads(route.calls[0].request.content)["files"]
    assert files == [{"name": "notes.md", "data": "YWJj", "type": "base64"}]


@respx.mock
async def test_search_with_only_query_sends_no_copied_defaults():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"query": "ai", "results": [], "request_id": "r"})
    )

    await tavily.search.ainvoke(query="ai")

    assert json.loads(route.calls[0].request.content) == {"query": "ai"}


@respx.mock
async def test_extract_single_url_string_stays_a_string_on_the_wire():
    route = respx.post(f"{API}extract").mock(
        return_value=httpx.Response(200, json={"results": [], "request_id": "r"})
    )

    await tavily.extract.ainvoke(urls="https://example.com")

    assert json.loads(route.calls[0].request.content) == {"urls": "https://example.com"}


@respx.mock
async def test_include_answer_advanced_stays_the_documented_union_value():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"query": "ai", "results": [], "request_id": "r"})
    )

    await tavily.search.ainvoke(
        query="ai",
        include_answer="advanced",
        include_raw_content="text",
        include_usage=True,
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "ai",
        "include_answer": "advanced",
        "include_raw_content": "text",
        "include_usage": True,
    }


@respx.mock
async def test_map_and_crawl_with_only_url_send_no_copied_defaults():
    mapped = respx.post(f"{API}map").mock(
        return_value=httpx.Response(200, json={"base_url": "https://a.example", "results": []})
    )
    crawled = respx.post(f"{API}crawl").mock(
        return_value=httpx.Response(200, json={"base_url": "https://a.example", "results": []})
    )

    await tavily.map.ainvoke(url="https://a.example")
    await tavily.crawl.ainvoke(url="https://a.example")

    assert json.loads(mapped.calls[0].request.content) == {"url": "https://a.example"}
    assert json.loads(crawled.calls[0].request.content) == {"url": "https://a.example"}


@respx.mock
async def test_research_get_202_is_still_running_not_an_error():
    respx.get(f"{API}research/abc-123").mock(
        return_value=httpx.Response(
            202,
            json={"request_id": "abc-123", "status": "in_progress", "response_time": 1},
        )
    )

    result = await tavily.research_get.ainvoke(request_id="abc-123")
    assert result["status"] == "in_progress"


@respx.mock
async def test_tavily_nested_detail_error_reaches_the_exception_message():
    respx.post(f"{API}extract").mock(
        return_value=httpx.Response(
            400,
            json={"detail": {"error": "Max 20 URLs are allowed."}},
        )
    )

    with pytest.raises(APIError, match="Max 20 URLs are allowed") as exc:
        await tavily.extract.ainvoke(urls=[f"https://example.com/{i}" for i in range(2)])

    assert exc.value.message == "Max 20 URLs are allowed."
    assert exc.value.status_code == 400


@respx.mock
async def test_logs_merges_filters_onto_the_required_empty_object():
    route = respx.post(f"{API}logs").mock(
        return_value=httpx.Response(200, json={"logs": [], "count": 0})
    )

    await tavily.logs.ainvoke(limit=5, endpoints=["search", "research"], filter_by_api_key=False)

    assert json.loads(route.calls[0].request.content) == {
        "limit": 5,
        "endpoints": ["search", "research"],
        "filter_by_api_key": False,
    }


@respx.mock
async def test_crawl_select_and_exclude_paths_stay_snake():
    route = respx.post(f"{API}crawl").mock(
        return_value=httpx.Response(
            200, json={"base_url": "https://docs.tavily.com", "results": []}
        )
    )

    await tavily.crawl.ainvoke(
        url="https://docs.tavily.com",
        instructions="Python SDK pages only",
        chunks_per_source=2,
        max_depth=2,
        select_paths=["/sdk/.*"],
        exclude_paths=["/changelog/.*"],
        include_usage=True,
        format="text",
    )

    assert json.loads(route.calls[0].request.content) == {
        "url": "https://docs.tavily.com",
        "instructions": "Python SDK pages only",
        "chunks_per_source": 2,
        "max_depth": 2,
        "select_paths": ["/sdk/.*"],
        "exclude_paths": ["/changelog/.*"],
        "include_usage": True,
        "format": "text",
    }


@respx.mock
async def test_include_domains_mode_reaches_the_wire_with_domains():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"query": "ai", "results": [], "request_id": "r"})
    )

    await tavily.search.ainvoke(
        query="ai",
        include_domains=["example.com"],
        include_domains_mode="filter",
        country="united states",
        topic="general",
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "ai",
        "include_domains": ["example.com"],
        "include_domains_mode": "filter",
        "country": "united states",
        "topic": "general",
    }


def test_search_llm_schema_rejects_country_when_topic_is_news():
    with pytest.raises(ValueError, match="topic is general"):
        tavily.search.llm_schema()(query="x", topic="news", country="united states")


def test_search_llm_schema_rejects_safe_search_on_fast_depth():
    with pytest.raises(ValueError, match="safe_search"):
        tavily.search.llm_schema()(query="x", search_depth="fast", safe_search=True)


def test_search_llm_schema_rejects_chunks_on_ultra_fast():
    with pytest.raises(ValueError, match="chunks_per_source"):
        tavily.search.llm_schema()(query="x", search_depth="ultra-fast", chunks_per_source=2)


def test_extract_llm_schema_rejects_chunks_without_query():
    with pytest.raises(ValueError, match="chunks_per_source requires query"):
        tavily.extract.llm_schema()(urls=["https://example.com"], chunks_per_source=2)


def test_crawl_llm_schema_rejects_chunks_without_instructions():
    with pytest.raises(ValueError, match="chunks_per_source requires instructions"):
        tavily.crawl.llm_schema()(url="https://example.com", chunks_per_source=2)


@respx.mock
async def test_research_create_omits_stream():
    route = respx.post(f"{API}research").mock(
        return_value=httpx.Response(
            201,
            json={
                "request_id": "req-1",
                "created_at": "2025-01-15T10:30:00Z",
                "status": "pending",
                "input": "summarize",
                "model": "mini",
                "response_time": 1,
            },
        )
    )

    await tavily.research_create.ainvoke(input="summarize", model="mini", citation_format="apa")

    body = json.loads(route.calls[0].request.content)
    assert body == {"input": "summarize", "model": "mini", "citation_format": "apa"}
    assert "stream" not in body


@respx.mock
async def test_llm_camel_arguments_reach_the_wire_as_snake():
    route = respx.post(f"{API}search").mock(
        return_value=httpx.Response(200, json={"query": "ai", "results": [], "request_id": "r"})
    )

    await tavily.search.ainvoke(
        query="ai",
        includeRawContent="text",
        maxResults=3,
        includeDomainsMode="filter",
        includeDomains=["example.com"],
    )

    assert json.loads(route.calls[0].request.content) == {
        "query": "ai",
        "include_raw_content": "text",
        "max_results": 3,
        "include_domains_mode": "filter",
        "include_domains": ["example.com"],
    }


def test_research_file_llm_schema_uses_type_not_type_underscore():
    schema = tavily.research_create.llm_schema().model_json_schema()
    defs = schema.get("$defs") or schema.get("definitions") or {}
    file_schema = next(
        (spec for name, spec in defs.items() if "ResearchFile" in name),
        None,
    )
    assert file_schema is not None
    assert "type" in file_schema["properties"]
    assert "type_" not in file_schema["properties"]


def test_extract_crawl_and_map_wait_past_documented_timeouts():
    assert tavily.extract.timeout >= 60
    assert tavily.crawl.timeout >= 150
    assert tavily.map.timeout >= 150


def test_search_rejects_filter_by_language_without_language():
    from charter.packs.tavily.types.search.actions import SearchRequest

    with pytest.raises(ValueError, match="language"):
        SearchRequest(query="test", filter_by_language=True)
