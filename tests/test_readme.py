"""R8 — the README's code blocks actually run.

A README whose examples do not execute is worse than no README: it costs the
reader trust the first time they paste one. Every ```python block is extracted
and executed here, offline, against a catch-all respx mock.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path as FsPath

import httpx
import pytest
import respx

ROOT = FsPath(__file__).resolve().parent.parent
README = ROOT / "README.md"

_BLOCK = re.compile(r"^```(\w+)\n(.*?)^```", re.M | re.S)


def _blocks(lang: str) -> list[str]:
    return [body for tag, body in _BLOCK.findall(README.read_text()) if tag == lang]


PYTHON_BLOCKS = _blocks("python")


def test_readme_has_python_blocks():
    """Guard against the extraction silently matching nothing."""
    assert len(PYTHON_BLOCKS) >= 5


@pytest.mark.parametrize(
    "source", PYTHON_BLOCKS, ids=[f"block{i}" for i in range(len(PYTHON_BLOCKS))]
)
def test_readme_python_block_parses(source):
    ast.parse(source)


@pytest.mark.parametrize(
    "source", PYTHON_BLOCKS, ids=[f"block{i}" for i in range(len(PYTHON_BLOCKS))]
)
async def test_readme_python_block_runs(source, monkeypatch):
    """Execute the block for real, with the network mocked out."""
    # Blocks demonstrating an optional adapter need that extra installed.
    for module, extra in (
        ("charter.adapters.langchain", "langchain_core"),
        ("charter.adapters.mcp", "mcp"),
    ):
        if module in source:
            pytest.importorskip(extra, reason=f"README block needs {extra}")

    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_readme")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "readme-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "readme-client-secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "readme-refresh-token")

    namespace: dict = {
        "__name__": "__readme__",
        # The README elides where the token comes from; supply one.
        "access_token": "test-token",
    }

    with respx.mock:
        respx.route().mock(return_value=httpx.Response(200, json={"ok": True}))

        # dont_inherit: compile() otherwise inherits this module's
        # `from __future__ import annotations`, so every snippet is compiled
        # under PEP 563 and a schema written the way the docs teach —
        # `city: Annotated[str, Path()]` — fails when pydantic rebuilds the
        # generated LLM model and cannot resolve the stringified marker. The
        # reader pasting the block into a real module never hits that; only the
        # harness invents it. Today the wrapper below happens to hide it, by
        # giving pydantic a parent namespace to resolve from. That is luck, not
        # design, and it runs out the day a marker-carrying schema lands on the
        # non-wrapped path.
        if re.search(r"^\s*await ", source, re.M):
            # Top-level await: wrap the block in a coroutine and run it.
            indented = "\n".join("    " + line for line in source.splitlines())
            wrapper = f"async def __readme_main__():\n{indented}\n"
            exec(compile(wrapper, "<readme>", "exec", dont_inherit=True), namespace)
            await namespace["__readme_main__"]()
        else:
            exec(compile(source, "<readme>", "exec", dont_inherit=True), namespace)


# -----------------------------------------------------
# Links and hygiene
# -----------------------------------------------------

_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_HREF = re.compile(r'href="([^"]+)"')


def _links(text: str) -> list:
    """Both ways a docs page points somewhere: markdown, and a JSX `href`.

    The pack pages' tool lists are generated JSX — the whole row is the anchor —
    so a markdown-only sweep would call ninety live links orphaned.
    """
    return _LINK.findall(text) + _HREF.findall(text)


def test_every_relative_link_resolves():
    missing = []
    for target in _LINK.findall(README.read_text()):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (ROOT / target.split("#")[0]).resolve()
        if not path.exists():
            missing.append(target)
    assert not missing, f"README links to missing files: {missing}"


def _spec_slugs(docs) -> set:
    """Every page Mintlify mints from a pack's OpenAPI document.

    These pages have no file: ``docs.json`` points a navigation group at
    ``packs/<pack>.openapi.json`` and the pages are generated at build time, one
    per operation, under the group's directory and the operation's tag. A link to
    one resolves against the spec, which is where the operation is declared.
    """
    slugs = set()
    for spec_file in docs.glob("packs/*.openapi.json"):
        spec = json.loads(spec_file.read_text())
        pack = spec_file.name.split(".")[0]
        for methods in spec["paths"].values():
            for operation in methods.values():
                for tag in operation.get("tags", ["api-reference"]):
                    slugs.add(f"packs/{pack}/{tag.lower()}/{operation['operationId']}")
    return slugs


def test_docs_links_resolve_too():
    """The docs directory is also the Mintlify site, which addresses a page by a
    root-relative slug (`/oauth-flow`) rather than by filename. So a link
    resolves against docs/ with whichever extension that page uses — and an
    asset path still resolves the ordinary way, relative to the page.
    """
    docs = ROOT / "docs"
    generated = _spec_slugs(docs)
    missing = []
    for doc in sorted([*docs.rglob("*.md"), *docs.rglob("*.mdx")]):
        for target in _links(doc.read_text()):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            slug = target.split("#")[0].lstrip("/")
            if not slug:
                continue
            if slug in generated:
                continue
            candidates = [
                docs / f"{slug}.md",
                docs / f"{slug}.mdx",
                doc.parent / slug,
                # Last, for a root-relative link to something served as a file
                # rather than rendered as a page.
                docs / slug,
            ]
            # A link that ends in `.md` is a page fetched as markdown, which
            # Mintlify serves from the `.mdx` source rather than from a file of
            # that name. The setup prompt is linked that way.
            if slug.endswith(".md"):
                candidates.append(docs / f"{slug[: -len('.md')]}.mdx")
            if not any(candidate.exists() for candidate in candidates):
                missing.append(f"{doc.name} -> {target}")
    assert not missing, f"docs link to missing files: {missing}"


def test_every_tool_page_a_spec_generates_is_linked_to():
    """The inverse: 89 generated pages, and the pack pages reach all of them."""
    docs = ROOT / "docs"
    linked = {
        target.split("#")[0].lstrip("/")
        for doc in docs.glob("packs/*.mdx")
        for target in _links(doc.read_text())
    }
    orphaned = _spec_slugs(docs) - linked
    assert not orphaned, f"generated pages nothing links to: {sorted(orphaned)}"


def test_skill_and_agents_links_resolve():
    missing = []
    for source in (ROOT / "AGENTS.md", ROOT / "skills/writing-charter-packs/SKILL.md"):
        for target in _LINK.findall(source.read_text()):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (source.parent / target.split("#")[0]).resolve()
            if not path.exists():
                missing.append(f"{source.name} -> {target}")
    assert not missing, f"missing link targets: {missing}"


# Every file an agent reads before writing its first pack. The two namespaces
# are the thing most easily got wrong here, and got wrong silently: an agent
# told the surface is `charter.__all__` concludes `EnvTokenProvider` does not
# exist, and writes around it.
_AGENT_FACING = (
    "README.md",
    "AGENTS.md",
    "skills/writing-charter-packs/SKILL.md",
    "docs/agent-setup/prompt.mdx",
    "docs/start/coding-agents.mdx",
)

_IMPORT = re.compile(r"^\s*from (charter[\w.]*) import ([^\n(]+)$", re.M)


@pytest.mark.parametrize("relative", _AGENT_FACING)
def test_every_import_an_agent_is_taught_actually_imports(relative):
    """A name taught from the wrong namespace is an ImportError for the reader."""
    import importlib

    source = ROOT / relative
    problems = []
    for module_name, names in _IMPORT.findall(source.read_text()):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            problems.append(f"no module {module_name}")
            continue
        for name in (n.strip() for n in names.split(",")):
            if name and not hasattr(module, name):
                problems.append(f"{module_name} has no {name!r}")
    assert not problems, f"{relative}: {problems}"


@pytest.mark.parametrize("relative", _AGENT_FACING)
def test_no_agent_facing_file_calls_charter_the_whole_surface(relative):
    """`charter.__all__` alone stopped being the public surface.

    Anything that points a reader at it has to point at `charter.auth.__all__`
    in the same breath, or it is telling them half the library is missing.
    """
    text = (ROOT / relative).read_text()
    if "charter.__all__" not in text:
        return
    assert "charter.auth.__all__" in text, (
        f"{relative} names charter.__all__ as the surface without charter.auth.__all__"
    )


def test_the_covenant_is_present_verbatim():
    """A locked line. If it drifts, that is a decision, not a typo."""
    covenant = (
        "A library, not a service.\n"
        "Runs in your process. No proxy, no per-call pricing, no telemetry."
    )
    assert covenant in README.read_text()


def test_readme_documents_every_shipped_pack():
    from charter.mcp import PACKS

    text = README.read_text()
    for pack in PACKS:
        assert f"charter.packs.{pack}" in text, f"{pack} is missing from the coverage table"


def test_coverage_table_tool_counts_are_accurate():
    """The table claims a tool count per pack; check it against reality.

    Every pack, not a sample. Four of the fourteen were named here, so GitHub
    could reach 139 tools while the table said 29 and nothing went red.
    """
    import importlib

    from charter.mcp import PACKS

    text = README.read_text()
    for pack in PACKS:
        module = importlib.import_module(f"charter.packs.{pack}")
        row = next(ln for ln in text.splitlines() if f"`charter.packs.{pack}`" in ln)
        cells = [c.strip() for c in row.split("|")]
        assert str(len(module.TOOLS)) in cells, (
            f"{pack}: table says {cells}, actual tool count is {len(module.TOOLS)}"
        )


def test_the_conformance_counts_are_accurate():
    """Three pages quote how many properties the suite checks. Derive them.

    The README said fifteen, the conformance page's own description said
    thirteen, and the real number was sixteen: three claims, no two agreeing,
    because a count written in prose has nothing holding it to the code.

    Every number word in front of "properties", "in all" or "mutations" is
    checked, not just the presence of the right one somewhere on the page. The
    first version of this check asked whether the correct word appeared at all,
    which the frontmatter satisfied while the body said nineteen.
    """
    import ast

    from tests.test_landing_docs import _word

    conformance = ROOT / "tests" / "test_conformance.py"
    vacuous = ROOT / "tests" / "test_conformance_is_not_vacuous.py"

    properties = len(
        [
            node
            for node in ast.parse(conformance.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]
    )
    mutations = vacuous.read_text().count("_must_fail(")
    spellings = {_word(n) for n in range(100)}

    pages = {
        "README.md": README,
        "docs/guarantees/conformance.mdx": ROOT / "docs" / "guarantees" / "conformance.mdx",
        "docs/start/coding-agents.mdx": ROOT / "docs" / "start" / "coding-agents.mdx",
    }
    for name, path in pages.items():
        text = path.read_text().lower()
        for word, noun in re.findall(r"\b([a-z-]+) (properties|in all|mutations)\b", text):
            if word not in spellings:
                continue
            expected = _word(mutations if noun == "mutations" else properties)
            assert word == expected, (
                f"{name} says {word!r} {noun}; it is {expected!r} ({properties} "
                f"properties, {mutations} mutations)"
            )


def test_readme_does_not_claim_unmeasured_numbers():
    """No benchmark exists yet. Until the harness ships, the README must not
    quote token counts, percentages, or speedups."""
    import re

    text = README.read_text()
    # Strip code blocks and tables — quota units and schema values live there.
    prose = re.sub(r"^```.*?^```", "", text, flags=re.M | re.S)
    prose = "\n".join(ln for ln in prose.splitlines() if not ln.strip().startswith("|"))

    forbidden = re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|x faster|x cheaper|× faster)", prose)
    assert not forbidden, f"unmeasured performance claim in README: {forbidden}"


def test_egress_doc_example_matches_reality():
    """The doc shows a rendered map; it must still be what the code produces."""
    from charter.egress import egress_map
    from charter.packs import gmail

    doc = (ROOT / "docs" / "boundary" / "egress-control.md").read_text()
    entry = egress_map(gmail.TOOLS)["gmail__messages_send"]
    withheld = {w["field"] for w in entry["withheld"]}

    for field in ("body.payload", "body.id", "body.snippet"):
        assert field in withheld
        assert field in doc, f"{field} shown in docs but no longer withheld"
    assert "body.raw" in entry["visible"]
