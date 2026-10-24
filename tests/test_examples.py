"""The shipped examples actually run, offline.

Every example is imported, the basics that need no account are executed as they
are, and the ones that call an API or a model are replayed: respx answers for
the API, and a scripted model makes the calls a real run made. Examples that
only look right are worse than none, and a reader follows a link to one long
after it was written.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
from pathlib import Path as FsPath
from typing import Any

import httpx
import pytest
import respx

EXAMPLES = FsPath(__file__).resolve().parent.parent / "examples"
GITHUB = "https://api.github.com"


def _load(name: str):
    """Import an example module by path, without installing the examples dir.

    ``name`` is the path under ``examples/`` without the suffix: ``basics/01_hello_tool``.
    """
    path = EXAMPLES / f"{name}.py"
    module_name = "charter_example_" + name.replace("/", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _names() -> list[str]:
    return sorted(
        p.relative_to(EXAMPLES).with_suffix("").as_posix() for p in EXAMPLES.rglob("*.py")
    )


def test_every_example_fits_on_a_screen():
    """An example is read top to bottom. Comments, which hold what a real run printed, are
    not counted. A basic stays under 60 lines; 100 is the web app in connect/."""
    for path in EXAMPLES.rglob("*.py"):
        tree = ast.parse(path.read_text())
        lines = path.read_text().splitlines()[tree.body[0].end_lineno :]
        code = [line for line in lines if not line.strip().startswith("#")]
        limit = 60 if path.parent.name == "basics" else 100
        assert len(code) <= limit, f"{path.relative_to(EXAMPLES)} is {len(code)} lines of code"


def test_every_example_opens_with_a_short_docstring():
    """What it shows and what it needs, in a few lines. The rest is code."""
    for path in EXAMPLES.rglob("*.py"):
        docstring = ast.get_docstring(ast.parse(path.read_text()))
        assert docstring, f"{path.name} doesn't say what it shows"
        assert len(docstring.splitlines()) <= 4, f"{path.name}'s docstring is a header"


def _environment_keys(tree: ast.AST) -> set[str]:
    """Every `os.environ["KEY"]` and `os.environ.get("KEY")` in a file."""
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            keys.add(ast.literal_eval(node.slice))
        elif isinstance(node, ast.Call) and ast.unparse(node.func) == "os.environ.get":
            keys.add(ast.literal_eval(node.args[0]))
    return keys


def test_what_an_example_needs_is_on_its_first_line():
    """Every key a file reads from the environment is named on line 1, before anything else.
    MODEL is optional: it picks a different model."""
    for path in EXAMPLES.rglob("*.py"):
        text = path.read_text()
        tree = ast.parse(text)
        for key in _environment_keys(tree) - {"MODEL"}:
            assert key in text.splitlines()[0], f"{path.name} reads {key}; line 1 doesn't say so"
        assert "Needs" not in (ast.get_docstring(tree) or ""), path.name


def test_a_basic_needs_nothing_but_charter():
    """Each basic shows one thing about Charter, and runs with no key: no model client, no SDK."""
    allowed = {"asyncio", "base64", "datetime", "importlib", "json", "logging", "os", "pkgutil",
               "sys", "textwrap", "typing", "pydantic",
               "httpx", "charter"}  # fmt: skip
    for path in (EXAMPLES / "basics").glob("*.py"):
        tree = ast.parse(path.read_text())
        imported = {
            (node.module or "").split(".")[0] for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name.split(".")[0] for node in ast.walk(tree)
            if isinstance(node, ast.Import) for alias in node.names
        }  # fmt: skip
        assert imported <= allowed, f"{path.name} imports {imported - allowed}"


def test_no_basic_needs_a_key():
    """examples/README.md and the README promise the basics run with nothing set up, in order.
    An example that needs a key belongs in connect/ or frameworks/, where its first line says so."""
    for path in (EXAMPLES / "basics").glob("*.py"):
        first = path.read_text().splitlines()[0]
        assert not first.startswith("# Needs"), f"{path.name}: {first}"


def test_no_example_shadows_a_package_it_imports():
    """A script's own folder comes first on sys.path: `openai.py` would import itself."""
    for path in EXAMPLES.rglob("*.py"):
        imported = {
            (node.module or "").split(".")[0]
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom)
        } | {
            alias.name.split(".")[0]
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        siblings = {p.stem for p in path.parent.glob("*.py")}
        assert not imported & siblings, (
            f"{path.relative_to(EXAMPLES)} shadows {imported & siblings}"
        )


@pytest.fixture
def packs_restored():
    """Examples call `configure()`, and packs are process-wide: hand them back as found."""
    import importlib

    from charter.mcp import PACKS

    saved = []
    for name in PACKS:
        module = importlib.import_module(f"charter.packs.{name}")
        for attr in ("_credentials", "_headers"):
            holder = getattr(module, attr, None)
            for field in ("_provider", "_api_key", "_shop"):
                if holder is not None and hasattr(holder, field):
                    saved.append((holder, field, getattr(holder, field)))
    try:
        yield
    finally:
        for holder, field, value in saved:
            setattr(holder, field, value)


@pytest.fixture
def github_app(monkeypatch, tmp_path):
    """What users_oauth.py reads at import, and a folder for its grants.db."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "csec")


def test_every_example_is_listed_and_run_below():
    """Most examples run as they are imported, so each one is loaded by a test of its own
    with the API it calls mocked. A new file has to be added here, and given one."""
    assert _names() == [
        "basics/01_hello_tool",
        "basics/02_wire_formats",
        "basics/03_errors_for_the_model",
        "basics/04_trim_responses",
        "basics/05_catch_failed_200s",
        "basics/06_cut_a_tool",
        "basics/07_price_a_tool",
        "basics/08_many_tools",
        "basics/09_rules_on_fields",
        "basics/10_pin_a_value",
        "basics/11_one_tool_per_plan",
        "basics/12_scopes_from_tools",
        "basics/13_review_the_boundary",
        "connect/my_api_keys",
        "connect/my_google",
        "connect/use_a_pack",
        "connect/users_api_keys",
        "connect/users_oauth",
        "connect/users_refresh",
        "frameworks/langchain_agent",
        "frameworks/mcp_server",
        "frameworks/openai_loop",
    ]


# --------------------------------------------------------------------- basics


def _echo(request: httpx.Request) -> httpx.Response:
    """httpbin.org/anything: the request, handed back."""
    return httpx.Response(200, json={
        "method": request.method, "url": str(request.url),
        "headers": {"Authorization": request.headers.get("authorization")},
        "json": json.loads(request.content or b"null"),
    })  # fmt: skip


@respx.mock
def test_hello_tool_shows_the_schema_then_what_was_sent(capsys):
    respx.route(host="httpbin.org").mock(side_effect=_echo)
    _load("basics/01_hello_tool")
    assert capsys.readouterr().out.splitlines() == [
        "the model fills in ['calendarId', 'maxResults', 'timeMin']",
        "Charter sent       GET https://httpbin.org/anything/calendars/primary/events"
        "?maxResults=5&timeMin=2026-10-20T10%3A00%3A00",
        "  auth header      Bearer sk_live_123  (the model never saw it)",
    ]


@respx.mock
def test_use_a_pack_trims_then_hands_back_everything_then_parses(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    runs = [{"name": "CI", "run_number": n, "conclusion": "success", "id": n} for n in (108, 107)]
    route = respx.get(f"{GITHUB}/repos/r28ai/charter/actions/runs").respond(
        json={"total_count": 2, "workflow_runs": runs}
    )
    _load("connect/use_a_pack")
    latest, parsed = capsys.readouterr().out.splitlines()
    assert latest == "Latest CI run: CI #108, success"
    assert parsed == "['#108 success', '#107 success']"
    assert route.call_count == 3


def test_the_offline_basics_print_what_they_promise(capsys):
    _load("basics/06_cut_a_tool")
    assert capsys.readouterr().out.splitlines() == [
        "both tools call  POST v1/documents/{document_id}:batchUpdate",
        "full            33 kinds of edit",
        "edit_text       replace_all_text, insert_text, delete_content_range",
    ]

    _load("basics/07_price_a_tool")
    out = capsys.readouterr().out
    assert out.startswith("linear.issues_list_full costs 45,072 tokens") and "filter" in out

    _load("basics/10_pin_a_value")
    sets, never = capsys.readouterr().out.splitlines()
    assert sets.startswith("the model sets  page_size")
    assert never == (
        "it never sees   q, which every call sends as "
        "\"mimeType='application/vnd.google-apps.document'\""
    )

    _load("basics/12_scopes_from_tools")
    reader, cleaner = capsys.readouterr().out.splitlines()
    assert reader == "a reader  asks for  gmail.readonly, calendar.events.readonly"
    assert cleaner == "a cleaner asks for  https://mail.google.com/, calendar.events.readonly"

    _load("basics/09_rules_on_fields")
    amount, cut = capsys.readouterr().out.splitlines()
    assert amount.startswith("the model reads on amount: A positive integer")
    assert amount.endswith("Cents, not dollars: $15.00 is 1500, and 15 is 15 cents.")
    assert cut == "cut amount, and its rule leaves too: ['charge', 'reason']"


@respx.mock
def test_one_tool_per_plan_refuses_then_sends_the_same_call(capsys):
    echo = respx.post("https://httpbin.org/anything/accounts/acc_42/reports").mock(
        side_effect=_echo
    )
    _load("basics/11_one_tool_per_plan")
    free, pro, sent = capsys.readouterr().out.splitlines()
    assert free == "free  refused  raw_events, forecast_months"
    assert pro == "pro   refused  forecast_months"
    assert sent.startswith("max   sent") and echo.call_count == 1
    assert json.loads(echo.calls.last.request.content) == {
        "metric": "revenue",
        "rawEvents": True,
        "forecastMonths": 6,
    }


@respx.mock
def test_catch_failed_200s_raises_on_graphqls_errors(capsys):
    errors = {"errors": [{"message": 'Cannot query field "population" on type "Country".'}]}
    route = respx.post("https://countries.trevorblades.com/graphql").respond(200, json=errors)
    _load("basics/05_catch_failed_200s")
    trusting, blank, enveloped = capsys.readouterr().out.splitlines()
    assert blank == ""
    assert trusting == "without the envelope: no error, the call returned ['errors']"
    assert enveloped.startswith("with the envelope:    APIError on HTTP 200, the API rejected")
    assert "population" in enveloped
    assert json.loads(route.calls.last.request.content)["query"].startswith("{ country")


@respx.mock
def test_trim_responses_does_nothing_then_keeps_what_matters(capsys):
    user = {"id": 1, "name": "Leanne Graham", "email": "Sincere@april.biz",
            "address": {"geo": {"lat": "-37.3159"}}, "company": {"name": "Romaguera-Crona"}}  # fmt: skip
    respx.get("https://jsonplaceholder.typicode.com/users").respond(json=[user])
    _load("basics/04_trim_responses")
    nothing, handled = capsys.readouterr().out.splitlines()
    assert nothing.startswith("do nothing:") and "address" in nothing
    assert handled.startswith("with a handler:") and handled.endswith("fields name, email, company")


@respx.mock
def test_hand_to_a_model_runs_the_loop(monkeypatch, capsys):
    pytest.importorskip("openai", reason="needs openai")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fw_test")
    users = respx.get("https://jsonplaceholder.typicode.com/users").respond(
        json=[{"id": 2, "username": "Antonette"}]
    )

    def turn(message: dict) -> httpx.Response:
        choice = {"index": 0, "message": {"role": "assistant", **message}, "finish_reason": "stop"}
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0,
                                         "model": "m", "choices": [choice]})  # fmt: skip

    def tool_call(name: str, args: dict) -> dict:
        call = {"id": f"call-{name}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}  # fmt: skip
        return {"content": None, "tool_calls": [call]}

    respx.post("https://api.fireworks.ai/inference/v1/chat/completions").mock(
        side_effect=[
            turn(tool_call("myapi_find_users", {"username": "Antonette"})),
            turn({"content": "12."}),
        ]
    )
    module = _load("frameworks/openai_loop")
    # The client's own transport is out of respx's reach; a plain httpx client isn't.
    from openai import AsyncOpenAI

    monkeypatch.setattr(
        module, "AsyncOpenAI", lambda **kw: AsyncOpenAI(**kw, http_client=httpx.AsyncClient())
    )
    asyncio.run(module.main())
    assert users.calls.last.request.url.params["username"] == "Antonette"
    assert capsys.readouterr().out.strip() == "12."


# ----------------------------------------------------------------- frameworks


def _scripted(*calls: dict, final: str = "Done."):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    class Scripted(GenericFakeChatModel):
        """Says what it is told to, in order, and accepts any tools it is given."""

        def bind_tools(self, tools: Any, **kwargs: Any) -> Scripted:
            return self

    turns = [AIMessage("", tool_calls=[call]) for call in calls] + [AIMessage(final)]
    return Scripted(messages=iter(turns))


def _call(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "id": f"call-{name}"}


@respx.mock
def test_langchain_example_runs_the_loop():
    pytest.importorskip("langchain.agents", reason="needs langchain")
    todos = [{"userId": 2, "id": 21, "title": "x", "completed": False}]
    route = respx.get("https://jsonplaceholder.typicode.com/todos").respond(json=todos)
    model = _scripted(_call("myapi_list_todos", {"userId": 2, "completed": False}), final="1.")
    state = asyncio.run(
        _load("frameworks/langchain_agent")
        .build_agent(model)
        .ainvoke({"messages": [{"role": "user", "content": "left?"}]})
    )
    assert route.called and state["messages"][-1].text == "1."
    assert dict(route.calls.last.request.url.params) == {"userId": "2", "completed": "false"}


async def test_mcp_example_lists_tools(monkeypatch):
    pytest.importorskip("mcp", reason="needs the [mcp] extra")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test")

    from charter.packs import firecrawl

    listed = await _load("frameworks/mcp_server").build().list_tools()
    assert [t.name for t in listed] == [f"firecrawl_{t.name}" for t in firecrawl.TOOLS]


# -------------------------------------------------------------------- connect


def test_connect_google_example_builds_a_consent_url(monkeypatch):
    """The on-ramp example: PKCE on, Google's silent-failure params present."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csec")

    module = _load("connect/my_google")
    request = module.build_flow().authorize(["https://www.googleapis.com/auth/gmail.modify"])

    assert request.url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge_method=S256" in request.url
    assert "access_type=offline" in request.url and "prompt=consent" in request.url
    assert request.code_verifier and request.state


@respx.mock
def test_my_api_keys_example_fixes_or_fetches_the_key(capsys):
    respx.route(host="httpbin.org").mock(side_effect=_echo)
    _load("connect/my_api_keys")
    assert capsys.readouterr().out.splitlines() == [
        "fixed     Bearer sk_live_123",
        "fetched   Bearer sk_live_v1",
        "fetched   Bearer sk_live_v2",
    ]


@respx.mock
def test_users_api_keys_example_acts_as_each_user(capsys):
    respx.route(host="httpbin.org").mock(side_effect=_echo)
    _load("connect/users_api_keys")
    ada, bo, nobody = capsys.readouterr().out.splitlines()
    assert ada == "ada      sent     Bearer sk_live_ada_123"
    assert bo == "bo       refused  bo hasn't connected yet"
    assert nobody.startswith("nobody   refused  No subject is set")


@respx.mock
def test_users_oauth_example_connects_calls_and_disconnects(github_app, packs_restored):
    pytest.importorskip("fastapi", reason="needs fastapi")
    token = respx.post("https://github.com/login/oauth/access_token").respond(
        json={"access_token": "gho_ada", "token_type": "bearer", "scope": "repo,read:user"}
    )
    me = respx.get(f"{GITHUB}/user").respond(json={"login": "ada-gh"})
    revoke = respx.delete(f"{GITHUB}/applications/cid/grant").respond(204)
    app = _load("connect/users_oauth").app

    async def browse() -> None:
        # httpx's own ASGI transport: respx leaves it alone, so the app is reached directly.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as browser:
            assert "Connect GitHub" in (await browser.get("/?user=ada")).text

            consent = await browser.get("/connect?user=ada")
            assert consent.headers["location"].startswith(
                "https://github.com/login/oauth/authorize?"
            )
            state = browser.cookies["oauth"].strip('"').split(":")[0]

            assert (await browser.get("/callback?code=wrong&state=forged")).status_code == 400
            assert not token.called

            done = await browser.get(f"/callback?code=c1&state={state}")
            assert done.headers["location"] == "/?user=ada"
            assert "Hi ada-gh" in (await browser.get("/?user=ada")).text
            assert me.calls.last.request.headers["authorization"] == "Bearer gho_ada"

            await browser.get("/disconnect?user=ada")
            assert revoke.called
            assert "Connect GitHub" in (await browser.get("/?user=ada")).text

    asyncio.run(browse())


# ---------------------------------------------------------------- the newer basics


@respx.mock
def test_wire_formats_turns_an_email_into_base64_mime(capsys):
    respx.route(host="httpbin.org").mock(side_effect=_echo)
    _load("basics/02_wire_formats")
    out = capsys.readouterr().out
    assert out.startswith("the model fills in  to, subject, body")
    assert "To: ada@example.com" in out and "Subject: Lunch?" in out
    assert out.rstrip().endswith("Thursday at noon?")


def test_errors_for_the_model_are_refused_before_sending(capsys):
    with respx.mock(assert_all_called=False) as router:
        sent = router.route(host="httpbin.org")
        _load("basics/03_errors_for_the_model")
    out = capsys.readouterr().out
    assert "(got 'ten')" in out
    assert "q cannot be combined with syncToken" in out and "Drop syncToken" in out
    assert not sent.called


def test_many_tools_sends_one_search_tool_first(capsys):
    _load("basics/08_many_tools")
    every, first, searched = capsys.readouterr().out.splitlines()
    tokens = lambda line: int(line.split("tokens")[0].split()[-1].replace(",", ""))  # noqa: E731
    assert tokens(first) < tokens(searched) < tokens(every)
    assert first.endswith("one search tool") and "gmail_messages_send" in searched


def test_review_the_boundary_names_what_widened(capsys):
    _load("basics/13_review_the_boundary")
    assert capsys.readouterr().out.splitlines() == [
        "gdrive_search_docs    the model can now set q",
        "gmail_messages_send   new tool",
    ]


@respx.mock
def test_users_refresh_refreshes_once_and_stores_it(monkeypatch, capsys, packs_restored):
    for name, value in {"GOOGLE_CLIENT_ID": "cid", "GOOGLE_CLIENT_SECRET": "csec",
                        "GOOGLE_REFRESH_TOKEN": "1//ada"}.items():  # fmt: skip
        monkeypatch.setenv(name, value)
    token = respx.post("https://oauth2.googleapis.com/token").respond(
        json={"access_token": "ya29.ada", "expires_in": 3599, "token_type": "Bearer"}
    )
    about = respx.get("https://www.googleapis.com/drive/v3/about").respond(
        json={"user": {"emailAddress": "ada@example.com"}}
    )
    module = _load("connect/users_refresh")

    refreshed, first, second = capsys.readouterr().out.splitlines()
    assert refreshed.startswith("  refreshed ada's token") and refreshed.endswith("stored")
    assert first == "first call   Drive says this is ada@example.com"
    assert second == "second call  Drive says this is ada@example.com"
    assert token.call_count == 1 and about.call_count == 2
    assert about.calls.last.request.headers["authorization"] == "Bearer ya29.ada"
    assert module.grants["ada"]["access_token"] == "ya29.ada"
