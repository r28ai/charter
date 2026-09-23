"""The deployer's end of `Mode`: `Tool.with_mode` and `ToolSession(mode=...)`.

`Mode` is declared by whoever writes the pack and resolved by whoever deploys
it, and until there was a `with_mode` only the first half existed: a deployer
holding a pack that already shipped had to hand-build one tool set per tier and
choose between them. What these pin is that the second half resolves the same
declarations the author wrote, that it resolves *once*, and that it cannot reach
a field the author withheld unconditionally.

Offline: nothing here makes a request.
"""

from __future__ import annotations

import json
from typing import Annotated, Optional, Union, get_args

import pytest
from pydantic import BaseModel

from charter import Body, Mode, Path, Query, Tool, ToolSession
from charter.execution.schema import create_llm_schema
from charter.factories import api_key_tool_factory
from charter.types.errors import DeclarationError

BASE = "https://reports.example.com/"


class Report(BaseModel):
    """One resource model serving four surfaces, which is the whole claim."""

    account_id: Annotated[str, Path()]
    raw_events: Annotated[Optional[list], Body(), Mode("pro, max")] = None
    model_weights: Annotated[Optional[dict], Body(), Mode("max")] = None
    eu_consent_id: Annotated[Optional[str], Body(), Mode("eu")] = None


# What each label yields, asserted field set by field set. These are the numbers
# `docs/boundary/mode-system.md` prints, so a change to either has to change both.
TIERS = {
    None: ["account_id", "eu_consent_id", "model_weights", "raw_events"],
    "free": ["account_id"],
    "pro": ["account_id", "raw_events"],
    "max": ["account_id", "model_weights", "raw_events"],
    "eu": ["account_id", "eu_consent_id"],
}


def _factory(pack: str = "rep"):
    return api_key_tool_factory(base_url=BASE, pack=pack, api_key_headers={"x-api-key": "k"})


def _reports(mode: Optional[str] = None, **kw) -> Tool:
    return _factory()(
        name="reports_create",
        args_schema=Report,
        method="POST",
        url_template="r/{account_id}",
        description="Create a report.",
        mode=mode,
        **kw,
    )


def _fields(tool: Tool) -> list:
    return sorted(tool.llm_schema().model_fields)


def _generated(tool: Tool, field: str):
    """The model generated for an ``Optional[Model]`` field, out of its Union."""
    annotation = tool.llm_schema().model_fields[field].annotation
    return next(a for a in get_args(annotation) if a is not type(None))


# ----------------------------------------------------------------------
# the label resolves the view
# ----------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(TIERS))
def test_a_label_the_author_declared_resolves_the_view_the_deployer_gets(mode):
    """The author's four labels, reached from the deployer's end.

    The same field sets `create_llm_schema` produces directly, which is the
    point: `with_mode` is not a second filter with its own rules, it is the one
    filter reached by whoever holds the tool rather than whoever wrote it.
    """
    assert _fields(_reports().with_mode(mode)) == TIERS[mode]
    assert sorted(create_llm_schema(Report, mode=mode).model_fields) == TIERS[mode]


@pytest.mark.parametrize("mode", list(TIERS))
def test_a_session_resolves_every_tool_it_holds(mode):
    session = ToolSession([_reports()], mode=mode)
    assert _fields(session.tools["rep__reports_create"]) == TIERS[mode]


def test_the_published_name_does_not_change_with_the_mode():
    """A `pro` variant of a tool is still that tool.

    `charter.naming` argues that a published name is a function of the tool
    alone: qualifying "just some" of a surface breaks every allow-list and log
    grep over it silently, and a mode suffix would do the same thing one axis
    over. Nothing about a tool's identity is a deployment decision.
    """
    tool = _reports()
    for mode in TIERS:
        variant = tool.with_mode(mode)
        assert variant.name == tool.name
        assert variant.pack == tool.pack

    session = ToolSession([tool], mode="pro")
    assert list(session.tools) == ["rep__reports_create"]


def test_the_label_already_applied_hands_back_the_tool_itself():
    """Identity, not an equal copy: the views it has built are worth keeping.

    The test is the *deployment's* label, and only that one. Asking for the
    label a tool was declared with resolves to the same view, so it could return
    the tool too — and then `session_mode` would be unset on those tools and set
    on the ones beside them, and `egress_map` would report one deployment two
    ways depending on which labels the pack happened to use internally. Three
    schema builds on the widest pack that has any is the whole saving, against
    an audit artifact that varies with a coincidence.
    """
    plain = _reports()
    assert plain.with_mode(None) is plain

    pro = plain.with_mode("pro")
    assert pro.with_mode("pro") is pro
    assert pro.with_mode("max") is not pro

    declared = _reports(mode="pro")
    at_pro = declared.with_mode("pro")
    assert at_pro is not declared, "the deployment's label went unrecorded"
    assert at_pro.modes == declared.modes, "and yet the view is the same one"


# ----------------------------------------------------------------------
# precedence
# ----------------------------------------------------------------------


def test_a_session_mode_adds_its_label_to_the_one_the_tool_was_built_with():
    """Not replaces. The deployer is downstream of the author, not instead of.

    The original reading was that the deployer wins outright, on the argument
    that anything else makes the parameter inert on exactly the tools that use
    `Mode`. It is inert on nothing: a label a deployment passes turns on the
    fields carrying that label, on every tool, whatever the pack declared. What
    the first reading actually cost was the author's operation split, silently,
    and a deployer cannot use a parameter whose effect depends on a pack's
    private labelling convention.
    """
    session = ToolSession([_reports(mode="free")], mode="max")
    resolved = session.tools["rep__reports_create"]
    assert resolved.mode == "free" and resolved.session_mode == "max"
    # Nothing in `Report` carries `free`, so `max` is the whole of what is added.
    assert _fields(resolved) == TIERS["max"]


def test_a_session_mode_composes_with_the_operation_split_the_author_declared():
    """The two ends of `Mode` answer different questions, so both stay in force.

    A pack that separates `create` from `update` has written an *operation* into
    those labels: create replaces and update merges, and that is not a
    deployment decision. A tier is. Replacing the first with the second made a
    session mode silently delete the operation — at `pro`, `messages_create`
    stopped being a create — and which fields a tool lost depended on whether
    its author had happened to use `Mode` for operations, which is not something
    a deployer can predict pack by pack. It made the parameter unusable on any
    surface assembled from packs somebody else wrote.

    Both labels resolve the view together. The tier adds the fields carrying it
    and takes nothing away.
    """

    class Message(BaseModel):
        account_id: Annotated[str, Path()]
        id: Annotated[Optional[str], Body(), Mode("update")] = None
        subject: Annotated[Optional[str], Body(), Mode("create")] = None
        tier_note: Annotated[Optional[str], Body(), Mode("pro")] = None
        always: Annotated[Optional[str], Body()] = None

    factory = _factory("msg")

    def op(name, mode):
        return factory(
            name=name,
            args_schema=Message,
            method="POST",
            url_template="m/{account_id}",
            description="An operation.",
            mode=mode,
        )

    create, update = op("messages_create", "create"), op("messages_update", "update")
    assert _fields(create) == ["account_id", "always", "subject"]
    assert _fields(update) == ["account_id", "always", "id"]

    session = ToolSession([create, update], mode="pro")
    at = session.tools
    assert _fields(at["msg__messages_create"]) == ["account_id", "always", "subject", "tier_note"]
    assert _fields(at["msg__messages_update"]) == ["account_id", "always", "id", "tier_note"]


def test_a_tier_the_deployment_did_not_buy_takes_nothing_away():
    """The other half of the same guarantee, and the one worth stating alone.

    Whatever the pack did with `Mode`, a session label can only ever *add* the
    fields carrying it. A deployment that asks for a tier with no extra fields on
    a given tool gets that tool exactly as the pack ships it — so reading a pack
    is not a prerequisite for using a session mode safely.
    """

    class Message(BaseModel):
        account_id: Annotated[str, Path()]
        subject: Annotated[Optional[str], Body(), Mode("create")] = None
        tier_note: Annotated[Optional[str], Body(), Mode("pro")] = None

    create = _factory("plain")(
        name="messages_create",
        args_schema=Message,
        method="POST",
        url_template="m/{account_id}",
        description="Create.",
        mode="create",
    )
    shipped = _fields(create)
    for tier in ("free", "enterprise", "eu", "some-label-no-field-carries"):
        assert _fields(create.with_mode(tier)) == shipped, f"tier {tier!r} moved the surface"


def test_the_labels_in_force_are_both_of_them_and_are_readable():
    """`Tool.modes` is the resolved pair, and it is what filters the view."""
    plain = _reports()
    assert plain.modes == frozenset()

    pro = plain.with_mode("pro")
    assert pro.mode is None and pro.session_mode == "pro"
    assert pro.modes == frozenset({"pro"})

    create = _reports(mode="create")
    at_pro = create.with_mode("pro")
    assert at_pro.mode == "create", "the author's operation survived the deployment's label"
    assert at_pro.session_mode == "pro"
    assert at_pro.modes == frozenset({"create", "pro"})


def test_clearing_the_session_label_leaves_the_tool_the_pack_ships():
    """`with_mode(None)` drops the deployment's label, not the author's."""
    create = _reports(mode="create")
    assert create.with_mode("pro").with_mode(None).modes == frozenset({"create"})
    assert create.with_mode(None) is create


# ----------------------------------------------------------------------
# the author's floor
# ----------------------------------------------------------------------


def test_no_mode_reaches_a_field_the_author_withheld_unconditionally():
    """`response_only` and `disabled` are refused without consulting the mode.

    This is the line that makes `with_mode` safe to hand to a deployer even
    though, unlike a projection, it can widen. A deployer can choose which of the
    author's *optional* surfaces this conversation is. What the author marked
    absent is absent at every label, including labels the author never wrote
    down, so there is no string a deployment can pass that widens egress past
    what the declaration allows.
    """

    class Locked(BaseModel):
        account_id: Annotated[str, Path()]
        etag: Annotated[Optional[str], Body(), Mode("response_only")] = None
        internal: Annotated[Optional[str], Body(), Mode("disabled")] = None
        tiered: Annotated[Optional[str], Body(), Mode("pro")] = None

    tool = _factory("lock")(
        name="locked_create",
        args_schema=Locked,
        method="POST",
        url_template="l/{account_id}",
        description="Locked.",
    )

    for mode in (None, "pro", "response_only", "disabled", "anything-at-all"):
        fields = set(tool.with_mode(mode).llm_schema().model_fields)
        assert "etag" not in fields, f"mode={mode!r} exposed a response-only field"
        assert "internal" not in fields, f"mode={mode!r} exposed a disabled field"


def test_a_mode_can_widen_relative_to_the_tool_it_came_from():
    """Which is why this is not `derived()`.

    A projection can only ever remove, and that single property is what makes one
    safe to hand to whoever owns a deployment. Resolving a mode rebuilds the view
    from the declarations, so against the tool it came from it adds as readily as
    it removes. Putting `mode=` on `derived()` would have cost that sentence.
    """
    free = _reports(mode="free")
    assert _fields(free) == ["account_id"]
    assert _fields(free.with_mode("max")) == TIERS["max"]


# ----------------------------------------------------------------------
# composition with a projection
# ----------------------------------------------------------------------


class Listing(BaseModel):
    account_id: Annotated[str, Path()]
    q: Annotated[Optional[str], Query()] = None
    page_size: Annotated[Optional[int], Query()] = None
    cursor: Annotated[Optional[str], Query()] = None
    raw_events: Annotated[Optional[list], Body(), Mode("pro, max")] = None


def _listing() -> Tool:
    return _factory("lst")(
        name="listings_list",
        args_schema=Listing,
        method="GET",
        url_template="l/{account_id}",
        description="List.",
    )


def test_a_projection_survives_the_mode_that_resolves_it():
    """Both restrictions hold, and neither is a special case of the other.

    A deployer narrows a tool once, at startup, and keys the surface to a tier
    per conversation. If the mode rebuilt the view from the pack's declarations
    and forgot the projection, the narrowing would come off on exactly the
    sessions that asked for a tier.
    """
    narrowed = _listing().derived(name="listings_list", drop={"cursor"})
    pro = narrowed.with_mode("pro")

    assert "cursor" not in pro.llm_schema().model_fields, "the projection came off"
    assert "raw_events" in pro.llm_schema().model_fields, "the mode did not resolve"
    assert pro._prune == narrowed._prune

    free = narrowed.with_mode("free")
    assert sorted(free.llm_schema().model_fields) == ["account_id", "page_size", "q"]


def test_a_pin_survives_the_mode_and_still_sends_its_value():
    pinned = _listing().derived(name="listings_list", pin={"q": "kind=report"})
    pro = pinned.with_mode("pro")

    assert "q" not in pro.llm_schema().model_fields
    assert pro._pins == {"q": "kind=report"}
    assert "q" in pro._exec_schema.model_fields, "the pinned value has nowhere to go"


def test_a_mode_that_hides_a_pinned_field_is_refused_where_it_is_asked_for():
    """Rather than on every call, which is where it would otherwise land.

    The pinned value is merged into the executed view and revalidated, and that
    view forbids extras, so a pin whose field the mode removed fails every call
    with a validation error naming a field the deployer never set. Raised where
    the mode is asked for instead, naming the mode and the field.
    """
    pinned = _listing().derived(name="listings_list", pin={"raw_events": [1]})

    # `pro` names the field, so the pin still has somewhere to go.
    at_pro = pinned.with_mode("pro")
    assert at_pro._exec_schema.model_fields["raw_events"] is not None
    assert "raw_events" not in at_pro.llm_schema().model_fields

    with pytest.raises(DeclarationError, match="mode 'free' withholds 'raw_events'"):
        pinned.with_mode("free")
    with pytest.raises(DeclarationError, match="mode 'free' withholds 'raw_events'"):
        ToolSession([pinned], mode="free")


def test_a_field_no_mode_can_see_cannot_be_pinned_at_all():
    """The same failure one step earlier, and it does not blame the mode.

    A pin on a `response_only` field was accepted at declaration and then failed
    every call with `Extra inputs are not permitted` naming a field the caller
    never set: the value check skipped a field it could not find in the executed
    view. No label fixes that one, so the message says so rather than pointing at
    whichever mode happened to be resolving.
    """

    class Locked(BaseModel):
        account_id: Annotated[str, Path()]
        etag: Annotated[Optional[str], Body(), Mode("response_only")] = None
        internal: Annotated[Optional[str], Body(), Mode("disabled")] = None

    tool = _factory("locked")(
        name="locked_create",
        args_schema=Locked,
        method="POST",
        url_template="l/{account_id}",
        description="Locked.",
    )

    for field in ("etag", "internal"):
        with pytest.raises(DeclarationError, match="withheld from the model at every mode"):
            tool.derived(name="locked_create", pin={field: "x"})


# ----------------------------------------------------------------------
# a label, or nothing
# ----------------------------------------------------------------------


@pytest.mark.parametrize("empty", ["", "   ", 0, False])
def test_an_empty_mode_is_refused_rather_than_read_as_no_mode(empty):
    """The one direction a deployer's label must never move egress.

    `should_include_field` guards on `if mode`, so every falsy mode reads as "no
    mode at all" — which is the *widest* view, where each custom label is inert
    and every tiered field is offered. `None` is how that is asked for, and the
    session checks for it by identity before it copies anything.

    An empty string is not that. It arrives from `plan_of(request.user)`, where a
    nullable plan column or a `user.plan or ""` hands back `""` for the smallest
    tier, and reading it as "no tier" serves that user every tier. Every other
    way a label can be wrong fails closed — `"prro"` matches nothing and
    withholds everything optional — so this is the only one worth a check.
    """
    for build in (
        lambda: _reports(mode=empty),
        lambda: _reports().with_mode(empty),
        lambda: ToolSession([_reports()], mode=empty),
    ):
        with pytest.raises(DeclarationError, match="is not a label"):
            build()


def test_an_empty_mode_does_not_widen_a_tool_that_shipped_with_one():
    """Which is the half that makes it egress rather than ergonomics.

    A session mode replaces the author's, so `""` does not merely fail to narrow
    a plain tool — it takes a tool the pack shipped at `free` and resolves it at
    every label the schema declares.
    """
    free = _reports(mode="free")
    assert _fields(free) == ["account_id"]
    with pytest.raises(DeclarationError, match="is not a label"):
        ToolSession([free], mode="")


def test_a_session_with_no_tools_still_vets_its_mode():
    """`Tool` is where a mode is checked, and a session may reach no `Tool`."""
    with pytest.raises(DeclarationError, match="on ToolSession"):
        ToolSession([], mode="")


def test_a_label_that_matches_nothing_is_still_a_label():
    """Fail-closed, so it is not this check's business.

    A typo cannot be told from a tier that has no extra fields, and refusing
    every label no field names would make a pack's first `Mode` a breaking
    change for every tool beside it.
    """
    assert _fields(_reports().with_mode("prro")) == ["account_id"]
    assert _fields(_reports().with_mode(" pro")) == ["account_id"]


# ----------------------------------------------------------------------
# a required field survives the label
# ----------------------------------------------------------------------


class Ledger(BaseModel):
    """`ledger` is required by the API and labelled with a tier."""

    account_id: Annotated[str, Path()]
    ledger: Annotated[str, Body(), Mode("pro")]
    note: Annotated[Optional[str], Body()] = None


def _ledger(**kw) -> Tool:
    return _factory("led")(
        name="ledgers_create",
        args_schema=Ledger,
        method="POST",
        url_template="l/{account_id}",
        description="Create a ledger.",
        **kw,
    )


def test_a_mode_that_hides_a_required_field_is_refused_where_it_is_asked_for():
    """The same argument as the pin check, one axis over.

    `Mode` moves visibility and requiredness is a separate axis, so a label can
    take a *required* field out of the view and nothing puts it back: the tool
    constructs, validates a call that never mentions the field, and sends a body
    without it. A 400 on every call, naming a field the deployer never saw
    offered. `derived(drop=...)` already refuses precisely this removal; reached
    through a label it went unchecked, which mattered little while only the pack
    author could write `mode=` and matters now that a deployer can.
    """
    with pytest.raises(DeclarationError, match="is required by the API"):
        _ledger().derived(name="ledgers_create", drop={"ledger"})

    for build in (
        lambda: _ledger(mode="free"),
        lambda: _ledger().with_mode("free"),
        lambda: ToolSession([_ledger()], mode="free"),
    ):
        with pytest.raises(DeclarationError, match="mode 'free' withholds 'ledger'"):
            build()


def test_the_label_that_names_the_field_is_fine():
    assert _fields(_ledger().with_mode("pro")) == ["account_id", "ledger", "note"]


def test_a_required_field_the_author_withheld_unconditionally_is_not_the_mode_s_doing():
    """`response_only` and `disabled` are refused at every label, so no label did it.

    The test is "present with no mode, absent at this one", which is the mode's
    doing exactly. Reporting the author's own unconditional choice here would
    refuse to construct tools that shipped years ago, and would blame whichever
    label happened to be resolving for a decision that had nothing to do with it.
    `egress_map` already reports those fields, with the author's reason.
    """

    class Locked(BaseModel):
        account_id: Annotated[str, Path()]
        etag: Annotated[str, Body(), Mode("response_only")]
        internal: Annotated[str, Body(), Mode("disabled")]

    tool = _factory("lk")(
        name="locked_create",
        args_schema=Locked,
        method="POST",
        url_template="l/{account_id}",
        description="Locked.",
    )
    for mode in ("free", "pro", "anything"):
        assert _fields(tool.with_mode(mode)) == ["account_id"]


def test_a_pinned_required_field_is_still_allowed_to_leave_the_view():
    """A pin is how you drop a required field on purpose, and it keeps working.

    The projection supplies the value, so the request still carries it. The check
    skips a pruned path for the same reason `_check_required` does.
    """
    pinned = _ledger().derived(name="ledgers_create", pin={"ledger": "main"})
    assert "ledger" not in pinned.llm_schema().model_fields
    assert pinned.with_mode("pro")._pins == {"ledger": "main"}


def test_the_check_reaches_a_required_field_nested_under_one_the_mode_keeps():
    """One level down is where a walk stops being obviously right.

    A required field inside a model the mode kept is as absent from the request
    as a top-level one. A required field inside a subtree the mode *removed* is
    not reported, and must not be: an optional parent that is gone takes the
    whole branch with it and the API never expects any of it.
    """

    class Inner(BaseModel):
        tier_field: Annotated[str, Body(), Mode("pro")]

    class Kept(BaseModel):
        account_id: Annotated[str, Path()]
        inner: Annotated[Optional[Inner], Body()] = None

    class Gone(BaseModel):
        account_id: Annotated[str, Path()]
        inner: Annotated[Optional[Inner], Body(), Mode("pro")] = None

    def build(schema, mode):
        return _factory("nst")(
            name="n_create",
            args_schema=schema,
            method="POST",
            url_template="n/{account_id}",
            description="n",
            mode=mode,
        )

    with pytest.raises(DeclarationError, match="'inner.tier_field'"):
        build(Kept, "free")

    # The whole optional branch is withheld, so nothing is missing from a
    # request that never carries it.
    assert _fields(build(Gone, "free")) == ["account_id"]


def test_the_check_reaches_every_member_of_a_union_not_just_the_first():
    """A guard that walks only the first branch is a hole, not a guard.

    `charter.derive._unwrap` takes the first member of a union and is right to:
    it resolves a path a person typed, and the first member is the one they
    meant. This is a completeness check, so it goes through `_models_in`
    instead — a model it does not reach is a model nobody checked, and
    `Union[Draft, Published]` would hide the second half's required field.
    """

    class Draft(BaseModel):
        tier: Annotated[str, Body(), Mode("pro")]

    class Published(BaseModel):
        other: Annotated[str, Body(), Mode("pro")]

    class Either(BaseModel):
        account_id: Annotated[str, Path()]
        thing: Annotated[Optional[Union[Draft, Published]], Body()] = None

    with pytest.raises(DeclarationError) as raised:
        _factory("un")(
            name="either_create",
            args_schema=Either,
            method="POST",
            url_template="e/{account_id}",
            description="Either.",
            mode="free",
        )
    assert "'thing.tier'" in str(raised.value)
    assert "'thing.other'" in str(raised.value), "the second union member was skipped"


def test_a_shipped_pack_keeps_its_operation_split_under_every_session_mode():
    """The property, against packs that really do use `Mode` for operations.

    gcalendar declares `write` on three tools and `import` on a fourth; gforms
    declares `create` and `update`. Those labels are what the tools *are*, and a
    deployment keying the surface to a tier has no idea they exist. Under the
    old reading, `ToolSession(gcalendar.TOOLS, mode="pro")` silently resolved
    `events_insert` at `pro` and took its `write` fields away.
    """
    from charter.packs import gcalendar, gforms

    for pack in (gcalendar, gforms):
        for tool in pack.TOOLS:
            shipped = set(tool.llm_schema().model_fields)
            for tier in ("free", "pro", "enterprise", "eu"):
                at_tier = tool.with_mode(tier)
                assert at_tier.mode == tool.mode, f"{tool.name}: the pack's label was replaced"
                offered = set(at_tier.llm_schema().model_fields)
                assert shipped <= offered, (
                    f"{tool.name} at {tier!r} lost {sorted(shipped - offered)}, "
                    f"which the tier had nothing to say about"
                )


def test_every_shipped_tool_still_constructs_at_every_label_its_pack_declares():
    """The check has to be true of what ships, or it is not shippable.

    Across the fifteen packs no required field carries a custom `Mode`, which is
    why this is a latent defect rather than a live one — and why a check for it
    can go in at all.
    """
    from charter.packs import gcalendar, gforms, gmail, stripe

    for pack in (gmail, gcalendar, gforms, stripe):
        for tool in pack.TOOLS:
            for mode in (None, "write", "import", "create", "update", "pro"):
                tool.with_mode(mode)


# ----------------------------------------------------------------------
# cost
# ----------------------------------------------------------------------


def test_tools_at_one_mode_build_their_shared_types_once_between_them():
    """The store is keyed by mode, and a variant keeps reading the pack's.

    Without this, a moded session pays for the shared type graph once per tool
    rather than once per mode: Linear's 128 tools reach the same filters, and
    that is the difference the pack's own store already exists to avoid. Identity
    is the assertion for the same reason it is on the factory's own test: equal
    shape would pass while every tool rebuilt its own copy.
    """

    class Shared(BaseModel):
        label: Annotated[Optional[str], Body()] = None
        premium: Annotated[Optional[str], Body(), Mode("pro")] = None

    class First(BaseModel):
        account_id: Annotated[str, Path()]
        item: Annotated[Optional[Shared], Body()] = None

    class Second(BaseModel):
        account_id: Annotated[str, Path()]
        other: Annotated[Optional[Shared], Body()] = None

    factory = _factory("shared")
    one = factory("one", First, "POST", "o/{account_id}", description="One.")
    two = factory("two", Second, "POST", "t/{account_id}", description="Two.")

    session = ToolSession([one, two], mode="pro")
    first = _generated(session.tools["shared__one"], "item")
    second = _generated(session.tools["shared__two"], "other")
    assert first is second, "the shared type was generated once per tool"

    # And the mode is part of the key, because it has to be: the `pro` view of
    # `Shared` carries a field the unmoded one does not, so sharing across modes
    # would hand one session the other's fields.
    free = ToolSession([one], mode="free")
    at_free = _generated(free.tools["shared__one"], "item")
    assert at_free is not first
    assert "premium" in first.model_fields and "premium" not in at_free.model_fields


@pytest.mark.parametrize("mode", [None, "write", "import", "pro"])
def test_the_shared_store_never_changes_the_answer(mode):
    """Sharing is an optimisation, so it has to be invisible in the output.

    The store is what makes a moded surface affordable, and it is also the way to
    get a subtly wrong schema: a model memoised under a key that does not capture
    everything the walk depended on comes back to a caller the walk never ran
    for. `create_llm_schema` puts the mode in that key, and this is the assertion
    that it is enough. Byte-identical JSON, not merely the same field names,
    because the failure this guards is a spliced `$defs` graph.
    """
    from charter.packs import gcalendar

    for tool in gcalendar.TOOLS:
        shared = tool.with_mode(mode)
        alone = tool.with_mode(mode)
        alone._llm_cache = None
        alone._llm_schema_built = None
        alone._json_schema = None
        assert json.dumps(shared.to_json_schema(), sort_keys=True) == json.dumps(
            alone.to_json_schema(), sort_keys=True
        ), f"{tool.name} at mode={mode!r} differs with and without the shared store"
