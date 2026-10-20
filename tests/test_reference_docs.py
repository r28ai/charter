"""The reference documents the whole public surface, and its examples run.

Two failure modes this suite exists to catch. A symbol added to
``charter.__all__`` with no reference page — the surface grows, the docs do not,
and nobody notices until a reader searches for a name that is not there. And a
snippet that only looks right, which costs the reader trust the first time they
paste one.

Coverage is checked against the same scan ``scripts/generate_reference_docs.py``
performs: a symbol is documented when a page under ``docs/reference/`` carries a
heading that is exactly its name in backticks. A mention in prose does not
count.

Execution follows the rule the reference is written to: a ``python`` block that
imports something is a worked example and is executed here, offline, against a
catch-all respx mock; a block that imports nothing is a signature listing and is
only parsed.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import logging
import re
from fnmatch import fnmatch
from pathlib import Path as FsPath
from typing import List

import httpx
import pytest
import respx
from tests._doc_blocks import run_doc_block

import charter

ROOT = FsPath(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference"


def _load_generator():
    path = ROOT / "scripts" / "generate_reference_docs.py"
    spec = importlib.util.spec_from_file_location("generate_reference_docs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


GENERATOR = _load_generator()

_BLOCK = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)

PAGES = sorted(REFERENCE.glob("*.mdx"))


# -----------------------------------------------------
# The public surface is covered
# -----------------------------------------------------


def test_there_are_reference_pages_at_all():
    """Guard against every scan below matching an empty directory."""
    assert len(PAGES) >= 10


def test_every_public_symbol_is_documented():
    missing = GENERATOR.undocumented(GENERATOR.headings())
    assert not missing, (
        "these names are in charter.__all__ with no `## `name`` heading under "
        f"docs/reference/: {missing}"
    )


def test_the_inventory_block_is_current():
    """Regenerate in memory; the committed block must match."""
    expected = GENERATOR.render_inventory(GENERATOR.headings())
    assert GENERATOR.current_block() == expected, (
        "docs/reference/overview.mdx is stale — run "
        "`uv run python scripts/generate_reference_docs.py`"
    )


def test_the_inventory_lists_the_whole_surface():
    """The generated table is read directly, not just compared against itself."""
    block = GENERATOR.current_block()
    for name in charter.__all__:
        assert f"| `{name}` |" in block, f"{name} is missing from the inventory"


def test_a_heading_is_the_only_documented_position():
    """A name in prose, in a code block, or in a link must not count as coverage."""
    heading = GENERATOR._HEADING
    assert heading.findall("## `Tool`\n") == ["Tool"]
    assert heading.findall("### `Tool.ainvoke`\n") == ["Tool.ainvoke"]
    assert heading.findall("Pass a `Tool` to the adapter.\n") == []
    assert heading.findall("- [`Tool`](/reference/tool)\n") == []
    assert heading.findall("```python\n# `Tool`\n```\n") == []
    assert heading.findall("## `Tool` and its methods\n") == []


def test_nothing_private_is_presented_as_public():
    """`charter.execution` is the runtime, not an API — no page may import it."""
    offenders = [
        page.name
        for page in PAGES
        if "from charter.execution" in page.read_text()
        or "import charter.execution" in page.read_text()
    ]
    assert not offenders, f"reference pages importing the runtime: {offenders}"


@pytest.mark.parametrize(
    "name",
    [
        "PermissionManager",
        "GoogleCredentialProvider",
        "GoogleScopes",
        "create_chat_client",
        "set_current_r28_user",
        "api_tool_factory",
        "r28sdk",
    ],
)
def test_no_page_invents_api(name):
    offenders = [page.name for page in PAGES if name in page.read_text()]
    assert not offenders, f"{name} does not exist but appears in: {offenders}"


def test_create_agent_is_only_ever_langchains():
    """`create_agent` is on neither surface and both.

    The closed-source runtime Charter replaced had one, and a page describing it
    as Charter's would be inventing API — which is what the list above guards.
    LangChain 1.x also has one, and it is the function you pass
    `CharterMiddleware` to, so the name cannot simply be banned. A page may use
    it only where it is imported from langchain.
    """
    offenders = [
        page.name
        for page in PAGES
        if "create_agent" in (text := page.read_text())
        and "from langchain.agents import create_agent" not in text
    ]
    assert not offenders, f"create_agent used as if it were Charter's in: {offenders}"


# -----------------------------------------------------
# House style
# -----------------------------------------------------


def test_every_code_block_has_a_language_tag():
    untagged = []
    for page in PAGES:
        for tag, _ in _BLOCK.findall(page.read_text()):
            if not tag:
                untagged.append(page.name)
    assert not untagged, f"untagged code fences in: {sorted(set(untagged))}"


def test_no_page_frames_charter_as_fixing_pydantic():
    forbidden = re.compile(r"(fix|patch|work around|works around)\w*\s+pydantic", re.I)
    offenders = [page.name for page in PAGES if forbidden.search(page.read_text())]
    assert not offenders, f"pages framing Charter as papering over Pydantic: {offenders}"


# -----------------------------------------------------
# The examples run
# -----------------------------------------------------


def _python_blocks(page: FsPath) -> list[str]:
    return [body for tag, body in _BLOCK.findall(page.read_text()) if tag == "python"]


def _is_worked_example(source: str) -> bool:
    """A block that imports something is meant to run; a signature listing is not."""
    tree = ast.parse(source)
    return any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree))


ALL_BLOCKS = [(page.name, body) for page in PAGES for body in _python_blocks(page)]
EXAMPLES = [(name, body) for name, body in ALL_BLOCKS if _is_worked_example(body)]


def test_the_extraction_matches_something():
    assert len(ALL_BLOCKS) >= 30
    assert len(EXAMPLES) >= 15


@pytest.mark.parametrize(
    "source", [body for _, body in ALL_BLOCKS], ids=[name for name, _ in ALL_BLOCKS]
)
def test_every_python_block_parses(source):
    ast.parse(source)


def _listed_parameters(text: str, name: str) -> List[str]:
    """The parameters a written-out signature of ``name`` declares, parsed rather than grepped."""
    for body in re.findall(r"^```python[^\n]*\n(.*?)^```", text, re.M | re.S):
        source = body.strip()
        if not re.match(rf"(def )?{name}\(", source):
            continue
        if not source.startswith("def "):
            source = f"def {source}"
        if not source.endswith(": ..."):
            source += ": ..."
        function = ast.parse(source).body[0]
        assert isinstance(function, ast.FunctionDef)
        arguments = function.args
        return [a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)]
    raise AssertionError(f"no written-out signature of {name}")


def _builder_parameters():
    """What the API-key builder and the OAuth builder each take."""
    from charter.auth import StaticTokenProvider

    api_key = charter.api_key_tool_factory(
        "https://api.example.com/", {"x-api-key": "k"}, pack="acme"
    )
    oauth = charter.oauth_tool_factory(
        "https://api.example.com/", "acme", StaticTokenProvider("t"), pack="acme"
    )
    return list(inspect.signature(api_key).parameters), list(inspect.signature(oauth).parameters)


@pytest.mark.parametrize(
    "page, name",
    [
        ("reference/factories.mdx", "api_key_tool_factory"),
        ("reference/factories.mdx", "oauth_tool_factory"),
        ("auth/api-key-tool-factory.md", "api_key_tool_factory"),
    ],
)
def test_a_written_out_factory_signature_is_the_factory_s_own(page, name):
    """Parsing a listing proves it is Python, not that it is this function.

    The API-key factory's own page listed 7 of its 17 parameters, and the five
    it left out first included ``body_format``, ``static_query`` and
    ``envelope`` — the three AGENTS.md sends a pack author to.
    """
    listed = _listed_parameters((ROOT / "docs" / page).read_text(), name)
    assert listed == list(inspect.signature(getattr(charter, name)).parameters)


def test_the_builder_listing_is_what_both_builders_take():
    api_key, oauth = _builder_parameters()
    section = (REFERENCE / "factories.mdx").read_text().split("## The builder", 1)[1]
    section = section.split("\n## ", 1)[0]
    assert _listed_parameters(section, "create_tool") == [p for p in api_key if p in oauth]
    # The listing leaves out exactly the two its prose says belong to one builder.
    differ = set(api_key) ^ set(oauth)
    assert differ == {"api_key_headers_override", "scopes_override"}
    assert all(f"`{name}`" in section for name in differ)


def test_the_api_key_page_tables_every_builder_parameter():
    api_key, _ = _builder_parameters()
    page = (ROOT / "docs" / "auth" / "api-key-tool-factory.md").read_text()
    table = page.split("The returned builder takes:", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `([\w*]+)`", table, re.M)
    assert not [row for row in rows if not any(fnmatch(p, row) for p in api_key)], rows
    assert [p for p in api_key if not any(fnmatch(p, row) for row in rows)] == []


def test_the_signature_check_catches_an_abridged_listing():
    """The listing the API-key page carried, so the check cannot pass on one again."""
    abridged = (
        "```python\napi_key_tool_factory(\n    base_url: str,\n"
        "    api_key_headers: dict[str, str] | None = None,\n    *,\n    pack: str,\n"
        '    body_case: KeyCase = "camel",\n    query_case: KeyCase = "snake",\n'
        '    path_case: KeyCase = "snake",\n    timeout: int = 20,\n) -> ToolBuilder\n```\n'
    )
    listed = _listed_parameters(abridged, "api_key_tool_factory")
    assert listed != list(inspect.signature(charter.api_key_tool_factory).parameters)


@pytest.fixture
def pack_state_restored():
    """Doc examples call `configure()`; hand the packs back as they were found."""
    import importlib

    from charter.mcp import PACKS

    saved = []
    for name in PACKS:
        module = importlib.import_module(f"charter.packs.{name}")
        for attr in ("_credentials", "_headers"):
            holder = getattr(module, attr, None)
            if holder is None:
                continue
            for field in ("_provider", "_api_key", "_shop"):
                if hasattr(holder, field):
                    saved.append((holder, field, getattr(holder, field)))

    logger = logging.getLogger("charter")
    level = logger.level
    try:
        yield
    finally:
        for holder, field, value in saved:
            setattr(holder, field, value)
        logger.setLevel(level)


@pytest.mark.parametrize(
    "source", [body for _, body in EXAMPLES], ids=[name for name, _ in EXAMPLES]
)
async def test_every_worked_example_runs(source, pack_state_restored):
    namespace: dict = {"__name__": "__charter_reference__"}
    with respx.mock:
        respx.route().mock(return_value=httpx.Response(200, json={"ok": True}))
        # dont_inherit, or this module's `from __future__ import annotations`
        # would follow the snippet in and turn every annotation into a string —
        # which a reader pasting the block into their own file would not get.
        await run_doc_block(source, namespace, "<reference>")


def test_the_cli_page_shows_the_usage_the_parser_prints(capsys):
    from charter.mcp import main

    with pytest.raises(SystemExit):
        main(["--help"])
    usage = capsys.readouterr().out.splitlines()[0]
    assert usage.startswith("usage: charter-mcp ")
    assert usage in (REFERENCE / "cli.mdx").read_text().splitlines()
