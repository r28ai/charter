"""R3 — the LLM view of a schema: mode filtering, semantic retyping, coercion."""

from __future__ import annotations

import pathlib
from typing import Annotated, Dict, List, Optional, get_args

import pytest
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

import charter.execution.schema as schema_module
from charter import (
    Body,
    DeclarationError,
    EmailContent,
    Format,
    Gloss,
    Mode,
    Path,
    Query,
    Value,
)
from charter.execution.schema import (
    LLMBase,
    _pydantic_decorators,
    create_llm_schema,
    partial_of,
    should_include_field,
)

# -----------------------------------------------------
# Mode filtering
# -----------------------------------------------------


class Message(BaseModel):
    id: Annotated[Optional[str], Body(), Mode("response_only")] = None
    thread_id: Annotated[Optional[str], Body(), Mode("response_only")] = None
    raw: Annotated[Optional[str], Body(), Mode("request_only")] = None
    internal: Annotated[Optional[int], Body(), Mode("disabled")] = None
    subject: Annotated[Optional[str], Body()] = None
    full_text: Annotated[Optional[str], Body(), Mode("create")] = None
    delta: Annotated[Optional[str], Body(), Mode("update")] = None


def test_response_only_and_disabled_are_dropped_from_the_llm_view():
    llm = create_llm_schema(Message)
    assert "id" not in llm.model_fields
    assert "thread_id" not in llm.model_fields
    assert "internal" not in llm.model_fields


def test_request_only_and_unmarked_fields_survive():
    llm = create_llm_schema(Message)
    assert "raw" in llm.model_fields
    assert "subject" in llm.model_fields


def test_custom_modes_are_filtered_by_the_tools_mode():
    create = create_llm_schema(Message, mode="create")
    assert "full_text" in create.model_fields
    assert "delta" not in create.model_fields

    update = create_llm_schema(Message, mode="update")
    assert "delta" in update.model_fields
    assert "full_text" not in update.model_fields


def test_custom_mode_fields_are_all_visible_when_no_mode_is_set():
    """With no mode on the tool, a custom Mode() is not a restriction.

    Only the special modes (response_only / disabled) hide a field unconditionally;
    a custom mode narrows the view *when the tool declares one*, and is otherwise
    inert. Setting mode= is what makes create/update mutually exclusive.
    """
    llm = create_llm_schema(Message)
    assert "full_text" in llm.model_fields
    assert "delta" in llm.model_fields


def test_the_original_schema_is_never_mutated():
    """Field names *and* the FieldInfo objects behind them.

    Comparing names only let a real mutation through: setting a WireName's alias
    while building the LLM view reached back into the author's own schema,
    because `fields` holds their FieldInfo objects rather than copies.

    `description` joined the snapshot when `Gloss` started appending to it.
    `Message` declares no gloss, so that pass does not run here and
    `test_a_gloss_never_reaches_the_documented_description` is what catches a
    missing copy. This records that a description is now something the build
    writes to, not only the aliases.
    """
    import copy as _copy

    before = set(Message.model_fields)
    snapshot = {
        name: (
            f.alias,
            f.validation_alias,
            f.serialization_alias,
            f.description,
            _copy.copy(f.metadata),
        )
        for name, f in Message.model_fields.items()
    }

    create_llm_schema(Message, mode="create")

    assert set(Message.model_fields) == before
    assert "id" in Message.model_fields  # response_only still there on the wire schema
    for name, f in Message.model_fields.items():
        assert (
            f.alias,
            f.validation_alias,
            f.serialization_alias,
            f.description,
        ) == snapshot[name][:4], name
        assert list(f.metadata) == list(snapshot[name][4]), name


def test_multi_mode_field_matches_either_mode():
    class Multi(BaseModel):
        both: Annotated[Optional[str], Body(), Mode("create,update")] = None

    assert "both" in create_llm_schema(Multi, mode="create").model_fields
    assert "both" in create_llm_schema(Multi, mode="update").model_fields
    assert "both" not in create_llm_schema(Multi, mode="delete").model_fields


# -----------------------------------------------------
# Mode cascading into nested models
# -----------------------------------------------------


class Inner(BaseModel):
    visible: Annotated[Optional[str], Body()] = None
    hidden: Annotated[Optional[str], Body(), Mode("response_only")] = None


class Outer(BaseModel):
    kept: Annotated[Optional[Inner], Body()] = None
    dropped: Annotated[Optional[Inner], Body(), Mode("response_only")] = None


def test_nested_response_only_field_is_dropped():
    llm = create_llm_schema(Outer)
    nested = llm.model_fields["kept"].annotation
    # Optional[Inner_LLM] -> pull the model out
    from typing import get_args

    nested_model = next(a for a in get_args(nested) if a is not type(None))
    assert "visible" in nested_model.model_fields
    assert "hidden" not in nested_model.model_fields


def test_response_only_cascades_to_the_whole_subtree():
    llm = create_llm_schema(Outer)
    assert "dropped" not in llm.model_fields


def test_list_of_nested_models_is_rewritten():
    class WithList(BaseModel):
        items: Annotated[Optional[List[Inner]], Body()] = None

    llm = create_llm_schema(WithList)
    schema = llm.model_json_schema()
    # The nested model in the list is the _LLM variant, so 'hidden' is gone.
    defs = schema.get("$defs", {})
    inner_def = next(v for k, v in defs.items() if k.startswith("Inner"))
    assert "visible" in inner_def["properties"]
    assert "hidden" not in inner_def["properties"]


def test_self_referential_schema_terminates():
    class Node(BaseModel):
        name: Annotated[str, Body()]
        children: Annotated[Optional[List[Node]], Body()] = None

    Node.model_rebuild()
    llm = create_llm_schema(Node)
    assert "name" in llm.model_fields
    assert "children" in llm.model_fields


def test_mutually_recursive_optional_models_build_a_json_schema():
    """A optional-B, B optional-A — Linear's collection filters look like this.

    A cycle parks the generated class's name, and those classes are bound in no
    module, so the ref resolves only where pydantic has the class in scope.
    """

    class Left(BaseModel):
        name: Annotated[str, Body()]
        right: Annotated[Optional[Right], Body()] = None

    class Right(BaseModel):
        name: Annotated[str, Body()]
        left: Annotated[Optional[Left], Body()] = None

    Left.model_rebuild()
    Right.model_rebuild()
    llm = create_llm_schema(Left)
    assert llm.__pydantic_complete__
    schema = llm.model_json_schema()
    # A cycle is emitted as a $ref into $defs rather than an inline `type`.
    root = schema
    if "$ref" in schema:
        root = schema["$defs"][schema["$ref"].rsplit("/", 1)[-1]]
    assert root["type"] == "object"
    right = root["properties"]["right"]
    assert right.get("type") != "string"
    llm.model_validate({"name": "l", "right": {"name": "r", "left": {"name": "l2"}}})

    # The root proves nothing on its own: pydantic keeps the class it is
    # building in scope, so `Left_LLM` completes whether or not the walk
    # resolves anything. `Right_LLM` is the one left undefined, and the deeper
    # graphs that take the root down with them start here.
    inner = get_args(llm.model_fields["right"].annotation)[0]
    assert inner.__pydantic_complete__
    inner.model_json_schema()


# -----------------------------------------------------
# should_include_field directly
# -----------------------------------------------------


def _field(schema, name):
    return schema.model_fields[name]


@pytest.mark.parametrize(
    ("name", "mode", "expected"),
    [
        ("id", None, False),  # response_only
        ("internal", None, False),  # disabled
        ("raw", None, True),  # request_only
        ("subject", None, True),  # unmarked
        ("full_text", "create", True),
        ("full_text", "update", False),
    ],
)
def test_should_include_field(name, mode, expected):
    assert should_include_field(_field(Message, name), mode) is expected


def test_response_only_wins_over_a_matching_custom_mode():
    class Both(BaseModel):
        x: Annotated[Optional[str], Body(), Mode("create,response_only")] = None

    assert should_include_field(_field(Both, "x"), "create") is False


# -----------------------------------------------------
# Format -> semantic type rewriting
# -----------------------------------------------------


class SendMessage(BaseModel):
    user_id: Annotated[str, Path()] = "me"
    raw: Annotated[str, Body(), Format("rfc822_base64")]


def test_format_field_is_retyped_to_the_semantic_type():
    llm = create_llm_schema(SendMessage)
    assert llm.model_fields["raw"].annotation is EmailContent


def test_the_semantic_description_replaces_the_wire_one():
    llm = create_llm_schema(SendMessage)
    assert llm.model_fields["raw"].description == "Email message content"


def test_http_markers_survive_the_rewrite():
    llm = create_llm_schema(SendMessage)
    metadata = llm.model_fields["raw"].metadata
    assert any(isinstance(m, Body) for m in metadata)
    assert any(isinstance(m, Format) for m in metadata)


def test_optional_format_field_stays_optional():
    class OptionalFormat(BaseModel):
        raw: Annotated[Optional[str], Body(), Format("rfc822_base64")] = None

    llm = create_llm_schema(OptionalFormat)
    from typing import get_args

    assert EmailContent in get_args(llm.model_fields["raw"].annotation)


def test_proto_json_keeps_the_original_type():
    """proto_json registers against bare BaseModel — the original Value type
    already handles LLM input, so it must not be replaced."""

    class Sheet(BaseModel):
        values: Annotated[Optional[List[List[Value]]], Format("proto_json")] = Field(default=None)

    llm = create_llm_schema(Sheet)
    assert llm.model_fields["values"].annotation == Optional[List[List[Value]]]


def test_unknown_transform_leaves_the_field_alone():
    class Odd(BaseModel):
        x: Annotated[str, Body(), Format("no_such_transform")]

    llm = create_llm_schema(Odd)
    assert llm.model_fields["x"].annotation is str


def test_required_format_field_stays_required():
    llm = create_llm_schema(SendMessage)
    assert llm.model_fields["raw"].is_required()
    with pytest.raises(ValidationError):
        llm.model_validate({})


# -----------------------------------------------------
# LLMBase input tolerance
# -----------------------------------------------------


class DateInput(BaseModel):
    user_id: Annotated[str, Path()]
    start_date: Annotated[Optional[str], Query()] = None


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "u1", "start_date": "2026-01-01"},
        {"userId": "u1", "startDate": "2026-01-01"},
        {"UserId": "u1", "StartDate": "2026-01-01"},
    ],
    ids=["snake", "camel", "pascal"],
)
def test_llm_schema_accepts_snake_camel_and_pascal_keys(payload):
    llm = create_llm_schema(DateInput)
    m = llm.model_validate(payload)
    assert m.user_id == "u1"
    assert m.start_date == "2026-01-01"


def test_model_dump_still_returns_snake_case():
    """call_api's casing depends on this — the dump must stay snake_case."""
    llm = create_llm_schema(DateInput)
    m = llm.model_validate({"userId": "u1", "startDate": "2026-01-01"})
    dumped = m.model_dump(exclude_none=True)
    assert dumped == {"user_id": "u1", "start_date": "2026-01-01"}


class BodyHolder(BaseModel):
    payload: Annotated[dict, Body()]


def test_json_string_body_is_coerced_to_an_object():
    llm = create_llm_schema(BodyHolder)
    m = llm.model_validate({"payload": '{"requests": [1, 2]}'})
    assert m.payload == {"requests": [1, 2]}


def test_json_string_list_is_coerced():
    class ListHolder(BaseModel):
        items: Annotated[list, Body()]

    llm = create_llm_schema(ListHolder)
    assert llm.model_validate({"items": "[1, 2, 3]"}).items == [1, 2, 3]


def test_malformed_json_string_reports_a_syntax_error_not_a_type_error():
    """Told only that the type is wrong, a model retries with the same broken
    syntax forever. The message has to say it is a syntax problem."""
    llm = create_llm_schema(BodyHolder)
    with pytest.raises(ValidationError) as excinfo:
        llm.model_validate({"payload": '{"requests": [1, 2}'})

    message = str(excinfo.value)
    assert "looks like JSON but is malformed" in message


def test_a_plain_string_field_is_not_touched_by_json_coercion():
    class StrHolder(BaseModel):
        note: Annotated[str, Body()]

    llm = create_llm_schema(StrHolder)
    assert llm.model_validate({"note": "{not json but a string field}"}).note == (
        "{not json but a string field}"
    )


def test_generated_schemas_inherit_llm_base():
    assert issubclass(create_llm_schema(DateInput), LLMBase)


def test_schema_case_dunder_is_carried_onto_the_llm_view():
    """call_api reads __case__ off the instance's class, which is the generated
    LLM model — so the override has to travel with it."""

    class PascalBody(BaseModel):
        __case__ = "pascal"
        first_name: Annotated[str, Body()]

    llm = create_llm_schema(PascalBody)
    assert getattr(llm, "__case__", None) == "pascal"


# -----------------------------------------------------
# Validators and config survive the derivation
#
# create_model builds a genuinely new class, and validators are not fields. For
# a while they were therefore dropped: a pack author could write a cross-field
# rule, watch the wire schema enforce it, and ship a tool that never checked the
# one input that mattered — the model's. Google Docs alone declares ~20 of them.
# -----------------------------------------------------


class OneOfInput(BaseModel):
    """A Docs-shaped oneof: exactly one location, and nothing unexpected."""

    model_config = {"extra": "forbid"}

    text: Annotated[str, Body()]
    location: Annotated[Optional[str], Body()] = None
    end_of_segment_location: Annotated[Optional[str], Body()] = None
    secret: Annotated[Optional[str], Body(), Mode("response_only")] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_sentinel(cls, values):
        if isinstance(values, dict) and values.get("text") == "__SENTINEL__":
            raise ValueError("text may not be the sentinel")
        return values

    @model_validator(mode="after")
    def _exactly_one_location(self):
        if (self.location is None) == (self.end_of_segment_location is None):
            raise ValueError(
                "Exactly one of `location` or `end_of_segment_location` must be set."
            )
        return self

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value):
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("secret")
    @classmethod
    def _never_reached(cls, value):  # pragma: no cover - the field is filtered out
        raise AssertionError("a validator for a filtered field must not be carried")


def test_an_after_model_validator_is_carried_onto_the_llm_view():
    llm = create_llm_schema(OneOfInput)

    with pytest.raises(ValidationError, match="Exactly one"):
        llm(text="hi")
    with pytest.raises(ValidationError, match="Exactly one"):
        llm(text="hi", location="a", end_of_segment_location="b")

    assert llm(text="hi", location="a").location == "a"


def test_a_before_model_validator_is_carried_onto_the_llm_view():
    llm = create_llm_schema(OneOfInput)

    with pytest.raises(ValidationError, match="sentinel"):
        llm(text="__SENTINEL__", location="a")


def test_a_field_validator_is_carried_onto_the_llm_view():
    llm = create_llm_schema(OneOfInput)

    with pytest.raises(ValidationError, match="must not be blank"):
        llm(text="   ", location="a")


def test_a_validator_for_a_mode_filtered_field_is_dropped_not_carried():
    """Pydantic rejects a validator naming a field the model does not have."""
    llm = create_llm_schema(OneOfInput)

    assert "secret" not in llm.model_fields
    assert "_never_reached" not in llm.__pydantic_decorators__.field_validators
    # And the model still builds and validates.
    assert llm(text="hi", location="a").text == "hi"


def test_extra_forbid_is_carried_onto_the_llm_view():
    """Otherwise a misspelled key is dropped in silence and the call does nothing."""
    llm = create_llm_schema(OneOfInput)

    with pytest.raises(ValidationError, match="Extra inputs"):
        llm(text="hi", location="a", bogus=1)


def test_carrying_config_does_not_break_the_case_insensitive_aliases():
    """LLMBase owns the alias machinery; only strictness keys are carried."""
    llm = create_llm_schema(OneOfInput)

    assert llm(text="hi", endOfSegmentLocation="tail").end_of_segment_location == "tail"
    assert llm(text="hi", EndOfSegmentLocation="tail").end_of_segment_location == "tail"


def test_a_schema_without_validators_is_unaffected():
    class Plain(BaseModel):
        name: Annotated[str, Body()]

    llm = create_llm_schema(Plain)
    assert llm(name="ok").name == "ok"
    # Every generated schema refuses undeclared keys, carried config or not: a
    # dropped argument is a wrong answer the caller cannot see.
    with pytest.raises(ValidationError):
        llm(name="ok", extra=1)


def test_validators_are_carried_into_nested_models_too():
    class Outer(BaseModel):
        edit: Annotated[OneOfInput, Body()]

    llm = create_llm_schema(Outer)

    with pytest.raises(ValidationError, match="Exactly one"):
        llm(edit={"text": "hi"})

    assert llm(edit={"text": "hi", "location": "a"}).edit.location == "a"


# -----------------------------------------------------
# The one private Pydantic attribute Charter depends on
# -----------------------------------------------------


def test_the_private_pydantic_attribute_is_reached_from_exactly_one_place():
    """A second direct read is a second thing to find when pydantic moves it."""
    source = pathlib.Path(schema_module.__file__).read_text()
    start = source.index("def _pydantic_decorators(")
    end = source.index("\ndef ", start + 1)
    outside = source[:start] + source[end:]
    assert "__pydantic_decorators__" not in outside, (
        "execution/schema.py reads __pydantic_decorators__ outside the accessor; "
        "route it through _pydantic_decorators() so one place fails when "
        "pydantic moves it"
    )


def test_a_pydantic_that_moved_its_decorators_fails_loudly():
    """Silence here would drop every cross-field rule a pack declared."""

    class NotAModel:
        pass

    with pytest.raises(RuntimeError, match="__pydantic_decorators__"):
        _pydantic_decorators(NotAModel)


def test_the_accessor_returns_the_decorators_of_a_real_model():
    class HasARule(BaseModel):
        a: Optional[str] = None

        @model_validator(mode="after")
        def _rule(self):
            return self

    assert "_rule" in _pydantic_decorators(HasARule).model_validators


# -----------------------------------------------------
# An argument the schema does not declare
# -----------------------------------------------------


def test_an_undeclared_argument_is_refused_not_dropped():
    """The failure this prevents is a wrong answer, not an error.

    Pydantic's default is to ignore unknown keys. On a tool boundary that means
    a model inventing `created` on a list endpoint, or typing `emails` for
    `email`, gets HTTP 200 and a page of *unfiltered* rows — with nothing in the
    response saying the filter was discarded. Verified against the live Stripe
    API before this changed: `customers_list(limit=2, created={"gt": ...})` sent
    `limit=2` and returned two arbitrary customers.
    """

    class Listing(BaseModel):
        limit: Annotated[int, Body()] = 10

    llm = create_llm_schema(Listing)
    with pytest.raises(ValidationError, match="not permitted"):
        llm(limit=2, created={"gt": 1600000000})


def test_the_json_schema_says_so_too():
    """A model plans against the schema, so the refusal belongs there as well."""

    class Listing(BaseModel):
        limit: Annotated[int, Body()] = 10

    assert create_llm_schema(Listing).model_json_schema()["additionalProperties"] is False


def test_every_spelling_of_a_field_name_still_validates():
    """camelCase, PascalCase and snake_case stay interchangeable under `forbid`.

    They have to be *declared* aliases now: with extras refused, a spelling that
    is merely tolerated by populate_by_name becomes an error. Both authoring
    conventions matter — Stripe's schemas are snake_case, Gmail's camelCase — so
    the mapping has to resolve in both directions.
    """

    class SnakeAuthored(BaseModel):
        starting_after: Annotated[str, Body()] = ""

    class CamelAuthored(BaseModel):
        userId: Annotated[str, Body()] = ""

    snake = create_llm_schema(SnakeAuthored)
    for spelling in ("starting_after", "startingAfter", "StartingAfter"):
        assert snake(**{spelling: "x"}).starting_after == "x"

    camel = create_llm_schema(CamelAuthored)
    for spelling in ("userId", "user_id", "UserId"):
        assert camel(**{spelling: "me"}).userId == "me"


# -----------------------------------------------------
# partial_of — one resource, several operations
# -----------------------------------------------------


class _Colour(BaseModel):
    text: Optional[str] = Field(None, description="Text colour.")
    background: Optional[str] = Field(None, description="Background colour.")

    @model_validator(mode="after")
    def _both_or_neither(self) -> _Colour:
        if (self.text is None) != (self.background is None):
            raise ValueError("text and background are both required")
        return self


class _Resource(BaseModel):
    """A resource that create, update and patch all send."""

    ident: Annotated[Optional[str], Field(None, description="Server-set."), Mode("response_only")]
    name: str = Field(..., description="The display name.")
    size: Annotated[Optional[int], Field(None, ge=1, le=500, description="How big."), Query()]
    colour: Optional[_Colour] = Field(None, description="Its colour.")

    @model_validator(mode="after")
    def _name_is_not_blank(self) -> _Resource:
        if self.name is not None and not self.name.strip():
            raise ValueError("name cannot be blank")
        return self


_Partial = partial_of(_Resource, name="ResourcePatch", doc="Only what changed.")


def test_partial_of_relaxes_every_field():
    assert not [n for n, f in _Partial.model_fields.items() if f.is_required()]
    # ...and the source is untouched.
    assert _Resource.model_fields["name"].is_required()


def test_partial_of_inherits_the_descriptions_rather_than_copying_them():
    """The whole point: one home for the field documentation."""
    for name, field in _Resource.model_fields.items():
        assert _Partial.model_fields[name].description == field.description


def test_partial_of_keeps_markers_and_constraints():
    """Dropping Query() would move the field into the body; dropping Le(500)
    would let a value through that the API rejects."""
    assert any(isinstance(m, Query) for m in _Partial.model_fields["size"].metadata)
    assert any(isinstance(m, Mode) for m in _Partial.model_fields["ident"].metadata)
    assert [repr(m) for m in _Partial.model_fields["size"].metadata] == [
        repr(m) for m in _Resource.model_fields["size"].metadata
    ]

    with pytest.raises(ValidationError):
        _Partial(size=900)


def test_partial_of_carries_the_models_own_validators():
    """Partial does not mean unconstrained."""
    with pytest.raises(ValidationError, match="cannot be blank"):
        _Partial(name="   ")


def test_partial_of_leaves_nested_models_alone():
    """Relaxing a whole tree would drop rules the API still enforces below."""
    assert _Partial.model_fields["colour"].annotation is _Resource.model_fields["colour"].annotation

    with pytest.raises(ValidationError, match="both required"):
        _Partial(colour={"text": "#fff"})


def test_partial_of_names_itself_and_reports_where_it_was_declared():
    """The pack reference renders both."""
    assert _Partial.__name__ == "ResourcePatch"
    assert _Partial.__doc__ == "Only what changed."
    assert _Partial.__module__ == __name__
    assert partial_of(_Resource).__name__ == "Partial_Resource"


def test_a_partial_still_hides_what_mode_hides():
    """The derived model is a wire schema like any other."""
    view = create_llm_schema(_Partial)
    assert "ident" not in view.model_fields
    assert set(view.model_fields) == {"name", "size", "colour"}


def test_building_the_llm_view_does_not_alias_the_authors_own_fields():
    """The mutation case, with a field that actually triggers it.

    `test_the_original_schema_is_never_mutated` uses a model with no `WireName`,
    so the alias pass never runs for it — removing the defensive copy leaves that
    test green. This one declares the marker, which is the only path that writes
    to a FieldInfo, and those objects come straight from the author's model.
    """

    from charter.types import WireName

    class Declared(BaseModel):
        i_cal_uid: Annotated[Optional[str], Field(None), Query(), WireName("iCalUID")]
        plain: Annotated[Optional[str], Field(None), Query()]

    def aliases():
        return {
            name: (f.alias, f.validation_alias, f.serialization_alias)
            for name, f in Declared.model_fields.items()
        }

    before = aliases()
    llm = create_llm_schema(Declared)

    assert aliases() == before, "create_llm_schema aliased the schema it was given"
    assert before["i_cal_uid"] == (None, None, None)
    # ...while the derived view does carry it.
    assert llm.model_fields["i_cal_uid"].alias == "iCalUID"


# -----------------------------------------------------
# ConflictsWith — declared on the field, enforced by the runtime
# -----------------------------------------------------


def _conflict_message(exc) -> str:
    """Only the clause the validator raised.

    `str(ValidationError)` also echoes the input dict, so asserting a field name
    against the whole thing passes on the input rather than on the message — the
    first version of these tests did exactly that, and stayed green when the
    message was made to use the wrong name.
    """
    return str(exc.value).split("Value error, ", 1)[1].split(" [type=", 1)[0]


def _conflicting_model():

    from charter.types import ConflictsWith, WireName

    class Listing(BaseModel):
        sync_token: Annotated[Optional[str], Field(None), Query()]
        i_cal_uid: Annotated[
            Optional[str],
            Field(None),
            Query(),
            WireName("iCalUID"),
            ConflictsWith("sync_token", reason="Continue the sync or start a new query."),
        ]
        time_min: Annotated[
            Optional[str], Field(None), Query(), ConflictsWith("sync_token")
        ]
        harmless: Annotated[Optional[str], Field(None), Query()]

    return Listing


def test_a_conflict_is_enforced_without_the_author_writing_a_validator():
    """The rule has one home: the field it is about. A list beside a hand-written
    validator is a second place to keep in step, and nothing notices when it
    stops matching the fields."""
    import pydantic

    llm = create_llm_schema(_conflicting_model())

    assert llm.model_validate({"syncToken": "t"})
    assert llm.model_validate({"iCalUID": "a", "timeMin": "x", "harmless": "y"})

    with pytest.raises(pydantic.ValidationError) as exc:
        llm.model_validate({"syncToken": "t", "iCalUID": "a"})
    message = _conflict_message(exc)
    assert "iCalUID cannot be combined with syncToken" in message
    assert "Continue the sync or start a new query." in message


def test_every_conflict_is_reported_at_once():
    """Raising on the first makes a model fix one parameter, retry, and meet the
    next — the round trips the local check exists to avoid."""
    import pydantic

    llm = create_llm_schema(_conflicting_model())
    with pytest.raises(pydantic.ValidationError) as exc:
        llm.model_validate({"syncToken": "t", "iCalUID": "a", "timeMin": "x"})
    message = _conflict_message(exc)
    assert "iCalUID" in message and "timeMin" in message
    assert message.count("cannot be combined") == 1, "reported as two separate errors"


def test_the_message_uses_the_api_s_own_name_for_the_field():
    """A WireName is what the API calls it, so that is what the model is told."""
    import pydantic

    llm = create_llm_schema(_conflicting_model())
    with pytest.raises(pydantic.ValidationError) as exc:
        llm.model_validate({"syncToken": "t", "iCalUID": "a"})
    message = _conflict_message(exc)
    assert "iCalUID" in message
    assert "iCalUid" not in message, "camelised the field name instead of using WireName"
    assert "i_cal_uid" not in message


def test_a_schema_with_no_conflicts_gains_no_validator():
    llm = create_llm_schema(Message)
    assert "_charter_conflicts" not in llm.__pydantic_decorators__.model_validators


# -----------------------------------------------------
# What create_model drops, and what has to be put back
# -----------------------------------------------------


def test_a_nested_serializer_reaches_the_wire():
    """A model serializer is carried onto the LLM view, like a validator.

    ``create_model`` builds a genuinely new class, so neither survives on its
    own — but a dropped serializer is worse than a dropped validator, because
    the LLM view is the instance the runtime dumps. The bytes change and nothing
    raises.

    This is how a field Python will not let you name reaches the API under its
    own spelling. Notion's compound filter is ``{"and": [...]}``; ``and`` is a
    keyword, so the field is ``and_``. ``WireName`` cannot reach it either —
    key conversion carries per-field markers at the top level of a body only,
    and the filter is nested inside one.
    """

    class Nested(BaseModel):
        and_: Optional[List[str]] = Field(None, alias="and", description="all of these")
        plain: Optional[str] = Field(None, description="a normal field")

        @model_serializer(mode="wrap")
        def _keyword_on_the_wire(self, handler):
            data = handler(self)
            if "and_" in data:
                data["and"] = data.pop("and_")
            return data

    view = create_llm_schema(Nested)
    # The model is told the API's spelling...
    assert "and" in view.model_json_schema()["properties"]
    # ...accepts it...
    instance = view.model_validate({"and": ["x"], "plain": "y"})
    # ...and sends it.
    assert instance.model_dump(exclude_none=True, mode="json") == {"and": ["x"], "plain": "y"}


def test_a_model_reached_as_a_dict_value_still_has_its_modes_applied():
    """``Dict[str, Model]`` was copied across whole, Mode markers and all.

    Which made ``response_only`` mean nothing inside one — an egress hole, not
    an ergonomic lapse: a withheld field is how a pack keeps something out of a
    model's context window.
    """

    class Value(BaseModel):
        writable: Optional[str] = Field(None, description="accepted on a write")
        computed: Annotated[
            Optional[str],
            Field(None, description="returned only"),
            Mode("response_only"),
        ]

    class Holder(BaseModel):
        properties: Optional[Dict[str, Value]] = Field(None, description="a map")

    view = create_llm_schema(Holder)
    rendered = view.model_json_schema()
    assert "writable" in str(rendered)
    assert "computed" not in str(rendered)


# -----------------------------------------------------
# Gloss — the pack's own sentence, beside the API's
# -----------------------------------------------------


class _Refund(BaseModel):
    amount: Annotated[
        Optional[int],
        Field(None, ge=1, description="A positive integer in the smallest currency unit."),
        Body(),
        Gloss("Cents, not dollars: $15.00 is 1500."),
    ]


def test_a_gloss_is_appended_to_the_description_the_model_reads():
    view = create_llm_schema(_Refund)
    described = view.model_json_schema()["properties"]["amount"]["description"]
    assert described == (
        "A positive integer in the smallest currency unit. "
        "Cents, not dollars: $15.00 is 1500."
    )


def test_a_gloss_never_reaches_the_documented_description():
    """The whole reason the marker exists.

    `description` is the API's own text, which is what makes it checkable
    against the reference page. A gloss that landed there would be
    indistinguishable from the API's words, and the next regeneration from the
    docs would take it away without anyone noticing it had been there.
    """
    create_llm_schema(_Refund)
    documented = _Refund.model_fields["amount"].description
    assert documented == "A positive integer in the smallest currency unit."
    assert "Cents" not in documented


def test_a_gloss_leaves_the_constraints_alone():
    """The gloss is delivered by moving the FieldInfo into the annotation, and
    `ge` is on that same object. Losing it would let 0 through to an API that
    answers 400, which is the round trip a constraint exists to save."""
    view = create_llm_schema(_Refund)
    integer = view.model_json_schema()["properties"]["amount"]["anyOf"][0]
    assert integer["minimum"] == 1
    with pytest.raises(ValidationError):
        view.model_validate({"amount": 0})


def test_a_gloss_on_a_format_field_survives_the_retyping():
    """A `Format` field's markers move onto its annotation, so a pass reading
    them off the FieldInfo finds nothing. They are read off the author's schema
    instead, which is the one place they are always still visible."""

    class Send(BaseModel):
        raw: Annotated[str, Body(), Format("rfc822_base64"), Gloss("Plain text is fine.")]

    view = create_llm_schema(Send)
    assert view.model_fields["raw"].annotation is EmailContent
    assert view.model_fields["raw"].description == "Email message content Plain text is fine."
    assert view.model_fields["raw"].is_required(), "the gloss cost the field its default"
    assert any(isinstance(m, Body) for m in view.model_fields["raw"].metadata)


def test_a_gloss_inside_a_nested_model_reaches_the_json_schema():
    class Line(BaseModel):
        unit_amount: Annotated[
            Optional[int],
            Field(None, description="The price per unit."),
            Body(),
            Gloss("Cents, not dollars."),
        ]

    class Invoice(BaseModel):
        line: Annotated[Optional[Line], Field(None, description="One line."), Body()]

    rendered = create_llm_schema(Invoice).model_json_schema()
    # camelCase, because that is the spelling LLMBase publishes.
    described = rendered["$defs"]["Line_LLM"]["properties"]["unitAmount"]["description"]
    assert described == "The price per unit. Cents, not dollars."


def test_two_glosses_on_one_field_are_both_kept():
    """Two glosses is a pack author saying two things. Keeping the first only
    would drop the second where no reader of the declaration could tell."""

    class Two(BaseModel):
        x: Annotated[
            Optional[str],
            Field(None, description="A field."),
            Body(),
            Gloss("First."),
            Gloss("Second."),
        ]

    view = create_llm_schema(Two)
    assert view.model_fields["x"].description == "A field. First. Second."


def test_a_gloss_stands_alone_when_the_field_has_no_description():
    class Undocumented(BaseModel):
        x: Annotated[Optional[str], Body(), Gloss("Cents, not dollars.")] = None

    assert create_llm_schema(Undocumented).model_fields["x"].description == (
        "Cents, not dollars."
    )


def test_repeated_builds_do_not_append_the_gloss_twice():
    """The view is built per tool and `derived` builds it again with a different
    prune. Both read the same author FieldInfo, so appending in place would
    compound."""
    first = create_llm_schema(_Refund).model_fields["amount"].description
    second = create_llm_schema(_Refund).model_fields["amount"].description
    assert first == second
    assert second.count("Cents") == 1


def test_a_gloss_with_no_text_is_refused_at_declaration():
    with pytest.raises(DeclarationError, match="needs the sentence"):
        Gloss("   ")


def test_a_gloss_and_a_wire_name_on_one_field_both_take_effect():
    """The two passes write to the same FieldInfo, and the order is why.

    The alias pass reads `WireName` off the FieldInfo, and the gloss pass moves
    that FieldInfo into the annotation. Glossing first left the alias pass
    reading a bare `Field(description=...)` with no markers on it, so the API's
    own spelling was never published.
    """
    from charter.types import WireName

    class Declared(BaseModel):
        i_cal_uid: Annotated[
            Optional[str],
            Field(None, description="Event unique identifier."),
            Query(),
            WireName("iCalUID"),
            Gloss("The organiser's copy carries it too."),
        ]

    rendered = create_llm_schema(Declared).model_json_schema()
    assert "iCalUID" in rendered["properties"]
    assert rendered["properties"]["iCalUID"]["description"] == (
        "Event unique identifier. The organiser's copy carries it too."
    )


# The shapes `create_llm_schema` walks. A gloss that lands on a scalar and not
# on a retyped field, or not inside a dict value, is the silent half-failure
# this matrix exists to refuse: the marker reads as declared either way.


class _Leaf(BaseModel):
    inner: Annotated[Optional[str], Field(None, description="Leaf."), Body(), Gloss("G-nested")]


class _Tree(BaseModel):
    kids: Annotated[Optional[List[_Tree]], Field(None, description="Kids."), Body()] = None
    label: Annotated[Optional[str], Field(None, description="L."), Body(), Gloss("G-self-ref")]


class _Shapes(BaseModel):
    plain: Annotated[Optional[str], Field(None, description="P."), Body(), Gloss("G-plain")]
    required: Annotated[str, Field(..., description="R."), Body(), Gloss("G-required")]
    retyped: Annotated[
        Optional[str],
        Field(None, description="Rt."),
        Body(),
        Format("rfc822_base64"),
        Gloss("G-format"),
    ]
    unknown_format: Annotated[
        Optional[str], Field(None, description="U."), Body(), Format("nope"), Gloss("G-unknown")
    ]
    proto: Annotated[
        Optional[List[List[Value]]],
        Field(None, description="Pj."),
        Body(),
        Format("proto_json"),
        Gloss("G-proto"),
    ]
    model_field: Annotated[Optional[_Leaf], Field(None, description="N."), Body(), Gloss("G-model")]
    model_list: Annotated[
        Optional[List[_Leaf]], Field(None, description="Ml."), Body(), Gloss("G-model-list")
    ]
    scalar_list: Annotated[
        Optional[List[str]], Field(None, description="Sl."), Body(), Gloss("G-scalar-list")
    ]
    model_map: Annotated[
        Optional[Dict[str, _Leaf]], Field(None, description="Mm."), Body(), Gloss("G-model-map")
    ]
    scalar_map: Annotated[
        Optional[Dict[str, str]], Field(None, description="Sm."), Body(), Gloss("G-scalar-map")
    ]
    tree: Annotated[Optional[_Tree], Field(None, description="Tr."), Body(), Gloss("G-tree")]
    moded: Annotated[
        Optional[str], Field(None, description="M."), Body(), Mode("create"), Gloss("G-mode")
    ]


_EVERY_GLOSS = [
    "G-plain",
    "G-required",
    "G-format",
    "G-unknown",
    "G-proto",
    "G-model",
    "G-model-list",
    "G-scalar-list",
    "G-model-map",
    "G-scalar-map",
    "G-tree",
    "G-mode",
    "G-nested",
    "G-self-ref",
]


@pytest.mark.parametrize("text", _EVERY_GLOSS)
def test_a_gloss_lands_on_every_shape_the_walk_handles(text):
    published = str(create_llm_schema(_Shapes, mode="create").model_json_schema())
    assert text in published


@pytest.mark.parametrize("text", _EVERY_GLOSS)
def test_a_gloss_survives_a_partial_and_a_prune(text):
    """`partial_of` carries markers across, and a projection rebuilds the view."""
    relaxed = partial_of(_Shapes, name="_ShapesPatch")
    assert text in str(create_llm_schema(relaxed, mode="create").model_json_schema())
    pruned = create_llm_schema(_Shapes, mode="create", prune=frozenset({"plain"}))
    rendered = str(pruned.model_json_schema())
    assert (text in rendered) is (text != "G-plain")


def test_no_shape_leaks_its_gloss_into_the_wire_schema():
    create_llm_schema(_Shapes, mode="create")
    for model in (_Shapes, _Leaf, _Tree):
        for name, field in model.model_fields.items():
            assert "G-" not in (field.description or ""), f"{model.__name__}.{name}"
