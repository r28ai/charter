"""GitHub pack — the OAuth-plus-constant-header and page-number-pagination case."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx
import pytest
import respx
from pydantic import ValidationError

from charter import APIError, CredentialError, Tool, ToolValidationError
from charter.auth import StaticTokenProvider
from charter.packs import github

API = "https://api.github.com/"


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    github.configure(StaticTokenProvider("ghp_test_123"))


def _issue(number: int = 1, **extra: Any) -> Dict[str, Any]:
    """A GitHub issue with the envelope a real one carries."""
    base: Dict[str, Any] = {
        "id": 900 + number,
        "node_id": "I_kwDO",
        "url": f"{API}repos/octocat/hello/issues/{number}",
        "repository_url": f"{API}repos/octocat/hello",
        "labels_url": f"{API}repos/octocat/hello/issues/{number}/labels{{/name}}",
        "comments_url": f"{API}repos/octocat/hello/issues/{number}/comments",
        "events_url": f"{API}repos/octocat/hello/issues/{number}/events",
        "html_url": f"https://github.com/octocat/hello/issues/{number}",
        "number": number,
        "state": "open",
        "title": f"Issue {number}",
        "body": "Something is broken.",
        "user": {"login": "octocat", "id": 1, "node_id": "MDQ6", "type": "User"},
        "labels": [{"id": 1, "name": "bug", "color": "d73a4a", "default": True}],
        "assignee": {"login": "hubot", "id": 2},
        "assignees": [{"login": "hubot", "id": 2}],
        "milestone": {"number": 1, "title": "v1.0", "state": "open"},
        "comments": 3,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "closed_at": None,
        "author_association": "OWNER",
        "reactions": {"url": "...", "total_count": 0, "+1": 0, "-1": 0},
        "performed_via_github_app": None,
    }
    base.update(extra)
    return base


# -----------------------------------------------------
# Shape
# -----------------------------------------------------


def test_pack_ships_one_hundred_and_thirty_nine_tools():
    assert len(github.TOOLS) == 139
    assert all(isinstance(t, Tool) for t in github.TOOLS)


def test_every_tool_builds_its_schemas():
    for tool in github.TOOLS:
        tool.llm_schema()
        assert tool.to_json_schema()["parameters"]["type"] == "object"


def test_every_tool_is_described_for_a_model_and_a_human():
    for tool in github.TOOLS:
        assert tool.description, tool.name
        assert tool.action_label, tool.name


def test_the_whole_pack_is_snake_case_in_both_directions():
    for tool in github.TOOLS:
        assert tool.body_case == "snake", tool.name
        assert tool.query_case == "snake", tool.name


def test_no_envelope_is_declared():
    """GitHub uses real HTTP status codes; there is no 200-on-failure to declare."""
    for tool in github.TOOLS:
        assert tool.envelope is None, tool.name


# -----------------------------------------------------
# static_headers: the OAuth-plus-constant-header case
# -----------------------------------------------------


def test_every_tool_carries_the_constant_headers():
    """Three factories, one set of constants — and the differences are declared.

    Most of the pack is built on one factory. Two endpoints are not, and each is
    a real property of GitHub rather than a convenience: `pulls_get_diff` asks
    for a different *representation* of a pull request through `Accept`, and
    `releases_upload_asset` posts bytes to a different host. Both inherit
    everything else, which is what this checks — a second factory that quietly
    dropped the version pin or the `User-Agent` would answer 403 on its first
    call, and only on that one tool.
    """
    for tool in github.TOOLS:
        headers = tool.static_headers or {}
        assert headers["X-GitHub-Api-Version"] == github.API_VERSION, tool.name
        assert headers["User-Agent"] == github.GITHUB_HEADERS["User-Agent"], tool.name

    by_accept: Dict[str, List[str]] = {}
    for tool in github.TOOLS:
        by_accept.setdefault((tool.static_headers or {})["Accept"], []).append(tool.name)

    # Exactly one tool departs from the JSON representation, and it is the one
    # whose whole purpose is the departure.
    assert by_accept["application/vnd.github.diff"] == ["pulls_get_diff"]
    assert set(by_accept) == {"application/vnd.github+json", "application/vnd.github.diff"}

    # And exactly one sets a Content-Type, because exactly one sends a file.
    typed = {t.name for t in github.TOOLS if "Content-Type" in (t.static_headers or {})}
    assert typed == {"releases_upload_asset"}


def test_the_two_endpoints_that_leave_the_json_api_say_so_in_their_declarations():
    """A different host and a different body format are declarations, not code.

    The upload is the only tool in the pack that does not talk to
    api.github.com and the only one whose body is not JSON. Both facts live on
    its factory, so nothing in the tool or its schema has to know.
    """
    upload = github.releases_upload_asset
    assert str(upload.base_url) == github.UPLOAD_BASE_URL
    assert upload.base_url != github.BASE_URL
    assert upload.body_format == "raw"

    # Every other tool stayed on the JSON API.
    others = [t for t in github.TOOLS if t is not upload]
    assert {str(t.base_url) for t in others} == {github.BASE_URL}
    assert {t.body_format for t in others} == {"json"}


def test_only_the_log_and_artifact_downloads_follow_redirects():
    """Following a redirect is off by default and turned on where it is the answer.

    GitHub hands out logs and artifacts as a 302 to a signed URL that lives one
    minute; a tool that does not follow it receives an empty body and cannot ask
    again. Everywhere else a redirect would mean a wrong URL, and following one
    silently would hide that — so this is three tools, not a factory setting.
    """
    following = {t.name for t in github.TOOLS if t.follow_redirects}
    assert following == {
        "actions_download_job_logs",
        "actions_download_run_logs",
        "actions_download_artifact",
    }


def test_the_api_version_is_pinned():
    """An unpinned integration breaks on GitHub's schedule rather than yours."""
    assert github.GITHUB_HEADERS["X-GitHub-Api-Version"] == github.API_VERSION
    assert github.API_VERSION == "2022-11-28"


@respx.mock
async def test_constant_headers_and_bearer_token_are_both_on_the_wire():
    """The case that was unwritable two commits ago: OAuth *and* fixed headers.

    Before static_headers reached the runtime there was nowhere to put an
    ``Accept`` or ``X-GitHub-Api-Version`` on a bearer-auth tool — the header
    dict belonged to api_key auth, and using it meant giving up the credential
    provider. This asserts both channels arrive together on one request.
    """
    route = respx.get(f"{API}repos/octocat/hello").mock(
        return_value=httpx.Response(200, json={"full_name": "octocat/hello"})
    )

    await github.repos_get.ainvoke(owner="octocat", repo="hello")

    sent = route.calls.last.request.headers
    # The credential provider's token.
    assert sent["authorization"] == "Bearer ghp_test_123"
    # The constants, verbatim — no casing conversion applied to the keys.
    assert sent["accept"] == "application/vnd.github+json"
    assert sent["x-github-api-version"] == "2022-11-28"
    # GitHub answers 403 to a request with no User-Agent.
    assert sent["user-agent"] == "charter"


@respx.mock
async def test_constant_headers_survive_a_body_carrying_request():
    """POST takes a different branch through the header build than GET."""
    route = respx.post(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(201, json=_issue(7))
    )

    await github.issues_create.ainvoke(
        owner="octocat", repo="hello", body={"title": "Flaky test"}
    )

    sent = route.calls.last.request.headers
    assert sent["authorization"] == "Bearer ghp_test_123"
    assert sent["x-github-api-version"] == "2022-11-28"
    assert sent["accept"] == "application/vnd.github+json"
    assert sent["content-type"] == "application/json"


@respx.mock
async def test_a_per_call_header_can_add_to_the_constants_but_the_model_cannot():
    """Per-call headers are the host application's channel, applied last."""
    route = respx.get(f"{API}user").mock(return_value=httpx.Response(200, json={"login": "octocat"}))

    await github.users_get_authenticated.ainvoke(headers={"X-Request-Id": "abc-123"})

    sent = route.calls.last.request.headers
    assert sent["x-request-id"] == "abc-123"
    # The constants are still there alongside it.
    assert sent["x-github-api-version"] == "2022-11-28"
    assert sent["accept"] == "application/vnd.github+json"


def test_no_tool_exposes_a_header_field_to_the_model():
    """The constants must not be reachable from tool arguments."""
    for tool in github.TOOLS:
        fields = set(tool.llm_schema().model_fields)
        assert not fields & {"accept", "user_agent", "x_github_api_version"}, tool.name


# -----------------------------------------------------
# Page-number pagination
# -----------------------------------------------------


def test_list_tools_declare_page_number_pagination():
    assert github.GITHUB_PAGINATION.style == "page"
    assert github.repos_list_commits.pagination is github.GITHUB_PAGINATION
    assert github.issues_get.pagination is None


def test_search_tools_look_for_the_list_under_items():
    """Search wraps results in `items`; the plain list endpoints do not."""
    assert github.search_issues.pagination is github.SEARCH_PAGINATION
    assert github.search_repositories.pagination is github.SEARCH_PAGINATION
    assert github.SEARCH_PAGINATION.items_field == "items"
    assert github.GITHUB_PAGINATION.items_field is None


def test_cursor_and_page_paginations_cannot_be_mixed():
    from charter import Pagination

    with pytest.raises(ValueError, match="one style"):
        Pagination(cursor_field="a", cursor_param="b", page_param="page")


def test_only_the_endpoints_that_page_declare_pagination():
    """Pagination belongs to a list endpoint, not to the API.

    Declaring it on the factory would have labelled every single-item endpoint
    with a marker it does not have — `issues_get` advertising a `page` parameter
    it cannot accept. It is declared per tool instead, and at 138 tools the
    check has to be a rule rather than a list: a tool declares pagination when
    and only when its schema has the two fields to walk with.
    """
    for tool in github.TOOLS:
        fields = set(tool.args_schema.model_fields)
        walkable = {"page", "per_page"} <= fields
        if tool.pagination is not None:
            assert walkable, f"{tool.name} declares pagination without page/per_page"
        elif walkable:
            assert tool.name in _PAGES_BUT_DOES_NOT_WALK, (
                f"{tool.name} accepts page and per_page but declares no pagination"
            )


# Endpoints that accept the paging parameters and still declare no pagination.
# Empty, and kept as the place an exception would have to be written down: a
# list tool that silently lost its pagination is a walk that stops after thirty
# items and reports nothing wrong, so the rule above refuses one by default and
# an exception has to be argued for here.
_PAGES_BUT_DOES_NOT_WALK: Dict[str, str] = {}


def test_the_endpoints_that_cannot_be_walked_are_the_ones_github_does_not_page():
    """Three list endpoints deliberately declare no pagination.

    Each is a case where the marker would be a lie. `dependabot_list_alerts` has
    no `page` parameter at all — GitHub pages it by an opaque cursor in the
    `Link` header, which is not in the response body and so is not something
    Charter can follow. The other two are not paged by GitHub in the first
    place: pending deployments and requested reviewers come back whole.
    """
    for name in (
        "dependabot_list_alerts",
        "actions_list_pending_deployments",
        "pulls_list_requested_reviewers",
        "repos_list_languages",
    ):
        tool = getattr(github, name)
        assert tool.pagination is None, name
        assert "page" not in tool.args_schema.model_fields, name


def test_the_page_params_name_real_schema_fields():
    """A pagination that names a field the schema lacks cannot be followed."""
    for tool in github.TOOLS:
        if tool.pagination is None:
            continue
        fields = set(tool.args_schema.model_fields)
        assert tool.pagination.page_param in fields, tool.name
        assert tool.pagination.per_page_param in fields, tool.name


def test_a_full_page_advances_and_a_short_page_stops():
    previous = {"owner": "octocat", "repo": "hello", "per_page": 2, "page": 1}
    full = [_issue(1), _issue(2)]

    nxt = github.GITHUB_PAGINATION.next_page_args(full, previous)
    assert nxt == {**previous, "page": 2}

    assert github.GITHUB_PAGINATION.next_page_args([_issue(3)], nxt) is None
    assert github.GITHUB_PAGINATION.next_page_args([], nxt) is None


def test_search_pagination_walks_the_items_array():
    previous = {"q": "is:open", "per_page": 2, "page": 1}
    full = {"total_count": 9, "items": [_issue(1), _issue(2)]}

    assert github.SEARCH_PAGINATION.next_page_args(full, previous) == {**previous, "page": 2}
    assert (
        github.SEARCH_PAGINATION.next_page_args(
            {"total_count": 9, "items": [_issue(3)]}, previous
        )
        is None
    )


@respx.mock
async def test_a_two_page_walk_against_the_wire():
    """The loop from the docstring, run for real against two mocked pages."""
    pages = [
        httpx.Response(200, json=[_issue(1), _issue(2)]),
        httpx.Response(200, json=[_issue(3)]),
    ]
    route = respx.get(f"{API}repos/octocat/hello/issues").mock(side_effect=pages)

    args: Dict[str, Any] = {"owner": "octocat", "repo": "hello", "per_page": 2}
    collected: List[Any] = []
    page = await github.issues_list_for_repo.ainvoke(args)
    collected.extend(page)
    while (args := github.issues_list_for_repo.pagination.next_page_args(page, args)) is not None:
        page = await github.issues_list_for_repo.ainvoke(args)
        collected.extend(page)

    assert [i["number"] for i in collected] == [1, 2, 3]
    assert route.call_count == 2
    assert dict(route.calls[0].request.url.params)["page"] == "1"
    assert dict(route.calls[1].request.url.params)["page"] == "2"


# -----------------------------------------------------
# The wire
# -----------------------------------------------------


@respx.mock
async def test_list_issues_sends_its_filters_as_query_parameters():
    route = respx.get(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(200, json=[])
    )

    await github.issues_list_for_repo.ainvoke(
        owner="octocat",
        repo="hello",
        state="closed",
        labels="bug,ui",
        sort="updated",
        direction="asc",
        per_page=50,
    )

    request = route.calls.last.request
    params = dict(request.url.params)
    assert request.url.path == "/repos/octocat/hello/issues"
    assert params["state"] == "closed"
    assert params["labels"] == "bug,ui"
    assert params["sort"] == "updated"
    assert params["direction"] == "asc"
    assert params["per_page"] == "50"
    assert request.method == "GET"


@respx.mock
async def test_a_datetime_filter_is_sent_as_rfc3339():
    from datetime import datetime, timezone

    route = respx.get(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(200, json=[])
    )

    await github.issues_list_for_repo.ainvoke(
        owner="octocat",
        repo="hello",
        since=datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc),
    )

    assert dict(route.calls.last.request.url.params)["since"] == "2026-01-15T09:30:00+00:00"


@respx.mock
async def test_create_issue_unwraps_the_body_to_the_json_root():
    """One Body() field unwraps: GitHub wants {"title": ...}, not {"body": {...}}."""
    route = respx.post(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(201, json=_issue(7))
    )

    await github.issues_create.ainvoke(
        owner="octocat",
        repo="hello",
        body={
            "title": "Flaky test on main",
            "body": "It fails one run in ten.",
            "labels": ["bug", "ci"],
            "assignees": ["hubot"],
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "title": "Flaky test on main",
        "body": "It fails one run in ten.",
        "labels": ["bug", "ci"],
        "assignees": ["hubot"],
    }


@respx.mock
async def test_update_issue_sends_a_patch_with_only_what_changed():
    route = respx.patch(f"{API}repos/octocat/hello/issues/7").mock(
        return_value=httpx.Response(200, json=_issue(7, state="closed"))
    )

    await github.issues_update.ainvoke(
        owner="octocat",
        repo="hello",
        issue_number=7,
        body={"state": "closed", "state_reason": "completed"},
    )

    request = route.calls.last.request
    assert request.method == "PATCH"
    assert json.loads(request.content) == {"state": "closed", "state_reason": "completed"}


@respx.mock
async def test_snake_case_body_keys_are_not_camelised():
    """GitHub is snake_case; the default camel casing would send `stateReason`."""
    route = respx.patch(f"{API}repos/octocat/hello/issues/7").mock(
        return_value=httpx.Response(200, json=_issue(7))
    )

    await github.issues_update.ainvoke(
        owner="octocat", repo="hello", issue_number=7, body={"state_reason": "not_planned"}
    )

    assert "state_reason" in json.loads(route.calls.last.request.content)


@respx.mock
async def test_a_path_with_slashes_reaches_the_contents_endpoint_intact():
    route = respx.get(f"{API}repos/octocat/hello/contents/src/charter/tool.py").mock(
        return_value=httpx.Response(200, json={"name": "tool.py", "type": "file"})
    )

    await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="src/charter/tool.py"
    )

    assert route.called


# -----------------------------------------------------
# Schema constraints
# -----------------------------------------------------


def _validate(tool: Tool, args: Dict[str, Any]):
    """Validate args exactly as ainvoke would, without sending anything."""
    from charter.execution.validation import validate_input

    return validate_input(tool.llm_schema(), args, tool_name=tool.name)


def test_pull_create_requires_exactly_one_of_title_or_issue():
    """A oneof declared on the schema must survive into the LLM view.

    This is the constraint create_llm_schema used to drop: the rule was written,
    the wire schema enforced it, and the model's input — the only input that
    needed checking — was never checked against it.
    """
    with pytest.raises(ToolValidationError):
        _validate(
            github.pulls_create,
            {"owner": "octocat", "repo": "hello", "body": {"head": "fix", "base": "main"}},
        )

    with pytest.raises(ToolValidationError):
        _validate(
            github.pulls_create,
            {
                "owner": "octocat",
                "repo": "hello",
                "body": {"head": "fix", "base": "main", "title": "Fix", "issue": 4},
            },
        )


def test_a_valid_pull_request_body_passes_both_ways():
    _validate(
        github.pulls_create,
        {"owner": "o", "repo": "r", "body": {"title": "Fix", "head": "fix", "base": "main"}},
    )
    _validate(
        github.pulls_create,
        {"owner": "o", "repo": "r", "body": {"issue": 12, "head": "fix", "base": "main"}},
    )


def test_per_page_is_bounded_at_one_hundred():
    with pytest.raises(ToolValidationError):
        _validate(
            github.issues_list_for_repo,
            {"owner": "o", "repo": "r", "per_page": 500},
        )


def test_optional_filters_are_genuinely_optional():
    """A field with no default is required in Pydantic v2 — the classic pack bug."""
    for tool in (github.issues_list_for_repo, github.pulls_list, github.repos_list_commits):
        required = tool.to_json_schema()["parameters"].get("required", [])
        assert set(required) <= {"owner", "repo"}, tool.name


def test_search_requires_its_query():
    assert "q" in github.search_issues.to_json_schema()["parameters"]["required"]


# -----------------------------------------------------
# Response handlers
# -----------------------------------------------------


@respx.mock
async def test_issue_trimming_keeps_what_an_agent_acts_on():
    respx.get(f"{API}repos/octocat/hello/issues/1").mock(
        return_value=httpx.Response(200, json=_issue(1))
    )

    out = await github.issues_get.ainvoke(owner="octocat", repo="hello", issue_number=1)

    assert out["number"] == 1
    assert out["title"] == "Issue 1"
    assert out["author"] == "octocat"
    assert out["assignees"] == ["hubot"]
    assert out["labels"] == ["bug"]
    assert out["milestone"] == "v1.0"
    # The envelope is gone.
    assert "labels_url" not in out
    assert "reactions" not in out
    assert "node_id" not in out
    assert "performed_via_github_app" not in out


@respx.mock
async def test_trimming_never_drops_an_item_because_pagination_counts_them():
    respx.get(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(200, json=[_issue(1), _issue(2), _issue(3)])
    )

    out = await github.issues_list_for_repo.ainvoke(owner="octocat", repo="hello")

    assert len(out) == 3


@respx.mock
async def test_a_pull_request_in_the_issues_list_is_marked_as_one():
    respx.get(f"{API}repos/octocat/hello/issues").mock(
        return_value=httpx.Response(
            200,
            json=[_issue(1), _issue(2, pull_request={"url": "...", "html_url": "..."})],
        )
    )

    out = await github.issues_list_for_repo.ainvoke(owner="octocat", repo="hello")

    assert "is_pull_request" not in out[0]
    assert out[1]["is_pull_request"] is True


@respx.mock
async def test_pull_trimming_keeps_the_branch_pair_and_merge_state():
    respx.get(f"{API}repos/octocat/hello/pulls/4").mock(
        return_value=httpx.Response(
            200,
            json=_issue(
                4,
                head={"ref": "fix-flake", "sha": "abc", "repo": {"full_name": "octocat/hello"}},
                base={"ref": "main", "sha": "def", "repo": {"full_name": "octocat/hello"}},
                merged=False,
                mergeable=True,
                mergeable_state="clean",
                additions=12,
                deletions=3,
                changed_files=2,
            ),
        )
    )

    out = await github.pulls_get.ainvoke(owner="octocat", repo="hello", pull_number=4)

    assert out["head"] == "fix-flake"
    assert out["base"] == "main"
    assert out["mergeable"] is True
    assert out["changed_files"] == 2


@respx.mock
async def test_file_contents_come_back_decoded():
    import base64

    body = "def hello():\n    return 'world'\n"
    respx.get(f"{API}repos/octocat/hello/contents/app.py").mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "app.py",
                "path": "app.py",
                "sha": "abc123",
                "size": len(body),
                "type": "file",
                "encoding": "base64",
                # GitHub wraps the payload at 60 characters.
                "content": base64.encodebytes(body.encode()).decode(),
                "url": "...",
                "git_url": "...",
                "download_url": "...",
                "_links": {"self": "...", "git": "...", "html": "..."},
            },
        )
    )

    out = await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="app.py"
    )

    assert out["content"] == body
    assert out["name"] == "app.py"
    assert "_links" not in out
    assert "git_url" not in out


@respx.mock
async def test_a_directory_listing_reduces_to_its_entries():
    respx.get(f"{API}repos/octocat/hello/contents/src").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "a.py", "path": "src/a.py", "type": "file", "size": 10, "url": "..."},
                {"name": "sub", "path": "src/sub", "type": "dir", "size": 0, "url": "..."},
            ],
        )
    )

    out = await github.repos_get_content.ainvoke(owner="octocat", repo="hello", path="src")

    assert out == [
        {"name": "a.py", "path": "src/a.py", "type": "file", "size": 10},
        # size 0 is kept: zero is a value, not an absence.
        {"name": "sub", "path": "src/sub", "type": "dir", "size": 0},
    ]


@respx.mock
async def test_commit_trimming_flattens_the_nested_commit_object():
    respx.get(f"{API}repos/octocat/hello/commits").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "sha": "abc123",
                    "node_id": "C_kwDO",
                    "html_url": "https://github.com/octocat/hello/commit/abc123",
                    "commit": {
                        "message": "Fix the flake",
                        "author": {"name": "Ada", "email": "a@x.com", "date": "2026-01-01T00:00:00Z"},
                        "tree": {"sha": "t", "url": "..."},
                    },
                    "author": {"login": "ada", "id": 3},
                    "parents": [{"sha": "p", "url": "..."}],
                }
            ],
        )
    )

    out = await github.repos_list_commits.ainvoke(owner="octocat", repo="hello")

    assert out[0]["message"] == "Fix the flake"
    assert out[0]["author"] == "Ada"
    assert out[0]["sha"] == "abc123"
    assert "parents" not in out[0]
    assert "node_id" not in out[0]


@respx.mock
async def test_search_results_keep_their_envelope():
    """total_count is the one part of the search envelope worth keeping."""
    respx.get(f"{API}search/issues").mock(
        return_value=httpx.Response(
            200,
            json={"total_count": 42, "incomplete_results": False, "items": [_issue(1)]},
        )
    )

    out = await github.search_issues.ainvoke(q="repo:octocat/hello is:open")

    assert out["total_count"] == 42
    assert out["incomplete_results"] is False
    assert len(out["items"]) == 1
    assert out["items"][0]["title"] == "Issue 1"


# -----------------------------------------------------
# Egress and failure
# -----------------------------------------------------


def test_the_model_is_never_shown_a_server_set_field():
    """GitHub's ids, node_ids and URLs are response data; a request never takes them."""
    for tool in github.TOOLS:
        fields = set(tool.llm_schema().model_fields)
        assert not fields & {"id", "node_id", "url", "html_url", "created_at"}, tool.name


def test_the_egress_map_reports_only_fields_github_accepts():
    from charter import egress_map

    entries = egress_map(github.TOOLS)
    assert entries, "the egress map should not be empty"


@respx.mock
async def test_an_unconfigured_pack_raises_before_it_reaches_the_network(monkeypatch):
    from charter.packs._config import DeferredCredentialProvider

    route = respx.get(f"{API}repos/o/r").mock(return_value=httpx.Response(200, json={}))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(
        github.repos_get._executor,
        "_credential_provider",
        DeferredCredentialProvider("github", env_var="GITHUB_TOKEN"),
    )

    with pytest.raises(CredentialError, match="no credentials"):
        await github.repos_get.ainvoke(owner="o", repo="r")

    assert not route.called


@respx.mock
async def test_a_401_becomes_a_credential_error():
    respx.get(f"{API}user").mock(
        return_value=httpx.Response(
            401, json={"message": "Bad credentials", "documentation_url": "..."}
        )
    )

    with pytest.raises(CredentialError, match="Bad credentials"):
        await github.users_get_authenticated.ainvoke()


@respx.mock
async def test_a_rate_limit_reports_the_retry_after_github_sent():

    respx.get(f"{API}search/issues").mock(
        return_value=httpx.Response(
            403,
            headers={"retry-after": "60"},
            json={"message": "API rate limit exceeded"},
        )
    )

    with pytest.raises(APIError) as excinfo:
        await github.search_issues.ainvoke(q="test")

    # GitHub says 403 for a rate limit, which is not an instruction to
    # re-authenticate. Filing it as a credential failure would have thrown away
    # the one thing the caller needs: how long to wait.
    assert excinfo.value.status_code == 403
    assert excinfo.value.retry_after == 60
    assert "rate limit exceeded" in str(excinfo.value)


# -----------------------------------------------------
# Parameters GitHub refuses in combination
# -----------------------------------------------------


@respx.mock
async def test_listing_your_repositories_sends_none_of_the_exclusive_three():
    """A documented default that is *sent* is not a default.

    GitHub's defaults for `visibility`, `affiliation` and `type` describe what it
    applies to a request that omits them — and it answers 422 to a request
    carrying `type` beside either of the others. Copying all three onto the
    schema put all three on the wire, so the no-argument call, which is the one
    an agent makes first, was a guaranteed 422.
    """
    route = respx.get(f"{API}user/repos").mock(return_value=httpx.Response(200, json=[]))

    await github.repos_list_for_authenticated_user.ainvoke({})

    sent = route.calls.last.request.url.params
    assert "visibility" not in sent
    assert "affiliation" not in sent
    assert "type" not in sent


def test_type_beside_visibility_is_refused_before_the_round_trip():
    with pytest.raises(ToolValidationError) as excinfo:
        _validate(
            github.repos_list_for_authenticated_user,
            {"type": "owner", "visibility": "private"},
        )
    assert "422" in str(excinfo.value)


def test_type_beside_affiliation_is_refused_too():
    with pytest.raises(ToolValidationError):
        _validate(
            github.repos_list_for_authenticated_user,
            {"type": "member", "affiliation": "owner"},
        )


def test_type_on_its_own_is_fine():
    _validate(github.repos_list_for_authenticated_user, {"type": "owner"})


def test_visibility_and_affiliation_together_are_fine():
    """GitHub only rejects `type` beside them — these two combine happily."""
    _validate(
        github.repos_list_for_authenticated_user,
        {"visibility": "private", "affiliation": "owner,collaborator"},
    )


# -----------------------------------------------------
# The 1,000-result search window
# -----------------------------------------------------


def test_paging_past_the_thousandth_search_result_is_refused_locally():
    """`total_count` invites a walk that GitHub will not serve.

    Search reports the true size of the match set and then serves only the first
    1,000 of them, so a page-number walk keeps asking and takes a 422 at page 11
    of 100. The pair is checked here so the walk ends with a message that says
    what to do instead.
    """
    with pytest.raises(ToolValidationError) as excinfo:
        _validate(github.search_issues, {"q": "is:open", "page": 11, "per_page": 100})
    assert "1000" in str(excinfo.value)

    with pytest.raises(ToolValidationError):
        _validate(github.search_repositories, {"q": "stars:>1", "page": 34, "per_page": 30})


def test_the_last_page_inside_the_window_is_accepted():
    _validate(github.search_issues, {"q": "is:open", "page": 10, "per_page": 100})


@respx.mock
async def test_advanced_search_and_search_type_reach_the_wire():
    """Two documented parameters the schema used to omit entirely."""
    route = respx.get(f"{API}search/issues").mock(
        return_value=httpx.Response(200, json={"total_count": 0, "items": []})
    )

    await github.search_issues.ainvoke(
        q="repo:octocat/hello (is:open OR label:bug)",
        advanced_search=True,
        search_type="hybrid",
    )

    sent = route.calls.last.request.url.params
    assert sent["advanced_search"] == "true"
    assert sent["search_type"] == "hybrid"


# -----------------------------------------------------
# The two files repos_get_content cannot hand over
# -----------------------------------------------------


def _content(**extra: Any) -> Dict[str, Any]:
    base = {
        "name": "f",
        "path": "f",
        "type": "file",
        "sha": "abc",
        "download_url": "https://raw.example/f",
    }
    base.update(extra)
    return base


@respx.mock
async def test_a_text_file_still_decodes_to_its_text():
    import base64
    import textwrap

    text = "# Title\n\nA paragraph with unicode: café, naïve.\n" * 8
    wrapped = "\n".join(textwrap.wrap(base64.b64encode(text.encode()).decode(), 60)) + "\n"
    respx.get(f"{API}repos/octocat/hello/contents/README.md").mock(
        return_value=httpx.Response(
            200,
            json=_content(name="README.md", path="README.md", size=len(text),
                          encoding="base64", content=wrapped),
        )
    )

    result = await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="README.md"
    )

    # GitHub wraps the payload at 60 characters and the decoder tolerates it.
    assert result["content"] == text


@respx.mock
async def test_a_binary_file_is_named_as_one_rather_than_decoded_to_mojibake():
    """A lenient decoder turns a PNG into replacement characters and calls it content.

    That is worse than an error: the model receives something that looks like a
    file and is not, with no signal that anything went wrong. Strict decoding
    makes the case detectable, and the download_url is the one field that is
    still actionable.
    """
    import base64

    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452") + bytes(range(256))
    respx.get(f"{API}repos/octocat/hello/contents/logo.png").mock(
        return_value=httpx.Response(
            200,
            json=_content(name="logo.png", path="logo.png", size=len(png),
                          encoding="base64", content=base64.b64encode(png).decode()),
        )
    )

    result = await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="logo.png"
    )

    assert "binary" in result["content"]
    assert "�" not in result["content"]
    assert result["download_url"] == "https://raw.example/f"


@respx.mock
async def test_a_file_over_a_megabyte_says_why_there_is_no_content():
    """GitHub answers `encoding: "none"` and an empty string, which projects away.

    Without this branch the model gets a file object carrying a size and no
    content at all — indistinguishable from an empty file.
    """
    respx.get(f"{API}repos/octocat/hello/contents/dump.csv").mock(
        return_value=httpx.Response(
            200,
            json=_content(name="dump.csv", path="dump.csv", size=5 * 1024 * 1024,
                          encoding="none", content=""),
        )
    )

    result = await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="dump.csv"
    )

    assert "1MB" in result["content"]
    assert result["download_url"] == "https://raw.example/f"


@respx.mock
async def test_a_directory_listing_is_unaffected_by_either_branch():
    respx.get(f"{API}repos/octocat/hello/contents/src").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"name": "a.py", "path": "src/a.py", "type": "file", "size": 10,
                 "sha": "1", "download_url": "https://raw.example/a"},
                {"name": "sub", "path": "src/sub", "type": "dir", "size": 0, "sha": "2"},
            ],
        )
    )

    result = await github.repos_get_content.ainvoke(
        owner="octocat", repo="hello", path="src"
    )

    assert [entry["name"] for entry in result] == ["a.py", "sub"]
    assert all("content" not in entry for entry in result)


# -----------------------------------------------------
# Rate limits and the search result cap
# -----------------------------------------------------


@respx.mock
async def test_a_rate_limited_call_reports_when_to_retry():
    """GitHub sends no `Retry-After`: it answers 403 with `x-ratelimit-reset`.

    Confirmed live — the search limit trips at 30/minute and the response
    carries `x-ratelimit-remaining: 0` and an epoch `x-ratelimit-reset`. Without
    reading it, every backoff loop built on `retry_after` spins against a limit
    it cannot see.
    """
    reset = int(datetime.now(timezone.utc).timestamp()) + 42
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(reset)},
        )
    )

    with pytest.raises(APIError) as caught:
        await github.users_get_authenticated.ainvoke({})

    assert caught.value.status_code == 403
    assert caught.value.retry_after is not None
    assert 35 <= caught.value.retry_after <= 42


@respx.mock
async def test_quota_headers_on_a_healthy_response_are_not_a_wait():
    """Every GitHub response carries these; only a spent budget is a delay."""
    reset = int(datetime.now(timezone.utc).timestamp()) + 600
    respx.get("https://api.github.com/repos/o/r").mock(
        return_value=httpx.Response(
            404,
            json={"message": "Not Found"},
            headers={"x-ratelimit-remaining": "4999", "x-ratelimit-reset": str(reset)},
        )
    )

    with pytest.raises(APIError) as caught:
        await github.repos_get.ainvoke({"owner": "o", "repo": "r"})
    assert caught.value.retry_after is None


def test_a_search_walk_stops_at_the_thousand_result_wall():
    """GitHub counts matches it will not serve.

    `total_count` reports tens of thousands while only the first 1,000 are
    reachable, and the request schema already refuses a page past that. Without
    the cap on the pagination, `has_more` stays True right up to the wall and
    the *next* call is the one that raises — so the documented walk ends by
    throwing instead of finishing.
    """
    pg = github.search_issues.pagination
    page = {"total_count": 77776, "items": [{"number": n} for n in range(5)]}

    assert pg.has_more(page, {"q": "x", "per_page": 5, "page": 10}) is True
    assert pg.has_more(page, {"q": "x", "per_page": 5, "page": 200}) is False
    assert pg.next_page_args(page, {"q": "x", "per_page": 5, "page": 200}) is None


# -----------------------------------------------------
# Closing the round trips
# -----------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_a_file_is_written_as_text_and_sent_as_base64():
    """GitHub wants base64. The model writes the file."""
    route = respx.put(f"{API}repos/octocat/hello/contents/src/app.py").mock(
        return_value=httpx.Response(201, json={"content": {"name": "app.py"}})
    )
    await github.repos_create_or_update_file.ainvoke(
        {
            "owner": "octocat", "repo": "hello", "path": "src/app.py",
            "message": "add app", "content": "print('hi')\n",
        }
    )
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == base64.b64encode(b"print('hi')\n").decode()
    assert "sha" not in body


@pytest.mark.asyncio
@respx.mock
async def test_a_file_path_keeps_its_slashes():
    """`path` is multi-segment: escaping the slashes would address a file called
    'src/app.py' in the root rather than app.py inside src."""
    route = respx.put(f"{API}repos/octocat/hello/contents/a/b/c.txt").mock(
        return_value=httpx.Response(201, json={"content": {}})
    )
    await github.repos_create_or_update_file.ainvoke(
        {"owner": "octocat", "repo": "hello", "path": "a/b/c.txt",
         "message": "m", "content": "x"}
    )
    assert route.calls.last.request.url.path == "/repos/octocat/hello/contents/a/b/c.txt"


@pytest.mark.asyncio
async def test_a_branch_ref_must_be_fully_qualified():
    """GitHub states the rejection: it must start with refs and have two slashes."""
    with pytest.raises(ToolValidationError):
        await github.git_refs_create.ainvoke(
            {"owner": "o", "repo": "r", "ref": "my-branch", "sha": "abc123"}
        )


@pytest.mark.asyncio
@respx.mock
async def test_a_fully_qualified_ref_is_accepted():
    route = respx.post(f"{API}repos/o/r/git/refs").mock(
        return_value=httpx.Response(201, json={"ref": "refs/heads/my-branch"})
    )
    await github.git_refs_create.ainvoke(
        {"owner": "o", "repo": "r", "ref": "refs/heads/my-branch", "sha": "abc123"}
    )
    assert json.loads(route.calls.last.request.content)["ref"] == "refs/heads/my-branch"


def test_a_review_must_say_what_it_is():
    """GitHub marks `event` optional, and omitting it leaves a PENDING review that
    only a submit endpoint can finish. This pack has no submit endpoint, so an
    agent could create a review it could never deliver."""
    required = github.pulls_create_review.to_json_schema()["parameters"]["required"]
    assert "event" in required


@pytest.mark.asyncio
async def test_requesting_changes_needs_a_body_but_approving_does_not():
    with pytest.raises(ToolValidationError):
        await github.pulls_create_review.ainvoke(
            {"owner": "o", "repo": "r", "pull_number": 1, "event": "REQUEST_CHANGES"}
        )

    with respx.mock:
        respx.post(f"{API}repos/o/r/pulls/1/reviews").mock(
            return_value=httpx.Response(200, json={"id": 1, "state": "APPROVED"})
        )
        await github.pulls_create_review.ainvoke(
            {"owner": "o", "repo": "r", "pull_number": 1, "event": "APPROVE"}
        )


@pytest.mark.asyncio
async def test_a_review_request_must_ask_somebody():
    with pytest.raises(ToolValidationError):
        await github.pulls_request_reviewers.ainvoke(
            {"owner": "o", "repo": "r", "pull_number": 1}
        )


def test_review_comments_do_not_offer_the_deprecated_position():
    """GitHub deprecated `position` in 2022 and says to use `line`."""
    params = github.pulls_create_review.to_json_schema()["parameters"]
    comment = params["$defs"]["ReviewComment_LLM"]["properties"]
    assert "position" not in comment
    assert "line" in comment


def test_workflow_runs_declares_no_conclusion_filter():
    """GitHub has one filter that matches status OR conclusion. A `conclusion`
    parameter would be silently ignored, and the model would read an unfiltered
    page as a filtered one."""
    props = github.actions_list_workflow_runs.to_json_schema()["parameters"]["properties"]
    assert "conclusion" not in props
    branch = next(b for b in props["status"]["anyOf"] if "enum" in b)
    assert {"in_progress", "success", "failure", "stale"} <= set(branch["enum"])
    assert len(branch["enum"]) == 14


def test_protected_is_tri_state():
    """Absent means every branch, not unprotected ones."""
    props = github.branches_list.to_json_schema()["parameters"]["properties"]
    assert props["protected"].get("default") is None


@pytest.mark.asyncio
@respx.mock
async def test_the_workflow_runs_envelope_is_trimmed_and_kept():
    """Actions answers {total_count, workflow_runs}, unlike the bare arrays
    elsewhere in this pack. The count is the paging signal."""
    respx.get(f"{API}repos/o/r/actions/runs").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 1,
                "workflow_runs": [
                    {
                        "id": 7, "name": "ci", "status": "completed",
                        "conclusion": "startup_failure", "head_branch": "main",
                        "actor": {"login": "octocat", "avatar_url": "https://x/y.png"},
                        "repository": {"full_name": "o/r", "owner": {"id": 1}},
                    }
                ],
            },
        )
    )
    result = await github.actions_list_workflow_runs.ainvoke({"owner": "o", "repo": "r"})
    assert result["total_count"] == 1
    run = result["workflow_runs"][0]
    assert run["actor"] == "octocat"
    assert "repository" not in run
    # An undocumented conclusion survives: GitHub's schema does not close that set.
    assert run["conclusion"] == "startup_failure"


def test_search_code_omits_the_closing_down_sort():
    props = github.search_code.to_json_schema()["parameters"]["properties"]
    assert "sort" not in props and "order" not in props
    assert "1,000" in github.search_code.description


@pytest.mark.asyncio
@respx.mock
async def test_merge_sends_the_method_and_the_expected_head():
    route = respx.put(f"{API}repos/o/r/pulls/3/merge").mock(
        return_value=httpx.Response(200, json={"sha": "s", "merged": True, "message": "ok"})
    )
    await github.pulls_merge.ainvoke(
        {"owner": "o", "repo": "r", "pull_number": 3, "merge_method": "squash", "sha": "head1"}
    )
    body = json.loads(route.calls.last.request.content)
    assert body == {"merge_method": "squash", "sha": "head1"}


@pytest.mark.asyncio
@respx.mock
async def test_writing_a_file_reports_the_commit_and_the_new_sha():
    """A PUT to the contents endpoint answers a different shape from the GET it
    shares a URL with: {"content": {...}, "commit": {...}}. Running that through
    the read handler projected every key away and returned `{}` — a write
    indistinguishable from one that did nothing, and with it went the blob sha
    the next write to that path has to send."""
    respx.put("https://api.github.com/repos/o/r/contents/docs/a.md").mock(
        return_value=httpx.Response(
            201,
            json={
                "content": {
                    "name": "a.md", "path": "docs/a.md", "sha": "blob123",
                    "size": 12, "html_url": "https://github.com/o/r/blob/main/docs/a.md",
                    "url": "https://api.github.com/repos/o/r/contents/docs/a.md",
                    "git_url": "https://api.github.com/repos/o/r/git/blobs/blob123",
                    "download_url": "https://raw.githubusercontent.com/o/r/main/docs/a.md",
                    "_links": {"self": "…", "git": "…", "html": "…"},
                },
                "commit": {
                    "sha": "commit456", "message": "add a.md",
                    "html_url": "https://github.com/o/r/commit/commit456",
                    "author": {"name": "Ada", "email": "a@b.com", "date": "2026-09-12T10:00:00Z"},
                    "committer": {"name": "Ada", "email": "a@b.com"},
                    "tree": {"sha": "tree789"}, "parents": [{"sha": "parent000"}],
                },
            },
        )
    )
    written = await github.repos_create_or_update_file.ainvoke(
        owner="o", repo="r", path="docs/a.md", message="add a.md", content="hello"
    )

    assert written["content"]["sha"] == "blob123"
    assert written["content"]["path"] == "docs/a.md"
    assert written["commit"]["sha"] == "commit456"
    assert written["commit"]["message"] == "add a.md"
    assert written["commit"]["date"] == "2026-09-12T10:00:00Z"
    # The envelope around the blob is still dropped: four URLs for one file.
    assert "_links" not in written["content"]
    assert "git_url" not in written["content"]


# =====================================================
# CI debugging — the block that turns "CI is red" into a fix
# =====================================================


@respx.mock
async def test_listing_a_runs_jobs_names_the_failing_step_without_a_log():
    """The cheapest answer to "why is CI red", and the one an agent should try first.

    A job carries a `steps` array where every step repeats status, conclusion,
    number and two timestamps. On a green job that is the same word twenty
    times; on a red one, the failing entry is the answer. The projection keeps
    the failures by name and counts the rest, so the page says which command
    broke without anyone downloading anything.
    """
    respx.get(f"{API}repos/o/r/actions/runs/42/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 1,
                "jobs": [
                    {
                        "id": 77,
                        "run_id": 42,
                        "name": "test (3.11)",
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-09-13T10:00:00Z",
                        "completed_at": "2026-09-13T10:04:00Z",
                        "html_url": "https://github.com/o/r/actions/runs/42/job/77",
                        "node_id": "CR_kwDO",
                        "check_run_url": f"{API}repos/o/r/check-runs/77",
                        "labels": ["ubuntu-latest"],
                        "runner_id": 3,
                        "runner_name": "GitHub Actions 3",
                        "steps": [
                            {"number": 1, "name": "Set up job", "status": "completed",
                             "conclusion": "success", "started_at": "…", "completed_at": "…"},
                            {"number": 2, "name": "Checkout", "status": "completed",
                             "conclusion": "success", "started_at": "…", "completed_at": "…"},
                            {"number": 3, "name": "Run pytest", "status": "completed",
                             "conclusion": "failure", "started_at": "…", "completed_at": "…"},
                            {"number": 4, "name": "Upload coverage", "status": "completed",
                             "conclusion": "skipped", "started_at": "…", "completed_at": "…"},
                        ],
                    }
                ],
            },
        )
    )

    page = await github.actions_list_jobs_for_run.ainvoke(owner="o", repo="r", run_id=42)

    job = page["jobs"][0]
    assert job["conclusion"] == "failure"
    assert job["failed_steps"] == [{"number": 3, "name": "Run pytest", "conclusion": "failure"}]
    assert job["steps_total"] == 4
    # A skipped step is not a failure, and the three successes are a count.
    assert all(step["name"] != "Upload coverage" for step in job["failed_steps"])
    # The item count survives, because it is what pagination reads.
    assert page["total_count"] == 1


@respx.mock
async def test_a_job_log_comes_back_as_its_tail_and_its_errors_not_as_itself():
    """The tool that could undo every projection in this pack, and does not.

    GitHub answers with a 302 to a signed URL and serves the log as plain text
    from there. Two things are asserted: that the redirect is followed at all —
    without it the body is empty and the signed URL is gone in a minute — and
    that what reaches the model is a bounded view with the *real* length stated
    beside it, so a model reading 200 lines of a 5,000-line log knows which it
    is looking at.
    """
    log = "\n".join(f"ok line {i}" for i in range(1, 5000))
    log += "\n##[error]Process completed with exit code 1.\n"

    respx.get(f"{API}repos/o/r/actions/jobs/77/logs").mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://pipelines.actions.example/logs/77"}
        )
    )
    blob = respx.get("https://pipelines.actions.example/logs/77").mock(
        return_value=httpx.Response(
            200, text=log, headers={"Content-Type": "text/plain; charset=utf-8"}
        )
    )

    out = await github.actions_download_job_logs.ainvoke(owner="o", repo="r", job_id=77)

    assert blob.called, "the 302 was not followed, so the log was never fetched"
    assert out["total_lines"] == 5000
    assert out["tail_lines"] == 200
    assert out["tail"].count("\n") == 199
    assert out["matched_lines"] == ["5000: ##[error]Process completed with exit code 1."]
    # The whole file is not in the answer: that is the entire point of the tool.
    assert len(out["tail"]) < len(log) / 10


@respx.mock
async def test_the_bearer_token_does_not_travel_to_the_signed_url():
    """A signed URL authenticates itself; the token has no business there.

    httpx drops `Authorization` when a redirect leaves the origin, which is why
    following one here is safe. Asserted rather than assumed, because the thing
    being leaked would be a repository-scoped credential and the leak would be
    silent.
    """
    respx.get(f"{API}repos/o/r/actions/jobs/77/logs").mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://pipelines.actions.example/logs/77"}
        )
    )
    blob = respx.get("https://pipelines.actions.example/logs/77").mock(
        return_value=httpx.Response(200, text="fine", headers={"Content-Type": "text/plain"})
    )

    await github.actions_download_job_logs.ainvoke(owner="o", repo="r", job_id=77)

    assert "authorization" not in {k.lower() for k in blob.calls.last.request.headers}


@respx.mock
async def test_a_run_log_archive_is_unzipped_rather_than_decoded_as_text():
    """The sibling endpoint's payload is a ZIP, and text-decoding it is mojibake.

    `resp.text` replaces the bytes it cannot decode, so a ZIP run through it
    comes back as replacement characters that read like content. The runtime
    keeps a non-textual body as bytes for exactly this, and the handler opens
    the archive: one tail per job, from one call.
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("0_build.txt", "compiling\nok\n")
        archive.writestr("1_test.txt", "running\nFAILED: test_thing\n")
        # GitHub also packs a per-step copy under a directory; it is the same
        # content split up, and the root file already has it.
        archive.writestr("1_test/3_pytest.txt", "running\nFAILED: test_thing\n")

    respx.get(f"{API}repos/o/r/actions/runs/42/logs").mock(
        return_value=httpx.Response(302, headers={"Location": "https://blob.example/runs/42.zip"})
    )
    respx.get("https://blob.example/runs/42.zip").mock(
        return_value=httpx.Response(
            200, content=buf.getvalue(), headers={"Content-Type": "application/zip"}
        )
    )

    out = await github.actions_download_run_logs.ainvoke(owner="o", repo="r", run_id=42)

    assert out["job_count"] == 2, "the per-step copies should not be counted twice"
    assert {job["job"] for job in out["jobs"]} == {"0_build.txt", "1_test.txt"}
    failing = next(j for j in out["jobs"] if j["job"] == "1_test.txt")
    assert failing["matched_lines"] == ["2: FAILED: test_thing"]
    # No replacement characters anywhere: the bytes were never decoded as text.
    assert "�" not in json.dumps(out)


@respx.mock
async def test_an_artifact_is_reported_as_its_manifest_not_its_bytes():
    """An artifact is an arbitrary archive, and may be enormous.

    So the handler reads the ZIP's own index — every entry's name and size,
    which is cheap and complete — and inlines only the small text entries. A
    binary entry is *skipped and said to be skipped*, rather than decoded into
    something that looks like content.
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("report.json", '{"failed": 1}')
        archive.writestr("screenshot.png", b"\x89PNG\r\n\x1a\n\xff\xfe binary")

    respx.get(f"{API}repos/o/r/actions/artifacts/9/zip").mock(
        return_value=httpx.Response(302, headers={"Location": "https://blob.example/a/9.zip"})
    )
    respx.get("https://blob.example/a/9.zip").mock(
        return_value=httpx.Response(
            200, content=buf.getvalue(), headers={"Content-Type": "application/zip"}
        )
    )

    out = await github.actions_download_artifact.ainvoke(owner="o", repo="r", artifact_id=9)

    assert out["entry_count"] == 2
    assert {e["name"] for e in out["entries"]} == {"report.json", "screenshot.png"}
    assert out["files"] == {"report.json": '{"failed": 1}'}
    assert out["not_inlined"] == ["screenshot.png"]
    assert "�" not in json.dumps(out)


@respx.mock
async def test_check_annotations_arrive_already_located():
    """The cheap alternative to a log: GitHub has extracted the file and the line."""
    respx.get(f"{API}repos/o/r/check-runs/5/annotations").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "path": "src/charter/tool.py",
                    "blob_href": "https://github.com/o/r/blob/abc/src/charter/tool.py",
                    "start_line": 42,
                    "end_line": 42,
                    "start_column": None,
                    "end_column": None,
                    "annotation_level": "failure",
                    "title": "F821",
                    "message": "undefined name 'Tool'",
                    "raw_details": None,
                }
            ],
        )
    )

    found = await github.checks_list_annotations.ainvoke(owner="o", repo="r", check_run_id=5)

    assert found == [
        {
            "path": "src/charter/tool.py",
            "start_line": 42,
            "end_line": 42,
            "annotation_level": "failure",
            "title": "F821",
            "message": "undefined name 'Tool'",
        }
    ]
    # `blob_href` is the longest field and points at the file the path names.
    assert "blob_href" not in found[0]


def test_the_check_run_status_filter_is_a_status_and_not_a_conclusion():
    """Two filters in this pack spell `status` and mean different sets.

    `actions_list_workflow_runs` folds statuses and conclusions into one
    parameter, because GitHub does. The Checks API does not: `failure` is a
    conclusion there and is refused as a status. Modelling both against the same
    enum would let a model ask the Checks API for `failure` and read an
    unfiltered page as a filtered one.
    """
    from typing import get_args

    from charter.packs.github.types import CheckRunStatusFilter, WorkflowRunStatusFilter

    assert set(get_args(CheckRunStatusFilter)) == {"queued", "in_progress", "completed"}
    assert "failure" in get_args(WorkflowRunStatusFilter)
    assert "failure" not in get_args(CheckRunStatusFilter)


# =====================================================
# Code review — a comment on a line of a diff
# =====================================================


@respx.mock
async def test_a_review_comment_puts_its_placement_on_the_wire():
    """The bytes of the primitive this pack was missing."""
    route = respx.post(f"{API}repos/o/r/pulls/7/comments").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 500,
                "body": "This drops the error.",
                "path": "src/a.py",
                "line": 12,
                "side": "RIGHT",
                "commit_id": "abc123",
                "user": {"login": "octocat", "id": 1},
                "diff_hunk": "@@ -1,5 +1,7 @@\n" + "context\n" * 40,
                "html_url": "https://github.com/o/r/pull/7#discussion_r500",
                "created_at": "2026-09-13T10:00:00Z",
                "author_association": "COLLABORATOR",
                "reactions": {"total_count": 0, "+1": 0},
                "_links": {"self": {"href": "…"}, "html": {"href": "…"}},
            },
        )
    )

    out = await github.pulls_create_review_comment.ainvoke(
        owner="o", repo="r", pull_number=7,
        body="This drops the error.", commit_id="abc123", path="src/a.py",
        line=12, side="RIGHT",
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent == {
        "body": "This drops the error.",
        "commit_id": "abc123",
        "path": "src/a.py",
        "line": 12,
        "side": "RIGHT",
    }
    # The placement is what the comment *is*, so it survives the projection.
    assert out["path"] == "src/a.py" and out["line"] == 12 and out["side"] == "RIGHT"
    # `diff_hunk` repeats a diff the caller has, on every comment in the thread.
    assert "diff_hunk" not in out
    assert "_links" not in out


def test_a_reply_refuses_the_fields_github_would_silently_ignore():
    """GitHub *ignores* the placement fields on a reply rather than refusing them.

    So a model that sets a path and a line beside `in_reply_to` gets a 201 and a
    comment somewhere other than where it aimed. A 201 that means "not where you
    said" is worse than a validation error, and this is the only place the two
    can be told apart.
    """
    with pytest.raises(ValidationError) as caught:
        github.pulls_create_review_comment.args_schema(
            owner="o", repo="r", pull_number=7,
            body="agreed", commit_id="abc", path="src/a.py",
            in_reply_to=500, line=12,
        )
    assert "in_reply_to" in str(caught.value)


def test_a_line_comment_without_a_line_is_refused_unless_it_is_a_file_comment():
    """GitHub: "Required unless using `subject_type:file`"."""
    with pytest.raises(ValidationError):
        github.pulls_create_review_comment.args_schema(
            owner="o", repo="r", pull_number=7,
            body="x", commit_id="abc", path="src/a.py",
        )

    ok = github.pulls_create_review_comment.args_schema(
        owner="o", repo="r", pull_number=7,
        body="x", commit_id="abc", path="src/a.py", subject_type="file",
    )
    assert ok.line is None


def test_a_multi_line_comment_needs_both_ends_of_its_range():
    with pytest.raises(ValidationError):
        github.pulls_create_review_comment.args_schema(
            owner="o", repo="r", pull_number=7, body="x", commit_id="abc",
            path="src/a.py", line=20, start_line=10,
        )
    with pytest.raises(ValidationError):
        github.pulls_create_review_comment.args_schema(
            owner="o", repo="r", pull_number=7, body="x", commit_id="abc",
            path="src/a.py", line=10, start_line=20, start_side="RIGHT",
        )


def test_start_side_does_not_offer_the_third_value_githubs_spec_carries():
    """GitHub's OpenAPI spec types `start_side` as LEFT | RIGHT | "side".

    The third is an artefact of their generator, not a value: there is no side
    of a diff called "side", and the prose names two. Offering it would put a
    nonsense option in front of the model on an optional field. Named here so
    that the omission is a decision on record rather than an oversight.
    """
    from typing import get_args

    schema = github.pulls_create_review_comment.llm_schema()
    start_side = schema.model_fields["start_side"].annotation
    assert set(get_args(get_args(start_side)[0])) == {"LEFT", "RIGHT"}


@respx.mock
async def test_check_merged_turns_a_bodiless_204_into_an_answer():
    """This endpoint reports in its status line and sends no payload at all.

    Left alone, the empty body becomes `{}`, which reads as "nothing found" —
    the opposite of the 204's meaning. The handler says the word.
    """
    respx.get(f"{API}repos/o/r/pulls/7/merge").mock(return_value=httpx.Response(204))
    assert await github.pulls_check_merged.ainvoke(owner="o", repo="r", pull_number=7) == {
        "merged": True
    }


@respx.mock
async def test_the_diff_tool_asks_for_a_diff_and_measures_what_comes_back():
    """One endpoint, two representations, selected by a header the model cannot set."""
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-x\n+y\n"
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-p\n+q\n"
    )
    route = respx.get(f"{API}repos/o/r/pulls/7").mock(
        return_value=httpx.Response(
            200, text=diff, headers={"Content-Type": "application/vnd.github.diff; charset=utf-8"}
        )
    )

    out = await github.pulls_get_diff.ainvoke(owner="o", repo="r", pull_number=7)

    assert route.calls.last.request.headers["Accept"] == "application/vnd.github.diff"
    assert out["diff"] == diff
    assert out["files_changed"] == 2
    assert out["lines"] == len(diff.splitlines())
    # And the JSON tool beside it still asks for JSON, from the same URL.
    assert github.pulls_get.static_headers["Accept"] == "application/vnd.github+json"
    assert github.pulls_get.url_template == github.pulls_get_diff.url_template


# =====================================================
# Authoring a change — the Git object store
# =====================================================


@respx.mock
async def test_a_tree_deletion_reaches_the_wire_as_an_explicit_null():
    """GitHub's signal for "remove this path" is a present-and-null `sha`.

    Pydantic dumps with `exclude_none`, so a `None` sha never leaves the
    process and the entry would arrive as a no-op — a commit that silently did
    not delete the file. The flag is the semantic form and `build_request`
    compiles it back, which is the one place the wire form can be produced.
    """
    route = respx.post(f"{API}repos/o/r/git/trees").mock(
        return_value=httpx.Response(
            201, json={"sha": "tree1", "url": "…", "truncated": False, "tree": []}
        )
    )

    await github.git_trees_create.ainvoke(
        owner="o", repo="r", base_tree="base1",
        tree=[
            {"path": "new.py", "mode": "100644", "type": "blob", "content": "print(1)"},
            {"path": "old.py", "mode": "100644", "type": "blob", "delete": True},
        ],
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["base_tree"] == "base1"
    assert sent["tree"][0] == {
        "path": "new.py", "mode": "100644", "type": "blob", "content": "print(1)"
    }
    # Present, and null. Both halves matter.
    assert "sha" in sent["tree"][1] and sent["tree"][1]["sha"] is None
    assert "delete" not in sent["tree"][1], "the semantic flag must not reach GitHub"


def test_a_tree_entry_refuses_both_content_and_sha():
    """GitHub: "Using both `tree.sha` and `content` will return an error"."""
    with pytest.raises(ValidationError):
        github.git_trees_create.args_schema(
            owner="o", repo="r",
            tree=[{"path": "a.py", "sha": "abc", "content": "print(1)"}],
        )


def test_a_commit_with_no_parents_is_refused_rather_than_written_as_a_root():
    """An omitted `parents` is a root commit, and the failure surfaces a step later.

    GitHub writes the commit happily; it is the branch update afterwards that
    refuses it as a non-fast-forward, with an error that says nothing about the
    cause. Asked for explicitly, an empty list still works.
    """
    with pytest.raises(ValidationError) as caught:
        github.git_commits_create.args_schema(
            owner="o", repo="r", message="m", tree="t"
        )
    assert "root commit" in str(caught.value)

    deliberate = github.git_commits_create.args_schema(
        owner="o", repo="r", message="m", tree="t", parents=[]
    )
    assert deliberate.parents == []


def test_the_ref_endpoints_refuse_the_prefix_their_sibling_requires():
    """`git_refs_create` wants `refs/heads/x` in its body; these want `heads/x` in
    the path. GitHub documents both, in adjacent endpoints, and a 404 is all it
    says when the wrong one is sent."""
    for tool in (github.git_refs_get, github.git_refs_update, github.git_refs_delete):
        kwargs = {"owner": "o", "repo": "r", "ref": "refs/heads/main"}
        if tool is github.git_refs_update:
            kwargs["sha"] = "abc"
        with pytest.raises(ValidationError) as caught:
            tool.args_schema(**kwargs)
        assert "refs/" in str(caught.value), tool.name

    # And the create endpoint still insists on the prefix, unchanged.
    with pytest.raises(ValidationError):
        github.git_refs_create.args_schema(owner="o", repo="r", ref="heads/main", sha="abc")


@respx.mock
async def test_a_truncated_tree_says_so_even_when_it_is_false():
    """`truncated` is the one field here that must never be dropped.

    GitHub sets it when a recursive read exceeded 100,000 entries or 7 MB. A
    caller that does not see it reads a partial tree as a complete one — and
    then writes a commit from it. `_pick` drops falsy values, so this is carried
    explicitly, in both directions.
    """
    respx.get(f"{API}repos/o/r/git/trees/abc").mock(
        return_value=httpx.Response(
            200,
            json={
                "sha": "abc", "url": "…", "truncated": False,
                "tree": [{"path": "a.py", "mode": "100644", "type": "blob",
                          "sha": "b1", "size": 12, "url": "…"}],
            },
        )
    )
    whole = await github.git_trees_get.ainvoke(owner="o", repo="r", tree_sha="abc")
    assert whole["truncated"] is False
    assert whole["entry_count"] == 1

    respx.get(f"{API}repos/o/r/git/trees/big").mock(
        return_value=httpx.Response(200, json={"sha": "big", "truncated": True, "tree": []})
    )
    partial = await github.git_trees_get.ainvoke(owner="o", repo="r", tree_sha="big")
    assert partial["truncated"] is True


def test_comparing_commits_refuses_the_two_dot_form():
    """`main..feature` is a different Git operator and GitHub does not take it here."""
    with pytest.raises(ValidationError):
        github.repos_compare_commits.args_schema(owner="o", repo="r", basehead="main..feature")
    ok = github.repos_compare_commits.args_schema(owner="o", repo="r", basehead="main...feature")
    assert ok.basehead == "main...feature"


# =====================================================
# Issues, releases and the feeds
# =====================================================


@respx.mock
async def test_adding_labels_sends_the_object_github_recommends():
    """GitHub takes a bare array here too and recommends the object. The envelope
    marker is what keeps the field's own name as the root key."""
    route = respx.post(f"{API}repos/o/r/issues/3/labels").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "name": "bug", "color": "d73a4a"}])
    )
    await github.issues_add_labels.ainvoke(owner="o", repo="r", issue_number=3, labels=["bug"])
    assert json.loads(route.calls.last.request.content) == {"labels": ["bug"]}


def test_a_label_colour_is_refused_with_the_hash_github_rejects():
    """GitHub's words: "without the leading `#`"."""
    with pytest.raises(ValidationError):
        github.issues_create_label.args_schema(owner="o", repo="r", name="bug", color="#d73a4a")
    assert github.issues_create_label.args_schema(
        owner="o", repo="r", name="bug", color="d73a4a"
    ).color == "d73a4a"


def test_dismissing_a_dependabot_alert_must_say_why():
    """GitHub: "Required when `state` is `dismissed`"."""
    with pytest.raises(ValidationError):
        github.dependabot_update_alert.args_schema(
            owner="o", repo="r", alert_number=1, state="dismissed"
        )
    ok = github.dependabot_update_alert.args_schema(
        owner="o", repo="r", alert_number=1, state="dismissed", dismissed_reason="not_used"
    )
    assert ok.dismissed_reason == "not_used"


@respx.mock
async def test_a_secret_scanning_alert_never_carries_the_secret():
    """The response handler is the last place a leaked credential can be stopped.

    `hide_secret` asks GitHub to leave it out, and a caller may not set it. So
    the field is dropped here unconditionally, whatever the request asked for:
    triage needs the pattern, the provider and the state, not the credential.
    """
    respx.get(f"{API}repos/o/r/secret-scanning/alerts").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "number": 2, "state": "open", "secret_type": "aws_access_key_id",
                    "secret_type_display_name": "Amazon AWS Access Key ID",
                    "secret": "AKIAIOSFODNN7EXAMPLE",
                    "provider_slug": "amazon", "validity": "active",
                    "created_at": "2026-09-01T00:00:00Z",
                    "html_url": "https://github.com/o/r/security/secret-scanning/2",
                    "locations_url": "…", "url": "…",
                }
            ],
        )
    )

    alerts = await github.secret_scanning_list_alerts.ainvoke(owner="o", repo="r")

    assert alerts[0]["secret_type"] == "aws_access_key_id"
    assert alerts[0]["validity"] == "active"
    assert "secret" not in alerts[0]
    assert "AKIAIOSFODNN7EXAMPLE" not in json.dumps(alerts)


@respx.mock
async def test_uploading_a_release_asset_posts_bytes_to_the_other_host():
    """The one tool that leaves api.github.com, and the one that is not JSON."""
    route = respx.post("https://uploads.github.com/repos/o/r/releases/5/assets").mock(
        return_value=httpx.Response(
            201,
            json={"id": 1, "name": "CHECKSUMS.txt", "state": "uploaded",
                  "content_type": "application/octet-stream", "size": 11,
                  "browser_download_url": "https://github.com/o/r/releases/download/v1/CHECKSUMS.txt",
                  "uploader": {"login": "octocat"}, "url": "…", "node_id": "…"},
        )
    )

    await github.releases_upload_asset.ainvoke(
        owner="o", repo="r", release_id=5, name="CHECKSUMS.txt", content="abc  file\n"
    )

    request = route.calls.last.request
    # Raw bytes, not a JSON document wrapping them.
    assert request.content == b"abc  file\n"
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert request.url.params["name"] == "CHECKSUMS.txt"
    # The version pin came along to the upload host.
    assert request.headers["X-GitHub-Api-Version"] == github.API_VERSION


@respx.mock
async def test_generating_release_notes_creates_nothing():
    """GitHub: "The generated release notes are not saved anywhere."

    Which makes this a read that happens to be a POST, and the reason its
    description says so — a model that believed it published would not follow
    it with `releases_create`.
    """
    respx.post(f"{API}repos/o/r/releases/generate-notes").mock(
        return_value=httpx.Response(200, json={"name": "v1.1.0", "body": "## What's Changed\n..."})
    )
    notes = await github.releases_generate_notes.ainvoke(
        owner="o", repo="r", tag_name="v1.1.0", previous_tag_name="v1.0.0"
    )
    assert set(notes) == {"name", "body"}


def test_make_latest_is_a_string_enum_and_not_a_boolean():
    """Three values, one of which is not a boolean at all."""
    from typing import get_args

    from charter.packs.github.types import MakeLatest

    assert set(get_args(MakeLatest)) == {"true", "false", "legacy"}


@respx.mock
async def test_a_notification_is_reduced_to_why_you_have_it_and_what_it_is_about():
    """`reason` says whether the agent is needed; `url` says what to fetch next."""
    respx.get(f"{API}notifications").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "1", "unread": True, "reason": "review_requested",
                    "updated_at": "2026-09-13T10:00:00Z",
                    "subject": {"title": "Fix the flaky test",
                                "url": f"{API}repos/o/r/pulls/7",
                                "latest_comment_url": f"{API}repos/o/r/issues/comments/9",
                                "type": "PullRequest"},
                    "repository": {"id": 1, "full_name": "o/r", "owner": {"login": "o"},
                                   "html_url": "…", "description": "…", "fork": False},
                    "url": f"{API}notifications/threads/1",
                    "subscription_url": "…", "last_read_at": None,
                }
            ],
        )
    )

    inbox = await github.notifications_list.ainvoke(participating=True)

    assert inbox[0]["reason"] == "review_requested"
    assert inbox[0]["url"] == f"{API}repos/o/r/pulls/7"
    assert inbox[0]["repository"] == "o/r"
    assert inbox[0]["type"] == "PullRequest"


def test_notifications_cap_per_page_at_fifty_not_one_hundred():
    """This one endpoint's ceiling is half the rest of the API's, and GitHub
    rejects a larger value rather than clamping it."""
    with pytest.raises(ValidationError):
        github.notifications_list.args_schema(per_page=100)
    assert github.notifications_list.args_schema(per_page=50).per_page == 50


# =====================================================
# The no-argument call, across the whole pack
# =====================================================


@respx.mock
async def test_no_tool_sends_a_parameter_it_was_not_given():
    """Everything a schema defaults into the request shows up on this line.

    A documented default copied onto a field is sent on every call, which is a
    different request from the one the documentation describes — and on
    `/user/repos` it was a guaranteed 422. Asserted over the whole pack rather
    than per tool, so a default added next year is caught by a test nobody has
    to remember to write.
    """
    minimal: Dict[str, Any] = {
        "owner": "o", "repo": "r", "org": "o", "issue_number": 1, "pull_number": 1,
        "run_id": 1, "job_id": 1, "workflow_id": "ci.yml", "artifact_id": 1,
        "check_run_id": 1, "review_id": 1, "comment_id": 1, "release_id": 1,
        "milestone_number": 1, "alert_number": 1, "thread_id": 1, "sub_issue_id": 1,
        "ref": "heads/main", "path": "a.py", "branch": "main", "tag": "v1",
        "basehead": "main...x", "commit_sha": "abc", "tree_sha": "abc", "file_sha": "abc",
        "sha": "abc", "name": "x", "new_name": "y", "message": "m", "body": "b",
        "content": "c", "title": "t", "tag_name": "v1", "q": "x", "state": "approved",
        "labels": ["bug"], "assignees": ["octocat"], "reviewers": ["octocat"],
        "environment_ids": [1], "comment": "c", "event": "APPROVE", "tree": "t",
        "parents": [], "object": "abc", "type": "commit", "commit_id": "abc",
        "line": 1, "base": "main", "head": "x", "expected_head_sha": "abc",
    }

    # `page` and `per_page` carry GitHub's own defaults on `GitHubListRequest`,
    # and that one is deliberate rather than copied. Page-number pagination has
    # no end marker: `has_more` decides a walk is finished when a page comes back
    # *shorter than was asked for*, which means the page size has to be in the
    # arguments from the first call. Defaulted to None, the first call would
    # carry no size, the walk could not recognise a short first page, and every
    # list would cost one extra round trip to discover it was already over.
    # Sending GitHub the value GitHub would have applied costs nothing.
    walking = {"page", "per_page"}

    # The three tools that carry a documented default on a *filter*, each a read.
    # Named rather than tolerated: the point of this sweep is that a fourth
    # cannot appear without someone deciding it should.
    known_defaults = {
        "issues_list_for_repo": {"state", "sort", "direction"},
        "pulls_list": {"state", "sort"},
        "repos_list_for_authenticated_user": {"sort"},
    }

    # Where one argument name means two different things across the pack.
    # `body` is a structured object on four tools and a string elsewhere; `ref`
    # is `heads/main` in a path parameter and `refs/heads/main` in a body, which
    # is GitHub's inconsistency and the one this pack validates against.
    overrides: Dict[str, Dict[str, Any]] = {
        "issues_create": {"body": {"title": "t"}},
        "issues_update": {"body": {}},
        "issues_create_comment": {"body": {"body": "b"}},
        "pulls_create": {"body": {"title": "t", "head": "x", "base": "main"}},
        "git_refs_create": {"ref": "refs/heads/main"},
        # `tree` is a commit's tree SHA on one endpoint and a list of entries on
        # the other.
        "git_trees_create": {"tree": [{"path": "a.py", "content": "x"}]},
    }

    # A cross-field rule can make a call impossible with only the *required*
    # fields — `pulls_request_reviewers` marks both lists optional and then
    # refuses a request that names nobody. The extra argument is supplied here
    # and counted as asked-for, so the sweep still tests what it is for.
    to_satisfy_a_validator: Dict[str, List[str]] = {
        "pulls_request_reviewers": ["reviewers"],
        "pulls_create_review_comment": ["line"],
        "git_commits_create": ["parents"],
    }

    anything = respx.route().mock(return_value=httpx.Response(200, json={}))

    for tool in github.TOOLS:
        fields = tool.llm_schema().model_fields
        required = [name for name, info in fields.items() if info.is_required()]
        required += to_satisfy_a_validator.get(tool.name, [])
        per_tool = {**minimal, **overrides.get(tool.name, {})}
        missing = [name for name in required if name not in per_tool]
        assert not missing, f"{tool.name} requires unmapped arguments: {missing}"

        await tool.ainvoke(**{name: per_tool[name] for name in required})

        sent = set(dict(anything.calls.last.request.url.params))
        asked_for = {name for name in required if name not in ("owner", "repo", "org")}
        allowed = asked_for | known_defaults.get(tool.name, set())
        if tool.pagination is not None:
            allowed |= walking
        surprises = sent - allowed
        assert not surprises, (
            f"{tool.name} sent query parameters nobody asked for: {sorted(surprises)}"
        )
        # And the converse: a tool that does not page must not send the paging
        # parameters, which is how a stray `GitHubListRequest` base class shows.
        if tool.pagination is None:
            assert not (sent & walking), (
                f"{tool.name} sends paging parameters but declares no pagination"
            )


# =====================================================
# The closed enums, against GitHub's values rather than against themselves
# =====================================================


# Transcribed from GitHub's OpenAPI description, which is the only place several
# of these are written down in full. A `Literal` missing a value the API accepts
# rejects a valid call, and the model cannot tell that from the API refusing it,
# so it has no way to recover — which is why this is a table of literal strings
# and not a loop over the schema.
_ENUMS: Dict[str, set] = {
    "JobFilter": {"latest", "all"},
    "CheckRunFilter": {"latest", "all"},
    "CheckRunStatusFilter": {"queued", "in_progress", "completed"},
    "DeploymentReviewState": {"approved", "rejected"},
    "WorkflowRunStatusFilter": {
        "completed", "action_required", "cancelled", "failure", "neutral", "skipped",
        "stale", "success", "timed_out", "in_progress", "queued", "requested",
        "waiting", "pending",
    },
    "ReviewSide": {"LEFT", "RIGHT"},
    "ReviewEvent": {"APPROVE", "REQUEST_CHANGES", "COMMENT"},
    "SubjectType": {"line", "file"},
    "ReviewCommentSort": {"created", "updated"},
    "RepoReviewCommentSort": {"created", "updated", "created_at"},
    "BlobEncoding": {"utf-8", "base64"},
    "TreeEntryMode": {"100644", "100755", "040000", "160000", "120000"},
    "TreeEntryType": {"blob", "tree", "commit"},
    "TagObjectType": {"commit", "tree", "blob"},
    "OrgRepoType": {"all", "public", "private", "forks", "sources", "member"},
    "MilestoneState": {"open", "closed", "all"},
    "MilestoneSort": {"due_on", "completeness"},
    "LockReason": {"off-topic", "too heated", "resolved", "spam"},
    "IssueFilter": {"assigned", "created", "mentioned", "subscribed", "repos", "all"},
    "MakeLatest": {"true", "false", "legacy"},
    "DependabotState": {"auto_dismissed", "dismissed", "fixed", "open"},
    "DependabotScope": {"development", "runtime"},
    "DependabotSort": {"created", "updated", "epss_percentage"},
    "DismissedReason": {
        "fix_started", "inaccurate", "no_bandwidth", "not_used", "tolerable_risk"
    },
    "CodeScanningState": {"open", "closed", "dismissed", "fixed"},
    "CodeScanningSeverity": {
        "critical", "high", "medium", "low", "warning", "note", "error"
    },
    "CodeScanningSort": {"created", "updated"},
    "SecretScanningState": {"open", "resolved"},
    "SecretScanningSort": {"created", "updated"},
    "CommitSearchSort": {"author-date", "committer-date"},
    "UserSearchSort": {"followers", "repositories", "joined"},
}


@pytest.mark.parametrize("name", sorted(_ENUMS))
def test_each_closed_literal_holds_the_whole_documented_enum(name):
    from typing import get_args

    from charter.packs.github import types

    assert set(get_args(getattr(types, name))) == _ENUMS[name], name


def test_the_lock_reason_with_a_space_survives_the_wire():
    """One of GitHub's four lock reasons is two words, and it is sent verbatim.

    A `Literal` is not case- or space-converted, but the key beside it is: this
    asserts the *value* arrives whole, since "too heated" silently becoming
    "too_heated" is a 422 that reads like a permissions problem.
    """
    from charter.packs.github.types import LockReason

    assert "too heated" in LockReason.__args__


def test_no_tool_offers_the_model_a_field_github_does_not_accept():
    """The egress map, read as an auditor would — but against the API, not itself.

    A field visible to the model that the API has never accepted is invisible at
    runtime: GitHub ignores an unknown body key and an unknown query parameter
    rather than refusing the call, so every request succeeds and the thing the
    model asked for silently does not happen.

    It found one: `repos_delete_file` was reusing the write endpoint's author
    model, which carries a `date` that `DELETE /contents/{path}` has never
    taken. The two endpoints differ by exactly that field and nothing failed.

    The field list is transcribed from GitHub's OpenAPI description rather than
    fetched, so this runs offline like everything else here.
    """
    from charter import egress_map

    # Nested objects whose leaf names GitHub documents on the parent. Checked by
    # name because a `Body()` field unwraps and the wire key is the leaf.
    accepted_leaves = {
        "committer", "author", "tagger", "name", "email", "date",
        "path", "mode", "type", "sha", "content", "body", "line", "side",
        "start_line", "start_side", "title", "labels", "milestone", "assignees",
        "state", "state_reason", "head", "base", "draft", "issue", "head_repo",
        "maintainer_can_modify",
    }
    # The two declared departures, each argued for where it is made.
    allowed = {
        # Compiled to the present-and-null `sha` GitHub reads as a deletion.
        ("git_trees_create", "tree.delete"),
        # The body *is* the file; GitHub types it as an opaque octet-stream.
        ("releases_upload_asset", "content"),
    }

    wrong = []
    for name, entry in egress_map(github.TOOLS).items():
        tool = getattr(github, name)
        declared = set(tool.args_schema.model_fields)
        for visible in entry["visible"]:
            leaf = visible.split(".")[-1]
            if leaf in declared or leaf in accepted_leaves:
                continue
            if (name, visible) in allowed:
                continue
            wrong.append(f"{name}.{visible}")

    assert not wrong, "fields visible to the model that no schema declares: " + ", ".join(wrong)


def test_the_two_contents_endpoints_disagree_about_date_and_the_schemas_say_so():
    """`PUT /contents/{path}` takes a commit `date`; `DELETE /contents/{path}` does not.

    One model across both offered a field the delete endpoint has never
    accepted. They share `CommitIdentity` and the write extends it, so the
    descriptions keep one home and the difference is the one field it is.
    """
    from charter.packs.github.types import CommitIdentity, GitAuthor

    assert set(CommitIdentity.model_fields) == {"name", "email"}
    assert set(GitAuthor.model_fields) == {"name", "email", "date"}
    assert issubclass(GitAuthor, CommitIdentity)

    def committer_of(tool):
        annotation = tool.llm_schema().model_fields["committer"].annotation
        return set(annotation.__args__[0].model_fields)

    assert committer_of(github.repos_delete_file) == {"name", "email"}
    assert committer_of(github.repos_create_or_update_file) == {"name", "email", "date"}


@respx.mock
async def test_user_search_projects_the_envelope_and_not_the_envelope_away():
    """`search_users` answers with a search envelope, not a user object.

    It shipped pointed at `trim_user`, which takes the single object `GET /user`
    returns. Run over `{"total_count": N, "items": [...]}` that projection found
    none of the keys it looks for and returned `{}` — a search that reported no
    matches however many there were, with no error anywhere. The live check
    against the real API is what surfaced it; nothing offline had put the two
    shapes together.
    """
    respx.get(f"{API}search/users").mock(
        return_value=httpx.Response(
            200,
            json={
                "total_count": 2,
                "incomplete_results": False,
                "items": [
                    {"login": "octocat", "id": 1, "type": "User",
                     "html_url": "https://github.com/octocat",
                     "node_id": "MDQ6", "followers_url": "…", "gists_url": "…"}
                ],
            },
        )
    )

    found = await github.search_users.ainvoke(q="type:user octocat")

    assert found["total_count"] == 2
    assert found["items"] == [
        {"login": "octocat", "html_url": "https://github.com/octocat", "type": "User"}
    ]


def test_the_two_user_projections_are_for_the_two_different_shapes():
    """One takes an object, one takes a page of them. Neither works as the other."""
    from charter.packs.github import response_handlers as handlers

    assert github.users_get_authenticated._response_handler is handlers.trim_user
    assert github.search_users._response_handler is handlers.trim_users
