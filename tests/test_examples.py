"""R4 — the shipped examples actually run, against respx.

The plan's R4 acceptance criterion: the weather example, rewritten on the new
API, runs against a mock. Examples that only look right are worse than none.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path as FsPath

import httpx
import pytest
import respx

EXAMPLES = FsPath(__file__).resolve().parent.parent / "examples"


def _load(name: str):
    """Import an example module by path, without installing the examples dir."""
    path = EXAMPLES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"charter_example_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_example_is_short_enough_to_read():
    """The plan caps examples at 60 lines — they are documentation."""
    for path in EXAMPLES.glob("*.py"):
        lines = len(path.read_text().splitlines())
        assert lines <= 60, f"{path.name} is {lines} lines"


@respx.mock
async def test_weather_example_runs(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    route = respx.get("https://api.openweathermap.org/data/2.5/weather/Tokyo").mock(
        return_value=httpx.Response(200, json={"main": {"temp": 21.5}})
    )

    tool = _load("weather_api_key").build_tool()
    result = await tool.ainvoke(city="Tokyo")

    assert result == {"main": {"temp": 21.5}}
    request = route.calls.last.request
    assert request.headers["x-api-key"] == "test-key"
    assert dict(request.url.params) == {"units": "metric"}


def test_weather_example_function_schema_is_well_formed(monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    fn = _load("weather_api_key").build_tool().to_json_schema()

    assert fn["name"] == "get_current_weather"
    assert set(fn["parameters"]["properties"]) == {"city", "units"}
    assert fn["parameters"]["required"] == ["city"]


@respx.mock
async def test_gmail_example_runs(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "tok123")
    route = respx.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send").mock(
        return_value=httpx.Response(200, json={"id": "m1", "threadId": "t1"})
    )

    tool = _load("gmail_send").build_tool()
    result = await tool.ainvoke(raw={"to": "ada@example.com", "subject": "Hi", "body": "Hello"})

    assert result["id"] == "m1"
    assert route.calls.last.request.headers["authorization"] == "Bearer tok123"


def test_gmail_example_hides_response_only_fields(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "tok123")
    fields = _load("gmail_send").build_tool().llm_schema().model_fields
    assert "id" not in fields
    assert "thread_id" not in fields
    assert "raw" in fields


# -----------------------------------------------------
# R8 examples
# -----------------------------------------------------


def test_every_example_module_imports(monkeypatch):
    """Every example must at least load without credentials present."""
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    names = sorted(p.stem for p in EXAMPLES.glob("*.py"))
    assert names == [
        "connect_google",
        "gmail_send",
        "langchain_agent",
        "mcp_server",
        "weather_api_key",
    ]
    for name in names:
        _load(name)


def test_connect_google_example_builds_a_consent_url(monkeypatch):
    """The on-ramp example: PKCE on, Google's silent-failure params present."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")

    module = _load("connect_google")
    request = module.build_flow().authorize(["https://www.googleapis.com/auth/gmail.modify"])

    assert request.url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge_method=S256" in request.url
    assert "access_type=offline" in request.url and "prompt=consent" in request.url
    assert request.code_verifier and request.state


def test_langchain_example_builds_bound_tools(monkeypatch):
    pytest.importorskip("langchain_core", reason="needs the [langchain] extra")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "test-token")

    from charter.packs import gmail

    tools = _load("langchain_agent").build_tools()
    assert len(tools) == len(gmail.TOOLS)
    assert all(t.args_schema is not None for t in tools)


async def test_mcp_example_lists_tools(monkeypatch):
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    from charter.packs import firecrawl

    listed = await _load("mcp_server").build().list_tools()
    assert [t.name for t in listed] == [f"firecrawl__{t.name}" for t in firecrawl.TOOLS]
