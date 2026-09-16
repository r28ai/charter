"""
Linear, read and written directly over GraphQL.

Fixtures are issues whose title carries ``[<ns>]``; read-back filters on the
same tag. Teardown deletes them (``issueDelete`` moves to trash), so the
workspace does not fill up.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from charter_harness.world._http import Http, WorldError, eventually

__all__ = ["Linear"]

_ISSUE_FIELDS = """
  id identifier title description priority trashed
  state { id name type }
  labels { nodes { id name } }
  comments { nodes { id body createdAt } }
"""


class Linear:
    def __init__(self, http: Http, *, team_key: str) -> None:
        self.http = http
        self.team_key = team_key
        self._team_id: str | None = None
        self._states: list[dict[str, Any]] | None = None

    async def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        data = await self.http.json("POST", "graphql", json={"query": query, "variables": variables or {}})
        if data.get("errors"):
            raise WorldError(f"Linear GraphQL error: {data['errors']}", status=200, body=str(data)[:2000])
        return data["data"]

    async def team_id(self) -> str:
        if self._team_id is None:
            data = await self.gql("query($key: String!) { teams(filter: { key: { eq: $key } }) { nodes { id key } } }", {"key": self.team_key})
            nodes = data["teams"]["nodes"]
            if not nodes:
                raise WorldError(f"No Linear team with key {self.team_key!r}")
            self._team_id = str(nodes[0]["id"])
        return str(self._team_id)

    async def workflow_states(self) -> list[dict[str, Any]]:
        if self._states is None:
            team = await self.team_id()
            data = await self.gql(
                "query($team: ID!) { workflowStates(filter: { team: { id: { eq: $team } } }) { nodes { id name type position } } }",
                {"team": team},
            )
            self._states = sorted(data["workflowStates"]["nodes"], key=lambda s: s["position"])
        return self._states

    async def state_by_type(self, type_: str) -> dict[str, Any]:
        for state in await self.workflow_states():
            if state["type"] == type_:
                return state
        raise WorldError(f"Team {self.team_key} has no workflow state of type {type_!r}")

    async def state_by_name(self, name: str) -> dict[str, Any] | None:
        for state in await self.workflow_states():
            if state["name"].lower() == name.lower():
                return state
        return None

    async def issue_create(
        self,
        *,
        title: str,
        description: str = "",
        state_id: str | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"teamId": await self.team_id(), "title": title, "description": description}
        if state_id:
            payload["stateId"] = state_id
        if priority is not None:
            payload["priority"] = priority
        data = await self.gql(
            "mutation($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { " + _ISSUE_FIELDS + " } } }",
            {"input": payload},
        )
        return data["issueCreate"]["issue"]

    async def issues_tagged(self, tag: str) -> list[dict[str, Any]]:
        team = await self.team_id()
        data = await self.gql(
            "query($team: ID!, $tag: String!) { issues(first: 100, filter: { team: { id: { eq: $team } }, title: { containsIgnoreCase: $tag } }) { nodes { "
            + _ISSUE_FIELDS
            + " } } }",
            {"team": team, "tag": tag},
        )
        return data["issues"]["nodes"]

    async def await_tagged(self, tag: str, ids: Sequence[str], *, timeout: float = 90.0) -> list[dict[str, Any]]:
        """Block until every issue in ``ids`` is returned by the title filter.

        Linear serves ``title: { containsIgnoreCase }`` from an index that lags
        creation by seconds to tens of seconds under load. A seed that returns
        before its fixtures are visible hands the model — and the observer — a
        world with nothing in it, which reads as a model failure. So the seed
        waits here, and a fixture that never shows up is a harness error.
        """
        wanted = set(ids)
        issues = await eventually(
            lambda: self.issues_tagged(tag), lambda got: wanted <= {i["id"] for i in got}, timeout=timeout, interval=2.0
        )
        missing = wanted - {i["id"] for i in issues}
        if missing:
            raise WorldError(f"{len(missing)} Linear issue(s) tagged {tag!r} not visible to the title filter after {timeout:.0f}s")
        return issues

    async def issues_by_ids(self, ids: Sequence[str]) -> list[dict[str, Any]]:
        """Direct lookups — strongly consistent, unlike the title filter."""
        out = []
        for issue_id in ids:
            issue = await self.issue_get(issue_id)
            if issue is not None and not issue.get("trashed"):
                out.append(issue)
        return out

    async def issues_tagged_eventually(self, tag: str, *, at_least: int, timeout: float = 45.0) -> list[dict[str, Any]]:
        """The tag query, retried until it returns ``at_least`` issues or time is up.

        For read-backs of issues the *model* created: their ids are unknown, so
        the filter is the only way in, and it may still be catching up.
        """
        return await eventually(lambda: self.issues_tagged(tag), lambda got: len(got) >= at_least, timeout=timeout, interval=3.0)

    async def issue_get(self, issue_id: str) -> dict[str, Any] | None:
        try:
            data = await self.gql("query($id: String!) { issue(id: $id) { " + _ISSUE_FIELDS + " } }", {"id": issue_id})
        except WorldError:
            return None
        return data.get("issue")

    async def comment_create(self, issue_id: str, body: str) -> dict[str, Any]:
        data = await self.gql(
            "mutation($input: CommentCreateInput!) { commentCreate(input: $input) { success comment { id body } } }",
            {"input": {"issueId": issue_id, "body": body}},
        )
        return data["commentCreate"]["comment"]

    async def issue_delete(self, issue_id: str) -> None:
        try:
            await self.gql("mutation($id: String!) { issueDelete(id: $id) { success } }", {"id": issue_id})
        except WorldError:
            pass

    async def delete_tagged(self, tag: str) -> int:
        issues = await self.issues_tagged(tag)
        for issue in issues:
            await self.issue_delete(issue["id"])
        return len(issues)

    @staticmethod
    def identifiers(issues: Sequence[dict[str, Any]]) -> list[str]:
        return [i["identifier"] for i in issues]
