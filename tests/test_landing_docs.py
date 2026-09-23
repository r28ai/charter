"""The landing page's comparison, checked against the package.

`docs/index.mdx` opens on one Gmail tool shown two ways: declared with Charter
in two numbered steps, and hand-written in six. Almost everything on that page
is a claim about the package that the page itself cannot verify.

The caption says the runtime builds an RFC 2822 document, encodes it base64url,
puts it under the `raw` key and attaches the token. That block is executed here
against a mock transport and the bytes on the wire are compared with the claim,
so the front page cannot advertise behaviour the package does not have.

The step counts are the other half. Each tab numbers its steps in comments, and
a separate `highlight={...}` list decides which lines are painted blue. Those
two live at opposite ends of the same fence and have no way of noticing when
they stop agreeing: insert a line anywhere in the hand-written block and the
highlight silently lands on the wrong rows. So the highlighted lines are
derived from the comments here, the numbering is checked to run 1..N, and the
"two steps against six" in the prose is checked against both.

The rest is the same principle applied to smaller numbers: how many packs
exist, how many tools they carry, which distributions the hand-written version
actually installs.
"""

from __future__ import annotations

import ast
import base64
import importlib
import json
import pkgutil
import re
from pathlib import Path as FsPath

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

# A numbered step comment: `# 1. Build the API client`, at any indent.
_STEP = re.compile(r"^\s*# (\d+)\. ")

WITH = "With Charter"
WITHOUT = "Without Charter"

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


def _tab(path, title: str) -> tuple[str, str]:
    """(meta, body) for the block whose fence carries title="...".

    Mintlify reads a bare trailing word in a fence header as a meta flag, so a
    label with a space in it has to be quoted. That is also what makes the
    label findable from here.
    """
    wanted = f'title="{title}'
    found = [(meta, body) for lang, meta, body in _blocks(path) if wanted in meta]
    assert found, f"{path.name} has no block labelled {title!r}"
    assert len(found) == 1, f"{path.name} has {len(found)} blocks labelled {title!r}"
    return found[0]


def _parse(source: str):
    return compile(
        source, "<docs>", "exec", ast.PyCF_ONLY_AST | _ALLOW_TOP_LEVEL_AWAIT, dont_inherit=True
    )


def _steps(body: str) -> dict[int, int]:
    """{step number: line number} for the numbered comments in a block."""
    out = {}
    for number, line in enumerate(body.strip("\n").split("\n"), start=1):
        match = _STEP.match(line)
        if match:
            out[int(match.group(1))] = number
    return out


def _label(meta: str) -> str:
    """The text inside title="..." on a fence."""
    import re as _re

    match = _re.search(r'title="([^"]*)"', meta)
    assert match, f"no title in fence meta: {meta!r}"
    return match.group(1)


def _highlighted(meta: str) -> list[int]:
    """The line numbers in `highlight={1,17,22}`."""
    match = re.search(r"highlight=\{([^}]*)\}", meta)
    assert match, f"no highlight list in fence meta: {meta!r}"
    return sorted(int(part) for part in match.group(1).split(",") if part.strip())


# --------------------------------------------------------------------------
# The two tabs.
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


@pytest.mark.parametrize("title", [WITH, WITHOUT])
def test_the_blue_lines_are_exactly_the_numbered_steps(title):
    """The highlight list and the step comments have to name the same rows.

    They are declared at opposite ends of the same fence: the numbers in the
    fence header, the comments forty lines down. Insert one line in the middle
    and the highlight lands on whatever now occupies those rows, with nothing
    to complain about it. This is that complaint.
    """
    meta, body = _tab(INDEX, title)
    steps = _steps(body)

    assert steps, f"the {title} block carries no numbered step comments"
    assert _highlighted(meta) == sorted(steps.values()), (
        f"the {title} block highlights {_highlighted(meta)} and its numbered "
        f"comments are on {sorted(steps.values())}"
    )


@pytest.mark.parametrize("title", [WITH, WITHOUT])
def test_the_steps_are_numbered_from_one_without_gaps(title):
    """A block that jumps from 4 to 6 is counting something the reader cannot."""
    _, body = _tab(INDEX, title)
    numbers = sorted(_steps(body))

    assert numbers == list(range(1, len(numbers) + 1)), (
        f"the {title} block numbers its steps {numbers}"
    )


@pytest.mark.parametrize("title", [WITH, WITHOUT])
def test_the_tab_label_counts_the_steps_in_its_own_block(title):
    """The count is on the tab, which is the only thing read before the click.

    It is also the number furthest from the code it describes: the label sits
    in the fence header, the steps are comments in the body, and a reader
    comparing "2 steps" with "6 steps" is taking both entirely on trust.
    """
    meta, body = _tab(INDEX, title)
    steps = len(_steps(body))
    label = _label(meta)

    assert label == f"{title} \u00b7 {steps} steps", (
        f"the tab is labelled {label!r} and its block takes {steps} steps"
    )


def test_the_prose_counts_the_steps_the_blocks_actually_take():
    """ "Two steps against six" is the page's headline claim about itself."""
    declared = len(_steps(_tab(INDEX, WITH)[1]))
    handwritten = len(_steps(_tab(INDEX, WITHOUT)[1]))

    claim = f"{_word(declared).capitalize()} steps against {_word(handwritten)}"
    assert claim in INDEX.read_text(), (
        f"index.mdx no longer says {claim!r}; the tabs now take {declared} steps and {handwritten}"
    )


# Import root -> the thing you would pip install to get it.
_DISTRIBUTIONS = {
    "google": "google-auth",
    "google_auth_oauthlib": "google-auth-oauthlib",
    "googleapiclient": "google-api-python-client",
}


def _distributions_of(body: str) -> set[str]:
    """Which pip distributions a block's imports come from.

    `google.auth` and `google.oauth2` are two imports and one install, which is
    exactly the sort of thing a hand-counted list gets wrong.
    """
    stdlib = {"base64", "os", "email", "typing"}

    roots = set()
    for node in ast.walk(_parse(body)):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])

    third_party = roots - stdlib
    unknown = third_party - set(_DISTRIBUTIONS)
    assert not unknown, f"the block imports {sorted(unknown)}, which maps to no distribution"
    return {_DISTRIBUTIONS[root] for root in third_party}


def test_the_caption_counts_the_installs_each_side_needs():
    """ "One package to install against three" is the caption's other number.

    The three are derived from what the hand-written block imports. The one is
    charter, and it is only one because pydantic arrives as its dependency
    rather than as something the reader installs, so that is what is checked.
    """
    try:
        import tomllib
    except ModuleNotFoundError:  # 3.10 predates tomllib
        import tomli as tomllib

    handwritten = len(_distributions_of(_tab(INDEX, WITHOUT)[1]))
    claim = f"one package to install against {_word(handwritten)}"
    assert claim in INDEX.read_text(), (
        f"index.mdx no longer says {claim!r}; the hand-written tab now installs {handwritten}"
    )

    requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    names = {re.split(r"[<>=!\[]", spec)[0].strip() for spec in requires}
    assert "pydantic" in names, (
        "index.mdx counts the Charter side as one install because charter brings "
        f"pydantic with it, and charter now requires {sorted(names)}"
    )


def test_the_hand_written_tab_names_the_packages_it_imports():
    """Step one lists three distributions, and the block imports from three.

    `google.auth` and `google.oauth2` are two imports and one install, which is
    exactly the kind of thing a hand-counted list gets wrong.
    """
    _, body = _tab(INDEX, WITHOUT)
    imported = _distributions_of(body)
    first_step = body.strip("\n").split("\n")[_steps(body)[1] - 1]
    named = {name for name in _DISTRIBUTIONS.values() if name in first_step}

    assert named == imported, (
        f"step one names {sorted(named)} and the block imports from {sorted(imported)}"
    )


def _build(monkeypatch):
    """Execute the Charter tab and hand back the tool it declares.

    `dont_inherit`, because this module reads annotations as strings and the
    block must not: pydantic needs the real `Annotated` objects to see the
    markers on a class declared outside any importable module.
    """
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "at-for-the-docs")
    tree = _parse(_tab(INDEX, WITH)[1])
    # The trailing call is the last statement; everything before it builds.
    declaration = ast.unparse(ast.Module(body=tree.body[:-1], type_ignores=[]))
    namespace: dict = {"__name__": "__charter_landing__"}
    exec(compile(declaration, "<index.mdx>", "exec", dont_inherit=True), namespace)  # noqa: S102
    return namespace["send_email"]


def test_the_charter_tab_sends_what_the_caption_says_it_sends(monkeypatch):
    """The caption's claims, checked against the bytes on the wire.

    This is also the test that would have caught the shape this block nearly
    shipped with. A single `Body()` field unwraps to its bare value, which sends
    the base64 string as the whole JSON body and never produces `{"raw": ...}`
    at all. `Body(envelop=True)` is what keeps the key, and nothing short of
    inspecting the request distinguishes the two.
    """
    respx = pytest.importorskip("respx")
    import asyncio

    import httpx

    tool = _build(monkeypatch)
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

    async def call():
        with respx.mock:
            route = respx.post(url).mock(return_value=httpx.Response(200, json={"id": "18f"}))
            await tool.ainvoke(raw={"to": "ada@example.com", "subject": "Hi", "body": "Hello"})
            return route.calls[0].request

    request = asyncio.run(call())

    assert str(request.url) == url
    assert request.headers.get("authorization") == "Bearer at-for-the-docs"

    payload = json.loads(request.content)
    assert list(payload) == ["raw"], (
        "index.mdx says the runtime puts the message under the `raw` key, and "
        f"the request body is {str(payload)[:80]}"
    )

    raw = payload["raw"]
    assert re.fullmatch(r"[A-Za-z0-9_-]+=*", raw), "the `raw` value is not base64url"
    document = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode()
    assert "To: ada@example.com" in document
    assert "Subject: Hi" in document
    assert "MIME-Version: 1.0" in document


def test_the_charter_tab_shows_the_model_only_the_email(monkeypatch):
    """ "The model fills `to`, `subject` and `body`" is an egress claim."""
    parameters = _build(monkeypatch).to_json_schema()["parameters"]

    assert list(parameters["properties"]) == ["raw"]
    # `raw` reaches the model as a reference into $defs, so the fields it
    # actually offers are one hop away.
    fields = set(parameters["$defs"]["EmailContent"]["properties"])
    assert {"to", "subject", "body"} <= fields, (
        f"index.mdx names to, subject and body; the model is shown {sorted(fields)}"
    )
    assert not fields & {"id", "threadId", "snippet", "payload", "labelIds"}, (
        f"a response-only Gmail field reached the model's schema: {sorted(fields)}"
    )


def test_both_tabs_end_by_passing_the_same_dict_to_the_tool():
    """Each side declares a tool and then calls it with the identical payload.

    The Charter tab once ended in an `ainvoke` while the hand-written one
    stopped at the function definition, which quietly rigged the comparison:
    one side was paying for a call the other never made.

    They now differ by one token, `raw=` against `**`, and that is the point.
    The same JSON goes into both, so what the page is comparing is the plumbing
    on either side of it and nothing else. This asserts the two dictionaries
    are equal rather than merely similar, because "the model fills to, subject
    and body either way" is only true if they are.
    """
    payloads = {}
    for title in (WITH, WITHOUT):
        body = _tab(INDEX, title)[1]
        last = _parse(body).body[-1]

        assert isinstance(last, ast.Expr), (
            f"the {title} block ends on a {type(last).__name__}, not a call"
        )
        call = last.value.value if isinstance(last.value, ast.Await) else last.value
        assert isinstance(call, ast.Call), f"the {title} block does not end by calling anything"

        dicts = [node for node in ast.walk(call) if isinstance(node, ast.Dict)]
        assert len(dicts) == 1, (
            f"the {title} block's final call passes {len(dicts)} dicts, and the "
            f"page shows one payload going into both tabs"
        )
        payloads[title] = ast.literal_eval(dicts[0])

    assert payloads[WITH] == payloads[WITHOUT], (
        f"the two tabs send different payloads:\n"
        f"  {WITH}: {payloads[WITH]}\n  {WITHOUT}: {payloads[WITHOUT]}"
    )
    assert set(payloads[WITH]) == {"to", "subject", "body"}, (
        f"the caption names to, subject and body; the call sends {sorted(payloads[WITH])}"
    )


def test_both_tabs_call_the_same_endpoint(monkeypatch):
    """The comparison is only a comparison if it is one tool shown twice."""
    from charter.packs import gmail

    tool = _build(monkeypatch)
    _, handwritten = _tab(INDEX, WITHOUT)

    assert tool.method == "POST"
    assert tool.url_template == "gmail/v1/users/me/messages/send"
    assert '.send(userId="me"' in handwritten, (
        "the hand-written tab no longer calls users.messages.send"
    )
    # And the same endpoint the pack ships, so the front page is not declaring
    # a tool that exists nowhere else on the site.
    assert re.sub(r"\{[^}]+\}", "me", gmail.messages_send.url_template) == tool.url_template


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

    entry = egress_map([gmail.drafts_create])["gmail__drafts_create"]
    visible, withheld = len(entry["visible"]), len(entry["withheld"])

    claim = f"offers the model {_word(visible)} fields and withholds {_word(withheld)}"
    assert claim in WHY.read_text(), (
        f"why-charter.mdx states a field split the egress map no longer produces "
        f"(now {visible} visible, {withheld} withheld)"
    )


def test_why_charter_describes_the_comparison_the_index_actually_shows():
    """That page opens by telling the reader what is on the front page.

    It is the one sentence on the site that goes stale when the landing page's
    example changes, and it has nothing to do with the package, so no other
    test would notice.
    """
    _, handwritten = _tab(INDEX, WITHOUT)
    text = WHY.read_text()

    assert "`users.messages.send`" in text, (
        "why-charter.mdx names a different endpoint than the front page's "
        "hand-written tab, which calls users.messages.send"
    )
    assert "declared with Charter" in text
    assert "users.drafts.create" not in text, (
        "why-charter.mdx still points at the drafts example the index dropped"
    )
    assert "InstalledAppFlow" in handwritten, (
        "why-charter.mdx calls the front page's example Google's documented one; "
        "the hand-written tab no longer contains their auth quickstart"
    )


def _quickstart_declaration() -> list[str]:
    """The python blocks of the quickstart's "Declare a tool" section, in order.

    They are written as four consecutive steps that build on each other, which
    is the thing worth checking: a reader types them in sequence and the
    sequence has to run.
    """
    import textwrap

    text = QUICKSTART.read_text()
    section = text[text.index("## Declare a tool") : text.index("## See what the model sees")]
    # These fences sit inside <Steps>, indented four spaces, so the page-level
    # block pattern (which anchors to the line start) does not see them. The
    # indent is stripped back off so the source compiles.
    indented = re.compile(r"^[ \t]*```(\w+)[^\n]*\n(.*?)^[ \t]*```", re.M | re.S)
    return [textwrap.dedent(body) for lang, body in indented.findall(section) if lang == "python"]


def test_the_quickstart_steps_build_a_tool_that_sends_what_it_claims():
    """The four steps are executed in order and the request is inspected.

    The section states the exact query string it produces, including the
    camelCase spelling the factory applies. That claim is the reason the
    section chose this endpoint, and it is invisible in the Python: nothing in
    `max_results: Annotated[int, Query()]` says the wire will read
    `maxResults`. Only the request shows it.
    """
    respx = pytest.importorskip("respx")
    import asyncio

    import httpx

    blocks = _quickstart_declaration()
    assert len(blocks) == 4, f"the section has {len(blocks)} python blocks, expected four"

    namespace: dict = {"__name__": "__charter_quickstart__"}
    import os

    os.environ["GOOGLE_ACCESS_TOKEN"] = "at-for-the-docs"
    for block in blocks[:-1]:
        exec(compile(block, "<quickstart.mdx>", "exec", dont_inherit=True), namespace)  # noqa: S102

    tool = namespace["list_messages"]

    # The arguments come out of the page's own final block rather than being
    # retyped here, so the request under test is the one a reader would make.
    (payload_node,) = [node for node in ast.walk(_parse(blocks[-1])) if isinstance(node, ast.Dict)]
    payload = ast.literal_eval(payload_node)

    # The call is written as a dict keyed the way a model would emit it, so
    # every key in it has to be a field the model is actually shown. This is
    # what catches the page drifting to a Python spelling: `max_results` is the
    # field name in the class and is not what the schema offers.
    shown = set(tool.to_json_schema()["parameters"]["properties"])
    assert set(payload) <= shown, (
        f"the quickstart calls with {sorted(payload)}, and the model is shown {sorted(shown)}"
    )

    async def call():
        with respx.mock:
            route = respx.get(url__startswith="https://gmail.googleapis.com/").mock(
                return_value=httpx.Response(200, json={"messages": []})
            )
            await tool.ainvoke(payload)
            return route.calls[0].request

    request = asyncio.run(call())
    query = request.url.query.decode()

    assert request.url.path == "/gmail/v1/users/me/messages"
    assert request.headers.get("authorization") == "Bearer at-for-the-docs"
    assert "maxResults=5" in query, (
        f"the quickstart says the runtime sends maxResults; the query was {query!r}"
    )
    assert "max_results" not in query, (
        f"the snake_case name reached the wire, so query_case is not applying: {query!r}"
    )
    assert (
        f"?{query}" in QUICKSTART.read_text() or query.replace("%3A", ":") in QUICKSTART.read_text()
    ), f"the quickstart prints a query string the tool does not produce (now {query!r})"


def test_the_quickstart_declares_a_subset_of_what_the_gmail_pack_declares():
    """ "Every pack is built from declarations like this one", made checkable.

    The section writes `messages_list` out by hand. Every field it declares
    should be one the shipped pack declares too, carrying the same marker,
    otherwise the sentence introducing it is decorative.
    """
    from charter.packs import gmail

    blocks = _quickstart_declaration()
    namespace: dict = {"__name__": "__charter_quickstart_schema__"}
    exec(compile(blocks[0], "<quickstart.mdx>", "exec", dont_inherit=True), namespace)  # noqa: S102

    def markers(model):
        return {
            re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower(): sorted(
                repr(m) for m in info.metadata if type(m).__module__.startswith("charter")
            )
            for name, info in model.model_fields.items()
        }

    declared = markers(namespace["ListMessages"])
    packed = markers(gmail.messages_list.args_schema)

    assert declared, "the quickstart's schema declares no fields"
    for field, marks in declared.items():
        assert field in packed, (
            f"the quickstart declares {field}, which charter.packs.gmail.messages_list does not"
        )
        assert marks == packed[field], (
            f"the quickstart marks {field} as {marks} and the pack marks it {packed[field]}"
        )


def test_the_quickstart_points_at_real_endpoints():
    """The hand-declared example has to be an API that exists.

    It used to be a weather service at a hostname nobody owns, which meant the
    one page that says "now do it yourself" ended in a call that could not be
    made. It was also one of the shipped packs, so the section's own premise
    was wrong.
    """
    text = QUICKSTART.read_text()
    assert "example-weather" not in text, "the quickstart points at an invented host"
    assert "gmail.googleapis.com" in text
    assert "gmail/v1/users/me/messages" in text


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


def test_the_markers_named_on_the_landing_page_are_the_ones_gmail_declares():
    """Every marker the front page names is one the Gmail pack still uses."""
    import charter.packs.gmail as gmail_pack

    source = "\n".join(p.read_text() for p in FsPath(gmail_pack.__file__).parent.rglob("*.py"))
    for marker in ('Format("rfc822_base64")', 'Mode("response_only")'):
        assert marker in source, (
            f"the docs name {marker} as part of the Gmail declaration, "
            f"which the pack no longer contains"
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


def test_the_quickstart_prints_the_egress_map_the_runtime_prints():
    """The sample output under "See what the model sees", against the real thing.

    The page's whole claim for that block is that it "cannot drift from what
    actually happens", which was not true of the block itself: it showed four
    visible fields and a withheld list in an order `format_egress_map` does not
    produce, against fifteen and eight in reality. Every line shown is checked,
    in order, and the counts are read out of the heading rather than assumed.
    """
    from charter import format_egress_map
    from charter.packs import gmail

    actual = format_egress_map([gmail.messages_send]).splitlines()
    page = (DOCS / "start/quickstart.mdx").read_text()

    block = re.search(r"```text\n(gmail__messages_send.*?)```", page, re.S)
    assert block, "the quickstart no longer prints an egress map"
    shown = [line for line in block.group(1).splitlines() if line.strip()]

    # Every line the page shows, except its own elisions, must appear in the
    # real output in the same order.
    cursor = 0
    for line in shown:
        if line.strip() == "...":
            continue
        assert line in actual[cursor:], f"quickstart prints a line the runtime does not: {line!r}"
        cursor = actual.index(line, cursor) + 1

    visible = len([line for line in actual if line.strip().startswith("+")])
    withheld = len([line for line in actual if line.strip().startswith("-")])
    assert f"visible to the model ({visible}):" in page
    assert f"withheld ({withheld}):" in page
    assert f"Eleven of the {_word(visible)}" in page, (
        f"the prose under the block miscounts the visible fields (now {visible})"
    )
