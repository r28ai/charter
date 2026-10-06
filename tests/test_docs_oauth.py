"""R10.4 — the OAuth docs' code blocks actually run.

Same rule as the README suite: a snippet that only looks right costs the reader
trust the first time they paste it. Every ```python block in the OAuth docs —
the three concept pages and the three per-provider pages — is executed here,
offline, in document order, against respx.

The doc snippets are written for a web framework the reader owns, so the names
that framework would provide (``session``, ``redirect``, ``db``, ``user``, the
callback's ``code`` and ``received_state``) are stubbed — re-seeded before each
block, the way each section of a doc assumes its own context. So are the
imports the docs elide by house style: ``os`` beside a ``os.environ[...]``
credential lookup, which the surrounding page has always assumed.
"""

from __future__ import annotations

import ast
import base64
import importlib
import importlib.util
import json
import os
import re
import sys
from functools import partial
from pathlib import Path as FsPath
from types import SimpleNamespace
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from tests._doc_blocks import run_doc_block

import charter
import charter.auth
from charter.auth import OAuth2Client, revoke_token

ROOT = FsPath(__file__).resolve().parent.parent
DOCS = [
    ROOT / "docs/auth/authorization-servers.md",
    ROOT / "docs/auth/oauth-flow.md",
    ROOT / "docs/auth/your-users.mdx",
    ROOT / "docs/auth/setup/google.mdx",
    ROOT / "docs/auth/setup/slack.mdx",
    ROOT / "docs/auth/setup/github.mdx",
    ROOT / "docs/auth/setup/notion.mdx",
    ROOT / "docs/auth/apps/stripe.mdx",
    ROOT / "docs/auth/providers/google.mdx",
    ROOT / "docs/auth/providers/slack.mdx",
    ROOT / "docs/auth/providers/github.mdx",
]

# The language, then whatever the fence carries after it: a filename, and on a
# pack page a highlight range too. Both are presentation — Mintlify draws the
# name on the card's bar and bands the line — so neither changes what is
# executed here, but a pattern that stopped at the language stopped matching the
# moment a block was named, and took every snippet on the page with it.
_BLOCK = re.compile(r"^```(\w+)[^\n]*\n(.*?)^```", re.M | re.S)


def _python_blocks(doc: FsPath) -> list[str]:
    return [body for tag, body in _BLOCK.findall(doc.read_text()) if tag == "python"]


def test_the_extraction_matches_something():
    for doc in DOCS:
        assert _python_blocks(doc), f"{doc.name} has no python blocks?"


class _Keys:
    async def get(self, subject, provider):
        return SimpleNamespace(api_key="key-stored")


class _Grants:
    async def get(self, subject, provider):
        return SimpleNamespace(refresh_token="rt-stored", access_token="at-stored", expires_at=None)

    async def put(self, subject, provider, refresh_token, **shared):
        self.stored = (subject, provider, refresh_token)

    async def delete(self, subject, provider):
        self.deleted = (subject, provider)


def _stubs() -> dict:
    """What the reader's own web framework and storage would provide.

    ``GOOGLE`` is in here for the same reason ``db`` is: the setup page uses the
    constant without restating it, because google.mdx is where it is maintained.
    ``STRIPE_APPS`` likewise: the Stripe app guide derives its test-link server
    from the one your-users.mdx declares.
    Stubbing it with the canonical declaration rather than a fresh literal is
    what keeps that page honest — a snippet written against a constant nobody
    checks is the failure this whole file exists to prevent.
    """
    db = SimpleNamespace(grants=_Grants(), keys=_Keys())
    return {
        "GOOGLE": _declared_server(ROOT / "docs/auth/providers/google.mdx", "GOOGLE"),
        "STRIPE_APPS": _declared_server(ROOT / "docs/auth/your-users.mdx", "STRIPE_APPS"),
        "__name__": "__charter_docs__",
        **{name: getattr(charter, name) for name in charter.__all__ if name != "__version__"},
        **{name: getattr(charter.auth, name) for name in charter.auth.__all__},
        "os": os,
        "partial": partial,
        "session": {},
        "redirect": lambda url: url,
        "abort": lambda status: None,  # the snippet's reject path; a no-op here
        "user": SimpleNamespace(id="u1", email="ada@example.com"),
        "db": db,
        "code": "code-from-the-callback",
        "received_state": "state-from-the-callback",
        "save": lambda *args, **kwargs: None,
        "save_to_db": lambda *args, **kwargs: None,
        "stored_refresh_token": "rt-stored",
        "verifier": "pkce-verifier-from-the-session",
        "CLIENT_ID": "cid",
        "CLIENT_SECRET": "csec",
        "agent": SimpleNamespace(ainvoke=_noop_ainvoke),
        "request": SimpleNamespace(user_id="u1"),
    }


async def _noop_ainvoke(*args, **kwargs):
    return None


def _mock_the_servers_the_docs_call() -> None:
    respx.get("https://login.acme-corp.com/.well-known/openid-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "issuer": "https://login.acme-corp.com",
                "token_endpoint": "https://login.acme-corp.com/oauth2/v1/token",
                "authorization_endpoint": "https://login.acme-corp.com/oauth2/v1/authorize",
            },
        )
    )
    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "at-1",
                "refresh_token": "rt-1",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/gmail.modify",
            },
        )
    )
    # Slack answers a code exchange with the bot token at the top level and the
    # user token nested under authed_user, which is the shape the provider page
    # reads. The refresh_token and expires_in are the rotation-enabled case.
    respx.post("https://slack.com/api/oauth.v2.access").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "access_token": "xoxb-1",
                "token_type": "bot",
                "refresh_token": "xoxe-1",
                "expires_in": 43200,
                "scope": "chat:write,channels:read",
                "authed_user": {
                    "id": "U1",
                    "access_token": "xoxp-1",
                    "refresh_token": "xoxe-user-1",
                    "scope": "search:read",
                },
            },
        )
    )
    # GitHub delimits `scope` with commas rather than spaces, which is the point
    # of the split on the provider page.
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ghu-1",
                "refresh_token": "ghr-1",
                "token_type": "bearer",
                "expires_in": 28800,
                "refresh_token_expires_in": 15897600,
                "scope": "repo,read:user",
            },
        )
    )
    # The verify step on the setup page really calls this one, and reads
    # `labels` out of the body — a catch-all would let a wrong shape pass.
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/labels").mock(
        return_value=httpx.Response(200, json={"labels": [{"name": "INBOX"}, {"name": "SENT"}]})
    )
    respx.route().mock(return_value=httpx.Response(200, json={"ok": True}))


async def _run_block(source: str, namespace: dict, origin: str) -> None:
    """Execute one block at module level, awaiting it if it uses top-level await.

    Module level rather than inside a wrapper coroutine, because the blocks
    chain: a later one uses the ``GOOGLE`` a earlier one declared, and inside a
    function that assignment would be a local that vanishes.
    """
    # A route snippet ends with `return redirect(...)`, which is what the
    # reader's handler does and a syntax error at module level. The redirect
    # stays — it is the line being tested — and the `return` goes.
    source = re.sub(r"^return (\S)", r"\1", source, flags=re.M)
    await run_doc_block(source, namespace, origin)


def _credentials_in_the_environment(monkeypatch) -> None:
    """The registration facts each provider page reads out of os.environ."""
    for name in ("GOOGLE", "SLACK", "GITHUB", "LINEAR", "NOTION", "SHOPIFY"):
        monkeypatch.setenv(f"{name}_CLIENT_ID", "cid")
        monkeypatch.setenv(f"{name}_CLIENT_SECRET", "csec")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "at-static")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "rt-stored")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-static")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-static")
    monkeypatch.setenv("NOTION_API_KEY", "ntn-static")
    monkeypatch.setenv("STRIPE_APP_CLIENT_ID", "ca_app")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dev")


def _restore_the_packs_afterwards(monkeypatch) -> None:
    """A snippet configures a pack, and a pack is process-wide.

    Each document starts from unconfigured packs, as a reader's fresh process
    would, and the state is put back afterwards — so one page's per-user setup,
    or another test's, is not what the next page's single-account snippet finds.
    """
    from charter.mcp import PACKS

    for pack in PACKS:
        module = importlib.import_module(f"charter.packs.{pack}")
        holder = getattr(module, "_credentials", None)
        if holder is not None:
            monkeypatch.setattr(holder, "_provider", None)
    shop = importlib.import_module("charter.packs.shopify")._base_url
    monkeypatch.setattr(shop, "_shop", None)
    monkeypatch.setattr(shop, "_resolve", None)


@pytest.mark.parametrize("doc", DOCS, ids=[d.name for d in DOCS])
async def test_every_python_block_runs(doc, monkeypatch):
    _credentials_in_the_environment(monkeypatch)
    _restore_the_packs_afterwards(monkeypatch)

    namespace: dict = {}
    with respx.mock:
        _mock_the_servers_the_docs_call()

        for index, source in enumerate(_python_blocks(doc)):
            namespace.update(_stubs())  # re-seed; blocks may clobber stub names
            await _run_block(source, namespace, f"<{doc.name} block {index}>")


# What a server declaration is written in, and nothing else.
_DECLARATIONS = {
    "OAuth2Server": charter.auth.OAuth2Server,
    "Revocation": charter.auth.Revocation,
}


def _declared_server(path: FsPath, name: str) -> charter.auth.OAuth2Server:
    """The ``name = OAuth2Server(...)`` a file declares, built from its own source.

    Only the assignment's right-hand side is evaluated, so this works on a doc
    block that also builds a flow and on the live-check script alike.
    """
    source = path.read_text()
    sources = _python_blocks(path) if path.suffix in (".md", ".mdx") else [source]
    for block in sources:
        for node in ast.parse(block).body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
            ):
                expression = ast.Expression(node.value)
                ast.copy_location(expression, node.value)
                return eval(  # noqa: S307 — this repo's own docs and scripts
                    compile(expression, str(path), "eval"),
                    _DECLARATIONS,
                )
    raise AssertionError(f"{path.name} declares no {name}")


def test_the_google_constant_has_one_definition():
    """The provider page is canonical; the copies elsewhere must equal it.

    docs/auth/providers/google.mdx is where the constant is maintained. The flow
    guide pastes it to stay self-contained and the live check holds it to compare
    against Google's real discovery document — so all three have to agree, or the
    page a reader copies from is not the one anybody checks.
    """
    canonical = _declared_server(ROOT / "docs/auth/providers/google.mdx", "GOOGLE")
    assert canonical == _declared_server(ROOT / "docs/auth/oauth-flow.md", "GOOGLE")
    assert canonical == _declared_server(ROOT / "scripts/live_google_check.py", "DOCUMENTED")
    # ...and the one the packs renew a grant from the environment with.
    from charter.packs._google import GOOGLE

    assert canonical == GOOGLE


LIVE_CHECK = ROOT / "scripts/live_oauth_check.py"


@pytest.mark.parametrize(
    ("page", "name"),
    [
        ("docs/auth/providers/google.mdx", "GOOGLE"),
        ("docs/auth/providers/slack.mdx", "SLACK"),
        ("docs/auth/providers/github.mdx", "GITHUB"),
        ("docs/auth/your-users.mdx", "LINEAR"),
        ("docs/auth/your-users.mdx", "NOTION"),
        ("docs/auth/your-users.mdx", "STRIPE_APPS"),
    ],
)
def test_the_live_check_holds_the_constant_the_page_tells_readers_to_paste(page, name):
    """So a live check that passes is a check of the page, not of a private
    copy beside it."""
    assert _declared_server(ROOT / page, name) == _declared_server(LIVE_CHECK, name)


def _shopify_server_from(source: str):
    """The ``shopify_server`` function a source defines, built from it alone."""
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name == "shopify_server":
            namespace: dict = dict(_DECLARATIONS)
            exec(
                compile(ast.Module(body=[node], type_ignores=[]), "<shopify_server>", "exec"),
                namespace,
            )  # noqa: S102
            return namespace["shopify_server"]
    raise AssertionError("no shopify_server")


def test_the_live_check_builds_shopify_s_server_as_the_page_does():
    """A function on both sides, since the store is part of the server."""
    page = next(
        b for b in _python_blocks(ROOT / "docs/auth/your-users.mdx") if "def shopify_server" in b
    )
    built = _shopify_server_from(page)("my-store")
    assert built == _shopify_server_from(LIVE_CHECK.read_text())("my-store")


async def test_the_grant_snippet_really_reaches_storage(monkeypatch):
    """Not just 'no exception': the exchange's refresh token lands in the store."""
    _credentials_in_the_environment(monkeypatch)

    doc = ROOT / "docs/auth/oauth-flow.md"
    (source,) = [b for b in _python_blocks(doc) if "flow.exchange" in b]

    namespace = _stubs()
    with respx.mock:
        _mock_the_servers_the_docs_call()
        await _run_block(source, namespace, "<oauth-flow.md: the flow>")

    assert namespace["db"].grants.stored == ("u1", "google", "rt-1")


# -----------------------------------------------------
# The picture and the table
# -----------------------------------------------------


def _diagram_module():
    """Import the drawing script for its labels; ``scripts/`` is not a package.

    It imports cleanly here because its matplotlib and pillow imports are inside
    ``render()`` — neither is a dependency of this suite, and neither should be.
    """
    path = ROOT / "scripts" / "generate_split_diagram.py"
    spec = importlib.util.spec_from_file_location("generate_split_diagram", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


DIAGRAM = _diagram_module()


def _split_section() -> str:
    """The § The split, precisely section of the flow guide."""
    text = (ROOT / "docs/auth/oauth-flow.md").read_text()
    return text.split("## The split, precisely", 1)[1].split("\n## ", 1)[0]


def test_the_diagram_draws_the_rows_the_table_states():
    """The labels are quoted from the table, not paraphrased from it.

    A diagram is the one part of a docs page that cannot be proofread by
    reading around it — the words are inside a raster. So the strings the
    renderer draws are asserted against the prose they came from, and a reworded
    row fails here rather than leaving a picture that quietly disagrees.
    """
    section = _split_section()
    for step in DIAGRAM.STEPS:
        assert step.phrase in section, f"the diagram draws a row the table lost: {step.phrase!r}"
    assert DIAGRAM.SPAN in section, "the bracket's row is not in the table"


def test_the_table_has_no_row_the_diagram_leaves_out():
    """The other direction: a row added to the table has to be drawn.

    Every row is a step except the one the diagram turns into a bracket, so the
    table carries exactly one more line than there are steps.
    """
    rows = [
        line for line in _split_section().splitlines() if line.startswith("|") and "---" not in line
    ]
    body = len(rows) - 1  # the header
    assert body == len(DIAGRAM.STEPS) + 1, (
        f"{body} table rows against {len(DIAGRAM.STEPS)} drawn steps plus the bracket. "
        "Update scripts/generate_split_diagram.py and rerun it."
    )


def test_both_themes_of_the_diagram_are_committed_and_referenced():
    """A theme-swapped pair is only ever half-visible, so half can rot unseen."""
    section = _split_section()
    for theme in ("light", "dark"):
        image = ROOT / f"docs/images/oauth-split-{theme}.webp"
        assert image.exists(), f"{image.name} is missing — run scripts/generate_split_diagram.py"
        assert image.stat().st_size > 4096, f"{image.name} looks empty"
        assert f"/images/oauth-split-{theme}.webp" in section


# -----------------------------------------------------
# What each documented server is sent
# -----------------------------------------------------
#
# The constants are read from the pages readers paste them from, so a page
# that changes its declaration changes what is pinned here.

PROVIDERS = ROOT / "docs/auth/providers"
YOUR_USERS = ROOT / "docs/auth/your-users.mdx"


def _form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def _basic(request: httpx.Request) -> str:
    scheme, _, encoded = request.headers["Authorization"].partition(" ")
    assert scheme == "Basic"
    return base64.b64decode(encoded).decode()


@respx.mock
async def test_google_is_sent_the_refresh_token_alone():
    google = _declared_server(PROVIDERS / "google.mdx", "GOOGLE")
    route = respx.post("https://oauth2.googleapis.com/revoke").mock(
        return_value=httpx.Response(200)
    )
    client = OAuth2Client(google, client_id="cid", client_secret="csec", refresh_token="1//rt")
    assert await client.revoke() is True
    request = route.calls.last.request
    assert _form(request) == {"token": "1//rt"}  # no client secret where none is asked for


@respx.mock
async def test_slack_uninstalls_the_app_with_the_bot_token():
    slack = _declared_server(PROVIDERS / "slack.mdx", "SLACK")
    route = respx.post("https://slack.com/api/apps.uninstall").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    # An app without rotation: a bot token, revoked as a string.
    assert await revoke_token(slack, access_token="xoxb-1", client_id="cid", client_secret="csec")
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer xoxb-1"
    assert _form(request) == {"client_id": "cid", "client_secret": "csec"}

    route.mock(return_value=httpx.Response(200, json={"ok": False, "error": "invalid_auth"}))
    assert (
        await revoke_token(slack, access_token="xoxb-1", client_id="cid", client_secret="csec")
        is False
    )


@respx.mock
async def test_github_deletes_the_grant_by_access_token():
    github = _declared_server(PROVIDERS / "github.mdx", "GITHUB")
    route = respx.delete("https://api.github.com/applications/Iv1.app/grant").mock(
        return_value=httpx.Response(204)
    )
    assert await revoke_token(
        github, access_token="gho_1", client_id="Iv1.app", client_secret="csec"
    )
    request = route.calls.last.request
    assert _basic(request) == "Iv1.app:csec"
    assert json.loads(request.content) == {"access_token": "gho_1"}

    route.mock(return_value=httpx.Response(422, json={"message": "Validation Failed"}))
    assert (
        await revoke_token(github, access_token="gho_1", client_id="Iv1.app", client_secret="csec")
        is False
    )


@respx.mock
async def test_linear_is_sent_the_refresh_token_alone():
    linear = _declared_server(YOUR_USERS, "LINEAR")
    route = respx.post("https://api.linear.app/oauth/revoke").mock(return_value=httpx.Response(200))
    assert await revoke_token(linear, refresh_token="lin_rt")
    assert _form(route.calls.last.request) == {"token": "lin_rt"}

    route.mock(return_value=httpx.Response(400))  # "e.g. token was already revoked"
    assert await revoke_token(linear, refresh_token="lin_rt") is False


@respx.mock
async def test_notion_is_sent_json_with_basic_auth():
    notion = _declared_server(YOUR_USERS, "NOTION")
    route = respx.post("https://api.notion.com/v1/oauth/revoke").mock(
        return_value=httpx.Response(200, json={"request_id": "r1"})
    )
    assert await revoke_token(notion, access_token="ntn_at", client_id="cid", client_secret="csec")
    request = route.calls.last.request
    assert json.loads(request.content) == {"token": "ntn_at"}
    assert _basic(request) == "cid:csec"


@respx.mock
async def test_shopify_uninstalls_the_app_from_the_store():
    (block,) = [b for b in _python_blocks(YOUR_USERS) if "def shopify_server" in b]
    shopify = _shopify_server_from(block)("merchant")
    route = respx.delete("https://merchant.myshopify.com/admin/api_permissions/current.json").mock(
        return_value=httpx.Response(200, json={})
    )
    assert await revoke_token(shopify, access_token="shpat_1")
    request = route.calls.last.request
    assert request.headers["X-Shopify-Access-Token"] == "shpat_1"
    assert "Authorization" not in request.headers

    route.mock(return_value=httpx.Response(401, json={"errors": "[API] Invalid API key"}))
    assert await revoke_token(shopify, access_token="shpat_1") is False


def test_stripe_apps_declares_no_revocation():
    """Stripe documents no endpoint that revokes a Stripe App's grant, so none
    is declared, and revoke() says so rather than guessing at one."""
    assert _declared_server(YOUR_USERS, "STRIPE_APPS").revocation is None
