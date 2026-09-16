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
from pathlib import Path as FsPath

import httpx
import pytest
import respx

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
        code = compile(
            source,
            "<reference>",
            "exec",
            flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
            dont_inherit=True,
        )
        result = eval(code, namespace)  # noqa: S307 — the input is this repo's own docs
        if inspect.iscoroutine(result):
            await result
