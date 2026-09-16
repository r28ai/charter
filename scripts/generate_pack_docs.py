#!/usr/bin/env python
"""Regenerate the introspected blocks in ``docs/packs/<pack>.mdx``.

Every fact a pack reference page needs — the tool list, the HTTP method, what
each tool does, the base URL, the body format, the envelope, the pagination
style — is already on the ``Tool`` objects the pack exports.
Writing those out by hand produces a page that is correct on the day it is written and
wrong on the day someone adds a tool.

So each page carries three generated regions, delimited by MDX comments:

    {/* generated:summary start ... */} the tool count, auth style and import
    {/* generated:tools start ... */}   the tool list
    {/* generated:auth start ... */}    where to get a credential
    {/* generated:wire start ... */}    the pack's wire declarations

Everything outside the markers is hand-written prose and is preserved verbatim.
``tests/test_pack_docs.py`` asserts that what is inside them equals what this
script would produce right now, so a pack added next year either shows up in the
docs or turns the suite red.

Usage::

    uv run python scripts/generate_pack_docs.py            # rewrite the pages
    uv run python scripts/generate_pack_docs.py --check     # exit 1 if stale
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from charter.mcp import PACKS
from charter.tool import Tool
from charter.types.envelope import Envelope
from charter.types.pagination import Pagination

ROOT = Path(__file__).resolve().parent.parent
PACK_DOCS = ROOT / "docs" / "packs"

_SCRIPT = "scripts/generate_pack_docs.py"

# Where a tool's generated page lands, which depends on whether the pack has
# more than one category. Imported rather than reconstructed so that the pack
# page and the pages it links to cannot disagree about a path. The sibling is
# reachable when this runs as a script; it is put on the path for the tests,
# which load both generators by file location.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_pack_specs import categorised, category_title, tool_page_path  # noqa: E402

# -----------------------------------------------------
# Markers
# -----------------------------------------------------


def start_marker(block: str) -> str:
    return f"{{/* generated:{block} start — do not edit by hand; run {_SCRIPT} */}}"


def end_marker(block: str) -> str:
    return f"{{/* generated:{block} end */}}"


def _region(block: str) -> re.Pattern[str]:
    return re.compile(
        f"{re.escape(start_marker(block))}\n(.*?)\n{re.escape(end_marker(block))}",
        re.S,
    )


def wrap(block: str, body: str) -> str:
    return f"{start_marker(block)}\n{body}\n{end_marker(block)}"


def extract(text: str, block: str) -> Optional[str]:
    """The current contents of one generated region, or ``None`` if absent."""
    found = _region(block).search(text)
    return found.group(1) if found else None


def replace(text: str, block: str, body: str) -> str:
    """Swap one generated region's contents, leaving the prose around it alone."""
    if not _region(block).search(text):
        raise SystemExit(
            f"no '{block}' region found — the page needs "
            f"{start_marker(block)} ... {end_marker(block)}"
        )
    return _region(block).sub(lambda _: wrap(block, body), text, count=1)


# -----------------------------------------------------
# Rendering helpers
# -----------------------------------------------------


def _cell(value: str) -> str:
    """A pipe inside a cell would split the column."""
    return value.replace("|", "\\|")


def _code(value: Any) -> str:
    return f"`{_cell(str(value))}`"


def _joined_plain(names: Sequence[str]) -> str:
    """``a, b and c`` — for a comment, where backticks would be literal."""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def _joined(names: Sequence[str]) -> str:
    """``a``, ``b`` and ``c`` — a list read as a sentence, not as a CSV."""
    if len(names) == 1:
        return _code(names[0])
    return ", ".join(_code(name) for name in names[:-1]) + f" and {_code(names[-1])}"


def _uniform(tools: Sequence[Tool], read: Callable[[Tool], Any]) -> Any:
    """One tool's value when the whole pack agrees, else ``_VARIES``."""
    values = [read(tool) for tool in tools]
    first = values[0]
    return first if all(value == first for value in values[1:]) else _VARIES


_VARIES = object()


def _varies(value: Any) -> bool:
    return value is _VARIES


def _dominant(
    tools: Sequence[Tool], read: Callable[[Tool], Any]
) -> Tuple[Any, List[str]]:
    """The value nearly every tool shares, and the tools that depart from it.

    ``_uniform`` answers "the pack agrees" or "it varies", which is the right
    pair for most packs and the wrong one for a pack with a deliberate
    exception. GitHub sends 138 of its 139 tools to ``api.github.com`` and the
    other to ``uploads.github.com``, because that is where GitHub serves an
    upload; collapsing that to ``base_url=...  # varies by tool`` loses the
    host *and* the exception, and documents neither.

    Returns ``(_VARIES, [])`` when there is no majority worth naming — more than
    a quarter of the pack departing is not an exception, it is a pack that
    genuinely varies.
    """
    values = [(tool.name, read(tool)) for tool in tools]
    counts: List[Tuple[Any, int]] = []
    for _, value in values:
        for index, (seen, count) in enumerate(counts):
            if seen == value:
                counts[index] = (seen, count + 1)
                break
        else:
            counts.append((value, 1))

    winner, hits = max(counts, key=lambda pair: pair[1])
    if hits == len(values):
        return winner, []
    if hits * 4 < len(values) * 3:
        return _VARIES, []
    return winner, [name for name, value in values if value != winner]


# -----------------------------------------------------
# The summary strip
# -----------------------------------------------------


# The glyph on each pill, as Lucide path data. Only the shape is here — size,
# stroke and color are one rule in docs/custom.css, so the generated markup stays
# a single line per pill and every pill is restyled in one place.
_ICON_TOOLS = (
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1'
    "-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 "
    '3.76z" />'
)
_ICON_OAUTH = (
    '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 '
    "1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 "
    '1 0 0 1 1 1z" />'
)
_ICON_API_KEY = (
    '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4" />'
    '<path d="m21 2-9.6 9.6" />'
    '<circle cx="7.5" cy="15.5" r="5.5" />'
)


def _render_auth_short(tool: Tool) -> Tuple[str, str]:
    """The two words a reader is scanning for, and the glyph that carries them.

    The packs declare one OAuth flavour — a bearer token from a credential
    provider — so the split a reader has to make is OAuth against API key, and
    two glyphs cover it. A pack that authenticates some third way would need a
    third here rather than falling into one of these.
    """
    if tool.credential_provider is not None:
        return _ICON_OAUTH, "OAuth bearer"
    return _ICON_API_KEY, "API key"


def _pill(icon: str, label: str) -> str:
    return f'  <span><svg viewBox="0 0 24 24">{icon}</svg>{label}</span>'


def render_summary(pack: str, module: ModuleType) -> str:
    """How many tools, and what credential they want. Nothing else.

    The wire block below answers everything; it is also forty lines down. These
    are the two facts a reader decides on before reading anything, so they go
    above the fold and are counted from the pack rather than typed. The import
    path is not here because the snippet underneath already shows it.
    """
    tools: List[Tool] = list(module.TOOLS)
    count = f"{len(tools)} tool" + ("s" if len(tools) != 1 else "")
    pills = [
        _pill(_ICON_TOOLS, count),
        _pill(*_render_auth_short(tools[0])),
    ]
    return '<div className="pack-summary">\n' + "\n".join(pills) + "\n</div>"


# -----------------------------------------------------
# The tool list
# -----------------------------------------------------


def _jsx_text(value: str) -> str:
    """Prose bound for a JSX child, with the four characters MDX would eat.

    A brace opens an expression and an angle bracket opens a tag, so both are
    entities here; ``&`` goes first or it would re-escape the entities that
    follow it.
    """
    for char, entity in (
        ("&", "&amp;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ("{", "&#123;"),
        ("}", "&#125;"),
    ):
        value = value.replace(char, entity)
    return value


_BACKTICKED = re.compile(r"`([^`]+)`")


def _inline_code(value: str) -> str:
    """``a `field` name`` as prose is markdown; inside JSX it has to be a tag."""
    return _BACKTICKED.sub(lambda m: f"<code>{m.group(1)}</code>", _jsx_text(value))


_SENTENCE_BREAK = re.compile(r"(?<!\.)\.\s+(?=[A-Z`])")


def _first_sentence(text: str) -> str:
    """The opening sentence, which is the summary of what the tool does.

    A tool's description is written for a model, so after the first sentence it
    becomes usage guidance — when to prefer this tool over that one, which field
    replaces rather than appends. That belongs on the tool's own page; an index
    wants the one line. The break needs a period followed by a capital or a
    backtick, which leaves ``e.g. 'repo:owner/name'`` and
    ``gid://shopify/Order/...`` intact.
    """
    found = _SENTENCE_BREAK.search(text)
    return text[: found.start() + 1] if found else text


def render_tools(pack: str, module: ModuleType) -> str:
    """One entry per exported tool: name, method, and what it does.

    A flat list rather than a table. The method is the pill the sidebar already
    puts beside every tool, in the same colors, so the two readings of the same
    list agree. The URL template and the quota cost are not here — a path is
    forty characters of near-identical prefix repeated down a column, and both
    facts are stated on the tool's own page, which is what the name links to.

    Under the same headings as the sidebar, where the pack has more than one
    category, and for the same reason: a reader who scanned the sidebar for
    ``events`` should not have to find it again in a list ordered differently.
    """
    tools: List[Tool] = list(module.TOOLS)

    entries = []
    for slug, category_tools in categorised(pack, tools):
        if slug is not None:
            entries.append(
                f'  <span className="tool-list-group">{category_title(pack, slug)}</span>'
            )
        entries.extend(_tool_rows(pack, category_tools))
    return '<div className="tool-list">\n' + "\n".join(entries) + "\n</div>"


def _tool_rows(pack: str, tools: Sequence[Tool]) -> List[str]:
    entries = []
    for tool in tools:
        href = tool_page_path(pack, tool)
        method = _jsx_text(tool.method)
        summary = _inline_code(_first_sentence(tool.description or ""))
        entries.append(
            f'  <a className="tool-row" href="{href}">\n'
            f'    <span className="tool-row-head">'
            f'<span className="tool-row-name">{_jsx_text(tool.name)}</span>'
            f'<span className="tool-row-method" data-method="{method}">{method}</span>'
            f"</span>\n"
            f'    <span className="tool-row-desc">{summary}</span>\n'
            f"  </a>"
        )
    return entries


# -----------------------------------------------------
# The auth signpost
# -----------------------------------------------------


# The three authorization servers the OAuth packs use, each with a page that
# holds its constant, its scopes and its silent failures. A pack whose provider
# is not here still gets the rest of the signpost; it just has nowhere specific
# to send a reader for the server itself.
_PROVIDER_PAGES = {
    "google": ("Google", "/auth/providers/google"),
    "slack": ("Slack", "/auth/providers/slack"),
    "github": ("GitHub", "/auth/providers/github"),
}


def _render_credential_source(module: ModuleType, tool: Tool) -> str:
    """The clause naming what a reader can set instead of calling ``configure()``.

    Only for a pack whose ``configure()`` takes one thing. Shopify takes two — a
    store as well as a token — and "optional when ``$SHOPIFY_ACCESS_TOKEN`` is
    set" would be a false completeness claim, so a multi-value pack gets no
    clause here and its own prose says what it needs.
    """
    holder = tool.credential_provider or tool.api_key_headers
    env_var = getattr(holder, "env_var", None)
    if not env_var or len(inspect.signature(module.configure).parameters) != 1:
        return ""
    return (
        f", and {_CONFIGURE} is optional when {_code('$' + env_var)} is set"
    )


# A name set in code type is a name a reader may want to look up, so every one
# of them in this file's prose is a link to its own reference anchor. These are
# the ones that recur.
_CONFIGURE = "[`configure()`](/reference/configuration#configure)"
_STATIC = "[`StaticTokenProvider`](/reference/credentials#statictokenprovider)"
_ENV = "[`EnvTokenProvider`](/reference/credentials#envtokenprovider)"
_CLIENT = "[`OAuth2Client`](/reference/oauth#oauth2client)"
_SUBJECT = "[`SubjectProvider`](/reference/credentials#subjectprovider)"
_USE_SUBJECT = "[`use_subject`](/reference/credentials#use_subject)"


def _fence(title: str, lines: Sequence[str], marked: Sequence[str]) -> List[str]:
    """One tab of the credential group, with its point highlighted.

    The tabs are read against each other, and what differs between them is one
    line each: the object handed to ``configure()``, or the value you had to
    supply to build it. Mintlify highlights lines by number, and a number typed
    beside a snippet is a number that goes stale the first time somebody adds an
    import — so the lines are named here by a substring and counted at
    generation time. A needle that stops matching, or starts matching twice,
    fails the run rather than quietly highlighting the wrong line.
    """
    numbers = []
    for needle in marked:
        found = [n for n, line in enumerate(lines, 1) if needle in line]
        if len(found) != 1:
            raise SystemExit(
                f"{title!r}: {needle!r} matches {len(found)} lines, expected 1"
            )
        numbers.append(found[0])
    ranges = ",".join(str(number) for number in sorted(numbers))
    return [f"```python {title} {{{ranges}}}", *lines, "```", ""]


def _credential_shapes(pack: str, provider: str, env_var: str, page: Optional[str]) -> str:
    """Three sections: the same pack, configured for three deployments.

    This is the one place the pack pages used to lie by omission. Every snippet
    on the page handed ``configure()`` a token somebody already had, which is the
    throwaway path, documented two pages away as the one that expires in an hour
    with no way to renew it. A reader had no way to tell from here that the other
    two existed.

    These were a ``CodeGroup`` first, on the argument that tabs hold the
    comparison still: the imports, the tools and the wire contract are identical
    across all three, and only the object handed to ``configure()`` moves. That
    argument is right about the code and wrong about the reader. Tabs are for a
    choice already made — the reader who knows they write Python and wants the
    Python tab — and this is a choice the reader arrives without. Two of the
    three were hidden behind a label, the section had no way to say who each one
    was for without repeating itself above the group, and none of them could be
    linked to or found with ctrl-F.

    So: a heading each, in increasing order of commitment, each with the one
    line that decides it. The headings land in the page's table of contents,
    which is where a reader scanning for their own case looks first.

    The third is longer than the other two on purpose. ``SubjectProvider`` is the
    only one whose argument is a function the reader writes, and the only one
    that needs a second call at request time, so a snippet showing
    ``SubjectProvider(for_user)`` and nothing else left both facts unstated: what
    ``for_user`` receives, what it returns, and where the subject it is called
    with comes from.

    The filenames say where the code lives: a script, an agent on your own
    account, a server serving your users. That is the fact the heading has no
    room for, and outside a ``CodeGroup`` it is what a code block's title is for.
    """
    constant = provider.upper()

    # Every shape binds the same name, and hands that name to `configure()`.
    # It is the object the section under this one asks for by name: a client the
    # pack did not build takes it as `credential_provider`, and a reader who has
    # seen it assigned three times here knows what is being asked for.
    hold = [
        "from charter.auth import EnvTokenProvider",
        f"from charter.packs import {pack}",
        "",
        f'{_CREDENTIAL} = EnvTokenProvider("{env_var}")',
        f"{pack}.configure({_CREDENTIAL})",
    ]
    refreshed = [
        "from charter.auth import OAuth2Client",
        f"from charter.packs import {pack}",
        "",
        f"{_CREDENTIAL} = OAuth2Client(",
        f"    {constant},",
        f'    client_id=os.environ["{constant}_CLIENT_ID"],',
        f'    client_secret=os.environ["{constant}_CLIENT_SECRET"],',
        f'    refresh_token=os.environ["{constant}_REFRESH_TOKEN"],',
        ")",
        f"{pack}.configure({_CREDENTIAL})",
    ]
    many = [
        "from functools import partial",
        "",
        "from charter.auth import OAuth2Client, SubjectProvider, use_subject",
        f"from charter.packs import {pack}",
        "",
        "# Yours to write: a user id in, that user's credential out.",
        "async def for_user(user_id: str) -> OAuth2Client:",
        f'    grant = await db.grants.get(user_id, "{provider}")',
        "    return OAuth2Client(",
        f"        {constant},",
        f'        client_id=os.environ["{constant}_CLIENT_ID"],',
        f'        client_secret=os.environ["{constant}_CLIENT_SECRET"],',
        "        refresh_token=grant.refresh_token,",
        "        on_refresh=partial(save_to_db, user_id),",
        "    )",
        "",
        f"{_CREDENTIAL} = SubjectProvider(for_user)",
        f"{pack}.configure({_CREDENTIAL})",
        "",
        "# Per request: whose grant the tools use.",
        "with use_subject(request.user_id):",
        "    ...  # your agent runs here",
    ]

    body: List[str] = []

    body += [
        "### A token you hold",
        "",
        f"For a script, or a notebook. {_ENV} re-reads the variable on every"
        " call, so a token rotated beside the process is picked up without a"
        f" restart; {_STATIC} takes one you already hold as a string. Neither"
        " renews anything, so the calls stop when the token expires.",
        "",
    ]
    body += _fence(f"{pack}_script.py", hold, [f"{_CREDENTIAL} = EnvTokenProvider("])

    body += [
        "### One account, refreshed",
        "",
        f"For an agent or a server acting as you. {_CLIENT} turns a client"
        " registration and a stored refresh token into an access token, and"
        " [renews it](/auth/authorization-servers#what-the-cache-does-precisely)"
        " before it lapses.",
        "",
    ]
    body += _fence(f"{pack}_agent.py", refreshed, ["_REFRESH_TOKEN"])

    # The question this shape raises the moment the code makes sense: the
    # snippet reads a refresh token out of the environment and says nothing
    # about how it got there. It goes under the snippet rather than in the
    # sentence above it, because that is where the reader thinks to ask.
    # The question this shape raises the moment the code makes sense: the
    # snippet reads a refresh token out of the environment and says nothing
    # about how it got there. Every OAuth pack owes the reader an answer, so
    # there is no branch where the note is simply absent.
    #
    # Google's walkthrough is written for Google, console and all, so a Google
    # pack sends the reader straight there; Slack and GitHub differ in exactly
    # the places that page says they differ, so theirs go to their own server's
    # section, which carries their code. A server with no page of its own gets
    # the general walkthrough, which is the one that generalises.
    if page and page != "/auth/providers/google":
        where = f"[Getting the first grant]({page}#getting-the-first-grant)"
    else:
        where = "[Your own account](/auth/your-own-account)"
    body += [
        "<Note>",
        f"No refresh token yet? {where} is the one-time consent flow that"
        " hands you one.",
        "</Note>",
        "",
    ]

    body += [
        "### Many end users",
        "",
        f"For a product whose users each connect their own account. {_SUBJECT}"
        " builds one credential per user through a factory you write, and"
        f" {_USE_SUBJECT} names the user a call acts for."
        " [Your users' accounts](/auth/oauth-flow) is the consent route inside"
        " your app;"
        " [serving many users](/auth/authorization-servers#serving-many-users)"
        " is the per-subject cache and its eviction.",
        "",
    ]
    body += _fence(
        f"{pack}_server.py",
        many,
        [f"{_CREDENTIAL} = SubjectProvider(", "with use_subject("],
    )

    return "\n".join(body).rstrip()


def render_auth(pack: str, module: ModuleType) -> str:
    """What credential this pack takes, in what shapes, and where to get one.

    Not a second copy of the wire block: the declarations tab already shows the
    provider, the scopes and the environment variable in the code that uses
    them. This section answers the two things that code cannot — which
    credential object suits the way you are deploying, and how you obtain one in
    the first place.

    An API-key pack gets told it is finished instead. It has one shape, and the
    whole OAuth apparatus below is machinery it never touches.
    """
    tools: List[Tool] = list(module.TOOLS)
    first = tools[0]
    source = _render_credential_source(module, first)

    if first.credential_provider is None:
        header = getattr(first.api_key_headers, "key_header", None)
        sent = f" in {_code(header)}" if header else ""
        return (
            f"This pack takes an API key{sent}{source}.\n"
            "\n"
            "There is no authorization server, no consent screen and no refresh — "
            "[API keys](/auth/api-key-tool-factory) is the whole story."
        )

    named = _PROVIDER_PAGES.get(first.provider or "")
    server = f"{named[0]} " if named else ""
    lines = [
        f"This pack takes {'a ' + server if server else 'an '}OAuth bearer token{source}."
        " Which credential provider you hand it depends on whose account the"
        " calls run as.",
    ]
    if named:
        # The question the snippets raise and cannot answer: two of the three
        # name a constant that is defined nowhere on this page, and a reader who
        # copies one hits it immediately. Answering it is what earns the
        # provider page its link, so the link rides on the answer.
        #
        # Above the sections rather than under them. A reader lands on this
        # heading, reads the lead, and jumps to their own case, so the lead is
        # the only place every path goes through: under the second shape this is
        # invisible to anyone who takes the third, and under the third it is
        # invisible to anyone who stops at the second. It also keeps the three
        # sections parallel — heading, one line, code — with no box between two
        # of them making the third look subordinate.
        #
        # One link and no symbol in it. Naming the constant as `GOOGLE` said
        # "Google" twice and put reference styling on a link to a guide page;
        # naming its class instead introduced a type the reader has not met, in
        # the sentence that sends them away.
        count = f"{len(tools)} tool" + ("s" if len(tools) != 1 else "")
        lines += [
            "",
            # <Note>, not <Info>: in this Mintlify version Info renders
            # neutral-gray and Note renders blue, which is the callout the rest
            # of the page already uses.
            "<Note>",
            f"Refer to [{named[0]}'s provider page]({named[1]}) for the"
            f' "{first.provider.upper()}" constant the snippets below name, the'
            f" scopes these {count} ask for, and this server's refresh"
            " behaviour.",
            "</Note>",
        ]

    env_var = getattr(first.credential_provider, "env_var", None)
    lines += [
        "",
        _credential_shapes(
            pack,
            first.provider or "server",
            env_var or "ACCESS_TOKEN",
            named[1] if named else None,
        ),
    ]
    return "\n".join(lines)


# -----------------------------------------------------
# The wire declarations
# -----------------------------------------------------


def _render_pagination_style(pagination: Pagination) -> str:
    if pagination.page_param:
        style = (
            f"page number, {_code(pagination.page_param)} with "
            f"{_code(pagination.per_page_param)}"
        )
        if pagination.items_field:
            style += f", list under {_code(pagination.items_field)}"
        return style

    style = (
        f"cursor at {_code(pagination.cursor_field)}, sent back as "
        f"{_code(pagination.cursor_param)}"
    )
    if pagination.more_field:
        style += f", more pages at {_code(pagination.more_field)}"
    return style


def _py(value: Any) -> str:
    """A Python literal, with the double quotes the rest of the docs use."""
    if isinstance(value, str):
        return '"' + value.replace('"', '\\"') + '"'
    return repr(value)


def _fits(text: str, indent: str, prefix: int) -> bool:
    """Whether ``indent + name= + text +","`` lands inside the card."""
    return len(indent) + prefix + len(text) + 1 <= _WIDTH


def _py_seq(
    values: Sequence[Any], open_: str, close: str, indent: str, prefix: int = 0
) -> str:
    """A list or set literal, broken over lines when it will not fit on one."""
    inline = open_ + ", ".join(_py(value) for value in values) + close
    if _fits(inline, indent, prefix):
        return inline
    body = "".join(f"\n{indent}    {_py(value)}," for value in values)
    return f"{open_}{body}\n{indent}{close}"


def _py_dict(mapping: Dict[str, Any], indent: str, prefix: int = 0) -> str:
    items = sorted(mapping.items())
    inline = "{" + ", ".join(f"{_py(k)}: {_py(v)}" for k, v in items) + "}"
    if _fits(inline, indent, prefix):
        return inline
    body = "".join(f"\n{indent}    {_py(k)}: {_py(v)}," for k, v in items)
    return "{" + body + f"\n{indent}" + "}"


def _py_envelope(envelope: Envelope, indent: str, prefix: int = 0) -> str:
    """``Envelope(...)`` as it would be written on the factory."""
    args: List[str] = []
    if envelope.ok_field:
        args.append(f"ok_field={_py(envelope.ok_field)}")
    if envelope.ok_value is not None:
        args.append(f"ok_value={_py(envelope.ok_value)}")
    if envelope.error_field:
        args.append(f"error_field={_py(envelope.error_field)}")
    if envelope.errors_field:
        paths = _paths_of(envelope.errors_field)
        rendered = _py(paths[0]) if len(paths) == 1 else _py_seq(paths, "(", ")", indent + "    ")
        args.append(f"errors_field={rendered}")
    if envelope.credential_errors:
        codes = sorted(envelope.credential_errors)
        args.append(f"credential_errors={_py_seq(codes, '{', '}', indent + '    ')}")
    if envelope.detail_fields:
        rendered = _py_seq(list(envelope.detail_fields), "(", ")", indent + "    ")
        args.append(f"detail_fields={rendered}")

    inline = "Envelope(" + ", ".join(args) + ")"
    if _fits(inline, indent, prefix) and "\n" not in inline:
        return inline
    body = "".join(f"\n{indent}    {arg}," for arg in args)
    return f"Envelope({body}\n{indent})"


def _paths_of(value: Any) -> Tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


# What both tabs hand over, named rather than built. An `EnvTokenProvider` here
# read as *the* way to authenticate a client, three sections after the page has
# just laid out three of them — and it hid the answer to the question the tab
# raises: a client you build yourself has no `configure()`, so the provider you
# picked has to arrive as a constructor argument. One name in both tabs makes
# that the only difference between them.
_CREDENTIAL = "credentials"


def _py_credential(tool: Tool) -> str:
    """The provider a caller would name, where a pack defers to ``configure()``."""
    return _CREDENTIAL


def _py_api_key_headers(tool: Tool, indent: str, prefix: int, key: str) -> str:
    """The auth headers, with ``key`` standing in for the secret.

    A pack holds these behind ``configure()``; written by hand they are a plain
    dict, so the block shows the dict — the template the pack declares, with the
    placeholder replaced by the variable read from the environment above.

    Only a value that carries the placeholder is a credential. A pack may put a
    constant in the same dict — a vendor may ask for an ``Accept-Encoding`` —
    and that one is passed through untouched rather than having a key pinned
    onto the end of it.
    """
    holder = tool.api_key_headers
    template = getattr(holder, "header_template", None)
    if not template:
        header = getattr(holder, "key_header", None)
        return "{" + f"{_py(header)}: ..." + "}" if header else "..."

    rendered: Dict[str, str] = {}
    for header, value in template.items():
        if _UNSET not in value:
            rendered[header] = _py(value)
            continue
        # What the header carries in front of the key — "Bearer ", or nothing.
        scheme = value.replace(_UNSET, "")
        rendered[header] = f'f"{scheme}{{{key}}}"' if scheme else key

    items = sorted(rendered.items())
    inline = "{" + ", ".join(f"{_py(k)}: {v}" for k, v in items) + "}"
    if _fits(inline, indent, prefix):
        return inline
    lines = "".join(f"\n{indent}    {_py(k)}: {v}," for k, v in items)
    return "{" + lines + f"\n{indent}" + "}"


def _py_host(resolver: Any, host: Optional[str]) -> str:
    """The host template a per-installation base URL resolves, as an f-string."""
    template = getattr(resolver, "template", None)
    if not template or not host:
        return "..."
    filled = re.sub(r"\{[a-z_]+\}", "{" + host + "}", template)
    return f'f"{filled}"'


def _env_bindings(module: ModuleType, key_var: Optional[str], host_var: Optional[str]):
    """The environment reads a hand-written setup would make, named.

    Named after the pack's own ``configure()`` parameters, so both tabs of the
    block call the same things by the same names. Returns the source lines and
    the two variables the factory call needs.
    """
    lines: List[str] = []
    key = host = None
    for name in inspect.signature(module.configure).parameters:
        if name == "shop" and host_var:
            host, env = name, host_var
        elif name in ("api_key", "access_token", "token") and key_var:
            key, env = name, key_var
        else:
            continue
        lines.append(f"{name} = os.environ[{_py(env)}]")
    return lines, key, host


def _py_pagination(pagination: Pagination, indent: str = "") -> str:
    """``Pagination(...)``, wrapped at the card's width against ``indent``.

    The indent is where the value starts on the page, not where it is written
    in this file: nested inside a builder call it has four columns less to
    work with, and a line that fits at the left margin does not fit there.
    """
    args: List[str] = []
    if pagination.page_param:
        args.append(f"page_param={_py(pagination.page_param)}")
        args.append(f"per_page_param={_py(pagination.per_page_param)}")
    else:
        args.append(f"cursor_field={_py(pagination.cursor_field)}")
        args.append(f"cursor_param={_py(pagination.cursor_param)}")
        if pagination.more_field:
            args.append(f"more_field={_py(pagination.more_field)}")
    if pagination.items_field:
        args.append(f"items_field={_py(pagination.items_field)}")

    inline = "Pagination(" + ", ".join(args) + ")"
    if len(indent) + len("    pagination=") + len(inline) <= _WIDTH:
        return inline
    body = "".join(f"\n{indent}    {arg}," for arg in args)
    return f"Pagination({body}\n{indent})"


def _comment(text: str) -> List[str]:
    """Prose as ``#`` lines, wrapped to the width of the card."""
    return [f"# {line}" for line in textwrap.wrap(text, _WIDTH - 2)]


def _wrapped_comment(names: Sequence[str]) -> List[str]:
    """``# a, b, c`` broken at the column the rest of the block respects."""
    lines: List[str] = []
    current = "#"
    for index, name in enumerate(names):
        piece = name + ("," if index < len(names) - 1 else "")
        if len(current) + 1 + len(piece) > _WIDTH:
            lines.append(current)
            current = "#"
        current += " " + piece
    lines.append(current)
    return lines


# What actually fits on one line inside a pack page's code card, measured
# rather than assumed: 566px of viewport over a 8.73px monospace character.
# A tabbed card is narrower than the page, so 79 or 88 would be cut off and
# the reader would have to scroll a declaration sideways to finish reading it.
_WIDTH = 64

# What ``DeferredApiKeyHeaders`` leaves where the key goes.
_UNSET = "CHARTER_UNCONFIGURED"


def wire_declarations(pack: str, module: ModuleType) -> str:
    """The pack's wire contract as Python.

    A declaration is emitted only where every tool in the pack agrees; where
    they do not, the value is ``...`` with a comment saying so rather than
    picking one tool's answer.
    """
    tools: List[Tool] = list(module.TOOLS)
    first = tools[0]
    oauth = first.credential_provider is not None
    factory = "oauth_tool_factory" if oauth else "api_key_tool_factory"

    def uniform(read: Callable[[Tool], Any]) -> Any:
        return _uniform(tools, read)

    # A kwarg is (comment or None, "name=value"); the comment goes on the line
    # above so nothing has to be aligned and a long value cannot push it off.
    kwargs: List[Tuple[Optional[str], str]] = []
    # Declarations that belong on a builder call rather than on the factory.
    per_tool: List[str] = []

    holder = first.credential_provider or first.api_key_headers
    key_var = getattr(holder, "env_var", None)
    base_url = uniform(lambda t: t.base_url)
    host_var = getattr(base_url, "env_var", None) if callable(base_url) else None
    reads, key_name, host_name = _env_bindings(module, key_var, host_var)

    if _varies(base_url):
        base_url, exceptions = _dominant(tools, lambda t: t.base_url)
    else:
        exceptions = []

    if _varies(base_url):
        kwargs.append(("varies by tool", "base_url=..."))
    elif exceptions:
        kwargs.append(
            (
                f"except {_joined_plain(exceptions)}, which "
                f"{'uses' if len(exceptions) == 1 else 'use'} a different host",
                f"base_url={_py(base_url)}",
            )
        )
    elif callable(base_url):
        kwargs.append(
            (
                "the host is a property of the installation, not of the API",
                f"base_url=lambda: {_py_host(base_url, host_name)}",
            )
        )
    else:
        kwargs.append((None, f"base_url={_py(base_url)}"))

    if oauth:
        provider = uniform(lambda t: t.provider)
        if not _varies(provider) and provider:
            kwargs.append((None, f"provider={_py(provider)}"))
        kwargs.append((None, f"credential_provider={_py_credential(first)}"))
    else:
        kwargs.append(
            (
                None,
                f"api_key_headers="
                f"{_py_api_key_headers(first, '    ', 16, key_name or '...')}",
            )
        )

    scopes = uniform(lambda t: tuple(t.scopes))
    if not _varies(scopes) and scopes:
        kwargs.append((None, f"scopes={_py_seq(list(scopes), '[', ']', '    ', 7)}"))

    for name, read in (
        ("body_format", lambda t: t.body_format),
        ("query_format", lambda t: t.query_format),
        ("body_case", lambda t: t.body_case),
        ("query_case", lambda t: t.query_case),
        ("path_case", lambda t: t.path_case),
    ):
        value = uniform(read)
        odd_ones: List[str] = []
        if _varies(value):
            value, odd_ones = _dominant(tools, read)
        if _varies(value):
            kwargs.append(("varies by tool", f"{name}=..."))
        elif odd_ones:
            kwargs.append(
                (
                    f"except {_joined_plain(odd_ones)}",
                    f"{name}={_py(value)}",
                )
            )
        else:
            kwargs.append((None, f"{name}={_py(value)}"))

    for name, read in (
        ("static_headers", lambda t: t.static_headers),
        ("static_query", lambda t: t.static_query),
        ("static_body", lambda t: t.static_body),
    ):
        present = [tool for tool in tools if read(tool)]
        if not present:
            continue
        def as_items(tool: Tool, r: Callable[[Tool], Any] = read) -> Any:
            return tuple(sorted(r(tool).items()))

        shared = _uniform(present, as_items)
        odd_ones: List[str] = []
        if _varies(shared):
            shared, odd_ones = _dominant(present, as_items)

        if _varies(shared):
            # Not a factory argument at all: it differs per tool, so it is
            # passed on each builder call instead. Saying so under the call is
            # honest; a `name=...` kwarg would not be.
            keys = sorted({key for tool in present for key in read(tool)})
            per_tool.extend(
                _comment(
                    f"{name} is per tool, not per API: {_joined_plain(keys)} "
                    f"differs across {len(present)} of {len(tools)} tools."
                )
            )
            continue

        value = dict(shared)
        if odd_ones:
            # The exception is named, and so is the key it turns on: "except
            # pulls_get_diff" says which tool, and the differing key says what
            # about it — which together are the whole of the departure.
            differing = sorted(
                {
                    key
                    for tool in present
                    if tool.name in odd_ones
                    for key, own in read(tool).items()
                    if value.get(key) != own
                }
            )
            kwargs.append(
                (
                    f"{_joined_plain(differing)} differ"
                    f"{'s' if len(differing) == 1 else ''} on "
                    f"{_joined_plain(odd_ones)}",
                    f"{name}={_py_dict(value, '    ', len(name) + 1)}",
                )
            )
        else:
            kwargs.append((None, f"{name}={_py_dict(value, '    ', len(name) + 1)}"))

    envelope = uniform(lambda t: t.envelope)
    if _varies(envelope):
        kwargs.append(("varies by tool", "envelope=..."))
    elif envelope is None:
        kwargs.append(("this API reports failure with an HTTP status code", "envelope=None"))
    else:
        kwargs.append((None, f"envelope={_py_envelope(envelope, '    ', 9)}"))

    # `Pagination` is imported by the block that declares it, which is now the
    # section under this one, so it is not in this tab's import line.
    imports = ["Envelope"] if isinstance(envelope, Envelope) else []
    imports.append(factory)

    body: List[str] = []
    if reads:
        body += reads + [""]
    body.append(f"{pack}_api_client = {factory}(")
    for comment, kwarg in kwargs:
        if comment:
            body.append(f"    # {comment}")
        body.append(f"    {kwarg},")
    body.append(")")

    if per_tool:
        # One blank line before the note, not one before each wrapped line.
        body.append("")
        body.extend(per_tool)

    # `os` only earns its import when a credential or a host reads the
    # environment, which is every pack but is not guaranteed to be.
    lines: List[str] = []
    if any("os.environ" in line for line in body):
        lines += ["import os", ""]
    lines.append(f"from charter import {', '.join(sorted(imports))}")
    lines.append("")
    lines += body

    return "\n".join(lines)


def _paginated(tools: Sequence[Tool]) -> Dict[Pagination, List[str]]:
    """The list endpoints, grouped by the pagination they declare."""
    declared: Dict[Pagination, List[str]] = {}
    for tool in tools:
        if tool.pagination is not None:
            declared.setdefault(tool.pagination, []).append(tool.name)
    return declared


def render_pagination(pack: str, module: ModuleType) -> str:
    """The per-tool declarations, under the factory rather than inside it.

    These used to sit at the bottom of the hand-written tab, under two comment
    lines explaining why they were not a factory argument. Code that needs a
    comment to explain why it is in the block it is in is usually in the wrong
    block: everything above is one call, and this is a different shape — one
    declaration per list endpoint, passed on the builder call.

    Out here the explanation is prose, the tools it applies to are named in the
    sentence rather than in a comment, and the tab above stays what it claims to
    be: the constants the client attaches to every request.
    """
    tools: List[Tool] = list(module.TOOLS)
    declared = _paginated(tools)
    if not declared:
        return ""

    by_name = {tool.name: tool for tool in tools}
    paging = [name for names in declared.values() for name in names]
    quiet = len(tools) - len(paging)

    body: List[str] = []
    for index, (pagination, names) in enumerate(declared.items()):
        if index:
            body.append("")
        # The builder call itself, so the declaration is shown where it goes.
        # On its own, `Pagination(...)` is a value with nowhere to be: a reader
        # who has just seen a factory call has no way to tell whether it is
        # another factory argument, and the sentence saying it is not was doing
        # work the code can do.
        #
        # One call per distinct declaration, and the tools sharing it are named
        # in a comment only where the pack has more than one — with a single
        # declaration the note above already lists every tool it is on, and the
        # comment was repeating it beside the code.
        tool = by_name[names[0]]
        if len(declared) > 1:
            body.extend(_comment(f"On {_joined_plain(names)}."))
        body += [
            f"{tool.name} = {pack}_api_client(",
            f'    name="{tool.name}",',
            f"    args_schema={tool.args_schema.__name__},",
            f'    method="{tool.method}",',
            f'    url_template="{tool.url_template}",',
            f"    pagination={_py_pagination(pagination, indent='    ')},",
            ")",
        ]

    # Which tools, by name. A count on its own ("2 of the 9") left the reader
    # to find out which two by reading every tool page, and the answer is two
    # names long.
    others = (
        f" The other {quiet} take no cursor." if quiet else ""
    )
    # Under the code, like the note in "One account, refreshed": the shape
    # comes first, and which tools carry it is what the reader asks once the
    # shape has landed.
    return "\n".join([
        "### Paging through a list",
        "",
        "A cursor belongs to the tool that returns it, so it is declared on that"
        " tool's builder call:",
        "",
        f"```python {pack}_pagination.py",
        *body,
        "```",
        "",
        "<Note>",
        f"Pagination is declared on {_joined(paging)}.{others}",
        "</Note>",
    ])


def pack_usage(pack: str, module: ModuleType) -> str:
    """The same setup, with the pack making every declaration for you.

    The second tab of the wire block. It reads the pack's own ``configure()``
    signature rather than assuming one, because three shapes exist: a
    credential provider, an API key, and Shopify's store-plus-token.
    """
    tools: List[Tool] = list(module.TOOLS)
    first = tools[0]
    holder = first.credential_provider or first.api_key_headers
    key_var = getattr(holder, "env_var", None)
    base_url = _uniform(tools, lambda t: t.base_url)
    host_var = getattr(base_url, "env_var", None) if callable(base_url) else None

    args: List[str] = []
    for name in inspect.signature(module.configure).parameters:
        if name == "credential_provider" and key_var:
            # The same name the other tab passes to the factory. These two tabs
            # are a controlled comparison — the only thing that should differ
            # between them is how much you had to write — so the credential is
            # one object handed over in two places, which is also the answer to
            # the question the first tab raises: where does the provider you
            # picked go, on a client the pack did not build for you.
            args.append(_CREDENTIAL)
        elif name == "shop" and host_var:
            args.append(f"{name}=os.environ[{_py(host_var)}]")
        elif key_var and name in ("api_key", "access_token", "token"):
            args.append(f"{name}=os.environ[{_py(key_var)}]")
        else:
            args.append(f"{name}=...")

    lines: List[str] = []
    if any("os.environ[" in arg for arg in args):
        lines += ["import os", ""]
    lines.append(f"from charter.packs import {pack}")
    lines.append("")

    call = f"{pack}.configure({', '.join(args)})"
    if len(call) > _WIDTH:
        call = f"{pack}.configure(\n    " + ",\n    ".join(args) + ",\n)"
    lines.append(call)
    lines.append("")
    lines.append("# The base URL, the casing, the envelope and the pagination are")
    lines.append(f"# already declared. {len(tools)} tools, ready to hand to a model:")
    lines.append(f"tools = {pack}.TOOLS")

    return "\n".join(lines)


# The PyPI packages a Python developer would otherwise install to call this
# API — what the callout names as never entering the dependency tree. Linear
# ship no official Python SDK, so their callout stays generic.
_VENDOR_SDKS: Dict[str, Tuple[str, ...]] = {
    "gmail": ("google-api-python-client", "google-auth"),
    "gcalendar": ("google-api-python-client", "google-auth"),
    "gdocs": ("google-api-python-client", "google-auth"),
    "gsheets": ("google-api-python-client", "google-auth"),
    "gdrive": ("google-api-python-client", "google-auth"),
    "gforms": ("google-api-python-client", "google-auth"),
    "slack": ("slack-sdk",),
    "github": ("PyGithub",),
    "stripe": ("stripe",),
    "shopify": ("ShopifyAPI",),
    "firecrawl": ("firecrawl-py",),
}


def render_wire(pack: str, module: ModuleType) -> str:
    """Both halves of the same integration, as two tabs.

    The first is every declaration this API needs, written out. The second is
    the pack, which has already made them. Side by side rather than one or the
    other, because the first tab is what the second is hiding.
    """
    code = wire_declarations(pack, module)
    oauth = module.TOOLS[0].credential_provider is not None
    factory = "oauth_tool_factory" if oauth else "api_key_tool_factory"
    # The claim this section can make that no other page can: the reader is
    # looking at the complete list of constants, so "no SDK" is checkable
    # against what is on screen rather than asserted. It goes in a callout
    # above the code — it frames what follows, so it cannot be a footnote —
    # and the factory is a link, because a name a reader may want to look up
    # is a link everywhere else in these docs.
    #
    # Two sentences, and each one earns its place by being checkable: the
    # first names the exact packages a pip install would have brought in
    # ("no SDK" alone was ambiguous — Charter is an SDK), the second says what
    # the factory actually is, in terms the block below demonstrates. The
    # benefits — less to learn, less to pin, less to download — stay implicit,
    # because a reader who sees the named packages missing from their tree
    # draws them without being told.
    link = f"[`{factory}`](/reference/factories#{factory})"
    sdks = _VENDOR_SDKS.get(pack)
    if sdks:
        names = " and ".join(f"`{sdk}`" for sdk in sdks)
        # Flat present tense, not "never": the fact is surprising enough on its
        # own, and the emphasis is the one word here doing no work.
        does = "do" if len(sdks) > 1 else "does"
        absent = f"{names} {does} not enter your dependency tree."
    else:
        absent = "No vendor SDK enters your dependency tree."
    credential = "token" if oauth else "key"
    lead = (
        f"{link} is the whole client: a thin wrapper over `httpx` that "
        f"attaches your {credential} and these endpoint constants to each "
        f"request. {absent}"
    )
    # A tab says which of the two you are reading; the card's own bar says what
    # the file would be called. The names cannot ride on the tabs — a tab title
    # is the tab's whole label — so they are carried on the wrapper and
    # code-blocks.js puts each one on the card it belongs to.
    #
    # "Without the pack", not "Hand written": the two labels are read against
    # each other, and only one of them said what it was the opposite of. Both
    # tabs are hand written — the difference is whether the pack exists.
    files = f"{pack}_api_client.py|{pack}_pack_client.py"
    lines = [
        "<Note>",
        lead,
        "</Note>",
        "",
        f'<div className="named-tabs" data-files="{files}">',
        "<CodeGroup>",
        "",
        "```python Without the pack",
        code,
        "```",
        "",
        "```python With the pack",
        pack_usage(pack, module),
        "```",
        "",
        "</CodeGroup>",
        "</div>",
    ]

    # The question both tabs raise and neither can answer in code: the page has
    # just shown three credential providers, all handed to `configure()`, and a
    # client you build yourself has no `configure()`. It takes the same object
    # one constructor argument earlier, and saying so is what connects this
    # section to the one above it.
    #
    # Only for an OAuth pack. An API-key pack has one credential shape and its
    # tabs read the key straight from the environment on both sides, so there is
    # no picked-provider to place and nothing here to say.
    if oauth:
        lines += [
            "",
            f"`{_CREDENTIAL}` is whichever of the three you built in"
            " [Authenticating](#authenticating). A pack takes it through"
            " [`configure()`](/reference/configuration#configure); a client you"
            " build takes the same object as `credential_provider`, and has no"
            " `configure()` of its own.",
        ]

    paging = render_pagination(pack, module)
    if paging:
        lines += ["", paging]
    return "\n".join(lines)


# -----------------------------------------------------
# Driving it
# -----------------------------------------------------


def pack_module(pack: str) -> ModuleType:
    return importlib.import_module(f"charter.packs.{pack}")


def page_path(pack: str) -> Path:
    return PACK_DOCS / f"{pack}.mdx"


def blocks(pack: str) -> Dict[str, str]:
    """What each generated region on this pack's page should contain."""
    module = pack_module(pack)
    return {
        "summary": render_summary(pack, module),
        "tools": render_tools(pack, module),
        "auth": render_auth(pack, module),
        "wire": render_wire(pack, module),
    }


def regenerate(text: str, pack: str) -> str:
    for block, body in blocks(pack).items():
        text = replace(text, block, body)
    return text


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    stale: List[str] = []

    for pack in PACKS:
        path = page_path(pack)
        if not path.exists():
            print(f"missing page: docs/packs/{pack}.mdx", file=sys.stderr)
            return 1
        current = path.read_text()
        updated = regenerate(current, pack)
        if updated == current:
            continue
        stale.append(pack)
        if not check:
            path.write_text(updated)

    if check and stale:
        print(f"stale generated blocks: {', '.join(stale)}", file=sys.stderr)
        print(f"run: uv run python {_SCRIPT}", file=sys.stderr)
        return 1

    verb = "stale" if check else "rewrote"
    print(f"{len(PACKS)} pack pages checked, {len(stale)} {verb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
