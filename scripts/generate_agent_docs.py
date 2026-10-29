"""Regenerate the two files the docs site hands to coding agents.

Mintlify writes `llms.txt` and `skill.md` itself when the docs leave them out,
and what it wrote told agents the wrong thing about Charter. Its `llms.txt`
listed one entry per pack tool, 736 of its 788 lines, so an agent skimming it saw
a catalogue of sixteen APIs. Its `skill.md` was its own model's summary: packs
first, any other API as an afterthought, and an example passing a `query_case`
value that does not exist. A file of the same name at the docs root replaces
each one.

- `docs/llms.txt`: the introduction above the markers is written by hand. The
  page list between them is generated from `docs.json` and each page's
  frontmatter, so a new page shows up and a changed description follows. Pack
  tool pages and the per-vendor auth pages are left out; their hubs are listed
  and link onward.
- `docs/.mintlify/skills/declaring-charter-tools/SKILL.md`: the repo skill with
  its relative links made absolute, because Mintlify serves the copy alone (at
  docs.r28.ai/charter/skill.md and under /.well-known/agent-skills/) and its
  neighbours are not served beside it. It lives in `.mintlify/skills/`, Mintlify's
  skills directory, rather than as a root `skill.md`: the root file stopped
  refreshing on deploy after 2026-10-20 and served that day's copy for weeks.

Run it after adding a page, changing a page's title or description, or editing
the skill::

    uv run python scripts/generate_agent_docs.py
    uv run python scripts/generate_agent_docs.py --check     # exit 1 if stale

`tests/test_agent_docs.py` asserts both files match what this would write.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
LLMS_TXT = DOCS / "llms.txt"
SKILL_MD = DOCS / ".mintlify" / "skills" / "declaring-charter-tools" / "SKILL.md"
SKILL_SOURCE = ROOT / "skills" / "declaring-charter-tools" / "SKILL.md"

SITE = "https://docs.r28.ai/charter"
REPO = "https://github.com/r28ai/charter/blob/main"

START = "<!-- generated: pages start -->"
END = "<!-- generated: pages end -->"

_SCRIPT = "scripts/generate_agent_docs.py"

# One page per pack tool and one per vendor's auth setup. Each sits under a hub
# that is listed (packs/overview, auth/your-own-account, auth/your-users), and
# listing every one of them is what made the generated file read as a catalogue.
_LEFT_OUT = re.compile(r"^(packs/(?!overview$)|auth/(setup|apps|providers)/)")

_FIELD = re.compile(r"^(title|description):\s*(.*)$", re.M)
_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _pages(node: object) -> Iterator[str]:
    """Every page slug under a navigation node, in the order the sidebar shows them."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for child in node.get("pages", []):
            yield from _pages(child)
    elif isinstance(node, list):
        for child in node:
            yield from _pages(child)


def sections() -> List[Tuple[str, List[str]]]:
    """The sidebar as headed lists of pages.

    A tab built from groups (Documentation) is one section per group, because
    there the groups are the topics. A tab built from pages (Packs, Reference)
    is one section named after the tab.
    """
    navigation = json.loads((DOCS / "docs.json").read_text())["navigation"]
    out: List[Tuple[str, List[str]]] = []
    for tab in navigation["tabs"]:
        if "groups" in tab:
            for group in tab["groups"]:
                out.append((group["group"], list(_pages(group))))
        else:
            out.append((tab["tab"], list(_pages(tab))))
    return [
        (heading, [page for page in pages if not _LEFT_OUT.match(page)]) for heading, pages in out
    ]


def frontmatter(page: str) -> Dict[str, str]:
    path = DOCS / f"{page}.mdx"
    if not path.exists():
        path = DOCS / f"{page}.md"
    text = path.read_text()
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    fields = {}
    for key, value in _FIELD.findall(head):
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].replace('\\"', '"')
        fields[key] = value
    return fields


def render_pages() -> str:
    lines: List[str] = []
    for heading, pages in sections():
        if not pages:
            continue
        lines += ["", f"## {heading}", ""]
        for page in pages:
            fields = frontmatter(page)
            entry = f"- [{fields.get('title', page)}]({SITE}/{page}.md)"
            if fields.get("description"):
                entry += f": {fields['description']}"
            lines.append(entry)
    return "\n".join(lines[1:])


def render_llms_txt(current: str) -> str:
    """The hand-written introduction, kept, over a regenerated page list."""
    head, rest = current.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{render_pages()}\n{END}{tail}"


def _absolute(target: str) -> str:
    if target.startswith(("http://", "https://", "#", "mailto:")):
        return target
    path, _, anchor = target.partition("#")
    relative = (SKILL_SOURCE.parent / path).resolve().relative_to(ROOT)
    if relative.parts[0] == "docs":
        slug = relative.relative_to("docs").with_suffix("").as_posix()
        url = f"{SITE}/{slug}.md"
    else:
        url = f"{REPO}/{relative.as_posix()}"
    return f"{url}#{anchor}" if anchor else url


def render_skill_md() -> str:
    return _LINK.sub(lambda m: f"]({_absolute(m.group(1))})", SKILL_SOURCE.read_text())


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    stale: List[str] = []
    for path, render in (
        (LLMS_TXT, lambda: render_llms_txt(LLMS_TXT.read_text())),
        (SKILL_MD, render_skill_md),
    ):
        current = path.read_text() if path.exists() else ""
        updated = render()
        if updated == current:
            continue
        stale.append(path.relative_to(ROOT).as_posix())
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(updated)

    if check and stale:
        print(f"stale: {', '.join(stale)}", file=sys.stderr)
        print(f"run: uv run python {_SCRIPT}", file=sys.stderr)
        return 1

    verb = "stale" if check else "rewrote"
    print(f"2 files checked, {len(stale)} {verb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
