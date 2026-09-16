"""
Does the conformance suite actually catch anything?

613 passing checks prove nothing on their own. A check that reads a declaration
and compares it to itself passes forever and protects nothing — and one of the
checks in :mod:`tests.test_conformance` was exactly that until this file caught
it.

So each check is exercised against a pack that has been broken on purpose, in
the specific way the bug it guards against broke it. If a mutation here starts
passing, the corresponding check has gone vacuous and the guard is gone.

``monkeypatch`` restores every mutation, so the packs are untouched afterwards.
"""

from __future__ import annotations

import inspect
import json
from typing import Annotated, List, Optional

import pytest
import tests.test_conformance as conformance
from pydantic import BaseModel, create_model, field_validator, model_validator

from charter.execution.schema import LLMBase, create_llm_schema
from charter.packs import gcalendar, github, gmail, granola, linear, stripe
from charter.tool import Tool
from charter.types.markers import Body, Mode
from charter.types.pagination import Pagination


def _must_fail(check, *args, because: str):
    """Run a conformance check that should fail, and report it if it does not."""
    try:
        check(*args)
    except AssertionError:
        return
    pytest.fail(
        f"{check.__name__} passed on broken input — the guard against {because} "
        f"is vacuous"
    )


def test_a_pagination_naming_a_missing_field_is_caught(monkeypatch):
    """The twenty-two wrong declarations a factory-level pagination created."""
    monkeypatch.setattr(stripe.balance_retrieve, "pagination", stripe.STRIPE_PAGINATION)
    _must_fail(
        conformance.test_a_pagination_names_fields_the_schema_accepts,
        "stripe",
        stripe.balance_retrieve,
        because="a cursor with nowhere to go",
    )


def test_pagination_on_a_write_endpoint_is_caught(monkeypatch):
    monkeypatch.setattr(stripe.refunds_create, "pagination", stripe.STRIPE_PAGINATION)
    _must_fail(
        conformance.test_only_endpoints_that_page_declare_pagination,
        "stripe",
        stripe.refunds_create,
        because="a POST that claims to paginate",
    )


def test_a_relay_walk_that_cannot_terminate_is_caught(monkeypatch):
    """The more_field bug: Relay sends endCursor on the last page too."""
    monkeypatch.setattr(
        linear.issues_list,
        "pagination",
        Pagination(cursor_field="pageInfo.endCursor", cursor_param="variables.after"),
    )
    _must_fail(
        conformance.test_a_pagination_walk_terminates,
        "linear",
        linear.issues_list,
        because="a pagination walk that never ends",
    )


def test_a_page_walk_that_never_advances_is_caught(monkeypatch):
    """A page-number pagination that stops on page one reads a fraction of the list."""
    monkeypatch.setattr(
        github.issues_list_for_repo,
        "pagination",
        # per_page names a field that does not exist, so no page is ever "full".
        Pagination(page_param="page", per_page_param="page"),
    )
    _must_fail(
        conformance.test_a_pagination_walk_terminates,
        "github",
        github.issues_list_for_repo,
        because="a walk that stops before the end",
    )


def test_failure_logic_inside_a_response_handler_is_caught(monkeypatch):
    """The boilerplate this project has removed three times."""
    real = inspect.getsource

    def fake(obj):
        if getattr(obj, "__name__", "").endswith("linear.response_handlers"):
            return "async def handler(response):\n    raise APIError('declined')\n"
        return real(obj)

    monkeypatch.setattr(inspect, "getsource", fake)
    _must_fail(
        conformance.test_no_response_handler_decides_whether_a_call_failed,
        "linear",
        because="failure detection that is opt-in per tool",
    )


def test_an_envelope_that_differs_per_tool_is_caught(monkeypatch):
    monkeypatch.setattr(linear.viewer, "envelope", None)
    _must_fail(
        conformance.test_an_envelope_is_declared_once_for_the_whole_api,
        "linear",
        because="a success predicate that is not a property of the API",
    )


def test_a_cross_field_rule_dropped_from_the_llm_view_is_caught(monkeypatch):
    """The silent bug: the model's input was the one never checked."""
    stripped_body = create_model(
        "PullCreateBody_LLM", __base__=LLMBase, head=(str, ...), base=(str, ...)
    )
    stripped = create_model(
        "PullsCreateRequest_LLM",
        __base__=LLMBase,
        owner=(str, ...),
        repo=(str, ...),
        body=(stripped_body, ...),
    )
    monkeypatch.setattr(github.pulls_create, "_llm_schema", stripped)
    _must_fail(
        conformance.test_every_cross_field_rule_survives_into_the_llm_view,
        "github",
        github.pulls_create,
        because="a oneof the model is never held to",
    )


def test_a_dropped_field_validator_is_caught(monkeypatch):
    """The half of the check that was missing until 2026-09-13.

    The walk read ``model_validators`` and nothing else, so a rule written as a
    ``field_validator`` was enforced on the wire schema, silently absent from
    the LLM view, and reported as fine. Which decorator a rule needs follows
    from its shape — one field judged alone is a field validator — not from how
    much the rule matters, and Granola's "``workspace`` cannot be mixed with
    another scope" is one of these.
    """
    stripped = create_model(
        "WebhookEndpointsCreateRequest_LLM",
        __base__=LLMBase,
        url=(str, ...),
        scopes=(List[str], ...),
    )
    monkeypatch.setattr(granola.webhook_endpoints_create, "_llm_schema", stripped)
    _must_fail(
        conformance.test_every_cross_field_rule_survives_into_the_llm_view,
        "granola",
        granola.webhook_endpoints_create,
        because="a field rule the model is never held to",
    )


def test_one_of_two_rules_surviving_is_still_caught(monkeypatch):
    """Counting models rather than rules would call this schema covered.

    The old walk collected the set of model *names* carrying a rule, so a model
    that kept one rule and dropped another matched on both sides and passed.
    """

    class TwoRules(BaseModel):
        a: Optional[str] = None
        b: Optional[str] = None

        @field_validator("a")
        @classmethod
        def _kept(cls, value: Optional[str]) -> Optional[str]:
            return value

        @field_validator("b")
        @classmethod
        def _dropped(cls, value: Optional[str]) -> Optional[str]:
            return value

    half = create_model(
        "TwoRules_LLM",
        __base__=LLMBase,
        a=(Optional[str], None),
        b=(Optional[str], None),
        __validators__={"_kept": field_validator("a")(classmethod(lambda cls, v: v))},
    )
    tool = Tool(
        name="two_rules",
        args_schema=TwoRules,
        method="POST",
        url_template="v1/two",
        base_url="https://example.com/",
        api_key_headers={"Authorization": "Bearer x"},
    )
    monkeypatch.setattr(tool, "_llm_schema", half)
    _must_fail(
        conformance.test_every_cross_field_rule_survives_into_the_llm_view,
        "example",
        tool,
        because="a model that kept one of its two rules",
    )


def test_a_rule_behind_a_response_only_field_is_not_reported():
    """The exemption the check makes, pinned from both sides.

    A rule on a model the LLM view never shows is not a dropped rule — the
    ``Mode`` marker withheld the whole subtree on purpose, which is the pack's
    egress policy working. Google Sheets reaches ``DataSourceRefreshSchedule``,
    and its ``at most one`` rule, only through ``Spreadsheet.dataSourceSchedules``,
    a field the API never accepts.

    Skipping too much is how that exemption goes wrong, so the same model behind
    a visible field must still be counted.
    """

    class Ruled(BaseModel):
        a: Optional[str] = None
        b: Optional[str] = None

        @model_validator(mode="after")
        def _at_most_one(self) -> Ruled:
            if self.a is not None and self.b is not None:
                raise ValueError("at most one of 'a', 'b'")
            return self

    class Hidden(BaseModel):
        ruled: Annotated[Optional[Ruled], Mode("response_only")] = None

    class Visible(BaseModel):
        ruled: Optional[Ruled] = None

    assert conformance._rules(Hidden) == {}
    assert conformance._rules(Visible) == {("Ruled", "_at_most_one"): ()}


def test_a_field_rule_whose_every_field_is_withheld_is_not_reported():
    """The second exemption, which only field validators can reach.

    ``_carry_validators`` skips a field validator whose targets were all
    filtered out by ``Mode``, because Pydantic refuses a validator naming a
    field the model does not have. The check has to make the same allowance or
    it reports the runtime doing the right thing.
    """

    class HalfHidden(BaseModel):
        shown: Optional[str] = None
        withheld: Annotated[Optional[str], Mode("response_only")] = None

        @field_validator("withheld")
        @classmethod
        def _only_judges_the_hidden_one(cls, value: Optional[str]) -> Optional[str]:
            return value

    tool = Tool(
        name="half_hidden",
        args_schema=HalfHidden,
        method="POST",
        url_template="v1/half",
        base_url="https://example.com/",
        api_key_headers={"Authorization": "Bearer x"},
    )

    # The rule is on the wire schema, the field it judges is not in the view,
    # and the runtime therefore drops it. That is not a finding.
    assert conformance._rules(HalfHidden) == {
        ("HalfHidden", "_only_judges_the_hidden_one"): ("withheld",)
    }
    assert conformance._visible_fields(create_llm_schema(HalfHidden)) == {
        "HalfHidden": {"shown"}
    }
    conformance.test_every_cross_field_rule_survives_into_the_llm_view("example", tool)


def test_snake_cased_google_query_parameters_are_caught(monkeypatch):
    """Google ignores what it cannot read, so this failure is entirely silent."""
    for tool in gcalendar.TOOLS:
        monkeypatch.setattr(tool, "query_case", "snake")
    _must_fail(
        conformance.test_google_packs_send_camel_cased_query_parameters,
        "gcalendar",
        because="filters Google silently discards",
    )


def test_a_constant_also_exposed_as_an_argument_is_caught(monkeypatch):
    monkeypatch.setattr(
        github.repos_get,
        "static_headers",
        {**(github.repos_get.static_headers or {}), "owner": "attacker"},
    )
    _must_fail(
        conformance.test_a_static_constant_is_never_reachable_from_tool_arguments,
        "github",
        github.repos_get,
        because="a model that can rewrite infrastructure",
    )


def test_an_undescribed_tool_is_caught(monkeypatch):
    monkeypatch.setattr(github.repos_get, "description", "")
    _must_fail(
        conformance.test_every_tool_is_described_for_both_audiences,
        "github",
        github.repos_get,
        because="a tool a model cannot choose",
    )


def test_an_optional_field_that_is_secretly_required_is_caught(monkeypatch):
    """The most common bug in a hand-written pack."""
    tool = github.issues_list_for_repo
    broken = dict(tool.to_json_schema())
    broken["parameters"] = {**broken["parameters"], "required": ["owner", "repo", "state"]}
    monkeypatch.setattr(tool, "to_json_schema", lambda: broken)
    _must_fail(
        conformance.test_no_optional_field_is_secretly_required,
        "github",
        tool,
        because="a filter the model is forced to invent",
    )



def test_a_patch_body_that_mandates_a_field_is_caught(monkeypatch):
    """Reusing the PUT resource on a PATCH endpoint.

    `Label` requires `name`, which is right for labels.update and wrong for
    labels.patch. Pointing patch at it is the shortcut a pack takes when one
    resource serves both, and it is what the check exists to refuse.
    """
    from charter.packs.gmail.types.label.models import Label

    broken = create_model(
        "BrokenLabelsPatch_LLM",
        __base__=LLMBase,
        id=(str, ...),
        body=(Annotated[Label, Body()], ...),
    )
    monkeypatch.setattr(gmail.labels_patch, "llm_schema", lambda: broken)
    _must_fail(
        conformance.test_a_patch_body_mandates_nothing,
        "gmail",
        gmail.labels_patch,
        because="a partial update demanding a field it is not changing",
    )


def test_a_gloss_the_model_never_sees_is_caught(monkeypatch):
    """The bug the check was written from, reproduced.

    Appending to `description` on the FieldInfo is what the first version did,
    and pydantic keeps a plain assignment only for the instances it marks final.
    A tool whose published schema has lost the gloss is indistinguishable from
    one that never declared it, so the mutation is a schema with the marker and
    without the sentence.
    """
    published = stripe.refunds_create.to_json_schema()
    amount = published["parameters"]["properties"]["amount"]
    amount["description"] = "A positive integer in the smallest currency unit."
    monkeypatch.setattr(stripe.refunds_create, "to_json_schema", lambda: published)
    _must_fail(
        conformance.test_every_gloss_a_pack_declares_reaches_the_model,
        "stripe",
        because="a gloss that reads as declared and reaches no model",
    )


def test_a_gloss_written_into_the_documented_description_is_caught(monkeypatch):
    """The drift the marker exists to prevent: the pack's sentence and the API's
    in one string, where no diff against the reference page can separate them."""
    from charter.packs.stripe.types.payments import RefundsCreateRequest

    field = RefundsCreateRequest.model_fields["amount"]
    monkeypatch.setattr(
        field,
        "description",
        f"{field.description} Cents, not dollars: $15.00 is 1500, and 15 refunds "
        "fifteen cents. Multiply a decimal amount by 100.",
    )
    _must_fail(
        conformance.test_no_gloss_reaches_the_documented_description,
        "stripe",
        because="a gloss mixed into the API's own words",
    )


def test_a_server_owned_field_offered_to_the_model_is_caught(monkeypatch):
    """The gcalendar conference status, reproduced on a pack that has none.

    Injected into the published schema rather than onto the declaration,
    because the check reads what the model is offered: the cascade means a
    withheld parent covers its children, so the declarations alone cannot
    answer the question.
    """
    published = gmail.labels_create.to_json_schema()
    first = next(iter(published["parameters"]["properties"]))
    published["parameters"]["properties"][first]["description"] = (
        "Output only. The server sets this."
    )
    monkeypatch.setattr(gmail.labels_create, "to_json_schema", lambda: published)
    _must_fail(
        conformance.test_no_field_the_vendor_calls_server_owned_reaches_the_model,
        "gmail",
        because="a field the vendor sets, offered to the model to get wrong",
    )


def test_the_packs_are_intact_after_every_mutation():
    """monkeypatch restores state; this is the assertion that it did."""
    assert stripe.balance_retrieve.pagination is None
    assert github.repos_get.description
    assert github.repos_get.static_headers == github.GITHUB_HEADERS
    assert linear.viewer.envelope is linear.LINEAR_ENVELOPE
    assert all(tool.query_case == "camel" for tool in gcalendar.TOOLS)
    patch_body = gmail.labels_patch.llm_schema().model_fields["body"].annotation
    assert not [n for n, f in patch_body.model_fields.items() if f.is_required()]
    assert linear.issues_list.pagination is linear.LINEAR_PAGINATION
    assert "Output only" not in json.dumps(gmail.labels_create.to_json_schema())
    amount = stripe.refunds_create.args_schema.model_fields["amount"]
    assert amount.description == (
        "A positive integer in the smallest currency unit representing how much "
        "to refund. Defaults to the entire charge."
    )
    assert "Cents, not dollars" in (
        stripe.refunds_create.to_json_schema()["parameters"]["properties"]["amount"][
            "description"
        ]
    )
