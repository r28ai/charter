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
import importlib.util
import inspect
import os
import re
import sys
from functools import partial
from pathlib import Path as FsPath
from types import SimpleNamespace

import httpx
import pytest
import respx

import charter
import charter.auth

ROOT = FsPath(__file__).resolve().parent.parent
DOCS = [
    ROOT / "docs/auth/authorization-servers.md",
    ROOT / "docs/auth/oauth-flow.md",
    ROOT / "docs/auth/your-own-account.mdx",
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


class _Grants:
    async def get(self, subject, provider):
        return SimpleNamespace(refresh_token="rt-stored")

    async def put(self, subject, provider, refresh_token):
        self.stored = (subject, provider, refresh_token)


def _stubs() -> dict:
    """What the reader's own web framework and storage would provide.

    ``GOOGLE`` is in here for the same reason ``db`` is: the setup page uses the
    constant without restating it, because google.mdx is where it is maintained.
    Stubbing it with the canonical declaration rather than a fresh literal is
    what keeps that page honest — a snippet written against a constant nobody
    checks is the failure this whole file exists to prevent.
    """
    db = SimpleNamespace(grants=_Grants())
    return {
        "GOOGLE": _declared_server(ROOT / "docs/auth/providers/google.mdx", "GOOGLE"),
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
    code = compile(source, origin, "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True)
    result = eval(code, namespace)  # noqa: S307 — the input is this repo's own docs
    if inspect.iscoroutine(result):
        await result


def _credentials_in_the_environment(monkeypatch) -> None:
    """The registration facts each provider page reads out of os.environ."""
    for name in ("GOOGLE", "SLACK", "GITHUB"):
        monkeypatch.setenv(f"{name}_CLIENT_ID", "cid")
        monkeypatch.setenv(f"{name}_CLIENT_SECRET", "csec")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "at-static")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "rt-stored")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-static")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-static")


@pytest.mark.parametrize("doc", DOCS, ids=[d.name for d in DOCS])
async def test_every_python_block_runs(doc, monkeypatch):
    _credentials_in_the_environment(monkeypatch)

    namespace: dict = {}
    with respx.mock:
        _mock_the_servers_the_docs_call()

        for index, source in enumerate(_python_blocks(doc)):
            namespace.update(_stubs())  # re-seed; blocks may clobber stub names
            await _run_block(source, namespace, f"<{doc.name} block {index}>")


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
                    {"OAuth2Server": charter.auth.OAuth2Server},
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
