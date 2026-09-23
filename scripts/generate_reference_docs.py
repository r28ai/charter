"""Regenerate the reference section's symbol inventory.

The reference documents the public surface — `charter.__all__` plus
`charter.auth.__all__` — and the two have to stay in step without anyone
remembering to check. So the mapping is derived rather than
written: this script reads the public surface, finds where each name is
documented, and rewrites the inventory block in `docs/reference/overview.mdx`.

A symbol counts as documented when a page under `docs/reference/` carries a
heading that is exactly its name in backticks — `## \x60Tool\x60`. A heading is a
documented position; a mention in prose is not, which is what keeps the check
from passing on an accident.

Run it after touching the public surface::

    uv run python scripts/generate_reference_docs.py

It exits non-zero when a symbol has no page, so it works as a check in CI as
well as a generator. `tests/test_reference_docs.py` asserts the same two
things — full coverage, and a block that matches what this would write.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference"
OVERVIEW = REFERENCE / "overview.mdx"

START = "{/* generated:inventory start */}"
END = "{/* generated:inventory end */}"

# `## \x60name\x60` or `### \x60name\x60`, and nothing else on the line. Dotted
# members (`Tool.ainvoke`) match too and are simply not in __all__.
_HEADING = re.compile(r"^#{2,3}\s+`([A-Za-z_][\w.]*)`\s*$", re.M)

# The order pages are listed in, which is the order the section reads in.
PAGE_ORDER = (
    "overview",
    "tool",
    "factories",
    "markers",
    "semantic-types",
    "protobuf-types",
    "credentials",
    "oauth",
    "envelopes-and-pagination",
    "transforms",
    "response-handling",
    "observability",
    "errors",
    "configuration",
    "cli",
)


def pages() -> List[Path]:
    """Every reference page, in reading order, unknown files last."""

    def key(path: Path) -> Tuple[int, str]:
        stem = path.stem
        return (PAGE_ORDER.index(stem) if stem in PAGE_ORDER else len(PAGE_ORDER), stem)

    return sorted(REFERENCE.glob("*.mdx"), key=key)


def headings() -> Dict[str, str]:
    """Every documented symbol, mapped to the page slug documenting it.

    First page wins, in reading order, so a symbol mentioned as a heading twice
    is indexed where it is defined rather than where it is cross-referenced.
    """
    found: Dict[str, str] = {}
    for page in pages():
        for name in _HEADING.findall(page.read_text()):
            found.setdefault(name, page.stem)
    return found


def public_namespaces() -> Dict[str, str]:
    """Every public name, mapped to the namespace it is imported from.

    Two namespaces, no overlap: `charter` is the tool surface, `charter.auth` is
    the whole of authentication. A name appearing in both would be an alias, which
    is exactly what the split refused, so a collision is an error rather than a
    tie to break.
    """
    import charter
    import charter.auth

    names: Dict[str, str] = {name: "charter" for name in charter.__all__}
    for name in charter.auth.__all__:
        if name in names:
            raise KeyError(
                f"{name} is exported from both charter and charter.auth; the "
                "public surface has one import path per name"
            )
        names[name] = "charter.auth"
    return names


def public_symbols() -> List[str]:
    """Every name on the public surface, both namespaces."""
    return list(public_namespaces())


def render_inventory(documented: Dict[str, str]) -> str:
    """The inventory table, as it belongs between the markers."""
    namespaces = public_namespaces()
    lines = [
        START,
        "",
        "| Symbol | Import from | Page |",
        "|---|---|---|",
    ]
    for name in sorted(namespaces, key=str.lower):
        page = documented.get(name)
        if page is None:
            raise KeyError(
                f"{name} is on the public surface with no reference page; give it "
                "a `## `name`` heading under docs/reference/"
            )
        anchor = name.lower()
        lines.append(f"| `{name}` | `{namespaces[name]}` | [{page}](/reference/{page}#{anchor}) |")
    lines.extend(["", END])
    return "\n".join(lines)


def undocumented(documented: Dict[str, str]) -> List[str]:
    return [name for name in public_symbols() if name not in documented]


def current_block() -> str:
    """What overview.mdx holds between the markers today, markers included."""
    text = OVERVIEW.read_text()
    start = text.index(START)
    end = text.index(END) + len(END)
    return text[start:end]


def write_inventory(block: str) -> bool:
    """Replace the block. Returns whether the file changed."""
    text = OVERVIEW.read_text()
    updated = text.replace(current_block(), block)
    if updated == text:
        return False
    OVERVIEW.write_text(updated)
    return True


def main() -> int:
    documented = headings()
    missing = undocumented(documented)
    if missing:
        print(
            "Undocumented public symbols — every name in charter.__all__ and "
            "charter.auth.__all__ needs a `## `name`` heading on a page under "
            "docs/reference/:",
            file=sys.stderr,
        )
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        return 1

    changed = write_inventory(render_inventory(documented))
    total = len(public_symbols())
    where = OVERVIEW.relative_to(ROOT)
    print(f"{total} symbols documented across {len(pages())} pages")
    print(f"{'rewrote' if changed else 'unchanged'}: {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
