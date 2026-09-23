"""
Qualified tool names.

Charter never renames a tool: `name` is what the API calls the endpoint, and an
MCP host composing `mcp__<server>__<tool>` over a library that had already
prefixed would produce `mcp__gcalendar__gcalendar__events_list`. What the
library owes an assembler instead is one convention, and these are its rules.
"""

from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel

from charter import Query, Tool, qualified_name, qualified_names, report_key
from charter.naming import SEPARATOR
from charter.packs import gcalendar, gmail, shopify, stripe
from charter.types.errors import DeclarationError


class Args(BaseModel):
    q: Annotated[str, Query()] = ""


def make(name: str, pack: str | None) -> Tool:
    return Tool(
        name=name,
        method="GET",
        url_template="x",
        args_schema=Args,
        base_url="https://api.test/",
        pack=pack,
        api_key_headers={"x-api-key": "k"},
    )


# -----------------------------------------------------
# The three identities
# -----------------------------------------------------


def test_a_tool_name_is_never_rewritten_by_the_library():
    """The host owns the namespace. Qualifying here would double a host's prefix."""
    assert gcalendar.events_list.name == "events_list"
    assert gcalendar.events_list.to_json_schema()["name"] == "events_list"


def test_pack_is_not_provider():
    """Four Google packs share one credential and deliberately one token, so
    naming by provider would collapse four namespaces into one."""
    google = [gmail.TOOLS[0], gcalendar.TOOLS[0]]
    assert {t.provider for t in google} == {"google"}
    assert {t.pack for t in google} == {"gmail", "gcalendar"}


def test_pack_is_not_derivable_from_base_url():
    """The same host serves several packs, and one pack has no URL until it is
    configured, so the mapping runs the wrong way in both directions."""
    assert gmail.TOOLS[0].base_url != gcalendar.TOOLS[0].base_url
    assert "googleapis.com" in str(gcalendar.TOOLS[0].base_url)
    assert "googleapis.com" in str(gmail.TOOLS[0].base_url)
    assert not str(shopify.TOOLS[0].base_url).startswith("https://")


@pytest.mark.parametrize(
    "pack",
    [
        "gmail",
        "gcalendar",
        "gsheets",
        "gdocs",
        "gdrive",
        "stripe",
        "github",
        "linear",
        "shopify",
        "slack",
        "firecrawl",
        "notion",
    ],
)
def test_every_shipped_pack_declares_itself(pack):
    """A pack that does not name itself cannot be assembled with any other."""
    import importlib

    module = importlib.import_module(f"charter.packs.{pack}")
    assert {t.pack for t in module.TOOLS} == {pack}


# -----------------------------------------------------
# Qualifying
# -----------------------------------------------------


def test_the_separator_is_doubled_so_the_name_can_be_split_back():
    """Tool names contain single underscores; `stripe_products_list` cannot be
    taken apart again, which is why MCP doubles it too."""
    assert SEPARATOR == "__"
    name = qualified_name(stripe.products_list)
    assert name == "stripe__products_list"
    assert name.split(SEPARATOR) == ["stripe", "products_list"]


def test_a_tool_without_a_pack_is_refused_rather_than_left_bare():
    """A silent fall back to the bare name is how a half-qualified surface
    happens, and a half-qualified surface cannot be filtered."""
    with pytest.raises(DeclarationError, match="declares no pack"):
        qualified_name(make("orphan", None))


def test_qualifying_refuses_a_pack_that_declares_a_name_twice():
    with pytest.raises(DeclarationError, match="qualify to"):
        qualified_names([make("dup", "acme"), make("dup", "acme")])


# -----------------------------------------------------
# Stability — a name is a property of the tool, not of its neighbours
# -----------------------------------------------------


def test_a_name_does_not_change_when_another_pack_is_added():
    """The bug this replaced. Qualifying only once a second pack appears renames
    every tool in the first the day someone adds one, and breaks saved prompts,
    allow-lists, logged traces and eval fixtures without a word. MCP servers
    publish the same names whatever else is installed; so does this."""
    alone = qualified_names(gcalendar.TOOLS)
    beside = qualified_names(list(gcalendar.TOOLS) + list(stripe.TOOLS))
    assert set(alone) <= set(beside)
    assert "gcalendar__events_list" in alone


def test_several_packs_are_all_qualified():
    resolved = qualified_names(list(stripe.TOOLS) + list(shopify.TOOLS))
    assert {"stripe__products_list", "shopify__products_list"} <= set(resolved)
    assert all(SEPARATOR in name for name in resolved)


def test_no_name_is_left_bare_beside_a_qualified_one():
    """The property the whole module exists for. `products_list` collides and
    `balance_retrieve` does not, but qualifying only the collision would make
    the pack a substring of some names and not others — so a `+stripe` filter,
    a log grep or an allow-list would silently miss the bare half."""
    resolved = qualified_names(list(stripe.TOOLS) + list(shopify.TOOLS))
    assert "balance_retrieve" not in resolved
    assert "stripe__balance_retrieve" in resolved


def test_nothing_is_dropped_when_two_packs_collide():
    """Keyed by bare name, this surface listed 23 tools and routed 21."""
    tools = list(stripe.TOOLS) + list(shopify.TOOLS)
    assert len({t.name for t in tools}) < len(tools)
    assert len(qualified_names(tools)) == len(tools)


def test_two_identical_tools_from_one_pack_are_refused():
    """A prefix cannot disambiguate within a pack, so the error says so rather
    than letting a dict drop one."""
    with pytest.raises(DeclarationError, match="qualify to"):
        qualified_names([make("dup", "acme"), make("dup", "acme")])


def test_a_user_pack_qualifies_like_a_shipped_one():
    """Nothing here is special-cased to `charter.packs`."""
    mine = [make("my_tool", "xyz"), make("other", "xyz")]
    assert set(qualified_names(mine)) == {"xyz__my_tool", "xyz__other"}
    assert set(qualified_names(mine + list(stripe.TOOLS))) >= {
        "xyz__my_tool",
        "stripe__products_list",
    }


# -----------------------------------------------------
# What a name may contain
# -----------------------------------------------------


@pytest.mark.parametrize(
    "pack,why",
    [("my pack", "a space"), ("acme.api", "a dot"), ("acme/v1", "a slash"), ("acmé", "an accent")],
)
def test_a_pack_that_cannot_be_a_tool_name_is_refused(pack, why):
    """OpenAI accepts `[A-Za-z0-9_-]{1,64}` for a function name and nothing else,
    so a pack like `myproprietary.api` would produce a name rejected at the first
    call. Refusing it where it is declared costs one line instead."""
    with pytest.raises(DeclarationError, match="not usable in a tool name"):
        qualified_name(make("thing", pack))


def test_a_pack_containing_the_separator_is_refused():
    """The doubled underscore is only worth having while it is unambiguous."""
    with pytest.raises(DeclarationError, match="contains '__'"):
        qualified_name(make("thing", "we__ird"))


def test_a_tool_name_containing_the_separator_is_refused():
    with pytest.raises(DeclarationError, match="contains '__'"):
        qualified_name(make("already__qualified", "acme"))


def test_hyphens_survive_because_openai_allows_them():
    assert qualified_name(make("my-tool", "my-pack")) == "my-pack__my-tool"


def test_every_shipped_name_is_valid_for_the_strictest_surface():
    """Every shipped name fits 64 under the prefix the setup docs produce.

    OpenAI accepts ``[A-Za-z0-9_-]{1,64}`` for a function name, and an MCP host
    composes ``mcp__<server>__<tool>`` from *the key the server was configured
    under* — not from the name the server reports. So the string to measure is
    the one docs/using/mcp.mdx tells a reader to write, which is one server
    named ``charter`` holding every pack: ``mcp__charter__<pack>__<tool>``.

    It used to measure the same prefix but over 12 of the 15 shipped packs, so
    a name in gforms, granola or tavily could go over without failing here.
    """
    import importlib
    import re

    from charter.mcp import PACKS

    assert len(PACKS) == 15, "a pack was added or removed; this test must cover all of them"
    names = [
        qualified_name(t)
        for p in PACKS
        for t in importlib.import_module(f"charter.packs.{p}").TOOLS
    ]
    assert all(re.match(r"^[A-Za-z0-9_-]{1,64}$", n) for n in names)
    # `mcp__charter__` is what a host adds on top, given the documented config.
    composed = [f"mcp__charter__{n}" for n in names]
    assert max(len(c) for c in composed) <= 64, "over 64 under the documented setup: " + ", ".join(
        sorted(c for c in composed if len(c) > 64)
    )


def test_naming_a_server_after_its_pack_is_what_the_budget_cannot_afford():
    """Why the setup page configures one server rather than one per pack.

    This is the arithmetic behind that advice, pinned so it cannot quietly stop
    being true. Spelling the pack in the server key as well as the tool name
    costs eight characters on gsheets and puts three names over 64 — which is
    the whole reason ``--pack`` takes a list. If a change ever makes this shape
    fit, the advice can be relaxed; until then the docs guard below keeps the
    page from recommending it.
    """
    import importlib

    from charter.mcp import PACKS

    names = [
        qualified_name(t)
        for p in PACKS
        for t in importlib.import_module(f"charter.packs.{p}").TOOLS
    ]
    per_pack = [f"mcp__charter-{n.split('__', 1)[0]}__{n}" for n in names]
    assert sorted(c for c in per_pack if len(c) > 64) == [
        "mcp__charter-gsheets__gsheets__spreadsheets_developer_metadata_get",
        "mcp__charter-gsheets__gsheets__spreadsheets_developer_metadata_search",
        "mcp__charter-gsheets__gsheets__values_batch_update_by_data_filter",
    ], "the per-pack overruns changed; re-check the advice in docs/using/mcp.mdx"


def test_qualifying_is_a_single_pass_over_its_input():
    """It has to take a generator: `qualified_names(t for t in ...)` is the
    natural call, and consuming the iterable twice would return nothing."""
    tools = [make("a", "p"), make("b", "p")]
    assert set(qualified_names(t for t in tools)) == {"p__a", "p__b"}


def test_no_tools_is_no_names_rather_than_an_error():
    assert qualified_names([]) == {}


# --- where the pack has to be named --------------------------------------------
#
# A factory is "everything shared across the tools of one API", so it always has
# a pack: there is no coherent factory whose tools share a base URL, a credential
# and a wire contract but not a namespace. Requiring it there puts the error on
# the line that has to change, at the moment the API is already being named.
#
# `Tool(...)` stays open, for the one-off a caller only ever `ainvoke`s — a test
# fixture, a private helper. That is the same carve-out `report_key` makes, and
# for the same reason: nothing filters or dispatches on it.


def test_a_factory_will_not_build_without_a_pack():
    from charter import api_key_tool_factory, oauth_tool_factory
    from charter.auth import StaticTokenProvider

    with pytest.raises(TypeError, match="pack"):
        api_key_tool_factory(base_url="https://x.test/", api_key_headers={"k": "v"})  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="pack"):
        oauth_tool_factory(  # type: ignore[call-arg]
            base_url="https://x.test/",
            provider="p",
            credential_provider=StaticTokenProvider("t"),
        )


@pytest.mark.parametrize(
    "pack,because",
    [
        ("", "empty"),
        ("   ", "blank"),
        ("my pack", "a space is not usable in a tool name"),
        ("my.pack", "a dot is not usable in a tool name"),
        ("my__pack", "the separator would not split back"),
    ],
)
def test_a_factory_refuses_a_pack_it_could_not_publish(pack, because):
    """Refused where it is written, not when an adapter reaches it."""
    from charter import api_key_tool_factory

    with pytest.raises(DeclarationError) as caught:
        api_key_tool_factory(base_url="https://x.test/", api_key_headers={"k": "v"}, pack=pack)
    assert "api_key_tool_factory" in str(caught.value), because


def test_a_tool_built_by_hand_still_needs_no_pack():
    """The carve-out. Calling it works; only publishing it does not."""
    tool = Tool(
        name="solo",
        description="d",
        method="GET",
        url_template="x",
        args_schema=Args,
        base_url="https://x.test/",
        api_key_headers={"k": "v"},
    )
    assert tool.pack is None
    assert report_key(tool) == "solo"
    with pytest.raises(DeclarationError, match="declares no pack"):
        qualified_name(tool)


def test_every_factory_call_in_the_tree_names_its_pack():
    """Every tree that holds runnable Python, not just the ones the suite imports.

    `scripts/live_google_check.py` built two factories and is run by hand against
    a real Google account, so nothing here would have caught it breaking. The
    docs are covered separately: the suite executes their blocks.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    missing = []
    trees = ("src/**/*.py", "examples/*.py", "scripts/**/*.py", "harness/src/**/*.py")
    for path in sorted(p for tree in trees for p in root.glob(tree)):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("api_key_tool_factory", "oauth_tool_factory")
                and not any(k.arg == "pack" for k in node.keywords)
                # `**kwargs` may carry it; only a literal call can be judged here.
                and not any(k.arg is None for k in node.keywords)
            ):
                missing.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not missing, f"factory calls that would now raise TypeError: {missing}"
