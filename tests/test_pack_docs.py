"""R10.5 — the pack reference pages are generated, and stay generated.

A pack page states the tool list, the HTTP method, what each tool does, the base
URL, the encoding, the envelope and the pagination style. Every one of those is
already on the ``Tool`` objects the pack exports, so a page that restates them by
hand is correct on the day it is written and wrong on the day somebody adds a
tool.

``scripts/generate_pack_docs.py`` renders those regions from the live package.
This file asserts that what is on disk equals what the generator would produce
right now, and that every pack in ``charter.packs`` has a page at all — so a pack
added next year either shows up in the docs or turns the suite red.

The prose around the markers is hand-written and deliberately not checked here,
beyond the links, which the README suite already resolves site-wide.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import re
import sys
from pathlib import Path as FsPath
from types import SimpleNamespace

import pytest

from charter.mcp import PACKS

ROOT = FsPath(__file__).resolve().parent.parent
PACK_DOCS = ROOT / "docs" / "packs"


def _load_generator():
    """Import the script by path; ``scripts/`` is not a package."""
    path = ROOT / "scripts" / "generate_pack_docs.py"
    spec = importlib.util.spec_from_file_location("generate_pack_docs", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


GEN = _load_generator()

BLOCKS = ("summary", "tools", "auth", "wire")


# -----------------------------------------------------
# Every pack has a page, and every page is a pack
# -----------------------------------------------------


def test_every_shipped_pack_has_a_page():
    missing = [pack for pack in PACKS if not GEN.page_path(pack).exists()]
    assert not missing, (
        f"packs with no docs/packs/<pack>.mdx: {missing}. "
        "Add the page, with both generated regions, and rerun the generator."
    )


def test_no_page_documents_a_pack_that_no_longer_exists():
    pages = {path.stem for path in PACK_DOCS.glob("*.mdx")} - {"overview"}
    assert pages == set(PACKS), f"pages {sorted(pages)} against packs {sorted(PACKS)}"


def test_the_overview_grid_counts_the_tools_each_pack_actually_ships():
    """The one number on that page nothing derives.

    Each pack page's own summary strip is generated and checked, but the
    coverage grid is hand-written, so it drifts silently: it claimed three
    Google Calendar tools against four in the code, and had done for as long as
    the fourth existed. A pack that grows now turns this red instead.
    """
    text = (PACK_DOCS / "overview.mdx").read_text()
    wrong = []
    for pack in PACKS:
        expected = len(importlib.import_module(f"charter.packs.{pack}").TOOLS)
        found = re.search(rf'href="/packs/{pack}">\s*\n\s*(\d+) tools', text)
        if found is None or int(found.group(1)) != expected:
            wrong.append(f"{pack}: card says {found.group(1) if found else 'nothing'}, code ships {expected}")
    assert not wrong, "docs/packs/overview.mdx miscounts: " + "; ".join(wrong)


def test_the_overview_links_to_every_pack_page():
    """Either as markdown — `(/packs/slack)` — or as a card's `href`."""
    text = (PACK_DOCS / "overview.mdx").read_text()
    missing = [
        pack
        for pack in PACKS
        if f"(/packs/{pack})" not in text and f'href="/packs/{pack}"' not in text
    ]
    assert not missing, f"overview.mdx does not link to: {missing}"


# -----------------------------------------------------
# The generated regions match the package
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_generated_blocks_are_current(pack):
    """The point of the whole exercise: the page equals what the code says."""
    text = GEN.page_path(pack).read_text()
    expected = GEN.blocks(pack)

    for block in BLOCKS:
        found = GEN.extract(text, block)
        assert found is not None, (
            f"docs/packs/{pack}.mdx has no '{block}' region. It needs\n"
            f"  {GEN.start_marker(block)}\n  ...\n  {GEN.end_marker(block)}"
        )
        assert found == expected[block], (
            f"docs/packs/{pack}.mdx '{block}' block is stale.\n"
            f"Run: uv run python scripts/generate_pack_docs.py"
        )


def test_the_generator_reports_a_clean_tree():
    """``--check`` is what CI would run; it must agree with the assertions above."""
    assert GEN.main(["--check"]) == 0


@pytest.mark.parametrize("pack", PACKS)
def test_regenerating_is_idempotent(pack):
    text = GEN.page_path(pack).read_text()
    assert GEN.regenerate(GEN.regenerate(text, pack), pack) == text


# -----------------------------------------------------
# The generated regions actually say something
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACKS)
def test_every_tool_appears_in_the_list(pack):
    """Guard against a renderer that silently produces an empty list.

    One entry per tool, and each one carries the three things the list is for:
    the name, the link to the tool's own page, and the method pill.
    """
    module = GEN.pack_module(pack)
    listing = GEN.blocks(pack)["tools"]
    for tool in module.TOOLS:
        assert f'>{tool.name}</span>' in listing
        assert f'href="{GEN.tool_page_path(pack, tool)}"' in listing
        assert f'data-method="{tool.method}"' in listing
    assert listing.count('className="tool-row"') == len(module.TOOLS)


@pytest.mark.parametrize("pack", PACKS)
def test_every_entry_says_what_the_tool_does(pack):
    """The description column is the whole reason the path column went.

    A tool description is written for a model, so it opens with what the tool
    does and then turns into usage guidance. The list takes the opening
    sentence; the rest is on the tool's own page.
    """
    module = GEN.pack_module(pack)
    listing = GEN.blocks(pack)["tools"]
    for tool in module.TOOLS:
        summary = GEN._first_sentence(tool.description)
        assert summary, f"{pack}.{tool.name} has no description to summarise"
        assert summary == summary.strip()
        assert f'<span className="tool-row-desc">{GEN._inline_code(summary)}</span>' in listing


def test_the_first_sentence_split_leaves_an_abbreviation_alone():
    """The split is what keeps a path or an `e.g.` from ending the summary."""
    assert GEN._first_sentence("Search with qualifiers, e.g. 'is:open'. Use when.") == (
        "Search with qualifiers, e.g. 'is:open'."
    )
    assert GEN._first_sentence("Takes a `gid://shopify/Order/...`, which list returns.") == (
        "Takes a `gid://shopify/Order/...`, which list returns."
    )
    assert GEN._first_sentence("Update a product.") == "Update a product."


@pytest.mark.parametrize("pack", PACKS)
def test_the_list_leaves_no_mdx_syntax_loose(pack):
    """A description reaches the page as a JSX child, not as markdown.

    Which is the one hazard of rendering prose into JSX: an unescaped brace
    opens an expression, an angle bracket opens a tag, and either breaks the
    build. Backticks are the mirror case — legal, silent, and rendered as
    literal backticks unless they are turned into a tag on the way out.
    """
    listing = GEN.blocks(pack)["tools"]
    for line in listing.splitlines():
        if 'className="tool-row-desc"' not in line:
            continue
        prose = re.sub(r"<[^>]+>", "", line)
        assert "`" not in prose, f"{pack}: backtick left as prose in {line}"
        assert "{" not in prose and "}" not in prose, f"{pack}: bare brace in {line}"


@pytest.mark.parametrize("pack", PACKS)
def test_the_auth_signpost_routes_rather_than_restates(pack):
    """The section that used to be eleven copies of one paragraph.

    Its job is to send a reader somewhere, so what is asserted is the
    destinations — and, for an API-key pack, that it says the OAuth machinery
    does not apply instead of quietly leaving the question open.
    """
    module = GEN.pack_module(pack)
    signpost = GEN.blocks(pack)["auth"]
    oauth = module.TOOLS[0].credential_provider is not None

    if oauth:
        # Where a reader with no refresh token is sent. Google's packs go to the
        # walkthrough, which is written for Google; Slack's and GitHub's go to
        # the grant section of their own server's page, which carries the code
        # for that server.
        assert (
            "/auth/your-own-account" in signpost
            or "#getting-the-first-grant" in signpost
        )
        assert "/auth/oauth-flow" in signpost
        assert "/auth/authorization-servers" in signpost
        assert "/auth/api-key-tool-factory" not in signpost
        provider = module.TOOLS[0].provider
        if provider in GEN._PROVIDER_PAGES:
            assert GEN._PROVIDER_PAGES[provider][1] in signpost
    else:
        assert "/auth/api-key-tool-factory" in signpost
        assert "no authorization server, no consent screen and no refresh" in signpost
        assert "/auth/oauth-flow" not in signpost
        assert "/auth/your-own-account" not in signpost


_AUTH_BLOCK = re.compile(r"^```python[^\n]*\n(.*?)^```", re.M | re.S)


def _oauth_packs():
    return [pack for pack in PACKS if GEN.pack_module(pack).TOOLS[0].credential_provider is not None]


@pytest.mark.parametrize("pack", _oauth_packs())
def test_every_credential_shape_actually_runs(pack, monkeypatch):
    """The three tabs are code a reader copies, so they are executed here.

    This is the block that fixed the pack pages' one real lie — every snippet
    on them used to hand `configure()` a token somebody already had. Three
    shapes are only an improvement if all three work, and two of them were
    never written down before, so none of them had ever been run.

    The names a deployment supplies — the token, the stored grant, the per-user
    factory, the server constant — are stubbed, the way the OAuth docs suite
    stubs a reader's web framework.
    """
    import charter
    import charter.auth

    constant = charter.auth.OAuth2Server(
        issuer="https://login.example.com",
        authorization_endpoint="https://login.example.com/authorize",
        token_endpoint="https://login.example.com/token",
    )

    async def for_user(subject):
        return charter.auth.StaticTokenProvider("token-for-" + subject)

    # The third tab names a user per request, the way a web framework would.
    request = SimpleNamespace(user_id="user-42")

    provider = GEN.pack_module(pack).TOOLS[0].provider or "server"
    monkeypatch.setenv(f"{provider.upper()}_CLIENT_ID", "cid")
    monkeypatch.setenv(f"{provider.upper()}_CLIENT_SECRET", "csec")
    # The snippets read their token out of the environment now, rather than
    # naming a variable that came from nowhere, so the environment has to hold
    # one for them to run here.
    monkeypatch.setenv(f"{provider.upper()}_REFRESH_TOKEN", "rt-stored")

    blocks = _AUTH_BLOCK.findall(GEN.blocks(pack)["auth"])
    assert len(blocks) == 3, f"{pack}: {len(blocks)} credential shapes, expected 3"

    for index, source in enumerate(blocks):
        namespace = {
            "__name__": "__pack_docs__",
            "os": os,
            "for_user": for_user,
            "request": request,
            provider.upper(): constant,
        }
        exec(compile(source, f"<{pack}.mdx credential {index}>", "exec"), namespace)  # noqa: S102


_TITLED_FENCE = re.compile(r"^```python ([^\n]*)\n(.*?)^```", re.M | re.S)


@pytest.mark.parametrize("pack", _oauth_packs())
def test_each_credential_snippet_highlights_the_line_it_is_about(pack):
    """A line number beside a snippet is the one thing on the page that rots silently.

    Mintlify takes the highlight as ``{4}``, counted from the top of the fence,
    so an import added above it moves the band onto whatever line took its
    place: a page that looks maintained and points at the wrong thing. The
    generator counts the numbers from named lines; this asserts that what the
    numbers land on is still what the section is about.
    """
    fences = _TITLED_FENCE.findall(GEN.blocks(pack)["auth"])
    assert len(fences) == 3, f"{pack}: {len(fences)} titled fences, expected 3"

    # The object being built, not the `configure()` call, which is the same
    # line in all three: what the reader is choosing between is the provider.
    wanted = (
        ["credentials = EnvTokenProvider("],
        ["_REFRESH_TOKEN"],
        ["credentials = SubjectProvider(for_user)", "with use_subject("],
    )
    for (meta, source), needles in zip(fences, wanted, strict=True):
        marks = re.search(r"\{([\d,]+)\}$", meta)
        assert marks, f"{pack}: no highlight on {meta!r}"
        lines = source.splitlines()
        numbers = [int(number) for number in marks.group(1).split(",")]
        assert numbers == sorted(numbers)
        assert len(numbers) == len(needles)
        for number, needle in zip(numbers, needles, strict=True):
            assert 1 <= number <= len(lines), f"{pack}: line {number} of {len(lines)}"
            assert needle in lines[number - 1], (
                f"{pack}: {meta!r} highlights {lines[number - 1]!r}, not {needle!r}"
            )


@pytest.mark.parametrize("pack", _oauth_packs())
def test_each_credential_shape_is_a_heading_naming_a_deployment(pack):
    """Three headings rather than three tabs, and a filename on each snippet.

    A tab is for a choice the reader has already made; this is the choice
    itself, so all three stay visible, land in the page's table of contents and
    answer to ctrl-F. The heading says which shape, and the filename says where
    the code lives — a script, an agent, a server — which is what the reader is
    really choosing between.
    """
    block = GEN.blocks(pack)["auth"]
    assert "<CodeGroup>" not in block, f"{pack}: the credential shapes are tabbed again"

    for heading in ("### A token you hold", "### One account, refreshed", "### Many end users"):
        assert heading in block, f"{pack}: no {heading!r} section"

    titles = [meta.split(" ")[0] for meta, _ in _TITLED_FENCE.findall(block)]
    assert titles == [f"{pack}_script.py", f"{pack}_agent.py", f"{pack}_server.py"]


@pytest.mark.parametrize("pack", _oauth_packs())
def test_each_credential_shape_links_its_own_signature(pack):
    """A name set in code type is a name a reader may want to look up.

    Each section names its provider class and links it at its own reference
    anchor, in the prose above that section's snippet — so the way further in is
    where the reader already is, rather than in a list at the top that reads as
    a fourth thing to choose from.
    """
    sections = GEN.blocks(pack)["auth"].split("### ")
    assert len(sections) == 4, f"{pack}: {len(sections) - 1} shapes, expected 3"

    for section, anchors in zip(
        sections[1:],
        (
            ["/reference/credentials#statictokenprovider"],
            ["/reference/oauth#oauth2client"],
            [
                "/reference/credentials#subjectprovider",
                "/reference/credentials#use_subject",
            ],
        ),
        strict=True,
    ):
        heading = section.splitlines()[0]
        for anchor in anchors:
            assert anchor in section, f"{pack}: {heading!r} does not link {anchor}"
            assert section.index(anchor) < section.index("```python"), (
                f"{pack}: {heading!r} links {anchor} below its snippet"
            )


@pytest.mark.parametrize("pack", PACKS)
def test_both_halves_of_the_comparison_use_the_same_credential(pack):
    """The declarations block is a controlled comparison, so it controls.

    Its two tabs exist to show how much you write by hand against how little you
    write with the pack. Anything else that differs between them reads as
    something the pack changed — and for a while the credential did differ, an
    EnvTokenProvider on one side against a StaticTokenProvider on the other,
    which made the choice of credential look like part of the bargain.
    """
    module = GEN.pack_module(pack)
    first = module.TOOLS[0]
    holder = first.credential_provider or first.api_key_headers
    env_var = getattr(holder, "env_var", None)
    if not env_var:
        pytest.skip(f"{pack} names no environment variable")

    wire = GEN.blocks(pack)["wire"]
    by_hand, with_pack = _AUTH_BLOCK.findall(wire)[:2]
    # An OAuth pack hands over one named provider — the one the reader chose in
    # Authenticating — rather than building a second kind here; an API-key pack
    # reads its key from the environment on both sides.
    expected = (
        GEN._CREDENTIAL
        if first.credential_provider is not None
        else f'os.environ["{env_var}"]'
    )
    for half, source in (("hand written", by_hand), ("with the pack", with_pack)):
        assert expected in source, f"{pack}: the {half} tab does not use {expected}"


@pytest.mark.parametrize("pack", _oauth_packs())
def test_the_shape_snippets_name_the_provider_page_s_own_constant(pack):
    """`OAuth2Client(GOOGLE, ...)` is only copyable if `GOOGLE` is declared somewhere.

    The generator derives the name from the pack's provider, so a provider whose
    page calls its constant something else would produce a snippet naming a
    variable that exists nowhere in the docs.
    """
    tool = GEN.pack_module(pack).TOOLS[0]
    named = GEN._PROVIDER_PAGES.get(tool.provider or "")
    if not named:
        pytest.skip(f"{tool.provider} has no provider page")

    constant = tool.provider.upper()
    page = (PACK_DOCS.parent / f"{named[1].lstrip('/')}.mdx").read_text()
    assert f"{constant} = OAuth2Server(" in page, (
        f"{pack} points at {constant}, which {named[1]} does not declare"
    )
    for suffix in ("CLIENT_ID", "CLIENT_SECRET"):
        assert f"{constant}_{suffix}" in page, (
            f"{pack} reads ${constant}_{suffix}, which {named[1]} never names"
        )


@pytest.mark.parametrize("pack", PACKS)
def test_the_signpost_never_promises_an_env_var_is_enough(pack):
    """Shopify needs a store as well as a token, so it gets no such clause.

    A generated "optional when `$X` is set" on a pack that needs two values is
    the worst kind of docs bug: derived from the package, and false.
    """
    module = GEN.pack_module(pack)
    signpost = GEN.blocks(pack)["auth"]
    single = len(inspect.signature(module.configure).parameters) == 1

    # The name is a link now, not bare code type, so the clause is matched
    # through its anchor: `configure()` is a symbol a reader can look up.
    clause = "[`configure()`](/reference/configuration#configure) is optional when"
    assert (clause in signpost) is single
    if single:
        holder = module.TOOLS[0].credential_provider or module.TOOLS[0].api_key_headers
        assert f"`${holder.env_var}`" in signpost


@pytest.mark.parametrize("pack", PACKS)
def test_the_page_states_the_global_configure_rule_only_once(pack):
    """The paragraph that made this section repetitive, kept from coming back.

    "Configuration reaches tools that were built at import time" and "headers
    are resolved per request" are properties of every pack, stated once on
    /reference/configuration#configure, which every pack page links to. Eleven
    restatements are what this pass removed.
    """
    text = GEN.page_path(pack).read_text()
    for global_fact in (
        "built at import time",
        "resolved per request",
        "raises `CredentialError` before anything is sent",
    ):
        assert global_fact not in text, f"docs/packs/{pack}.mdx restates: {global_fact}"


@pytest.mark.parametrize("pack", PACKS)
def test_the_summary_states_the_count_and_the_auth(pack):
    """The strip at the top of the page is the tool list counted, not a guess."""
    module = GEN.pack_module(pack)
    summary = GEN.blocks(pack)["summary"]

    assert f"</Visibility>{len(module.TOOLS)} tools</span>" in summary

    oauth = module.TOOLS[0].credential_provider is not None
    assert ("</Visibility>OAuth bearer</span>" in summary) is oauth
    assert ("</Visibility>API key</span>" in summary) is not oauth


@pytest.mark.parametrize("pack", PACKS)
def test_the_summary_pills_carry_a_glyph(pack):
    """Two pills, two icons, and the auth glyph says which credential it is.

    A wrench and a shield are different shapes; a shield on an API-key pack is
    the kind of wrong a reader believes, so the pairing is asserted rather than
    left to the renderer.

    Both glyphs are drawn for readers only. The `.md` behind this page is what a
    coding agent fetches, and it is made from this MDX, so an unwrapped `<svg>`
    would spend the agent's context on a path string that says nothing the label
    beside it does not already say. The wrapper is asserted here because nothing
    on the rendered page would look wrong if it went missing.
    """
    module = GEN.pack_module(pack)
    summary = GEN.blocks(pack)["summary"]

    assert summary.count('<svg viewBox="0 0 24 24">') == 2
    assert summary.count('<Visibility for="humans"><svg viewBox="0 0 24 24">') == 2
    assert summary.count("</svg></Visibility>") == 2
    assert GEN._ICON_TOOLS in summary

    oauth = module.TOOLS[0].credential_provider is not None
    assert (GEN._ICON_OAUTH in summary) is oauth
    assert (GEN._ICON_API_KEY in summary) is not oauth


_QUICKSTART_CALL = re.compile(r"await (\w+)\.(\w+)\.ainvoke\(")

@pytest.mark.parametrize("pack", PACKS)
def test_every_page_is_laid_out_the_same_way(pack):
    """One order across eleven pages, because a reader reads more than one.

    The client comes before the tool list: the list and "what crosses the
    boundary" are both about the schemas, and the client used to sit between
    them. It is also the section that answers what the credential from
    Authenticating is handed to.
    """
    headings = re.findall(r"^## (.+)$", GEN.page_path(pack).read_text(), re.M)
    assert "What the pack declares" not in headings, f"{pack}: old heading"

    for earlier, later in (("Authenticating", "The client"), ("The client", "Tools")):
        assert earlier in headings and later in headings, f"{pack}: missing sections"
        assert headings.index(earlier) < headings.index(later), (
            f"{pack}: '{later}' comes before '{earlier}' — {headings}"
        )


@pytest.mark.parametrize("pack", PACKS)
def test_the_tool_list_says_what_a_row_is(pack):
    """The list is links and pills; one line above it says what they are."""
    text = GEN.page_path(pack).read_text()
    lead = text.split("## Tools\n", 1)[1].split(GEN.start_marker("tools"))[0]
    assert "[`Tool`](/reference/tool)" in lead, f"{pack}: the tool list has no lead"
    assert "/reference/tool#tool-ainvoke" in lead, f"{pack}: ainvoke is not linked"


@pytest.mark.parametrize("pack", PACKS)
def test_the_opening_snippet_highlights_the_call(pack):
    """The line worth looking at is the result, not the setup around it."""
    text = GEN.page_path(pack).read_text()
    found = re.search(rf"^```python {pack}_example\.py \{{([\d,]+)\}}\n(.*?)^```", text, re.M | re.S)
    assert found, f"{pack}: the opening snippet carries no highlight"

    lines = found.group(2).splitlines()
    for number in (int(n) for n in found.group(1).split(",")):
        assert ".ainvoke(" in lines[number - 1], (
            f"{pack}: highlight {number} is on {lines[number - 1]!r}, not a call"
        )


@pytest.mark.parametrize("pack", PACKS)
def test_the_page_opens_with_a_snippet_that_configures_and_calls(pack):
    """A reader who copies the first code block should get a working call.

    So it comes before the prose, and it names a tool the pack actually
    exports — a snippet against a renamed tool is worse than no snippet.
    """
    text = GEN.page_path(pack).read_text()
    after_summary = text.split(GEN.end_marker("summary"), 1)[1]
    opening = after_summary.split("\n## ", 1)[0]

    # The fence carries a filename now, so the opener is matched past it.
    fences = re.findall(r"^```python[^\n]*\n(.*?)^```", opening, re.M | re.S)
    assert fences, f"docs/packs/{pack}.mdx has no python snippet above its first heading"

    snippet = fences[0]
    assert f"{pack}.configure(" in snippet, f"{pack}: the snippet never configures the pack"

    calls = _QUICKSTART_CALL.findall(snippet)
    assert calls, f"{pack}: the snippet configures but never calls anything"

    names = {tool.name for tool in GEN.pack_module(pack).TOOLS}
    for module_name, tool_name in calls:
        assert module_name == pack, f"{pack}: snippet calls `{module_name}`"
        assert tool_name in names, f"{pack}: snippet calls `{tool_name}`, which the pack does not export"


@pytest.mark.parametrize("pack", PACKS)
def test_the_list_states_neither_the_path_nor_the_quota(pack):
    """Both left the list on purpose; the tool's own page is where they live.

    A URL template in a list of nine is forty characters of shared prefix per
    row, and a quota column is a number that means nothing without the
    paragraph under it. Asserting their absence keeps a later "while I'm here"
    column from quietly rebuilding the table.
    """
    module = GEN.pack_module(pack)
    listing = GEN.blocks(pack)["tools"]
    for tool in module.TOOLS:
        # A single-segment template — Firecrawl's `search`, GitHub's `user` —
        # is also an ordinary English word, so only a real path is searched for.
        if "/" in tool.url_template:
            assert tool.url_template not in listing
    assert "Quota" not in listing


@pytest.mark.parametrize("pack", PACKS)
def test_the_wire_block_names_the_pack_s_own_declarations(pack):
    module = GEN.pack_module(pack)
    code = GEN.wire_declarations(pack, module)

    assert "base_url=" in code
    assert f"{pack}_api_client = " in code
    # The block stands on its own: it is what you would write if the pack did
    # not exist, so it must not reach for the pack to get there.
    assert "charter.packs" not in code
    assert ".configure(" not in code

    base_url = getattr(module, "BASE_URL", None)
    if base_url is not None:
        assert f'base_url="{base_url}"' in code

    first = module.TOOLS[0]
    if first.envelope is None:
        assert "envelope=None" in code
    else:
        assert "envelope=Envelope(" in code

    # Pagination is declared under the tabs, not inside the factory call: it is
    # one declaration per list endpoint rather than a property of the API, and
    # it needed a comment inside the code to say so.
    assert "Pagination(" not in code

    block = GEN.blocks(pack)["wire"]
    paging = [tool.name for tool in module.TOOLS if tool.pagination is not None]
    if paging:
        assert "### Paging through a list" in block
        assert f"```python {pack}_pagination.py" in block
        for name in paging:
            assert name in block
    else:
        assert "Pagination(" not in block
        assert "### Paging through a list" not in block


@pytest.mark.parametrize("pack", PACKS)
def test_the_wire_block_offers_both_ways(pack):
    """Two tabs: the declarations written out, and the pack that makes them.

    The first tab is what the pack is hiding, so neither is useful without the
    other sitting next to it. Both are hand written, which is why the label is
    "Without the pack": the two are read against each other, and each one has
    to say what it is the opposite of.
    """
    block = GEN.blocks(pack)["wire"]
    assert "<CodeGroup>" in block and "</CodeGroup>" in block
    assert "```python Without the pack" in block
    assert "```python With the pack" in block
    # The tab says which; the card's bar says what the file would be called.
    assert f'data-files="{pack}_api_client.py|{pack}_pack_client.py"' in block
    assert f"from charter.packs import {pack}" in block
    assert f"{pack}_api_client = " in block


@pytest.mark.parametrize("pack", PACKS)
def test_the_pack_tab_is_valid_python(pack):
    code = GEN.pack_usage(pack, GEN.pack_module(pack))
    compile(code, f"<{pack} pack usage>", "exec")


@pytest.mark.parametrize("pack", PACKS)
def test_the_wire_block_is_valid_python(pack):
    """It is published as `python`, so it has to parse as python."""
    code = GEN.wire_declarations(pack, GEN.pack_module(pack))
    compile(code, f"<{pack} wire>", "exec")


def test_the_env_var_a_pack_falls_back_to_is_on_its_page():
    """The most copy-pasted fact on the page, so it is read from the pack."""
    expected = {
        "gmail": "GOOGLE_ACCESS_TOKEN",
        "slack": "SLACK_BOT_TOKEN",
        "github": "GITHUB_TOKEN",
        "stripe": "STRIPE_API_KEY",
        "linear": "LINEAR_API_KEY",
        "shopify": "SHOPIFY_ACCESS_TOKEN",
        "firecrawl": "FIRECRAWL_API_KEY",
    }
    for pack, env_var in expected.items():
        page = GEN.page_path(pack).read_text()
        # An API-key pack reads it in the declarations block; an OAuth pack
        # names it in the auth signpost, where the fallback is what it means.
        # Quoted either way: an f-string embeds the read with single quotes.
        assert any(
            form in page for form in (f'"{env_var}"', f"'{env_var}'", f"${env_var}")
        ), pack


# -----------------------------------------------------
# MDX hygiene
# -----------------------------------------------------

_PAGES = sorted(PACK_DOCS.glob("*.mdx"))
_IDS = [path.name for path in _PAGES]

_FENCE = re.compile(r"^```(\w*)[^\n]*\n.*?^```", re.M | re.S)
_INLINE_CODE = re.compile(r"`[^`]*`")


def _prose(text: str) -> str:
    """The page with code fences, inline code, MDX comments and JSX tags removed.

    Tags go too because a component's attributes are JSX, not prose: the braces
    in `<Columns cols={3}>` are the point of the syntax, not a build break.
    """
    text = _FENCE.sub("", text)
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return _INLINE_CODE.sub("", text)


@pytest.mark.parametrize("page", _PAGES, ids=_IDS)
def test_no_bare_brace_outside_code(page):
    """A bare `{` in MDX prose is parsed as a JSX expression and breaks the build.

    Which matters here more than anywhere: half these pages quote URL templates
    like the Gmail one, and they must stay inside backticks or a fence.
    """
    offenders = [
        line for line in _prose(page.read_text()).splitlines() if "{" in line or "}" in line
    ]
    assert not offenders, f"{page.name}: unfenced brace in prose: {offenders}"


@pytest.mark.parametrize("page", _PAGES, ids=_IDS)
def test_every_fence_declares_a_language(page):
    untagged = [tag for tag in _FENCE.findall(page.read_text()) if not tag]
    assert not untagged, f"{page.name}: {len(untagged)} code block(s) with no language tag"


@pytest.mark.parametrize("page", _PAGES, ids=_IDS)
def test_frontmatter_has_a_title(page):
    head = page.read_text().split("---")[1]
    assert re.search(r'^title: ".+"$', head, re.M), page.name


@pytest.mark.parametrize("page", _PAGES, ids=_IDS)
def test_a_pack_page_carries_a_description(page):
    """The subheader under the title, on the eleven pages that name one API.

    The overview names none: a count of integrations restated the grid below it,
    so the page opens on what a pack is instead.
    """
    if page.stem == "overview":
        pytest.skip("the overview opens on its first paragraph, not a subheader")
    head = page.read_text().split("---")[1]
    assert re.search(r'^description: ".+"$', head, re.M), page.name


@pytest.mark.parametrize("page", _PAGES, ids=_IDS)
def test_no_marketing_language(page):
    """House style, enforced rather than remembered."""
    banned = (
        "powerful",
        "seamless",
        "robust",
        "it's important to note",
        "in order to",
        "simply ",
        "easily ",
    )
    prose = _prose(page.read_text()).lower()
    found = [word for word in banned if word in prose]
    assert not found, f"{page.name}: banned phrasing {found}"
