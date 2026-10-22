"""The front pages' claims, checked against the package.

The overview, Why Charter and the quickstart state facts about the package in
prose: how many packs ship and how many tools they carry, how many fields a tool
offers the model, what the quickstart prints and refuses. A page cannot verify
any of that itself, so each claim is checked here against the package, and every
Python block on those pages has to parse.
"""

from __future__ import annotations

import ast
import importlib
import json
import pkgutil
import re
from pathlib import Path as FsPath

import httpx
import pytest

from charter import egress_map, packs

ROOT = FsPath(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
INDEX = DOCS / "index.mdx"
WHY = DOCS / "why-charter.mdx"
QUICKSTART = DOCS / "start" / "quickstart.mdx"

_BLOCK = re.compile(r"^```(\w+)([^\n]*)\n(.*?)^```", re.M | re.S)

# Top-level `await` is how every call in these docs is written, and it is not
# valid in a plain module. This is the flag the REPL uses to allow it.
_ALLOW_TOP_LEVEL_AWAIT = 0x2000


_UNITS = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _word(n: int) -> str:
    """Spell a small number the way the prose spells it."""
    if n < 20:
        return _UNITS[n]
    tens, unit = divmod(n, 10)
    return _TENS[tens] + (f"-{_UNITS[unit]}" if unit else "")


def _blocks(path) -> list[tuple[str, str, str]]:
    """(language, meta, body) for every fenced block on the page."""
    return [(lang, meta.strip(), body) for lang, meta, body in _BLOCK.findall(path.read_text())]


def _parse(source: str):
    return compile(
        source, "<docs>", "exec", ast.PyCF_ONLY_AST | _ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True
    )


# --------------------------------------------------------------------------
# Every Python block on the overview, Why Charter and the quickstart.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("page", [INDEX, WHY, QUICKSTART], ids=lambda p: p.name)
def test_every_python_block_parses(page):
    for lang, meta, body in _blocks(page):
        if lang != "python":
            continue
        try:
            _parse(body)
        except SyntaxError as exc:
            pytest.fail(f"{page.name}: block {meta or '(untitled)'} does not parse: {exc}")


# --------------------------------------------------------------------------
# Counts stated in prose.
# --------------------------------------------------------------------------


def test_the_pack_counts_in_prose_match_the_package():
    names = sorted(
        m.name for m in pkgutil.iter_modules(packs.__path__) if not m.name.startswith("_")
    )
    tools = sum(len(importlib.import_module(f"charter.packs.{n}").TOOLS) for n in names)
    text = INDEX.read_text()

    assert f"one of {_word(len(names))}" in text, (
        f"index.mdx miscounts the packs (now {len(names)})"
    )
    assert f"{_word(len(names)).capitalize()} integrations, {tools} tools" in text, (
        f"index.mdx miscounts coverage (now {len(names)} packs, {tools} tools)"
    )


def test_the_field_split_in_prose_matches_the_egress_map():
    """The 'five fields / withholds nine' claim is the egress map, in words."""
    from charter.packs import gmail

    entry = egress_map([gmail.drafts_create])["gmail_drafts_create"]
    visible, withheld = len(entry["visible"]), len(entry["withheld"])

    claim = f"offers the model {_word(visible)} fields and withholds {_word(withheld)}"
    assert claim in WHY.read_text(), (
        f"why-charter.mdx states a field split the egress map no longer produces "
        f"(now {visible} visible, {withheld} withheld)"
    )


def _quickstart_section(start: str, end: str) -> str:
    text = QUICKSTART.read_text()
    return text[text.index(start) : text.index(end)]


def _indented_blocks(section: str, lang: str) -> list[str]:
    """Fenced blocks of one language in a section, indented or not, in order.

    The "Declare a tool" fences sit inside <Steps>, indented four spaces, so the
    page-level block pattern (which anchors to the line start) does not see
    them. The indent is stripped back off so the source compiles.
    """
    import textwrap

    indented = re.compile(r"^[ \t]*```(\w+)[^\n]*\n(.*?)^[ \t]*```", re.M | re.S)
    return [textwrap.dedent(body) for tag, body in indented.findall(section) if tag == lang]


def _quickstart_declaration() -> list[str]:
    """The python blocks of the quickstart's "Declare a tool" section, in order.

    They are written as four consecutive steps that build on each other, which
    is the thing worth checking: a reader types them in sequence and the
    sequence has to run.
    """
    return _indented_blocks(_quickstart_section("## Declare a tool", "## Break a rule"), "python")


def _httpbin_echo(request: httpx.Request) -> httpx.Response:
    """What httpbin.org/anything answers: the request it received.

    httpbin serialises with sorted keys, so the echoed body is sorted here too;
    the page prints a real run.
    """
    return httpx.Response(
        200,
        json={
            "method": request.method,
            "url": str(request.url),
            "json": dict(sorted(json.loads(request.content).items())),
            "headers": {"Authorization": request.headers.get("authorization")},
        },
    )


def _printed(source: str, namespace: dict) -> str:
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(source, "<quickstart.mdx>", "exec", dont_inherit=True), namespace)  # noqa: S102
    return out.getvalue().strip()


def _run_quickstart() -> tuple[dict, list[tuple[str, str]]]:
    """Run the page top to bottom, as a reader pasting into refund.py would.

    Returns the namespace and, for each block that prints, (what it printed,
    what the page says it prints). httpbin is mocked with an echo; the rules
    and the pin never reach it.
    """
    respx = pytest.importorskip("respx")

    declare = _quickstart_declaration()
    assert len(declare) == 4, f"the section has {len(declare)} python blocks, expected four"
    shown = _indented_blocks(_quickstart_section("## Declare a tool", "## Break a rule"), "text")

    later = []
    for start, end in (
        ("## Break a rule", "## Pin a value"),
        ("## Pin a value", "## Call a pack"),
    ):
        section = _quickstart_section(start, end)
        (code,) = _indented_blocks(section, "python")
        (text,) = _indented_blocks(section, "text")
        later.append((code, text))

    namespace: dict = {"__name__": "__charter_quickstart__"}
    pairs = []
    with respx.mock:
        route = respx.post("https://httpbin.org/anything/v1/refunds").mock(
            side_effect=_httpbin_echo
        )
        for block in declare[:-1]:
            exec(compile(block, "<quickstart.mdx>", "exec", dont_inherit=True), namespace)  # noqa: S102
        pairs.append((_printed(declare[-1], namespace), shown[0].strip()))
        calls_after_the_good_one = route.call_count
        for code, text in later:
            pairs.append((_printed(code, namespace), text.strip()))
        namespace["__calls__"] = (calls_after_the_good_one, route.call_count)
        namespace["__sent__"] = route.calls[0].request
    return namespace, pairs


def test_the_quickstart_prints_what_its_blocks_print():
    """Every output block on the page, against what its code prints.

    The page shows a call echoed back, a refusal, and an egress map, and says
    each is what the code above it prints. Each one is executed here and the
    output compared line for line, so none of them can drift from the package.
    """
    _, pairs = _run_quickstart()
    for printed, shown in pairs:
        assert printed == shown, f"the quickstart shows:\n{shown}\n\nthe code prints:\n{printed}"


def test_the_quickstart_tool_is_declared_by_hand_and_sends_the_key_unseen():
    """ "An API Charter has never seen", and "the model never saw" the key.

    The tool is the reader's own, not a pack, and the key travels in the header
    while the model's schema holds only the four arguments.
    """
    namespace, _ = _run_quickstart()
    tool = namespace["refund"]

    assert tool.pack == "payments" and "payments" not in {
        m.name for m in pkgutil.iter_modules(packs.__path__)
    }, "the quickstart's tool is a shipped pack"
    assert namespace["__sent__"].headers.get("authorization") == "Bearer sk_test_123"
    shown = set(tool.to_json_schema()["parameters"]["properties"])
    assert shown == {"charge", "amount", "reason", "currency"}, shown
    assert "sk_test_123" not in json.dumps(tool.to_json_schema())


def test_the_quickstart_refusal_sends_nothing():
    """ "Nothing was sent": the broken call and the pinned map make no request.

    The only request on the page is the good call in "Call it"; the refusal
    after it must not add one, or "every rule runs before any request" is false.
    """
    namespace, _ = _run_quickstart()
    good, total = namespace["__calls__"]
    assert good == 1, f"the good call made {good} requests"
    assert total == 1, f"the refused call reached the API ({total - good} more requests)"


def test_the_quickstart_rules_are_the_ones_it_names():
    """The note names three rules and a Gloss; each must be on the model.

    `le=10_000` is the $100 cap, the Literal is the allowlist without
    "fraudulent", the validator is the Python check, and the Gloss reaches the
    model's description after the field's own words.
    """
    namespace, _ = _run_quickstart()
    tool = namespace["refund"]
    props = tool.to_json_schema()["parameters"]["properties"]

    assert props["amount"]["maximum"] == 10_000
    assert sorted(props["reason"]["enum"]) == ["duplicate", "requested_by_customer"]
    assert props["amount"]["description"].endswith("Cents, not dollars: $15.00 is 1500.")
    assert "a_charge" in namespace["CreateRefund"].__pydantic_decorators__.field_validators


def test_the_quickstart_points_at_real_endpoints():
    """The hand-declared example has to be an API that exists.

    It used to be a weather service at a hostname nobody owns, which meant the
    one page that says "now do it yourself" ended in a call that could not be
    made. httpbin.org is real and echoes what it receives.
    """
    text = QUICKSTART.read_text()
    assert "example-weather" not in text, "the quickstart points at an invented host"
    assert "https://httpbin.org/anything/" in text


# The setup prompt exists twice: as the string a button copies without showing
# it, and as the block the coding-agents page prints. Hiding one of them behind
# a click is exactly what makes them able to drift unnoticed.
BUTTON = DOCS / "snippets" / "agent-button.mdx"
PROMPT = DOCS / "snippets" / "agent-prompt.mdx"


def _button_prompt() -> str:
    match = re.search(r'data-prompt="([^"]+)"', BUTTON.read_text())
    assert match, "the button snippet no longer declares data-prompt"
    return match.group(1)


def test_the_button_copies_what_the_prompt_page_prints():
    """One string, two surfaces, and only one of them is legible on the page."""
    printed = next(body.strip() for _, _, body in _blocks(PROMPT))

    assert _button_prompt() == printed, (
        "the prompt the index button copies is not the prompt coding-agents shows:\n"
        f"  button: {_button_prompt()}\n"
        f"  page:   {printed}"
    )


def test_the_prompt_points_at_a_file_that_exists():
    """The prompt sends an agent to a URL. A 404 there is a silent dead end."""
    from charter.types.errors import DOCS_BASE

    match = re.search(r"https://\S+", _button_prompt())
    assert match, f"no fetchable URL in the prompt: {_button_prompt()}"
    url = match.group(0)

    assert url.startswith(DOCS_BASE), (
        f"the setup prompt sends the agent outside the documentation site:\n"
        f"  prompt: {url}\n"
        f"  site:   {DOCS_BASE}"
    )

    # What follows DOCS_BASE is the path within this directory. The site is
    # served under a base path, which is a serving prefix rather than a folder
    # anyone can find here, and DOCS_BASE already carries it.
    slug = url[len(DOCS_BASE) :]
    # A page is fetched with `.md` appended, which is Mintlify serving the
    # `.mdx` source as markdown rather than a file sitting at that name.
    candidates = [DOCS / slug]
    if slug.endswith(".md"):
        candidates.append(DOCS / (slug[: -len(".md")] + ".mdx"))
    target = next((c for c in candidates if c.is_file()), candidates[0])
    assert target.is_file(), (
        f"the setup prompt fetches {url}, which no file backs (expected {target.relative_to(ROOT)})"
    )


# --- the pack count, wherever the prose states it ----------------------------
#
# `test_the_pack_counts_in_prose_match_the_package` guards index.mdx, and only
# index.mdx, which is why index.mdx said "fifteen" while four other pages still
# said "twelve" and "eleven". A count is a fact about the package, so every page
# that states it is checked against the package instead of against the front
# page. Claims are listed rather than pattern-matched because "six packs" (the
# Google set) and "four packs added in a single week" are also true sentences
# with a number in front of `packs`.

_TOTAL_CLAIMS = [
    ("start/coding-agents.mdx", "{Word} packs will not cover the API you use."),
    ("start/coding-agents.mdx", "[Packs](/packs/overview), the {word} that ship"),
    ("packs/overview.mdx", "{Word} packs will never cover the API you actually work with."),
    ("packs/overview.mdx", "holds the result to the same rules as the {word} above."),
    ("reference/tool-discovery.mdx", "The {word} shipped packs come to about"),
    ("reference/naming.mdx", "across the {word} shipped packs"),
]


@pytest.mark.parametrize("page,template", _TOTAL_CLAIMS, ids=lambda v: str(v)[:60])
def test_every_page_that_counts_the_packs_counts_them_right(page, template):
    total = len(
        [m.name for m in pkgutil.iter_modules(packs.__path__) if not m.name.startswith("_")]
    )
    word = _word(total)
    claim = template.format(word=word, Word=word.capitalize())
    text = (DOCS / page).read_text()
    assert claim in text, f"{page} does not state the pack count as {total}: expected {claim!r}"


def test_the_schema_total_on_the_discovery_page_is_still_roughly_true():
    """The rounded schema total is the reason `ToolSession` exists.

    Rounded in the prose, so this allows drift and fails on a move that would
    make the sentence misleading — a pack added, or a change to what the runtime
    emits. It was 209,000 for twelve packs and stayed on the page at fifteen,
    where the truth was 510,250; that is the failure this exists to catch.
    """
    from charter import schema_tokens

    names = [m.name for m in pkgutil.iter_modules(packs.__path__) if not m.name.startswith("_")]
    measured = sum(
        schema_tokens(tool)
        for name in names
        for tool in importlib.import_module(f"charter.packs.{name}").TOOLS
    )

    text = (DOCS / "reference/tool-discovery.mdx").read_text()
    stated = re.search(r"shipped packs come to about ([\d,]+) tokens", text)
    assert stated, "the discovery page no longer states a schema total"
    claimed = int(stated.group(1).replace(",", ""))

    assert abs(claimed - measured) / measured < 0.05, (
        f"the discovery page claims {claimed:,} tokens of schema; it is now {measured:,}"
    )
