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
    """Import an example module by path, without installing the examples dir.

    ``name`` is the path under ``examples/`` without the suffix: ``gmail/send``.
    """
    path = EXAMPLES / f"{name}.py"
    module_name = "charter_example_" + name.replace("/", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_example_is_short_enough_to_read():
    """The plan caps examples at 60 lines — they are documentation."""
    for path in EXAMPLES.rglob("*.py"):
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

    names = sorted(
        p.relative_to(EXAMPLES).with_suffix("").as_posix() for p in EXAMPLES.rglob("*.py")
    )
    assert names == [
        "connect_google",
        "gmail/read",
        "gmail/reply_all",
        "gmail/save_attachments",
        "gmail/send",
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
    assert [t.name for t in listed] == [f"firecrawl_{t.name}" for t in firecrawl.TOOLS]


# -----------------------------------------------------
# The Gmail demos, each answering one public bug report
# -----------------------------------------------------

_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def _b64(text: str) -> str:
    import base64

    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _sent_message(route):
    """The RFC 822 message a mocked messages.send received, parsed."""
    import base64
    import email
    import json

    body = json.loads(route.calls.last.request.content)
    raw = body["raw"]
    parsed = email.message_from_bytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)), policy=email.policy.default
    )
    return body, parsed


@respx.mock
async def test_the_reply_all_demo_keeps_a_cc_exchange_spelled_in_capitals():
    """googleworkspace/cli#911: `CC` from Exchange, and the reply went to A alone."""
    from charter.auth import StaticTokenProvider
    from charter.packs import gmail

    gmail.configure(StaticTokenProvider("tok"))
    headers = [
        {"name": "Delivered-To", "value": "me@example.com"},
        {"name": "From", "value": "Ada <ada@example.com>"},
        {"name": "To", "value": "me@example.com"},
        {"name": "CC", "value": "Bob <bob@example.com>, cy@example.com"},
        {"name": "Subject", "value": "Q4"},
        {"name": "Message-ID", "value": "<m1@example.com>"},
    ]
    respx.get(f"{_GMAIL}/m1").mock(
        return_value=httpx.Response(
            200, json={"id": "m1", "threadId": "t1", "payload": {"headers": headers}}
        )
    )
    send = respx.post(f"{_GMAIL}/send").mock(
        return_value=httpx.Response(200, json={"id": "m2", "threadId": "t1"})
    )
    respx.get(f"{_GMAIL}/m2").mock(
        return_value=httpx.Response(200, json={"id": "m2", "payload": {"headers": headers[1:2]}})
    )

    await _load("gmail/reply_all").reply_all("m1", "Thanks", send=True)

    body, sent = _sent_message(send)
    assert body["threadId"] == "t1"
    assert sent["To"] == "Ada <ada@example.com>"
    assert sent["Cc"] == "Bob <bob@example.com>, cy@example.com"
    assert sent["Subject"] == "Re: Q4"
    assert sent["In-Reply-To"] == sent["References"] == "<m1@example.com>"


async def test_the_non_ascii_demo_encodes_the_name_rather_than_splitting_it(capsys):
    await _load("gmail/send").send("you@example.com", really=False)

    printed = capsys.readouterr().out
    assert "To: =?utf-8?q?M=C3=BCller=2C_Jos=C3=A9?= <you@example.com>" in printed
    assert "Müller" not in printed


@respx.mock
async def test_the_body_demo_shows_the_placeholder_and_reads_the_html(capsys):
    """googleworkspace/cli#889: the text/plain stub returned, the message lost."""
    from charter.auth import StaticTokenProvider
    from charter.packs import gmail

    gmail.configure(StaticTokenProvider("tok"))
    html = "<p>" + " ".join(f"word{i}" for i in range(40)) + "</p>"
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("View this email in your browser")}},
            {"mimeType": "text/html", "body": {"data": _b64(html)}},
        ],
    }
    respx.get(f"{_GMAIL}/m1").mock(
        return_value=httpx.Response(200, json={"id": "m1", "payload": payload})
    )

    await _load("gmail/read").read("m1")

    printed = capsys.readouterr().out
    assert "text/plain part: 6 words" in printed
    assert "Charter's bodyText: 40 words" in printed


@respx.mock
async def test_the_attachment_demo_writes_the_file_and_tells_a_model_it_is_binary(tmp_path, capsys):
    """googleworkspace/cli#774: unpadded base64url, which a standard decoder rejects."""
    import base64

    from charter.auth import StaticTokenProvider
    from charter.packs import gmail

    gmail.configure(StaticTokenProvider("tok"))
    pdf = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + bytes(range(256))
    part = {
        "mimeType": "application/pdf",
        "filename": "../../report.pdf",
        "body": {"attachmentId": "a1", "size": len(pdf)},
    }
    respx.get(f"{_GMAIL}/m1").mock(
        return_value=httpx.Response(200, json={"id": "m1", "payload": {"parts": [part]}})
    )
    data = base64.urlsafe_b64encode(pdf).decode().rstrip("=")
    respx.get(f"{_GMAIL}/m1/attachments/a1").mock(
        return_value=httpx.Response(200, json={"size": len(pdf), "data": data})
    )

    await _load("gmail/save_attachments").save("m1", tmp_path)

    assert (tmp_path / "report.pdf").read_bytes() == pdf
    assert "<no content: it is a binary file" in capsys.readouterr().out
