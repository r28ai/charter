# SPDX-FileCopyrightText: 2026 R28 AI, Inc.
# SPDX-License-Identifier: Apache-2.0

"""scopes_for picks the fewest, narrowest scopes; AnyOf says where a provider accepts several.

The algorithm is checked three ways: by hand on the cases that broke earlier
drafts, against a brute-force search over every possible scope set on thousands
of random declarations, and across every pack, so a pack declaring its scopes
inconsistently fails here rather than on a consent screen.
"""

from __future__ import annotations

import itertools
import random

import pytest

from charter import DeclarationError, Tool
from charter.auth import AnyOf, Kind, Unavailable, missing_scopes, scopes_for
from charter.auth.scopes import _narrowest_first


def tool(name: str, *scopes) -> Tool:
    from pydantic import BaseModel

    class Args(BaseModel):
        pass

    return Tool(
        name=name,
        description="x",
        args_schema=Args,
        method="GET",
        base_url="https://api.example.com/",
        url_template="x",
        provider="example",
        api_key_headers={"Authorization": "Bearer test"},
        scopes=list(scopes),
    )


# -----------------------------------------------------------------------------
# By hand
# -----------------------------------------------------------------------------


def test_plain_scopes_are_all_required_and_keep_their_order():
    """The declaration every existing pack uses means what it meant: the union."""
    a = tool("a", "chat:write", "channels:read")
    b = tool("b", "channels:read", "users:read")
    assert scopes_for([a, b]) == ["chat:write", "channels:read", "users:read"]


def test_one_tool_asks_for_its_narrowest_option():
    send = tool("send", AnyOf("gmail.send", "gmail.compose", "gmail.modify", "mail"))
    assert scopes_for([send]) == ["gmail.send"]


def test_a_broader_scope_the_set_needs_anyway_absorbs_a_narrower_one():
    read = tool("read", AnyOf("gmail.readonly", "gmail.modify", "mail"))
    relabel = tool("relabel", AnyOf("gmail.modify", "mail"))
    assert scopes_for([read, relabel]) == ["gmail.modify"]


def test_two_narrow_scopes_are_preferred_to_one_broad_one():
    """Fewer lines on a consent screen is not worth more privilege."""
    docs = tool("docs", AnyOf("documents", "drive"))
    sheets = tool("sheets", AnyOf("spreadsheets", "drive"))
    assert scopes_for([docs, sheets]) == ["documents", "spreadsheets"]


def test_the_result_does_not_depend_on_the_order_tools_arrive_in():
    """The case that made an earlier draft order-dependent: A < B < C, A and C never together."""
    t1 = tool("t1", AnyOf("a", "b"))
    t2 = tool("t2", AnyOf("b", "c"))
    t3 = tool("t3", "c")
    results = {frozenset(scopes_for(list(p))) for p in itertools.permutations([t1, t2, t3])}
    assert results == {frozenset({"a", "c"})}


def test_plain_and_anyof_mix_on_one_tool():
    t = tool("t", "openid", AnyOf("files.read", "files.write"))
    assert scopes_for([t]) == ["openid", "files.read"]


def test_no_tools_and_no_scopes_ask_for_nothing():
    assert scopes_for([]) == []
    assert scopes_for([tool("public")]) == []


def test_two_tools_that_disagree_about_which_scope_is_narrower_are_refused():
    t1 = tool("t1", AnyOf("read", "write"))
    t2 = tool("t2", AnyOf("write", "read"))
    with pytest.raises(DeclarationError, match="read and write are each listed before the other"):
        scopes_for([t1, t2])


@pytest.mark.parametrize(
    ("args", "match"),
    [
        ((), "at least one"),
        (("a", "a"), "twice"),
        (("a", ""), "scope strings"),
        (("a", 3), "scope strings"),
    ],
)
def test_anyof_refuses_what_cannot_be_a_requirement(args, match):
    with pytest.raises(DeclarationError, match=match):
        AnyOf(*args)


@pytest.mark.parametrize("bad", ["", "  ", 3, None, ["a"]])
def test_a_tool_refuses_a_scope_that_is_neither_a_string_nor_anyof(bad):
    with pytest.raises(DeclarationError, match="scopes must be"):
        tool("t", bad)


def test_anyof_is_a_value():
    assert AnyOf("a", "b") == AnyOf("a", "b") != AnyOf("b", "a")
    assert len({AnyOf("a", "b"), AnyOf("a", "b")}) == 1
    assert repr(AnyOf("a", "b")) == "AnyOf('a', 'b')"
    with pytest.raises(AttributeError):
        AnyOf("a").options = ("b",)  # type: ignore[misc]


def test_missing_scopes_compares_by_requirement_not_by_string():
    read = tool("read", AnyOf("gmail.readonly", "gmail.modify"))
    send = tool("send", AnyOf("gmail.send", "gmail.modify"))
    assert missing_scopes([read, send], granted=["gmail.modify"]) == []
    assert missing_scopes([read, send], granted=["gmail.readonly"]) == ["gmail.send"]
    assert missing_scopes([read, send], granted=[]) == scopes_for([read, send])


# -----------------------------------------------------------------------------
# Against brute force
# -----------------------------------------------------------------------------


def _random_case(rng: random.Random):
    """Random tools over a random total order of scopes, every AnyOf respecting it."""
    universe = [f"s{i}" for i in range(rng.randint(1, 7))]
    rng.shuffle(universe)  # universe[0] is narrowest
    tools = []
    for i in range(rng.randint(1, 6)):
        reqs = []
        for _ in range(rng.randint(0, 3)):
            k = rng.randint(1, len(universe))
            picked = sorted(rng.sample(range(len(universe)), k))
            options = [universe[j] for j in picked]
            reqs.append(options[0] if len(options) == 1 and rng.random() < 0.5 else AnyOf(*options))
        tools.append(tool(f"t{i}", *reqs))
    return universe, tools


def _clauses(tools):
    return [
        r.options if isinstance(r, AnyOf) else (r,)
        for t in tools
        for r in t.scopes
        if not isinstance(r, Unavailable)
    ]


def _covers(chosen, clauses):
    return all(any(o in chosen for o in c) for c in clauses)


def _brute_force(universe, clauses):
    """Every subset that covers, the one that avoids the broadest scopes first."""
    rank = {s: i for i, s in enumerate(universe)}
    best = None
    for n in range(len(universe) + 1):
        for subset in itertools.combinations(universe, n):
            if not _covers(subset, clauses):
                continue
            key = sorted((rank[s] for s in subset), reverse=True)
            if best is None or key < best[0]:
                best = (key, set(subset))
    return best[1] if best else set()


@pytest.mark.parametrize("seed", range(40))
def test_scopes_for_matches_brute_force_on_random_declarations(seed):
    rng = random.Random(seed)
    for _ in range(100):
        universe, tools = _random_case(rng)
        clauses = _clauses(tools)
        got = scopes_for(tools)
        assert len(got) == len(set(got)), "no scope twice"
        assert _covers(got, clauses), "every requirement met"
        for s in got:  # irredundant: nothing can be dropped
            assert not _covers(set(got) - {s}, clauses), f"{s} could be dropped"
        assert set(got) == _brute_force(universe, clauses)
        shuffled = tools[:]
        rng.shuffle(shuffled)
        assert set(scopes_for(shuffled)) == set(got), "order of tools must not matter"
        granted = set(rng.sample(universe, rng.randint(0, len(universe))))
        extra = missing_scopes(tools, granted)
        assert _covers(granted | set(extra), clauses)
        assert not set(extra) & granted
        assert missing_scopes(tools, got) == []


# -----------------------------------------------------------------------------
# Every pack
# -----------------------------------------------------------------------------


def _packs():
    import importlib

    from tests.test_conformance import PACK_NAMES

    return [importlib.import_module(f"charter.packs.{name}") for name in PACK_NAMES]


def test_every_pack_and_all_of_them_together_order_their_scopes_consistently():
    every = [t for pack in _packs() for t in pack.TOOLS]
    _narrowest_first(_clauses(every))  # raises on a disagreement


def _kinds(tools):
    kinds = [None]
    for t in tools:
        kinds += [k for k in t.kind_scopes if k not in kinds]
    return kinds


def _kind_clauses(tools, kind):
    from charter.auth.scopes import _options, _requirements

    return [_options(r) for t in tools for r in _requirements(t, kind) if _options(r)]


def _runnable(tools, kind):
    from charter.auth.scopes import _requirements

    return [t for t in tools if not any(isinstance(r, Unavailable) for r in _requirements(t, kind))]


@pytest.mark.parametrize("pack", _packs(), ids=lambda p: p.__name__.rsplit(".", 1)[1])
def test_scopes_for_holds_on_random_slices_of_each_pack(pack):
    """Under every kind of credential the pack declares, not only the default."""
    rng = random.Random(pack.__name__)
    for kind in _kinds(pack.TOOLS):
        tools = _runnable(pack.TOOLS, kind)
        for _ in range(200 if kind is None else 60):
            chosen = rng.sample(tools, rng.randint(1, min(len(tools), 12)))
            clauses = _kind_clauses(chosen, kind)
            got = scopes_for(chosen, kind=kind)
            assert _covers(got, clauses)
            for s in got:
                assert not _covers(set(got) - {s}, clauses), (
                    f"{pack.__name__} [{kind}]: {s} could be dropped"
                )
            rng.shuffle(chosen)
            assert set(scopes_for(chosen, kind=kind)) == set(got)


# -----------------------------------------------------------------------------
# Kinds of credential
# -----------------------------------------------------------------------------

ACME = "acme"
OAUTH = Kind("oauth", provider=ACME, default=True)
APP = Kind("app", provider=ACME, granted="configured")
OTHER = Kind("app", provider="other")


def kinded(name: str, scopes, *, provider: str = ACME) -> Tool:
    from pydantic import BaseModel

    class Args(BaseModel):
        pass

    return Tool(
        name=name,
        args_schema=Args,
        method="GET",
        base_url="https://api.example.com/",
        url_template="x",
        provider=provider,
        api_key_headers={"Authorization": "Bearer test"},
        scopes=scopes,
    )


def test_a_kind_answers_with_its_own_requirements():
    a = kinded("a", {OAUTH: ["repo"], APP: [AnyOf("issues=read", "issues=write")]})
    b = kinded("b", {OAUTH: ["repo"], APP: ["issues=write"]})
    assert scopes_for([a, b]) == ["repo"]
    assert scopes_for([a, b], kind=APP) == ["issues=write"]
    assert a.scopes == ["repo"] and a.default_kind is OAUTH


def test_a_kind_can_be_named_by_its_string_and_a_misspelling_is_refused():
    a = kinded("a", {OAUTH: ["repo"], APP: ["issues=read"]})
    assert scopes_for([a], kind="app") == ["issues=read"]
    with pytest.raises(
        DeclarationError, match=r"'ap'.*'oauth', 'app'.*ACME\.APP|'ap'.*'oauth', 'app'"
    ):
        scopes_for([a], kind="ap")


def test_another_providers_kind_is_refused_naming_the_tool():
    a = kinded("a", {OAUTH: ["repo"], APP: ["issues=read"]})
    with pytest.raises(DeclarationError, match=r"other\.app.*a is a acme tool"):
        scopes_for([a], kind=OTHER)


def test_a_tool_with_plain_scopes_still_answers_and_has_no_kinds():
    plain = tool("plain", "x")
    assert scopes_for([plain]) == ["x"] and plain.kind_scopes == {} and plain.default_kind is None
    with pytest.raises(DeclarationError, match="only plain scopes"):
        scopes_for([plain], kind="app")


def test_a_tool_that_declares_nothing_needs_nothing_under_any_question():
    bare = tool("bare")
    assert scopes_for([bare]) == [] and missing_scopes([bare], []) == []


def test_unavailable_is_refused_by_name_with_a_kind_that_would_do():
    search = kinded("search", {OAUTH: [Unavailable("needs a user")], APP: ["search=read"]})
    other = kinded("other", {OAUTH: ["repo"], APP: ["x=read"]})
    with pytest.raises(DeclarationError, match=r"search \(needs a user\).*kind=acme\.APP"):
        scopes_for([search, other])
    assert scopes_for([search, other], kind=APP) == ["search=read", "x=read"]
    with pytest.raises(DeclarationError, match="search"):
        missing_scopes([search], ["repo"])


def test_missing_scopes_answers_per_kind():
    a = kinded("a", {OAUTH: ["repo"], APP: [AnyOf("issues=read", "issues=write")]})
    assert missing_scopes([a], ["issues=write"], kind=APP) == []
    assert missing_scopes([a], [], kind=APP) == ["issues=read"]
    assert missing_scopes([a], ["issues=write"]) == ["repo"]


@pytest.mark.parametrize(
    ("scopes", "match"),
    [
        ({"app": ["x"]}, "keyed by Kind"),
        ({OAUTH: ["x"], Kind("b", provider=ACME, default=True): ["y"]}, "two default kinds"),
        ({OAUTH: ["x"], OTHER: ["y"]}, "two providers"),
        ({OAUTH: "repo"}, "list of requirements"),
        ({APP: [3]}, "scope strings"),
    ],
)
def test_a_kinds_mapping_refuses_what_it_cannot_mean(scopes, match):
    with pytest.raises(DeclarationError, match=match):
        kinded("t", scopes)


def test_a_list_override_replaces_the_default_kind_and_keeps_the_others():
    base = kinded("t", {OAUTH: ["repo"], APP: ["issues=read"]})
    narrowed = base.derived(name="public", scopes=["public_repo"])
    assert narrowed.scopes == ["public_repo"] and narrowed.default_kind is OAUTH
    assert narrowed.kind_scopes == {APP: ["issues=read"]}


def test_a_mapping_override_replaces_only_the_kinds_it_names():
    base = kinded("t", {OAUTH: ["repo"], APP: ["issues=read"]})
    narrowed = base.derived(name="t2", scopes={APP: ["issues=write"]})
    assert narrowed.scopes == ["repo"] and narrowed.kind_scopes == {APP: ["issues=write"]}


def test_a_factory_kind_is_kept_by_a_tool_override():
    from pydantic import BaseModel

    from charter import oauth_tool_factory
    from charter.auth import StaticTokenProvider

    class Args(BaseModel):
        pass

    build = oauth_tool_factory(
        "https://api.example.com/",
        ACME,
        StaticTokenProvider("t"),
        scopes={OAUTH: ["repo"], APP: ["metadata=read"]},
        pack="acme",
    )
    one = build(
        name="one", args_schema=Args, method="GET", url_template="x", scopes_override=["gist"]
    )
    assert one.scopes == ["gist"] and one.kind_scopes == {APP: ["metadata=read"]}
    two = build(
        name="two",
        args_schema=Args,
        method="GET",
        url_template="x",
        scopes_override={APP: ["issues=read"]},
    )
    assert two.scopes == ["repo"] and two.kind_scopes == {APP: ["issues=read"]}


def test_a_kind_is_a_value_with_a_readable_name():
    assert Kind("app", provider=ACME) == Kind("app", provider=ACME, description="ignored")
    assert str(APP) == "acme.app"
    assert hash(Kind("app", provider=ACME)) == hash(Kind("app", provider=ACME, description="x"))


def test_unavailable_is_a_value_and_needs_a_reason():
    assert Unavailable("x") == Unavailable("x") and hash(Unavailable("x")) == hash(Unavailable("x"))
    with pytest.raises(DeclarationError, match="reason"):
        Unavailable(" ")


@pytest.mark.parametrize("seed", range(10))
def test_a_kind_answers_exactly_as_its_requirements_would_as_the_default(seed):
    """A kind adds no algorithm: scopes_for under it is scopes_for over its lists."""
    rng = random.Random(seed)
    for _ in range(50):
        universe, declared = _random_case(rng)
        as_app = [kinded(f"t{i}", {OAUTH: ["base"], APP: d.scopes}) for i, d in enumerate(declared)]
        try:
            expected = scopes_for(declared)
        except DeclarationError:
            with pytest.raises(DeclarationError):
                scopes_for(as_app, kind=APP)
            continue
        assert scopes_for(as_app, kind=APP) == expected
