"""What the docs site tells a coding agent Charter is.

An agent pointed at docs.r28.ai reads ``llms.txt``, may install ``skill.md``, and
gets the ``markdown.instructions`` from ``docs.json`` on every page it fetches.
Mintlify generates the first two when the docs leave them out, and what it
generated told agents Charter was a catalogue: 736 of the 788 lines of its
``llms.txt`` were pack pages. A real user's agent drew the same conclusion from
the repo and ignored the two APIs he wanted tools for, because neither had a pack.

So both files are ours, written by ``scripts/generate_agent_docs.py``, and this
suite pins three things: they match what the script would write, the catalogue
does not creep back into ``llms.txt``, and the definition an agent reads there is
the one the README and the docs overview give a person.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def _load_generator():
    path = ROOT / "scripts" / "generate_agent_docs.py"
    spec = importlib.util.spec_from_file_location("generate_agent_docs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()

_SITE_URL = re.compile(r"https://docs\.r28\.ai/charter/([\w./-]+)")


def _served(slug: str) -> bool:
    """A docs URL resolves to a file served as is, or to a page fetched as markdown."""
    if (DOCS / slug).exists():
        return True
    page = slug[: -len(".md")] if slug.endswith(".md") else slug
    return any((DOCS / f"{page}{suffix}").exists() for suffix in (".mdx", ".md"))


def test_the_llms_txt_page_list_is_current():
    current = GEN.LLMS_TXT.read_text()
    assert GEN.render_llms_txt(current) == current, (
        f"docs/llms.txt is stale — run `uv run python {GEN._SCRIPT}`"
    )


def test_the_served_skill_is_the_repo_skill():
    assert GEN.SKILL_MD.read_text() == GEN.render_skill_md(), (
        f"docs/skill.md is stale — run `uv run python {GEN._SCRIPT}`"
    )


def test_the_served_skill_has_no_relative_links():
    """It is served alone, so a relative link lands on a page that is not there."""
    relative = [
        target
        for target in GEN._LINK.findall(GEN.SKILL_MD.read_text())
        if not target.startswith(("http://", "https://", "#", "mailto:"))
    ]
    assert not relative, f"docs/skill.md links relatively: {relative}"


def test_llms_txt_lists_no_pack_tool_pages():
    """One line per pack tool is what made the generated file read as a catalogue."""
    listed = _SITE_URL.findall(GEN.LLMS_TXT.read_text())
    tool_pages = [
        slug for slug in listed if slug.startswith("packs/") and slug != "packs/overview.md"
    ]
    assert not tool_pages, f"llms.txt lists pack pages again: {tool_pages}"


def test_every_docs_url_handed_to_agents_resolves():
    instructions = json.loads((DOCS / "docs.json").read_text())["markdown"]["instructions"]
    sources = {
        "docs/llms.txt": GEN.LLMS_TXT.read_text(),
        "docs.json markdown.instructions": "\n".join(instructions),
    }
    missing = [
        f"{name} -> {slug}"
        for name, text in sources.items()
        for slug in _SITE_URL.findall(text)
        if not _served(slug.rstrip("."))
    ]
    assert not missing, f"agents are sent to pages that do not exist: {missing}"


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_agents_and_people_read_the_same_definition():
    """The README, the docs overview and llms.txt open with one paragraph.

    A change to it is a decision about what Charter is, so it is made in all
    three places or the test says which one was missed.
    """
    readme = (ROOT / "README.md").read_text()
    readme_definition = readme.split("# Charter\n\n", 1)[1].split(
        "\n\nA library, not a service.", 1
    )[0]

    overview = (DOCS / "index.mdx").read_text()
    overview_definition = overview.split("<AgentButton />\n\n", 1)[1].split(
        "\n\n**Charter is a library", 1
    )[0]

    llms = GEN.LLMS_TXT.read_text()
    llms_definition = re.search(r"^> (.+)$", llms, re.M)
    assert llms_definition

    expected = _flat(readme_definition)
    assert _flat(overview_definition) == expected, (
        "docs/index.mdx opens with a different definition"
    )
    assert _flat(llms_definition.group(1)) == expected, (
        "docs/llms.txt opens with a different definition"
    )
