"""R10.6 — every tool's arguments are documented, and documented from the code.

``test_pack_docs.py`` guards the pack *page*: the tool list, the wire table, the
prose around them. This guards the layer under it — the reference under
``docs/packs/<pack>/``, one page per tool and one per category of objects, every
argument with the provider's own description and the markers that decide where
it goes.

The claim these pages make is that a pack keeps the provider's schema at the
provider's own resolution. A hand-maintained copy of 90 tools' arguments would
falsify that claim within a release, so ``scripts/generate_pack_specs.py``
renders them from the live package and this file asserts that what is on disk is
what the generator would produce right now.

The pages were OpenAPI documents until the reference moved to MDX tables, and
the assertions that mattered came across unchanged: an argument that never
reaches the page, a type link that lands on no heading, and a page the
navigation does not list are all still the failures worth catching. What went
with the renderer is what only it could get wrong.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path as FsPath

import pytest

from charter.mcp import PACKS

ROOT = FsPath(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PACK_DOCS = DOCS / "packs"
DOCS_JSON = DOCS / "docs.json"


def _load_generator():
    """Import the script by path; ``scripts/`` is not a package."""
    path = ROOT / "scripts" / "generate_pack_specs.py"
    spec = importlib.util.spec_from_file_location("generate_pack_specs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()

PAGES = {path: body for path, body in GEN.all_pages().items()}
CONFIG = json.loads(DOCS_JSON.read_text())


def _page(pack, tool):
    """One tool's rendered page, found the way the navigation finds it."""
    return PAGES[GEN.tool_page_path(pack, tool).lstrip("/") + ".mdx"]


def _rows(text: str):
    """Every body row of every markdown table on a page, as cell lists.

    Cells are split on unescaped pipes, which is the same rule the renderer
    uses: a ``|`` inside a code span still ends a cell unless it is escaped.
    """
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("| -"):
            continue
        cells = re.split(r"(?<!\\)\|", line)[1:-1]
        if [c.strip() for c in cells] == ["Field", "Type", "Description"]:
            continue
        yield [cell.strip() for cell in cells]


def _field_names(text: str):
    return {row[0].split("`")[1] for row in _rows(text) if row[0].startswith("`")}


def _headings(text: str):
    return {line[3:].strip() for line in text.splitlines() if line.startswith("## ")}


def _hand_written_headings(slug: str):
    """Every heading a hand-written docs page offers, or ``None`` if there is no
    such page.

    ``PAGES`` holds the generated tree only, and the pages linked out to are
    written by hand and nest deeper: ``Tool.derived`` is an ``h3`` under
    ``Methods``, so the ``h2``-only sweep above would miss it and report a live
    anchor as dead.
    """
    for candidate in (DOCS / f"{slug}.mdx", DOCS / f"{slug}.md"):
        if candidate.exists():
            lines = candidate.read_text().splitlines()
            return {line.lstrip("#").strip() for line in lines if re.match(r"#{2,4} ", line)}
    return None


def _links(text: str):
    """Every internal target the page points at, from markdown links and anchors."""
    yield from re.findall(r"\]\((/[^)\s]*|#[^)\s]*)\)", text)
    yield from re.findall(r'href="(/[^"\s]*|#[^"\s]*)"', text)


def _walk(node):
    """Every mapping in a document, the document itself included."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def re_findall_braces(template: str):
    return re.findall(r"\{(\w+)\}", template)


# -----------------------------------------------------
# Every pack has a reference, and it is current
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_shipped_pack_has_a_reference(pack):
    written = [path for path in PAGES if path.startswith(f"packs/{pack}/")]
    assert written, (
        f"no pages under docs/packs/{pack}/. "
        "Run: uv run python scripts/generate_pack_specs.py"
    )


def test_no_page_documents_a_pack_that_no_longer_exists():
    packs = {path.split("/")[1] for path in PAGES}
    assert packs == set(PACKS), f"pages for {sorted(packs)} against packs {sorted(PACKS)}"


def test_the_reference_on_disk_is_what_the_code_says():
    """The point of the whole exercise."""
    stale = [
        path
        for path, body in PAGES.items()
        if not (DOCS / path).exists() or (DOCS / path).read_text() != body
    ]
    assert not stale, (
        f"stale pages: {stale[:5]}\nRun: uv run python scripts/generate_pack_specs.py"
    )


def test_no_page_on_disk_is_left_over_from_a_tool_that_went_away():
    orphans = [
        str(path.relative_to(DOCS))
        for path in GEN._generated_paths()
        if str(path.relative_to(DOCS)) not in PAGES
    ]
    assert not orphans, f"pages nothing generates any more: {orphans}"


def test_the_generator_reports_a_clean_tree():
    """``--check`` is what CI would run; it must agree with the assertions above."""
    assert GEN.main(["--check"]) == 0


def test_rendering_is_idempotent():
    assert GEN.all_pages() == PAGES


# -----------------------------------------------------
# Every tool is in it, exactly once
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_tool_has_a_page(pack):
    module = GEN.pack_module(pack)
    expected = {GEN.tool_page_path(pack, tool).lstrip("/") + ".mdx" for tool in module.TOOLS}
    assert expected <= set(PAGES)
    assert len(expected) == len(module.TOOLS), f"{pack}: two tools share a page"


@pytest.mark.parametrize("pack", PACKS)
def test_every_tool_lands_in_exactly_one_category(pack):
    """The category is derived from the request model's module, never declared.

    A tool whose request model sits outside the pack's ``types`` package would
    silently join whichever group happened to be first, so it is caught here.
    """
    module = GEN.pack_module(pack)
    grouped = GEN.categorised(pack, list(module.TOOLS))
    placed = [tool for _, tools in grouped for tool in tools]
    # Grouping reorders — GitHub's users tool follows its repos ones — but it
    # may not drop a tool, duplicate one, or invent one.
    assert sorted(t.name for t in placed) == sorted(t.name for t in module.TOOLS)


@pytest.mark.parametrize("pack", PACKS)
def test_a_pack_with_one_category_is_not_given_a_group_of_one(pack):
    grouped = GEN.categorised(pack, list(GEN.pack_module(pack).TOOLS))
    if len(grouped) == 1:
        assert grouped[0][0] is None, f"{pack}: a lone category should be flattened"


@pytest.mark.parametrize("pack", PACKS)
def test_a_page_states_its_tool_s_method_and_route(pack):
    """A page that renders beautifully at the wrong URL is worse than none."""
    for tool in GEN.pack_module(pack).TOOLS:
        text = _page(pack, tool)
        assert f'data-method="{tool.method}">{tool.method}<' in text
        assert GEN.route_of(tool) in text, f"{pack}.{tool.name} does not state its route"


@pytest.mark.parametrize("pack", PACKS)
def test_a_normalised_route_renames_nothing_but_the_case(pack):
    """``{calendar_id}`` becomes ``{calendarId}``; no segment may move or vanish."""
    for tool in GEN.pack_module(pack).TOOLS:
        original = re_findall_braces(tool.url_template)
        normalised = re_findall_braces(GEN.route_of(tool))
        assert len(original) == len(normalised)
        assert [name.replace("_", "").lower() for name in original] == [
            name.lower() for name in normalised
        ]
        assert GEN.route_of(tool).count("/") == ("/" + tool.url_template.lstrip("/")).count("/")


def test_a_pack_on_one_endpoint_still_gets_a_page_per_tool():
    """Linear and Shopify post every tool to the same URL. Nine must not vanish."""
    for pack in ("linear", "shopify"):
        module = GEN.pack_module(pack)
        routes = {(tool.method, GEN.route_of(tool)) for tool in module.TOOLS}
        assert len(routes) == 1, f"{pack} no longer shares one endpoint; revisit the keying"
        pages = {GEN.tool_page_path(pack, tool) for tool in module.TOOLS}
        assert len(pages) == len(module.TOOLS)
        for tool in module.TOOLS:
            assert "as every tool in this pack does" in _page(pack, tool)


@pytest.mark.parametrize("pack", PACKS)
def test_the_sample_call_names_the_tool_and_the_pack(pack):
    """The one block a reader copies. It must not be curl, and must not be fiction."""
    for tool in GEN.pack_module(pack).TOOLS:
        text = _page(pack, tool)
        assert "```python" in text and "curl" not in text
        assert f"from charter.packs import {pack}" in text
        assert f"{pack}.{tool.name}.ainvoke(" in text


# -----------------------------------------------------
# The arguments, and where they go
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_argument_reaches_the_page(pack):
    """Nothing the LLM schema exposes may be dropped on the way to the page."""
    for tool in GEN.pack_module(pack).TOOLS:
        expected = set(tool.to_json_schema()["parameters"].get("properties", {}))
        assert _field_names(_page(pack, tool)) == expected, f"{pack}.{tool.name}"


@pytest.mark.parametrize("pack", PACKS)
def test_arguments_are_grouped_by_where_the_value_lands(pack):
    """Path, query and body are the reader's first question about an argument."""
    for tool in GEN.pack_module(pack).TOOLS:
        text = _page(pack, tool)
        placements = set(GEN._placements(tool).values())
        for where, heading in GEN._SECTIONS:
            if where in placements:
                assert f"## {heading}" in text, f"{pack}.{tool.name} has no {heading}"


@pytest.mark.parametrize("pack", PACKS)
def test_path_parameters_are_the_ones_the_url_template_names(pack):
    """``{userId}`` in the template and a path parameter are the same statement."""
    for tool in GEN.pack_module(pack).TOOLS:
        templated = set(re_findall_braces(GEN.route_of(tool)))
        declared = {name for name, where in GEN._placements(tool).items() if where == "path"}
        assert declared == templated, f"{pack}.{tool.name}"


@pytest.mark.parametrize("pack", PACKS)
def test_a_path_parameter_can_always_be_filled(pack):
    """A URL cannot be built out of a hole.

    Not the same as required: Gmail's ``userId`` and Google Calendar's
    ``userId`` both default to ``"me"``, so a caller can leave them out and the
    template still resolves. What may not happen is a path segment that is
    neither required nor defaulted.
    """
    for tool in GEN.pack_module(pack).TOOLS:
        text = _page(pack, tool)
        section = text.split("## Path parameters")
        if len(section) == 1:
            continue
        body = section[1].split("\n## ")[0]
        for row in _rows(body):
            fillable = "required" in row[0] or "defaults to" in row[2]
            assert fillable, f"{pack}.{tool.name}: {row[0]} can leave a hole in the URL"


@pytest.mark.parametrize("pack", PACKS)
def test_the_placement_is_not_repeated_as_a_marker(pack):
    """The page heads each table with the location, so a pill would restate it.

    Asserted because the marker slot is the page's whole differentiator: it is
    for what nothing else on the page says.
    """
    for path, text in PAGES.items():
        if not path.startswith(f"packs/{pack}/"):
            continue
        for marker in re.findall(r'data-marker="(\w+)"', text):
            assert marker in {"transform", "case", "mode"}, f"{pack}: stray marker {marker}"
        for value in re.findall(r'data-marker="\w+">(\w+)<', text):
            assert value not in {"path", "query", "body"}, f"{pack}: placement as a marker"


# -----------------------------------------------------
# The markers, which are the reason for the pages
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_visible_transform_in_the_pack_is_annotated(pack):
    """A ``Format`` field is where a semantic type meets a wire encoding.

    It is the single most useful thing on the page and the easiest to lose,
    since it is usually declared several models deep. Only fields the LLM view
    keeps are expected: Gmail declares ``base64url`` on a ``response_only``
    field, which no caller can set and no page should offer.
    """
    module = GEN.pack_module(pack)
    expected = set()
    for tool in module.TOOLS:
        for pills in GEN.marker_map(tool.args_schema).values():
            expected |= {value for kind, value in sum(pills.values(), []) if kind == "transform"}

    rendered = "".join(text for path, text in PAGES.items() if path.startswith(f"packs/{pack}/"))
    found = set(re.findall(r'data-marker="transform">([^<]+)<', rendered))
    assert expected <= found, f"{pack}: transforms declared but never rendered: {expected - found}"

    from charter.transforms import get_transform

    for name in found:
        assert get_transform(name) is not None, f"{pack}: {name} is not a registered transform"


def test_the_gmail_send_body_carries_its_transform():
    """The worked example, pinned: an ``EmailContent`` in, RFC 822 base64 out."""
    text = PAGES["packs/gmail/message/objects.mdx"]
    row = next(row for row in _rows(text) if row[0].startswith("`raw`"))
    assert 'data-marker="transform">rfc822_base64<' in row[1]
    assert 'data-marker="mode">request_only<' in row[1]


@pytest.mark.parametrize("pack", PACKS)
def test_no_hidden_field_is_rendered(pack):
    """``response_only`` and ``disabled`` fields are not part of the LLM view.

    They are dropped before the schema is built, so a marker naming one would
    mean the page is showing the caller a field they cannot set.
    """
    for path, text in PAGES.items():
        if not path.startswith(f"packs/{pack}/"):
            continue
        for value in re.findall(r'data-marker="mode">([^<]+)<', text):
            assert value not in {"response_only", "disabled"}, f"{pack}: {value} rendered"


@pytest.mark.parametrize("pack", PACKS)
def test_scopes_and_pagination_are_stated_where_they_apply(pack):
    for tool in GEN.pack_module(pack).TOOLS:
        text = _page(pack, tool)
        for scope in tool.scopes:
            assert f"`{scope}`" in text, f"{pack}.{tool.name} does not state {scope}"
        if tool.pagination is not None:
            assert "Pages by" in text, f"{pack}.{tool.name} paginates but does not say so"


# -----------------------------------------------------
# Links resolve
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_type_link_lands_on_a_heading_that_exists(pack):
    """A link into an objects page is this reference's ``$ref``.

    It is also the thing a table cannot show is broken: an anchor that matches
    nothing scrolls nowhere and looks exactly like one that works.

    A generated page also links *out* of the generated tree, to the hand-written
    docs (``/reference/tool#tool-derived``, from a wide tool's projection note).
    Those are resolved against ``docs/`` on disk rather than skipped: Mint's
    broken-links check verifies the page and ignores the fragment, so the anchor
    is otherwise the one half of the link nothing checks.
    """
    for path, text in PAGES.items():
        if not path.startswith(f"packs/{pack}/"):
            continue
        for target in _links(text):
            page, _, fragment = target.partition("#")
            if page and not page.lstrip("/").startswith("packs/"):
                headings = _hand_written_headings(page.lstrip("/"))
                assert headings is not None, f"{path}: {target} has no page"
            elif page:
                assert page.lstrip("/") + ".mdx" in PAGES, f"{path}: {target} has no page"
                headings = _headings(PAGES[page.lstrip("/") + ".mdx"])
            else:
                headings = _headings(text)
            if fragment:
                anchors = {GEN.anchor(heading) for heading in headings}
                assert fragment in anchors, f"{path}: {target} lands on no heading"


@pytest.mark.parametrize("pack", PACKS)
def test_an_objects_page_publishes_nothing_no_field_reaches(pack):
    """The type modules name aliases for parts of an API a pack has not covered.

    A section for one of those is a table nothing on the site links to, which is
    the reference claiming a coverage it does not have.
    """
    linked = set()
    for path, text in PAGES.items():
        if path.startswith(f"packs/{pack}/"):
            linked |= {target.rpartition("#")[2] for target in _links(text)}
    for path, text in PAGES.items():
        if not path.startswith(f"packs/{pack}/") or not path.endswith("objects.mdx"):
            continue
        for heading in _headings(text):
            if heading == "Model tree":
                continue
            assert GEN.anchor(heading) in linked, f"{path}: {heading} is linked from nowhere"


@pytest.mark.parametrize("pack", PACKS)
def test_a_type_column_never_breaks_the_row_it_is_in(pack):
    """An unescaped ``|`` in a union or a description silently eats a column."""
    for path, text in PAGES.items():
        if not path.startswith(f"packs/{pack}/"):
            continue
        for row in _rows(text):
            assert len(row) in (1, 3), f"{path}: a row split into {len(row)} cells: {row}"


# -----------------------------------------------------
# The site is configured to render them
# -----------------------------------------------------


def _nav_pages(node):
    for entry in _walk(CONFIG["navigation"]):
        for page in entry.get("pages", []):
            if isinstance(page, str):
                yield page


def test_the_navigation_lists_every_page_and_no_others():
    """A page nothing points at is a file, not a page."""
    listed = {page for page in _nav_pages(CONFIG) if page.startswith("packs/")}
    generated = {path.removesuffix(".mdx") for path in PAGES}
    overviews = {f"packs/{pack}" for pack in PACKS} | {"packs/overview"}
    assert listed == generated | overviews


def test_each_pack_group_lists_its_prose_page_first():
    """The pack's own page is a sidebar entry, not only a clickable group title."""
    for pack in PACKS:
        group = next(
            node
            for node in _walk(CONFIG["navigation"])
            if isinstance(node.get("pages"), list) and f"packs/{pack}" in node["pages"]
        )
        assert group["pages"][0] == f"packs/{pack}"
        assert "root" not in group, f"{pack}: root duplicates the listed page"


@pytest.mark.parametrize("pack", PACKS)
def test_the_prose_page_is_labelled_overview_in_the_sidebar(pack):
    """Its title is the pack's name, which under a group of that name says nothing."""
    head = (PACK_DOCS / f"{pack}.mdx").read_text().split("---")[1]
    assert 'sidebarTitle: "Overview"' in head


def test_no_openapi_renderer_configuration_survives():
    """``api`` and an ``openapi`` source only ever fed the renderer that went."""
    assert "api" not in CONFIG
    assert not [node for node in _walk(CONFIG["navigation"]) if "openapi" in node]
    assert not list(PACK_DOCS.glob("*.openapi.json"))


@pytest.mark.parametrize("pack", PACKS)
def test_the_old_tool_url_still_resolves(pack):
    """These pages have been linked as ``/packs/<pack>/tools/<tool>`` since the
    packs shipped. Regrouping them must not turn a bookmark into a 404."""
    destinations = {r["source"]: r["destination"] for r in CONFIG["redirects"]}
    for tool in GEN.pack_module(pack).TOOLS:
        source = f"/packs/{pack}/tools/{tool.name}"
        expected = GEN.tool_page_path(pack, tool)
        if source == expected:
            continue
        assert destinations.get(source) == expected, f"{source} does not redirect"


# -----------------------------------------------------
# The pack page points into them
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_the_tool_list_links_to_each_tool_s_page(pack):
    """The link the pack page writes and the path the generator publishes at are
    one string, imported rather than reconstructed so they cannot disagree."""
    text = (PACK_DOCS / f"{pack}.mdx").read_text()
    for tool in GEN.pack_module(pack).TOOLS:
        href = GEN.tool_page_path(pack, tool)
        assert f'href="{href}"' in text, f"{pack}.{tool.name} is not linked at {href}"
