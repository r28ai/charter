"""
Conformance — properties every pack must have, checked mechanically.

The other test files check what a pack *does*. This one checks that a pack's
declarations are true, across all of them at once, without knowing anything
about any particular API.

It exists because of a pattern in this repository's own bug history. Six bugs
were found while writing the GitHub, Linear, Shopify and Docs packs. Five of the
six were silent — nothing raised, every call returned 200, and the whole suite
stayed green:

* every ``model_validator`` was dropped from the derived LLM view, so every
  ``oneof`` in the repository was enforced against the wire schema and never
  against the model's input;
* two Google packs sent snake_case query parameters, which Google ignores, so
  every filter was silently discarded;
* a Relay pagination could not reach ``pageInfo.hasNextPage`` and never
  terminated;
* a factory-level pagination labelled twenty-two retrieve and write endpoints
  with a cursor parameter they do not accept;
* failure detection was written into per-tool response handlers, where the
  first tool added without one reports a failed write as a success.

Every one of them is mechanically checkable, which is what the checks below do.

A test that only passes is doing nothing. Each check here was verified by
breaking the property on purpose and confirming it failed — nine of the ten
mutations tried were caught, and the tenth is named below as a known gap rather
than papered over.

Three properties this file deliberately does **not** check, because they are not
decidable from the declarations alone:

* **Whether ``more_field`` is needed.** Google omits ``nextPageToken`` on the
  last page, so the cursor fallback is correct there; a Relay connection sends
  one, so it is not. Rather than guess, the termination test checks the
  behaviour that matters, and requires ``more_field`` only where the cursor path
  says Relay.
* **Whether a declaration names the *right* key.** ``items_field="nope"`` is
  self-consistent: this file builds its fixtures from the same declaration it is
  checking, so it cannot tell a wrong key from a right one. Only a recorded
  response can, which is what the per-pack ``respx`` tests are for.
* **Whether a schema matches the vendor's current API.** That is drift, and it
  needs the published spec — GitHub's OpenAPI, Google's discovery documents,
  Linear's and Shopify's GraphQL SDL — rather than introspection.
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import re
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Type

import pytest
from pydantic import BaseModel
from pydantic.alias_generators import to_camel

from charter.execution.schema import LLMBase
from charter.tool import Tool
from charter.types import Mode
from charter.types.markers import Body, Gloss, Query

PACK_NAMES = [
    "gmail",
    "gcalendar",
    "gsheets",
    "gdocs",
    "gdrive",
    "gforms",
    "slack",
    "github",
    "stripe",
    "linear",
    "shopify",
    "firecrawl",
    "notion",
    "granola",
    "tavily",
]

PACKS = {name: importlib.import_module(f"charter.packs.{name}") for name in PACK_NAMES}


def _submodules(package):
    """Every module under a pack's ``types`` package, imported."""
    found = []
    path = getattr(package, "__path__", None)
    if path is None:
        return found
    for info in pkgutil.walk_packages(path, prefix=f"{package.__name__}."):
        try:
            found.append(importlib.import_module(info.name))
        except Exception:
            continue
    return found


GOOGLE_PACKS = ["gmail", "gcalendar", "gsheets", "gdocs", "gdrive", "gforms"]

ALL_TOOLS = [(name, tool) for name, pack in PACKS.items() for tool in pack.TOOLS]
PAGING_TOOLS = [(n, t) for n, t in ALL_TOOLS if t.pagination is not None]

# Endpoints that genuinely list, and are a POST because the query does not fit
# in a URL. Enumerated rather than inferred: see
# test_only_endpoints_that_page_declare_pagination.
POST_LIST_ENDPOINTS = {
    ("notion", "search"),
    ("notion", "data_sources_query"),
}

# PATCH endpoints that are an *operation* rather than a partial update of a
# resource, and whose argument is therefore mandatory: appending blocks with no
# blocks, or replacing a page's Markdown with no Markdown, are not requests with
# a sensible meaning. See test_a_patch_body_mandates_nothing.
PATCH_OPERATIONS = {
    ("notion", "blocks_children_append"),
    ("notion", "pages_update_markdown"),
}


def _ids(pairs):
    return [f"{pack}.{tool.name}" for pack, tool in pairs]


def _accepts(schema: Type[BaseModel], name: str) -> bool:
    """Whether ``schema`` accepts ``name``, allowing for the LLM view's aliases.

    A declaration may spell a field the way the *wire* spells it while the schema
    spells it snake_case — ``cursor_param="pageToken"`` against a ``page_token``
    field. The LLM view accepts both, so both are correct here.
    """
    fields = schema.model_fields
    if name in fields:
        return True
    return any(to_camel(field) == name for field in fields)


# -----------------------------------------------------
# Declarations must name something real
# -----------------------------------------------------


@pytest.mark.parametrize("pack, tool", PAGING_TOOLS, ids=_ids(PAGING_TOOLS))
def test_a_pagination_names_fields_the_schema_accepts(pack: str, tool: Tool):
    """A cursor with nowhere to go is a declaration that cannot be followed."""
    pagination = tool.pagination
    assert pagination is not None
    declared = [
        pagination.cursor_param,
        pagination.page_param,
        pagination.per_page_param,
    ]
    for param in [p for p in declared if p]:
        # A dotted param reaches into a nested argument; the root is the field.
        root = param.split(".")[0]
        assert _accepts(tool.args_schema, root), (
            f"{pack}.{tool.name} declares {param!r}, but its schema has no such "
            f"field: {sorted(tool.args_schema.model_fields)}"
        )


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_only_endpoints_that_page_declare_pagination(pack: str, tool: Tool):
    """Declared on a factory, pagination lands on every retrieve and write too.

    That was twenty-two wrong declarations across four shipped packs: a
    `balance_retrieve` advertising `starting_after`, a `chat_postMessage`
    advertising `cursor`. Harmless at runtime, and wrong — and anything built on
    the declaration inherits the error.

    A GET is the usual shape of a list, and a GraphQL query is a POST carrying a
    constant document, so those two pass on their own. The third shape is an API
    that lists through a POST because the query is too big for a URL — Notion's
    search and data source query take a whole filter tree in the body. Those are
    named here one at a time rather than admitted by a rule, because the point
    of this check is that a *write* cannot quietly claim to paginate, and
    "POST with a body" is every write there is.
    """
    if tool.pagination is None:
        return
    if (pack, tool.name) in POST_LIST_ENDPOINTS:
        return
    assert tool.method == "GET" or tool.static_body is not None, (
        f"{pack}.{tool.name} is a {tool.method} that declares pagination"
    )


@pytest.mark.parametrize("pack, tool", PAGING_TOOLS, ids=_ids(PAGING_TOOLS))
def test_a_pagination_walk_terminates(pack: str, tool: Tool):
    """The end of a list must be reachable, whatever the API's convention.

    Checked behaviourally rather than by inspecting `more_field`, because
    whether that field is needed depends on something no declaration records:
    Google omits its cursor on the last page, Relay sends one.
    """
    pagination = tool.pagination
    assert pagination is not None

    if pagination.style == "page":
        previous: Dict[str, Any] = {pagination.per_page_param: 2, pagination.page_param: 1}

        def wrap(items: List[Any]) -> Any:
            return {pagination.items_field: items} if pagination.items_field else items

        # It must advance while pages come back full...
        assert pagination.next_page_args(wrap([{"id": 1}, {"id": 2}]), previous) is not None, (
            f"{pack}.{tool.name} stops on a full page — it would read only page one"
        )
        # ...and stop when one comes back short or empty.
        assert pagination.next_page_args(wrap([{"id": 1}]), previous) is None
        assert pagination.next_page_args(wrap([]), previous) is None
        return

    # Cursor style. A last page arrives in one of two shapes, and which one
    # decides whether `more_field` is optional.
    assert pagination.next_page_args({}, {}) is None, (
        f"{pack}.{tool.name} does not stop when the cursor is absent"
    )

    # A Relay connection sends `endCursor` on its last page too, so the "a
    # non-empty cursor means another page" fallback never terminates against
    # one. `pageInfo` in the path is the reliable signal that this is Relay.
    if "pageInfo" in (pagination.cursor_field or ""):
        assert pagination.more_field, (
            f"{pack}.{tool.name} pages a Relay connection with no more_field. "
            f"Relay sends endCursor on the last page, so the cursor fallback "
            f"would walk forever — declare pageInfo.hasNextPage."
        )

    if pagination.more_field:
        exhausted = _nest(pagination.more_field, False)
        _merge(exhausted, _nest(pagination.cursor_field or "", "a-stale-cursor"))
        assert pagination.next_page_args(exhausted, {}) is None, (
            f"{pack}.{tool.name} keeps paging after the API said there is no more"
        )
        # And it must still advance while the API says there is more.
        live = _nest(pagination.more_field, True)
        _merge(live, _nest(pagination.cursor_field or "", "next-cursor"))
        assert pagination.next_page_args(live, {}) is not None, (
            f"{pack}.{tool.name} stops while the API says there is another page"
        )


def _nest(path: str, value: Any) -> Dict[str, Any]:
    """Build the smallest response body that puts ``value`` at ``path``.

    ``"pageInfo.hasNextPage"`` -> ``{"pageInfo": {"hasNextPage": value}}``, and
    ``"data[-1].id"`` -> ``{"data": [{"id": value}]}`` — a bracketed segment
    means a list, which is how Stripe's derived cursor is written.
    """
    if not path:
        return {}
    built: Any = value
    for segment in reversed(path.split(".")):
        key, bracket, _ = segment.partition("[")
        if bracket:
            built = [built]
        built = {key: built}
    return built


def _merge(target: Dict[str, Any], extra: Dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value


# -----------------------------------------------------
# Failure detection belongs to the contract layer
# -----------------------------------------------------


@pytest.mark.parametrize("pack", PACK_NAMES)
def test_no_response_handler_decides_whether_a_call_failed(pack: str):
    """Failure detection is a fact about the API, so it is declared, not written.

    In a response handler the check is opt-in per tool, and the first tool added
    without it reports a failed write as a success. That is the shape this
    project has removed three times: Slack's `ok:false`, the API-key guard, and
    the GraphQL mutation check.
    """
    try:
        handlers = importlib.import_module(f"charter.packs.{pack}.response_handlers")
    except ModuleNotFoundError:
        return

    source = inspect.getsource(handlers)
    for forbidden in ("raise APIError", "raise CredentialError"):
        assert forbidden not in source, (
            f"charter.packs.{pack}.response_handlers contains {forbidden!r}. Failure "
            f"detection belongs on an Envelope, where the runtime enforces it on "
            f"every call — including tools added later."
        )


@pytest.mark.parametrize("pack", PACK_NAMES)
def test_an_envelope_is_declared_once_for_the_whole_api(pack: str):
    """Every tool in a pack sees the same failure predicate, or none does."""
    envelopes = {id(t.envelope) for t in PACKS[pack].TOOLS}
    assert len(envelopes) == 1, (
        f"charter.packs.{pack} declares different envelopes on different tools; a "
        f"success predicate is a property of the API"
    )


# -----------------------------------------------------
# The LLM view must keep the schema's promises
# -----------------------------------------------------


# LLMBase declares a validator of its own, which every generated model inherits.
# Counting it would make any derived model look as though it carried the wire
# schema's rules — the check would then pass on a model with none.
_INHERITED = frozenset(LLMBase.__pydantic_decorators__.model_validators)
_INHERITED_FIELD_RULES = frozenset(LLMBase.__pydantic_decorators__.field_validators)


def _withheld(field: Any) -> bool:
    """True if this field, and its whole subtree, is kept out of the LLM view.

    ``Mode("response_only")`` and ``Mode("disabled")`` are the two the runtime
    enforces whatever mode a tool is in. A rule on a model reachable only through
    such a field is not missing from ``llm_schema()`` — the model is, and that is
    the marker doing its job.
    """
    for marker in field.metadata or ():
        if isinstance(marker, Mode) and marker.modes & {"response_only", "disabled"}:
            return True
    return False


def _nested_models(model: Type[BaseModel]) -> Iterator[Type[BaseModel]]:
    """Every model reachable from ``model``'s fields the LLM view still shows."""
    for field in model.model_fields.values():
        if _withheld(field):
            continue
        annotation = field.annotation
        for candidate in [annotation, *getattr(annotation, "__args__", ())]:
            for item in [candidate, *getattr(candidate, "__args__", ())]:
                if isinstance(item, type) and issubclass(item, BaseModel):
                    yield item


def _rules(
    model: Type[BaseModel], seen: Set[Any] | None = None
) -> Dict[Tuple[str, str], Tuple[str, ...]]:
    """Every validator in a schema tree, as ``(model, rule) -> fields judged``.

    A model validator judges the whole object, so its fields are empty. A field
    validator names the fields it is registered for, which is what decides
    whether the LLM view is allowed to have dropped it: ``_carry_validators``
    skips one whose every target was filtered out by ``Mode``, because Pydantic
    rejects a validator naming a field the model does not have.

    Naming each rule rather than each model is what makes the check catch a
    model that kept one of its two rules.
    """
    seen = seen if seen is not None else set()
    if model in seen:
        return {}
    seen.add(model)

    name = model.__name__.removesuffix("_LLM")
    decorators = model.__pydantic_decorators__
    found: Dict[Tuple[str, str], Tuple[str, ...]] = {
        (name, rule): ()
        for rule in set(decorators.model_validators) - _INHERITED
    }
    for rule, decorator in decorators.field_validators.items():
        if rule in _INHERITED_FIELD_RULES:
            continue
        found[(name, rule)] = tuple(decorator.info.fields)

    for nested in _nested_models(model):
        found.update(_rules(nested, seen))
    return found


def _visible_fields(
    model: Type[BaseModel], seen: Set[Any] | None = None
) -> Dict[str, Set[str]]:
    """``{model name: the fields it still declares}``, walked the same way."""
    seen = seen if seen is not None else set()
    if model in seen:
        return {}
    seen.add(model)

    found = {model.__name__.removesuffix("_LLM"): set(model.model_fields)}
    for nested in _nested_models(model):
        found.update(_visible_fields(nested, seen))
    return found


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_every_cross_field_rule_survives_into_the_llm_view(pack: str, tool: Tool):
    """The model's input is the one that needs checking, and it was not checked.

    ``create_model`` builds a new class and validators are not fields, so every
    ``oneof`` a pack author wrote was enforced against the wire schema and
    dropped from the view the model fills in.

    Both kinds count. A rule that judges two fields is a ``model_validator`` and
    a rule that judges one is a ``field_validator``, and which one a pack author
    reached for is a fact about the rule's shape rather than about how much it
    matters — Granola's "``workspace`` cannot be mixed with another scope" is a
    field validator, and dropping it would be as silent as dropping a oneof.
    """
    wire = _rules(tool.args_schema)
    llm = _rules(tool.llm_schema())
    visible = _visible_fields(tool.llm_schema())

    missing = []
    for (model, rule), judged in wire.items():
        if model not in visible:
            # The whole model is gone from the LLM view, so its rules are not
            # missing — the Mode marker withheld the subtree, on purpose.
            continue
        if judged and not set(judged) & visible[model]:
            # Every field this rule judges is withheld, and Pydantic will not
            # accept a validator naming a field the model does not have.
            continue
        if (model, rule) not in llm:
            missing.append(f"{model}.{rule}")

    assert not missing, (
        f"{pack}.{tool.name}: rules {sorted(missing)} are enforced on the wire "
        f"schema but not on llm_schema(), which is what validates model input"
    )


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_no_optional_field_is_secretly_required(pack: str, tool: Tool):
    """An ``Annotated[Optional[str], Query()]`` with no ``= None`` is required.

    The single most common bug in a hand-written pack, and invisible until a
    model is forced to invent a value for a filter it did not want.
    """
    required = tool.to_json_schema()["parameters"].get("required", [])
    for name in required:
        field = tool.args_schema.model_fields.get(name)
        if field is None:
            continue
        annotation = str(field.annotation)
        assert "Optional" not in annotation and "NoneType" not in annotation, (
            f"{pack}.{tool.name}.{name} is Optional yet required — it is missing "
            f"a `= None` default"
        )


# -----------------------------------------------------
# A method's semantics are part of its contract
# -----------------------------------------------------


def _body_models(tool: Tool, *, obliged_only: bool = False) -> List[Type[BaseModel]]:
    """The models a tool sends as its request body, in the LLM's view.

    ``obliged_only`` keeps the ones reached through a *required* body field —
    the models a caller has to fill in to call the tool at all.
    """
    found: List[Type[BaseModel]] = []
    for field in tool.llm_schema().model_fields.values():
        if not any(isinstance(m, Body) for m in field.metadata):
            continue
        if obliged_only and not field.is_required():
            continue
        annotation = field.annotation
        for candidate in [annotation, *getattr(annotation, "__args__", ())]:
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                found.append(candidate)
    return found


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_a_patch_body_mandates_nothing(pack: str, tool: Tool):
    """PATCH means "change these, leave the rest", so its body mandates nothing.

    The way this breaks is reuse: one resource model serves create, update and
    patch, and the field that create legitimately requires is then required on
    the endpoint whose whole purpose is not having to send it. Recolouring a
    Gmail label would mean reading the label first just to echo its name back.

    The wrapper field stays required — you must send *a* body. It is the
    contents that must all be optional.

    Which is also the limit of it: what makes a requirement a bug is being
    *forced* into it. A body field that is itself optional is one the caller
    opts into — Firecrawl's monitor webhook is replaced whole or left alone,
    and a webhook without a URL is not a webhook, so its ``url`` is the API's
    own shape rather than a create model leaking into an update. Every other
    PATCH body in the packs is reached through a required field, so this costs
    the check nothing on them.

    The exceptions are listed in ``PATCH_OPERATIONS``, and they are exceptions
    to the *premise* rather than to the rule: those endpoints do not patch a
    resource, they perform an operation whose argument happens to travel as a
    PATCH body. Reuse of a resource model — the bug this check exists for —
    cannot happen there, because there is no resource model.
    """
    if tool.method != "PATCH":
        return
    if (pack, tool.name) in PATCH_OPERATIONS:
        return

    for model in _body_models(tool, obliged_only=True):
        required = [n for n, f in model.model_fields.items() if f.is_required()]
        assert not required, (
            f"{pack}.{tool.name} is a PATCH whose body {model.__name__} requires "
            f"{required}; a partial update cannot demand a field it is not changing"
        )


# -----------------------------------------------------
# Casing must match the API, not the default
# -----------------------------------------------------


@pytest.mark.parametrize("pack", GOOGLE_PACKS)
def test_google_packs_send_camel_cased_query_parameters(pack: str):
    """Google's query parameters are camelCase, and it ignores what it cannot read.

    Two shipped packs sent `max_results` and `value_render_option` for weeks.
    Every call returned 200 with unfiltered results.
    """
    for tool in PACKS[pack].TOOLS:
        snake = [
            name
            for name, field in tool.args_schema.model_fields.items()
            if "_" in name and any(isinstance(m, Query) for m in field.metadata)
        ]
        if snake:
            assert tool.query_case == "camel", (
                f"{pack}.{tool.name} has snake_case query fields {snake} but "
                f"query_case={tool.query_case!r}; Google would ignore them"
            )


# -----------------------------------------------------
# Every tool is usable by a model and describable to a person
# -----------------------------------------------------


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_every_tool_is_described_for_both_audiences(pack: str, tool: Tool):
    assert tool.description.strip(), f"{pack}.{tool.name} has no description"
    assert tool.action_label, f"{pack}.{tool.name} has no action_label"


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_every_tool_builds_a_well_formed_function_definition(pack: str, tool: Tool):
    definition = tool.to_json_schema()
    assert definition["name"] == tool.name
    assert definition["parameters"]["type"] == "object"


@pytest.mark.parametrize("pack, tool", ALL_TOOLS, ids=_ids(ALL_TOOLS))
def test_a_static_constant_is_never_reachable_from_tool_arguments(pack: str, tool: Tool):
    """Constants are infrastructure. A model that can set one can redirect the call."""
    fields = set(tool.llm_schema().model_fields)
    for constant in (tool.static_headers or {}), (tool.static_body or {}):
        for key in constant:
            assert key not in fields, (
                f"{pack}.{tool.name} declares {key!r} as a constant and also exposes "
                f"it as a tool argument"
            )


@pytest.mark.parametrize("pack", PACK_NAMES)
def test_a_pack_exports_exactly_the_tools_it_names(pack: str):
    """A reference taken by name must be the object configure() reaches."""
    module = PACKS[pack]
    for tool in module.TOOLS:
        assert getattr(module, tool.name, None) is tool, (
            f"charter.packs.{pack}.{tool.name} is not the object in TOOLS"
        )
    names: List[str] = [t.name for t in module.TOOLS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("pack_name", PACK_NAMES)
def test_every_model_facing_parameter_is_described(pack_name):
    """A parameter with no description is one the model chooses blind.

    gcalendar shipped nineteen of them — `singleEvents` decides whether recurring
    events come back expanded, and the model had nothing to go on. It went
    unnoticed because the benchmark harness substituted the pydantic-derived
    title, so every measurement was taken against a schema the SDK does not emit.
    """
    module = importlib.import_module(f"charter.packs.{pack_name}")
    missing = [
        f"{tool.name}.{name}"
        for tool in module.TOOLS
        for name, prop in (tool.to_json_schema()["parameters"].get("properties") or {}).items()
        if not (prop.get("description") or "").strip() and not prop.get("$ref")
    ]
    assert not missing, f"{pack_name} ships undescribed parameters: {missing}"


# A field the vendor marks server-owned that the model is still offered, with the
# reason each one is not a bug. Every entry was read on the vendor's own
# reference page, because the phrase alone does not settle it: two of these are
# conditionally read-only and two are sentences about something else.
_SERVER_OWNED_EXCEPTIONS = {
    # "If this sheet is a DATA_SOURCE sheet, this field is output only" — so it
    # is writable on the grid sheets a caller actually creates.
    ("gsheets", "gridProperties"),
    # "Read only when true. When false, you can set to true."
    ("gsheets", "importFunctionsExternalUrlAccessAllowed"),
    # The content restriction a caller sets. "read-only" is what the field
    # means, not who owns it.
    ("gdrive", "readOnly"),
    # "If only read-only fields such as calendar properties or ACLs have
    # changed" — the phrase describes other fields in the same sentence.
    ("gcalendar", "syncToken"),
    # "Output only ... `documentTitle` can be set on create, but cannot be
    # modified by a batchUpdate request." Google's own next sentence contradicts
    # the marker, and `Mode("create")` is why this is offered on forms_create
    # and on nothing else.
    ("gforms", "documentTitle"),
    # "Read only. The question ID. On creation, it can be provided..." — and
    # UpdateItemRequest is documented as a read-modify-write that keeps the ID,
    # so withholding it would break the only way to edit a question.
    ("gforms", "questionId"),
}

_SAYS_SERVER_OWNED = re.compile(r"output only|read-only|read only", re.I)


def _described_leaves(
    node: Dict[str, Any],
    defs: Dict[str, Any],
    path: str = "",
    seen: Optional[Set[str]] = None,
):
    """(path, description) for every described field in a published schema.

    ``seen`` is one set for the whole walk rather than a per-branch trail. A
    trail is what this data punishes: Linear's filter types are mutually
    referential, so routes through them multiply, and walking `teams_list` that
    way produced 13,936,305 leaves in 30 seconds without finishing. With 17 such
    tools in the pack the test could not complete at all, which is why it had
    never been seen to finish since the Linear schemas began generating.

    What the single set costs is multiplicity, not coverage. Every definition is
    still visited, and every described field in it reported; a definition reached
    from two places is reported at the first path that reaches it. The question
    here is whether a server-owned field is offered anywhere, so one route to it
    answers it and a thousand only bury the answer."""
    seen = set() if seen is None else seen
    for name, prop in (node.get("properties") or {}).items():
        here = f"{path}.{name}" if path else name
        if prop.get("description"):
            yield here, prop["description"]
        options = [o for o in prop.get("anyOf", []) if o.get("type") != "null"]
        target = options[0] if len(options) == 1 else prop
        ref = target.get("$ref") or (target.get("items") or {}).get("$ref")
        if not ref:
            continue
        key = ref.rsplit("/", 1)[-1]
        if key in defs and key not in seen:
            seen.add(key)
            yield from _described_leaves(defs[key], defs, here, seen)


@pytest.mark.parametrize("pack_name", PACK_NAMES)
def test_no_field_the_vendor_calls_server_owned_reaches_the_model(pack_name):
    """A field the server sets is one the model can only get wrong.

    `Mode("response_only")` is the marker, and the cascade means a child of a
    withheld parent needs none of its own, so this asks the published schema
    rather than the declarations: what is the model actually offered.

    Google Calendar's `conferenceData.createRequest.status.statusCode` is what
    it found. `createRequest` is a field a caller does send, so the status rode
    along into every write that can attach a conference, and Google documents it
    Read-only.
    """
    module = importlib.import_module(f"charter.packs.{pack_name}")
    offered = {}
    for tool in module.TOOLS:
        params = tool.to_json_schema()["parameters"]
        for path, description in _described_leaves(params, params.get("$defs", {})):
            leaf = path.rsplit(".", 1)[-1]
            if (pack_name, leaf) in _SERVER_OWNED_EXCEPTIONS:
                continue
            if _SAYS_SERVER_OWNED.search(description):
                offered.setdefault(f"{tool.name}:{path}", description[:80])
    assert not offered, (
        f"{pack_name} offers the model fields the vendor calls server-owned: "
        f"{sorted(offered)}"
    )


def _glosses(model: Type[BaseModel], seen: Set[Any] | None = None) -> Set[str]:
    """Every `Gloss` text declared anywhere in a schema tree."""
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    found: Set[str] = set()
    for field in model.model_fields.values():
        found.update(
            marker.text
            for marker in getattr(field, "metadata", [])
            if isinstance(marker, Gloss)
        )
    for nested in _nested_models(model):
        found.update(_glosses(nested, seen))
    return found


@pytest.mark.parametrize("pack_name", PACK_NAMES)
def test_every_gloss_a_pack_declares_reaches_the_model(pack_name):
    """A gloss that lands nowhere is worse than no gloss at all.

    It reads as declared and is not, which is the failure the marker was written
    to prevent one level down. The first implementation had exactly this bug for
    `Format` fields: pydantic rebuilds a FieldInfo from its explicitly set
    attributes, so appending to `.description` silently did nothing for a
    retyped field and worked everywhere else.

    Checked against `to_json_schema()`, the schema the adapters hand to a model,
    rather than against the pass that writes it.
    """
    module = importlib.import_module(f"charter.packs.{pack_name}")
    lost = []
    for tool in module.TOOLS:
        declared = _glosses(tool.args_schema)
        if not declared:
            continue
        published = json.dumps(tool.to_json_schema())
        # Escaped the way the published text is escaped. Comparing the raw
        # sentence reported five false misses the moment a gloss quoted a
        # string value: `is "1500"` is `is \"1500\"` inside a JSON document.
        lost.extend(
            f"{tool.name}: {text}"
            for text in declared
            if json.dumps(text)[1:-1] not in published
        )
    assert not lost, f"{pack_name} declares glosses the model never sees: {lost}"


@pytest.mark.parametrize("pack_name", PACK_NAMES)
def test_no_gloss_reaches_the_documented_description(pack_name):
    """The wire schema's description is the API's own text, and stays diffable
    against the reference page. A gloss belongs in the LLM view only."""
    module = importlib.import_module(f"charter.packs.{pack_name}")
    leaked = []
    for tool in module.TOOLS:
        for text in _glosses(tool.args_schema):
            for field_name, field in tool.args_schema.model_fields.items():
                if text in (field.description or ""):
                    leaked.append(f"{tool.name}.{field_name}")
    assert not leaked, f"{pack_name} wrote a gloss into a documented description: {leaked}"


@pytest.mark.parametrize("pack_name", PACK_NAMES)
def test_no_conflict_rule_names_a_field_that_does_not_exist(pack_name):
    """A `ConflictsWith` naming an undeclared field never fires, and nothing says
    so — the rule reads as enforced and is not. Cheap to check from the same
    declarations the runtime reads."""
    from charter.conflicts import conflict_map

    module = importlib.import_module(f"charter.packs.{pack_name}")
    dangling = [
        f"{tool}.{rule['field']} -> {other['field']}"
        for tool, rules in conflict_map(module.TOOLS).items()
        for rule in rules
        for other in rule["excludes"]
        if not other["declared"]
    ]
    assert not dangling, f"{pack_name} declares rules that can never fire: {dangling}"


def test_no_pack_model_was_rewritten_by_its_own_llm_view():
    """Building a tool's LLM view must not rewrite the model it was built from.

    ``create_model`` is free to mutate the ``FieldInfo`` objects it is handed,
    and the builder hands it the pack's own. Whether that bites depends on the
    Pydantic version: under 2.7 it repointed the source annotation at the
    generated class, so ``IdComparator`` read ``IdComparator_LLM`` after one
    build and ``IdComparator_LLM_LLM`` after the next. The pinned version does
    not, which is the only reason no pack carries the damage today.

    It is asserted rather than assumed because the failure is silent and
    compounding: a self-referential model defeats the cycle cache — keyed on
    ``id(original_schema)``, which never matches an already-generated class — so
    every nesting level rebuilds every nested type afresh, inlined, up to the
    depth limit. More than one ``_LLM`` suffix is the visible tell.
    """
    corrupted = []
    for pack_name in PACKS:
        types_module = importlib.import_module(f"charter.packs.{pack_name}.types")
        for module in {types_module, *_submodules(types_module)}:
            for cls_name, cls in vars(module).items():
                if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
                    continue
                for field_name, field in cls.model_fields.items():
                    if "_LLM" in str(field.annotation):
                        corrupted.append(
                            f"{pack_name}.{cls_name}.{field_name} -> {field.annotation}"
                        )

    assert not corrupted, (
        "the LLM view rewrote the annotations on the models it was built from:\n  "
        + "\n  ".join(sorted(set(corrupted))[:10])
    )
