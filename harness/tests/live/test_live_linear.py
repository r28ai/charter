"""Linear, against the real workspace, over GraphQL.

Two of this pack's corrections came off the published schema and neither is
visible to a mock: ``issueSearch`` was deprecated in favour of ``searchIssues``,
and ``issueArchive`` returns its result under ``entity`` rather than ``issue``.
A constant GraphQL document is either the one the server still knows or it is
not, and only the server can say which.

Everything here is created in the team ``LINEAR_TEAM_KEY`` names and deleted on
the way out. Linear's ``issueDelete`` moves to trash rather than erasing, which
is the most a live suite should do to a workspace anyway.
"""

from __future__ import annotations

import pytest
from charter.packs import linear

pytestmark = pytest.mark.live


async def _team_id(world) -> str:
    return await world.linear.team_id()


async def _issue(world, trash, run_tag: str, *, title: str, **fields) -> dict:
    """One issue through the pack, trashed on the way out."""
    made = await linear.issue_create.ainvoke(
        {
            "variables": {
                "input": {"teamId": await _team_id(world), "title": title, **fields}
            }
        }
    )
    issue = made["issue"]
    trash.later(lambda: world.linear.issue_delete(issue["id"]))
    return issue


# -----------------------------------------------------
# Resolving names to UUIDs, which every write depends on
# -----------------------------------------------------


async def test_the_lookups_resolve_what_the_writes_require(needs, settings):
    """``teams_list``, ``users_list``, ``viewer`` and ``workflow_states_list``
    exist so that an agent holding a team key, a person's name or the word 'me'
    can reach the UUID Linear actually wants. Each is checked against the thing
    it has to resolve."""
    needs("linear")

    teams = await linear.teams_list.ainvoke({"variables": {"first": 50}})
    mine = [t for t in teams["nodes"] if t["key"] == settings.linear_team_key]
    assert mine, f"no team keyed {settings.linear_team_key}"

    me = await linear.viewer.ainvoke({})
    assert me["id"]

    users = await linear.users_list.ainvoke(
        {"variables": {"first": 50, "filter": {"email": {"eq": me["email"]}}}}
    )
    assert [u["id"] for u in users["nodes"]] == [me["id"]]

    states = await linear.workflow_states_list.ainvoke(
        {
            "variables": {
                "first": 50,
                "filter": {"team": {"key": {"eq": settings.linear_team_key}}},
            }
        }
    )
    # Linear's real set. The pack's docstring names five of these — `duplicate`
    # and `triage` are missing from it, and this workspace has a Duplicate state,
    # so the omission is not hypothetical. An agent that reasons "there are five
    # types" from the tool description gets this team wrong.
    assert {s["type"] for s in states["nodes"]} <= {
        "backlog",
        "unstarted",
        "started",
        "completed",
        "canceled",
        "duplicate",
        "triage",
    }
    assert any(s["type"] == "completed" for s in states["nodes"])


# -----------------------------------------------------
# An issue, end to end
# -----------------------------------------------------


async def test_an_issue_is_created_moved_and_closed(needs, world, trash, run_tag, settings):
    """Linear has no `close` — an issue is closed by moving it to a state whose
    type is 'completed'. That is the whole reason ``workflow_states_list``
    exists, so the two are tested together."""
    needs("linear")
    states = await linear.workflow_states_list.ainvoke(
        {
            "variables": {
                "first": 50,
                "filter": {"team": {"key": {"eq": settings.linear_team_key}}},
            }
        }
    )
    done = next(s for s in states["nodes"] if s["type"] == "completed")

    issue = await _issue(
        world,
        trash,
        run_tag,
        title=f"Live check {run_tag}",
        description="Opened by the live suite.",
        priority=2,
    )
    assert issue["priority"] == 2
    assert issue["identifier"].startswith(settings.linear_team_key)

    found = await linear.issue_get.ainvoke({"variables": {"id": issue["identifier"]}})
    # The human identifier resolves as well as the UUID, which is what the
    # docstring claims and what an agent reading a Slack message will have.
    assert found["id"] == issue["id"]
    assert found["description"] == "Opened by the live suite."

    moved = await linear.issue_update.ainvoke(
        {
            "variables": {
                "id": issue["id"],
                "input": {"stateId": done["id"], "title": f"Live check {run_tag}, done"},
            }
        }
    )
    assert moved["issue"]["state"]["type"] == "completed"
    assert moved["issue"]["title"].endswith("done")


async def test_an_issue_is_archived_and_restored(needs, world, trash, run_tag):
    """``issueArchive`` returns its payload under ``entity``, not ``issue``. A
    handler reading the wrong key gets ``None`` and reports success."""
    needs("linear")
    issue = await _issue(world, trash, run_tag, title=f"Live archive {run_tag}")

    archived = await linear.issue_archive.ainvoke({"variables": {"id": issue["id"]}})
    assert archived["entity"]["id"] == issue["id"]

    restored = await linear.issue_unarchive.ainvoke({"variables": {"id": issue["id"]}})
    assert restored["entity"]["id"] == issue["id"]


# -----------------------------------------------------
# Comments: the dead end this pack closed
# -----------------------------------------------------


async def test_a_comment_can_be_posted_read_back_and_edited(needs, world, trash, run_tag):
    """The pack could post a comment and had no way to read one. All three tools
    in the order an agent uses them."""
    needs("linear")
    issue = await _issue(world, trash, run_tag, title=f"Live comments {run_tag}")

    posted = await linear.comment_create.ainvoke(
        {"variables": {"input": {"issueId": issue["id"], "body": "First, from the live suite."}}}
    )
    comment = posted["comment"]
    assert comment["body"] == "First, from the live suite."

    thread = await linear.comments_list.ainvoke(
        {"variables": {"first": 50, "filter": {"issue": {"id": {"eq": issue["id"]}}}}}
    )
    assert [c["id"] for c in thread["nodes"]] == [comment["id"]]

    edited = await linear.comment_update.ainvoke(
        {"variables": {"id": comment["id"], "input": {"body": "Edited by the live suite."}}}
    )
    assert edited["comment"]["body"] == "Edited by the live suite."

    reread = await linear.comments_list.ainvoke(
        {"variables": {"first": 50, "filter": {"issue": {"id": {"eq": issue["id"]}}}}}
    )
    assert reread["nodes"][0]["body"] == "Edited by the live suite."


# -----------------------------------------------------
# Labels and projects
# -----------------------------------------------------


async def test_a_label_is_created_and_put_on_an_issue(needs, world, trash, run_tag, settings):
    """``issue_create`` takes ``labelIds``, which means a label has to exist
    first — the reason ``issue_label_create`` is in the pack at all."""
    needs("linear")
    team = await _team_id(world)

    label = await linear.issue_label_create.ainvoke(
        {
            "variables": {
                "input": {
                    "name": f"live-{run_tag}",
                    "color": "#4EA7FC",
                    "teamId": team,
                }
            }
        }
    )
    label_id = label["issueLabel"]["id"]
    trash.later(
        lambda: world.linear.gql(
            "mutation($id: String!) { issueLabelDelete(id: $id) { success } }", {"id": label_id}
        )
    )

    listed = await linear.issue_labels_list.ainvoke(
        {"variables": {"first": 50, "filter": {"name": {"eq": f"live-{run_tag}"}}}}
    )
    assert [n["id"] for n in listed["nodes"]] == [label_id]

    issue = await _issue(
        world, trash, run_tag, title=f"Live labelled {run_tag}", labelIds=[label_id]
    )
    assert [label["name"] for label in issue["labels"]["nodes"]] == [f"live-{run_tag}"]


async def test_a_project_is_created_updated_and_listed(needs, world, trash, run_tag):
    needs("linear")
    team = await _team_id(world)

    created = await linear.project_create.ainvoke(
        {
            "variables": {
                "input": {
                    "name": f"Live project {run_tag}",
                    "teamIds": [team],
                    "description": "Made by the live suite.",
                }
            }
        }
    )
    project = created["project"]
    trash.later(
        lambda: world.linear.gql(
            "mutation($id: String!) { projectDelete(id: $id) { success } }",
            {"id": project["id"]},
        )
    )

    updated = await linear.project_update.ainvoke(
        {"variables": {"id": project["id"], "input": {"state": "started"}}}
    )
    assert updated["project"]["state"] == "started"

    listed = await linear.projects_list.ainvoke({"variables": {"first": 50}})
    assert project["id"] in [p["id"] for p in listed["nodes"]]


# -----------------------------------------------------
# Finding things
# -----------------------------------------------------


async def test_the_issue_filters_narrow_rather_than_erroring(needs, world, trash, run_tag, settings):
    """``issues_list`` filters combine with AND, and each comparator here is one
    Linear could have renamed. An unknown filter field is a GraphQL error, not a
    silently ignored parameter, which is what makes this worth asserting live."""
    needs("linear")
    issue = await _issue(world, trash, run_tag, title=f"Live filter {run_tag}")

    listed = await linear.issues_list.ainvoke(
        {
            "variables": {
                "first": 50,
                "filter": {
                    "team": {"key": {"eq": settings.linear_team_key}},
                    "title": {"containsIgnoreCase": run_tag},
                },
                "orderBy": "createdAt",
            }
        }
    )
    assert issue["id"] in [i["id"] for i in listed["nodes"]]


async def test_search_issues_is_the_endpoint_that_replaced_issue_search(
    needs, world, trash, run_tag
):
    """``issueSearch`` is deprecated; this document names ``searchIssues``.

    The result is not asserted to contain the issue this test just made: Linear's
    full-text index lags creation by seconds to tens of seconds, and a test that
    waited on it would be testing the index. That the *document* is accepted is
    the assertion — a deprecated field would be a GraphQL error here.
    """
    needs("linear")
    await _issue(world, trash, run_tag, title=f"Live search {run_tag}")

    found = await linear.search_issues.ainvoke(
        {"variables": {"first": 10, "term": run_tag, "includeComments": True}}
    )
    assert "nodes" in found
