"""Linear pack — the GraphQL case: a constant document, and failure inside a 200."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from charter import APIError, CredentialError, Tool, ToolValidationError
from charter.packs import linear

API = "https://api.linear.app/graphql"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    linear.configure(api_key="lin_api_test123")


def _sent() -> Dict[str, Any]:
    return json.loads(respx.calls.last.request.content)


def _issues_page(*ids: str, cursor: str = "cur", more: bool = True) -> Dict[str, Any]:
    return {
        "data": {
            "issues": {
                "nodes": [{"id": i, "identifier": f"ENG-{i}", "title": f"Issue {i}"} for i in ids],
                "pageInfo": {"hasNextPage": more, "endCursor": cursor},
            }
        }
    }


def _validate(tool: Tool, args: Dict[str, Any]):
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_its_whole_declared_surface():
    assert len(linear.TOOLS) == 128
    assert all(isinstance(t, Tool) for t in linear.TOOLS)
    assert len({t.name for t in linear.TOOLS}) == len(linear.TOOLS)


def test_every_tool_builds_its_schemas():
    for tool in linear.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_every_tool_is_the_same_post_to_the_same_url():
    """A GraphQL API has one endpoint; the document is what differs."""
    for tool in linear.TOOLS:
        assert tool.method == "POST", tool.name
        assert tool.url_template == "graphql", tool.name
        assert tool.base_url == "https://api.linear.app/", tool.name


def test_every_tool_declares_the_envelope():
    """Failure detection belongs to the API, so it is declared once on the factory."""
    for tool in linear.TOOLS:
        assert tool.envelope is linear.LINEAR_ENVELOPE, tool.name


def test_the_envelope_covers_both_places_linear_reports_failure():
    """The document-level array, and the refusal nested inside the payload."""
    assert linear.LINEAR_ENVELOPE.errors_field == "errors"
    assert linear.LINEAR_ENVELOPE.ok_field == "data.*.success"


@respx.mock
async def test_a_mutation_added_without_ceremony_is_still_guarded():
    """The reason this is a declaration and not a response handler.

    A tool built from the factory with no handler at all — the shape somebody
    adds in a hurry — must still refuse a declined mutation. When this logic
    lived in each mutation's handler, that tool reported the write as done.
    """
    respx.post(API).mock(
        return_value=httpx.Response(200, json={"data": {"issueArchive": {"success": False}}})
    )

    added_later = linear._linear(
        name="issue_archive",
        args_schema=linear.types.ViewerRequest,
        method="POST",
        url_template=linear.GRAPHQL_PATH,
        static_body={"query": 'mutation { issueArchive(id: "x") { success } }'},
    )

    with pytest.raises(APIError, match="issueArchive.success is false"):
        await added_later.ainvoke()


@respx.mock
async def test_a_successful_mutation_is_not_mistaken_for_a_failure():
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueCreate": {"success": True, "issue": {"id": "i1"}}}}
        )
    )
    await linear.issue_create.ainvoke(variables={"input": {"team_id": "t1", "title": "ok"}})


@respx.mock
async def test_a_query_has_no_success_flag_and_must_not_trip_the_envelope():
    """`data.*.success` matches nothing on a query — silence is not failure."""
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    out = await linear.issues_list.ainvoke(variables={"first": 1})

    assert [n["id"] for n in out["nodes"]] == ["1"]


# -----------------------------------------------------
# static_body: the query document is a constant, not an argument
# -----------------------------------------------------


def test_every_tool_carries_its_document_as_a_constant():
    for tool in linear.TOOLS:
        assert tool.static_body is not None, tool.name
        assert "query" in tool.static_body, tool.name
        assert tool.static_body["query"].strip(), tool.name


def test_the_model_can_never_see_or_write_the_query_document():
    """The whole boundary: a GraphQL URL accepts arbitrary documents.

    If the model could supply the query, `issues_list` would not be a narrower
    capability than "call Linear" — it would be a shell. The document lives in
    static_body, which is structurally unreachable from tool arguments.
    """
    for tool in linear.TOOLS:
        fields = set(tool.llm_schema().model_fields)
        assert fields <= {"variables"}, tool.name
        assert "query" not in fields, tool.name


def test_documents_are_distinct_per_tool():
    documents = {t.name: t.static_body["query"] for t in linear.TOOLS}
    assert len(set(documents.values())) == len(documents)


@respx.mock
async def test_the_document_and_the_variables_arrive_together():
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list.ainvoke(variables={"first": 10})

    sent = _sent()
    assert set(sent) == {"query", "variables"}
    assert sent["query"] == linear.queries.ISSUES
    assert sent["variables"] == {"first": 10}


@respx.mock
async def test_tool_input_cannot_overwrite_the_document():
    """static_body is applied last, so a `query` in the variables cannot win."""
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list.ainvoke(variables={"first": 5})

    assert _sent()["query"] == linear.queries.ISSUES


# -----------------------------------------------------
# Auth: the raw key, with no scheme
# -----------------------------------------------------


@respx.mock
async def test_a_personal_api_key_is_sent_with_no_bearer_prefix():
    """Linear's one deviation from almost every other API in this repository."""
    respx.post(API).mock(return_value=httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}}))

    await linear.viewer.ainvoke()

    assert respx.calls.last.request.headers["authorization"] == "lin_api_test123"


def test_headers_resolve_per_request():
    for tool in linear.TOOLS:
        assert callable(tool.api_key_headers)


@respx.mock
async def test_an_unconfigured_pack_raises_before_it_reaches_the_network(monkeypatch):
    monkeypatch.setattr(linear._headers, "_api_key", None)
    route = respx.post(API).mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(CredentialError, match="configure"):
        await linear.viewer.ainvoke()

    assert not route.called


# -----------------------------------------------------
# Variables and casing
# -----------------------------------------------------


@respx.mock
async def test_snake_case_variables_arrive_camel_cased():
    """GraphQL variable names are camelCase; the schema is written snake_case."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueCreate": {"success": True, "issue": {"id": "1"}}}}
        )
    )

    await linear.issue_create.ainvoke(
        variables={
            "input": {
                "team_id": "team-uuid",
                "title": "Flaky test",
                "assignee_id": "user-uuid",
                "label_ids": ["l1", "l2"],
                "due_date": "2026-09-01",
            }
        }
    )

    sent = _sent()["variables"]["input"]
    assert sent == {
        "teamId": "team-uuid",
        "title": "Flaky test",
        "assigneeId": "user-uuid",
        "labelIds": ["l1", "l2"],
        "dueDate": "2026-09-01",
    }


@respx.mock
async def test_the_in_comparator_loses_its_keyword_underscore_on_the_wire():
    """`in` is a Python keyword; the casing layer restores the wire spelling."""
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list.ainvoke(
        variables={"filter": {"state": {"type": {"in_": ["started", "unstarted"]}}}}
    )

    assert _sent()["variables"]["filter"]["state"]["type"] == {"in": ["started", "unstarted"]}


@respx.mock
async def test_a_nested_relationship_filter_survives_intact():
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list.ainvoke(
        variables={
            "filter": {
                "team": {"key": {"eq": "ENG"}},
                "assignee": {"email": {"eq": "ada@example.com"}},
                "title": {"contains_ignore_case": "flake"},
            },
            "order_by": "updatedAt",
        }
    )

    variables = _sent()["variables"]
    assert variables["filter"]["team"]["key"]["eq"] == "ENG"
    assert variables["filter"]["assignee"]["email"]["eq"] == "ada@example.com"
    assert variables["filter"]["title"]["containsIgnoreCase"] == "flake"
    assert variables["orderBy"] == "updatedAt"


@respx.mock
async def test_a_query_with_no_variables_still_sends_the_document():
    respx.post(API).mock(return_value=httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}}))

    await linear.viewer.ainvoke()

    sent = _sent()
    assert sent["query"] == linear.queries.VIEWER
    # No variables were supplied, so none are sent — a valid GraphQL request.
    assert "variables" not in sent or sent["variables"] in ({}, None)
    assert respx.calls.last.request.headers["content-type"] == "application/json"


def test_no_document_selects_a_deprecated_field():
    """Checked against Linear's live introspection.

    `Team.private` is superseded by `Team.visibility` (an enum: public,
    restricted, private) and `Project.state` by `Project.status`, an object.
    Both still resolve today, which is exactly why a mocked suite cannot see
    them going.
    """
    from charter.packs.linear import queries

    assert "private" not in queries.TEAMS
    assert "visibility" in queries.TEAMS
    assert "status {" in queries.PROJECTS
    assert "description state" not in queries.PROJECTS


# -----------------------------------------------------
# Failure: the two ways a Linear write fails while looking fine
# -----------------------------------------------------


@respx.mock
async def test_an_errors_array_raises_even_though_the_status_is_200():
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "Field 'bogus' doesn't exist on type 'IssueFilter'"}]},
        )
    )

    with pytest.raises(APIError, match="doesn't exist"):
        await linear.issues_list.ainvoke(variables={"first": 5})


@respx.mock
async def test_a_declined_mutation_raises_even_with_no_errors_array():
    """The trap the *root-level* envelope misses.

    Linear reports a refused mutation as `success: false` inside a perfectly
    valid `data`, with HTTP 200 and no `errors`. Both other signals say the call
    worked. LINEAR_ENVELOPE reaches it with a path, so the runtime raises — there
    is no per-tool handler to forget.
    """
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueCreate": {"success": False, "issue": None}}}
        )
    )

    with pytest.raises(APIError, match="data.issueCreate.success is false"):
        await linear.issue_create.ainvoke(variables={"input": {"team_id": "t1", "title": "Nope"}})


@respx.mock
async def test_a_successful_mutation_returns_the_object_without_the_flag():
    respx.post(API).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "issueCreate": {
                        "success": True,
                        "issue": {"id": "i1", "identifier": "ENG-42", "title": "Flaky test"},
                    }
                }
            },
        )
    )

    out = await linear.issue_create.ainvoke(
        variables={"input": {"team_id": "t1", "title": "Flaky test"}}
    )

    assert out == {"issue": {"id": "i1", "identifier": "ENG-42", "title": "Flaky test"}}
    assert "success" not in out


@respx.mock
async def test_a_401_becomes_a_credential_error():
    respx.post(API).mock(return_value=httpx.Response(401, json={"error": "invalid api key"}))

    with pytest.raises(CredentialError):
        await linear.viewer.ainvoke()


# -----------------------------------------------------
# Unwrapping and pagination
# -----------------------------------------------------


@respx.mock
async def test_the_graphql_envelope_is_stripped_but_page_info_is_kept():
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1", "2")))

    out = await linear.issues_list.ainvoke(variables={"first": 2})

    assert "data" not in out
    assert [n["id"] for n in out["nodes"]] == ["1", "2"]
    # pageInfo is the cursor; trimming it would break paging.
    assert out["pageInfo"]["endCursor"] == "cur"


def test_the_cursor_goes_back_out_nested_inside_variables():
    """Relay puts the cursor inside the variables object, not beside it."""
    assert linear.LINEAR_PAGINATION.cursor_param == "variables.after"
    assert linear.LINEAR_PAGINATION.cursor_field == "pageInfo.endCursor"

    page = {"nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "c2"}}
    assert linear.LINEAR_PAGINATION.next_page_args(page, {"variables": {"first": 50}}) == {
        "variables": {"first": 50, "after": "c2"}
    }


def test_setting_a_nested_cursor_does_not_mutate_the_previous_arguments():
    previous = {"variables": {"first": 50}}
    page = {"pageInfo": {"hasNextPage": True, "endCursor": "c2"}}

    linear.LINEAR_PAGINATION.next_page_args(page, previous)

    assert previous == {"variables": {"first": 50}}


def test_only_the_connections_declare_pagination():
    """Every tool that pages, and no tool that does not.

    A "get one" endpoint labelled with a cursor is a marker that lies, so this
    is asserted as an exact set rather than a count.
    """
    paging = {t.name for t in linear.TOOLS if t.pagination is not None}
    assert paging == {
        "teams_list",
        "users_list",
        "workflow_states_list",
        "team_memberships_list",
        "issues_list",
        "issue_relations_list",
        "comments_list",
        "issue_labels_list",
        "project_labels_list",
        "projects_list",
        "project_statuses_list",
        "project_milestones_list",
        "project_updates_list",
        "cycles_list",
        "initiatives_list",
        "initiative_updates_list",
        "documents_list",
        "attachments_list",
        "attachments_for_url",
        "customers_list",
        "customer_needs_list",
        "customer_statuses_list",
        "customer_tiers_list",
        "notifications_list",
        "favorites_list",
        "custom_views_list",
        "search_issues",
        "search_projects",
        "search_documents",
        "webhooks_list",
    }


def test_every_paging_tool_accepts_the_cursor_it_is_declared_with():
    """`variables.after` must name a field the schema really has."""
    for tool in linear.TOOLS:
        if tool.pagination is None:
            continue
        variables = tool.llm_schema().model_fields["variables"].annotation
        inner = getattr(variables, "__args__", (variables,))[0]
        assert "after" in inner.model_fields, tool.name


@respx.mock
async def test_a_two_page_walk_against_the_wire():
    respx.post(API).mock(
        side_effect=[
            httpx.Response(200, json=_issues_page("1", "2", cursor="c1", more=True)),
            httpx.Response(200, json=_issues_page("3", cursor="c2", more=False)),
        ]
    )

    args: Dict[str, Any] = {"variables": {"first": 2}}
    collected = []
    page = await linear.issues_list.ainvoke(args)
    collected += page["nodes"]
    while (args := linear.issues_list.pagination.next_page_args(page, args)) is not None:
        page = await linear.issues_list.ainvoke(args)
        collected += page["nodes"]

    assert [n["id"] for n in collected] == ["1", "2", "3"]
    assert json.loads(respx.calls[1].request.content)["variables"]["after"] == "c1"


# -----------------------------------------------------
# Schema constraints
# -----------------------------------------------------


def test_an_empty_update_is_rejected_before_it_is_sent():
    """A mutation that changes nothing is a wasted write and a confusing log."""
    with pytest.raises(ToolValidationError):
        _validate(linear.issue_update, {"variables": {"id": "i1", "input": {}}})


def test_a_real_update_passes():
    _validate(linear.issue_update, {"variables": {"id": "i1", "input": {"priority": 1}}})


def test_issue_create_requires_a_team_and_a_title():
    with pytest.raises(ToolValidationError):
        _validate(linear.issue_create, {"variables": {"input": {"title": "No team"}}})
    with pytest.raises(ToolValidationError):
        _validate(linear.issue_create, {"variables": {"input": {"team_id": "t1"}}})


def test_priority_is_constrained_to_linears_scale():
    with pytest.raises(ToolValidationError):
        _validate(
            linear.issue_create,
            {"variables": {"input": {"team_id": "t1", "title": "x", "priority": 9}}},
        )


def test_paging_arguments_are_optional_everywhere():
    for tool in linear.TOOLS:
        required = tool.to_json_schema()["parameters"].get("required", [])
        assert "first" not in required and "after" not in required, tool.name


# -----------------------------------------------------
# The filter layer: boolean composition, and the full comparator set
# -----------------------------------------------------


@respx.mock
async def test_a_boolean_composition_survives_to_the_wire():
    """`and_`/`or_` are Python-safe spellings of `and`/`or`.

    The trailing underscore is stripped by the casing layer on the way out, the
    same way `in_` is. An earlier version of this pack could not express
    "urgent OR assigned to me" at all and said so as a known limit.
    """
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list_full.ainvoke(
        variables={
            "filter": {
                "or_": [
                    {"priority": {"eq": 1}},
                    {"assignee": {"is_me": {"eq": True}}},
                ],
                "and_": [{"state": {"type": {"neq": "completed"}}}],
            }
        }
    )

    sent = _sent()["variables"]["filter"]
    assert set(sent) == {"or", "and"}
    assert sent["or"][0]["priority"] == {"eq": 1}
    assert sent["or"][1]["assignee"]["isMe"] == {"eq": True}
    assert sent["and"][0]["state"]["type"] == {"neq": "completed"}


@respx.mock
async def test_a_filter_nests_arbitrarily_deep():
    """The recursion is real, not one level of it dressed up."""
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list_full.ainvoke(
        variables={
            "filter": {
                "or_": [
                    {"and_": [{"title": {"contains": "flake"}}, {"priority": {"lte": 2}}]},
                    {"parent": {"team": {"key": {"eq": "ENG"}}}},
                ]
            }
        }
    )

    sent = _sent()["variables"]["filter"]
    assert sent["or"][0]["and"][1]["priority"] == {"lte": 2}
    assert sent["or"][1]["parent"]["team"]["key"] == {"eq": "ENG"}


def test_the_string_comparator_carries_every_operator_linear_accepts():
    """Asserted against Linear's list, not against itself.

    A comparator missing an operator rejects a filter the API would have
    honoured, and the model cannot tell that from Linear refusing it.
    """
    from charter.packs.linear.types.common import StringComparator

    assert set(StringComparator.model_fields) == {
        "eq",
        "neq",
        "eq_ignore_case",
        "neq_ignore_case",
        "in_",
        "nin",
        "contains",
        "contains_ignore_case",
        "contains_ignore_case_and_accent",
        "not_contains",
        "not_contains_ignore_case",
        "starts_with",
        "starts_with_ignore_case",
        "not_starts_with",
        "ends_with",
        "not_ends_with",
    }


# -----------------------------------------------------
# Enums, asserted against the API's values
# -----------------------------------------------------


def test_issue_relation_type_holds_linears_four_values():
    from typing import get_args

    from charter.packs.linear.types.issues import IssueRelationType

    assert set(get_args(IssueRelationType)) == {"blocks", "duplicate", "related", "similar"}


def test_initiative_status_is_capitalised_the_way_linear_spells_it():
    from typing import get_args

    from charter.packs.linear.types.initiatives import InitiativeStatus

    assert set(get_args(InitiativeStatus)) == {
        "Planned",
        "Proposed",
        "Active",
        "Completed",
        "Canceled",
    }


def test_project_health_holds_the_three_values_a_status_update_reports():
    from typing import get_args

    from charter.packs.linear.types.projects import ProjectHealth

    assert set(get_args(ProjectHealth)) == {"onTrack", "atRisk", "offTrack"}


def test_priority_is_described_with_linears_own_wording():
    """Linear's schema documents 3 as Medium. The pack used to say Normal."""
    from charter.packs.linear.types.common import PRIORITY_DESCRIPTION

    assert "3 = Medium" in PRIORITY_DESCRIPTION
    assert "Normal" not in PRIORITY_DESCRIPTION


# -----------------------------------------------------
# A comment has several possible parents, not one
# -----------------------------------------------------


@respx.mock
async def test_a_comment_can_be_posted_on_a_project():
    """The bug this models away.

    `issue_id` used to be required, which modelled one of the parents and made
    the others unreachable — there was no way to comment on a project.
    """
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"commentCreate": {"success": True, "comment": {"id": "c1"}}}}
        )
    )

    await linear.comment_create.ainvoke(
        variables={"input": {"project_id": "p1", "body": "Shipping Friday."}}
    )

    assert _sent()["variables"]["input"] == {"projectId": "p1", "body": "Shipping Friday."}


def test_a_comment_with_no_parent_is_refused_before_it_is_sent():
    with pytest.raises(ToolValidationError):
        _validate(linear.comment_create, {"variables": {"input": {"body": "orphan"}}})


def test_a_comment_with_two_parents_is_refused_before_it_is_sent():
    with pytest.raises(ToolValidationError):
        _validate(
            linear.comment_create,
            {"variables": {"input": {"body": "both", "issue_id": "i1", "project_id": "p1"}}},
        )


def test_a_reaction_needs_exactly_one_target():
    _validate(linear.reaction_create, {"variables": {"input": {"emoji": "+1", "issue_id": "i1"}}})
    with pytest.raises(ToolValidationError):
        _validate(linear.reaction_create, {"variables": {"input": {"emoji": "+1"}}})
    with pytest.raises(ToolValidationError):
        _validate(
            linear.reaction_create,
            {"variables": {"input": {"emoji": "+1", "issue_id": "i1", "comment_id": "c1"}}},
        )


def test_a_favorite_needs_exactly_one_target():
    _validate(linear.favorite_create, {"variables": {"input": {"issue_id": "i1"}}})
    with pytest.raises(ToolValidationError):
        _validate(linear.favorite_create, {"variables": {"input": {}}})
    with pytest.raises(ToolValidationError):
        _validate(
            linear.favorite_create,
            {"variables": {"input": {"issue_id": "i1", "project_id": "p1"}}},
        )


# -----------------------------------------------------
# Payload shapes: the three ways a Linear mutation answers
# -----------------------------------------------------


def test_archive_mutations_select_entity_and_deletes_select_entity_id():
    """Not cosmetic: selecting the wrong one is a GraphQL error.

    An ordinary payload names what it changed after the resource, an archive
    payload always calls it `entity`, and a true delete carries no entity at
    all. These were checked against Linear's schema; they are pinned here so a
    later edit cannot quietly swap one for another.
    """
    from charter.packs.linear import queries

    for document in (
        queries.ISSUE_ARCHIVE,
        queries.ISSUE_UNARCHIVE,
        queries.ISSUE_DELETE,
        queries.PROJECT_UNARCHIVE,
        queries.DOCUMENT_UNARCHIVE,
        queries.INITIATIVE_ARCHIVE,
        queries.CYCLE_ARCHIVE,
        queries.WORKFLOW_STATE_ARCHIVE,
        queries.NOTIFICATION_ARCHIVE,
        queries.PROJECT_UPDATE_ARCHIVE,
    ):
        assert "entity {" in document

    for document in (
        queries.COMMENT_DELETE,
        queries.ISSUE_LABEL_DELETE,
        queries.ISSUE_RELATION_DELETE,
        queries.REACTION_DELETE,
        queries.FAVORITE_DELETE,
        queries.WEBHOOK_DELETE,
        queries.CUSTOMER_DELETE,
    ):
        assert "entityId" in document
        assert "entity {" not in document


def test_project_and_document_deletes_answer_with_an_archive_payload():
    """Both trash rather than erase, so both carry `entity` despite the name.

    Written the obvious way — `entityId`, like every other delete — these were
    two GraphQL errors that only a schema check would have caught.
    """
    from charter.packs.linear import queries

    assert "entity {" in queries.PROJECT_DELETE
    assert "entityId" not in queries.PROJECT_DELETE
    assert "entity {" in queries.DOCUMENT_DELETE
    assert "entityId" not in queries.DOCUMENT_DELETE


def test_customer_need_create_selects_no_entity_because_linear_returns_none():
    """The one mutation in the pack whose payload is `{success}` alone."""
    from charter.packs.linear import queries

    assert "success" in queries.CUSTOMER_NEED_CREATE
    assert "need {" not in queries.CUSTOMER_NEED_CREATE


# -----------------------------------------------------
# A project's status is an id, not a word
# -----------------------------------------------------


def test_project_update_takes_a_status_id_and_not_a_state_word():
    """The field the pack used to offer does not exist on Linear's input.

    `ProjectUpdateInput` has `statusId` and no `state`, so a tool offering
    `state="planned"` sent a field the API rejects.
    """
    from charter.packs.linear.types.projects import ProjectUpdateInput

    assert "status_id" in ProjectUpdateInput.model_fields
    assert "state" not in ProjectUpdateInput.model_fields


@respx.mock
async def test_a_project_status_change_goes_out_as_status_id():
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"projectUpdate": {"success": True, "project": {"id": "p1"}}}}
        )
    )

    await linear.project_update.ainvoke(variables={"id": "p1", "input": {"status_id": "st-uuid"}})

    assert _sent()["variables"]["input"] == {"statusId": "st-uuid"}


# -----------------------------------------------------
# Labels: adding is not replacing
# -----------------------------------------------------


@respx.mock
async def test_labels_can_be_added_without_replacing_the_existing_set():
    """Linear offers `addedLabelIds`, so read-modify-write is not needed."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueUpdate": {"success": True, "issue": {"id": "i1"}}}}
        )
    )

    await linear.issue_update.ainvoke(
        variables={"id": "i1", "input": {"added_label_ids": ["l1"], "removed_label_ids": ["l2"]}}
    )

    assert _sent()["variables"]["input"] == {
        "addedLabelIds": ["l1"],
        "removedLabelIds": ["l2"],
    }


# -----------------------------------------------------
# Destructive defaults
# -----------------------------------------------------


@respx.mock
async def test_deleting_an_issue_trashes_it_unless_asked_otherwise():
    """`permanentlyDelete` is irreversible, so it is never sent by default."""
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueDelete": {"success": True, "entity": {"id": "i1"}}}}
        )
    )

    await linear.issue_delete.ainvoke(variables={"id": "i1"})

    assert _sent()["variables"] == {"id": "i1"}


@respx.mock
async def test_creating_a_webhook_does_not_send_the_documented_enabled_default():
    """A default belongs to the request that omits the parameter.

    Linear documents `enabled: true`. Copying it onto the field would send it
    on every call, which is a different request from the one documented.
    """
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"webhookCreate": {"success": True, "webhook": {"id": "w1"}}}}
        )
    )

    await linear.webhook_create.ainvoke(
        variables={"input": {"url": "https://example.test/hook", "resource_types": ["Issue"]}}
    )

    assert _sent()["variables"]["input"] == {
        "url": "https://example.test/hook",
        "resourceTypes": ["Issue"],
    }


def test_a_webhook_cannot_be_scoped_to_one_team_and_all_teams_at_once():
    with pytest.raises(ToolValidationError):
        _validate(
            linear.webhook_create,
            {
                "variables": {
                    "input": {
                        "url": "https://example.test/hook",
                        "resource_types": ["Issue"],
                        "team_id": "t1",
                        "all_public_teams": True,
                    }
                }
            },
        )


# -----------------------------------------------------
# Update bodies mandate nothing — except where Linear says otherwise
# -----------------------------------------------------


def test_every_empty_update_is_refused_before_it_is_sent():
    """A mutation that changes nothing is a wasted write and a confusing log."""
    for tool in (
        linear.issue_update,
        linear.comment_update,
        linear.issue_label_update,
        linear.project_update,
        linear.project_milestone_update,
        linear.project_update_update,
        linear.cycle_update,
        linear.initiative_update,
        linear.document_update,
        linear.customer_update,
        linear.customer_need_update,
        linear.notification_update,
        linear.favorite_update,
        linear.webhook_update,
        linear.workflow_state_update,
        linear.team_membership_update,
        linear.issue_relation_update,
    ):
        with pytest.raises(ToolValidationError, match="at least one"):
            _validate(tool, {"variables": {"id": "x", "input": {}}})


def test_attachment_update_mandates_a_title_because_linear_does():
    """The documented exception, asserted rather than assumed."""
    from charter.packs.linear.types.attachments import AttachmentUpdateInput

    assert AttachmentUpdateInput.model_fields["title"].is_required()
    _validate(linear.attachment_update, {"variables": {"id": "a1", "input": {"title": "PR #4"}}})
    with pytest.raises(ToolValidationError):
        _validate(linear.attachment_update, {"variables": {"id": "a1", "input": {"subtitle": "x"}}})


# -----------------------------------------------------
# Deprecated surface stays out
# -----------------------------------------------------


def test_no_tool_reaches_a_deprecated_linear_domain():
    """Roadmaps were superseded by initiatives, and cycleCreate by cadence.

    Linear marks `roadmap`, `roadmaps`, `roadmapCreate`, `roadmapUpdate`,
    `roadmapArchive`, `roadmapUnarchive`, `roadmapDelete` and `cycleCreate`
    deprecated in its schema. A pack built from a third-party client binding
    rather than the schema would have shipped all of them.
    """
    names = {t.name for t in linear.TOOLS}
    assert not any("roadmap" in name for name in names)
    assert "cycle_create" not in names
    from charter.packs.linear.types.filters import ProjectFilter

    assert "roadmaps" not in ProjectFilter.model_fields

    documents = " ".join(t.static_body["query"] for t in linear.TOOLS)
    assert "roadmap" not in documents.lower()
    assert "cycleCreate" not in documents
    # `Team.private` is superseded by `Team.visibility`, and `Project.state` by
    # `Project.status`.
    assert "private" not in linear.queries.TEAMS
    assert "visibility" in linear.queries.TEAMS


def test_the_pack_declines_the_surface_it_says_it_declines():
    """The docstring names what is left out; this holds it to that."""
    names = {t.name for t in linear.TOOLS}
    for excluded in (
        "integration",
        "release",
        "oauth",
        "passkey",
        "saml",
        "logout",
        "organization_delete",
        "user_suspend",
        "team_create",
        "team_update",
        "team_delete",
        "issue_import",
        "git_automation",
        "agent_session",
        "agent_activity",
    ):
        assert not any(excluded in name for name in names), excluded


def test_cycle_period_is_when_not_which_cycle():
    """Linear's CyclePeriod is after/before/during, not current/next/previous.

    Those last three are boolean flags on CycleFilter (isActive, isNext,
    isPrevious). The pack used to mix the two up.
    """
    from typing import get_args

    from charter.packs.linear.types.common import CyclePeriod

    assert set(get_args(CyclePeriod)) == {"after", "before", "during"}


def test_sla_status_matches_linears_enum():
    from typing import get_args

    from charter.packs.linear.types.common import SlaStatus

    assert set(get_args(SlaStatus)) == {
        "Breached",
        "Completed",
        "Failed",
        "HighRisk",
        "LowRisk",
        "MediumRisk",
    }


def test_internal_and_actor_fields_are_not_on_issue_create():
    """createAsUser is OAuth-actor only; descriptionData is Prosemirror internals."""
    from charter.packs.linear.types.issues import IssueCreateInput

    names = set(IssueCreateInput.model_fields)
    for withheld in (
        "create_as_user",
        "display_icon_url",
        "description_data",
        "inherits_shared_access",
        "sla_breaches_at",
        "sla_started_at",
        "source_pull_request_comment_id",
    ):
        assert withheld not in names, withheld
    assert "template_id" in names
    assert "sla_type" in names
    assert "release_ids" in names


@respx.mock
async def test_a_collection_filter_survives_to_the_wire():
    """some/every/length are how Linear filters a related collection."""
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    await linear.issues_list_full.ainvoke(
        variables={
            "filter": {
                "comments": {
                    "some": {"body": {"contains_ignore_case": "flake"}},
                    "length": {"gte": 1},
                }
            }
        }
    )

    comments = _sent()["variables"]["filter"]["comments"]
    assert comments["some"]["body"] == {"containsIgnoreCase": "flake"}
    assert comments["length"] == {"gte": 1}


@respx.mock
async def test_issue_create_sends_the_full_modellable_input():
    respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"data": {"issueCreate": {"success": True, "issue": {"id": "1"}}}}
        )
    )

    await linear.issue_create.ainvoke(
        variables={
            "input": {
                "team_id": "t1",
                "title": "Imported",
                "template_id": "tpl-1",
                "sla_type": "onlyBusinessDays",
                "release_ids": ["r1"],
                "sub_issue_sort_order": 1.5,
            }
        }
    )

    sent = _sent()["variables"]["input"]
    assert sent["templateId"] == "tpl-1"
    assert sent["slaType"] == "onlyBusinessDays"
    assert sent["releaseIds"] == ["r1"]
    assert sent["subIssueSortOrder"] == 1.5


# -----------------------------------------------------
# Every tool, structurally
# -----------------------------------------------------


def test_no_optional_argument_is_secretly_required():
    """A field with no default is required in Pydantic v2.

    The single most common bug in a hand-written pack, checked here across all
    128 tools rather than trusted.
    """
    for tool in linear.TOOLS:
        variables = tool.llm_schema().model_fields["variables"].annotation
        inner = getattr(variables, "__args__", (variables,))[0]
        for name, field in inner.model_fields.items():
            if name in {"id", "input", "term", "url", "ids", "read_at", "label_id"}:
                continue
            assert not field.is_required(), f"{tool.name}.{name}"


def test_the_only_default_that_reaches_the_wire_is_the_page_size():
    """And it is the page size Linear itself applies when the field is absent.

    Everything else defaults to None and is dropped, so a no-argument call
    sends exactly what the documentation describes.
    """
    for tool in linear.TOOLS:
        variables = tool.llm_schema().model_fields["variables"].annotation
        inner = getattr(variables, "__args__", (variables,))[0]
        for name, field in inner.model_fields.items():
            if field.is_required():
                continue
            if name == "first":
                assert field.default == 50, tool.name
            else:
                assert field.default is None, f"{tool.name}.{name}"


def test_every_tool_names_an_operation_its_document_actually_contains():
    """The response handler strips `data` and then the operation name.

    Name an operation the document does not define and the handler returns the
    whole of `data` instead of the payload — a silent shape change rather than
    an error.
    """
    for tool in linear.TOOLS:
        handler = tool._response_handler
        operation = handler.__closure__[0].cell_contents
        assert operation in tool.static_body["query"], tool.name


@respx.mock
async def test_the_list_filter_is_narrowed_and_the_restriction_is_mechanical():
    """`issues_list` carries the conditions a list is narrowed by, and only those.

    The projection is not advice. A condition outside it fails validation before
    a request is built, which is the difference between a narrowed tool and a
    documented convention. The complete `IssueFilter` is still declared and still
    reachable — on `issues_list_full`, which is kept out of `TOOLS` because a
    187KB schema is one some providers reject outright.
    """
    respx.post(API).mock(return_value=httpx.Response(200, json=_issues_page("1")))

    # What a list is narrowed by still works, nested relation included.
    await linear.issues_list.ainvoke(
        variables={
            "filter": {
                "team": {"key": {"eq": "ENG"}},
                "state": {"type": {"eq": "started"}},
                "title": {"starts_with": "[h4d21a]"},
            }
        }
    )
    sent = _sent()["variables"]["filter"]
    assert sent["team"]["key"] == {"eq": "ENG"}
    assert sent["state"]["type"] == {"eq": "started"}
    assert sent["title"] == {"startsWith": "[h4d21a]"}

    # Boolean composition does not, and is refused locally.
    with pytest.raises(ToolValidationError):
        await linear.issues_list.ainvoke(variables={"filter": {"or_": [{"priority": {"eq": 1}}]}})

    # The same filter on the undiminished tool is accepted.
    await linear.issues_list_full.ainvoke(variables={"filter": {"or_": [{"priority": {"eq": 1}}]}})
    assert _sent()["variables"]["filter"]["or"][0]["priority"] == {"eq": 1}


def test_the_list_path_does_not_fetch_what_only_one_issue_needs():
    """`description` is a paragraph per node, 250 nodes to a page, and no part of
    picking an issue out of a list uses it. `issue_get` keeps the full selection."""
    assert "description" not in linear.queries.ISSUES
    assert "description" in linear.queries.ISSUE
    # The list still carries what identifies an issue.
    for field in ("identifier", "title", "state", "assignee", "team", "labels"):
        assert field in linear.queries.ISSUES


def test_no_list_tool_carries_the_whole_filter_mirror():
    """A tool a model is offered stays small enough for a model to accept.

    Two of three models tested reject a 187KB tool schema outright rather than
    degrade, so this is a hard property, not a preference. `custom_view_create`
    is the one exception: its filters arrive as `filter_data` on an input object
    rather than `variables.filter`, so `curation` does not reach them.
    """
    oversized = {
        t.name: len(json.dumps(t.to_json_schema()["parameters"]))
        for t in linear.TOOLS
        if len(json.dumps(t.to_json_schema()["parameters"])) > 50_000
    }
    assert oversized == {}, oversized


def test_every_narrowed_tool_keeps_an_undiminished_twin_out_of_tools():
    """Narrowing the model's view must not remove the capability from the SDK."""
    names = {t.name for t in linear.TOOLS}
    twins = [a for a in dir(linear) if a.endswith("_full")]
    assert len(twins) >= 16

    for attr in twins:
        full = getattr(linear, attr)
        narrowed = getattr(linear, attr[: -len("_full")])
        # The twin is reachable by name and is genuinely the wider tool.
        assert full is not narrowed
        assert len(json.dumps(full.to_json_schema()["parameters"])) > len(
            json.dumps(narrowed.to_json_schema()["parameters"])
        )
        # And it is not among the tools a pack hands a model.
        assert not any(t is full for t in linear.TOOLS)
        assert full.name in names  # same contract, same wire name


def test_the_curation_policy_keeps_scalars_and_one_level_of_relation():
    """The rule, pinned on a filter that exercises every branch of it."""
    from charter.packs.linear import curation

    paths = curation.list_filter_paths(linear.teams_list_full.args_schema)
    relative = {p.removeprefix("variables.filter.") for p in paths}

    assert "name" in relative and "key" in relative  # own scalars
    assert not any(p.startswith("issues.") for p in relative)  # collection dropped
    assert not any(p.startswith("parent.") for p in relative)  # own entity dropped
    assert not any(p.count(".") > 1 for p in relative)  # never two levels
    assert "and_" not in relative and "or_" not in relative  # no recursion

    # One level of relation is kept where the relation is a different entity.
    states = {
        p.removeprefix("variables.filter.")
        for p in curation.list_filter_paths(linear.workflow_states_list_full.args_schema)
    }
    assert "team.key" in states


def test_no_projection_leaves_a_module_path_where_a_type_name_belongs():
    """A type projected twice with different fields collides, and pydantic
    disambiguates it with its module - which then reaches the model and the
    published reference as `charter__execution__schema__TeamFilter_LLM__2`."""
    for tool in linear.TOOLS:
        defs = tool.to_json_schema()["parameters"].get("$defs", {})
        mangled = [d for d in defs if d.startswith("charter__")]
        assert not mangled, f"{tool.name}: {mangled}"


def test_a_tool_can_carry_more_than_one_filter():
    """`custom_view_create` saves a query as a view, so it has four.

    They hang off `variables.input`, not `variables.filter`. Finding filters by
    type rather than by name is what reaches them, and is what keeps the rule
    from needing a new clause the next time a tool puts one somewhere new.
    """
    from charter.packs.linear import curation

    roots = dict(curation.filter_roots(linear.custom_view_create_full.args_schema))
    assert set(roots) == {
        "variables.input.filter_data",
        "variables.input.project_filter_data",
        "variables.input.initiative_filter_data",
        "variables.input.feed_item_filter_data",
    }

    # Narrowing the filters leaves the rest of the input alone: a view still
    # needs its name, its team and its colour.
    params = linear.custom_view_create.to_json_schema()["parameters"]
    defs = params["$defs"]
    variables = defs[params["properties"]["variables"]["$ref"].rsplit("/", 1)[-1]]
    fields = defs[variables["properties"]["input"]["$ref"].rsplit("/", 1)[-1]]["properties"]
    for kept in ("name", "teamId", "color", "shared", "filterData"):
        assert kept in fields
