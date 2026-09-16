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

from charter import Query, Tool, qualified_name, qualified_names
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
    ["gmail", "gcalendar", "gsheets", "gdocs", "gdrive", "stripe", "github", "linear", "shopify",
     "slack", "firecrawl", "notion"],
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
    assert set(qualified_names(mine + list(stripe.TOOLS))) >= {"xyz__my_tool", "stripe__products_list"}


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
    """41 characters at the longest, and an MCP host still has room to prefix."""
    import importlib
    import re

    names = [
        qualified_name(t)
        for p in ["gmail", "gcalendar", "gsheets", "gdocs", "gdrive", "stripe", "github", "linear",
                  "shopify", "slack", "firecrawl", "notion"]
        for t in importlib.import_module(f"charter.packs.{p}").TOOLS
    ]
    assert all(re.match(r"^[A-Za-z0-9_-]{1,64}$", n) for n in names)
    # `mcp__charter__` is what a host adds on top
    assert max(len(f"mcp__charter__{n}") for n in names) <= 64


def test_qualifying_is_a_single_pass_over_its_input():
    """It has to take a generator: `qualified_names(t for t in ...)` is the
    natural call, and consuming the iterable twice would return nothing."""
    tools = [make("a", "p"), make("b", "p")]
    assert set(qualified_names(t for t in tools)) == {"p__a", "p__b"}


def test_no_tools_is_no_names_rather_than_an_error():
    assert qualified_names([]) == {}
